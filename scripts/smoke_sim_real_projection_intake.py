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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_projection_intake"
SCHEMA = "lerobot.sim.real_projection_intake.v1"
OUTPUT_JSON_NAME = "real_projection_intake.json"
OUTPUT_CSV_NAME = "real_projection_intake.csv"
OUTPUT_PNG_NAME = "real_projection_intake_contact_sheet.png"

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
        if nonempty(declared_metadata.get(key)):
            return {
                "status": "available_inline",
                "field": key,
                "path": None,
                "exists": True,
            }
    for key in path_keys:
        value = declared_metadata.get(key)
        if not isinstance(value, str) or not value:
            continue
        resolved = (repo_root / value).resolve() if not Path(value).expanduser().is_absolute() else Path(value).expanduser().resolve()
        exists = resolved.is_file()
        return {
            "status": "available" if exists else "declared_missing",
            "field": key,
            "path": str(resolved),
            "repo_relative_path": repo_relative(resolved, repo_root),
            "exists": exists,
        }
    return {
        "status": missing_status,
        "field": None,
        "path": None,
        "exists": False,
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
    else:
        status = "projection_comparable"

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
        "id": f"real_reference_{index:03d}",
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
            "true_depth_comparison": depth_comparable,
            "unavailable": unavailable_fields,
        },
        "declared_metadata": declared_metadata or None,
        "manifest_validation": media.get("manifest_validation"),
        "notes": [
            "This row links real reference media to simulator expected projections; it does not claim real depth is available.",
            "comparable is false until real intrinsics plus real board pose/extrinsics are supplied.",
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
        "missing_inputs",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: csv_value(record.get(key)) for key in fieldnames})


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

    comparable_count = sum(1 for record in records if record.get("comparable") is True)
    if not sim_expected_points:
        status = "missing_sim_metadata_native_depth_view"
        ok = False
    elif not records:
        status = "missing_real_reference_media"
        ok = True
    elif comparable_count == len(records):
        status = "projection_comparable"
        ok = True
    else:
        status = "missing_real_calibration"
        ok = True

    aggregate_missing_inputs = sorted(
        {
            str(item)
            for record in records
            for item in (record.get("missing_inputs") if isinstance(record.get("missing_inputs"), list) else [])
        }
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
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
            "png_relative_path": output_relative(png_path, suite_output_dir),
        },
        "real_reference_media_count": len(records),
        "comparable_count": comparable_count,
        "projection_comparable_count": comparable_count,
        "depth_comparable_count": sum(1 for record in records if record.get("depth_comparable") is True),
        "missing_input_count": len(aggregate_missing_inputs),
        "missing_inputs": aggregate_missing_inputs,
        "next_capture_requirements": capture_requirement_templates(aggregate_missing_inputs),
        "sim_metadata_native_depth_view_path": paths.get("json"),
        "sim_metadata_native_depth_view_png_path": paths.get("png"),
        "sim_metadata_native_depth_view_csv_path": paths.get("csv"),
        "sim_expected_projected_point_count": len(sim_expected_points),
        "sim_expected_projected_points": sim_expected_points,
        "visual": visual,
        "records": records,
        "notes": [
            "This is a hardware-free intake artifact. It does not open a camera, connect motors, or infer real depth.",
            "status=missing_real_calibration is expected until real intrinsics plus board pose/extrinsics are supplied.",
            "The PNG is a side-by-side contact sheet, not a calibrated overlay, when calibration inputs are missing.",
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
