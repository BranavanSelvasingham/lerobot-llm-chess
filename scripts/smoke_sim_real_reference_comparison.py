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
from lerobot.sim import (
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    SimCamera,
    make_sim_camera_config_from_profile,
)

CORNER_LABELS = ("a1", "h1", "h8", "a8")
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_reference_comparison"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the synthetic gripper SimCamera frame against the known real gripper-camera reference."
    )
    parser.add_argument(
        "--output-dir",
        "--frame-dir",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for synthetic, annotated, side-by-side, overlay, diff, and summary artifacts.",
    )
    parser.add_argument(
        "--reference-image",
        type=Path,
        default=REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg",
        help="Real gripper-camera reference image.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
    )
    parser.add_argument("--piece-square", default=None, help="Override the profile's synthetic piece square.")
    parser.add_argument("--gripper-percent", type=float, default=80.0)
    parser.add_argument("--overlay-alpha", type=float, default=0.50)
    return parser.parse_args()


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise AssertionError(f"cv2 failed to write {path}")


def read_reference_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError(f"cv2 failed to read reference image {path}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise AssertionError(f"Expected BGR reference image, got shape {image.shape}")
    return image


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

    return {
        "labels": list(CORNER_LABELS),
        "area_px2": polygon_area_xy(corners_xy),
        "in_bounds": True,
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


def annotate_reference_geometry(image_bgr: np.ndarray, corners_xy: np.ndarray, piece_square: str) -> np.ndarray:
    out = image_bgr.copy()
    pts = np.round(corners_xy).astype(int)
    cv2.polylines(out, [pts], isClosed=True, color=(0, 210, 255), thickness=2)
    for label, pt in zip(CORNER_LABELS, pts, strict=True):
        xy = tuple(int(value) for value in pt)
        cv2.circle(out, xy, 7, (0, 0, 255), -1)
        cv2.putText(out, label, (xy[0] + 7, xy[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3)
        cv2.putText(out, label, (xy[0] + 7, xy[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)

    _, _, center = square_center_xy(corners_xy, piece_square)
    cx, cy = int(round(center[0])), int(round(center[1]))
    cv2.drawMarker(out, (cx, cy), (0, 255, 0), markerType=cv2.MARKER_CROSS, markerSize=22, thickness=2)
    cv2.putText(out, piece_square, (cx + 9, cy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
    cv2.putText(out, piece_square, (cx + 9, cy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return out


def add_label(image_bgr: np.ndarray, label: str) -> np.ndarray:
    out = image_bgr.copy()
    cv2.rectangle(out, (0, 0), (min(out.shape[1], 300), 34), (0, 0, 0), -1)
    cv2.putText(out, label, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1)
    return out


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    reference_path = args.reference_image.expanduser().resolve()
    reference_bgr = read_reference_image(reference_path)
    height, width = reference_bgr.shape[:2]

    overrides: dict[str, Any] = {
        "width": int(width),
        "height": int(height),
        "color_mode": ColorMode.BGR,
        "reference_image_path": reference_path,
    }
    if args.piece_square is not None:
        overrides["piece_square"] = str(args.piece_square)

    camera_cfg = make_sim_camera_config_from_profile(str(args.profile), **overrides)
    camera = SimCamera(camera_cfg)
    gripper_percent = float(np.clip(float(args.gripper_percent), 0.0, 100.0))

    try:
        camera.connect(warmup=False)
        camera.set_robot_state({"gripper": gripper_percent})
        synthetic_bgr = camera.read(ColorMode.BGR)
        metadata = camera.calibration_metadata()
    finally:
        if camera.is_connected:
            camera.disconnect()

    if synthetic_bgr.shape != reference_bgr.shape:
        raise AssertionError(f"Synthetic frame shape {synthetic_bgr.shape} does not match {reference_bgr.shape}")

    corners_xy = np.asarray(metadata["board_corners_xy"], dtype=float)
    corner_checks = assert_corners_valid(corners_xy, width, height)
    file_idx, rank_idx, piece_center = square_center_xy(corners_xy, str(camera_cfg.piece_square))

    reference_annotated = annotate_reference_geometry(reference_bgr, corners_xy, str(camera_cfg.piece_square))
    synthetic_annotated = annotate_reference_geometry(synthetic_bgr, corners_xy, str(camera_cfg.piece_square))
    side_by_side = np.hstack(
        [
            add_label(reference_annotated, "real reference"),
            add_label(synthetic_annotated, "synthetic SimCamera"),
        ]
    )
    alpha = float(np.clip(float(args.overlay_alpha), 0.0, 1.0))
    overlay = cv2.addWeighted(reference_bgr, alpha, synthetic_bgr, 1.0 - alpha, 0.0)
    abs_delta = np.abs(reference_bgr.astype(np.int16) - synthetic_bgr.astype(np.int16)).astype(np.uint8)
    heatmap = cv2.applyColorMap(np.clip(abs_delta.mean(axis=2) * 2.0, 0, 255).astype(np.uint8), cv2.COLORMAP_TURBO)

    paths = {
        "reference_annotated_path": output_dir / "reference_annotated.jpg",
        "synthetic_path": output_dir / "synthetic.jpg",
        "synthetic_annotated_path": output_dir / "synthetic_annotated.jpg",
        "side_by_side_path": output_dir / "side_by_side.jpg",
        "overlay_path": output_dir / "overlay.jpg",
        "absolute_difference_path": output_dir / "absolute_difference_heatmap.jpg",
        "summary_path": output_dir / "summary.json",
    }
    write_image(paths["reference_annotated_path"], reference_annotated)
    write_image(paths["synthetic_path"], synthetic_bgr)
    write_image(paths["synthetic_annotated_path"], synthetic_annotated)
    write_image(paths["side_by_side_path"], side_by_side)
    write_image(paths["overlay_path"], overlay)
    write_image(paths["absolute_difference_path"], heatmap)

    delta = reference_bgr.astype(np.float32) - synthetic_bgr.astype(np.float32)
    summary = {
        "ok": True,
        "scenario": "sim_real_reference_comparison",
        "profile": str(args.profile),
        "profile_values": jsonable(SIM_CAMERA_CALIBRATION_PROFILES[str(args.profile)]),
        "reference_image_path": str(reference_path),
        "output_dir": str(output_dir),
        "overlay_alpha": alpha,
        "artifacts": {name: str(path) for name, path in paths.items()},
        "image": {
            "reference": image_stats(reference_bgr),
            "synthetic": image_stats(synthetic_bgr),
            "absolute_difference": image_stats(abs_delta),
            "mean_abs_delta_bgr": [float(value) for value in np.abs(delta).mean(axis=(0, 1))],
            "rmse_bgr": [float(value) for value in np.sqrt(np.mean(delta * delta, axis=(0, 1)))],
            "mean_abs_delta": float(np.abs(delta).mean()),
            "rmse": float(np.sqrt(np.mean(delta * delta))),
        },
        "board": {
            "corner_labels": list(CORNER_LABELS),
            "corners_xy": [[float(x), float(y)] for x, y in corners_xy.tolist()],
            "corner_checks": corner_checks,
        },
        "piece_square": {
            "square": str(camera_cfg.piece_square),
            "file_idx": int(file_idx),
            "rank_idx": int(rank_idx),
            "center_image_xy": [float(value) for value in piece_center],
        },
        "gripper": {
            "requested_percent": gripper_percent,
            "visible": bool(metadata["gripper_visible"]),
            "track_robot_gripper": bool(metadata["track_robot_gripper"]),
            "tracked_gripper_percent": metadata["tracked_gripper_percent"],
            "current_gripper_opening_px": metadata["current_gripper_opening_px"],
        },
        "camera_metadata": metadata,
        "notes": [
            "This smoke compares a metadata-aligned synthetic render against the saved real reference; it does not perform image registration or real corner detection.",
            "The current profile stores hand-picked board corners and the expected single pawn square for archive/chess_test_images/current_view.jpg.",
        ],
    }
    paths["summary_path"].write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
