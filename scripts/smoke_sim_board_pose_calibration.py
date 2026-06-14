#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.cameras.configs import ColorMode
from lerobot.configs.chessboard import ChessBoardParams
from lerobot.perception.chess.board_model import BoardModel
from lerobot.perception.chess.board_pose_estimator import BoardPoseEstimator
from lerobot.sim import SimCamera, SimCameraConfig

CORNER_LABELS = ("a1", "h1", "h8", "a8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test board pose calibration from synthetic simulator camera metadata."
    )
    parser.add_argument(
        "--frame-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "sim" / "board_pose_calibration",
        help="Directory for frame, annotated frame, BoardModel JSON, and summary JSON artifacts.",
    )
    parser.add_argument("--piece-square", default="e4")
    parser.add_argument("--view", choices=("gripper", "overview", "birdseye"), default="gripper")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--square-size-mm", type=float, default=50.0)
    return parser.parse_args()


def square_to_file_rank(square: str) -> tuple[int, int]:
    sq = square.strip().lower()
    if len(sq) != 2 or sq[0] < "a" or sq[0] > "h" or sq[1] < "1" or sq[1] > "8":
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(sq[0]) - ord("a"), int(sq[1]) - 1


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

    a1, h1, h8, a8 = corners_xy
    if not (a1[0] < h1[0] and a8[0] < h8[0]):
        raise AssertionError(f"Expected a-file corners left of h-file corners: {corners_xy}")
    if not (a1[1] > a8[1] and h1[1] > h8[1]):
        raise AssertionError(f"Expected rank-1 corners below rank-8 corners: {corners_xy}")

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
    }


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise AssertionError(f"cv2 failed to write {path}")


def jsonable_matrix(matrix: np.ndarray) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix.tolist()]


def project_board_xy_to_image(H_board_to_image: np.ndarray, board_xy: np.ndarray) -> np.ndarray:
    pts = np.asarray(board_xy, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(1, 2)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("board_xy must be (2,) or (N,2)")

    pts_h = np.vstack([pts.T, np.ones((1, pts.shape[0]), dtype=float)])
    projected_h = H_board_to_image @ pts_h
    return (projected_h[:2, :] / projected_h[2:3, :]).T


def main() -> int:
    args = parse_args()
    frame_dir = args.frame_dir.expanduser().resolve()
    frame_dir.mkdir(parents=True, exist_ok=True)

    camera_cfg = SimCameraConfig(
        width=int(args.width),
        height=int(args.height),
        fps=int(args.fps),
        color_mode=ColorMode.BGR,
        view=str(args.view),
        piece_layout="single_pawn",
        piece_square=str(args.piece_square),
        track_robot_gripper=True,
    )
    camera = SimCamera(camera_cfg)

    try:
        camera.connect(warmup=True)
        frame = camera.async_read()
        metadata = camera.calibration_metadata()
    finally:
        if camera.is_connected:
            camera.disconnect()

    expected_shape = (int(args.height), int(args.width), 3)
    assert frame.shape == expected_shape, frame.shape
    assert frame.dtype == np.uint8, frame.dtype
    unique_colors = int(len(np.unique(frame.reshape(-1, 3), axis=0)))
    assert unique_colors >= 12, unique_colors
    assert metadata["piece_layout"] == "single_pawn", metadata
    assert metadata["piece_square"] == str(args.piece_square), metadata

    corners_xy = np.asarray(metadata["board_corners_xy"], dtype=float)
    corner_checks = assert_corners_valid(corners_xy, int(args.width), int(args.height))

    estimator = BoardPoseEstimator(square_size_mm=float(args.square_size_mm))
    board_pose = estimator.estimate_from_corners(corners_xy)
    H_board_to_image = estimator.estimate_board_to_image_homography(corners_xy)
    H_image_to_board = estimator.estimate_image_to_board_homography(corners_xy)

    board_corners_m = estimator.board_corners_xy_m()
    remapped_corners_m = estimator.image_to_board_xy_m(corners_xy, corners_xy)
    corner_error_m = np.linalg.norm(remapped_corners_m - board_corners_m, axis=1)
    assert float(np.max(corner_error_m)) < 1e-9, corner_error_m

    params = ChessBoardParams(square_size_mm=float(args.square_size_mm))
    board_model = BoardModel(params=params, T_base_board=board_pose)
    board_model_path = frame_dir / "board_model.json"
    board_model.save(board_model_path)
    loaded_board_model = BoardModel.load(board_model_path)

    file_idx, rank_idx = square_to_file_rank(str(args.piece_square))
    piece_center_board_xyz = loaded_board_model.square_center_in_board(file_idx, rank_idx)
    piece_center_board_xy = piece_center_board_xyz[:2].reshape(1, 2)
    piece_center_image_xy = project_board_xy_to_image(H_board_to_image, piece_center_board_xy)
    piece_roundtrip_xy = estimator.image_to_board_xy_m(piece_center_image_xy, corners_xy)
    piece_error_m = float(np.linalg.norm(piece_roundtrip_xy[0] - piece_center_board_xy[0]))
    assert piece_error_m < 1e-9, piece_error_m

    square_centers_board_xy: list[list[float]] = []
    square_centers_image_xy: list[list[float]] = []
    square_center_errors_m: list[float] = []
    for rank in range(8):
        for file in range(8):
            center_xyz = loaded_board_model.square_center_in_board(file, rank)
            center_xy = center_xyz[:2]
            projected_xy = project_board_xy_to_image(H_board_to_image, center_xy)[0]
            roundtrip_xy = estimator.image_to_board_xy_m(projected_xy.reshape(1, 2), corners_xy)[0]
            square_centers_board_xy.append([float(center_xy[0]), float(center_xy[1])])
            square_centers_image_xy.append([float(projected_xy[0]), float(projected_xy[1])])
            square_center_errors_m.append(float(np.linalg.norm(roundtrip_xy - center_xy)))

    max_square_center_error_m = max(square_center_errors_m)
    assert max_square_center_error_m < 1e-9, max_square_center_error_m

    frame_path = frame_dir / "frame.jpg"
    annotated_path = frame_dir / "frame_annotated.jpg"
    write_image(frame_path, frame)
    write_image(annotated_path, estimator.draw_corners(frame, corners_xy))

    summary_path = frame_dir / "summary.json"
    summary = {
        "ok": True,
        "scenario": "sim_board_pose_calibration",
        "frame_dir": str(frame_dir),
        "summary_path": str(summary_path),
        "frame_path": str(frame_path),
        "annotated_frame_path": str(annotated_path),
        "board_model_path": str(board_model_path),
        "image": {
            "width": int(args.width),
            "height": int(args.height),
            "shape": list(frame.shape),
            "dtype": str(frame.dtype),
            "unique_colors": unique_colors,
            "mean_bgr": [float(value) for value in frame.mean(axis=(0, 1))],
        },
        "camera_metadata": metadata,
        "corner_checks": corner_checks,
        "board_geometry": {
            "square_size_mm": float(args.square_size_mm),
            "board_size_squares": list(estimator.board_size_squares),
            "board_corners_xy_m": board_corners_m.tolist(),
            "outer_size_m": [
                float(params.effective_square_size_x_mm * 8 / 1000.0),
                float(params.effective_square_size_y_mm * 8 / 1000.0),
            ],
        },
        "pose_estimator": {
            "board_to_image_homography": jsonable_matrix(H_board_to_image),
            "image_to_board_homography": jsonable_matrix(H_image_to_board),
            "estimated_T_camera_board": jsonable_matrix(board_pose.T),
            "corner_roundtrip_error_m": [float(value) for value in corner_error_m],
            "max_corner_roundtrip_error_m": float(np.max(corner_error_m)),
            "max_square_center_roundtrip_error_m": float(max_square_center_error_m),
        },
        "piece_square": {
            "square": str(args.piece_square),
            "file_idx": file_idx,
            "rank_idx": rank_idx,
            "center_board_xyz_m": [float(value) for value in piece_center_board_xyz],
            "projected_image_xy": [float(value) for value in piece_center_image_xy[0]],
            "roundtrip_board_xy_m": [float(value) for value in piece_roundtrip_xy[0]],
            "roundtrip_error_m": piece_error_m,
        },
        "square_centers": {
            "board_xy_m": square_centers_board_xy,
            "image_xy": square_centers_image_xy,
        },
        "notes": [
            "Synthetic calibration currently validates metadata-fed corner ordering and homography math; it does not detect corners from pixels.",
            "BoardPoseEstimator.estimate_from_corners returns a pseudo-camera identity pose until camera intrinsics/extrinsics are modeled.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
