#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SCHEMA = "lerobot.sim.calibration_visual_review.v1"
PERCEIVED_DEPTH_COMPARISON_SCHEMA = "lerobot.sim.pick_place_perceived_depth_comparison.v1"
PNP_RESIDUAL_DIAGNOSTIC_SCHEMA = "lerobot.sim.pick_place_pnp_residual_diagnostics.v1"
METADATA_NATIVE_DEPTH_VIEW_SCHEMA = "lerobot.sim.pick_place_metadata_native_depth_view.v1"
DEPTH_DISTANCE_SCORECARD_SCHEMA = "lerobot.sim.pick_place_depth_distance_scorecard.v1"
DEFAULT_CONTACT_SHEET_CELL_WIDTH = 360
DEFAULT_VIDEO_FPS = 1.0
VIDEO_CODEC = "mp4v"
SIM_BOARD_SIZE_M = 0.4
DEFAULT_BOARD_CORNER_ORDER = ("a1", "h1", "h8", "a8")
METADATA_PROJECTION_COMPARABILITY_THRESHOLD_PX = 5.0
PERCEIVED_DEPTH_ESTIMATOR_NAME = "rendered_board_corner_planar_pnp"
PERCEIVED_DEPTH_ESTIMATOR_STATUS = "metadata_derived_baseline"
PERCEIVED_DEPTH_ESTIMATOR_SOURCE = (
    "metadata_derived_from_rendered_board_corners_camera_intrinsics_and_known_board_size"
)
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


def board_corner_object_points_m() -> np.ndarray:
    return np.array(
        [
            [0.0, 0.0, 0.0],
            [SIM_BOARD_SIZE_M, 0.0, 0.0],
            [SIM_BOARD_SIZE_M, SIM_BOARD_SIZE_M, 0.0],
            [0.0, SIM_BOARD_SIZE_M, 0.0],
        ],
        dtype=np.float64,
    )


def board_corner_label_to_object_point_m(label: str) -> np.ndarray:
    points = {
        "a1": np.array([0.0, 0.0, 0.0], dtype=np.float64),
        "h1": np.array([SIM_BOARD_SIZE_M, 0.0, 0.0], dtype=np.float64),
        "h8": np.array([SIM_BOARD_SIZE_M, SIM_BOARD_SIZE_M, 0.0], dtype=np.float64),
        "a8": np.array([0.0, SIM_BOARD_SIZE_M, 0.0], dtype=np.float64),
    }
    try:
        return points[str(label)]
    except KeyError as exc:
        raise ValueError(f"Unsupported board corner label {label!r}.") from exc


def board_corner_object_points_for_order(labels: list[str] | tuple[str, ...]) -> np.ndarray:
    if len(labels) != 4:
        raise ValueError("Board corner order must contain exactly four labels.")
    return np.asarray([board_corner_label_to_object_point_m(label) for label in labels], dtype=np.float64)


def metadata_declared_corner_order(metadata: dict[str, Any]) -> list[str]:
    convention = metadata.get("coordinate_frame_convention")
    convention = convention if isinstance(convention, dict) else {}
    order = convention.get("board_corners_xy_order")
    if (
        isinstance(order, list)
        and len(order) == 4
        and all(isinstance(value, str) for value in order)
    ):
        return [str(value) for value in order]
    return list(DEFAULT_BOARD_CORNER_ORDER)


def camera_distortion_coefficients(metadata: dict[str, Any]) -> np.ndarray:
    try:
        distortion = np.asarray(metadata.get("distortion_coefficients"), dtype=np.float64)
    except (TypeError, ValueError):
        distortion = np.zeros((5, 1), dtype=np.float64)
    if distortion.size == 0 or not np.isfinite(distortion).all():
        return np.zeros((5, 1), dtype=np.float64)
    return distortion.reshape(-1, 1)


def solve_rendered_board_corner_pnp(
    metadata: dict[str, Any],
    *,
    object_points: np.ndarray | None = None,
) -> dict[str, Any]:
    try:
        camera_matrix = np.asarray(metadata.get("camera_matrix_px"), dtype=np.float64)
        image_points = np.asarray(metadata.get("board_corners_xy"), dtype=np.float64)
    except (TypeError, ValueError):
        return {"status": "estimator_unavailable", "reason": "camera matrix or board corners are invalid"}
    if camera_matrix.shape != (3, 3):
        return {"status": "estimator_unavailable", "reason": "camera_matrix_px must be 3x3"}
    if image_points.shape != (4, 2):
        return {"status": "estimator_unavailable", "reason": "board_corners_xy must contain four 2D corners"}
    if not np.isfinite(camera_matrix).all() or not np.isfinite(image_points).all():
        return {"status": "estimator_unavailable", "reason": "camera matrix or board corners are non-finite"}

    object_points = board_corner_object_points_m() if object_points is None else np.asarray(object_points, dtype=np.float64)
    if object_points.shape != (4, 3) or not np.isfinite(object_points).all():
        return {"status": "estimator_unavailable", "reason": "object points must be four finite 3D corners"}
    distortion = camera_distortion_coefficients(metadata)
    candidate_flags = [
        getattr(cv2, "SOLVEPNP_IPPE", cv2.SOLVEPNP_ITERATIVE),
        cv2.SOLVEPNP_ITERATIVE,
    ]
    last_error: str | None = None
    candidates: list[dict[str, Any]] = []
    for flag in dict.fromkeys(candidate_flags):
        try:
            ok, rvec, tvec = cv2.solvePnP(
                object_points,
                image_points,
                camera_matrix,
                distortion,
                flags=int(flag),
            )
        except cv2.error as exc:
            last_error = str(exc)
            continue
        if not ok:
            last_error = "cv2.solvePnP returned false"
            continue
        rotation, _ = cv2.Rodrigues(rvec)
        translation = tvec.reshape(3).astype(float)
        projected, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, distortion)
        projected_points = projected.reshape(-1, 2)
        residuals = np.linalg.norm(projected_points - image_points, axis=1)
        if not (
            np.isfinite(rotation).all()
            and np.isfinite(translation).all()
            and np.isfinite(residuals).all()
        ):
            last_error = "estimated pose or reprojection residuals are non-finite"
            continue
        candidates.append(
            {
                "status": "ok",
                "rotation_matrix": rotation,
                "translation_m": translation,
                "projected_corners_xy": projected_points,
                "rendered_corners_xy": image_points,
                "corner_reprojection_residuals_px": residuals,
                "corner_reprojection_mean_residual_px": float(np.mean(residuals)),
                "solve_pnp_flag": int(flag),
            }
        )
    if candidates:
        best = min(candidates, key=lambda row: float(row["corner_reprojection_mean_residual_px"]))
        return {
            "status": "ok",
            "rotation_matrix": best["rotation_matrix"],
            "translation_m": best["translation_m"],
            "projected_corners_xy": best["projected_corners_xy"],
            "rendered_corners_xy": best["rendered_corners_xy"],
            "corner_reprojection_residuals_px": best["corner_reprojection_residuals_px"],
            "solve_pnp_flag": best["solve_pnp_flag"],
            "solve_pnp_candidate_count": len(candidates),
            "solve_pnp_candidate_flags": [int(candidate["solve_pnp_flag"]) for candidate in candidates],
            "solve_pnp_candidate_mean_residuals_px": [
                rounded_float(float(candidate["corner_reprojection_mean_residual_px"]), digits=3)
                for candidate in candidates
            ],
        }
    return {
        "status": "estimator_unavailable",
        "reason": last_error or "cv2.solvePnP could not estimate a board pose",
    }


def estimate_depth_from_rendered_board_geometry(
    metadata: dict[str, Any],
    *,
    piece_square: str,
    target_square: str,
) -> dict[str, Any]:
    pnp = solve_rendered_board_corner_pnp(metadata)
    if pnp.get("status") != "ok":
        return pnp
    try:
        piece_board_m = board_square_center_m(piece_square)
        target_board_m = board_square_center_m(target_square)
    except ValueError as exc:
        return {"status": "estimator_unavailable", "reason": str(exc)}

    rotation = np.asarray(pnp["rotation_matrix"], dtype=float)
    translation = np.asarray(pnp["translation_m"], dtype=float)
    camera_center_board_m = -(rotation.T @ translation)
    piece_camera_m = rotation @ piece_board_m + translation
    target_camera_m = rotation @ target_board_m + translation
    residuals = np.asarray(pnp["corner_reprojection_residuals_px"], dtype=float)
    return {
        "status": "ok",
        "estimated_camera_to_piece_distance_mm": meters_to_mm(float(np.linalg.norm(piece_camera_m))),
        "estimated_camera_to_board_plane_distance_mm": meters_to_mm(abs(float(camera_center_board_m[2]))),
        "estimated_camera_to_target_square_distance_mm": meters_to_mm(float(np.linalg.norm(target_camera_m))),
        "estimated_camera_center_board_mm": vector_m_to_mm(camera_center_board_m),
        "estimated_piece_camera_xyz_mm": vector_m_to_mm(piece_camera_m),
        "estimated_target_square_camera_xyz_mm": vector_m_to_mm(target_camera_m),
        "board_corner_reprojection_mean_residual_px": rounded_float(float(np.mean(residuals)), digits=3),
        "board_corner_reprojection_max_residual_px": rounded_float(float(np.max(residuals)), digits=3),
        "board_corner_reprojection_residuals_px": [rounded_float(value, digits=3) for value in residuals],
        "estimated_projected_corners_xy": rounded_list(
            np.asarray(pnp["projected_corners_xy"], dtype=float).reshape(-1),
            digits=3,
        ),
        "rendered_corners_xy": rounded_list(
            np.asarray(pnp["rendered_corners_xy"], dtype=float).reshape(-1),
            digits=3,
        ),
        "solve_pnp_flag": pnp.get("solve_pnp_flag"),
        "solve_pnp_candidate_count": pnp.get("solve_pnp_candidate_count"),
        "solve_pnp_candidate_flags": pnp.get("solve_pnp_candidate_flags"),
        "solve_pnp_candidate_mean_residuals_px": pnp.get("solve_pnp_candidate_mean_residuals_px"),
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


def subtract_or_none(left: Any, right: Any, digits: int = 1) -> float | None:
    if left is None or right is None:
        return None
    try:
        left_float = float(left)
        right_float = float(right)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(left_float) or not math.isfinite(right_float):
        return None
    return round(left_float - right_float, digits)


def abs_or_none(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(abs(float(value)), digits)


def pnp_pose_diagnostics(
    pnp: dict[str, Any],
    *,
    piece_square: str,
    target_square: str,
) -> dict[str, Any]:
    if pnp.get("status") != "ok":
        return {"status": pnp.get("status"), "reason": pnp.get("reason")}
    try:
        piece_board_m = board_square_center_m(piece_square)
        target_board_m = board_square_center_m(target_square)
    except ValueError as exc:
        return {"status": "estimator_unavailable", "reason": str(exc)}

    rotation = np.asarray(pnp["rotation_matrix"], dtype=float)
    translation = np.asarray(pnp["translation_m"], dtype=float)
    camera_center = -(rotation.T @ translation)
    piece_camera = rotation @ piece_board_m + translation
    target_camera = rotation @ target_board_m + translation
    residuals = np.asarray(pnp["corner_reprojection_residuals_px"], dtype=float)
    if not (
        np.isfinite(camera_center).all()
        and np.isfinite(piece_camera).all()
        and np.isfinite(target_camera).all()
        and np.isfinite(residuals).all()
    ):
        return {"status": "estimator_unavailable", "reason": "estimated pose contains non-finite values"}
    return {
        "status": "ok",
        "camera_center_board_m": camera_center,
        "camera_to_board_plane_m": abs(float(camera_center[2])),
        "camera_to_piece_m": float(np.linalg.norm(piece_camera)),
        "camera_to_target_square_m": float(np.linalg.norm(target_camera)),
        "piece_camera_m": piece_camera,
        "target_square_camera_m": target_camera,
        "board_corner_reprojection_mean_residual_px": float(np.mean(residuals)),
        "board_corner_reprojection_max_residual_px": float(np.max(residuals)),
        "board_corner_reprojection_residuals_px": residuals,
        "estimated_projected_corners_xy": np.asarray(pnp["projected_corners_xy"], dtype=float),
        "rendered_corners_xy": np.asarray(pnp["rendered_corners_xy"], dtype=float),
        "solve_pnp_flag": pnp.get("solve_pnp_flag"),
        "solve_pnp_candidate_count": pnp.get("solve_pnp_candidate_count"),
        "solve_pnp_candidate_flags": pnp.get("solve_pnp_candidate_flags"),
        "solve_pnp_candidate_mean_residuals_px": pnp.get("solve_pnp_candidate_mean_residuals_px"),
    }


def metadata_projected_board_corner_check(
    metadata: dict[str, Any],
    *,
    corner_order: list[str],
) -> dict[str, Any]:
    try:
        rendered_corners = np.asarray(metadata.get("board_corners_xy"), dtype=float)
        object_points = board_corner_object_points_for_order(corner_order)
    except (TypeError, ValueError) as exc:
        return {
            "status": "source_unavailable",
            "reason_label": "metadata_corner_geometry_unavailable",
            "reason": str(exc),
        }
    if rendered_corners.shape != (4, 2) or not np.isfinite(rendered_corners).all():
        return {
            "status": "source_unavailable",
            "reason_label": "rendered_board_corners_invalid",
            "reason": "camera_metadata.board_corners_xy must contain four finite 2D points",
        }
    if metadata_camera_model(metadata) is None:
        return {
            "status": "source_unavailable",
            "reason_label": "metadata_camera_model_unavailable",
            "reason": "camera matrix or board_to_camera extrinsics are unavailable",
        }

    projected_rows: list[np.ndarray] = []
    residuals: list[float] = []
    for point, rendered in zip(object_points, rendered_corners, strict=True):
        projected = project_board_point_m(metadata, point)
        if projected is None:
            return {
                "status": "source_unavailable",
                "reason_label": "metadata_projection_unavailable",
                "reason": "Could not project at least one metadata 3D board corner",
            }
        _, projected_xy = projected
        projected_rows.append(projected_xy)
        residuals.append(float(np.linalg.norm(projected_xy - rendered)))

    residual_array = np.asarray(residuals, dtype=float)
    mean_residual = float(np.mean(residual_array))
    comparable = mean_residual <= METADATA_PROJECTION_COMPARABILITY_THRESHOLD_PX
    reason_label = (
        "metadata_projection_matches_rendered_corners"
        if comparable
        else "rendered_board_corners_do_not_match_metadata_pinhole_projection"
    )
    return {
        "status": "ok",
        "corner_order": list(corner_order),
        "projected_corners_xy": rounded_list(np.asarray(projected_rows).reshape(-1), digits=3),
        "rendered_corners_xy": rounded_list(rendered_corners.reshape(-1), digits=3),
        "residuals_px": [rounded_float(value, digits=3) for value in residual_array],
        "mean_residual_px": rounded_float(mean_residual, digits=3),
        "max_residual_px": rounded_float(float(np.max(residual_array)), digits=3),
        "comparability_threshold_px": METADATA_PROJECTION_COMPARABILITY_THRESHOLD_PX,
        "geometrically_comparable": comparable,
        "reason_label": reason_label,
        "source": (
            "camera_metadata.camera_matrix_px plus "
            "camera_metadata.extrinsics.board_to_camera projected onto metadata board_corners_xy"
        ),
    }


def pnp_order_candidate_summary(
    metadata: dict[str, Any],
    *,
    declared_order: list[str],
    ground_truth_camera_center_m: np.ndarray | None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for order in itertools.permutations(DEFAULT_BOARD_CORNER_ORDER):
        try:
            object_points = board_corner_object_points_for_order(order)
        except ValueError:
            continue
        pnp = solve_rendered_board_corner_pnp(metadata, object_points=object_points)
        candidate: dict[str, Any] = {
            "corner_order": list(order),
            "status": pnp.get("status"),
        }
        if pnp.get("status") == "ok":
            pose = pnp_pose_diagnostics(
                pnp,
                piece_square=str(metadata.get("piece_square") or "e4"),
                target_square=str(metadata.get("piece_square") or "e4"),
            )
            candidate.update(
                {
                    "board_corner_reprojection_mean_residual_px": rounded_float(
                        pose.get("board_corner_reprojection_mean_residual_px"),
                        digits=3,
                    ),
                    "estimated_camera_center_board_mm": vector_m_to_mm(
                        pose.get("camera_center_board_m")
                    ),
                    "estimated_camera_to_board_plane_distance_mm": meters_to_mm(
                        pose.get("camera_to_board_plane_m")
                    ),
                    "solve_pnp_flag": pnp.get("solve_pnp_flag"),
                }
            )
            if ground_truth_camera_center_m is not None and pose.get("camera_center_board_m") is not None:
                candidate["camera_center_delta_norm_mm"] = meters_to_mm(
                    float(
                        np.linalg.norm(
                            np.asarray(pose["camera_center_board_m"], dtype=float)
                            - np.asarray(ground_truth_camera_center_m, dtype=float)
                        )
                    )
                )
        else:
            candidate["reason"] = pnp.get("reason")
        rows.append(candidate)

    ok_rows = [row for row in rows if row.get("status") == "ok"]
    by_center = sorted(
        [row for row in ok_rows if row.get("camera_center_delta_norm_mm") is not None],
        key=lambda row: float(row["camera_center_delta_norm_mm"]),
    )
    by_reprojection = sorted(
        [row for row in ok_rows if row.get("board_corner_reprojection_mean_residual_px") is not None],
        key=lambda row: float(row["board_corner_reprojection_mean_residual_px"]),
    )
    declared_key = tuple(declared_order)
    ranked_orders = [tuple(row["corner_order"]) for row in by_center if isinstance(row.get("corner_order"), list)]
    declared_rank = ranked_orders.index(declared_key) + 1 if declared_key in ranked_orders else None
    low_reprojection_count = sum(
        1
        for row in ok_rows
        if row.get("board_corner_reprojection_mean_residual_px") is not None
        and float(row["board_corner_reprojection_mean_residual_px"]) <= 1.0
    )
    best_center_order = by_center[0]["corner_order"] if by_center else None
    reason_label = (
        "corner_order_candidate_changes_closest_ground_truth_pose"
        if best_center_order is not None and list(best_center_order) != list(declared_order)
        else "declared_corner_order_recorded"
    )
    return {
        "declared_corner_order": list(declared_order),
        "tested_order_count": len(rows),
        "ok_order_count": len(ok_rows),
        "best_by_camera_center_delta": by_center[0] if by_center else None,
        "best_by_reprojection_residual": by_reprojection[0] if by_reprojection else None,
        "declared_order_rank_by_camera_center_delta": declared_rank,
        "low_reprojection_order_count": low_reprojection_count,
        "reason_label": reason_label,
        "candidate_rows": rows,
        "note": (
            "Low reprojection residual alone cannot prove the rendered-corner PnP pose matches "
            "the simulator metadata pose; this ranking compares estimated camera centers when "
            "metadata extrinsics are available."
        ),
    }


def source_comparability_diagnostic(
    *,
    metadata_projection_check: dict[str, Any],
    pnp_pose: dict[str, Any],
) -> dict[str, Any]:
    metadata_comparable = metadata_projection_check.get("geometrically_comparable")
    if metadata_projection_check.get("status") != "ok":
        rendered_vs_metadata_status = "source_unavailable"
        rendered_vs_metadata_reason = metadata_projection_check.get("reason_label")
    elif metadata_comparable is True:
        rendered_vs_metadata_status = "geometrically_comparable"
        rendered_vs_metadata_reason = "metadata_projection_matches_rendered_corners"
    else:
        rendered_vs_metadata_status = "not_geometrically_comparable"
        rendered_vs_metadata_reason = metadata_projection_check.get("reason_label")

    pnp_status = "geometrically_comparable" if metadata_comparable is True else rendered_vs_metadata_status
    pnp_reason = (
        "rendered_corner_pnp_and_ground_truth_share_metadata_projection"
        if metadata_comparable is True
        else "rendered_corner_pnp_uses_overlay_geometry_that_does_not_match_metadata_extrinsics"
    )
    if pnp_pose.get("status") != "ok":
        pnp_status = "source_unavailable"
        pnp_reason = pnp_pose.get("reason") or "rendered_corner_pnp_unavailable"

    return {
        "metadata_extrinsics_projected_corners_vs_rendered_corners": {
            "status": rendered_vs_metadata_status,
            "reason_label": rendered_vs_metadata_reason,
            "mean_residual_px": metadata_projection_check.get("mean_residual_px"),
            "threshold_px": metadata_projection_check.get("comparability_threshold_px"),
        },
        "rendered_board_corner_pnp_vs_sim_ground_truth": {
            "status": pnp_status,
            "reason_label": pnp_reason,
            "metadata_projection_mean_residual_px": metadata_projection_check.get("mean_residual_px"),
        },
        "rendered_board_corner_pnp_vs_rendered_corners": {
            "status": "geometrically_comparable_by_construction"
            if pnp_pose.get("status") == "ok"
            else "source_unavailable",
            "reason_label": (
                "pnp_reprojects_the_same_rendered_corners_used_as_inputs"
                if pnp_pose.get("status") == "ok"
                else pnp_pose.get("reason")
            ),
            "mean_reprojection_residual_px": rounded_float(
                pnp_pose.get("board_corner_reprojection_mean_residual_px"),
                digits=3,
            ),
        },
    }


def compute_pnp_residual_diagnostic_row(
    metric: dict[str, Any],
    source_row: dict[str, Any],
) -> dict[str, Any]:
    capture = source_row.get("capture")
    capture = capture if isinstance(capture, dict) else {}
    metadata = capture.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    flat = metric.get("distance_depth_fields")
    flat = flat if isinstance(flat, dict) else {}
    piece_square = str(metric.get("piece_square") or source_row.get("source_square") or "")
    target_square = str(metric.get("target_square") or source_row.get("target_square") or piece_square)
    declared_order = metadata_declared_corner_order(metadata)
    ground_truth_center = camera_center_board_m(metadata)
    metadata_projection = metadata_projected_board_corner_check(metadata, corner_order=declared_order)

    try:
        object_points = board_corner_object_points_for_order(declared_order)
    except ValueError:
        object_points = board_corner_object_points_m()
    pnp = solve_rendered_board_corner_pnp(metadata, object_points=object_points)
    pnp_pose = pnp_pose_diagnostics(pnp, piece_square=piece_square, target_square=target_square)
    comparability = source_comparability_diagnostic(
        metadata_projection_check=metadata_projection,
        pnp_pose=pnp_pose,
    )
    order_summary = pnp_order_candidate_summary(
        metadata,
        declared_order=declared_order,
        ground_truth_camera_center_m=ground_truth_center,
    )

    reason_labels = {
        metadata_projection.get("reason_label"),
        order_summary.get("reason_label"),
    }
    for row in comparability.values():
        if isinstance(row, dict) and row.get("status") in {
            "not_geometrically_comparable",
            "source_unavailable",
        }:
            reason_labels.add(row.get("reason_label"))
    if (
        pnp_pose.get("status") == "ok"
        and metadata_projection.get("status") == "ok"
        and metadata_projection.get("geometrically_comparable") is False
    ):
        reason_labels.add("pnp_fits_rendered_overlay_but_not_metadata_extrinsics")
    reason_label_rows = sorted(str(value) for value in reason_labels if value)

    pnp_camera_center = pnp_pose.get("camera_center_board_m")
    camera_center_delta_norm_mm = None
    if ground_truth_center is not None and pnp_camera_center is not None:
        camera_center_delta_norm_mm = meters_to_mm(
            float(
                np.linalg.norm(
                    np.asarray(pnp_camera_center, dtype=float)
                    - np.asarray(ground_truth_center, dtype=float)
                )
            )
        )
    piece_error = subtract_or_none(
        meters_to_mm(pnp_pose.get("camera_to_piece_m")),
        flat.get("camera_to_piece_distance_mm"),
    )
    board_error = subtract_or_none(
        meters_to_mm(pnp_pose.get("camera_to_board_plane_m")),
        flat.get("camera_to_board_plane_distance_mm"),
    )
    target_error = subtract_or_none(
        meters_to_mm(pnp_pose.get("camera_to_target_square_m")),
        flat.get("camera_to_target_square_distance_mm"),
    )

    return {
        "id": metric.get("id") or source_row.get("id"),
        "capture_label": metric.get("capture_label") or source_row.get("capture_label"),
        "stage": metric.get("stage") or source_row.get("stage"),
        "description": metric.get("description") or source_row.get("description"),
        "scenario_id": metric.get("scenario_id") or source_row.get("scenario_id"),
        "source_square": metric.get("source_square") or source_row.get("source_square"),
        "target_square": target_square,
        "piece_square": piece_square,
        "status": "ok" if pnp_pose.get("status") == "ok" and metadata_projection.get("status") == "ok" else "partial",
        "ok": pnp_pose.get("status") == "ok" and metadata_projection.get("status") == "ok",
        "reason_labels": reason_label_rows,
        "board_size_m": SIM_BOARD_SIZE_M,
        "corner_order_assumption": list(DEFAULT_BOARD_CORNER_ORDER),
        "metadata_declared_corner_order": declared_order,
        "coordinate_frame_convention": metadata.get("coordinate_frame_convention"),
        "source_comparability": comparability,
        "metadata_projection_check": metadata_projection,
        "corner_order_diagnostic": order_summary,
        "ground_truth_source": "camera_metadata.extrinsics.board_to_camera",
        "ground_truth_frame": flat.get("ground_truth_frame"),
        "ground_truth_camera_center_board_mm": vector_m_to_mm(ground_truth_center),
        "ground_truth_camera_to_piece_distance_mm": flat.get("camera_to_piece_distance_mm"),
        "ground_truth_camera_to_board_plane_distance_mm": flat.get("camera_to_board_plane_distance_mm"),
        "ground_truth_camera_to_target_square_distance_mm": flat.get("camera_to_target_square_distance_mm"),
        "metadata_projected_corner_mean_residual_px": metadata_projection.get("mean_residual_px"),
        "metadata_projected_corner_max_residual_px": metadata_projection.get("max_residual_px"),
        "metadata_projected_corner_residuals_px": metadata_projection.get("residuals_px"),
        "metadata_projected_corners_xy": metadata_projection.get("projected_corners_xy"),
        "rendered_corners_xy": metadata_projection.get("rendered_corners_xy"),
        "rendered_corner_pnp_estimator": PERCEIVED_DEPTH_ESTIMATOR_NAME,
        "rendered_corner_pnp_status": pnp_pose.get("status"),
        "rendered_corner_pnp_solve_flag": pnp_pose.get("solve_pnp_flag"),
        "rendered_corner_pnp_candidate_count": pnp_pose.get("solve_pnp_candidate_count"),
        "rendered_corner_pnp_candidate_flags": pnp_pose.get("solve_pnp_candidate_flags"),
        "rendered_corner_pnp_candidate_mean_residuals_px": pnp_pose.get(
            "solve_pnp_candidate_mean_residuals_px"
        ),
        "rendered_corner_pnp_camera_center_board_mm": vector_m_to_mm(pnp_camera_center),
        "rendered_corner_pnp_camera_center_delta_norm_mm": camera_center_delta_norm_mm,
        "rendered_corner_pnp_camera_to_piece_distance_mm": meters_to_mm(pnp_pose.get("camera_to_piece_m")),
        "rendered_corner_pnp_camera_to_board_plane_distance_mm": meters_to_mm(
            pnp_pose.get("camera_to_board_plane_m")
        ),
        "rendered_corner_pnp_camera_to_target_square_distance_mm": meters_to_mm(
            pnp_pose.get("camera_to_target_square_m")
        ),
        "rendered_corner_pnp_camera_to_piece_error_mm": piece_error,
        "rendered_corner_pnp_camera_to_piece_abs_error_mm": abs_or_none(piece_error),
        "rendered_corner_pnp_camera_to_board_error_mm": board_error,
        "rendered_corner_pnp_camera_to_board_abs_error_mm": abs_or_none(board_error),
        "rendered_corner_pnp_camera_to_target_square_error_mm": target_error,
        "rendered_corner_pnp_camera_to_target_square_abs_error_mm": abs_or_none(target_error),
        "rendered_corner_pnp_reprojection_mean_residual_px": rounded_float(
            pnp_pose.get("board_corner_reprojection_mean_residual_px"),
            digits=3,
        ),
        "rendered_corner_pnp_reprojection_max_residual_px": rounded_float(
            pnp_pose.get("board_corner_reprojection_max_residual_px"),
            digits=3,
        ),
        "rendered_corner_pnp_reprojection_residuals_px": [
            rounded_float(value, digits=3)
            for value in np.asarray(
                pnp_pose.get("board_corner_reprojection_residuals_px", []),
                dtype=float,
            ).reshape(-1)
        ]
        if pnp_pose.get("board_corner_reprojection_residuals_px") is not None
        else None,
        "rendered_corner_pnp_projected_corners_xy": rounded_list(
            np.asarray(pnp_pose.get("estimated_projected_corners_xy"), dtype=float).reshape(-1),
            digits=3,
        )
        if pnp_pose.get("estimated_projected_corners_xy") is not None
        else None,
        "diagnosis": (
            "The rendered board-corner PnP residuals are trustworthy only as evidence that "
            "the rendered overlay geometry and metadata extrinsics are not the same pinhole "
            "camera source. Use metadata-projected-corner residuals and source_comparability "
            "before treating this as a depth estimator."
        ),
    }


def aggregate_pnp_diagnostic_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "row_count": len(rows),
        "ok_row_count": sum(1 for row in rows if row.get("ok") is True),
    }
    numeric_fields = {
        "mean_metadata_projected_corner_residual_px": "metadata_projected_corner_mean_residual_px",
        "max_metadata_projected_corner_residual_px": "metadata_projected_corner_max_residual_px",
        "mean_rendered_corner_pnp_reprojection_residual_px": "rendered_corner_pnp_reprojection_mean_residual_px",
        "mean_abs_rendered_corner_pnp_camera_to_piece_error_mm": "rendered_corner_pnp_camera_to_piece_abs_error_mm",
        "mean_abs_rendered_corner_pnp_camera_to_board_error_mm": "rendered_corner_pnp_camera_to_board_abs_error_mm",
        "mean_abs_rendered_corner_pnp_camera_to_target_square_error_mm": "rendered_corner_pnp_camera_to_target_square_abs_error_mm",
        "mean_rendered_corner_pnp_camera_center_delta_norm_mm": "rendered_corner_pnp_camera_center_delta_norm_mm",
    }
    for output_key, row_key in numeric_fields.items():
        values = [float(row[row_key]) for row in rows if row.get(row_key) is not None]
        aggregate[output_key] = round(float(np.mean(values)), 3) if values else None

    not_comparable = 0
    label_counts: dict[str, int] = {}
    for row in rows:
        comparability = row.get("source_comparability")
        comparability = comparability if isinstance(comparability, dict) else {}
        pnp_vs_gt = comparability.get("rendered_board_corner_pnp_vs_sim_ground_truth")
        pnp_vs_gt = pnp_vs_gt if isinstance(pnp_vs_gt, dict) else {}
        if pnp_vs_gt.get("status") == "not_geometrically_comparable":
            not_comparable += 1
        labels = row.get("reason_labels")
        for label in labels if isinstance(labels, list) else []:
            label_counts[str(label)] = label_counts.get(str(label), 0) + 1
    aggregate["not_geometrically_comparable_row_count"] = not_comparable
    aggregate["reason_label_counts"] = dict(sorted(label_counts.items()))
    return aggregate


def write_pnp_residual_diagnostic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "stage",
        "capture_label",
        "scenario_id",
        "source_square",
        "target_square",
        "piece_square",
        "status",
        "board_size_m",
        "metadata_declared_corner_order",
        "corner_order_assumption",
        "metadata_projected_corner_mean_residual_px",
        "metadata_projected_corner_max_residual_px",
        "rendered_corner_pnp_reprojection_mean_residual_px",
        "rendered_corner_pnp_solve_flag",
        "rendered_corner_pnp_candidate_flags",
        "rendered_corner_pnp_candidate_mean_residuals_px",
        "rendered_corner_pnp_camera_center_delta_norm_mm",
        "rendered_corner_pnp_camera_to_piece_distance_mm",
        "ground_truth_camera_to_piece_distance_mm",
        "rendered_corner_pnp_camera_to_piece_error_mm",
        "rendered_corner_pnp_camera_to_board_plane_distance_mm",
        "ground_truth_camera_to_board_plane_distance_mm",
        "rendered_corner_pnp_camera_to_board_error_mm",
        "rendered_corner_pnp_camera_to_target_square_distance_mm",
        "ground_truth_camera_to_target_square_distance_mm",
        "rendered_corner_pnp_camera_to_target_square_error_mm",
        "reason_labels",
        "source_comparability",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def write_pnp_residual_diagnostics(
    *,
    metric_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
    distance_metrics: dict[str, Any],
    perceived_depth_comparison: dict[str, Any],
) -> dict[str, Any]:
    source_by_id = {
        str(row.get("id")): row
        for row in source_rows
        if isinstance(row, dict) and row.get("id") is not None
    }
    rows = [
        compute_pnp_residual_diagnostic_row(metric, source_by_id.get(str(metric.get("id")), {}))
        for metric in metric_rows
        if isinstance(metric, dict)
    ]
    json_path = output_dir / "pick_place_pnp_residual_diagnostics.json"
    csv_path = output_dir / "pick_place_pnp_residual_diagnostics.csv"
    aggregate = aggregate_pnp_diagnostic_rows(rows)
    ok = bool(rows) and all(row.get("ok") is True for row in rows)
    summary = {
        "schema": PNP_RESIDUAL_DIAGNOSTIC_SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "scenario_id": sequence_metadata.get("scenario_id"),
        "source_square": sequence_metadata.get("source_square"),
        "target_square": sequence_metadata.get("target_square"),
        "frame_count": len(rows),
        "paths": {
            "json": str(json_path),
            "csv": str(csv_path),
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
        },
        "source_depth_distance_metrics": distance_metrics.get("paths"),
        "source_perceived_depth_comparison": perceived_depth_comparison.get("paths"),
        "assumptions": {
            "board_size_m": SIM_BOARD_SIZE_M,
            "default_corner_order": list(DEFAULT_BOARD_CORNER_ORDER),
            "metadata_corner_order_source": "camera_metadata.coordinate_frame_convention.board_corners_xy_order",
            "metadata_projection_comparability_threshold_px": METADATA_PROJECTION_COMPARABILITY_THRESHOLD_PX,
        },
        "sources": {
            "simulator_ground_truth_extrinsics": "camera_metadata.extrinsics.board_to_camera",
            "rendered_board_corner_pnp": PERCEIVED_DEPTH_ESTIMATOR_SOURCE,
            "internal_consistency_check": (
                "Project 3D board corners through SimCamera metadata intrinsics/extrinsics and "
                "compare them to camera_metadata.board_corners_xy."
            ),
        },
        "units": {
            "distance": "millimeters",
            "image_residual": "pixels",
        },
        "aggregate": aggregate,
        "rows": rows,
        "review_note": (
            "Large rendered-board-corner PnP depth residuals should be interpreted through "
            "source_comparability. A low PnP reprojection residual only proves the PnP pose fits "
            "the rendered corner overlay, not that the overlay was generated by the metadata "
            "extrinsics as a true pinhole camera."
        ),
    }
    write_json(json_path, summary)
    write_pnp_residual_diagnostic_csv(csv_path, rows)
    return summary


def image_size_from_metadata(metadata: dict[str, Any]) -> tuple[int, int]:
    image_size = metadata.get("image_size_px")
    image_size = image_size if isinstance(image_size, dict) else {}
    try:
        width = int(image_size.get("width") or 640)
        height = int(image_size.get("height") or 480)
    except (TypeError, ValueError):
        return 640, 480
    return max(1, width), max(1, height)


def board_plane_distance_m(metadata: dict[str, Any]) -> float | None:
    camera_center = camera_center_board_m(metadata)
    if camera_center is None:
        return None
    return rounded_float(abs(float(camera_center[2])))


def metadata_native_depth_row(
    *,
    source_row: dict[str, Any],
    metadata: dict[str, Any],
    point_role: str,
    point_label: str,
    board_point_m: np.ndarray,
    square: str | None,
    source_depth_metric_id: str | None,
    source_pnp_diagnostic_id: str | None,
    stage: str | None = None,
    capture_label: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    projection = project_board_point_m(metadata, board_point_m)
    camera_point = projection[0] if projection is not None else None
    image_xy = projection[1] if projection is not None else None
    board_to_camera = metadata.get("extrinsics")
    board_to_camera = board_to_camera if isinstance(board_to_camera, dict) else {}
    board_to_camera = board_to_camera.get("board_to_camera")
    board_to_camera = board_to_camera if isinstance(board_to_camera, dict) else {}
    status = "ok" if camera_point is not None and image_xy is not None else "projection_unavailable"
    row_id = source_depth_metric_id or source_row.get("id") or point_label
    if stage == "reference_board_geometry":
        row_id = f"reference_{point_label}"
    return {
        "id": row_id,
        "capture_label": capture_label if capture_label is not None else source_row.get("capture_label"),
        "stage": stage if stage is not None else source_row.get("stage"),
        "description": description if description is not None else source_row.get("description"),
        "scenario_id": source_row.get("scenario_id"),
        "source_square": source_row.get("source_square"),
        "target_square": source_row.get("target_square"),
        "piece_square": source_row.get("piece_square"),
        "point_role": point_role,
        "point_label": point_label,
        "square": square,
        "status": status,
        "ok": status == "ok",
        "source_model": "simcamera_metadata",
        "source_projection_model": "camera_metadata.camera_matrix_px + camera_metadata.extrinsics.board_to_camera",
        "camera_model": "opencv_pinhole",
        "uses_rendered_overlay_corners": False,
        "simulator_ground_truth": True,
        "not_perceived_real_camera_depth": True,
        "board_frame": board_to_camera.get("from_frame"),
        "camera_frame": board_to_camera.get("to_frame"),
        "board_to_camera_source": board_to_camera.get("source"),
        "metadata_projected_pixel_xy": rounded_list(image_xy, digits=3),
        "camera_frame_xyz_mm": vector_m_to_mm(camera_point),
        "camera_z_depth_mm": meters_to_mm(float(camera_point[2])) if camera_point is not None else None,
        "camera_range_mm": (
            meters_to_mm(float(np.linalg.norm(camera_point))) if camera_point is not None else None
        ),
        "board_plane_distance_mm": meters_to_mm(board_plane_distance_m(metadata)),
        "board_frame_xyz_mm": vector_m_to_mm(board_point_m),
        "source_depth_metric_id": source_depth_metric_id,
        "source_pnp_diagnostic_id": source_pnp_diagnostic_id,
        "depth_semantics": (
            "camera_z_depth_mm is OpenCV camera-frame z from SimCamera metadata; "
            "camera_range_mm is Euclidean range from the camera origin."
        ),
    }


def metadata_native_reference_rows(
    *,
    metadata: dict[str, Any],
    source_row: dict[str, Any],
) -> list[dict[str, Any]]:
    reference_points = [
        ("board_corner", "board_corner_a1", None, np.array([0.0, 0.0, 0.0], dtype=float)),
        ("board_corner", "board_corner_h1", None, np.array([SIM_BOARD_SIZE_M, 0.0, 0.0], dtype=float)),
        (
            "board_corner",
            "board_corner_h8",
            None,
            np.array([SIM_BOARD_SIZE_M, SIM_BOARD_SIZE_M, 0.0], dtype=float),
        ),
        ("board_corner", "board_corner_a8", None, np.array([0.0, SIM_BOARD_SIZE_M, 0.0], dtype=float)),
        (
            "board_center",
            "board_center",
            None,
            np.array([SIM_BOARD_SIZE_M / 2.0, SIM_BOARD_SIZE_M / 2.0, 0.0], dtype=float),
        ),
    ]
    return [
        metadata_native_depth_row(
            source_row=source_row,
            metadata=metadata,
            point_role=role,
            point_label=label,
            board_point_m=point,
            square=square,
            source_depth_metric_id=None,
            source_pnp_diagnostic_id=None,
            stage="reference_board_geometry",
            capture_label="metadata_reference",
            description="Metadata-projected board reference point.",
        )
        for role, label, square, point in reference_points
    ]


def compute_metadata_native_depth_rows(
    *,
    metric_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    pnp_residual_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    source_by_id = {
        str(row.get("id")): row
        for row in source_rows
        if isinstance(row, dict) and row.get("id") is not None
    }
    pnp_rows = pnp_residual_diagnostics.get("rows")
    pnp_by_id = {
        str(row.get("id")): row
        for row in pnp_rows
        if isinstance(row, dict) and row.get("id") is not None
    } if isinstance(pnp_rows, list) else {}
    rows: list[dict[str, Any]] = []
    added_reference = False
    for metric in metric_rows:
        if not isinstance(metric, dict):
            continue
        metric_id = str(metric.get("id") or "")
        source_row = source_by_id.get(metric_id, {})
        capture = source_row.get("capture")
        capture = capture if isinstance(capture, dict) else {}
        metadata = capture.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata_camera_model(metadata) is None:
            continue
        source_row_with_metric = {
            **source_row,
            "source_square": metric.get("source_square") or source_row.get("source_square"),
            "target_square": metric.get("target_square") or source_row.get("target_square"),
            "piece_square": metric.get("piece_square") or source_row.get("source_square"),
        }
        if not added_reference:
            rows.extend(metadata_native_reference_rows(metadata=metadata, source_row=source_row_with_metric))
            added_reference = True
        source_depth_metric_id = metric_id or None
        source_pnp_diagnostic_id = metric_id if metric_id in pnp_by_id else None
        for point_role, point_label, square_value in (
            ("piece_center", "piece_center", source_row_with_metric.get("piece_square")),
            ("target_square_center", "target_square_center", source_row_with_metric.get("target_square")),
        ):
            if not isinstance(square_value, str) or not square_value:
                continue
            try:
                board_point = board_square_center_m(square_value)
            except ValueError:
                continue
            rows.append(
                metadata_native_depth_row(
                    source_row=source_row_with_metric,
                    metadata=metadata,
                    point_role=point_role,
                    point_label=point_label,
                    board_point_m=board_point,
                    square=square_value,
                    source_depth_metric_id=source_depth_metric_id,
                    source_pnp_diagnostic_id=source_pnp_diagnostic_id,
                )
            )
    return rows


def canvas_point(row: dict[str, Any], *, y_offset: int) -> tuple[int, int] | None:
    xy = row.get("metadata_projected_pixel_xy")
    if not isinstance(xy, list) or len(xy) < 2:
        return None
    try:
        return int(round(float(xy[0]))), int(round(float(xy[1]))) + y_offset
    except (TypeError, ValueError):
        return None


def draw_projected_grid(image: np.ndarray, *, metadata: dict[str, Any], y_offset: int) -> None:
    def projected_xy(point: np.ndarray) -> tuple[int, int] | None:
        projection = project_board_point_m(metadata, point)
        if projection is None:
            return None
        _, xy = projection
        return int(round(float(xy[0]))), int(round(float(xy[1]))) + y_offset

    square = SIM_BOARD_SIZE_M / 8.0
    for index in range(9):
        x = square * index
        y = square * index
        vertical = [
            projected_xy(np.array([x, 0.0, 0.0], dtype=float)),
            projected_xy(np.array([x, SIM_BOARD_SIZE_M, 0.0], dtype=float)),
        ]
        horizontal = [
            projected_xy(np.array([0.0, y, 0.0], dtype=float)),
            projected_xy(np.array([SIM_BOARD_SIZE_M, y, 0.0], dtype=float)),
        ]
        if vertical[0] is not None and vertical[1] is not None:
            cv2.line(image, vertical[0], vertical[1], (78, 90, 102), 1, cv2.LINE_AA)
        if horizontal[0] is not None and horizontal[1] is not None:
            cv2.line(image, horizontal[0], horizontal[1], (78, 90, 102), 1, cv2.LINE_AA)

    corners = [
        projected_xy(np.array([0.0, 0.0, 0.0], dtype=float)),
        projected_xy(np.array([SIM_BOARD_SIZE_M, 0.0, 0.0], dtype=float)),
        projected_xy(np.array([SIM_BOARD_SIZE_M, SIM_BOARD_SIZE_M, 0.0], dtype=float)),
        projected_xy(np.array([0.0, SIM_BOARD_SIZE_M, 0.0], dtype=float)),
    ]
    if all(point is not None for point in corners):
        cv2.polylines(
            image,
            [np.asarray(corners, dtype=np.int32).reshape(-1, 1, 2)],
            isClosed=True,
            color=(95, 220, 150),
            thickness=2,
            lineType=cv2.LINE_AA,
        )


def render_metadata_native_depth_view_png(
    *,
    path: Path,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    suite_output_dir: Path,
) -> dict[str, Any]:
    image_width, image_height = image_size_from_metadata(metadata)
    header_height = 92
    panel_width = 360
    width = image_width + panel_width
    height = image_height + header_height
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:, :] = (24, 27, 31)
    cv2.rectangle(
        canvas,
        (0, header_height),
        (image_width - 1, header_height + image_height - 1),
        (18, 20, 24),
        thickness=-1,
    )
    cv2.rectangle(
        canvas,
        (0, header_height),
        (image_width - 1, header_height + image_height - 1),
        (96, 110, 122),
        thickness=1,
    )
    cv2.putText(
        canvas,
        "Metadata-Native SimCamera Projection / Depth View",
        (14, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "Generated from camera_matrix_px and board_to_camera extrinsics; rendered overlay corners are not used.",
        (14, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (190, 214, 244),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "Simulator ground truth / camera-model-aligned. Not perceived real-camera depth.",
        (14, 78),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (188, 232, 188),
        1,
        cv2.LINE_AA,
    )

    draw_projected_grid(canvas, metadata=metadata, y_offset=header_height)
    reference_rows = [row for row in rows if row.get("stage") == "reference_board_geometry"]
    stage_rows = [row for row in rows if row.get("stage") != "reference_board_geometry"]
    for row in reference_rows:
        point = canvas_point(row, y_offset=header_height)
        if point is None:
            continue
        color = (115, 220, 160) if row.get("point_role") == "board_corner" else (150, 185, 255)
        cv2.circle(canvas, point, 4, color, thickness=-1, lineType=cv2.LINE_AA)
        cv2.putText(
            canvas,
            str(row.get("point_label") or ""),
            (point[0] + 6, point[1] - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            color,
            1,
            cv2.LINE_AA,
        )

    stage_colors = {
        "piece_center": (255, 170, 95),
        "target_square_center": (85, 215, 255),
    }
    stage_index_by_id = {
        str(row.get("id")): index
        for index, row in enumerate(
            [row for row in stage_rows if row.get("point_role") == "piece_center"],
            start=1,
        )
    }
    for row in stage_rows:
        point = canvas_point(row, y_offset=header_height)
        if point is None:
            continue
        role = str(row.get("point_role") or "")
        color = stage_colors.get(role, (230, 230, 230))
        if role == "target_square_center":
            cv2.drawMarker(canvas, point, color, markerType=cv2.MARKER_DIAMOND, markerSize=16, thickness=2)
        else:
            cv2.circle(canvas, point, 7, color, thickness=2, lineType=cv2.LINE_AA)
            label = str(stage_index_by_id.get(str(row.get("id")), ""))
            cv2.putText(
                canvas,
                label,
                (point[0] + 8, point[1] + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                color,
                1,
                cv2.LINE_AA,
            )

    panel_x = image_width + 18
    panel_lines = [
        "Source model: simcamera_metadata",
        f"Rows: {len(rows)}",
        "Board grid: metadata projected",
        "Piece: orange circles by stage",
        "Target: cyan diamonds",
    ]
    first_stage = next((row for row in stage_rows if row.get("point_role") == "piece_center"), None)
    if first_stage:
        panel_lines.extend(
            [
                "",
                f"Example: {first_stage.get('stage')}",
                f"pixel xy: {first_stage.get('metadata_projected_pixel_xy')}",
                f"camera xyz mm: {first_stage.get('camera_frame_xyz_mm')}",
                f"z depth mm: {first_stage.get('camera_z_depth_mm')}",
                f"range mm: {first_stage.get('camera_range_mm')}",
                f"board plane mm: {first_stage.get('board_plane_distance_mm')}",
            ]
        )
    y = header_height + 28
    for line in panel_lines:
        cv2.putText(
            canvas,
            short_text(line, 48),
            (panel_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (230, 235, 238) if line else (230, 235, 238),
            1,
            cv2.LINE_AA,
        )
        y += 22 if line else 14

    write_image(path, canvas)
    return {
        "path": str(path),
        "relative_path": output_relative(path, suite_output_dir),
        "output_dimensions": {
            "width_px": int(canvas.shape[1]),
            "height_px": int(canvas.shape[0]),
            "channels": int(canvas.shape[2]),
        },
    }


def write_metadata_native_depth_view_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "stage",
        "capture_label",
        "scenario_id",
        "source_square",
        "target_square",
        "piece_square",
        "point_role",
        "point_label",
        "square",
        "status",
        "source_model",
        "metadata_projected_pixel_xy",
        "camera_frame_xyz_mm",
        "camera_z_depth_mm",
        "camera_range_mm",
        "board_plane_distance_mm",
        "board_frame_xyz_mm",
        "source_depth_metric_id",
        "source_pnp_diagnostic_id",
        "uses_rendered_overlay_corners",
        "not_perceived_real_camera_depth",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def write_metadata_native_depth_view(
    *,
    metric_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
    distance_metrics: dict[str, Any],
    pnp_residual_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    rows = compute_metadata_native_depth_rows(
        metric_rows=metric_rows,
        source_rows=source_rows,
        pnp_residual_diagnostics=pnp_residual_diagnostics,
    )
    json_path = output_dir / "pick_place_metadata_native_depth_view.json"
    csv_path = output_dir / "pick_place_metadata_native_depth_view.csv"
    png_path = output_dir / "pick_place_metadata_native_depth_view.png"
    first_metadata: dict[str, Any] | None = None
    for source_row in source_rows:
        capture = source_row.get("capture")
        capture = capture if isinstance(capture, dict) else {}
        metadata = capture.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata_camera_model(metadata) is not None:
            first_metadata = metadata
            break
    if first_metadata is None:
        first_metadata = {}
    visual = render_metadata_native_depth_view_png(
        path=png_path,
        rows=rows,
        metadata=first_metadata,
        suite_output_dir=suite_output_dir,
    )
    write_metadata_native_depth_view_csv(csv_path, rows)
    ok = bool(rows) and all(row.get("ok") is True for row in rows)
    first_stage_row = next(
        (row for row in rows if row.get("stage") != "reference_board_geometry"),
        rows[0] if rows else {},
    )
    summary = {
        "schema": METADATA_NATIVE_DEPTH_VIEW_SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "scenario_id": sequence_metadata.get("scenario_id"),
        "source_square": sequence_metadata.get("source_square"),
        "target_square": sequence_metadata.get("target_square"),
        "frame_count": len(metric_rows),
        "row_count": len(rows),
        "point_roles": sorted({str(row.get("point_role")) for row in rows if row.get("point_role")}),
        "paths": {
            "png": str(png_path),
            "json": str(json_path),
            "csv": str(csv_path),
            "png_relative_path": output_relative(png_path, suite_output_dir),
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
        },
        "visual": visual,
        "source_artifacts": {
            "depth_distance_metrics": distance_metrics.get("paths"),
            "pnp_residual_diagnostics": pnp_residual_diagnostics.get("paths"),
        },
        "source_model": "simcamera_metadata",
        "source_projection_model": "camera_metadata.camera_matrix_px + camera_metadata.extrinsics.board_to_camera",
        "uses_rendered_overlay_corners": False,
        "ground_truth_scope": (
            "Simulator ground truth projected directly from SimCamera metadata. "
            "This is camera-model-aligned and does not treat rendered board-corner overlays as depth authority."
        ),
        "units": {
            "metadata_projected_pixel_xy": "pixels",
            "camera_frame_xyz_mm": "millimeters",
            "camera_z_depth_mm": "millimeters",
            "camera_range_mm": "millimeters",
            "board_plane_distance_mm": "millimeters",
        },
        "example_row": first_stage_row,
        "rows": rows,
        "review_note": (
            "Use this artifact when reviewing simulator ground-truth pinhole projections and depth/range "
            "expected by SimCamera metadata. Use the rendered-overlay PnP diagnostic only to explain "
            "why rendered overlay corners disagree with that metadata, not as depth authority."
        ),
    }
    write_json(json_path, summary)
    return summary


def compute_perceived_depth_comparison_row(
    metric: dict[str, Any],
    source_row: dict[str, Any],
) -> dict[str, Any]:
    capture = source_row.get("capture")
    capture = capture if isinstance(capture, dict) else {}
    metadata = capture.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    flat = metric.get("distance_depth_fields")
    flat = flat if isinstance(flat, dict) else {}
    piece_square = str(metric.get("piece_square") or source_row.get("source_square") or "")
    target_square = str(metric.get("target_square") or source_row.get("target_square") or piece_square)
    estimate = estimate_depth_from_rendered_board_geometry(
        metadata,
        piece_square=piece_square,
        target_square=target_square,
    )

    row: dict[str, Any] = {
        "id": metric.get("id") or source_row.get("id"),
        "capture_label": metric.get("capture_label") or source_row.get("capture_label"),
        "stage": metric.get("stage") or source_row.get("stage"),
        "description": metric.get("description") or source_row.get("description"),
        "scenario_id": metric.get("scenario_id") or source_row.get("scenario_id"),
        "source_square": metric.get("source_square") or source_row.get("source_square"),
        "target_square": target_square,
        "piece_square": piece_square,
        "estimator": PERCEIVED_DEPTH_ESTIMATOR_NAME,
        "estimator_source": PERCEIVED_DEPTH_ESTIMATOR_SOURCE,
        "perceived_depth_status": PERCEIVED_DEPTH_ESTIMATOR_STATUS,
        "uses_sim_metadata": True,
        "uses_real_camera_pixels": False,
        "uses_depth_sensor": False,
        "status": estimate.get("status"),
        "ok": estimate.get("status") == "ok",
        "ground_truth_camera_to_piece_distance_mm": flat.get("camera_to_piece_distance_mm"),
        "ground_truth_camera_to_board_plane_distance_mm": flat.get("camera_to_board_plane_distance_mm"),
        "ground_truth_camera_to_target_square_distance_mm": flat.get("camera_to_target_square_distance_mm"),
        "ground_truth_source_metric_id": metric.get("id"),
        "ground_truth_source": "pick_place_depth_distance_metrics.distance_depth_fields",
        "ground_truth_frame": flat.get("ground_truth_frame"),
        "source_depth_metric_status": flat.get("metric_status"),
        "limitations": (
            "This is a metadata-derived planar-PnP baseline from rendered board corners and "
            "SimCamera intrinsics, not an independent real-camera depth or segmentation estimate."
        ),
        "future_real_camera_perception_gap": (
            "Replace or compare this baseline with real reference media, calibrated camera "
            "intrinsics/extrinsics, and an image/depth estimator when physical captures are available."
        ),
    }
    if estimate.get("status") != "ok":
        row.update(
            {
                "estimated_camera_to_piece_distance_mm": None,
                "estimated_camera_to_board_plane_distance_mm": None,
                "estimated_camera_to_target_square_distance_mm": None,
                "camera_to_piece_error_mm": None,
                "camera_to_piece_abs_error_mm": None,
                "camera_to_board_error_mm": None,
                "camera_to_board_abs_error_mm": None,
                "camera_to_target_square_error_mm": None,
                "camera_to_target_square_abs_error_mm": None,
                "reason": estimate.get("reason"),
            }
        )
        return row

    row.update(estimate)
    piece_error = subtract_or_none(
        row.get("estimated_camera_to_piece_distance_mm"),
        row.get("ground_truth_camera_to_piece_distance_mm"),
    )
    board_error = subtract_or_none(
        row.get("estimated_camera_to_board_plane_distance_mm"),
        row.get("ground_truth_camera_to_board_plane_distance_mm"),
    )
    target_error = subtract_or_none(
        row.get("estimated_camera_to_target_square_distance_mm"),
        row.get("ground_truth_camera_to_target_square_distance_mm"),
    )
    row.update(
        {
            "camera_to_piece_error_mm": piece_error,
            "camera_to_piece_abs_error_mm": abs_or_none(piece_error),
            "camera_to_board_error_mm": board_error,
            "camera_to_board_abs_error_mm": abs_or_none(board_error),
            "camera_to_target_square_error_mm": target_error,
            "camera_to_target_square_abs_error_mm": abs_or_none(target_error),
        }
    )
    return row


def aggregate_comparison_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "row_count": len(rows),
        "ok_row_count": sum(1 for row in rows if row.get("ok") is True),
    }
    for prefix, key in (
        ("camera_to_piece", "camera_to_piece_abs_error_mm"),
        ("camera_to_board", "camera_to_board_abs_error_mm"),
        ("camera_to_target_square", "camera_to_target_square_abs_error_mm"),
    ):
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if values:
            aggregate[f"mean_abs_{prefix}_error_mm"] = round(float(np.mean(values)), 3)
            aggregate[f"max_abs_{prefix}_error_mm"] = round(float(np.max(values)), 3)
        else:
            aggregate[f"mean_abs_{prefix}_error_mm"] = None
            aggregate[f"max_abs_{prefix}_error_mm"] = None
    residuals = [
        float(row["board_corner_reprojection_mean_residual_px"])
        for row in rows
        if row.get("board_corner_reprojection_mean_residual_px") is not None
    ]
    aggregate["mean_board_corner_reprojection_residual_px"] = (
        round(float(np.mean(residuals)), 3) if residuals else None
    )
    aggregate["max_board_corner_reprojection_residual_px"] = (
        round(float(np.max(residuals)), 3) if residuals else None
    )
    return aggregate


def write_perceived_depth_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "stage",
        "capture_label",
        "scenario_id",
        "source_square",
        "target_square",
        "piece_square",
        "estimator",
        "estimator_source",
        "perceived_depth_status",
        "status",
        "estimated_camera_to_piece_distance_mm",
        "ground_truth_camera_to_piece_distance_mm",
        "camera_to_piece_error_mm",
        "camera_to_piece_abs_error_mm",
        "estimated_camera_to_board_plane_distance_mm",
        "ground_truth_camera_to_board_plane_distance_mm",
        "camera_to_board_error_mm",
        "camera_to_board_abs_error_mm",
        "estimated_camera_to_target_square_distance_mm",
        "ground_truth_camera_to_target_square_distance_mm",
        "camera_to_target_square_error_mm",
        "camera_to_target_square_abs_error_mm",
        "board_corner_reprojection_mean_residual_px",
        "board_corner_reprojection_max_residual_px",
        "uses_sim_metadata",
        "uses_real_camera_pixels",
        "uses_depth_sensor",
        "ground_truth_source_metric_id",
        "limitations",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def write_perceived_depth_comparison(
    *,
    metric_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
    distance_metrics: dict[str, Any],
) -> dict[str, Any]:
    source_by_id = {
        str(row.get("id")): row
        for row in source_rows
        if isinstance(row, dict) and row.get("id") is not None
    }
    rows = [
        compute_perceived_depth_comparison_row(metric, source_by_id.get(str(metric.get("id")), {}))
        for metric in metric_rows
        if isinstance(metric, dict)
    ]
    json_path = output_dir / "pick_place_perceived_depth_comparison.json"
    csv_path = output_dir / "pick_place_perceived_depth_comparison.csv"
    aggregate = aggregate_comparison_rows(rows)
    ok = bool(rows) and all(row.get("ok") is True for row in rows)
    summary = {
        "schema": PERCEIVED_DEPTH_COMPARISON_SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "scenario_id": sequence_metadata.get("scenario_id"),
        "source_square": sequence_metadata.get("source_square"),
        "target_square": sequence_metadata.get("target_square"),
        "frame_count": len(rows),
        "paths": {
            "json": str(json_path),
            "csv": str(csv_path),
            "json_relative_path": output_relative(json_path, suite_output_dir),
            "csv_relative_path": output_relative(csv_path, suite_output_dir),
        },
        "source_depth_distance_metrics": distance_metrics.get("paths"),
        "ground_truth_source": "pick_place_depth_distance_metrics",
        "estimator": {
            "name": PERCEIVED_DEPTH_ESTIMATOR_NAME,
            "status": PERCEIVED_DEPTH_ESTIMATOR_STATUS,
            "source": PERCEIVED_DEPTH_ESTIMATOR_SOURCE,
            "uses_sim_metadata": True,
            "uses_real_camera_pixels": False,
            "uses_depth_sensor": False,
            "inputs": [
                "camera_metadata.camera_matrix_px",
                "camera_metadata.board_corners_xy",
                f"known_sim_board_size_m={SIM_BOARD_SIZE_M}",
                "metric row source/target square centers",
            ],
            "honesty_note": (
                "The baseline estimates camera pose from rendered board-corner geometry and "
                "known intrinsics. It is useful for artifact plumbing and residual accounting, "
                "but it is not independent real-camera perception."
            ),
        },
        "units": {
            "distance": "millimeters",
            "image_residual": "pixels",
        },
        "aggregate": aggregate,
        "rows": rows,
    }
    write_json(json_path, summary)
    write_perceived_depth_comparison_csv(csv_path, rows)
    return summary


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def numeric_stats(values: list[Any], *, digits: int = 3) -> dict[str, Any]:
    finite = [value for value in (finite_float(value) for value in values) if value is not None]
    if not finite:
        return {"count": 0, "mean": None, "min": None, "max": None}
    return {
        "count": len(finite),
        "mean": round(float(np.mean(finite)), digits),
        "min": round(float(np.min(finite)), digits),
        "max": round(float(np.max(finite)), digits),
    }


def scorecard_flat_metric_values(rows: list[dict[str, Any]], key: str) -> list[Any]:
    values: list[Any] = []
    for row in rows:
        flat = row.get("distance_depth_fields")
        flat = flat if isinstance(flat, dict) else {}
        values.append(flat.get(key))
    return values


def quality_label(value: Any, *, good_at_most: float, warning_at_most: float) -> str:
    number = finite_float(value)
    if number is None:
        return "unknown"
    if number <= good_at_most:
        return "good"
    if number <= warning_at_most:
        return "warning"
    return "bad"


def scorecard_quality_status(label: str, *, metric: str) -> str:
    if label == "unknown":
        return f"{metric}_unknown"
    return f"{metric}_{label}_vs_sim"


def first_row_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id") is not None
    }


def pnp_vs_ground_truth_status(row: dict[str, Any]) -> str | None:
    comparability = row.get("source_comparability")
    comparability = comparability if isinstance(comparability, dict) else {}
    pnp_vs_gt = comparability.get("rendered_board_corner_pnp_vs_sim_ground_truth")
    pnp_vs_gt = pnp_vs_gt if isinstance(pnp_vs_gt, dict) else {}
    status = pnp_vs_gt.get("status")
    return str(status) if isinstance(status, str) and status else None


def build_depth_distance_scorecard_payload(
    *,
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
    distance_metrics: dict[str, Any],
    perceived_depth_comparison: dict[str, Any],
    pnp_residual_diagnostics: dict[str, Any],
    metadata_native_depth_view: dict[str, Any],
) -> dict[str, Any]:
    distance_rows = [
        row for row in distance_metrics.get("rows", []) if isinstance(row, dict)
    ] if isinstance(distance_metrics.get("rows"), list) else []
    comparison_rows = [
        row for row in perceived_depth_comparison.get("rows", []) if isinstance(row, dict)
    ] if isinstance(perceived_depth_comparison.get("rows"), list) else []
    pnp_rows = [
        row for row in pnp_residual_diagnostics.get("rows", []) if isinstance(row, dict)
    ] if isinstance(pnp_residual_diagnostics.get("rows"), list) else []
    pnp_by_id = first_row_by_id(pnp_rows)
    distance_by_id = first_row_by_id(distance_rows)

    comparison_aggregate = perceived_depth_comparison.get("aggregate")
    comparison_aggregate = comparison_aggregate if isinstance(comparison_aggregate, dict) else {}
    pnp_aggregate = pnp_residual_diagnostics.get("aggregate")
    pnp_aggregate = pnp_aggregate if isinstance(pnp_aggregate, dict) else {}
    estimator = perceived_depth_comparison.get("estimator")
    estimator = estimator if isinstance(estimator, dict) else {}
    true_depth = distance_metrics.get("true_depth_estimation")
    true_depth = true_depth if isinstance(true_depth, dict) else {}

    depth_error_means = [
        comparison_aggregate.get("mean_abs_camera_to_piece_error_mm"),
        comparison_aggregate.get("mean_abs_camera_to_board_error_mm"),
        comparison_aggregate.get("mean_abs_camera_to_target_square_error_mm"),
    ]
    worst_mean_depth_error_mm = max(
        (value for value in (finite_float(value) for value in depth_error_means) if value is not None),
        default=None,
    )
    baseline_depth_quality = quality_label(
        worst_mean_depth_error_mm,
        good_at_most=25.0,
        warning_at_most=75.0,
    )
    pnp_reprojection_quality = quality_label(
        comparison_aggregate.get("mean_board_corner_reprojection_residual_px"),
        good_at_most=2.0,
        warning_at_most=5.0,
    )
    metadata_corner_quality = quality_label(
        pnp_aggregate.get("mean_metadata_projected_corner_residual_px"),
        good_at_most=2.0,
        warning_at_most=5.0,
    )
    not_comparable_count = int(pnp_aggregate.get("not_geometrically_comparable_row_count") or 0)
    if not_comparable_count:
        baseline_depth_quality = "bad"

    if baseline_depth_quality == "bad" or metadata_corner_quality == "bad":
        at_a_glance = "bad_metadata_baseline_alignment"
    elif baseline_depth_quality == "warning" or metadata_corner_quality == "warning":
        at_a_glance = "warning_metadata_baseline_alignment"
    elif baseline_depth_quality == "good" and metadata_corner_quality == "good":
        at_a_glance = "good_metadata_baseline_alignment"
    else:
        at_a_glance = "unknown_metadata_baseline_alignment"
    review_status = "needs_real_depth_reference"

    pnp_status_counts: dict[str, int] = {}
    for row in pnp_rows:
        status = pnp_vs_ground_truth_status(row) or "unknown"
        pnp_status_counts[status] = pnp_status_counts.get(status, 0) + 1

    stage_rows: list[dict[str, Any]] = []
    for comparison in comparison_rows:
        row_id = str(comparison.get("id"))
        pnp_row = pnp_by_id.get(row_id, {})
        distance_row = distance_by_id.get(row_id, {})
        flat = distance_row.get("distance_depth_fields")
        flat = flat if isinstance(flat, dict) else {}
        stage_rows.append(
            {
                "id": comparison.get("id"),
                "stage": comparison.get("stage"),
                "capture_label": comparison.get("capture_label"),
                "status": comparison.get("status"),
                "sim_ground_truth": {
                    "camera_to_piece_distance_mm": comparison.get(
                        "ground_truth_camera_to_piece_distance_mm"
                    ),
                    "camera_to_board_plane_distance_mm": comparison.get(
                        "ground_truth_camera_to_board_plane_distance_mm"
                    ),
                    "camera_to_target_square_distance_mm": comparison.get(
                        "ground_truth_camera_to_target_square_distance_mm"
                    ),
                    "piece_projected_pixel_xy": flat.get("piece_projected_pixel_xy"),
                    "piece_rendered_pixel_xy": flat.get("piece_rendered_pixel_xy"),
                    "piece_projection_residual_px": flat.get("piece_projection_residual_px"),
                },
                "metadata_derived_baseline": {
                    "estimated_camera_to_piece_distance_mm": comparison.get(
                        "estimated_camera_to_piece_distance_mm"
                    ),
                    "estimated_camera_to_board_plane_distance_mm": comparison.get(
                        "estimated_camera_to_board_plane_distance_mm"
                    ),
                    "estimated_camera_to_target_square_distance_mm": comparison.get(
                        "estimated_camera_to_target_square_distance_mm"
                    ),
                    "camera_to_piece_error_mm": comparison.get("camera_to_piece_error_mm"),
                    "camera_to_piece_abs_error_mm": comparison.get(
                        "camera_to_piece_abs_error_mm"
                    ),
                    "camera_to_board_error_mm": comparison.get("camera_to_board_error_mm"),
                    "camera_to_board_abs_error_mm": comparison.get(
                        "camera_to_board_abs_error_mm"
                    ),
                    "camera_to_target_square_error_mm": comparison.get(
                        "camera_to_target_square_error_mm"
                    ),
                    "camera_to_target_square_abs_error_mm": comparison.get(
                        "camera_to_target_square_abs_error_mm"
                    ),
                    "board_corner_reprojection_mean_residual_px": comparison.get(
                        "board_corner_reprojection_mean_residual_px"
                    ),
                    "board_corner_reprojection_max_residual_px": comparison.get(
                        "board_corner_reprojection_max_residual_px"
                    ),
                    "pnp_vs_sim_ground_truth_status": pnp_vs_ground_truth_status(pnp_row),
                    "reason_labels": pnp_row.get("reason_labels"),
                },
            }
        )

    json_path = output_dir / "pick_place_depth_distance_scorecard.json"
    png_path = output_dir / "pick_place_depth_distance_scorecard.png"
    return {
        "schema": DEPTH_DISTANCE_SCORECARD_SCHEMA,
        "ok": bool(distance_rows and comparison_rows),
        "status": "ok" if distance_rows and comparison_rows else "validation_failed",
        "review_status": review_status,
        "at_a_glance": at_a_glance,
        "scenario_id": sequence_metadata.get("scenario_id"),
        "source_square": sequence_metadata.get("source_square"),
        "target_square": sequence_metadata.get("target_square"),
        "frame_count": len(comparison_rows),
        "paths": {
            "png": str(png_path),
            "json": str(json_path),
            "png_relative_path": output_relative(png_path, suite_output_dir),
            "json_relative_path": output_relative(json_path, suite_output_dir),
        },
        "status_labels": [
            {
                "label": "sim_ground_truth",
                "status": "available" if distance_rows else "missing",
                "source": "pick_place_depth_distance_metrics",
            },
            {
                "label": "metadata_derived_baseline",
                "status": scorecard_quality_status(
                    baseline_depth_quality,
                    metric="metadata_derived_baseline",
                ),
                "source": PERCEIVED_DEPTH_ESTIMATOR_SOURCE,
            },
            {
                "label": "not_real_camera_depth",
                "status": "not_implemented",
                "source": "no real camera pixels or depth sensor are consumed",
            },
            {
                "label": "needs_real_depth_reference",
                "status": "blocked_until_real_capture_sidecars_exist",
                "source": "real SO-101 capture sidecars are required for real-vs-sim residuals",
            },
        ],
        "quality_thresholds": {
            "mean_abs_depth_error_mm": {
                "good_at_most": 25.0,
                "warning_at_most": 75.0,
                "bad_above": 75.0,
            },
            "corner_reprojection_residual_px": {
                "good_at_most": 2.0,
                "warning_at_most": 5.0,
                "bad_above": 5.0,
            },
        },
        "sim_ground_truth": {
            "source": "camera_metadata.extrinsics.board_to_camera + SimCamera intrinsics",
            "status": "sim_ground_truth",
            "camera_to_piece_distance_mm": numeric_stats(
                scorecard_flat_metric_values(distance_rows, "camera_to_piece_distance_mm"),
                digits=1,
            ),
            "camera_to_board_plane_distance_mm": numeric_stats(
                scorecard_flat_metric_values(distance_rows, "camera_to_board_plane_distance_mm"),
                digits=1,
            ),
            "camera_to_target_square_distance_mm": numeric_stats(
                scorecard_flat_metric_values(
                    distance_rows,
                    "camera_to_target_square_distance_mm",
                ),
                digits=1,
            ),
            "piece_projection_residual_px": numeric_stats(
                scorecard_flat_metric_values(distance_rows, "piece_projection_residual_px"),
                digits=3,
            ),
            "target_square_projection_residual_px": numeric_stats(
                scorecard_flat_metric_values(
                    distance_rows,
                    "target_square_projection_residual_px",
                ),
                digits=3,
            ),
        },
        "metadata_derived_baseline": {
            "estimator": estimator.get("name") or PERCEIVED_DEPTH_ESTIMATOR_NAME,
            "status": estimator.get("status") or PERCEIVED_DEPTH_ESTIMATOR_STATUS,
            "quality": baseline_depth_quality,
            "quality_status": scorecard_quality_status(
                baseline_depth_quality,
                metric="metadata_derived_baseline",
            ),
            "worst_mean_abs_depth_error_mm": rounded_float(
                worst_mean_depth_error_mm,
                digits=3,
            ),
            "uses_sim_metadata": estimator.get("uses_sim_metadata"),
            "uses_real_camera_pixels": estimator.get("uses_real_camera_pixels"),
            "uses_depth_sensor": estimator.get("uses_depth_sensor"),
            "mean_abs_camera_to_piece_error_mm": comparison_aggregate.get(
                "mean_abs_camera_to_piece_error_mm"
            ),
            "max_abs_camera_to_piece_error_mm": comparison_aggregate.get(
                "max_abs_camera_to_piece_error_mm"
            ),
            "mean_abs_camera_to_board_error_mm": comparison_aggregate.get(
                "mean_abs_camera_to_board_error_mm"
            ),
            "max_abs_camera_to_board_error_mm": comparison_aggregate.get(
                "max_abs_camera_to_board_error_mm"
            ),
            "mean_abs_camera_to_target_square_error_mm": comparison_aggregate.get(
                "mean_abs_camera_to_target_square_error_mm"
            ),
            "max_abs_camera_to_target_square_error_mm": comparison_aggregate.get(
                "max_abs_camera_to_target_square_error_mm"
            ),
            "mean_board_corner_reprojection_residual_px": comparison_aggregate.get(
                "mean_board_corner_reprojection_residual_px"
            ),
            "max_board_corner_reprojection_residual_px": comparison_aggregate.get(
                "max_board_corner_reprojection_residual_px"
            ),
            "reprojection_quality": pnp_reprojection_quality,
        },
        "pnp_residuals": {
            "quality": metadata_corner_quality,
            "quality_status": scorecard_quality_status(
                metadata_corner_quality,
                metric="metadata_corner_projection",
            ),
            "mean_metadata_projected_corner_residual_px": pnp_aggregate.get(
                "mean_metadata_projected_corner_residual_px"
            ),
            "max_metadata_projected_corner_residual_px": pnp_aggregate.get(
                "max_metadata_projected_corner_residual_px"
            ),
            "mean_rendered_corner_pnp_reprojection_residual_px": pnp_aggregate.get(
                "mean_rendered_corner_pnp_reprojection_residual_px"
            ),
            "mean_rendered_corner_pnp_camera_center_delta_norm_mm": pnp_aggregate.get(
                "mean_rendered_corner_pnp_camera_center_delta_norm_mm"
            ),
            "not_geometrically_comparable_row_count": not_comparable_count,
            "pnp_vs_sim_ground_truth_status_counts": dict(sorted(pnp_status_counts.items())),
            "reason_label_counts": pnp_aggregate.get("reason_label_counts"),
        },
        "metadata_native_depth_view": {
            "status": metadata_native_depth_view.get("status"),
            "source_model": metadata_native_depth_view.get("source_model"),
            "source_projection_model": metadata_native_depth_view.get(
                "source_projection_model"
            ),
            "uses_rendered_overlay_corners": metadata_native_depth_view.get(
                "uses_rendered_overlay_corners"
            ),
            "row_count": metadata_native_depth_view.get("row_count"),
            "point_roles": metadata_native_depth_view.get("point_roles"),
            "paths": metadata_native_depth_view.get("paths"),
        },
        "real_camera_depth_gap": {
            "implemented": False,
            "status": "not_real_camera_depth",
            "needs_real_depth_reference": True,
            "gap": true_depth.get("gap") or (
                "No true real-camera or depth-sensor estimate is implemented in this "
                "hardware-free scorecard."
            ),
            "next_follow_up": (
                "Use actual SO-101 capture sidecars to compare real camera/depth measurements "
                "against this simulator scorecard and produce real-vs-sim residual overlays."
            ),
        },
        "source_artifacts": {
            "pick_place_depth_distance_metrics": distance_metrics.get("paths"),
            "pick_place_perceived_depth_comparison": perceived_depth_comparison.get("paths"),
            "pick_place_pnp_residual_diagnostics": pnp_residual_diagnostics.get("paths"),
            "pick_place_metadata_native_depth_view": metadata_native_depth_view.get("paths"),
        },
        "units": {
            "distance": "millimeters",
            "image_residual": "pixels",
        },
        "stage_rows": stage_rows,
        "review_note": (
            "This scorecard is hardware-free. It is good for simulator evidence and for "
            "spotting rendered-corner PnP baseline errors at a glance, but it explicitly "
            "does not claim real robot/camera depth judgment until real capture sidecars "
            "supply comparable depth or calibrated camera measurements."
        ),
    }


SCORECARD_COLORS: dict[str, tuple[int, int, int]] = {
    "good": (90, 150, 70),
    "warning": (0, 165, 220),
    "bad": (60, 70, 220),
    "blocked": (105, 90, 170),
    "unknown": (120, 120, 120),
    "text": (34, 34, 34),
    "muted": (105, 112, 120),
    "border": (205, 211, 218),
    "panel": (255, 255, 255),
    "background": (245, 247, 250),
    "header": (42, 49, 57),
}


def scorecard_color_for_status(status: Any) -> tuple[int, int, int]:
    value = str(status or "").lower()
    if "good" in value or value == "available":
        return SCORECARD_COLORS["good"]
    if "warning" in value:
        return SCORECARD_COLORS["warning"]
    if "bad" in value or "not_geometrically_comparable" in value:
        return SCORECARD_COLORS["bad"]
    if "not_real_camera_depth" in value or "needs_real_depth_reference" in value or "blocked" in value:
        return SCORECARD_COLORS["blocked"]
    return SCORECARD_COLORS["unknown"]


def scorecard_display_status(status: Any) -> str:
    value = str(status or "")
    display = {
        "metadata_derived_baseline_good_vs_sim": "good vs sim",
        "metadata_derived_baseline_warning_vs_sim": "warning vs sim",
        "metadata_derived_baseline_bad_vs_sim": "bad vs sim",
        "metadata_derived_baseline_unknown": "unknown",
        "metadata_corner_projection_good_vs_sim": "good projection",
        "metadata_corner_projection_warning_vs_sim": "warning projection",
        "metadata_corner_projection_bad_vs_sim": "bad projection",
        "not_geometrically_comparable": "not comparable",
        "not_implemented": "not implemented",
        "blocked_until_real_capture_sidecars_exist": "needs real depth reference",
    }.get(value)
    return display or value.replace("_", " ")


def scorecard_text(
    canvas: np.ndarray,
    text: Any,
    x: int,
    y: int,
    *,
    scale: float = 0.55,
    color: tuple[int, int, int] | None = None,
    thickness: int = 1,
) -> None:
    cv2.putText(
        canvas,
        "" if text is None else str(text),
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        float(scale),
        color or SCORECARD_COLORS["text"],
        int(thickness),
        cv2.LINE_AA,
    )


def scorecard_wrapped_text(
    canvas: np.ndarray,
    text: Any,
    x: int,
    y: int,
    *,
    max_chars: int,
    scale: float = 0.47,
    color: tuple[int, int, int] | None = None,
    line_height: int = 22,
    max_lines: int | None = None,
) -> int:
    lines = textwrap.wrap(str(text or ""), width=max_chars) or [""]
    if max_lines is not None:
        lines = lines[:max_lines]
    for index, line in enumerate(lines):
        scorecard_text(
            canvas,
            line,
            x,
            y + index * line_height,
            scale=scale,
            color=color or SCORECARD_COLORS["text"],
        )
    return y + len(lines) * line_height


def scorecard_badge(
    canvas: np.ndarray,
    label: str,
    status: str,
    x: int,
    y: int,
    *,
    width: int,
) -> None:
    color = scorecard_color_for_status(status)
    cv2.rectangle(canvas, (x, y), (x + width, y + 54), color, -1)
    cv2.rectangle(canvas, (x, y), (x + width, y + 54), (255, 255, 255), 1)
    scorecard_text(canvas, label.upper(), x + 12, y + 20, scale=0.42, color=(255, 255, 255))
    scorecard_wrapped_text(
        canvas,
        scorecard_display_status(status),
        x + 12,
        y + 40,
        max_chars=max(14, width // 12),
        scale=0.38,
        color=(255, 255, 255),
        line_height=17,
        max_lines=1,
    )


def scorecard_format_number(value: Any, suffix: str = "") -> str:
    number = finite_float(value)
    if number is None:
        return "n/a"
    if abs(number) >= 100:
        text = f"{number:.1f}"
    elif abs(number) >= 10:
        text = f"{number:.2f}"
    else:
        text = f"{number:.3f}"
    return f"{text}{suffix}"


def scorecard_metric_card(
    canvas: np.ndarray,
    title: str,
    value: str,
    detail: str,
    x: int,
    y: int,
    *,
    width: int,
    height: int,
    status: str = "unknown",
) -> None:
    cv2.rectangle(canvas, (x, y), (x + width, y + height), SCORECARD_COLORS["panel"], -1)
    cv2.rectangle(canvas, (x, y), (x + width, y + height), SCORECARD_COLORS["border"], 1)
    cv2.rectangle(canvas, (x, y), (x + 8, y + height), scorecard_color_for_status(status), -1)
    scorecard_wrapped_text(
        canvas,
        title,
        x + 20,
        y + 24,
        max_chars=max(12, (width - 30) // 11),
        scale=0.42,
        color=SCORECARD_COLORS["muted"],
        line_height=18,
        max_lines=2,
    )
    scorecard_text(canvas, value, x + 20, y + 72, scale=0.72, thickness=2)
    scorecard_wrapped_text(
        canvas,
        detail,
        x + 20,
        y + height - 30,
        max_chars=max(14, (width - 30) // 9),
        scale=0.38,
        color=SCORECARD_COLORS["muted"],
        line_height=16,
        max_lines=2,
    )


def render_depth_distance_scorecard_png(path: Path, scorecard: dict[str, Any]) -> dict[str, Any]:
    width = 1500
    height = 1100
    canvas = np.full((height, width, 3), SCORECARD_COLORS["background"], dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (width, 106), SCORECARD_COLORS["header"], -1)
    scorecard_text(
        canvas,
        "Pick/Place Depth-Distance Scorecard",
        34,
        44,
        scale=1.0,
        color=(255, 255, 255),
        thickness=2,
    )
    subtitle = (
        f"Scenario {scorecard.get('scenario_id') or 'n/a'} | "
        f"{scorecard.get('source_square') or '?'} -> {scorecard.get('target_square') or '?'} | "
        f"review_status={scorecard.get('review_status')}"
    )
    scorecard_text(canvas, subtitle, 36, 78, scale=0.52, color=(218, 226, 235))

    labels = scorecard.get("status_labels")
    labels = labels if isinstance(labels, list) else []
    badge_width = 340
    for index, label in enumerate(labels[:4]):
        label = label if isinstance(label, dict) else {}
        scorecard_badge(
            canvas,
            str(label.get("label") or "status"),
            str(label.get("status") or "unknown"),
            34 + index * (badge_width + 18),
            126,
            width=badge_width,
        )

    sim = scorecard.get("sim_ground_truth")
    sim = sim if isinstance(sim, dict) else {}
    baseline = scorecard.get("metadata_derived_baseline")
    baseline = baseline if isinstance(baseline, dict) else {}
    pnp = scorecard.get("pnp_residuals")
    pnp = pnp if isinstance(pnp, dict) else {}
    gap = scorecard.get("real_camera_depth_gap")
    gap = gap if isinstance(gap, dict) else {}
    cards = [
        (
            "GT camera-to-piece mean",
            scorecard_format_number(
                sim.get("camera_to_piece_distance_mm", {}).get("mean")
                if isinstance(sim.get("camera_to_piece_distance_mm"), dict)
                else None,
                " mm",
            ),
            "SimCamera metadata ground truth",
            "good",
        ),
        (
            "GT camera-to-board mean",
            scorecard_format_number(
                sim.get("camera_to_board_plane_distance_mm", {}).get("mean")
                if isinstance(sim.get("camera_to_board_plane_distance_mm"), dict)
                else None,
                " mm",
            ),
            "Board plane distance",
            "good",
        ),
        (
            "PnP piece abs error mean",
            scorecard_format_number(baseline.get("mean_abs_camera_to_piece_error_mm"), " mm"),
            "Metadata-derived baseline vs sim",
            str(baseline.get("quality")),
        ),
        (
            "PnP board abs error mean",
            scorecard_format_number(baseline.get("mean_abs_camera_to_board_error_mm"), " mm"),
            "Metadata-derived baseline vs sim",
            str(baseline.get("quality")),
        ),
        (
            "PnP reprojection mean",
            scorecard_format_number(baseline.get("mean_board_corner_reprojection_residual_px"), " px"),
            "Rendered-corner PnP fit",
            str(baseline.get("reprojection_quality")),
        ),
        (
            "Metadata corner residual mean",
            scorecard_format_number(pnp.get("mean_metadata_projected_corner_residual_px"), " px"),
            "SimCamera projection vs rendered corners",
            str(pnp.get("quality")),
        ),
        (
            "PnP not comparable rows",
            str(pnp.get("not_geometrically_comparable_row_count") or 0),
            "Rendered-corner PnP vs sim GT",
            "bad" if pnp.get("not_geometrically_comparable_row_count") else "good",
        ),
        (
            "Real camera/depth estimate",
            "not implemented",
            "Needs real capture sidecars",
            "blocked",
        ),
    ]
    card_w = 340
    card_h = 124
    for index, (title, value, detail, status) in enumerate(cards):
        col = index % 4
        row = index // 4
        scorecard_metric_card(
            canvas,
            title,
            value,
            detail,
            34 + col * (card_w + 18),
            212 + row * (card_h + 18),
            width=card_w,
            height=card_h,
            status=status,
        )

    table_x = 34
    table_y = 508
    table_w = width - 68
    row_h = 44
    cv2.rectangle(canvas, (table_x, table_y), (table_x + table_w, table_y + 42), SCORECARD_COLORS["header"], -1)
    scorecard_text(canvas, "Per-stage residuals", table_x + 14, table_y + 27, scale=0.55, color=(255, 255, 255), thickness=2)
    headers = [
        ("Stage", 16),
        ("GT piece", 250),
        ("Est piece", 385),
        ("Abs err", 520),
        ("GT board", 650),
        ("Est board", 785),
        ("Abs err", 920),
        ("Reproj", 1040),
        ("PnP vs GT", 1160),
    ]
    header_y = table_y + 76
    cv2.rectangle(canvas, (table_x, table_y + 42), (table_x + table_w, table_y + 86), (230, 235, 241), -1)
    for label, x_offset in headers:
        scorecard_text(canvas, label, table_x + x_offset, header_y, scale=0.42, color=SCORECARD_COLORS["muted"], thickness=1)

    stage_rows = scorecard.get("stage_rows")
    stage_rows = stage_rows if isinstance(stage_rows, list) else []
    for index, row in enumerate(stage_rows[:7]):
        row = row if isinstance(row, dict) else {}
        y0 = table_y + 86 + index * row_h
        fill = (255, 255, 255) if index % 2 == 0 else (245, 248, 252)
        cv2.rectangle(canvas, (table_x, y0), (table_x + table_w, y0 + row_h), fill, -1)
        cv2.line(canvas, (table_x, y0 + row_h), (table_x + table_w, y0 + row_h), (222, 226, 232), 1)
        gt = row.get("sim_ground_truth")
        gt = gt if isinstance(gt, dict) else {}
        estimate = row.get("metadata_derived_baseline")
        estimate = estimate if isinstance(estimate, dict) else {}
        pnp_status = str(estimate.get("pnp_vs_sim_ground_truth_status") or "unknown")
        values = [
            str(row.get("stage") or row.get("id") or ""),
            scorecard_format_number(gt.get("camera_to_piece_distance_mm"), ""),
            scorecard_format_number(estimate.get("estimated_camera_to_piece_distance_mm"), ""),
            scorecard_format_number(estimate.get("camera_to_piece_abs_error_mm"), ""),
            scorecard_format_number(gt.get("camera_to_board_plane_distance_mm"), ""),
            scorecard_format_number(estimate.get("estimated_camera_to_board_plane_distance_mm"), ""),
            scorecard_format_number(estimate.get("camera_to_board_abs_error_mm"), ""),
            scorecard_format_number(estimate.get("board_corner_reprojection_mean_residual_px"), ""),
            scorecard_display_status(pnp_status),
        ]
        for (header, x_offset), value in zip(headers, values):
            max_chars = 24 if header == "Stage" else 18
            if len(value) > max_chars:
                value = value[: max_chars - 1] + "."
            color = scorecard_color_for_status(value) if header == "PnP vs GT" else SCORECARD_COLORS["text"]
            scorecard_text(canvas, value, table_x + x_offset, y0 + 27, scale=0.38, color=color)

    gap_y = 930
    cv2.rectangle(canvas, (34, gap_y), (width - 34, height - 34), (255, 255, 255), -1)
    cv2.rectangle(canvas, (34, gap_y), (width - 34, height - 34), SCORECARD_COLORS["border"], 1)
    scorecard_text(canvas, "Explicit gap", 54, gap_y + 32, scale=0.58, thickness=2)
    scorecard_wrapped_text(
        canvas,
        gap.get("gap"),
        54,
        gap_y + 62,
        max_chars=160,
        scale=0.43,
        color=SCORECARD_COLORS["text"],
        line_height=21,
        max_lines=2,
    )
    scorecard_wrapped_text(
        canvas,
        gap.get("next_follow_up"),
        54,
        gap_y + 106,
        max_chars=160,
        scale=0.41,
        color=SCORECARD_COLORS["muted"],
        line_height=19,
        max_lines=2,
    )

    write_image(path, canvas)
    return {
        "path": str(path),
        "output_dimensions": {
            "width_px": int(width),
            "height_px": int(height),
        },
        "status": "ok",
    }


def write_depth_distance_scorecard(
    *,
    output_dir: Path,
    suite_output_dir: Path,
    sequence_metadata: dict[str, Any],
    distance_metrics: dict[str, Any],
    perceived_depth_comparison: dict[str, Any],
    pnp_residual_diagnostics: dict[str, Any],
    metadata_native_depth_view: dict[str, Any],
) -> dict[str, Any]:
    summary = build_depth_distance_scorecard_payload(
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=sequence_metadata,
        distance_metrics=distance_metrics,
        perceived_depth_comparison=perceived_depth_comparison,
        pnp_residual_diagnostics=pnp_residual_diagnostics,
        metadata_native_depth_view=metadata_native_depth_view,
    )
    paths = summary.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    png_path = Path(str(paths.get("png")))
    json_path = Path(str(paths.get("json")))
    visual = render_depth_distance_scorecard_png(png_path, summary)
    summary["visual"] = visual
    write_json(json_path, summary)
    return summary


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


def comparison_dict(row: dict[str, Any]) -> dict[str, Any]:
    comparison = row.get("perceived_depth_comparison")
    return comparison if isinstance(comparison, dict) else {}


def fmt_mm(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.1f}mm"


def fmt_px(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.1f}px"


def fmt_xy(value: Any) -> str:
    if not isinstance(value, list) or len(value) < 2:
        return "n/a"
    return f"({float(value[0]):.1f},{float(value[1]):.1f})"


def annotate_pick_place_frame(image_bgr: np.ndarray, row: dict[str, Any]) -> np.ndarray:
    header_height = 142
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
    comparison = comparison_dict(row)
    comparison_metrics = (
        f"PnP est/GT cam-piece={fmt_mm(comparison.get('estimated_camera_to_piece_distance_mm'))}/"
        f"{fmt_mm(comparison.get('ground_truth_camera_to_piece_distance_mm'))} "
        f"err={fmt_mm(comparison.get('camera_to_piece_error_mm'))} "
        f"| cam-board err={fmt_mm(comparison.get('camera_to_board_error_mm'))} "
        f"| {comparison.get('perceived_depth_status') or 'n/a'}"
    )
    cv2.putText(out, short_text(title), (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(route), (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (205, 220, 255), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(distance_metrics, 138), (10, 67), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (205, 245, 205), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(target_metrics, 138), (10, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 230, 175), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(comparison_metrics, 138), (10, 109), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 210, 210), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(gripper_metrics, 138), (10, 128), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (220, 220, 255), 1, cv2.LINE_AA)
    cv2.putText(out, short_text(visibility_metrics, 138), (10, 139), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (190, 220, 255), 1, cv2.LINE_AA)
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
                "perceived_depth_comparison": comparison_dict(row),
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
    metric_rows = [
        metric
        for metric in distance_metrics.get("rows", [])
        if isinstance(metric, dict)
    ]
    perceived_depth_comparison = write_perceived_depth_comparison(
        metric_rows=metric_rows,
        source_rows=pick_place_source_rows,
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=pick_place_metadata,
        distance_metrics=distance_metrics,
    )
    pnp_residual_diagnostics = write_pnp_residual_diagnostics(
        metric_rows=metric_rows,
        source_rows=pick_place_source_rows,
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=pick_place_metadata,
        distance_metrics=distance_metrics,
        perceived_depth_comparison=perceived_depth_comparison,
    )
    metadata_native_depth_view = write_metadata_native_depth_view(
        metric_rows=metric_rows,
        source_rows=pick_place_source_rows,
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=pick_place_metadata,
        distance_metrics=distance_metrics,
        pnp_residual_diagnostics=pnp_residual_diagnostics,
    )
    depth_distance_scorecard = write_depth_distance_scorecard(
        output_dir=output_dir,
        suite_output_dir=suite_output_dir,
        sequence_metadata=pick_place_metadata,
        distance_metrics=distance_metrics,
        perceived_depth_comparison=perceived_depth_comparison,
        pnp_residual_diagnostics=pnp_residual_diagnostics,
        metadata_native_depth_view=metadata_native_depth_view,
    )
    metrics_by_id = {
        str(metric.get("id")): metric
        for metric in metric_rows
        if metric.get("id") is not None
    }
    comparisons_by_id = {
        str(comparison.get("id")): comparison
        for comparison in perceived_depth_comparison.get("rows", [])
        if isinstance(comparison, dict) and comparison.get("id") is not None
    }
    for row in pick_place_source_rows:
        row["depth_distance_metric"] = metrics_by_id.get(str(row.get("id")))
        row["perceived_depth_comparison"] = comparisons_by_id.get(str(row.get("id")))
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
        "perceived_depth_comparison": perceived_depth_comparison,
        "pnp_residual_diagnostics": pnp_residual_diagnostics,
        "metadata_native_depth_view": metadata_native_depth_view,
        "depth_distance_scorecard": depth_distance_scorecard,
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
            "Pick/place perceived-depth comparison artifacts add a metadata-derived rendered-board-corner PnP baseline and residuals against simulator ground truth; this is not a real-camera depth estimator.",
            "Pick/place PnP residual diagnostics compare metadata-projected board corners, rendered-corner PnP, and simulator ground-truth extrinsics so source mismatches are visible.",
            "Pick/place metadata-native depth artifacts project board, piece, and target points directly through SimCamera metadata and do not use rendered overlay corners as depth authority.",
            "Pick/place depth-distance scorecard artifacts summarize simulator ground truth, the metadata-derived PnP baseline, residual severity, and the missing true real-camera/depth-sensor reference in one visual PNG plus JSON.",
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
        "perceived_depth_comparison": {},
        "pnp_residual_diagnostics": {},
        "metadata_native_depth_view": {},
        "depth_distance_scorecard": {},
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
