#!/usr/bin/env python3

from __future__ import annotations

import argparse
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

from lerobot.sim import CURRENT_GRIPPER_REFERENCE_PROFILE, SIM_CAMERA_CALIBRATION_PROFILES

CORNER_LABELS = ("a1", "h1", "h8", "a8")
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_reference_corner_probe"
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
FULL_BOARD_INTERNAL_PATTERN = (7, 7)
PATTERN_CANDIDATES = (
    FULL_BOARD_INTERNAL_PATTERN,
    (6, 7),
    (7, 6),
    (6, 6),
    (8, 8),
)


@dataclass(frozen=True)
class DetectionAttempt:
    method: str
    pattern_size: tuple[int, int]
    variant: str
    found: bool
    corners: np.ndarray | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe archive/chess_test_images/current_view.jpg for real chessboard internal corners "
            "and compare detected board geometry with the current SimCamera profile metadata."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for annotated overlays, preprocessing debug images, and summary JSON.",
    )
    parser.add_argument(
        "--reference-image",
        type=Path,
        default=DEFAULT_REFERENCE_IMAGE,
        help="Saved real gripper-camera reference image.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
        help="Calibration profile whose board_corners_xy metadata should be compared.",
    )
    return parser.parse_args()


def read_reference_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError(f"cv2 failed to read reference image {path}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise AssertionError(f"Expected BGR reference image, got shape {image.shape}")
    return image


def write_image(path: Path, image_bgr_or_gray: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr_or_gray)
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


def polygon_area_xy(points_xy: np.ndarray) -> float:
    x = points_xy[:, 0]
    y = points_xy[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


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
    }


def preprocessing_variants(image_bgr: np.ndarray) -> dict[str, np.ndarray]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return {
        "gray": gray,
        "equalized": cv2.equalizeHist(gray),
        "clahe": clahe,
        "gaussian_blur": cv2.GaussianBlur(gray, (5, 5), 0),
        "otsu_binary": cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        "otsu_binary_inv": cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
        "adaptive_mean": cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        ),
        "adaptive_gaussian": cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        ),
        "canny_edges": cv2.Canny(clahe, 60, 160),
    }


def find_classic_corners(variant: np.ndarray, pattern_size: tuple[int, int]) -> tuple[bool, np.ndarray | None]:
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FILTER_QUADS
    found, corners = cv2.findChessboardCorners(variant, pattern_size, flags)
    if not found or corners is None:
        return False, None

    refined = cv2.cornerSubPix(
        variant,
        corners,
        winSize=(7, 7),
        zeroZone=(-1, -1),
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.001),
    )
    return True, refined


def find_sector_based_corners(variant: np.ndarray, pattern_size: tuple[int, int]) -> tuple[bool, np.ndarray | None]:
    if not hasattr(cv2, "findChessboardCornersSB"):
        return False, None
    flags = cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
    found, corners = cv2.findChessboardCornersSB(variant, pattern_size, flags)
    if not found or corners is None:
        return False, None
    return True, corners


def run_detection_attempts(variants: dict[str, np.ndarray]) -> list[DetectionAttempt]:
    attempts: list[DetectionAttempt] = []
    finders = (
        ("classic", find_classic_corners),
        ("sector_based", find_sector_based_corners),
    )
    for pattern_size in PATTERN_CANDIDATES:
        for variant_name, variant in variants.items():
            if variant_name == "canny_edges":
                continue
            for method_name, finder in finders:
                found, corners = finder(variant, pattern_size)
                attempts.append(
                    DetectionAttempt(
                        method=method_name,
                        pattern_size=pattern_size,
                        variant=variant_name,
                        found=found,
                        corners=corners,
                    )
                )
    return attempts


def attempt_priority(attempt: DetectionAttempt, variant_order: dict[str, int]) -> tuple[int, int, int]:
    pattern_priority = 0 if attempt.pattern_size == FULL_BOARD_INTERNAL_PATTERN else 1
    method_priority = 0 if attempt.method == "sector_based" else 1
    return pattern_priority, method_priority, variant_order[attempt.variant]


def select_detection(attempts: list[DetectionAttempt], variants: dict[str, np.ndarray]) -> DetectionAttempt | None:
    variant_order = {name: idx for idx, name in enumerate(variants)}
    successes = [attempt for attempt in attempts if attempt.found and attempt.corners is not None]
    if not successes:
        return None
    return min(successes, key=lambda attempt: attempt_priority(attempt, variant_order))


def estimate_outer_corners_from_grid(corners: np.ndarray, pattern_size: tuple[int, int]) -> np.ndarray:
    cols, rows = pattern_size
    grid = corners.reshape(rows, cols, 2)

    row_top_left = grid[1, 0] - grid[0, 0]
    row_top_right = grid[1, -1] - grid[0, -1]
    row_bottom_left = grid[-1, 0] - grid[-2, 0]
    row_bottom_right = grid[-1, -1] - grid[-2, -1]
    col_top_left = grid[0, 1] - grid[0, 0]
    col_top_right = grid[0, -1] - grid[0, -2]
    col_bottom_left = grid[-1, 1] - grid[-1, 0]
    col_bottom_right = grid[-1, -1] - grid[-1, -2]

    top_left = grid[0, 0] - row_top_left - col_top_left
    top_right = grid[0, -1] - row_top_right + col_top_right
    bottom_left = grid[-1, 0] + row_bottom_left - col_bottom_left
    bottom_right = grid[-1, -1] + row_bottom_right + col_bottom_right
    return np.asarray([bottom_left, bottom_right, top_right, top_left], dtype=float)


def oriented_outer_corner_candidates(corners: np.ndarray, pattern_size: tuple[int, int]) -> dict[str, np.ndarray]:
    cols, rows = pattern_size
    grid = corners.reshape(rows, cols, 2)
    orientations = {
        "opencv_order": grid,
        "flip_rows": np.flip(grid, axis=0),
        "flip_cols": np.flip(grid, axis=1),
        "flip_rows_and_cols": np.flip(np.flip(grid, axis=0), axis=1),
    }
    return {
        name: estimate_outer_corners_from_grid(oriented.reshape(-1, 1, 2), pattern_size)
        for name, oriented in orientations.items()
    }


def select_profile_aligned_corners(
    detected_corners: np.ndarray,
    pattern_size: tuple[int, int],
    profile_corners: np.ndarray,
) -> tuple[str, np.ndarray, list[dict[str, Any]]]:
    candidates = oriented_outer_corner_candidates(detected_corners, pattern_size)
    scored = []
    for orientation, corners_xy in candidates.items():
        deltas = corners_xy - profile_corners
        distances = np.linalg.norm(deltas, axis=1)
        scored.append(
            {
                "orientation": orientation,
                "mean_l2_px": float(distances.mean()),
                "max_l2_px": float(distances.max()),
            }
        )
    best = min(scored, key=lambda item: item["mean_l2_px"])
    return str(best["orientation"]), candidates[str(best["orientation"])], scored


def draw_labeled_polygon(
    image_bgr: np.ndarray,
    corners_xy: np.ndarray,
    *,
    color: tuple[int, int, int],
    labels: tuple[str, ...],
    prefix: str = "",
) -> None:
    pts = np.round(corners_xy).astype(int)
    cv2.polylines(image_bgr, [pts], isClosed=True, color=color, thickness=2)
    for label, pt in zip(labels, pts, strict=True):
        xy = tuple(int(value) for value in pt)
        cv2.circle(image_bgr, xy, 5, color, -1)
        text = f"{prefix}{label}"
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        text_x = int(np.clip(xy[0] + 6, 4, max(4, image_bgr.shape[1] - text_size[0] - 4)))
        text_y = int(np.clip(xy[1] - 6, text_size[1] + 4, max(text_size[1] + 4, image_bgr.shape[0] - 4)))
        cv2.putText(image_bgr, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
        cv2.putText(image_bgr, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)


def add_label(image_bgr: np.ndarray, lines: list[str], *, height_px: int = 58) -> np.ndarray:
    out = image_bgr.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], min(out.shape[0], height_px)), (0, 0, 0), -1)
    for idx, line in enumerate(lines[:3]):
        y = 20 + idx * 17
        cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (255, 255, 255), 1)
    return out


def make_profile_overlay(reference_bgr: np.ndarray, profile_corners: np.ndarray) -> np.ndarray:
    out = reference_bgr.copy()
    draw_labeled_polygon(out, profile_corners, color=(0, 210, 255), labels=CORNER_LABELS, prefix="profile ")
    return add_label(out, ["profile board_corners_xy overlay", "cyan: current metadata"])


def make_detection_overlay(
    reference_bgr: np.ndarray,
    profile_corners: np.ndarray,
    detected_corners: np.ndarray,
) -> np.ndarray:
    out = reference_bgr.copy()
    draw_labeled_polygon(out, profile_corners, color=(0, 210, 255), labels=CORNER_LABELS, prefix="profile ")
    draw_labeled_polygon(out, detected_corners, color=(255, 0, 255), labels=CORNER_LABELS, prefix="detected ")
    for profile_pt, detected_pt in zip(profile_corners, detected_corners, strict=True):
        cv2.line(
            out,
            tuple(int(round(value)) for value in profile_pt),
            tuple(int(round(value)) for value in detected_pt),
            (255, 255, 255),
            1,
        )
    return add_label(out, ["detected vs profile board corners", "cyan: profile, magenta: detected"])


def make_internal_corner_overlay(
    reference_bgr: np.ndarray,
    attempt: DetectionAttempt,
) -> np.ndarray:
    out = reference_bgr.copy()
    corners = attempt.corners
    if corners is None:
        raise AssertionError("Cannot draw internal corners for a failed detection attempt.")
    cv2.drawChessboardCorners(out, attempt.pattern_size, corners, True)
    return add_label(out, [f"{attempt.method} {attempt.pattern_size} on {attempt.variant}", "detected internal corners"])


def summarize_attempt(attempt: DetectionAttempt) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "method": attempt.method,
        "pattern_size": [int(value) for value in attempt.pattern_size],
        "variant": attempt.variant,
        "found": bool(attempt.found),
    }
    if attempt.found and attempt.corners is not None:
        corners_xy = attempt.corners.reshape(-1, 2)
        summary["corner_count"] = int(len(corners_xy))
        summary["corner_bounds_xy"] = {
            "min": [float(value) for value in corners_xy.min(axis=0)],
            "max": [float(value) for value in corners_xy.max(axis=0)],
        }
    return summary


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    reference_path = args.reference_image.expanduser().resolve()
    reference_bgr = read_reference_image(reference_path)
    profile_values = SIM_CAMERA_CALIBRATION_PROFILES[str(args.profile)]
    profile_corners = np.asarray(profile_values["board_corners_xy"], dtype=float)
    variants = preprocessing_variants(reference_bgr)

    preprocessed_dir = output_dir / "preprocessed"
    artifacts: dict[str, str] = {
        "summary_path": str(output_dir / "summary.json"),
        "profile_overlay_path": str(output_dir / "profile_overlay.jpg"),
        "preprocessed_dir": str(preprocessed_dir),
    }
    for variant_name, variant in variants.items():
        path = preprocessed_dir / f"{variant_name}.jpg"
        write_image(path, variant)

    profile_overlay = make_profile_overlay(reference_bgr, profile_corners)
    write_image(Path(artifacts["profile_overlay_path"]), profile_overlay)

    attempts = run_detection_attempts(variants)
    selected = select_detection(attempts, variants)
    detection_summary: dict[str, Any] = {
        "found": selected is not None,
        "attempt_count": len(attempts),
        "success_count": sum(1 for attempt in attempts if attempt.found),
        "attempts": [summarize_attempt(attempt) for attempt in attempts],
    }

    geometry_summary: dict[str, Any] | None = None
    notes = [
        "Classic OpenCV chessboard detection and sector-based detection are both attempted with deterministic preprocessing variants.",
        "Only a detected 7x7 internal-corner grid is treated as full 8x8-board geometry evidence.",
    ]

    if selected is not None:
        internal_overlay_path = output_dir / "detected_internal_corners.jpg"
        write_image(internal_overlay_path, make_internal_corner_overlay(reference_bgr, selected))
        artifacts["detected_internal_corners_path"] = str(internal_overlay_path)
        detection_summary["selected_attempt"] = summarize_attempt(selected)

        if selected.pattern_size == FULL_BOARD_INTERNAL_PATTERN and selected.corners is not None:
            orientation, detected_outer_corners, orientation_scores = select_profile_aligned_corners(
                selected.corners,
                selected.pattern_size,
                profile_corners,
            )
            deltas = detected_outer_corners - profile_corners
            distances = np.linalg.norm(deltas, axis=1)
            height, width = reference_bgr.shape[:2]
            in_bounds_x = np.logical_and(detected_outer_corners[:, 0] >= 0.0, detected_outer_corners[:, 0] < width)
            in_bounds_y = np.logical_and(detected_outer_corners[:, 1] >= 0.0, detected_outer_corners[:, 1] < height)
            detected_outer_in_bounds = bool(np.all(in_bounds_x & in_bounds_y))
            max_distance = float(distances.max())
            detected_overlay_path = output_dir / "detected_vs_profile_overlay.jpg"
            write_image(
                detected_overlay_path,
                make_detection_overlay(reference_bgr, profile_corners, detected_outer_corners),
            )
            artifacts["detected_vs_profile_overlay_path"] = str(detected_overlay_path)
            geometry_summary = {
                "corner_labels": list(CORNER_LABELS),
                "profile_corners_xy": [[float(x), float(y)] for x, y in profile_corners.tolist()],
                "detected_outer_corners_xy": [
                    [float(x), float(y)] for x, y in detected_outer_corners.tolist()
                ],
                "selected_orientation": orientation,
                "orientation_scores": orientation_scores,
                "corner_deltas_xy": [
                    {
                        "label": label,
                        "dx_px": float(delta[0]),
                        "dy_px": float(delta[1]),
                        "l2_px": float(distance),
                    }
                    for label, delta, distance in zip(CORNER_LABELS, deltas, distances, strict=True)
                ],
                "mean_corner_l2_px": float(distances.mean()),
                "max_corner_l2_px": max_distance,
                "profile_area_px2": polygon_area_xy(profile_corners),
                "detected_area_px2": polygon_area_xy(detected_outer_corners),
                "area_delta_px2": polygon_area_xy(detected_outer_corners) - polygon_area_xy(profile_corners),
                "detected_outer_in_bounds": detected_outer_in_bounds,
                "direct_profile_override_recommended": bool(detected_outer_in_bounds and max_distance <= 40.0),
                "interpretation": (
                    "Detected grid geometry is plausible for evidence collection, but at least one extrapolated "
                    "outer corner is outside the image or too far from the current profile for an automatic "
                    "profile override."
                    if (not detected_outer_in_bounds or max_distance > 40.0)
                    else "Detected grid geometry is close enough to consider as a profile override candidate."
                ),
                "next_action": (
                    "Inspect the detected-vs-profile overlay, then use a manual corner picker/profile generator "
                    "before changing canonical calibration metadata."
                    if (not detected_outer_in_bounds or max_distance > 40.0)
                    else "Review the overlay before promoting detected corners into an explicit calibration override."
                ),
            }
            notes.append(
                "Detected outer corners are extrapolated one square beyond the 7x7 internal grid and orientation-aligned to the profile for delta reporting."
            )
        else:
            geometry_summary = {
                "available": False,
                "reason": (
                    f"Selected detection pattern {selected.pattern_size} is not the full "
                    f"{FULL_BOARD_INTERNAL_PATTERN} internal grid required to estimate 8x8 board corners."
                ),
            }
            notes.append("A detection succeeded, but not for the full 7x7 internal grid needed for profile comparison.")
    else:
        detection_summary["failure_reason"] = (
            "No OpenCV chessboard/internal-corner detector succeeded for the bounded pattern and preprocessing set."
        )
        geometry_summary = {
            "available": False,
            "reason": "No full-board internal-corner grid was detected.",
            "next_action": "Use the profile overlay and preprocessing artifacts to seed a manual corner picker/profile generator.",
        }
        notes.append("Automatic corner detection failed; manual corner picking is the next calibration path.")

    summary = {
        "ok": True,
        "scenario": "sim_real_reference_corner_probe",
        "profile": str(args.profile),
        "profile_values": jsonable(profile_values),
        "reference_image_path": str(reference_path),
        "output_dir": str(output_dir),
        "image": {
            "reference": image_stats(reference_bgr),
        },
        "detection": detection_summary,
        "geometry_comparison": geometry_summary,
        "artifacts": artifacts,
        "notes": notes,
    }

    summary_path = Path(artifacts["summary_path"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
