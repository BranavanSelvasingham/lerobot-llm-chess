#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_calibration_sidecars"
SCHEMA = "lerobot.sim.real_calibration_sidecars.v1"
SIDECAR_SCHEMA_PREFIX = "lerobot.sim.real_calibration_sidecar"

INTRINSICS_PATH_KEYS = (
    "real_intrinsics_path",
    "camera_intrinsics_path",
    "intrinsics_path",
    "real_camera_calibration_path",
    "camera_calibration_path",
)
EXTRINSICS_PATH_KEYS = (
    "real_extrinsics_path",
    "camera_extrinsics_path",
    "extrinsics_path",
    "real_camera_pose_path",
)
BOARD_POSE_PATH_KEYS = (
    "real_board_pose_path",
    "board_pose_path",
    "board_corner_detections_path",
    "board_corners_path",
    "corner_detections_path",
)
DEPTH_PATH_KEYS = ("real_depth_path", "depth_map_path", "depth_reference_path", "metric_depth_reference_path")

SUPPORTED_KINDS = ("intrinsics", "extrinsics", "board_pose", "depth")
SIDE_CAR_PATH_KEYS = {
    "intrinsics": INTRINSICS_PATH_KEYS,
    "extrinsics": EXTRINSICS_PATH_KEYS,
    "board_pose": BOARD_POSE_PATH_KEYS,
    "depth": DEPTH_PATH_KEYS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate hardware-free real calibration sidecar JSON files declared by a "
            "reference-media manifest or supplied directly."
        )
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--sidecar", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--require-valid-count", type=int, default=0)
    parser.add_argument(
        "--expect-invalid",
        action="store_true",
        help="Require at least one invalid sidecar while still returning success.",
    )
    return parser.parse_args()


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def repo_relative(path: Path, repo_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def resolve_repo_path(value: str, repo_root: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def is_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_number_matrix(value: Any, *, rows: int, cols: int, field: str) -> list[str]:
    issues: list[str] = []
    if not isinstance(value, list) or len(value) != rows:
        return [f"{field} must be a {rows}x{cols} numeric array."]
    for row_index, row in enumerate(value):
        if not isinstance(row, list) or len(row) != cols:
            issues.append(f"{field}[{row_index}] must contain {cols} numeric values.")
            continue
        for col_index, item in enumerate(row):
            if not is_number(item):
                issues.append(f"{field}[{row_index}][{col_index}] must be a finite number.")
    return issues


def validate_number_list(value: Any, *, length: int | None, field: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{field} must be a numeric array."]
    if length is not None and len(value) != length:
        return [f"{field} must contain {length} values."]
    issues: list[str] = []
    for index, item in enumerate(value):
        if not is_number(item):
            issues.append(f"{field}[{index}] must be a finite number.")
    return issues


def validate_image_size(payload: dict[str, Any], issues: list[str]) -> None:
    image_size = payload.get("image_size_px")
    if (
        not isinstance(image_size, list)
        or len(image_size) != 2
        or not all(is_number(item) for item in image_size)
    ):
        issues.append("image_size_px must be [width_px, height_px].")
        return
    if int(image_size[0]) <= 0 or int(image_size[1]) <= 0:
        issues.append("image_size_px values must be positive.")


def validate_intrinsics(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    validate_image_size(payload, issues)
    issues.extend(
        validate_number_matrix(payload.get("camera_matrix_px"), rows=3, cols=3, field="camera_matrix_px")
    )
    distortion = payload.get("distortion_coefficients")
    if not isinstance(distortion, list) or len(distortion) < 4:
        issues.append("distortion_coefficients must contain at least four numeric values.")
    else:
        issues.extend(validate_number_list(distortion, length=None, field="distortion_coefficients"))
    if not is_string(payload.get("camera_id")):
        issues.append("camera_id is required so sidecars can be tied to a capture source.")
    if not is_string(payload.get("calibration_source")):
        issues.append(
            "calibration_source is required and should say synthetic/example or real capture source."
        )
    if not is_string(payload.get("units")) or payload.get("units") != "pixels":
        issues.append('units must be "pixels" for intrinsics.')
    return issues


def validate_transform(payload: dict[str, Any], issues: list[str]) -> None:
    transform = payload.get("transform")
    if isinstance(transform, dict):
        matrix = transform.get("matrix_4x4")
        translation = transform.get("translation_m")
        rotation = transform.get("rotation_matrix")
    else:
        matrix = payload.get("matrix_4x4")
        translation = payload.get("translation_m")
        rotation = payload.get("rotation_matrix")
    if matrix is not None:
        issues.extend(validate_number_matrix(matrix, rows=4, cols=4, field="transform.matrix_4x4"))
    else:
        issues.extend(validate_number_list(translation, length=3, field="transform.translation_m"))
        issues.extend(validate_number_matrix(rotation, rows=3, cols=3, field="transform.rotation_matrix"))


def validate_extrinsics(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    convention = payload.get("transform_convention")
    if convention not in {"board_to_camera", "camera_to_board"}:
        issues.append('transform_convention must be "board_to_camera" or "camera_to_board".')
    if not is_string(payload.get("camera_id")):
        issues.append("camera_id is required so extrinsics match intrinsics.")
    if not is_string(payload.get("coordinate_frame_convention")):
        issues.append("coordinate_frame_convention is required.")
    validate_transform(payload, issues)
    return issues


def validate_corner_detection(corner: Any, *, index: int) -> list[str]:
    issues: list[str] = []
    if not isinstance(corner, dict):
        return [f"corners[{index}] must be an object."]
    if corner.get("label") not in {"a1", "h1", "h8", "a8"}:
        issues.append(f"corners[{index}].label must be one of a1,h1,h8,a8.")
    xy = corner.get("pixel_xy")
    if not isinstance(xy, list) or len(xy) != 2 or not all(is_number(item) for item in xy):
        issues.append(f"corners[{index}].pixel_xy must be [x_px, y_px].")
    confidence = corner.get("confidence")
    if confidence is not None and (
        not is_number(confidence) or float(confidence) < 0.0 or float(confidence) > 1.0
    ):
        issues.append(f"corners[{index}].confidence must be between 0 and 1 when supplied.")
    return issues


def validate_board_pose(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    validate_image_size(payload, issues)
    corner_order = payload.get("corner_order")
    if corner_order != ["a1", "h1", "h8", "a8"]:
        issues.append('corner_order must be ["a1", "h1", "h8", "a8"].')
    corners = payload.get("corners")
    if not isinstance(corners, list) or len(corners) != 4:
        issues.append("corners must contain four ordered board-corner detections.")
    else:
        labels = [corner.get("label") for corner in corners if isinstance(corner, dict)]
        if labels != ["a1", "h1", "h8", "a8"]:
            issues.append("corners labels must appear in a1,h1,h8,a8 order.")
        for index, corner in enumerate(corners):
            issues.extend(validate_corner_detection(corner, index=index))
    board_size = payload.get("board_size_m")
    if board_size is not None and (not is_number(board_size) or float(board_size) <= 0.0):
        issues.append("board_size_m must be positive when supplied.")
    if "transform_convention" in payload or "transform" in payload or "matrix_4x4" in payload:
        pose_issues: list[str] = []
        validate_transform(payload, pose_issues)
        issues.extend(pose_issues)
    if not is_string(payload.get("detection_source")):
        issues.append("detection_source is required.")
    return issues


def validate_depth(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    units = payload.get("depth_units")
    if units not in {"m", "mm"}:
        issues.append('depth_units must be "m" or "mm".')
    scale = payload.get("depth_scale_to_m")
    if not is_number(scale) or float(scale) <= 0.0:
        issues.append("depth_scale_to_m must be a positive number.")
    if not is_string(payload.get("reference_frame")):
        issues.append("reference_frame is required.")
    metric_references = payload.get("metric_references")
    depth_map = payload.get("depth_map")
    if metric_references is None and depth_map is None:
        issues.append("Provide metric_references or depth_map metadata.")
    if metric_references is not None:
        if not isinstance(metric_references, list) or not metric_references:
            issues.append("metric_references must be a non-empty array when supplied.")
        else:
            for index, reference in enumerate(metric_references):
                if not isinstance(reference, dict):
                    issues.append(f"metric_references[{index}] must be an object.")
                    continue
                if not is_string(reference.get("id")):
                    issues.append(f"metric_references[{index}].id is required.")
                distance_m = reference.get("distance_m")
                if not is_number(distance_m) or float(distance_m) <= 0.0:
                    issues.append(f"metric_references[{index}].distance_m must be positive.")
            point = reference.get("pixel_xy")
            if point is not None and (
                not isinstance(point, list)
                or len(point) != 2
                or not all(is_number(item) for item in point)
            ):
                issues.append(f"metric_references[{index}].pixel_xy must be [x_px, y_px] when supplied.")
    if depth_map is not None and not isinstance(depth_map, dict):
        issues.append("depth_map must be an object when supplied.")
    return issues


def infer_kind(payload: dict[str, Any], path: Path) -> str:
    kind = payload.get("sidecar_type")
    if isinstance(kind, str) and kind in SUPPORTED_KINDS:
        return kind
    schema = payload.get("schema")
    if isinstance(schema, str):
        for candidate in SUPPORTED_KINDS:
            if candidate in schema:
                return candidate
    name = path.name.lower()
    for candidate in SUPPORTED_KINDS:
        if candidate in name:
            return candidate
    if "corner" in name:
        return "board_pose"
    return "unknown"


def validate_sidecar_payload(payload: dict[str, Any], *, path: Path) -> tuple[str, list[str]]:
    kind = infer_kind(payload, path)
    issues: list[str] = []
    schema = payload.get("schema")
    if not isinstance(schema, str) or not schema.startswith(SIDECAR_SCHEMA_PREFIX):
        issues.append(f"schema must start with {SIDECAR_SCHEMA_PREFIX}.")
    if payload.get("example_only") is not True and payload.get("real_capture") is not True:
        issues.append(
            "Set example_only=true for synthetic fixtures or real_capture=true for real calibration sidecars."
        )
    if kind == "intrinsics":
        issues.extend(validate_intrinsics(payload))
    elif kind == "extrinsics":
        issues.extend(validate_extrinsics(payload))
    elif kind == "board_pose":
        issues.extend(validate_board_pose(payload))
    elif kind == "depth":
        issues.extend(validate_depth(payload))
    else:
        issues.append("Could not infer sidecar_type; expected intrinsics, extrinsics, board_pose, or depth.")
    return kind, issues


def validate_sidecar_path(path: Path, *, repo_root: Path, source: str) -> dict[str, Any]:
    exists = path.is_file()
    result: dict[str, Any] = {
        "source": source,
        "path": str(path),
        "repo_relative_path": repo_relative(path, repo_root),
        "exists": exists,
        "kind": "unknown",
        "ok": False,
        "status": "missing",
        "issues": [],
    }
    if not exists:
        result["issues"] = ["Sidecar path does not exist."]
        return result
    try:
        payload = read_json_object(path, label="sidecar")
    except ValueError as exc:
        result["status"] = "invalid_json"
        result["issues"] = [str(exc)]
        return result
    kind, issues = validate_sidecar_payload(payload, path=path)
    result.update(
        {
            "kind": kind,
            "schema": payload.get("schema"),
            "sidecar_type": payload.get("sidecar_type"),
            "example_only": payload.get("example_only"),
            "real_capture": payload.get("real_capture"),
            "ok": not issues,
            "status": "valid" if not issues else "invalid",
            "issues": issues,
        }
    )
    return result


def manifest_declared_paths(manifest_path: Path, *, repo_root: Path) -> list[tuple[str, Path]]:
    manifest = read_json_object(manifest_path, label="manifest")
    media = manifest.get("media")
    if not isinstance(media, list):
        raise ValueError(f"manifest {manifest_path} must contain a media array.")
    paths: list[tuple[str, Path]] = []
    for media_index, entry in enumerate(media, start=1):
        if not isinstance(entry, dict):
            continue
        for kind, keys in SIDE_CAR_PATH_KEYS.items():
            for key in keys:
                value = entry.get(key)
                if isinstance(value, str) and value:
                    paths.append(
                        (f"manifest.media[{media_index}].{key}:{kind}", resolve_repo_path(value, repo_root))
                    )
                    break
    return paths


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    path_sources: list[tuple[str, Path]] = []
    if args.manifest is not None:
        manifest_path = args.manifest.expanduser()
        if not manifest_path.is_absolute():
            manifest_path = (repo_root / manifest_path).resolve()
        path_sources.extend(manifest_declared_paths(manifest_path, repo_root=repo_root))
    for index, sidecar in enumerate(args.sidecar, start=1):
        path = sidecar.expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        path_sources.append((f"sidecar[{index}]", path))

    validations = [
        validate_sidecar_path(path, repo_root=repo_root, source=source)
        for source, path in path_sources
    ]
    valid_count = sum(1 for item in validations if item.get("ok") is True)
    invalid_count = sum(1 for item in validations if item.get("ok") is not True)
    kinds_validated = sorted({str(item.get("kind")) for item in validations if item.get("ok") is True})
    requirements_met = valid_count >= args.require_valid_count and (
        invalid_count > 0 if args.expect_invalid else invalid_count == 0
    )
    status = "ok" if requirements_met else "validation_failed"
    summary = {
        "schema": SCHEMA,
        "ok": requirements_met,
        "status": status,
        "output_dir": str(output_dir),
        "repo_root": str(repo_root),
        "manifest_path": str(args.manifest) if args.manifest is not None else None,
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "openai_skipped": True,
        "required_valid_count": args.require_valid_count,
        "expect_invalid": bool(args.expect_invalid),
        "declared_sidecar_count": len(validations),
        "valid_sidecar_count": valid_count,
        "invalid_sidecar_count": invalid_count,
        "kinds_validated": kinds_validated,
        "validations": validations,
        "notes": [
            (
                "This validator checks sidecar shape only; it does not capture real camera data "
                "or assert calibration truth."
            ),
            (
                "Synthetic fixtures should use example_only=true unless they are explicitly "
                "labelled test-only real_capture fixtures for residual plumbing; neither form "
                "proves hardware calibration truth."
            ),
        ],
    }
    write_json(output_dir / "real_calibration_sidecars.json", summary)
    return summary


def main() -> int:
    args = parse_args()
    try:
        summary = build_summary(args)
    except ValueError as exc:
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "status": "validation_failed",
            "output_dir": str(output_dir),
            "error": str(exc),
            "hardware_skipped": True,
            "gui_skipped": True,
            "real_camera_capture_skipped": True,
            "openai_skipped": True,
            "validations": [],
        }
        write_json(output_dir / "real_calibration_sidecars.json", summary)
    print(json.dumps(summary, indent=2))
    if not summary["ok"]:
        print(f"ERROR: real calibration sidecar validation status={summary['status']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
