#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SCHEMA = "lerobot.sim.calibration_visual_review.v1"
DEFAULT_CONTACT_SHEET_CELL_WIDTH = 360
DEFAULT_VIDEO_FPS = 1.0
VIDEO_CODEC = "mp4v"
SIM_BOARD_SIZE_M = 0.4
PICK_PLACE_SEQUENCE_STAGES = (
    ("source_open_path", "Ready/open", "open gripper with piece at source"),
    ("source_hover_open_path", "Approach", "approach source square with gripper open"),
    ("source_pinched_path", "Grasp/contact", "close gripper around the source piece"),
    ("source_closed_path", "Lift", "closed-gripper pickup state before transfer"),
    ("target_hover_closed_path", "Transfer", "move closed gripper toward target square"),
    ("target_release_open_path", "Place/release", "open gripper with piece at target"),
    ("target_retreat_open_path", "Retreat", "open gripper retreat after release"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render durable PNG visual-review artifacts from an existing simulator "
            "calibration regression suite summary."
        )
    )
    parser.add_argument(
        "suite_summary",
        type=Path,
        help="Path to calibration_regression_summary.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to visual_review beside the suite summary.",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        default=DEFAULT_CONTACT_SHEET_CELL_WIDTH,
        help="Maximum image cell width for contact sheets.",
    )
    parser.add_argument(
        "--try-video",
        action="store_true",
        help="Best-effort MP4 from gripper POV annotated frames; skipped cleanly if unavailable.",
    )
    parser.add_argument(
        "--video-fps",
        type=float,
        default=DEFAULT_VIDEO_FPS,
        help="FPS for optional gripper POV review video.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


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


def resolve_path(value: str, *, suite_summary_path: Path, output_dir: Path, repo_root: Path | None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    output_candidate = (output_dir / path).resolve()
    if output_candidate.exists():
        return output_candidate

    if repo_root is not None:
        repo_candidate = (repo_root / path).resolve()
        if repo_candidate.exists():
            return repo_candidate

    return (suite_summary_path.parent / path).resolve()


def output_relative(path: Path, output_dir: Path) -> str | None:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return None


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"OpenCV could not read image {path}.")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected BGR image with 3 channels at {path}, got shape {image.shape}.")
    return image


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise ValueError(f"OpenCV could not write image {path}.")


def resize_to_max_width(image_bgr: np.ndarray, max_width: int) -> np.ndarray:
    if max_width <= 0:
        raise ValueError("--cell-width must be positive.")
    height, width = image_bgr.shape[:2]
    if width <= max_width:
        return image_bgr.copy()
    scale = float(max_width) / float(width)
    target = (max_width, max(1, int(round(height * scale))))
    return cv2.resize(image_bgr, target, interpolation=cv2.INTER_AREA)


def labeled_image(image_bgr: np.ndarray, *, label: str, detail: str = "") -> np.ndarray:
    label_height = 48 if detail else 30
    height, width = image_bgr.shape[:2]
    out = np.zeros((height + label_height, width, 3), dtype=np.uint8)
    out[:, :] = (18, 18, 18)
    out[label_height:, :] = image_bgr
    cv2.putText(out, label, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    if detail:
        cv2.putText(out, detail, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (205, 220, 255), 1, cv2.LINE_AA)
    return out


def ordered_path_rows(
    section: dict[str, Any],
    *,
    collection_key: str,
    ids_key: str,
    suite_summary_path: Path,
    suite_output_dir: Path,
    repo_root: Path | None,
) -> list[dict[str, Any]]:
    paths = section.get(collection_key)
    if not isinstance(paths, dict) or not paths:
        return []

    ordered_ids: list[str] = []
    ids = section.get(ids_key)
    if isinstance(ids, list):
        ordered_ids.extend(str(value) for value in ids if str(value) in paths)
    ordered_ids.extend(sorted(str(key) for key in paths if str(key) not in set(ordered_ids)))

    rows: list[dict[str, Any]] = []
    for item_id in ordered_ids:
        value = paths.get(item_id)
        if not isinstance(value, str) or not value:
            continue
        resolved = resolve_path(
            value,
            suite_summary_path=suite_summary_path,
            output_dir=suite_output_dir,
            repo_root=repo_root,
        )
        rows.append({"id": item_id, "path": resolved, "path_value": value})
    return rows


def load_pick_place_matrix_summary(
    matrix: dict[str, Any],
    *,
    suite_summary_path: Path,
    suite_output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    summary_path_value = matrix.get("summary_path")
    if not isinstance(summary_path_value, str) or not summary_path_value:
        return {}
    summary_path = resolve_path(
        summary_path_value,
        suite_summary_path=suite_summary_path,
        output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    if not summary_path.is_file():
        return {}
    return read_json_object(summary_path, label="pick/place scenario matrix summary")


def selected_pick_place_scenario(matrix: dict[str, Any], matrix_summary: dict[str, Any]) -> dict[str, Any]:
    scenarios = matrix_summary.get("scenarios")
    scenario_rows = [row for row in scenarios if isinstance(row, dict)] if isinstance(scenarios, list) else []
    for wanted_id in ("center_to_center", "near_gripper_lower_board"):
        for scenario in scenario_rows:
            if scenario.get("scenario_id") == wanted_id:
                return scenario
    if scenario_rows:
        return scenario_rows[0]

    selected = matrix.get("selected_frame_paths")
    selected = selected if isinstance(selected, dict) else {}
    for wanted_id in ("center_to_center", "near_gripper_lower_board"):
        frame_paths = selected.get(wanted_id)
        if isinstance(frame_paths, dict):
            return {"scenario_id": wanted_id, "selected_frame_paths": frame_paths}
    for scenario_id, frame_paths in sorted(selected.items()):
        if isinstance(frame_paths, dict):
            return {"scenario_id": str(scenario_id), "selected_frame_paths": frame_paths}
    return {}


def rows_by_capture_label(section: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    captures = section.get("captures") if isinstance(section, dict) else None
    rows = captures if isinstance(captures, list) else []
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = row.get(key)
        if isinstance(label, str) and label:
            indexed[label] = row
    return indexed


def square_file_rank(square: str) -> tuple[int, int]:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(value[0]) - ord("a"), int(value[1]) - 1


def board_square_center_m(square: str, *, board_size_m: float = SIM_BOARD_SIZE_M) -> np.ndarray:
    file_idx, rank_idx = square_file_rank(square)
    square_size = float(board_size_m) / 8.0
    return np.array(
        [
            (file_idx + 0.5) * square_size,
            (rank_idx + 0.5) * square_size,
            0.0,
        ],
        dtype=float,
    )


def image_board_point(corners: np.ndarray, u: float, v: float) -> np.ndarray:
    a1, h1, h8, a8 = corners
    bottom = a1 * (1.0 - u) + h1 * u
    top = a8 * (1.0 - u) + h8 * u
    return bottom * (1.0 - v) + top * v


def rendered_square_center_xy(metadata: dict[str, Any], square: str) -> np.ndarray | None:
    try:
        file_idx, rank_idx = square_file_rank(square)
        corners = np.asarray(metadata.get("board_corners_xy"), dtype=float)
    except (TypeError, ValueError):
        return None
    if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
        return None
    return image_board_point(corners, (file_idx + 0.5) / 8.0, (rank_idx + 0.5) / 8.0)


def metadata_camera_model(metadata: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    try:
        camera_matrix = np.asarray(metadata.get("camera_matrix_px"), dtype=float)
        extrinsics = metadata.get("extrinsics")
        extrinsics = extrinsics if isinstance(extrinsics, dict) else {}
        board_to_camera = extrinsics.get("board_to_camera")
        board_to_camera = board_to_camera if isinstance(board_to_camera, dict) else {}
        rotation = np.asarray(board_to_camera.get("rotation_matrix"), dtype=float)
        translation = np.asarray(board_to_camera.get("translation_m"), dtype=float)
    except (TypeError, ValueError):
        return None
    if camera_matrix.shape != (3, 3) or rotation.shape != (3, 3) or translation.shape != (3,):
        return None
    if not (
        np.all(np.isfinite(camera_matrix))
        and np.all(np.isfinite(rotation))
        and np.all(np.isfinite(translation))
    ):
        return None
    return camera_matrix, rotation, translation


def project_board_point_m(metadata: dict[str, Any], board_point_m: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    model = metadata_camera_model(metadata)
    if model is None:
        return None
    camera_matrix, rotation, translation = model
    camera_point = rotation @ np.asarray(board_point_m, dtype=float).reshape(3) + translation
    if not np.isfinite(camera_point).all() or abs(float(camera_point[2])) < 1e-9:
        return None
    projected = camera_matrix @ camera_point
    image_xy = projected[:2] / projected[2]
    if not np.isfinite(image_xy).all():
        return None
    return camera_point, image_xy


def camera_center_board_m(metadata: dict[str, Any]) -> np.ndarray | None:
    model = metadata_camera_model(metadata)
    if model is None:
        return None
    _, rotation, translation = model
    center = -(rotation.T @ translation)
    return center if np.isfinite(center).all() else None


def camera_ray_board_intersection_m(metadata: dict[str, Any], image_xy: np.ndarray) -> np.ndarray | None:
    model = metadata_camera_model(metadata)
    center = camera_center_board_m(metadata)
    if model is None or center is None:
        return None
    camera_matrix, rotation, _ = model
    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    cx = float(camera_matrix[0, 2])
    cy = float(camera_matrix[1, 2])
    if abs(fx) < 1e-9 or abs(fy) < 1e-9:
        return None
    direction_camera = np.array(
        [
            (float(image_xy[0]) - cx) / fx,
            (float(image_xy[1]) - cy) / fy,
            1.0,
        ],
        dtype=float,
    )
    direction_board = rotation.T @ direction_camera
    if not np.isfinite(direction_board).all() or abs(float(direction_board[2])) < 1e-9:
        return None
    scale = -float(center[2]) / float(direction_board[2])
    point = center + scale * direction_board
    if not np.isfinite(point).all():
        return None
    return point


def rounded_list(values: np.ndarray | list[float] | None, digits: int = 6) -> list[float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all():
        return None
    return [round(float(value), digits) for value in array.reshape(-1)]


def rounded_float(value: float | np.floating[Any] | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    value_float = float(value)
    if not math.isfinite(value_float):
        return None
    return round(value_float, digits)


def meters_to_mm(value: float | np.floating[Any] | None, digits: int = 1) -> float | None:
    rounded = rounded_float(value)
    if rounded is None:
        return None
    return round(float(rounded) * 1000.0, digits)


def vector_m_to_mm(values: np.ndarray | list[float] | None, digits: int = 1) -> list[float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all():
        return None
    return [round(float(value) * 1000.0, digits) for value in array.reshape(-1)]


def distance_or_none(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    if a is None or b is None:
        return None
    return rounded_float(float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))))


def piece_center_from_capture(capture: dict[str, Any], metadata: dict[str, Any], piece_square: str) -> np.ndarray | None:
    metric = capture.get("piece_visibility")
    metric = metric if isinstance(metric, dict) else {}
    piece = metric.get("piece")
    piece = piece if isinstance(piece, dict) else {}
    center = piece.get("center_xy")
    if isinstance(center, list) and len(center) >= 2:
        try:
            point = np.asarray(center[:2], dtype=float)
            if np.isfinite(point).all():
                return point
        except (TypeError, ValueError):
            pass
    return rendered_square_center_xy(metadata, piece_square)


def projection_residual_px(projected_xy: np.ndarray | None, rendered_xy: np.ndarray | None) -> float | None:
    if projected_xy is None or rendered_xy is None:
        return None
    return rounded_float(float(np.linalg.norm(np.asarray(projected_xy) - np.asarray(rendered_xy))))


def board_corner_projection_residuals(metadata: dict[str, Any]) -> dict[str, Any]:
    rendered = metadata.get("board_corners_xy")
    try:
        rendered_corners = np.asarray(rendered, dtype=float)
    except (TypeError, ValueError):
        return {"available": False, "reason": "board_corners_xy unavailable"}
    if rendered_corners.shape != (4, 2) or not np.all(np.isfinite(rendered_corners)):
        return {"available": False, "reason": "board_corners_xy invalid"}

    model_corners = np.array(
        [
            [0.0, 0.0, 0.0],
            [SIM_BOARD_SIZE_M, 0.0, 0.0],
            [SIM_BOARD_SIZE_M, SIM_BOARD_SIZE_M, 0.0],
            [0.0, SIM_BOARD_SIZE_M, 0.0],
        ],
        dtype=float,
    )
    projected_rows: list[list[float] | None] = []
    residuals: list[float] = []
    for point, actual in zip(model_corners, rendered_corners, strict=True):
        projected = project_board_point_m(metadata, point)
        if projected is None:
            projected_rows.append(None)
            continue
        _, projected_xy = projected
        projected_rows.append(rounded_list(projected_xy, digits=3))
        residual = projection_residual_px(projected_xy, actual)
        if residual is not None:
            residuals.append(float(residual))
    if not residuals:
        return {"available": False, "reason": "board corner projection unavailable"}
    return {
        "available": True,
        "projected_corners_xy": projected_rows,
        "rendered_corners_xy": rounded_list(rendered_corners.reshape(-1), digits=3),
        "mean_residual_px": rounded_float(float(np.mean(residuals)), digits=3),
        "max_residual_px": rounded_float(float(np.max(residuals)), digits=3),
        "residuals_px": [rounded_float(value, digits=3) for value in residuals],
    }


def compute_depth_distance_metric(row: dict[str, Any]) -> dict[str, Any]:
    capture = row.get("capture")
    capture = capture if isinstance(capture, dict) else {}
    metadata = capture.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    piece_square = str(metadata.get("piece_square") or row.get("source_square") or "")
    target_square = str(row.get("target_square") or piece_square)

    try:
        piece_board_m = board_square_center_m(piece_square)
        target_board_m = board_square_center_m(target_square)
    except ValueError as exc:
        return {
            "id": row.get("id"),
            "capture_label": row.get("capture_label"),
            "stage": row.get("stage"),
            "status": "metric_unavailable",
            "ok": False,
            "reason": str(exc),
            "perceived_depth_status": "not_implemented",
            "distance_depth_fields": {
                "simulator_ground_truth": True,
                "perceived_depth_status": "not_implemented",
                "metric_status": "metric_unavailable",
            },
        }
    board_center_m = np.array([SIM_BOARD_SIZE_M / 2.0, SIM_BOARD_SIZE_M / 2.0, 0.0], dtype=float)
    camera_center_m = camera_center_board_m(metadata)

    piece_projection = project_board_point_m(metadata, piece_board_m)
    target_projection = project_board_point_m(metadata, target_board_m)
    piece_camera_m = piece_projection[0] if piece_projection is not None else None
    target_camera_m = target_projection[0] if target_projection is not None else None
    piece_projected_xy = piece_projection[1] if piece_projection is not None else None
    target_projected_xy = target_projection[1] if target_projection is not None else None
    piece_rendered_xy = piece_center_from_capture(capture, metadata, piece_square)
    target_rendered_xy = rendered_square_center_xy(metadata, target_square)

    image_size = metadata.get("image_size_px")
    image_size = image_size if isinstance(image_size, dict) else {}
    width = float(image_size.get("width") or 0.0)
    height = float(image_size.get("height") or 0.0)
    gripper_image_xy = np.array([width / 2.0, height * 0.78], dtype=float) if width > 0 and height > 0 else None
    gripper_board_proxy_m = (
        camera_ray_board_intersection_m(metadata, gripper_image_xy)
        if gripper_image_xy is not None
        else None
    )
    gripper_to_piece_image_px = (
        projection_residual_px(gripper_image_xy, piece_rendered_xy)
        if gripper_image_xy is not None
        else None
    )

    board_corner_residuals = board_corner_projection_residuals(metadata)
    target_offset_board_m = piece_board_m - target_board_m
    target_offset_norm_m = distance_or_none(piece_board_m, target_board_m)
    camera_to_board_plane_m = (
        rounded_float(abs(float(camera_center_m[2]))) if camera_center_m is not None else None
    )
    camera_to_board_center_m = distance_or_none(camera_center_m, board_center_m)
    camera_to_piece_m = (
        rounded_float(float(np.linalg.norm(piece_camera_m))) if piece_camera_m is not None else None
    )
    camera_to_target_square_m = (
        rounded_float(float(np.linalg.norm(target_camera_m))) if target_camera_m is not None else None
    )
    gripper_to_piece_board_plane_proxy_m = distance_or_none(gripper_board_proxy_m, piece_board_m)
    piece_projection_residual = projection_residual_px(piece_projected_xy, piece_rendered_xy)
    target_projection_residual = projection_residual_px(target_projected_xy, target_rendered_xy)
    true_gripper_status = "unavailable_without_ee_kinematics_or_depth_sensor"
    perceived_depth_status = "not_implemented"

    distance_depth_fields = {
        "simulator_ground_truth": True,
        "ground_truth_frame": "sim_board_frame_xyz_mm",
        "metric_status": "ok",
        "camera_to_piece_distance_mm": meters_to_mm(camera_to_piece_m),
        "camera_to_board_plane_distance_mm": meters_to_mm(camera_to_board_plane_m),
        "camera_to_board_center_distance_mm": meters_to_mm(camera_to_board_center_m),
        "camera_to_target_square_distance_mm": meters_to_mm(camera_to_target_square_m),
        "true_gripper_to_piece_distance_mm": None,
        "true_gripper_to_piece_status": true_gripper_status,
        "gripper_to_piece_distance_mm": meters_to_mm(gripper_to_piece_board_plane_proxy_m),
        "gripper_to_piece_distance_source": "board_plane_proxy_from_rendered_gripper_overlay",
        "gripper_to_piece_image_px": gripper_to_piece_image_px,
        "piece_world_xyz_mm": vector_m_to_mm(piece_board_m),
        "gripper_world_xyz_mm": vector_m_to_mm(gripper_board_proxy_m),
        "gripper_world_xyz_source": "camera_ray_intersection_with_sim_board_plane",
        "target_square_world_xy_mm": vector_m_to_mm(target_board_m[:2]),
        "target_square_world_xyz_mm": vector_m_to_mm(target_board_m),
        "target_actual_offset_world_mm": vector_m_to_mm(target_offset_board_m),
        "target_actual_offset_norm_mm": meters_to_mm(target_offset_norm_m),
        "piece_projected_pixel_xy": rounded_list(piece_projected_xy, digits=3),
        "piece_rendered_pixel_xy": rounded_list(piece_rendered_xy, digits=3),
        "piece_projection_residual_px": piece_projection_residual,
        "target_square_projected_pixel_xy": rounded_list(target_projected_xy, digits=3),
        "target_square_rendered_pixel_xy": rounded_list(target_rendered_xy, digits=3),
        "target_square_projection_residual_px": target_projection_residual,
        "board_corner_projection_mean_residual_px": board_corner_residuals.get("mean_residual_px")
        if isinstance(board_corner_residuals, dict)
        else None,
        "board_corner_projection_max_residual_px": board_corner_residuals.get("max_residual_px")
        if isinstance(board_corner_residuals, dict)
        else None,
        "perceived_depth_status": perceived_depth_status,
        "perceived_depth_distance_mm": None,
        "perceived_depth_gap": (
            "Simulator ground truth is available, but no inferred real-camera or depth-sensor "
            "estimate is implemented in this hardware-free smoke."
        ),
    }
    depth_source = {
        "ground_truth_simulator": (
            "Distances are computed from SimCamera board_to_camera extrinsics and "
            f"a {SIM_BOARD_SIZE_M} m board size in the simulator board frame."
        ),
        "gripper_board_plane_proxy": (
            "Gripper-to-piece distance is a camera ray-to-board-plane proxy from the rendered "
            "gripper overlay midpoint; true SO-101 end-effector depth is not available in this "
            "hardware-free joint-state smoke."
        ),
        "perceived_depth_estimate": "not_implemented",
    }

    return {
        "id": row.get("id"),
        "capture_label": row.get("capture_label"),
        "stage": row.get("stage"),
        "description": row.get("description"),
        "status": "ok",
        "ok": True,
        "scenario_id": row.get("scenario_id"),
        "source_square": row.get("source_square"),
        "target_square": target_square,
        "piece_square": piece_square,
        "distance_depth_fields": distance_depth_fields,
        "perceived_depth_status": perceived_depth_status,
        "board_frame": {
            "units": "meters",
            "board_size_m": SIM_BOARD_SIZE_M,
            "piece_center_m": rounded_list(piece_board_m),
            "target_square_center_m": rounded_list(target_board_m),
            "target_offset_piece_minus_target_m": rounded_list(target_offset_board_m),
            "target_offset_norm_m": target_offset_norm_m,
        },
        "camera_ground_truth": {
            "units": "meters",
            "camera_center_board_m": rounded_list(camera_center_m),
            "camera_to_board_plane_m": camera_to_board_plane_m,
            "camera_to_board_center_m": camera_to_board_center_m,
            "camera_to_piece_m": camera_to_piece_m,
            "camera_to_target_square_m": camera_to_target_square_m,
        },
        "gripper_distance": {
            "true_gripper_to_piece_m": None,
            "true_gripper_to_piece_status": true_gripper_status,
            "board_plane_proxy_m": rounded_list(gripper_board_proxy_m),
            "gripper_to_piece_board_plane_proxy_m": gripper_to_piece_board_plane_proxy_m,
            "gripper_to_piece_image_px": gripper_to_piece_image_px,
            "gripper_image_proxy_xy": rounded_list(gripper_image_xy, digits=3),
        },
        "projection": {
            "piece_projected_xy": rounded_list(piece_projected_xy, digits=3),
            "piece_rendered_xy": rounded_list(piece_rendered_xy, digits=3),
            "piece_projection_residual_px": piece_projection_residual,
            "target_projected_xy": rounded_list(target_projected_xy, digits=3),
            "target_rendered_xy": rounded_list(target_rendered_xy, digits=3),
            "target_projection_residual_px": target_projection_residual,
            "board_corner_projection_residuals": board_corner_residuals,
        },
        "perceived_depth_estimate": {
            "implemented": False,
            "distance_m": None,
            "status": perceived_depth_status,
            "next_follow_up": (
                "Add manifest-aware real-media/depth comparison or a perception depth estimate "
                "beside this simulator ground truth."
            ),
        },
        "source": depth_source,
    }


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return "" if value is None else value


def write_depth_distance_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "stage",
        "capture_label",
        "source_square",
        "target_square",
        "piece_square",
        "simulator_ground_truth",
        "ground_truth_frame",
        "camera_to_piece_distance_mm",
        "camera_to_board_plane_distance_mm",
        "camera_to_board_center_distance_mm",
        "camera_to_target_square_distance_mm",
        "true_gripper_to_piece_distance_mm",
        "true_gripper_to_piece_status",
        "gripper_to_piece_distance_mm",
        "gripper_to_piece_distance_source",
        "gripper_to_piece_image_px",
        "piece_world_xyz_mm",
        "gripper_world_xyz_mm",
        "gripper_world_xyz_source",
        "target_square_world_xy_mm",
        "target_square_world_xyz_mm",
        "target_actual_offset_world_mm",
        "target_actual_offset_norm_mm",
        "piece_projected_pixel_xy",
        "piece_rendered_pixel_xy",
        "piece_projection_residual_px",
        "target_square_projected_pixel_xy",
        "target_square_rendered_pixel_xy",
        "target_square_projection_residual_px",
        "board_corner_projection_mean_residual_px",
        "board_corner_projection_max_residual_px",
        "perceived_depth_status",
        "perceived_depth_distance_mm",
        "perceived_depth_gap",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = row.get("distance_depth_fields")
            flat = flat if isinstance(flat, dict) else {}
            writer.writerow(
                {
                    "id": row.get("id"),
                    "stage": row.get("stage"),
                    "capture_label": row.get("capture_label"),
                    "source_square": row.get("source_square"),
                    "target_square": row.get("target_square"),
                    "piece_square": row.get("piece_square"),
                    **{
                        key: csv_value(flat.get(key))
                        for key in fieldnames
                        if key
                        not in {
                            "id",
                            "stage",
                            "capture_label",
                            "source_square",
                            "target_square",
                            "piece_square",
                        }
                    },
                }
            )


def write_depth_distance_metrics(
    *,
    rows: list[dict[str, Any]],
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
) -> dict[str, Any]:
    metric_rows = [compute_depth_distance_metric(row) for row in rows]
    json_path = output_dir / "pick_place_depth_distance_metrics.json"
    csv_path = output_dir / "pick_place_depth_distance_metrics.csv"
    summary = {
        "schema": "lerobot.sim.pick_place_depth_distance_metrics.v1",
        "ok": True,
        "status": "ok",
        "scenario_id": sequence_metadata.get("scenario_id"),
        "source_square": sequence_metadata.get("source_square"),
        "target_square": sequence_metadata.get("target_square"),
        "frame_count": len(metric_rows),
        "units": {
            "distance_depth_fields": "millimeters",
            "legacy_nested_distance_fields": "meters",
            "image": "pixels",
        },
        "paths": {
            "json": str(json_path),
            "csv": str(csv_path),
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
        },
        "ground_truth_scope": (
            "Simulator-only geometry from SimCamera board_to_camera metadata and the "
            "rendered board/piece metadata. This is not real-camera depth estimation."
        ),
        "metric_sources": {
            "camera_to_piece_distance_mm": "simulator_ground_truth_from_board_to_camera_extrinsics",
            "camera_to_board_plane_distance_mm": "simulator_ground_truth_from_camera_center_to_board_z0",
            "gripper_to_piece_distance_mm": "board_plane_proxy_from_rendered_gripper_overlay",
            "world_coordinates_mm": "simulator_board_frame",
            "projected_pixel_coordinates": "SimCamera intrinsics/extrinsics projected into the rendered image",
        },
        "perceived_depth_status": "not_implemented",
        "true_depth_estimation": {
            "implemented": False,
            "status": "not_implemented",
            "gap": (
                "The current smoke provides simulator ground-truth distances and a gripper "
                "image/board-plane proxy, but no real depth sensor, stereo estimate, or "
                "SO-101 end-effector-to-piece 3D contact estimate."
            ),
        },
        "rows": metric_rows,
    }
    write_json(json_path, summary)
    write_depth_distance_csv(csv_path, metric_rows)
    return summary


def pick_place_sequence_rows(
    matrix: dict[str, Any],
    *,
    suite_summary_path: Path,
    suite_output_dir: Path,
    repo_root: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matrix_summary = load_pick_place_matrix_summary(
        matrix,
        suite_summary_path=suite_summary_path,
        suite_output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    scenario = selected_pick_place_scenario(matrix, matrix_summary)
    child_summary = {}
    summary_path_value = scenario.get("summary_path")
    if isinstance(summary_path_value, str) and summary_path_value:
        child_summary_path = resolve_path(
            summary_path_value,
            suite_summary_path=suite_summary_path,
            output_dir=suite_output_dir,
            repo_root=repo_root,
        )
        if child_summary_path.is_file():
            child_summary = read_json_object(child_summary_path, label="pick/place scenario summary")
    frame_paths = scenario.get("selected_frame_paths")
    frame_paths = frame_paths if isinstance(frame_paths, dict) else {}
    if not frame_paths:
        raise ValueError("pick_place_scenario_matrix.selected_frame_paths is not populated.")

    scenario_id = str(scenario.get("scenario_id") or "pick_place_sequence")
    gripper_rows = rows_by_capture_label(
        scenario.get("gripper_visibility") if isinstance(scenario.get("gripper_visibility"), dict) else {},
        "label",
    )
    visibility_rows = rows_by_capture_label(
        scenario.get("piece_visibility") if isinstance(scenario.get("piece_visibility"), dict) else {},
        "label",
    )
    capture_rows = rows_by_capture_label(child_summary, "label")

    rows: list[dict[str, Any]] = []
    for index, (path_key, stage, description) in enumerate(PICK_PLACE_SEQUENCE_STAGES, start=1):
        path_value = frame_paths.get(path_key)
        if not isinstance(path_value, str) or not path_value:
            continue
        capture_label = path_key.removesuffix("_path")
        resolved = resolve_path(
            path_value,
            suite_summary_path=suite_summary_path,
            output_dir=suite_output_dir,
            repo_root=repo_root,
        )
        gripper = gripper_rows.get(capture_label, {})
        visibility = visibility_rows.get(capture_label, {})
        capture = capture_rows.get(capture_label, {})
        rows.append(
            {
                "id": f"{index:02d}_{capture_label}",
                "path": resolved,
                "path_value": path_value,
                "capture_label": capture_label,
                "stage": stage,
                "description": description,
                "scenario_id": scenario_id,
                "source_square": scenario.get("source_square"),
                "target_square": scenario.get("target_square"),
                "gripper": gripper,
                "piece_visibility": visibility,
                "capture": capture,
            }
        )
    if len(rows) < 6:
        raise ValueError(f"Expected at least 6 pick/place sequence frames, found {len(rows)}.")

    return rows, {
        "scenario_id": scenario_id,
        "source_square": scenario.get("source_square"),
        "target_square": scenario.get("target_square"),
        "matrix_summary_path": matrix_summary.get("summary_path") or matrix.get("summary_path"),
        "scenario_summary_path": child_summary.get("summary_path") or scenario.get("summary_path"),
        "source": "pick_place_scenario_matrix.selected_frame_paths",
    }


def short_text(value: Any, max_chars: int = 116) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def metric_dict(row: dict[str, Any]) -> dict[str, Any]:
    metric = row.get("depth_distance_metric")
    metric = metric if isinstance(metric, dict) else {}
    flat = metric.get("distance_depth_fields")
    return flat if isinstance(flat, dict) else {}


def fmt_mm(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.1f}mm"


def fmt_px(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.1f}px"


def fmt_xy(value: Any) -> str:
    if not isinstance(value, list) or len(value) < 2:
        return "n/a"
    return f"({float(value[0]):.1f},{float(value[1]):.1f})"


def annotate_pick_place_frame(image_bgr: np.ndarray, row: dict[str, Any]) -> np.ndarray:
    header_height = 120
    height, width = image_bgr.shape[:2]
    out = np.zeros((height + header_height, width, 3), dtype=np.uint8)
    out[:, :] = (18, 18, 18)
    out[header_height:, :] = image_bgr

    gripper = row.get("gripper")
    gripper = gripper if isinstance(gripper, dict) else {}
    visibility = row.get("piece_visibility")
    visibility = visibility if isinstance(visibility, dict) else {}
    title = f"{row.get('id')} | {row.get('stage')}"
    route = f"{row.get('scenario_id')} | {row.get('source_square')} -> {row.get('target_square')} | capture={row.get('capture_label')}"
    visibility_metrics = (
        f"gripper={gripper.get('tracked_gripper_percent')}% opening={gripper.get('current_gripper_opening_px')}px "
        f"| visible={visibility.get('visible_fraction')} occlusion={visibility.get('occlusion_fraction')} "
        f"| clearance={visibility.get('min_clearance_px')}"
    )
    depth = metric_dict(row)
    distance_metrics = (
        f"GT cam-piece={fmt_mm(depth.get('camera_to_piece_distance_mm'))} "
        f"cam-board={fmt_mm(depth.get('camera_to_board_plane_distance_mm'))} "
        f"cam-target={fmt_mm(depth.get('camera_to_target_square_distance_mm'))} "
        f"| target offset={fmt_mm(depth.get('target_actual_offset_norm_mm'))}"
    )
    target_metrics = (
        f"target_world_xy_mm={depth.get('target_square_world_xy_mm')} "
        f"piece_px={fmt_xy(depth.get('piece_projected_pixel_xy'))} "
        f"target_px={fmt_xy(depth.get('target_square_projected_pixel_xy'))} "
        f"resid={fmt_px(depth.get('piece_projection_residual_px'))}"
    )
    gripper_source = depth.get("gripper_to_piece_distance_source")
    if gripper_source == "board_plane_proxy_from_rendered_gripper_overlay":
        gripper_source = "board-plane proxy"
    perceived_status = depth.get("perceived_depth_status")
    if perceived_status == "not_implemented":
        perceived_status = "not impl"
    gripper_metrics = (
        f"proxy grip-piece={fmt_mm(depth.get('gripper_to_piece_distance_mm'))} "
        f"({gripper_source or 'n/a'}) "
        f"| perceived depth={perceived_status or 'n/a'}"
    )
    cv2.putText(out, short_text(title), (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(route), (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (205, 220, 255), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(distance_metrics, 138), (10, 67), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (205, 245, 205), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(target_metrics, 138), (10, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 230, 175), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(gripper_metrics, 138), (10, 108), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 210, 210), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(visibility_metrics, 138), (10, 116), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (190, 220, 255), 1, cv2.LINE_AA)
    return out


def render_pick_place_sequence_frames(
    rows: list[dict[str, Any]],
    *,
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frame_dir = output_dir / "pick_place_sequence_frames"
    annotated_rows: list[dict[str, Any]] = []
    frame_summaries: list[dict[str, Any]] = []
    for row in rows:
        source_path = Path(row["path"])
        source = read_image(source_path)
        annotated = annotate_pick_place_frame(source, row)
        output_path = frame_dir / f"{row['id']}.png"
        write_image(output_path, annotated)
        annotated_row = {**row, "path": output_path, "source_path": source_path}
        depth_fields = metric_dict(row)
        annotated_rows.append(annotated_row)
        frame_summaries.append(
            {
                "id": row["id"],
                "capture_label": row.get("capture_label"),
                "stage": row.get("stage"),
                "description": row.get("description"),
                "path": str(output_path),
                "relative_path": output_relative(output_path, suite_output_dir),
                "source_path": str(source_path),
                "source_relative_path": output_relative(source_path, suite_output_dir),
                "output_dimensions": {
                    "width_px": int(annotated.shape[1]),
                    "height_px": int(annotated.shape[0]),
                    "channels": int(annotated.shape[2]),
                },
                "gripper": row.get("gripper"),
                "piece_visibility": row.get("piece_visibility"),
                "distance_depth_fields": depth_fields,
            }
        )
    return (
        {
            "id": "pick_place_sequence",
            "label": "Pick/Place Gripper-Camera Sequence",
            **sequence_metadata,
            "frame_count": len(frame_summaries),
            "frames": frame_summaries,
        },
        annotated_rows,
    )


def make_contact_sheet(
    rows: list[dict[str, Any]],
    *,
    title: str,
    output_path: Path,
    suite_output_dir: Path,
    cell_width: int,
) -> dict[str, Any]:
    if not rows:
        raise ValueError(f"No source frames found for contact sheet {title!r}.")

    cells: list[np.ndarray] = []
    source_paths: list[str] = []
    labels: list[str] = []
    for row in rows:
        path = Path(row["path"])
        if not path.is_file():
            raise ValueError(f"Source frame for {title!r} does not exist: {path}")
        source = read_image(path)
        resized = resize_to_max_width(source, cell_width)
        detail = output_relative(path, suite_output_dir) or str(path)
        cell = labeled_image(resized, label=str(row["id"]), detail=detail)
        cells.append(cell)
        source_paths.append(str(path))
        labels.append(str(row["id"]))

    columns = min(len(cells), 6)
    row_count = int(math.ceil(len(cells) / float(columns)))
    cell_w = max(int(cell.shape[1]) for cell in cells)
    cell_h = max(int(cell.shape[0]) for cell in cells)
    gap = 8
    title_h = 42
    sheet_w = columns * cell_w + (columns + 1) * gap
    sheet_h = title_h + row_count * cell_h + (row_count + 1) * gap
    sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
    sheet[:, :] = (32, 32, 32)
    cv2.putText(sheet, title, (gap, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 1, cv2.LINE_AA)

    for index, cell in enumerate(cells):
        row_index = index // columns
        column_index = index % columns
        x = gap + column_index * (cell_w + gap)
        y = title_h + gap + row_index * (cell_h + gap)
        sheet[y : y + cell.shape[0], x : x + cell.shape[1]] = cell

    write_image(output_path, sheet)
    return {
        "path": str(output_path),
        "relative_path": output_relative(output_path, suite_output_dir),
        "label": title,
        "source_frame_count": len(rows),
        "source_frame_labels": labels,
        "source_frame_paths": source_paths,
        "output_dimensions": {
            "width_px": int(sheet.shape[1]),
            "height_px": int(sheet.shape[0]),
            "channels": int(sheet.shape[2]),
        },
    }


def copy_app_entrypoint_frame(
    app_entrypoint: dict[str, Any],
    *,
    output_path: Path,
    suite_summary_path: Path,
    suite_output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    frame_path_value = app_entrypoint.get("frame_path")
    if not isinstance(frame_path_value, str) or not frame_path_value:
        raise ValueError("app_entrypoint_metadata.frame_path is not populated.")
    source_path = resolve_path(
        frame_path_value,
        suite_summary_path=suite_summary_path,
        output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    if not source_path.is_file():
        raise ValueError(f"App-entrypoint frame does not exist: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)
    image = read_image(output_path)
    return {
        "status": "ok",
        "source_path": str(source_path),
        "review_copy_path": str(output_path),
        "relative_path": output_relative(output_path, suite_output_dir),
        "output_dimensions": {
            "width_px": int(image.shape[1]),
            "height_px": int(image.shape[0]),
            "channels": int(image.shape[2]),
        },
    }


def video_frame(row: dict[str, Any], *, target_width: int | None) -> np.ndarray:
    image = read_image(Path(row["path"]))
    if target_width is not None:
        image = resize_to_max_width(image, target_width)
    detail = Path(row["path"]).name
    return labeled_image(image, label=str(row["id"]), detail=detail)


def render_optional_video(
    rows: list[dict[str, Any]],
    *,
    output_path: Path,
    fps: float,
    cell_width: int,
    try_video: bool,
) -> dict[str, Any]:
    if not try_video:
        return {
            "attempted": False,
            "produced": False,
            "path": None,
            "codec": None,
            "fps": None,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "not requested; PNG contact sheets are the CI-stable visual-review artifact",
        }
    if not rows:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "no gripper POV annotated frames were available",
        }
    if fps <= 0:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "--video-fps must be positive",
        }

    try:
        prepared = [video_frame(row, target_width=cell_width) for row in rows]
        frame_h, frame_w = prepared[0].shape[:2]
        normalized = [
            frame if frame.shape[:2] == (frame_h, frame_w) else cv2.resize(frame, (frame_w, frame_h), interpolation=cv2.INTER_AREA)
            for frame in prepared
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*VIDEO_CODEC),
            float(fps),
            (int(frame_w), int(frame_h)),
        )
        if not writer.isOpened():
            return {
                "attempted": True,
                "produced": False,
                "path": None,
                "codec": VIDEO_CODEC,
                "fps": fps,
                "frame_count": 0,
                "duration_seconds": 0.0,
                "skipped_reason": "OpenCV VideoWriter could not open an MP4 writer",
            }
        try:
            for frame in normalized:
                writer.write(frame)
        finally:
            writer.release()
    except (cv2.error, OSError, ValueError) as exc:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": f"OpenCV MP4 render failed: {exc}",
        }

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "OpenCV reported success but no non-empty MP4 was written",
        }

    capture = cv2.VideoCapture(str(output_path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or len(rows))
        actual_fps = float(capture.get(cv2.CAP_PROP_FPS) or fps)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or frame_w)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or frame_h)
    finally:
        capture.release()
    duration = float(frame_count) / actual_fps if actual_fps > 0 else 0.0
    return {
        "attempted": True,
        "produced": True,
        "path": str(output_path),
        "codec": VIDEO_CODEC,
        "fps": actual_fps,
        "frame_count": frame_count,
        "duration_seconds": duration,
        "dimensions": {"width_px": width, "height_px": height},
        "skipped_reason": None,
    }


def build_summary(
    *,
    suite_summary_path: Path,
    output_dir: Path,
    cell_width: int,
    try_video: bool,
    video_fps: float,
) -> dict[str, Any]:
    suite = read_json_object(suite_summary_path, label="suite summary")
    suite_output_dir = Path(str(suite.get("output_dir") or suite_summary_path.parent)).expanduser().resolve()
    repo_root_value = suite.get("repo_root")
    repo_root = Path(repo_root_value).expanduser().resolve() if isinstance(repo_root_value, str) else None

    pose_fixture = suite.get("sim_camera_pose_fixture")
    pose_fixture = pose_fixture if isinstance(pose_fixture, dict) else {}
    pov = suite.get("gripper_camera_pov_review")
    pov = pov if isinstance(pov, dict) else {}
    matrix = suite.get("pick_place_scenario_matrix")
    matrix = matrix if isinstance(matrix, dict) else {}
    app_entrypoint = suite.get("app_entrypoint_metadata")
    app_entrypoint = app_entrypoint if isinstance(app_entrypoint, dict) else {}

    contact_specs = [
        {
            "id": "gripper_camera_pov_annotated",
            "label": "Gripper POV Annotated Contact Sheet",
            "section": pov,
            "collection_key": "annotated_frame_paths",
            "ids_key": "state_ids",
            "output_name": "gripper_camera_pov_annotated_contact_sheet.png",
            "source": "gripper_camera_pov_review.annotated_frame_paths",
        },
        {
            "id": "gripper_camera_pov_raw",
            "label": "Gripper POV Raw Contact Sheet",
            "section": pov,
            "collection_key": "frame_paths",
            "ids_key": "state_ids",
            "output_name": "gripper_camera_pov_raw_contact_sheet.png",
            "source": "gripper_camera_pov_review.frame_paths",
        },
        {
            "id": "sim_camera_pose_fixture_annotated",
            "label": "SimCamera Pose Fixture Annotated Contact Sheet",
            "section": pose_fixture,
            "collection_key": "annotated_frame_paths",
            "ids_key": "case_ids",
            "output_name": "sim_camera_pose_fixture_annotated_contact_sheet.png",
            "source": "sim_camera_pose_fixture.annotated_frame_paths",
        },
        {
            "id": "sim_camera_pose_fixture_raw",
            "label": "SimCamera Pose Fixture Raw Contact Sheet",
            "section": pose_fixture,
            "collection_key": "frame_paths",
            "ids_key": "case_ids",
            "output_name": "sim_camera_pose_fixture_raw_contact_sheet.png",
            "source": "sim_camera_pose_fixture.frame_paths",
        },
    ]

    contact_sheets: list[dict[str, Any]] = []
    gripper_annotated_rows: list[dict[str, Any]] = []
    for spec in contact_specs:
        rows = ordered_path_rows(
            spec["section"],
            collection_key=str(spec["collection_key"]),
            ids_key=str(spec["ids_key"]),
            suite_summary_path=suite_summary_path,
            suite_output_dir=suite_output_dir,
            repo_root=repo_root,
        )
        if spec["id"] == "gripper_camera_pov_annotated":
            gripper_annotated_rows = rows
        sheet = make_contact_sheet(
            rows,
            title=str(spec["label"]),
            output_path=output_dir / str(spec["output_name"]),
            suite_output_dir=suite_output_dir,
            cell_width=cell_width,
        )
        sheet.update(
            {
                "id": spec["id"],
                "source": spec["source"],
                "source_collection": spec["collection_key"],
            }
        )
        contact_sheets.append(sheet)

    pick_place_source_rows, pick_place_metadata = pick_place_sequence_rows(
        matrix,
        suite_summary_path=suite_summary_path,
        suite_output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    distance_metrics = write_depth_distance_metrics(
        rows=pick_place_source_rows,
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=pick_place_metadata,
    )
    metrics_by_id = {
        str(metric.get("id")): metric
        for metric in distance_metrics.get("rows", [])
        if isinstance(metric, dict) and metric.get("id") is not None
    }
    for row in pick_place_source_rows:
        row["depth_distance_metric"] = metrics_by_id.get(str(row.get("id")))
    pick_place_sequence, pick_place_annotated_rows = render_pick_place_sequence_frames(
        pick_place_source_rows,
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=pick_place_metadata,
    )
    for sheet_id, title, rows, output_name, source, collection in (
        (
            "pick_place_sequence_distance_annotated",
            "Pick/Place Sequence Distance-Annotated Contact Sheet",
            pick_place_annotated_rows,
            "pick_place_sequence_distance_annotated_contact_sheet.png",
            "visual_review.frame_sequences.pick_place_sequence.frames",
            "annotated_frame_paths",
        ),
        (
            "pick_place_sequence_raw",
            "Pick/Place Sequence Raw Contact Sheet",
            pick_place_source_rows,
            "pick_place_sequence_raw_contact_sheet.png",
            "pick_place_scenario_matrix.selected_frame_paths",
            "selected_frame_paths",
        ),
    ):
        sheet = make_contact_sheet(
            rows,
            title=title,
            output_path=output_dir / output_name,
            suite_output_dir=suite_output_dir,
            cell_width=cell_width,
        )
        sheet.update(
            {
                "id": sheet_id,
                "source": source,
                "source_collection": collection,
                "scenario_id": pick_place_metadata.get("scenario_id"),
            }
        )
        contact_sheets.append(sheet)

    app_frame = copy_app_entrypoint_frame(
        app_entrypoint,
        output_path=output_dir / "app_entrypoint_frame.jpg",
        suite_summary_path=suite_summary_path,
        suite_output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    recording = render_optional_video(
        gripper_annotated_rows,
        output_path=output_dir / "gripper_camera_pov_annotated_sequence.mp4",
        fps=float(video_fps),
        cell_width=int(cell_width),
        try_video=bool(try_video),
    )
    pick_place_recording = render_optional_video(
        pick_place_annotated_rows,
        output_path=output_dir / "pick_place_sequence_distance_annotated_sequence.mp4",
        fps=float(video_fps),
        cell_width=int(cell_width),
        try_video=bool(try_video),
    )

    return {
        "schema": SCHEMA,
        "ok": True,
        "status": "ok",
        "summary_path": str(output_dir / "visual_review_summary.json"),
        "suite_summary_path": str(suite_summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(repo_root) if repo_root else None,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "skipped_markers": {
            "hardware": "Visual review consumes generated simulator frames only; no SO-101 motors, serial ports, or camera devices are opened.",
            "gui": "Visual review writes image files directly and does not open display windows.",
            "openai": "Visual review is local image composition only; no OpenAI credentials or network calls are required.",
        },
        "contact_sheets": contact_sheets,
        "contact_sheet_paths": {str(sheet["id"]): str(sheet["path"]) for sheet in contact_sheets},
        "frame_sequences": [pick_place_sequence],
        "distance_metrics": distance_metrics,
        "app_entrypoint_frame": app_frame,
        "recording": recording,
        "recordings": {
            "gripper_camera_pov": recording,
            "pick_place_sequence": pick_place_recording,
        },
        "notes": [
            "Contact sheets are the stable review artifact and are generated from existing smoke frames.",
            "The pick/place sequence is rendered from the existing simulator scenario matrix and shows approach, grasp/contact, lift/transfer, place/release, and retreat frames with simulator ground-truth camera/board/piece distances.",
            "Pick/place depth artifacts label simulator ground truth separately from the unimplemented perceived-depth estimate; gripper-to-piece distance is currently a board-plane proxy from the rendered gripper overlay.",
            "Optional MP4 recordings are best-effort only and are not required for the suite to pass.",
            "No simulator pixels, camera profiles, perception algorithms, UI behavior, or robot paths are changed by this helper.",
        ],
    }


def failure_summary(output_dir: Path, suite_summary_path: Path, error: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "validation_failed",
        "summary_path": str(output_dir / "visual_review_summary.json"),
        "suite_summary_path": str(suite_summary_path),
        "output_dir": str(output_dir),
        "error": error,
        "contact_sheets": [],
        "contact_sheet_paths": {},
        "frame_sequences": [],
        "distance_metrics": {},
        "app_entrypoint_frame": None,
        "recording": {
            "attempted": False,
            "produced": False,
            "path": None,
            "skipped_reason": "visual review failed before optional video handling",
        },
        "recordings": {},
    }


def main() -> int:
    args = parse_args()
    suite_summary_path = args.suite_summary.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else suite_summary_path.parent / "visual_review"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary = build_summary(
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            cell_width=int(args.cell_width),
            try_video=bool(args.try_video),
            video_fps=float(args.video_fps),
        )
    except ValueError as exc:
        summary = failure_summary(output_dir, suite_summary_path, str(exc))
    write_json(output_dir / "visual_review_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
