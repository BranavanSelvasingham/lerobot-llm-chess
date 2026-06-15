#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.cameras.configs import ColorMode  # noqa: E402
from lerobot.sim import (  # noqa: E402
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    SimCamera,
    SimCameraConfig,
    make_sim_camera_config_from_profile,
)
import lerobot.sim.camera as sim_camera_module  # noqa: E402
from lerobot.sim.config import SIM_CAMERA_DISTORTION_COEFFICIENT_ORDER  # noqa: E402

SCHEMA = "lerobot.sim.camera_pose_fixture.v1"
CORNER_LABELS = ("a1", "h1", "h8", "a8")
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "sim_camera_pose_fixture"
FROZEN_MARKER_TIME_SECONDS = 0.0
METADATA_CONTRACT_KEYS = (
    "image_size_px",
    "camera_matrix_px",
    "intrinsics",
    "distortion_coefficients",
    "extrinsics.board_to_camera",
    "coordinate_frame_convention",
    "board_corners_xy",
    "target_square.center_image_xy",
    "piece_square.center_image_xy",
    "hardware_skipped",
    "gui_skipped",
    "deterministic_case_id",
)


@dataclass(frozen=True)
class PoseCase:
    case_id: str
    description: str
    overrides: dict[str, Any]
    robot_state: dict[str, float]
    target_square: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a small deterministic SimCamera pose fixture for reviewing camera/board "
            "calibration metadata without hardware or GUI display flows."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
    )
    parser.add_argument("--target-square", default="e4")
    parser.add_argument("--overview-square", default="d4")
    parser.add_argument("--closed-gripper-square", default="e5")
    parser.add_argument("--open-gripper-percent", type=float, default=80.0)
    parser.add_argument("--closed-gripper-percent", type=float, default=20.0)
    return parser.parse_args()


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if hasattr(value, "value"):
        return jsonable(value.value)
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise AssertionError(f"cv2 failed to write {path}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_stats(image_bgr: np.ndarray) -> dict[str, Any]:
    flat = image_bgr.reshape(-1, 3)
    return {
        "width": int(image_bgr.shape[1]),
        "height": int(image_bgr.shape[0]),
        "shape": [int(value) for value in image_bgr.shape],
        "dtype": str(image_bgr.dtype),
        "min_bgr": [int(value) for value in flat.min(axis=0)],
        "max_bgr": [int(value) for value in flat.max(axis=0)],
        "mean_bgr": [float(value) for value in flat.mean(axis=0)],
        "std_bgr": [float(value) for value in flat.std(axis=0)],
        "unique_colors": int(len(np.unique(flat, axis=0))),
    }


def square_to_file_rank(square: str) -> tuple[int, int]:
    sq = square.strip().lower()
    if len(sq) != 2 or sq[0] < "a" or sq[0] > "h" or sq[1] < "1" or sq[1] > "8":
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(sq[0]) - ord("a"), int(sq[1]) - 1


def board_point(corners_xy: np.ndarray, u: float, v: float) -> np.ndarray:
    a1, h1, h8, a8 = corners_xy
    bottom = a1 * (1.0 - u) + h1 * u
    top = a8 * (1.0 - u) + h8 * u
    return bottom * (1.0 - v) + top * v


def square_center_xy(corners_xy: np.ndarray, square: str) -> tuple[int, int, np.ndarray]:
    file_idx, rank_idx = square_to_file_rank(square)
    center = board_point(corners_xy, (file_idx + 0.5) / 8.0, (rank_idx + 0.5) / 8.0)
    return file_idx, rank_idx, center


def polygon_area_xy(points_xy: np.ndarray) -> float:
    x = points_xy[:, 0]
    y = points_xy[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def assert_corners_valid(corners_xy: np.ndarray, width: int, height: int) -> dict[str, Any]:
    if corners_xy.shape != (4, 2):
        raise AssertionError(f"Expected four board corners, got {corners_xy.shape}")
    if not np.all(np.isfinite(corners_xy)):
        raise AssertionError(f"Board corners contain non-finite values: {corners_xy}")

    in_bounds_x = np.logical_and(corners_xy[:, 0] >= 0.0, corners_xy[:, 0] < float(width))
    in_bounds_y = np.logical_and(corners_xy[:, 1] >= 0.0, corners_xy[:, 1] < float(height))
    if not bool(np.all(in_bounds_x & in_bounds_y)):
        raise AssertionError(f"Board corners out of image bounds {width}x{height}: {corners_xy}")

    area_px2 = polygon_area_xy(corners_xy)
    min_area_px2 = float(width * height) * 0.10
    if abs(area_px2) < min_area_px2:
        raise AssertionError(f"Board quadrilateral area too small: {area_px2} px^2")

    edge_lengths = [
        float(np.linalg.norm(corners_xy[(idx + 1) % 4] - corners_xy[idx])) for idx in range(4)
    ]
    if min(edge_lengths) < 12.0:
        raise AssertionError(f"Board edge too short for calibration: {edge_lengths}")

    return {
        "labels": list(CORNER_LABELS),
        "area_px2": area_px2,
        "edge_lengths_px": edge_lengths,
        "image_y_down_orientation": "clockwise" if area_px2 > 0.0 else "counter_clockwise",
        "in_bounds": True,
    }


def assert_point_in_bounds(point_xy: np.ndarray, width: int, height: int, *, label: str) -> None:
    x, y = float(point_xy[0]), float(point_xy[1])
    if not (0.0 <= x < float(width) and 0.0 <= y < float(height)):
        raise AssertionError(f"{label} is out of image bounds {width}x{height}: {[x, y]}")


def assert_float_matrix(value: Any, *, shape: tuple[int, int], label: str) -> np.ndarray:
    try:
        matrix = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise AssertionError(f"{label} must be numeric: {value!r}") from exc
    if matrix.shape != shape:
        raise AssertionError(f"{label} shape {matrix.shape} != {shape}")
    if not np.all(np.isfinite(matrix)):
        raise AssertionError(f"{label} contains non-finite values: {matrix}")
    return matrix


def assert_float_vector(value: Any, *, length: int | None, label: str) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise AssertionError(f"{label} must be numeric: {value!r}") from exc
    if vector.ndim != 1:
        raise AssertionError(f"{label} must be one-dimensional, got {vector.shape}")
    if length is not None and vector.shape != (length,):
        raise AssertionError(f"{label} shape {vector.shape} != ({length},)")
    if vector.size == 0:
        raise AssertionError(f"{label} must contain at least one coefficient")
    if not np.all(np.isfinite(vector)):
        raise AssertionError(f"{label} contains non-finite values: {vector}")
    return vector


def assert_camera_metadata_contract(metadata: dict[str, Any], *, width: int, height: int) -> dict[str, Any]:
    image_size = metadata.get("image_size_px")
    if not isinstance(image_size, dict):
        raise AssertionError("camera_metadata.image_size_px must be an object")
    if image_size.get("width") != width or image_size.get("height") != height:
        raise AssertionError(f"camera_metadata image size {image_size} != {width}x{height}")

    camera_matrix = assert_float_matrix(
        metadata.get("camera_matrix_px"),
        shape=(3, 3),
        label="camera_metadata.camera_matrix_px",
    )
    if not np.allclose(camera_matrix[2], np.array([0.0, 0.0, 1.0], dtype=float)):
        raise AssertionError(f"camera_metadata.camera_matrix_px has invalid final row: {camera_matrix[2]}")

    intrinsics = metadata.get("intrinsics")
    if not isinstance(intrinsics, dict):
        raise AssertionError("camera_metadata.intrinsics must be an object")
    for key in ("fx_px", "fy_px", "cx_px", "cy_px", "camera_matrix_px"):
        if key not in intrinsics:
            raise AssertionError(f"camera_metadata.intrinsics missing {key}")
    nested_matrix = assert_float_matrix(
        intrinsics.get("camera_matrix_px"),
        shape=(3, 3),
        label="camera_metadata.intrinsics.camera_matrix_px",
    )
    if not np.allclose(camera_matrix, nested_matrix):
        raise AssertionError("camera_metadata intrinsics matrix does not match camera_matrix_px")

    distortion = assert_float_vector(
        metadata.get("distortion_coefficients"),
        length=None,
        label="camera_metadata.distortion_coefficients",
    )
    coefficient_order = metadata.get("distortion_coefficient_order")
    if not isinstance(coefficient_order, list) or len(coefficient_order) != len(distortion):
        raise AssertionError(
            "camera_metadata.distortion_coefficient_order must name each distortion coefficient"
        )

    extrinsics = metadata.get("extrinsics")
    if not isinstance(extrinsics, dict):
        raise AssertionError("camera_metadata.extrinsics must be an object")
    board_to_camera = extrinsics.get("board_to_camera")
    if not isinstance(board_to_camera, dict):
        raise AssertionError("camera_metadata.extrinsics.board_to_camera must be an object")
    rotation = assert_float_matrix(
        board_to_camera.get("rotation_matrix"),
        shape=(3, 3),
        label="camera_metadata.extrinsics.board_to_camera.rotation_matrix",
    )
    translation = assert_float_vector(
        board_to_camera.get("translation_m"),
        length=3,
        label="camera_metadata.extrinsics.board_to_camera.translation_m",
    )
    if not board_to_camera.get("name"):
        raise AssertionError("camera_metadata.extrinsics.board_to_camera must have a name")

    convention = metadata.get("coordinate_frame_convention")
    if not isinstance(convention, dict):
        raise AssertionError("camera_metadata.coordinate_frame_convention must be an object")
    for key in ("image_frame", "camera_frame", "board_frame", "extrinsics", "scope"):
        if not isinstance(convention.get(key), str) or not convention.get(key):
            raise AssertionError(f"camera_metadata.coordinate_frame_convention missing {key}")

    return {
        "image_size_px": True,
        "camera_matrix_px": True,
        "intrinsics": True,
        "distortion_coefficients": True,
        "distortion_coefficient_count": int(distortion.size),
        "distortion_coefficient_order": [str(value) for value in coefficient_order],
        "extrinsics.board_to_camera": True,
        "extrinsics_name": str(board_to_camera.get("name")),
        "extrinsics_rotation_shape": [int(value) for value in rotation.shape],
        "extrinsics_translation_m": [float(value) for value in translation.tolist()],
        "coordinate_frame_convention": True,
        "coordinate_frame_scope": str(convention.get("scope")),
    }


def assert_distortion_config_contract() -> dict[str, Any]:
    expected_length = len(SIM_CAMERA_DISTORTION_COEFFICIENT_ORDER)
    default_cfg = SimCameraConfig()
    default_coefficients = default_cfg.distortion_coefficients or ()
    if len(default_coefficients) != expected_length:
        raise AssertionError(
            "Default SimCameraConfig distortion_coefficients must match "
            f"distortion_coefficient_order length {expected_length}; got {len(default_coefficients)}."
        )

    mismatched_error: str | None = None
    try:
        SimCameraConfig(distortion_coefficients=(0.0, 0.0, 0.0, 0.0))
    except ValueError as exc:
        mismatched_error = str(exc)
    if not mismatched_error or "distortion_coefficients" not in mismatched_error:
        raise AssertionError("Mismatched distortion_coefficients vector did not fail with a clear ValueError.")

    return {
        "default_coefficients_match_order": True,
        "mismatched_coefficients_rejected": True,
        "distortion_coefficient_order": list(SIM_CAMERA_DISTORTION_COEFFICIENT_ORDER),
        "mismatched_error": mismatched_error,
    }


def shifted_corners(corners: np.ndarray, offsets: list[tuple[float, float]]) -> list[list[float]]:
    return (corners + np.asarray(offsets, dtype=float)).tolist()


def build_cases(args: argparse.Namespace) -> list[PoseCase]:
    profile = SIM_CAMERA_CALIBRATION_PROFILES[str(args.profile)]
    corners = np.asarray(profile["board_corners_xy"], dtype=float)
    perturbed_corners = shifted_corners(
        corners,
        [(2.0, -1.0), (-2.0, 2.0), (-2.0, 2.0), (2.0, 2.0)],
    )
    open_pct = float(np.clip(float(args.open_gripper_percent), 0.0, 100.0))
    closed_pct = float(np.clip(float(args.closed_gripper_percent), 0.0, 100.0))
    target_square = str(args.target_square)
    overview_square = str(args.overview_square)
    closed_square = str(args.closed_gripper_square)
    return [
        PoseCase(
            case_id=f"nominal_gripper_open_{target_square}",
            description="Named gripper reference profile with the tracked gripper open.",
            overrides={"piece_square": target_square},
            robot_state={"gripper": open_pct},
            target_square=target_square,
        ),
        PoseCase(
            case_id=f"perturbed_board_pose_open_{target_square}",
            description="Mild board-corner perturbation for camera-first calibration review.",
            overrides={"board_corners_xy": perturbed_corners, "piece_square": target_square},
            robot_state={"gripper": open_pct},
            target_square=target_square,
        ),
        PoseCase(
            case_id=f"overview_nominal_{overview_square}",
            description="Overview board view using SimCamera's overview pose geometry.",
            overrides={
                "view": "overview",
                "board_corners_xy": None,
                "gripper_visible": False,
                "piece_square": overview_square,
            },
            robot_state={},
            target_square=overview_square,
        ),
        PoseCase(
            case_id=f"nominal_gripper_closed_{closed_square}",
            description="Named gripper reference profile with the tracked gripper mostly closed.",
            overrides={"piece_square": closed_square},
            robot_state={"gripper": closed_pct},
            target_square=closed_square,
        ),
    ]


def add_label(image_bgr: np.ndarray, lines: list[str], *, height_px: int = 58) -> np.ndarray:
    out = image_bgr.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], min(out.shape[0], height_px)), (0, 0, 0), -1)
    for index, line in enumerate(lines[:3]):
        y = 20 + index * 17
        cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (255, 255, 255), 1)
    return out


def draw_labeled_marker(
    image_bgr: np.ndarray,
    point_xy: np.ndarray,
    label: str,
    color: tuple[int, int, int],
    *,
    marker_type: int,
) -> None:
    xy = (int(round(float(point_xy[0]))), int(round(float(point_xy[1]))))
    cv2.drawMarker(image_bgr, xy, color, markerType=marker_type, markerSize=22, thickness=2)
    cv2.putText(image_bgr, label, (xy[0] + 9, xy[1] + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 3)
    cv2.putText(image_bgr, label, (xy[0] + 9, xy[1] + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)


def annotate_pose(
    image_bgr: np.ndarray,
    *,
    case_id: str,
    profile: str,
    view: str,
    corners_xy: np.ndarray,
    target_square: str,
    target_center_xy: np.ndarray,
    piece_square: str,
    piece_center_xy: np.ndarray,
) -> np.ndarray:
    out = image_bgr.copy()
    pts = np.round(corners_xy).astype(int)
    cv2.polylines(out, [pts], isClosed=True, color=(0, 210, 255), thickness=2)
    for label, pt in zip(CORNER_LABELS, pts, strict=True):
        xy = (int(pt[0]), int(pt[1]))
        cv2.circle(out, xy, 6, (0, 0, 255), -1)
        cv2.putText(out, label, (xy[0] + 7, xy[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (0, 0, 0), 3)
        cv2.putText(out, label, (xy[0] + 7, xy[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1)

    draw_labeled_marker(
        out,
        target_center_xy,
        f"target {target_square}",
        (0, 255, 0),
        marker_type=cv2.MARKER_CROSS,
    )
    if piece_square != target_square or np.linalg.norm(piece_center_xy - target_center_xy) > 1e-6:
        draw_labeled_marker(
            out,
            piece_center_xy,
            f"piece {piece_square}",
            (255, 0, 255),
            marker_type=cv2.MARKER_TILTED_CROSS,
        )
    return add_label(out, [case_id, f"profile={profile} view={view}", f"target={target_square} piece={piece_square}"])


def render_frame(camera: SimCamera) -> tuple[np.ndarray, dict[str, Any]]:
    original_time = sim_camera_module.time.time
    sim_camera_module.time.time = lambda: FROZEN_MARKER_TIME_SECONDS
    try:
        camera.connect(warmup=False)
        frame_bgr = camera.read(ColorMode.BGR)
        metadata = camera.calibration_metadata()
    finally:
        sim_camera_module.time.time = original_time
        if camera.is_connected:
            camera.disconnect()
    return frame_bgr, metadata


def render_case(
    *,
    profile_name: str,
    case: PoseCase,
    output_dir: Path,
) -> tuple[dict[str, Any], np.ndarray]:
    camera_cfg = make_sim_camera_config_from_profile(
        profile_name,
        color_mode=ColorMode.BGR,
        **case.overrides,
    )
    camera = SimCamera(camera_cfg)
    if case.robot_state:
        camera.set_robot_state(case.robot_state)
    frame_bgr, metadata = render_frame(camera)

    expected_shape = (int(camera_cfg.height), int(camera_cfg.width), 3)
    if frame_bgr.shape != expected_shape:
        raise AssertionError(f"{case.case_id} frame shape {frame_bgr.shape} != {expected_shape}")
    if frame_bgr.dtype != np.uint8:
        raise AssertionError(f"{case.case_id} frame dtype {frame_bgr.dtype} != uint8")

    stats = image_stats(frame_bgr)
    if int(stats["unique_colors"]) < 12:
        raise AssertionError(f"{case.case_id} rendered too few unique colors: {stats['unique_colors']}")

    corners_xy = np.asarray(metadata["board_corners_xy"], dtype=float)
    corner_checks = assert_corners_valid(corners_xy, int(camera_cfg.width), int(camera_cfg.height))
    metadata_checks = assert_camera_metadata_contract(
        metadata,
        width=int(camera_cfg.width),
        height=int(camera_cfg.height),
    )

    target_file, target_rank, target_center = square_center_xy(corners_xy, case.target_square)
    piece_file, piece_rank, piece_center = square_center_xy(corners_xy, str(camera_cfg.piece_square))
    assert_point_in_bounds(target_center, int(camera_cfg.width), int(camera_cfg.height), label="target center")
    assert_point_in_bounds(piece_center, int(camera_cfg.width), int(camera_cfg.height), label="piece center")

    case_dir = output_dir / "cases" / case.case_id
    frame_path = case_dir / "frame.png"
    annotated_path = case_dir / "frame_annotated.png"
    metadata_path = case_dir / "camera_metadata.json"
    annotated = annotate_pose(
        frame_bgr,
        case_id=case.case_id,
        profile=profile_name,
        view=str(camera_cfg.view),
        corners_xy=corners_xy,
        target_square=case.target_square,
        target_center_xy=target_center,
        piece_square=str(camera_cfg.piece_square),
        piece_center_xy=piece_center,
    )
    write_image(frame_path, frame_bgr)
    write_image(annotated_path, annotated)

    projection = {
        "corner_labels": list(CORNER_LABELS),
        "board_corners_xy": [[float(x), float(y)] for x, y in corners_xy.tolist()],
        "target_square": {
            "square": case.target_square,
            "file_idx": target_file,
            "rank_idx": target_rank,
            "center_image_xy": [float(value) for value in target_center],
        },
        "piece_square": {
            "square": str(camera_cfg.piece_square),
            "file_idx": piece_file,
            "rank_idx": piece_rank,
            "center_image_xy": [float(value) for value in piece_center],
        },
    }
    metadata_contract_checks = {
        **metadata_checks,
        "board_corners_xy": True,
        "target_square.center_image_xy": True,
        "piece_square.center_image_xy": True,
        "hardware_skipped": True,
        "gui_skipped": True,
        "deterministic_case_id": bool(case.case_id),
        "required_keys": list(METADATA_CONTRACT_KEYS),
    }
    payload = {
        "schema": SCHEMA,
        "ok": True,
        "case_id": case.case_id,
        "description": case.description,
        "profile": profile_name,
        "view": str(camera_cfg.view),
        "overrides": jsonable(case.overrides),
        "robot_state": jsonable(case.robot_state),
        "hardware_skipped": True,
        "gui_skipped": True,
        "deterministic": {
            "sim_camera_marker_time_seconds": FROZEN_MARKER_TIME_SECONDS,
            "warmup": False,
            "read_count": 1,
        },
        "artifacts": {
            "frame_path": str(frame_path),
            "annotated_frame_path": str(annotated_path),
            "metadata_path": str(metadata_path),
        },
        "image": {
            **stats,
            "frame_sha256": file_sha256(frame_path),
            "annotated_frame_sha256": file_sha256(annotated_path),
        },
        "camera_metadata": metadata,
        "metadata_contract_checks": metadata_contract_checks,
        "corner_checks": corner_checks,
        "projection": projection,
    }
    write_json(metadata_path, payload)
    return payload, frame_bgr


def metadata_contract_summary(case_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, dict[str, Any]] = {}
    for payload in case_payloads:
        case_id = str(payload.get("case_id"))
        checks = payload.get("metadata_contract_checks")
        checks = checks if isinstance(checks, dict) else {}
        by_case[case_id] = {
            key: bool(checks.get(key))
            for key in METADATA_CONTRACT_KEYS
        }
    return {
        "required_keys": list(METADATA_CONTRACT_KEYS),
        "all_cases_include_required_metadata": all(
            all(case_checks.values()) for case_checks in by_case.values()
        ),
        "case_count": len(case_payloads),
        "by_case": by_case,
        "scope": (
            "SimCamera intrinsics/extrinsics are stable simulator reference metadata, "
            "not physical SO-101 calibration truth."
        ),
    }


def same_shape_frame_delta(reference_bgr: np.ndarray, candidate_bgr: np.ndarray) -> dict[str, Any] | None:
    if reference_bgr.shape != candidate_bgr.shape:
        return None
    delta = reference_bgr.astype(np.float32) - candidate_bgr.astype(np.float32)
    abs_delta = np.abs(delta)
    return {
        "mean_abs_delta": float(abs_delta.mean()),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "mean_abs_delta_bgr": [float(value) for value in abs_delta.mean(axis=(0, 1))],
    }


def case_comparison(
    nominal: dict[str, Any],
    nominal_frame: np.ndarray,
    candidate: dict[str, Any],
    candidate_frame: np.ndarray,
) -> dict[str, Any]:
    nominal_corners = np.asarray(nominal["projection"]["board_corners_xy"], dtype=float)
    candidate_corners = np.asarray(candidate["projection"]["board_corners_xy"], dtype=float)
    corner_delta = candidate_corners - nominal_corners
    nominal_target = np.asarray(nominal["projection"]["target_square"]["center_image_xy"], dtype=float)
    candidate_target = np.asarray(candidate["projection"]["target_square"]["center_image_xy"], dtype=float)
    return {
        "baseline_case_id": nominal["case_id"],
        "case_id": candidate["case_id"],
        "same_view": nominal.get("view") == candidate.get("view"),
        "board_corner_delta_px": [[float(x), float(y)] for x, y in corner_delta.tolist()],
        "mean_corner_l2_px": float(np.linalg.norm(corner_delta, axis=1).mean()),
        "max_corner_l2_px": float(np.linalg.norm(corner_delta, axis=1).max()),
        "target_center_delta_px": [float(value) for value in (candidate_target - nominal_target)],
        "target_center_l2_px": float(np.linalg.norm(candidate_target - nominal_target)),
        "frame_delta": same_shape_frame_delta(nominal_frame, candidate_frame),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config_contract_checks = assert_distortion_config_contract()

    rendered = [
        render_case(profile_name=str(args.profile), case=case, output_dir=output_dir)
        for case in build_cases(args)
    ]
    case_payloads = [payload for payload, _frame in rendered]
    nominal_payload, nominal_frame = rendered[0]
    comparisons = [
        case_comparison(nominal_payload, nominal_frame, payload, frame)
        for payload, frame in rendered[1:]
    ]

    frame_paths = {payload["case_id"]: payload["artifacts"]["frame_path"] for payload in case_payloads}
    annotated_frame_paths = {
        payload["case_id"]: payload["artifacts"]["annotated_frame_path"] for payload in case_payloads
    }
    metadata_paths = {payload["case_id"]: payload["artifacts"]["metadata_path"] for payload in case_payloads}
    summary_path = output_dir / "sim_camera_pose_fixture_summary.json"
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": "ok",
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "profile": str(args.profile),
        "case_count": len(case_payloads),
        "case_ids": [payload["case_id"] for payload in case_payloads],
        "deterministic_case_ids": True,
        "hardware_skipped": True,
        "gui_skipped": True,
        "skipped_markers": {
            "hardware": "Fixture renders existing SimCamera frames only; no SO-101 motors, serial ports, or camera devices are opened.",
            "gui": "Fixture writes files directly and does not request OpenCV display, click, or GUI calibration flows.",
        },
        "deterministic": {
            "sim_camera_marker_time_seconds": FROZEN_MARKER_TIME_SECONDS,
            "warmup": False,
            "reads_per_case": 1,
        },
        "config_contract_checks": config_contract_checks,
        "artifacts": {
            "summary_path": str(summary_path),
            "case_dir": str(output_dir / "cases"),
            "frame_paths": frame_paths,
            "annotated_frame_paths": annotated_frame_paths,
            "metadata_paths": metadata_paths,
        },
        "frame_paths": frame_paths,
        "annotated_frame_paths": annotated_frame_paths,
        "metadata_paths": metadata_paths,
        "metadata_contract": metadata_contract_summary(case_payloads),
        "cases": case_payloads,
        "comparisons_to_nominal": comparisons,
        "real_media_gap_notes": [
            "The current real reference media inventory is limited to archive/chess_test_images/current_view.jpg.",
            "No real-world videos are present for motion, recovery, or timing references.",
            "No reference media currently documents failure modes.",
        ],
        "notes": [
            "This fixture uses existing SimCamera and SimCameraConfig profile APIs; it does not modify rendering or canonical calibration constants.",
            "SimCamera intrinsics/extrinsics are simulator reference metadata for downstream tool compatibility, not physical calibration truth.",
            "Pixel deltas are recorded as review evidence only; pass/fail checks stay structural because SimCamera is a synthetic renderer.",
        ],
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
