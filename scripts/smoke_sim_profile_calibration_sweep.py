#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import json
import math
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

from lerobot.cameras.configs import ColorMode
from lerobot.sim import (
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    SimCamera,
    make_sim_camera_config_from_profile,
)
import lerobot.sim.camera as sim_camera_module

CORNER_LABELS = ("a1", "h1", "h8", "a8")
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "profile_calibration_sweep"
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"


@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    overrides: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a small explicit perturbation sweep for a SimCamera calibration profile "
            "against the saved real gripper-camera reference."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for candidate frames, montage, overlays, diffs, and summary JSON.",
    )
    parser.add_argument(
        "--reference-image",
        type=Path,
        default=DEFAULT_REFERENCE_IMAGE,
        help="Real gripper-camera reference image used for shape and image-delta scoring.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
    )
    parser.add_argument(
        "--piece-square",
        default=None,
        help="Override the base profile's synthetic piece square.",
    )
    parser.add_argument("--gripper-percent", type=float, default=80.0)
    parser.add_argument(
        "--gripper-finger-width-px",
        type=int,
        default=None,
        help=(
            "Override the base gripper finger width for this sweep. This is useful for "
            "deterministic before/after checks without changing the selected profile."
        ),
    )
    parser.add_argument(
        "--marker-time-seconds",
        type=float,
        default=0.0,
        help=(
            "Fixed timestamp used by SimCamera marker rendering while scoring candidates. "
            "Keeping this fixed makes image-delta rankings deterministic."
        ),
    )
    parser.add_argument("--overlay-alpha", type=float, default=0.50)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional candidate limit for quick local checks. Zero renders the full sweep.",
    )
    return parser.parse_args()


def read_reference_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError(f"cv2 failed to read reference image {path}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise AssertionError(f"Expected BGR reference image, got shape {image.shape}")
    return image


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise AssertionError(f"cv2 failed to write {path}")


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


@contextlib.contextmanager
def fixed_sim_camera_marker_time(marker_time_seconds: float):
    original_time = sim_camera_module.time.time
    sim_camera_module.time.time = lambda: float(marker_time_seconds)
    try:
        yield
    finally:
        sim_camera_module.time.time = original_time


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


def square_center_xy(corners_xy: np.ndarray, square: str) -> np.ndarray:
    file_idx, rank_idx = square_to_file_rank(square)
    return board_point(corners_xy, (file_idx + 0.5) / 8.0, (rank_idx + 0.5) / 8.0)


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


def shifted_corners(corners: np.ndarray, dx: float = 0.0, dy: float = 0.0) -> list[list[float]]:
    return (corners + np.array([dx, dy], dtype=float)).tolist()


def scaled_corners(corners: np.ndarray, scale: float) -> list[list[float]]:
    center = corners.mean(axis=0)
    return (center + (corners - center) * scale).tolist()


def adjusted_corners(corners: np.ndarray, offsets: list[tuple[float, float]]) -> list[list[float]]:
    return (corners + np.asarray(offsets, dtype=float)).tolist()


def build_candidates(profile_values: dict[str, Any], piece_square_override: str | None) -> list[Candidate]:
    corners = np.asarray(profile_values["board_corners_xy"], dtype=float)
    base_piece_square = piece_square_override or str(profile_values.get("piece_square", "e4"))
    gripper_center = int(profile_values.get("gripper_center_x_px") or 320)
    gripper_y = int(profile_values.get("gripper_y_px") or 374)
    gripper_opening = int(profile_values.get("gripper_opening_px") or 56)
    finger_width = int(profile_values.get("gripper_finger_width_px") or 72)

    candidates = [
        Candidate("current", "Unmodified named profile.", {}),
        Candidate(
            "board_up_8px",
            "Shift all board corners 8 px up.",
            {"board_corners_xy": shifted_corners(corners, dy=-8)},
        ),
        Candidate(
            "board_down_8px",
            "Shift all board corners 8 px down.",
            {"board_corners_xy": shifted_corners(corners, dy=8)},
        ),
        Candidate(
            "board_left_8px",
            "Shift all board corners 8 px left.",
            {"board_corners_xy": shifted_corners(corners, dx=-8)},
        ),
        Candidate(
            "board_right_8px",
            "Shift all board corners 8 px right.",
            {"board_corners_xy": shifted_corners(corners, dx=8)},
        ),
        Candidate(
            "board_expand_3pct",
            "Scale board corners 3 percent away from their center.",
            {"board_corners_xy": scaled_corners(corners, 1.03)},
        ),
        Candidate(
            "board_contract_3pct",
            "Scale board corners 3 percent toward their center.",
            {"board_corners_xy": scaled_corners(corners, 0.97)},
        ),
        Candidate(
            "board_top_up_10px",
            "Move h8/a8 10 px up while keeping the bottom edge fixed.",
            {"board_corners_xy": adjusted_corners(corners, [(0, 0), (0, 0), (0, -10), (0, -10)])},
        ),
        Candidate(
            "board_bottom_down_10px",
            "Move a1/h1 10 px down while keeping the top edge fixed.",
            {"board_corners_xy": adjusted_corners(corners, [(0, 10), (0, 10), (0, 0), (0, 0)])},
        ),
        Candidate(
            "gripper_left_12px",
            "Move the rendered gripper center 12 px left.",
            {"gripper_center_x_px": gripper_center - 12},
        ),
        Candidate(
            "gripper_right_12px",
            "Move the rendered gripper center 12 px right.",
            {"gripper_center_x_px": gripper_center + 12},
        ),
        Candidate(
            "gripper_up_12px",
            "Move the rendered gripper base 12 px up.",
            {"gripper_y_px": gripper_y - 12},
        ),
        Candidate(
            "gripper_down_12px",
            "Move the rendered gripper base 12 px down.",
            {"gripper_y_px": gripper_y + 12},
        ),
        Candidate(
            "gripper_narrow_10px",
            "Reduce the nominal gripper opening by 10 px.",
            {"gripper_opening_px": max(10, gripper_opening - 10)},
        ),
        Candidate(
            "gripper_wide_10px",
            "Increase the nominal gripper opening by 10 px.",
            {"gripper_opening_px": gripper_opening + 10},
        ),
        Candidate(
            "fingers_narrow_8px",
            "Reduce each rendered finger width by 8 px.",
            {"gripper_finger_width_px": max(12, finger_width - 8)},
        ),
        Candidate(
            "fingers_wide_8px",
            "Increase each rendered finger width by 8 px.",
            {"gripper_finger_width_px": finger_width + 8},
        ),
    ]

    if base_piece_square != "e4":
        candidates.append(
            Candidate(
                f"piece_{base_piece_square}",
                f"Use the requested base piece square {base_piece_square}.",
                {"piece_square": base_piece_square},
            )
        )
    for square in ("d4", "e3", "e5", "f4"):
        if square != base_piece_square:
            candidates.append(
                Candidate(
                    f"piece_{square}",
                    f"Move the single synthetic piece to {square}.",
                    {"piece_square": square},
                )
            )
    return candidates


def add_label(image_bgr: np.ndarray, lines: list[str], *, height_px: int = 58) -> np.ndarray:
    out = image_bgr.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], min(out.shape[0], height_px)), (0, 0, 0), -1)
    for idx, line in enumerate(lines[:3]):
        y = 20 + idx * 17
        cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (255, 255, 255), 1)
    return out


def annotate_geometry(
    image_bgr: np.ndarray,
    corners_xy: np.ndarray,
    piece_square: str,
    title_lines: list[str],
) -> np.ndarray:
    out = image_bgr.copy()
    pts = np.round(corners_xy).astype(int)
    cv2.polylines(out, [pts], isClosed=True, color=(0, 210, 255), thickness=2)
    for label, pt in zip(CORNER_LABELS, pts, strict=True):
        xy = tuple(int(value) for value in pt)
        cv2.circle(out, xy, 6, (0, 0, 255), -1)
        cv2.putText(out, label, (xy[0] + 7, xy[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (0, 0, 0), 3)
        cv2.putText(out, label, (xy[0] + 7, xy[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1)

    e4_center = square_center_xy(corners_xy, "e4")
    e4_xy = (int(round(e4_center[0])), int(round(e4_center[1])))
    cv2.drawMarker(out, e4_xy, (0, 255, 0), markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)
    cv2.putText(out, "e4", (e4_xy[0] + 8, e4_xy[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3)
    cv2.putText(out, "e4", (e4_xy[0] + 8, e4_xy[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)

    if piece_square != "e4":
        piece_center = square_center_xy(corners_xy, piece_square)
        piece_xy = (int(round(piece_center[0])), int(round(piece_center[1])))
        cv2.drawMarker(
            out,
            piece_xy,
            (255, 0, 255),
            markerType=cv2.MARKER_TILTED_CROSS,
            markerSize=18,
            thickness=2,
        )
        cv2.putText(
            out,
            piece_square,
            (piece_xy[0] + 8, piece_xy[1] + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 0, 0),
            3,
        )
        cv2.putText(
            out,
            piece_square,
            (piece_xy[0] + 8, piece_xy[1] + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255),
            1,
        )
    return add_label(out, title_lines)


def make_diff_heatmap(reference_bgr: np.ndarray, candidate_bgr: np.ndarray) -> np.ndarray:
    abs_delta = np.abs(reference_bgr.astype(np.int16) - candidate_bgr.astype(np.int16)).astype(np.uint8)
    heatmap = np.clip(abs_delta.mean(axis=2) * 2.0, 0, 255).astype(np.uint8)
    return cv2.applyColorMap(heatmap, cv2.COLORMAP_TURBO)


def score_candidate(reference_bgr: np.ndarray, candidate_bgr: np.ndarray) -> dict[str, Any]:
    delta = reference_bgr.astype(np.float32) - candidate_bgr.astype(np.float32)
    abs_delta = np.abs(delta)
    return {
        "mean_abs_delta": float(abs_delta.mean()),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "mean_abs_delta_bgr": [float(value) for value in abs_delta.mean(axis=(0, 1))],
        "rmse_bgr": [float(value) for value in np.sqrt(np.mean(delta * delta, axis=(0, 1)))],
    }


def render_candidate(
    *,
    profile_name: str,
    base_overrides: dict[str, Any],
    candidate: Candidate,
    reference_bgr: np.ndarray,
    gripper_percent: float,
    candidate_dir: Path,
    marker_time_seconds: float,
) -> dict[str, Any]:
    overrides = {**base_overrides, **candidate.overrides}
    camera_cfg = make_sim_camera_config_from_profile(profile_name, **overrides)
    camera = SimCamera(camera_cfg)
    try:
        camera.connect(warmup=False)
        camera.set_robot_state({"gripper": gripper_percent})
        with fixed_sim_camera_marker_time(marker_time_seconds):
            frame_bgr = camera.read(ColorMode.BGR)
        metadata = camera.calibration_metadata()
    finally:
        if camera.is_connected:
            camera.disconnect()

    if frame_bgr.shape != reference_bgr.shape:
        raise AssertionError(
            f"{candidate.name} frame shape {frame_bgr.shape} does not match {reference_bgr.shape}"
        )

    height, width = frame_bgr.shape[:2]
    corners_xy = np.asarray(metadata["board_corners_xy"], dtype=float)
    corner_checks = assert_corners_valid(corners_xy, width, height)
    piece_square = str(camera_cfg.piece_square)
    e4_center = square_center_xy(corners_xy, "e4")
    piece_center = square_center_xy(corners_xy, piece_square)
    metrics = score_candidate(reference_bgr, frame_bgr)

    frame_path = candidate_dir / f"{candidate.name}.jpg"
    annotated_path = candidate_dir / f"{candidate.name}_annotated.jpg"
    title_lines = [
        candidate.name,
        f"MAD {metrics['mean_abs_delta']:.2f} RMSE {metrics['rmse']:.2f}",
        candidate.description,
    ]
    annotated = annotate_geometry(frame_bgr, corners_xy, piece_square, title_lines)
    write_image(frame_path, frame_bgr)
    write_image(annotated_path, annotated)

    return {
        "name": candidate.name,
        "description": candidate.description,
        "overrides": jsonable(candidate.overrides),
        "frame_path": str(frame_path),
        "annotated_path": str(annotated_path),
        "metrics": metrics,
        "board": {
            "corner_labels": list(CORNER_LABELS),
            "corners_xy": [[float(x), float(y)] for x, y in corners_xy.tolist()],
            "corner_checks": corner_checks,
            "e4_center_image_xy": [float(value) for value in e4_center],
        },
        "piece_square": {
            "square": piece_square,
            "center_image_xy": [float(value) for value in piece_center],
        },
        "gripper": {
            "requested_percent": gripper_percent,
            "visible": bool(metadata["gripper_visible"]),
            "track_robot_gripper": bool(metadata["track_robot_gripper"]),
            "tracked_gripper_percent": metadata["tracked_gripper_percent"],
            "current_gripper_opening_px": metadata["current_gripper_opening_px"],
            "center_x_px": camera_cfg.gripper_center_x_px,
            "y_px": camera_cfg.gripper_y_px,
            "opening_px": camera_cfg.gripper_opening_px,
            "finger_width_px": camera_cfg.gripper_finger_width_px,
            "length_px": camera_cfg.gripper_length_px,
        },
        "camera_metadata": metadata,
    }


def load_image(path: str) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError(f"cv2 failed to read generated image {path}")
    return image


def make_montage(candidate_summaries: list[dict[str, Any]], output_path: Path) -> None:
    images = [load_image(summary["annotated_path"]) for summary in candidate_summaries]
    if not images:
        raise AssertionError("No candidate images were rendered.")
    tile_h, tile_w = images[0].shape[:2]
    cols = min(4, len(images))
    rows = int(math.ceil(len(images) / cols))
    montage = np.zeros((rows * tile_h, cols * tile_w, 3), dtype=np.uint8)
    montage[:, :] = np.array([18, 18, 18], dtype=np.uint8)
    for idx, image in enumerate(images):
        row, col = divmod(idx, cols)
        montage[row * tile_h : (row + 1) * tile_h, col * tile_w : (col + 1) * tile_w] = image
    write_image(output_path, montage)


def write_overlay_set(
    *,
    reference_bgr: np.ndarray,
    candidate_summary: dict[str, Any],
    output_dir: Path,
    label: str,
    overlay_alpha: float,
) -> dict[str, str]:
    frame = load_image(candidate_summary["frame_path"])
    overlay = cv2.addWeighted(reference_bgr, overlay_alpha, frame, 1.0 - overlay_alpha, 0.0)
    diff = make_diff_heatmap(reference_bgr, frame)
    overlay_path = output_dir / f"{label}_overlay.jpg"
    diff_path = output_dir / f"{label}_absolute_difference_heatmap.jpg"
    side_by_side_path = output_dir / f"{label}_side_by_side.jpg"
    annotated = load_image(candidate_summary["annotated_path"])
    reference_labeled = add_label(reference_bgr, ["real reference"])
    side_by_side = np.hstack([reference_labeled, annotated])
    write_image(overlay_path, overlay)
    write_image(diff_path, diff)
    write_image(side_by_side_path, side_by_side)
    return {
        f"{label}_overlay_path": str(overlay_path),
        f"{label}_absolute_difference_path": str(diff_path),
        f"{label}_side_by_side_path": str(side_by_side_path),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    candidate_dir = output_dir / "candidates"
    reference_path = args.reference_image.expanduser().resolve()
    reference_bgr = read_reference_image(reference_path)
    height, width = reference_bgr.shape[:2]
    profile_values = SIM_CAMERA_CALIBRATION_PROFILES[str(args.profile)]
    effective_profile_values = dict(profile_values)
    gripper_percent = float(np.clip(float(args.gripper_percent), 0.0, 100.0))
    if args.gripper_finger_width_px is not None:
        if args.gripper_finger_width_px <= 0:
            raise AssertionError("--gripper-finger-width-px must be positive.")
        effective_profile_values["gripper_finger_width_px"] = int(args.gripper_finger_width_px)
    overlay_alpha = float(np.clip(float(args.overlay_alpha), 0.0, 1.0))
    marker_time_seconds = float(args.marker_time_seconds)

    base_overrides: dict[str, Any] = {
        "width": int(width),
        "height": int(height),
        "color_mode": ColorMode.BGR,
        "reference_image_path": reference_path,
    }
    if args.gripper_finger_width_px is not None:
        base_overrides["gripper_finger_width_px"] = int(args.gripper_finger_width_px)
    if args.piece_square is not None:
        base_overrides["piece_square"] = str(args.piece_square)

    candidates = build_candidates(effective_profile_values, args.piece_square)
    if args.limit and args.limit > 0:
        candidates = candidates[: int(args.limit)]

    candidate_summaries = [
        render_candidate(
            profile_name=str(args.profile),
            base_overrides=base_overrides,
            candidate=candidate,
            reference_bgr=reference_bgr,
            gripper_percent=gripper_percent,
            candidate_dir=candidate_dir,
            marker_time_seconds=marker_time_seconds,
        )
        for candidate in candidates
    ]

    best = min(candidate_summaries, key=lambda summary: float(summary["metrics"]["mean_abs_delta"]))
    current = next(summary for summary in candidate_summaries if summary["name"] == "current")
    output_dir.mkdir(parents=True, exist_ok=True)
    montage_path = output_dir / "candidate_montage.jpg"
    summary_path = output_dir / "summary.json"
    make_montage(candidate_summaries, montage_path)

    artifacts = {
        "summary_path": str(summary_path),
        "candidate_montage_path": str(montage_path),
        "candidate_dir": str(candidate_dir),
    }
    artifacts.update(
        write_overlay_set(
            reference_bgr=reference_bgr,
            candidate_summary=current,
            output_dir=output_dir,
            label="current",
            overlay_alpha=overlay_alpha,
        )
    )
    artifacts.update(
        write_overlay_set(
            reference_bgr=reference_bgr,
            candidate_summary=best,
            output_dir=output_dir,
            label="best",
            overlay_alpha=overlay_alpha,
        )
    )

    summary = {
        "ok": True,
        "scenario": "sim_profile_calibration_sweep",
        "profile": str(args.profile),
        "profile_values": jsonable(profile_values),
        "effective_profile_values": jsonable(effective_profile_values),
        "reference_image_path": str(reference_path),
        "output_dir": str(output_dir),
        "gripper_percent": gripper_percent,
        "marker_time_seconds": marker_time_seconds,
        "overlay_alpha": overlay_alpha,
        "image": {
            "reference": image_stats(reference_bgr),
            "candidate_count": len(candidate_summaries),
        },
        "selection": {
            "best_by": "mean_abs_delta_full_frame",
            "best_candidate": best["name"],
            "best_mean_abs_delta": best["metrics"]["mean_abs_delta"],
            "current_mean_abs_delta": current["metrics"]["mean_abs_delta"],
            "delta_vs_current": best["metrics"]["mean_abs_delta"] - current["metrics"]["mean_abs_delta"],
            "caveat": (
                "Full-frame image delta is a coarse triage metric because the synthetic renderer is not "
                "photorealistic and this script does not detect real board corners."
            ),
        },
        "artifacts": artifacts,
        "candidates": candidate_summaries,
        "notes": [
            (
                "This script renders explicit metadata perturbations only; it does not rewrite the "
                "canonical profile."
            ),
            "Use the montage and per-candidate metadata to choose the next manual calibration direction.",
            (
                "A detection-assisted real-reference corner picker is the natural follow-up if these "
                "candidates are insufficient."
            ),
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
