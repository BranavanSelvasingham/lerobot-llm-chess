#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from smoke_sim_real_calibration_sidecars import validate_sidecar_path, validate_sidecar_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_projection_intake"
SCHEMA = "lerobot.sim.real_projection_intake.v1"
OUTPUT_JSON_NAME = "real_projection_intake.json"
OUTPUT_CSV_NAME = "real_projection_intake.csv"
OUTPUT_PNG_NAME = "real_projection_intake_contact_sheet.png"
RESIDUAL_JSON_NAME = "real_projection_residuals.json"
RESIDUAL_CSV_NAME = "real_projection_residuals.csv"
RESIDUAL_PNG_NAME = "real_projection_residual_overlay_contact_sheet.png"
BOARD_CORNER_LABELS = ("a1", "h1", "h8", "a8")
SIM_BOARD_CORNER_LABELS = {
    "a1": "board_corner_a1",
    "h1": "board_corner_h1",
    "h8": "board_corner_h8",
    "a8": "board_corner_a8",
}

INTRINSICS_PATH_KEYS = (
    "real_intrinsics_path",
    "camera_intrinsics_path",
    "intrinsics_path",
    "real_camera_calibration_path",
    "camera_calibration_path",
)
INTRINSICS_INLINE_KEYS = ("real_intrinsics", "camera_intrinsics", "intrinsics")
EXTRINSICS_PATH_KEYS = (
    "real_extrinsics_path",
    "camera_extrinsics_path",
    "extrinsics_path",
    "real_camera_pose_path",
)
EXTRINSICS_INLINE_KEYS = ("real_extrinsics", "camera_extrinsics", "extrinsics")
BOARD_POSE_PATH_KEYS = (
    "real_board_pose_path",
    "board_pose_path",
    "board_corner_detections_path",
    "board_corners_path",
    "corner_detections_path",
)
BOARD_POSE_INLINE_KEYS = (
    "real_board_pose",
    "board_pose",
    "board_corner_detections",
    "board_corners",
)
DEPTH_PATH_KEYS = ("real_depth_path", "depth_map_path", "depth_reference_path", "metric_depth_reference_path")
DEPTH_INLINE_KEYS = ("real_depth", "depth_map", "metric_depth_reference")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a hardware-free intake artifact that links selected real reference media "
            "to the metadata-native SimCamera projection/depth view."
        )
    )
    parser.add_argument("suite_summary", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
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


def resolve_path(value: Any, *, base_dir: Path, repo_root: Path | None = None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    base_candidate = (base_dir / path).resolve()
    if base_candidate.exists():
        return base_candidate
    if repo_root is not None:
        repo_candidate = (repo_root / path).resolve()
        if repo_candidate.exists():
            return repo_candidate
    return base_candidate


def output_relative(path: Path, output_dir: Path) -> str | None:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return None


def repo_relative(path: Path, repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return None


def load_optional_json(path_value: Any, *, base_dir: Path, repo_root: Path | None, label: str) -> dict[str, Any] | None:
    path = resolve_path(path_value, base_dir=base_dir, repo_root=repo_root)
    if path is None or not path.is_file():
        return None
    return read_json_object(path, label=label)


def selected_media_records(suite: dict[str, Any], comparison: dict[str, Any] | None) -> list[dict[str, Any]]:
    if comparison is not None and isinstance(comparison.get("selected_media"), list):
        return [row for row in comparison["selected_media"] if isinstance(row, dict)]
    comparison_section = suite.get("comparison_set")
    comparison_section = comparison_section if isinstance(comparison_section, dict) else {}
    artifacts = comparison_section.get("artifacts")
    rows: list[dict[str, Any]] = []
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict) and isinstance(item.get("relative_path"), str):
                rows.append({"relative_path": item.get("relative_path"), "media_type": "image"})
    return rows


def metadata_native_summary(
    suite: dict[str, Any],
    *,
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    visual_review = suite.get("visual_review")
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    view = visual_review.get("metadata_native_depth_view")
    view = view if isinstance(view, dict) else {}
    paths = view.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    loaded = load_optional_json(
        paths.get("json"),
        base_dir=suite_summary_path.parent,
        repo_root=repo_root,
        label="metadata-native depth view",
    )
    if loaded is not None:
        return loaded
    loaded = load_optional_json(
        paths.get("json_relative_path"),
        base_dir=output_dir,
        repo_root=repo_root,
        label="metadata-native depth view",
    )
    if loaded is not None:
        return loaded
    return view


def expected_projected_points(metadata_native: dict[str, Any]) -> list[dict[str, Any]]:
    rows = metadata_native.get("rows")
    rows = rows if isinstance(rows, list) else []
    wanted = (
        "id",
        "stage",
        "capture_label",
        "point_role",
        "point_label",
        "square",
        "metadata_projected_pixel_xy",
        "camera_frame_xyz_mm",
        "camera_z_depth_mm",
        "camera_range_mm",
        "board_plane_distance_mm",
        "board_frame_xyz_mm",
        "source_model",
        "status",
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        points.append({key: row.get(key) for key in wanted if key in row})
    return points


def nonempty(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    return True


def sidecar_status(
    declared_metadata: dict[str, Any],
    *,
    path_keys: tuple[str, ...],
    inline_keys: tuple[str, ...],
    missing_status: str,
    repo_root: Path,
) -> dict[str, Any]:
    for key in inline_keys:
        value = declared_metadata.get(key)
        if nonempty(value):
            validation: dict[str, Any] | None = None
            valid = True
            if isinstance(value, dict):
                kind, issues = validate_sidecar_payload(value, path=Path(key))
                valid = not issues
                validation = {
                    "source": f"inline.{key}",
                    "kind": kind,
                    "ok": valid,
                    "status": "valid" if valid else "invalid",
                    "issues": issues,
                    "schema": value.get("schema"),
                    "sidecar_type": value.get("sidecar_type"),
                    "example_only": value.get("example_only"),
                    "real_capture": value.get("real_capture"),
                }
            real_capture = bool(validation and validation.get("real_capture") is True)
            status = "inline_invalid"
            if valid and real_capture:
                status = "available_inline"
            elif valid:
                status = "valid_example_inline"
            return {
                "status": status,
                "field": key,
                "path": None,
                "exists": True,
                "validation": validation,
            }
    for key in path_keys:
        value = declared_metadata.get(key)
        if not isinstance(value, str) or not value:
            continue
        resolved = (repo_root / value).resolve() if not Path(value).expanduser().is_absolute() else Path(value).expanduser().resolve()
        exists = resolved.is_file()
        validation = validate_sidecar_path(resolved, repo_root=repo_root, source=key) if exists else None
        valid = bool(validation and validation.get("ok") is True)
        real_capture = bool(validation and validation.get("real_capture") is True)
        status = "declared_missing"
        if valid and real_capture:
            status = "available"
        elif valid:
            status = "valid_example"
        elif exists:
            status = "declared_invalid"
        return {
            "status": status,
            "field": key,
            "path": str(resolved),
            "repo_relative_path": repo_relative(resolved, repo_root),
            "exists": exists,
            "validation": validation,
        }
    return {
        "status": missing_status,
        "field": None,
        "path": None,
        "exists": False,
        "validation": None,
    }


def missing_inputs_for(
    *,
    reference_exists: bool,
    sim_view_available: bool,
    intrinsics: dict[str, Any],
    extrinsics: dict[str, Any],
    board_pose: dict[str, Any],
    depth: dict[str, Any],
) -> list[str]:
    missing: list[str] = []
    if not reference_exists:
        missing.append("real_reference_media_file")
    if not sim_view_available:
        missing.append("sim_metadata_native_depth_view_json")
    if intrinsics.get("status") not in {"available", "available_inline"}:
        missing.append("real_camera_intrinsics_json")
    if extrinsics.get("status") not in {"available", "available_inline"}:
        missing.append("real_camera_extrinsics_json")
    if board_pose.get("status") not in {"available", "available_inline"}:
        missing.append("real_board_pose_or_corner_detections_json")
    if depth.get("status") not in {"available", "available_inline"}:
        missing.append("real_depth_map_or_metric_distance_reference")
    return missing


def sidecar_validation_summary(sidecars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    valid = 0
    invalid = 0
    missing = 0
    for name, sidecar in sidecars.items():
        validation = sidecar.get("validation") if isinstance(sidecar, dict) else None
        validation = validation if isinstance(validation, dict) else None
        status = sidecar.get("status") if isinstance(sidecar, dict) else "missing"
        if validation is not None:
            is_valid = validation.get("ok") is True
            valid += int(is_valid)
            invalid += int(not is_valid)
            rows.append(
                {
                    "name": name,
                    "status": status,
                    "validation_status": validation.get("status"),
                    "ok": is_valid,
                    "kind": validation.get("kind"),
                    "schema": validation.get("schema"),
                    "example_only": validation.get("example_only"),
                    "real_capture": validation.get("real_capture"),
                    "issues": validation.get("issues"),
                    "path": sidecar.get("path"),
                    "repo_relative_path": sidecar.get("repo_relative_path"),
                    "field": sidecar.get("field"),
                }
            )
        else:
            missing += int(status not in {"available", "available_inline"})
            rows.append(
                {
                    "name": name,
                    "status": status,
                    "validation_status": None,
                    "ok": False,
                    "kind": None,
                    "issues": [],
                    "path": sidecar.get("path") if isinstance(sidecar, dict) else None,
                    "repo_relative_path": sidecar.get("repo_relative_path") if isinstance(sidecar, dict) else None,
                    "field": sidecar.get("field") if isinstance(sidecar, dict) else None,
                }
            )
    return {
        "valid_count": valid,
        "invalid_count": invalid,
        "missing_count": missing,
        "sidecars": rows,
    }


def capture_requirement_templates(missing_inputs: list[str]) -> list[dict[str, Any]]:
    templates = {
        "real_reference_media_file": {
            "id": "real_reference_media_file",
            "description": "Add repo-local SO-101 reference image or video media and declare it in the manifest.",
            "manifest_fields": ["relative_path", "capture_id", "camera_view", "calibration_targets"],
        },
        "sim_metadata_native_depth_view_json": {
            "id": "sim_metadata_native_depth_view_json",
            "description": "Run visual review so pick_place_metadata_native_depth_view.json exists.",
            "artifact": "visual_review/pick_place_metadata_native_depth_view.json",
        },
        "real_camera_intrinsics_json": {
            "id": "real_camera_intrinsics_json",
            "description": "Provide calibrated real camera intrinsics for the reference frame.",
            "manifest_fields": ["real_intrinsics_path"],
            "expected_contents": ["camera_matrix_px", "distortion_coefficients", "image_size_px"],
        },
        "real_camera_extrinsics_json": {
            "id": "real_camera_extrinsics_json",
            "description": "Provide calibrated real camera extrinsics or a camera-to-board pose for the reference frame.",
            "manifest_fields": ["real_extrinsics_path"],
            "expected_contents": ["board_to_camera or camera_to_board transform", "frame convention"],
        },
        "real_board_pose_or_corner_detections_json": {
            "id": "real_board_pose_or_corner_detections_json",
            "description": "Provide detected board corners or a solved board pose for the real frame.",
            "manifest_fields": ["board_corner_detections_path", "real_board_pose_path"],
            "expected_contents": ["a1,h1,h8,a8 image coordinates", "corner order", "detection confidence"],
        },
        "real_depth_map_or_metric_distance_reference": {
            "id": "real_depth_map_or_metric_distance_reference",
            "description": "Provide a real depth map or measured camera-to-board/piece distance reference when true depth comparison is required.",
            "manifest_fields": ["real_depth_path", "depth_reference_path"],
            "expected_contents": ["depth units", "depth scale", "camera frame convention"],
        },
    }
    return [templates[key] for key in missing_inputs if key in templates]


def image_read_status(path: Path | None) -> tuple[bool, dict[str, Any]]:
    if path is None or not path.is_file():
        return False, {"status": "missing", "path": str(path) if path else None}
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return False, {"status": "unreadable", "path": str(path)}
    return True, {
        "status": "ok",
        "path": str(path),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "channels": int(image.shape[2]) if image.ndim == 3 else 1,
    }


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def vector_from_mm(value: Any, *, length: int) -> np.ndarray | None:
    if not isinstance(value, list) or len(value) != length:
        return None
    numbers = [finite_float(item) for item in value]
    if any(item is None for item in numbers):
        return None
    return np.asarray(numbers, dtype=float) / 1000.0


def point_xy(value: Any) -> np.ndarray | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    x = finite_float(value[0])
    y = finite_float(value[1])
    if x is None or y is None:
        return None
    return np.asarray([x, y], dtype=float)


def sidecar_payload(sidecar: dict[str, Any], declared_metadata: dict[str, Any]) -> dict[str, Any] | None:
    field = sidecar.get("field")
    inline = declared_metadata.get(field) if isinstance(field, str) else None
    if isinstance(inline, dict):
        return inline
    path_value = sidecar.get("path")
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.is_file():
        return None
    try:
        return read_json_object(path, label="calibration sidecar")
    except ValueError:
        return None


def camera_matrix(payload: dict[str, Any]) -> np.ndarray | None:
    value = payload.get("camera_matrix_px")
    if not isinstance(value, list):
        return None
    try:
        matrix = np.asarray(value, dtype=float).reshape(3, 3)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(matrix)):
        return None
    return matrix


def distortion_coefficients(payload: dict[str, Any]) -> np.ndarray:
    value = payload.get("distortion_coefficients")
    if not isinstance(value, list):
        return np.zeros((5, 1), dtype=float)
    try:
        coeffs = np.asarray(value, dtype=float).reshape(-1, 1)
    except (TypeError, ValueError):
        return np.zeros((5, 1), dtype=float)
    if not np.all(np.isfinite(coeffs)):
        return np.zeros((5, 1), dtype=float)
    return coeffs


def transform_matrix(payload: dict[str, Any]) -> np.ndarray | None:
    transform = payload.get("transform")
    transform = transform if isinstance(transform, dict) else payload
    matrix = transform.get("matrix_4x4")
    if matrix is not None:
        try:
            result = np.asarray(matrix, dtype=float).reshape(4, 4)
        except (TypeError, ValueError):
            return None
    else:
        rotation = transform.get("rotation_matrix")
        translation = transform.get("translation_m")
        try:
            rot = np.asarray(rotation, dtype=float).reshape(3, 3)
            trans = np.asarray(translation, dtype=float).reshape(3)
        except (TypeError, ValueError):
            return None
        result = np.eye(4, dtype=float)
        result[:3, :3] = rot
        result[:3, 3] = trans
    if not np.all(np.isfinite(result)):
        return None
    convention = payload.get("transform_convention")
    if convention == "camera_to_board":
        try:
            result = np.linalg.inv(result)
        except np.linalg.LinAlgError:
            return None
    return result


def project_board_point(
    board_point_m: np.ndarray,
    *,
    intrinsics_payload: dict[str, Any],
    extrinsics_payload: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray] | None:
    k = camera_matrix(intrinsics_payload)
    transform = transform_matrix(extrinsics_payload)
    if k is None or transform is None:
        return None
    camera_point = transform[:3, :3] @ board_point_m.reshape(3) + transform[:3, 3]
    z = float(camera_point[2])
    if not np.isfinite(z) or abs(z) < 1e-9:
        return None
    normalized_x = float(camera_point[0]) / z
    normalized_y = float(camera_point[1]) / z
    coeffs = distortion_coefficients(intrinsics_payload).reshape(-1)
    k1 = float(coeffs[0]) if coeffs.size > 0 else 0.0
    k2 = float(coeffs[1]) if coeffs.size > 1 else 0.0
    p1 = float(coeffs[2]) if coeffs.size > 2 else 0.0
    p2 = float(coeffs[3]) if coeffs.size > 3 else 0.0
    k3 = float(coeffs[4]) if coeffs.size > 4 else 0.0
    r2 = normalized_x * normalized_x + normalized_y * normalized_y
    radial = 1.0 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    distorted_x = normalized_x * radial + 2.0 * p1 * normalized_x * normalized_y + p2 * (
        r2 + 2.0 * normalized_x * normalized_x
    )
    distorted_y = normalized_y * radial + p1 * (r2 + 2.0 * normalized_y * normalized_y) + 2.0 * p2 * normalized_x * normalized_y
    image_xy = np.asarray(
        [
            float(k[0, 0]) * distorted_x + float(k[0, 1]) * distorted_y + float(k[0, 2]),
            float(k[1, 1]) * distorted_y + float(k[1, 0]) * distorted_x + float(k[1, 2]),
        ],
        dtype=float,
    )
    if not np.all(np.isfinite(image_xy)):
        return None
    return camera_point, image_xy


def rounded_float(value: Any, *, digits: int = 3) -> float | None:
    number = finite_float(value)
    return round(number, digits) if number is not None else None


def rounded_list(values: np.ndarray | list[float] | None, *, digits: int = 3) -> list[float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float).reshape(-1)
    if not np.all(np.isfinite(array)):
        return None
    return [round(float(item), digits) for item in array]


def residual_norm(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    if a is None or b is None:
        return None
    return rounded_float(float(np.linalg.norm(a - b)))


def board_corner_observations(board_pose_payload: dict[str, Any] | None) -> dict[str, np.ndarray]:
    if board_pose_payload is None:
        return {}
    corners = board_pose_payload.get("corners")
    if not isinstance(corners, list):
        return {}
    observed: dict[str, np.ndarray] = {}
    for corner in corners:
        if not isinstance(corner, dict):
            continue
        label = corner.get("label")
        xy = point_xy(corner.get("pixel_xy"))
        if isinstance(label, str) and xy is not None:
            observed[label] = xy
    return observed


def depth_reference_rows(depth_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if depth_payload is None:
        return []
    rows = depth_payload.get("metric_references")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def reference_depth_mm(reference: dict[str, Any]) -> float | None:
    distance_m = finite_float(reference.get("distance_m"))
    if distance_m is None:
        return None
    return round(distance_m * 1000.0, 3)


def point_match_tokens(row: dict[str, Any]) -> set[str]:
    values = [
        row.get("point_label"),
        row.get("point_role"),
        row.get("square"),
        row.get("id"),
        row.get("stage"),
    ]
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, str) and value:
            tokens.add(value.lower())
    return tokens


def match_depth_reference(reference: dict[str, Any], sim_points: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = str(reference.get("target") or reference.get("id") or "").lower()
    if not target:
        return None
    aliases = {
        "board_center": {"board_center"},
        "piece_top": {"piece_center"},
        "piece_center": {"piece_center"},
        "target_square": {"target_square_center"},
        "target_square_center": {"target_square_center"},
    }
    wanted = aliases.get(target, {target})
    for row in sim_points:
        if not isinstance(row, dict):
            continue
        if point_match_tokens(row) & wanted:
            return row
    return None


def board_plane_distance_from_extrinsics(extrinsics_payload: dict[str, Any] | None) -> float | None:
    if extrinsics_payload is None:
        return None
    transform = transform_matrix(extrinsics_payload)
    if transform is None:
        return None
    try:
        camera_center_board = -transform[:3, :3].T @ transform[:3, 3]
    except ValueError:
        return None
    return rounded_float(abs(float(camera_center_board[2])) * 1000.0)


def compute_real_residuals(
    *,
    record_id: str,
    declared_metadata: dict[str, Any],
    sidecars: dict[str, dict[str, Any]],
    sim_expected_points: list[dict[str, Any]],
) -> dict[str, Any]:
    payloads = {
        name: sidecar_payload(sidecar, declared_metadata)
        for name, sidecar in sidecars.items()
        if isinstance(sidecar, dict) and sidecar.get("status") in {"available", "available_inline"}
    }
    intrinsics_payload = payloads.get("intrinsics")
    extrinsics_payload = payloads.get("extrinsics")
    board_pose_payload = payloads.get("board_pose")
    depth_payload = payloads.get("depth")
    projection_rows: list[dict[str, Any]] = []
    corner_rows: list[dict[str, Any]] = []
    depth_rows: list[dict[str, Any]] = []
    real_projected_by_label: dict[str, np.ndarray] = {}
    sim_projected_by_label: dict[str, np.ndarray] = {}

    if intrinsics_payload is not None and extrinsics_payload is not None:
        for point in sim_expected_points:
            if not isinstance(point, dict):
                continue
            board_point_m = vector_from_mm(point.get("board_frame_xyz_mm"), length=3)
            sim_xy = point_xy(point.get("metadata_projected_pixel_xy"))
            if board_point_m is None or sim_xy is None:
                continue
            projected = project_board_point(
                board_point_m,
                intrinsics_payload=intrinsics_payload,
                extrinsics_payload=extrinsics_payload,
            )
            if projected is None:
                continue
            real_camera_point, real_xy = projected
            label = str(point.get("point_label") or point.get("id") or "")
            if label:
                real_projected_by_label[label] = real_xy
                sim_projected_by_label[label] = sim_xy
            camera_z_mm = float(real_camera_point[2]) * 1000.0
            camera_range_mm = float(np.linalg.norm(real_camera_point)) * 1000.0
            projection_rows.append(
                {
                    "record_id": record_id,
                    "sim_point_id": point.get("id"),
                    "stage": point.get("stage"),
                    "point_role": point.get("point_role"),
                    "point_label": point.get("point_label"),
                    "square": point.get("square"),
                    "real_projected_pixel_xy": rounded_list(real_xy),
                    "sim_expected_pixel_xy": rounded_list(sim_xy),
                    "real_vs_sim_projection_residual_px": residual_norm(real_xy, sim_xy),
                    "real_camera_frame_xyz_mm": rounded_list(real_camera_point * 1000.0),
                    "real_camera_z_depth_mm": rounded_float(camera_z_mm),
                    "sim_camera_z_depth_mm": rounded_float(point.get("camera_z_depth_mm")),
                    "real_vs_sim_camera_z_residual_mm": rounded_float(
                        camera_z_mm - float(point.get("camera_z_depth_mm"))
                    )
                    if finite_float(point.get("camera_z_depth_mm")) is not None
                    else None,
                    "real_camera_range_mm": rounded_float(camera_range_mm),
                    "sim_camera_range_mm": rounded_float(point.get("camera_range_mm")),
                    "real_vs_sim_camera_range_residual_mm": rounded_float(
                        camera_range_mm - float(point.get("camera_range_mm"))
                    )
                    if finite_float(point.get("camera_range_mm")) is not None
                    else None,
                    "status": "ok",
                }
            )

    observed_corners = board_corner_observations(board_pose_payload)
    for label in BOARD_CORNER_LABELS:
        observed_xy = observed_corners.get(label)
        sim_label = SIM_BOARD_CORNER_LABELS[label]
        sim_xy = sim_projected_by_label.get(sim_label)
        if sim_xy is None:
            sim_point = next(
                (
                    point
                    for point in sim_expected_points
                    if isinstance(point, dict) and point.get("point_label") == sim_label
                ),
                {},
            )
            sim_xy = point_xy(sim_point.get("metadata_projected_pixel_xy"))
        if observed_xy is None or sim_xy is None:
            continue
        real_projected_xy = real_projected_by_label.get(sim_label)
        corner_rows.append(
            {
                "record_id": record_id,
                "corner_label": label,
                "real_detected_pixel_xy": rounded_list(observed_xy),
                "real_projected_pixel_xy": rounded_list(real_projected_xy),
                "sim_expected_pixel_xy": rounded_list(sim_xy),
                "detected_vs_sim_projection_residual_px": residual_norm(observed_xy, sim_xy),
                "detected_vs_real_projection_residual_px": residual_norm(observed_xy, real_projected_xy),
                "status": "ok",
            }
        )

    for reference in depth_reference_rows(depth_payload):
        sim_point = match_depth_reference(reference, sim_expected_points)
        measured_mm = reference_depth_mm(reference)
        if sim_point is None or measured_mm is None:
            continue
        distance_type = str(reference.get("distance_type") or "camera_range")
        sim_mm = (
            finite_float(sim_point.get("camera_z_depth_mm"))
            if distance_type in {"camera_z", "z_depth", "camera_z_depth"}
            else finite_float(sim_point.get("camera_range_mm"))
        )
        if sim_mm is None:
            continue
        depth_rows.append(
            {
                "record_id": record_id,
                "reference_id": reference.get("id"),
                "target": reference.get("target"),
                "distance_type": distance_type,
                "measured_distance_mm": measured_mm,
                "sim_point_id": sim_point.get("id"),
                "sim_point_label": sim_point.get("point_label"),
                "sim_distance_mm": rounded_float(sim_mm),
                "real_vs_sim_depth_residual_mm": rounded_float(measured_mm - sim_mm),
                "reference_pixel_xy": reference.get("pixel_xy"),
                "status": "ok",
            }
        )

    board_plane_real_mm = board_plane_distance_from_extrinsics(extrinsics_payload)
    board_plane_sim_values = [
        finite_float(point.get("board_plane_distance_mm"))
        for point in sim_expected_points
        if isinstance(point, dict) and finite_float(point.get("board_plane_distance_mm")) is not None
    ]
    board_plane_sim_mm = round(float(np.mean(board_plane_sim_values)), 3) if board_plane_sim_values else None
    board_plane_residual = (
        rounded_float(board_plane_real_mm - board_plane_sim_mm)
        if board_plane_real_mm is not None and board_plane_sim_mm is not None
        else None
    )
    all_projection_residuals = [
        row["real_vs_sim_projection_residual_px"]
        for row in projection_rows
        if row.get("real_vs_sim_projection_residual_px") is not None
    ]
    detected_residuals = [
        row["detected_vs_sim_projection_residual_px"]
        for row in corner_rows
        if row.get("detected_vs_sim_projection_residual_px") is not None
    ]
    depth_residuals = [
        abs(float(row["real_vs_sim_depth_residual_mm"]))
        for row in depth_rows
        if row.get("real_vs_sim_depth_residual_mm") is not None
    ]
    return {
        "available": bool(projection_rows or corner_rows or depth_rows or board_plane_residual is not None),
        "status": "ok" if projection_rows or corner_rows or depth_rows else "no_residual_rows",
        "projection_rows": projection_rows,
        "board_corner_rows": corner_rows,
        "depth_rows": depth_rows,
        "board_plane": {
            "real_camera_to_board_plane_mm": board_plane_real_mm,
            "sim_camera_to_board_plane_mm": board_plane_sim_mm,
            "real_vs_sim_board_plane_residual_mm": board_plane_residual,
        },
        "aggregate": {
            "projected_point_count": len(projection_rows),
            "board_corner_observation_count": len(corner_rows),
            "depth_reference_count": len(depth_rows),
            "mean_real_vs_sim_projection_residual_px": (
                rounded_float(float(np.mean(all_projection_residuals))) if all_projection_residuals else None
            ),
            "max_real_vs_sim_projection_residual_px": (
                rounded_float(float(np.max(all_projection_residuals))) if all_projection_residuals else None
            ),
            "mean_detected_corner_vs_sim_residual_px": (
                rounded_float(float(np.mean(detected_residuals))) if detected_residuals else None
            ),
            "max_detected_corner_vs_sim_residual_px": (
                rounded_float(float(np.max(detected_residuals))) if detected_residuals else None
            ),
            "mean_abs_real_vs_sim_depth_residual_mm": (
                rounded_float(float(np.mean(depth_residuals))) if depth_residuals else None
            ),
            "max_abs_real_vs_sim_depth_residual_mm": (
                rounded_float(float(np.max(depth_residuals))) if depth_residuals else None
            ),
        },
        "sources": {
            "real_intrinsics": sidecars.get("intrinsics", {}).get("repo_relative_path") or sidecars.get("intrinsics", {}).get("field"),
            "real_extrinsics": sidecars.get("extrinsics", {}).get("repo_relative_path") or sidecars.get("extrinsics", {}).get("field"),
            "real_board_pose": sidecars.get("board_pose", {}).get("repo_relative_path") or sidecars.get("board_pose", {}).get("field"),
            "real_depth": sidecars.get("depth", {}).get("repo_relative_path") or sidecars.get("depth", {}).get("field"),
        },
    }


def build_record(
    *,
    media: dict[str, Any],
    index: int,
    repo_root: Path,
    suite_output_dir: Path,
    metadata_native: dict[str, Any],
    sim_expected_points: list[dict[str, Any]],
) -> dict[str, Any]:
    relative_path = media.get("relative_path")
    reference_path = resolve_path(relative_path, base_dir=suite_output_dir, repo_root=repo_root)
    declared_metadata = media.get("declared_metadata")
    declared_metadata = declared_metadata if isinstance(declared_metadata, dict) else {}
    reference_exists, reference_image = image_read_status(reference_path)
    intrinsics = sidecar_status(
        declared_metadata,
        path_keys=INTRINSICS_PATH_KEYS,
        inline_keys=INTRINSICS_INLINE_KEYS,
        missing_status="missing_real_intrinsics",
        repo_root=repo_root,
    )
    extrinsics = sidecar_status(
        declared_metadata,
        path_keys=EXTRINSICS_PATH_KEYS,
        inline_keys=EXTRINSICS_INLINE_KEYS,
        missing_status="missing_real_extrinsics",
        repo_root=repo_root,
    )
    board_pose = sidecar_status(
        declared_metadata,
        path_keys=BOARD_POSE_PATH_KEYS,
        inline_keys=BOARD_POSE_INLINE_KEYS,
        missing_status="missing_real_board_pose",
        repo_root=repo_root,
    )
    depth = sidecar_status(
        declared_metadata,
        path_keys=DEPTH_PATH_KEYS,
        inline_keys=DEPTH_INLINE_KEYS,
        missing_status="missing_real_depth",
        repo_root=repo_root,
    )
    validation_summary = sidecar_validation_summary(
        {
            "intrinsics": intrinsics,
            "extrinsics": extrinsics,
            "board_pose": board_pose,
            "depth": depth,
        }
    )
    paths = metadata_native.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    sim_view_available = bool(sim_expected_points) and isinstance(paths.get("json"), str)
    missing_inputs = missing_inputs_for(
        reference_exists=reference_exists,
        sim_view_available=sim_view_available,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
        board_pose=board_pose,
        depth=depth,
    )
    has_intrinsics = intrinsics.get("status") in {"available", "available_inline"}
    has_pose = extrinsics.get("status") in {"available", "available_inline"} or board_pose.get("status") in {
        "available",
        "available_inline",
    }
    comparable = bool(reference_exists and sim_view_available and has_intrinsics and has_pose)
    depth_comparable = bool(comparable and depth.get("status") in {"available", "available_inline"})
    if not reference_exists:
        status = "missing_real_reference_media"
    elif not sim_view_available:
        status = "missing_sim_metadata_native_depth_view"
    elif not comparable:
        status = "missing_real_calibration"
    elif depth_comparable:
        status = "real_depth_comparable"
    else:
        status = "projection_comparable"

    record_id = f"real_reference_{index:03d}"
    residuals = (
        compute_real_residuals(
            record_id=record_id,
            declared_metadata=declared_metadata,
            sidecars={
                "intrinsics": intrinsics,
                "extrinsics": extrinsics,
                "board_pose": board_pose,
                "depth": depth,
            },
            sim_expected_points=sim_expected_points,
        )
        if comparable
        else {
            "available": False,
            "status": "not_comparable",
            "projection_rows": [],
            "board_corner_rows": [],
            "depth_rows": [],
            "board_plane": None,
            "aggregate": {},
            "sources": {},
        }
    )

    unavailable_fields = []
    if not comparable:
        unavailable_fields.extend(
            [
                "real_expected_projected_points",
                "real_vs_sim_projection_residual_px",
                "real_overlay_projected_points",
            ]
        )
    if not depth_comparable:
        unavailable_fields.extend(
            [
                "real_camera_z_depth_mm",
                "real_camera_range_mm",
                "real_vs_sim_depth_residual_mm",
            ]
        )

    return {
        "id": record_id,
        "status": status,
        "ok": True,
        "real_reference_media_path": str(reference_path) if reference_path else None,
        "real_reference_media_relative_path": str(relative_path) if isinstance(relative_path, str) else None,
        "real_reference_image_status": reference_image,
        "real_intrinsics_status": intrinsics.get("status"),
        "real_intrinsics": intrinsics,
        "real_extrinsics_status": extrinsics.get("status"),
        "real_extrinsics": extrinsics,
        "real_board_pose_status": board_pose.get("status"),
        "real_board_pose": board_pose,
        "real_depth_status": depth.get("status"),
        "real_depth": depth,
        "sidecar_validation": validation_summary,
        "sim_metadata_native_depth_view_path": paths.get("json"),
        "sim_metadata_native_depth_view_png_path": paths.get("png"),
        "sim_metadata_native_depth_view_csv_path": paths.get("csv"),
        "sim_expected_projected_point_count": len(sim_expected_points),
        "sim_expected_projected_points": sim_expected_points,
        "comparable": comparable,
        "projection_comparable": comparable,
        "depth_comparable": depth_comparable,
        "missing_inputs": missing_inputs,
        "next_capture_requirements": capture_requirement_templates(missing_inputs),
        "comparison_fields": {
            "side_by_side_contact_sheet": reference_exists and bool(paths.get("png")),
            "projection_overlay": comparable,
            "real_projection_residuals": bool(residuals.get("projection_rows")),
            "real_board_corner_residuals": bool(residuals.get("board_corner_rows")),
            "true_depth_comparison": bool(depth_comparable and residuals.get("depth_rows")),
            "unavailable": unavailable_fields,
        },
        "residuals": residuals,
        "declared_metadata": declared_metadata or None,
        "manifest_validation": media.get("manifest_validation"),
        "notes": [
            "This row links real reference media to simulator expected projections; it does not claim physical calibration truth.",
            "comparable is false until real intrinsics plus real board pose/extrinsics are supplied.",
            "real_depth_comparable is true only when a selected media row supplies real_capture=true depth references.",
        ],
    }


def csv_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "status",
        "real_reference_media_path",
        "real_intrinsics_status",
        "real_extrinsics_status",
        "real_board_pose_status",
        "real_depth_status",
        "sim_metadata_native_depth_view_path",
        "sim_expected_projected_point_count",
        "comparable",
        "projection_comparable",
        "depth_comparable",
        "residuals_available",
        "residual_projection_row_count",
        "residual_board_corner_row_count",
        "residual_depth_row_count",
        "missing_inputs",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            residuals = record.get("residuals")
            residuals = residuals if isinstance(residuals, dict) else {}
            aggregate = residuals.get("aggregate")
            aggregate = aggregate if isinstance(aggregate, dict) else {}
            row = {key: record.get(key) for key in fieldnames}
            row.update(
                {
                    "residuals_available": residuals.get("available"),
                    "residual_projection_row_count": aggregate.get("projected_point_count"),
                    "residual_board_corner_row_count": aggregate.get("board_corner_observation_count"),
                    "residual_depth_row_count": aggregate.get("depth_reference_count"),
                }
            )
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def put_wrapped_text(
    image: np.ndarray,
    text: str,
    *,
    x: int,
    y: int,
    max_chars: int,
    color: tuple[int, int, int],
    scale: float = 0.46,
    thickness: int = 1,
    line_height: int = 18,
) -> int:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for line in lines:
        cv2.putText(image, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
        y += line_height
    return y


def tile_with_label(
    image: np.ndarray | None,
    *,
    width: int,
    height: int,
    label: str,
    detail: str,
    placeholder: str,
) -> np.ndarray:
    tile = np.full((height, width, 3), (246, 247, 249), dtype=np.uint8)
    cv2.rectangle(tile, (0, 0), (width, 44), (24, 32, 44), -1)
    cv2.putText(tile, label[:58], (12, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(tile, detail[:76], (12, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (205, 221, 255), 1, cv2.LINE_AA)
    if image is None:
        put_wrapped_text(
            tile,
            placeholder,
            x=18,
            y=height // 2 - 28,
            max_chars=52,
            color=(70, 80, 95),
            scale=0.5,
            line_height=21,
        )
        return tile
    src_h, src_w = image.shape[:2]
    max_w = width - 24
    max_h = height - 58
    scale = min(max_w / max(src_w, 1), max_h / max(src_h, 1))
    target_w = max(1, int(round(src_w * scale)))
    target_h = max(1, int(round(src_h * scale)))
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
    x0 = (width - target_w) // 2
    y0 = 50 + (max_h - target_h) // 2
    tile[y0 : y0 + target_h, x0 : x0 + target_w] = resized
    return tile


def status_tile(record: dict[str, Any], *, width: int, height: int) -> np.ndarray:
    tile = np.full((height, width, 3), (250, 250, 248), dtype=np.uint8)
    cv2.rectangle(tile, (0, 0), (width, 44), (52, 65, 85), -1)
    cv2.putText(tile, "Calibration Intake Status", (12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(tile, str(record.get("status") or "")[:70], (12, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (210, 230, 255), 1, cv2.LINE_AA)
    y = 66
    lines = [
        f"comparable: {record.get('comparable')}",
        f"intrinsics: {record.get('real_intrinsics_status')}",
        f"board pose: {record.get('real_board_pose_status')}",
        f"depth: {record.get('real_depth_status')}",
        f"sim points: {record.get('sim_expected_projected_point_count')}",
    ]
    for line in lines:
        cv2.putText(tile, line, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (25, 32, 42), 1, cv2.LINE_AA)
        y += 24
    missing = record.get("missing_inputs")
    if isinstance(missing, list) and missing:
        y += 8
        cv2.putText(tile, "missing inputs:", (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (25, 32, 42), 1, cv2.LINE_AA)
        y += 22
        for item in missing[:7]:
            y = put_wrapped_text(
                tile,
                f"- {item}",
                x=20,
                y=y,
                max_chars=46,
                color=(85, 55, 35),
                scale=0.41,
                line_height=18,
            )
    return tile


def render_contact_sheet(
    *,
    path: Path,
    records: list[dict[str, Any]],
    suite_output_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    tile_w = 480
    tile_h = 360
    gap = 12
    rows: list[np.ndarray] = []
    source_records = records or [
        {
            "id": "no_real_reference_media",
            "status": "missing_real_reference_media",
            "real_reference_media_path": None,
            "sim_metadata_native_depth_view_png_path": None,
            "comparable": False,
            "real_intrinsics_status": "missing_real_intrinsics",
            "real_board_pose_status": "missing_real_board_pose",
            "real_depth_status": "missing_real_depth",
            "sim_expected_projected_point_count": 0,
            "missing_inputs": ["real_reference_media_file"],
        }
    ]
    for record in source_records:
        real_path = resolve_path(record.get("real_reference_media_path"), base_dir=suite_output_dir, repo_root=repo_root)
        sim_png_path = resolve_path(
            record.get("sim_metadata_native_depth_view_png_path"),
            base_dir=suite_output_dir,
            repo_root=repo_root,
        )
        real_image = cv2.imread(str(real_path), cv2.IMREAD_COLOR) if real_path and real_path.is_file() else None
        sim_image = cv2.imread(str(sim_png_path), cv2.IMREAD_COLOR) if sim_png_path and sim_png_path.is_file() else None
        real_tile = tile_with_label(
            real_image,
            width=tile_w,
            height=tile_h,
            label="real reference frame",
            detail=str(record.get("real_reference_media_relative_path") or record.get("real_reference_media_path") or ""),
            placeholder="No usable real reference image was available for this intake row.",
        )
        sim_tile = tile_with_label(
            sim_image,
            width=tile_w,
            height=tile_h,
            label="metadata-native expected projection/depth",
            detail=str(record.get("sim_metadata_native_depth_view_path") or ""),
            placeholder="No metadata-native SimCamera projection/depth PNG was available.",
        )
        row = np.hstack([real_tile, sim_tile, status_tile(record, width=tile_w, height=tile_h)])
        rows.append(row)

    width = tile_w * 3 + gap * 2
    header_h = 58
    sheet_h = header_h + len(rows) * tile_h + max(0, len(rows) - 1) * gap
    sheet = np.full((sheet_h, width, 3), (235, 238, 243), dtype=np.uint8)
    cv2.rectangle(sheet, (0, 0), (width, header_h), (15, 23, 42), -1)
    cv2.putText(
        sheet,
        "Real Reference to SimCamera Metadata Projection Intake",
        (18, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        sheet,
        "Side-by-side review only until real intrinsics and board pose/detections are supplied.",
        (18, 49),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (204, 221, 246),
        1,
        cv2.LINE_AA,
    )
    y = header_h
    for row in rows:
        sheet[y : y + tile_h, 0 : tile_w] = row[:, 0:tile_w]
        sheet[y : y + tile_h, tile_w + gap : tile_w * 2 + gap] = row[:, tile_w : tile_w * 2]
        sheet[y : y + tile_h, tile_w * 2 + gap * 2 : tile_w * 3 + gap * 2] = row[:, tile_w * 2 :]
        y += tile_h + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), sheet)
    if not ok:
        raise ValueError(f"cv2 failed to write contact sheet {path}")
    return {
        "path": str(path),
        "width_px": int(sheet.shape[1]),
        "height_px": int(sheet.shape[0]),
        "row_count": len(rows),
    }


def residual_rows(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    projection: list[dict[str, Any]] = []
    corners: list[dict[str, Any]] = []
    depth: list[dict[str, Any]] = []
    board_plane: list[dict[str, Any]] = []
    for record in records:
        residuals = record.get("residuals")
        residuals = residuals if isinstance(residuals, dict) else {}
        if residuals.get("available") is not True:
            continue
        projection.extend(
            row for row in residuals.get("projection_rows", []) if isinstance(row, dict)
        )
        corners.extend(row for row in residuals.get("board_corner_rows", []) if isinstance(row, dict))
        depth.extend(row for row in residuals.get("depth_rows", []) if isinstance(row, dict))
        plane = residuals.get("board_plane")
        if isinstance(plane, dict):
            board_plane.append({"record_id": record.get("id"), **plane})
    return {
        "projection": projection,
        "board_corners": corners,
        "depth": depth,
        "board_plane": board_plane,
    }


def aggregate_residuals(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    def numeric_values(collection: list[dict[str, Any]], key: str, *, absolute: bool = False) -> list[float]:
        values: list[float] = []
        for row in collection:
            value = finite_float(row.get(key))
            if value is None:
                continue
            values.append(abs(value) if absolute else value)
        return values

    def mean_value(values: list[float]) -> float | None:
        return rounded_float(float(np.mean(values))) if values else None

    def max_value(values: list[float]) -> float | None:
        return rounded_float(float(np.max(values))) if values else None

    projection_values = numeric_values(rows["projection"], "real_vs_sim_projection_residual_px")
    corner_values = numeric_values(rows["board_corners"], "detected_vs_sim_projection_residual_px")
    depth_values = numeric_values(rows["depth"], "real_vs_sim_depth_residual_mm", absolute=True)
    z_values = numeric_values(rows["projection"], "real_vs_sim_camera_z_residual_mm", absolute=True)
    range_values = numeric_values(rows["projection"], "real_vs_sim_camera_range_residual_mm", absolute=True)
    board_plane_values = numeric_values(rows["board_plane"], "real_vs_sim_board_plane_residual_mm", absolute=True)
    return {
        "projection_row_count": len(rows["projection"]),
        "board_corner_row_count": len(rows["board_corners"]),
        "depth_row_count": len(rows["depth"]),
        "board_plane_row_count": len(rows["board_plane"]),
        "mean_real_vs_sim_projection_residual_px": mean_value(projection_values),
        "max_real_vs_sim_projection_residual_px": max_value(projection_values),
        "mean_detected_corner_vs_sim_residual_px": mean_value(corner_values),
        "max_detected_corner_vs_sim_residual_px": max_value(corner_values),
        "mean_abs_real_vs_sim_depth_residual_mm": mean_value(depth_values),
        "max_abs_real_vs_sim_depth_residual_mm": max_value(depth_values),
        "mean_abs_real_vs_sim_camera_z_residual_mm": mean_value(z_values),
        "max_abs_real_vs_sim_camera_z_residual_mm": max_value(z_values),
        "mean_abs_real_vs_sim_camera_range_residual_mm": mean_value(range_values),
        "max_abs_real_vs_sim_camera_range_residual_mm": max_value(range_values),
        "mean_abs_real_vs_sim_board_plane_residual_mm": mean_value(board_plane_values),
        "max_abs_real_vs_sim_board_plane_residual_mm": max_value(board_plane_values),
    }


def write_residual_csv(path: Path, rows: dict[str, list[dict[str, Any]]]) -> None:
    fieldnames = [
        "row_type",
        "record_id",
        "sim_point_id",
        "stage",
        "point_role",
        "point_label",
        "square",
        "corner_label",
        "reference_id",
        "target",
        "real_projected_pixel_xy",
        "real_detected_pixel_xy",
        "sim_expected_pixel_xy",
        "real_vs_sim_projection_residual_px",
        "detected_vs_sim_projection_residual_px",
        "detected_vs_real_projection_residual_px",
        "real_camera_z_depth_mm",
        "sim_camera_z_depth_mm",
        "real_vs_sim_camera_z_residual_mm",
        "real_camera_range_mm",
        "sim_camera_range_mm",
        "real_vs_sim_camera_range_residual_mm",
        "measured_distance_mm",
        "sim_distance_mm",
        "real_vs_sim_depth_residual_mm",
        "real_camera_to_board_plane_mm",
        "sim_camera_to_board_plane_mm",
        "real_vs_sim_board_plane_residual_mm",
        "status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    typed_rows: list[dict[str, Any]] = []
    for row_type, collection in rows.items():
        for row in collection:
            typed_rows.append({"row_type": row_type, **row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in typed_rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def draw_labeled_point(
    image: np.ndarray,
    xy_value: Any,
    *,
    color: tuple[int, int, int],
    label: str,
    marker: str = "circle",
) -> None:
    xy = point_xy(xy_value)
    if xy is None:
        return
    x = int(round(float(xy[0])))
    y = int(round(float(xy[1])))
    if x < -50 or y < -50 or x > image.shape[1] + 50 or y > image.shape[0] + 50:
        return
    if marker == "diamond":
        cv2.drawMarker(image, (x, y), color, markerType=cv2.MARKER_DIAMOND, markerSize=15, thickness=2)
    elif marker == "cross":
        cv2.drawMarker(image, (x, y), color, markerType=cv2.MARKER_CROSS, markerSize=14, thickness=2)
    else:
        cv2.circle(image, (x, y), 5, color, thickness=2, lineType=cv2.LINE_AA)
    cv2.putText(image, label[:24], (x + 7, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA)


def residual_overlay_tile(record: dict[str, Any], *, suite_output_dir: Path, repo_root: Path) -> np.ndarray | None:
    real_path = resolve_path(record.get("real_reference_media_path"), base_dir=suite_output_dir, repo_root=repo_root)
    image = cv2.imread(str(real_path), cv2.IMREAD_COLOR) if real_path and real_path.is_file() else None
    if image is None:
        return None
    overlay = image.copy()
    residuals = record.get("residuals")
    residuals = residuals if isinstance(residuals, dict) else {}
    projection_rows = residuals.get("projection_rows")
    projection_rows = projection_rows if isinstance(projection_rows, list) else []
    for row in projection_rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("point_label") or row.get("sim_point_id") or "")
        draw_labeled_point(overlay, row.get("sim_expected_pixel_xy"), color=(70, 170, 255), label=f"sim {label}", marker="cross")
        draw_labeled_point(overlay, row.get("real_projected_pixel_xy"), color=(80, 230, 130), label=f"real {label}", marker="circle")
    board_corner_rows = residuals.get("board_corner_rows")
    board_corner_rows = board_corner_rows if isinstance(board_corner_rows, list) else []
    for row in board_corner_rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("corner_label") or "")
        draw_labeled_point(overlay, row.get("real_detected_pixel_xy"), color=(245, 115, 95), label=f"det {label}", marker="diamond")
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1] - 1, 54), (18, 27, 42), -1)
    cv2.putText(
        overlay,
        "Real-vs-Sim Residual Overlay",
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    aggregate = residuals.get("aggregate")
    aggregate = aggregate if isinstance(aggregate, dict) else {}
    detail = (
        f"mean proj px={aggregate.get('mean_real_vs_sim_projection_residual_px')} "
        f"mean corner px={aggregate.get('mean_detected_corner_vs_sim_residual_px')} "
        f"mean depth mm={aggregate.get('mean_abs_real_vs_sim_depth_residual_mm')}"
    )
    cv2.putText(overlay, detail[:110], (12, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (210, 230, 255), 1, cv2.LINE_AA)
    return overlay


def render_residual_overlay_contact_sheet(
    *,
    path: Path,
    records: list[dict[str, Any]],
    suite_output_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    tiles: list[np.ndarray] = []
    for record in records:
        residuals = record.get("residuals")
        if not isinstance(residuals, dict) or residuals.get("available") is not True:
            continue
        overlay = residual_overlay_tile(record, suite_output_dir=suite_output_dir, repo_root=repo_root)
        if overlay is None:
            continue
        tiles.append(
            tile_with_label(
                overlay,
                width=640,
                height=480,
                label=str(record.get("id") or "real residual overlay"),
                detail=str(record.get("real_reference_media_relative_path") or ""),
                placeholder="Residual overlay unavailable.",
            )
        )
    if not tiles:
        return None
    gap = 12
    header_h = 58
    width = 640
    height = header_h + len(tiles) * 480 + max(0, len(tiles) - 1) * gap
    sheet = np.full((height, width, 3), (235, 238, 243), dtype=np.uint8)
    cv2.rectangle(sheet, (0, 0), (width, header_h), (15, 23, 42), -1)
    cv2.putText(
        sheet,
        "Real-Capture Projection / Depth Residuals",
        (18, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.68,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        sheet,
        "Generated only for sidecars gated as real_capture=true, not for example_only fixtures.",
        (18, 49),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (204, 221, 246),
        1,
        cv2.LINE_AA,
    )
    y = header_h
    for tile in tiles:
        sheet[y : y + 480, 0:640] = tile
        y += 480 + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), sheet)
    if not ok:
        raise ValueError(f"cv2 failed to write residual contact sheet {path}")
    return {
        "path": str(path),
        "width_px": int(sheet.shape[1]),
        "height_px": int(sheet.shape[0]),
        "row_count": len(tiles),
    }


def write_residual_artifacts(
    *,
    output_dir: Path,
    records: list[dict[str, Any]],
    suite_output_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    rows = residual_rows(records)
    if not any(rows.values()):
        return {
            "available": False,
            "status": "not_available",
            "paths": {"json": None, "csv": None, "png": None},
            "aggregate": aggregate_residuals(rows),
            "rows": rows,
        }
    json_path = output_dir / RESIDUAL_JSON_NAME
    csv_path = output_dir / RESIDUAL_CSV_NAME
    png_path = output_dir / RESIDUAL_PNG_NAME
    visual = render_residual_overlay_contact_sheet(
        path=png_path,
        records=records,
        suite_output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    summary = {
        "schema": "lerobot.sim.real_projection_residuals.v1",
        "available": True,
        "status": "ok",
        "paths": {
            "json": str(json_path),
            "csv": str(csv_path),
            "png": str(png_path) if visual is not None else None,
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
            "png_relative_path": output_relative(png_path, suite_output_dir) if visual is not None else None,
        },
        "aggregate": aggregate_residuals(rows),
        "visual": visual,
        "rows": rows,
        "notes": [
            "Residual artifacts are generated only from sidecars validated as real_capture=true.",
            "Synthetic test-only positive fixtures can exercise this path but do not prove physical SO-101 calibration.",
        ],
    }
    write_json(json_path, summary)
    write_residual_csv(csv_path, rows)
    return summary


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    suite_summary_path = args.suite_summary.expanduser().resolve()
    suite = read_json_object(suite_summary_path, label="suite summary")
    suite_output_dir = Path(str(suite.get("output_dir") or suite_summary_path.parent)).expanduser().resolve()
    repo_root_value = suite.get("repo_root")
    repo_root = Path(repo_root_value).expanduser().resolve() if isinstance(repo_root_value, str) else REPO_ROOT
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison_section = suite.get("comparison_set")
    comparison_section = comparison_section if isinstance(comparison_section, dict) else {}
    comparison = load_optional_json(
        comparison_section.get("summary_path"),
        base_dir=suite_summary_path.parent,
        repo_root=repo_root,
        label="comparison set summary",
    )
    metadata_native = metadata_native_summary(
        suite,
        suite_summary_path=suite_summary_path,
        output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    sim_expected_points = expected_projected_points(metadata_native)
    media_rows = selected_media_records(suite, comparison)
    records = [
        build_record(
            media=media,
            index=index,
            repo_root=repo_root,
            suite_output_dir=suite_output_dir,
            metadata_native=metadata_native,
            sim_expected_points=sim_expected_points,
        )
        for index, media in enumerate(media_rows, start=1)
    ]

    json_path = output_dir / OUTPUT_JSON_NAME
    csv_path = output_dir / OUTPUT_CSV_NAME
    png_path = output_dir / OUTPUT_PNG_NAME
    write_csv(csv_path, records)
    visual = render_contact_sheet(path=png_path, records=records, suite_output_dir=suite_output_dir, repo_root=repo_root)
    residual_artifacts = write_residual_artifacts(
        output_dir=output_dir,
        records=records,
        suite_output_dir=suite_output_dir,
        repo_root=repo_root,
    )

    comparable_count = sum(1 for record in records if record.get("comparable") is True)
    depth_comparable_count = sum(1 for record in records if record.get("depth_comparable") is True)
    if not sim_expected_points:
        status = "missing_sim_metadata_native_depth_view"
        ok = False
    elif not records:
        status = "missing_real_reference_media"
        ok = True
    elif depth_comparable_count == len(records):
        status = "real_depth_comparable"
        ok = True
    elif comparable_count == len(records):
        status = "missing_real_depth_reference"
        ok = True
    else:
        status = "missing_real_depth_reference"
        ok = True

    aggregate_missing_inputs = sorted(
        {
            str(item)
            for record in records
            for item in (record.get("missing_inputs") if isinstance(record.get("missing_inputs"), list) else [])
        }
    )
    sidecar_valid_count = sum(
        int(record.get("sidecar_validation", {}).get("valid_count", 0))
        for record in records
        if isinstance(record.get("sidecar_validation"), dict)
    )
    sidecar_invalid_count = sum(
        int(record.get("sidecar_validation", {}).get("invalid_count", 0))
        for record in records
        if isinstance(record.get("sidecar_validation"), dict)
    )
    sidecar_missing_count = sum(
        int(record.get("sidecar_validation", {}).get("missing_count", 0))
        for record in records
        if isinstance(record.get("sidecar_validation"), dict)
    )
    if not records:
        aggregate_missing_inputs = ["real_reference_media_file"]
    paths = metadata_native.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": status,
        "suite_summary_path": str(suite_summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(repo_root),
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "openai_skipped": True,
        "paths": {
            "json": str(json_path),
            "csv": str(csv_path),
            "png": str(png_path),
            "residual_json": residual_artifacts.get("paths", {}).get("json"),
            "residual_csv": residual_artifacts.get("paths", {}).get("csv"),
            "residual_png": residual_artifacts.get("paths", {}).get("png"),
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
            "png_relative_path": output_relative(png_path, suite_output_dir),
            "residual_json_relative_path": residual_artifacts.get("paths", {}).get("json_relative_path"),
            "residual_csv_relative_path": residual_artifacts.get("paths", {}).get("csv_relative_path"),
            "residual_png_relative_path": residual_artifacts.get("paths", {}).get("png_relative_path"),
        },
        "real_reference_media_count": len(records),
        "comparable_count": comparable_count,
        "projection_comparable_count": comparable_count,
        "depth_comparable_count": depth_comparable_count,
        "sidecar_valid_count": sidecar_valid_count,
        "sidecar_invalid_count": sidecar_invalid_count,
        "sidecar_missing_count": sidecar_missing_count,
        "missing_input_count": len(aggregate_missing_inputs),
        "missing_inputs": aggregate_missing_inputs,
        "next_capture_requirements": capture_requirement_templates(aggregate_missing_inputs),
        "sim_metadata_native_depth_view_path": paths.get("json"),
        "sim_metadata_native_depth_view_png_path": paths.get("png"),
        "sim_metadata_native_depth_view_csv_path": paths.get("csv"),
        "sim_expected_projected_point_count": len(sim_expected_points),
        "sim_expected_projected_points": sim_expected_points,
        "visual": visual,
        "residual_artifacts": {
            "available": residual_artifacts.get("available"),
            "status": residual_artifacts.get("status"),
            "paths": residual_artifacts.get("paths"),
            "aggregate": residual_artifacts.get("aggregate"),
            "visual": residual_artifacts.get("visual"),
        },
        "records": records,
        "notes": [
            "This is a hardware-free intake artifact. It does not open a camera, connect motors, or infer real depth.",
            "status=missing_real_depth_reference is expected until real_capture=true intrinsics, board pose/extrinsics, and depth references are supplied.",
            "The PNG is a side-by-side contact sheet, not a calibrated overlay, when calibration inputs are missing.",
            "Residual JSON/CSV/overlay files are emitted only when non-example real_capture sidecars pass the gate.",
        ],
    }
    write_json(json_path, summary)
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
            "suite_summary_path": str(args.suite_summary.expanduser().resolve()),
            "output_dir": str(output_dir),
            "hardware_skipped": True,
            "gui_skipped": True,
            "real_camera_capture_skipped": True,
            "openai_skipped": True,
            "error": str(exc),
            "paths": {
                "json": str(output_dir / OUTPUT_JSON_NAME),
                "csv": str(output_dir / OUTPUT_CSV_NAME),
                "png": str(output_dir / OUTPUT_PNG_NAME),
            },
            "records": [],
        }
        write_json(output_dir / OUTPUT_JSON_NAME, summary)
    print(json.dumps(summary, indent=2))
    if not summary["ok"]:
        print(f"ERROR: real projection intake status={summary['status']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
