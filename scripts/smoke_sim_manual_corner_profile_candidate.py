#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
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
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "manual_corner_profile_candidate"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render and summarize a reviewable SimCamera profile override candidate from manually supplied "
            "real-reference board corners. Corner order is a1, h1, h8, a8 in image pixels. "
            "Corners can be supplied explicitly, loaded from JSON, replayed from click JSON, or picked "
            "interactively with OpenCV."
        )
    )
    source = parser.add_argument_group("corner input")
    source.add_argument(
        "--corners-json",
        type=Path,
        default=None,
        help=(
            "JSON file with {'corner_labels':['a1','h1','h8','a8'], "
            "'board_corners_xy':[[x,y],...]}. Mutually exclusive with other corner input sources."
        ),
    )
    source.add_argument("--a1", type=float, nargs=2, metavar=("X", "Y"), default=None)
    source.add_argument("--h1", type=float, nargs=2, metavar=("X", "Y"), default=None)
    source.add_argument("--h8", type=float, nargs=2, metavar=("X", "Y"), default=None)
    source.add_argument("--a8", type=float, nargs=2, metavar=("X", "Y"), default=None)
    source.add_argument(
        "--click-corners",
        action="store_true",
        help=(
            "Open an interactive OpenCV picker on --reference-image. Click corners in order a1, h1, h8, a8; "
            "Enter/c confirms, u/backspace undoes, r resets, q/Esc cancels."
        ),
    )
    source.add_argument(
        "--replay-clicks-json",
        type=Path,
        default=None,
        help=(
            "Replay a non-interactive click capture JSON. Accepted shapes include "
            "{'click_labels':['a1','h1','h8','a8'],'click_points_xy':[[x,y],...]} or "
            "{'clicks':[{'label':'a1','xy':[x,y]},...]}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        "--frame-dir",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for annotated images, candidate JSON, and summary JSON.",
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
        help="Base SimCamera profile to render with a board_corners_xy override.",
    )
    parser.add_argument("--piece-square", default=None, help="Override the profile's synthetic piece square.")
    parser.add_argument("--gripper-percent", type=float, default=80.0)
    parser.add_argument("--overlay-alpha", type=float, default=0.50)
    parser.add_argument(
        "--min-area-ratio",
        type=float,
        default=0.01,
        help="Minimum absolute polygon area as a fraction of the reference image area.",
    )
    return parser.parse_args()


def read_reference_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cv2 failed to read reference image {path}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected BGR reference image, got shape {image.shape}")
    return image


def write_image(path: Path, image_bgr_or_gray: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr_or_gray)
    if not ok:
        raise ValueError(f"cv2 failed to write {path}")


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


def load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Corner JSON must be an object, got {type(loaded).__name__}")
    return loaded


def coerce_corners_array(value: Any, *, source: str) -> np.ndarray:
    try:
        corners = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} must contain numeric corner coordinates: {exc}") from exc
    return corners


def validate_corner_labels(labels: Any, *, source: str) -> None:
    if not isinstance(labels, list):
        raise ValueError(f"{source} must contain corner labels {list(CORNER_LABELS)}, got {labels!r}")
    if labels != list(CORNER_LABELS):
        raise ValueError(f"{source} must be {list(CORNER_LABELS)}, got {labels!r}")


def corners_from_json(path: Path) -> np.ndarray:
    loaded = load_json(path.expanduser().resolve())
    labels = loaded.get("corner_labels")
    if labels is not None:
        validate_corner_labels(labels, source="corner_labels")
    if "board_corners_xy" not in loaded:
        raise ValueError("Corner JSON must contain board_corners_xy.")
    return coerce_corners_array(loaded["board_corners_xy"], source=f"board_corners_xy in {path}")


def click_point_from_mapping(click: dict[str, Any], *, index: int, source: Path) -> list[Any]:
    if "xy" in click:
        xy = click["xy"]
    elif "point_xy" in click:
        xy = click["point_xy"]
    elif "x" in click and "y" in click:
        xy = [click["x"], click["y"]]
    else:
        raise ValueError(f"clicks[{index}] in {source} must contain xy, point_xy, or x/y coordinates.")
    if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        raise ValueError(f"clicks[{index}] in {source} must be an [x, y] pair, got {xy!r}.")
    return [xy[0], xy[1]]


def corners_from_replay_clicks_json(path: Path) -> np.ndarray:
    replay_path = path.expanduser().resolve()
    loaded = load_json(replay_path)
    labels: Any
    points: Any

    if "clicks" in loaded:
        clicks = loaded["clicks"]
        if not isinstance(clicks, list):
            raise ValueError(f"clicks in {replay_path} must be a list.")
        labels = []
        points = []
        for index, click in enumerate(clicks):
            if not isinstance(click, dict):
                raise ValueError(f"clicks[{index}] in {replay_path} must be an object.")
            labels.append(click.get("label", CORNER_LABELS[index] if index < len(CORNER_LABELS) else None))
            points.append(click_point_from_mapping(click, index=index, source=replay_path))
    elif "click_labels" in loaded or "click_points_xy" in loaded:
        if "click_labels" not in loaded or "click_points_xy" not in loaded:
            raise ValueError(f"Replay click JSON {replay_path} must contain both click_labels and click_points_xy.")
        labels = loaded.get("click_labels")
        points = loaded.get("click_points_xy")
    elif "corner_labels" in loaded and "board_corners_xy" in loaded:
        labels = loaded.get("corner_labels")
        points = loaded.get("board_corners_xy")
    else:
        raise ValueError(
            f"Replay click JSON {replay_path} must contain clicks, click_labels/click_points_xy, "
            "or corner_labels/board_corners_xy."
        )

    validate_corner_labels(labels, source="Replay click labels")
    return coerce_corners_array(points, source=f"replayed click points in {replay_path}")


def draw_picker_state(image_bgr: np.ndarray, clicks_xy: list[tuple[float, float]]) -> np.ndarray:
    out = image_bgr.copy()
    next_label = CORNER_LABELS[len(clicks_xy)] if len(clicks_xy) < len(CORNER_LABELS) else "ready to confirm"
    lines = [
        "Click board corners in order: a1, h1, h8, a8",
        f"Next: {next_label}",
        "Enter/c: confirm  u/backspace: undo  r: reset  q/Esc: cancel",
    ]
    out = add_label(out, lines, height_px=70)
    if not clicks_xy:
        return out

    pts = np.round(np.asarray(clicks_xy, dtype=float)).astype(int)
    if len(pts) > 1:
        cv2.polylines(out, [pts], isClosed=len(pts) == len(CORNER_LABELS), color=(255, 0, 255), thickness=2)
    for label, pt in zip(CORNER_LABELS, pts, strict=False):
        xy = tuple(int(value) for value in pt)
        cv2.circle(out, xy, 6, (255, 0, 255), -1)
        cv2.putText(out, label, (xy[0] + 8, xy[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(out, label, (xy[0] + 8, xy[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return out


def pick_corners_interactive(reference_bgr: np.ndarray) -> np.ndarray:
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise ValueError(
            "OpenCV interactive display is unavailable because neither DISPLAY nor WAYLAND_DISPLAY is set. "
            "Use --replay-clicks-json for headless validation."
        )

    window_name = "Sim manual corner picker"
    clicks_xy: list[tuple[float, float]] = []
    confirmed = False
    cancelled = False

    def on_mouse(event: int, x: int, y: int, _flags: int, _userdata: Any) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks_xy) < len(CORNER_LABELS):
            clicks_xy.append((float(x), float(y)))

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, on_mouse)
        while True:
            cv2.imshow(window_name, draw_picker_state(reference_bgr, clicks_xy))
            key = cv2.waitKey(50)
            if key == -1:
                try:
                    if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                        raise ValueError("OpenCV corner picker window was closed before confirmation.")
                except cv2.error:
                    pass
                continue

            key_code = key & 0xFF
            if key_code in (27, ord("q")):
                cancelled = True
                break
            if key_code in (8, 127, ord("u")):
                if clicks_xy:
                    clicks_xy.pop()
                continue
            if key_code == ord("r"):
                clicks_xy.clear()
                continue
            if key_code in (10, 13, ord("c")) and len(clicks_xy) == len(CORNER_LABELS):
                confirmed = True
                break
    except cv2.error as exc:
        raise ValueError(
            f"OpenCV interactive display failed: {exc}. Use --replay-clicks-json for headless validation."
        ) from exc
    finally:
        try:
            cv2.destroyWindow(window_name)
        except cv2.error:
            pass

    if cancelled:
        raise ValueError("OpenCV corner picker cancelled before confirmation.")
    if not confirmed:
        raise ValueError("OpenCV corner picker exited before four corners were confirmed.")
    return np.asarray(clicks_xy, dtype=float)


def corners_from_args(args: argparse.Namespace, reference_bgr: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    cli_values = [args.a1, args.h1, args.h8, args.a8]
    provided_count = sum(value is not None for value in cli_values)
    if provided_count not in (0, len(CORNER_LABELS)):
        raise ValueError(
            "Provide all explicit corner arguments in label order: --a1 X Y --h1 X Y --h8 X Y --a8 X Y."
        )

    sources = []
    if args.corners_json is not None:
        sources.append("corners-json")
    if provided_count:
        sources.append("cli")
    if args.click_corners:
        sources.append("click-corners")
    if args.replay_clicks_json is not None:
        sources.append("replay-clicks-json")
    if len(sources) != 1:
        raise ValueError(
            "Choose exactly one corner input source: --corners-json, all explicit --a1/--h1/--h8/--a8 "
            "values, --click-corners, or --replay-clicks-json."
        )

    if args.corners_json is not None:
        path = args.corners_json.expanduser().resolve()
        return corners_from_json(path), {"kind": "corners-json", "path": str(path)}
    if provided_count:
        return coerce_corners_array(cli_values, source="explicit CLI corners"), {"kind": "cli"}
    if args.replay_clicks_json is not None:
        path = args.replay_clicks_json.expanduser().resolve()
        return corners_from_replay_clicks_json(path), {"kind": "replay-clicks-json", "path": str(path)}
    return pick_corners_interactive(reference_bgr), {"kind": "click-corners"}


def polygon_area_xy(points_xy: np.ndarray) -> float:
    x = points_xy[:, 0]
    y = points_xy[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def image_stats(image_bgr: np.ndarray) -> dict[str, Any]:
    flat = image_bgr.reshape(-1, image_bgr.shape[-1])
    return {
        "width": int(image_bgr.shape[1]),
        "height": int(image_bgr.shape[0]),
        "shape": [int(value) for value in image_bgr.shape],
        "dtype": str(image_bgr.dtype),
        "min": [int(value) for value in flat.min(axis=0)],
        "max": [int(value) for value in flat.max(axis=0)],
        "mean": [float(value) for value in flat.mean(axis=0)],
        "std": [float(value) for value in flat.std(axis=0)],
    }


def validate_candidate_corners(
    corners_xy: np.ndarray,
    *,
    width: int,
    height: int,
    min_area_ratio: float,
) -> dict[str, Any]:
    if corners_xy.shape != (4, 2):
        raise ValueError(f"Expected exactly four (x, y) board corners, got array shape {corners_xy.shape}.")
    if not np.all(np.isfinite(corners_xy)):
        raise ValueError(f"Board corners contain non-finite values: {corners_xy.tolist()}")

    in_bounds_x = np.logical_and(corners_xy[:, 0] >= 0.0, corners_xy[:, 0] < float(width))
    in_bounds_y = np.logical_and(corners_xy[:, 1] >= 0.0, corners_xy[:, 1] < float(height))
    if not bool(np.all(in_bounds_x & in_bounds_y)):
        failures = [
            {
                "label": label,
                "xy": [float(corners_xy[idx, 0]), float(corners_xy[idx, 1])],
                "in_bounds": bool(in_bounds_x[idx] and in_bounds_y[idx]),
            }
            for idx, label in enumerate(CORNER_LABELS)
        ]
        raise ValueError(f"Board corners must be inside image bounds {width}x{height}: {failures}")

    signed_area = polygon_area_xy(corners_xy)
    area_px2 = abs(signed_area)
    min_area_px2 = float(width * height) * float(min_area_ratio)
    if area_px2 < min_area_px2:
        raise ValueError(
            f"Board polygon area {area_px2:.2f}px^2 is below the minimum {min_area_px2:.2f}px^2 "
            f"({min_area_ratio:.4f} of image area)."
        )
    if signed_area >= 0.0:
        raise ValueError(
            "Board corner orientation is wrong for a1,h1,h8,a8 image-coordinate order; "
            f"expected negative signed area, got {signed_area:.2f}."
        )

    contour = np.round(corners_xy).astype(np.int32).reshape(-1, 1, 2)
    if not bool(cv2.isContourConvex(contour)):
        raise ValueError("Board corners must form a convex quadrilateral in a1,h1,h8,a8 order.")

    a1, h1, h8, a8 = corners_xy
    bottom_center = (a1 + h1) / 2.0
    top_center = (a8 + h8) / 2.0
    left_center = (a1 + a8) / 2.0
    right_center = (h1 + h8) / 2.0
    if bottom_center[1] <= top_center[1]:
        raise ValueError(
            "Board labels appear vertically flipped; expected a1/h1 below a8/h8 in this reference image."
        )
    if right_center[0] <= left_center[0]:
        raise ValueError(
            "Board labels appear horizontally flipped; expected h-file corners to the right of a-file corners."
        )

    side_lengths = {
        "a1_h1": float(np.linalg.norm(h1 - a1)),
        "h1_h8": float(np.linalg.norm(h8 - h1)),
        "h8_a8": float(np.linalg.norm(a8 - h8)),
        "a8_a1": float(np.linalg.norm(a1 - a8)),
    }
    min_side_px = max(8.0, min(width, height) * 0.02)
    short_sides = {name: length for name, length in side_lengths.items() if length < min_side_px}
    if short_sides:
        raise ValueError(f"Board polygon has implausibly short side lengths: {short_sides}")

    return {
        "corner_labels": list(CORNER_LABELS),
        "in_bounds": True,
        "convex": True,
        "signed_area_px2": float(signed_area),
        "area_px2": float(area_px2),
        "area_ratio": float(area_px2 / float(width * height)),
        "min_area_px2": float(min_area_px2),
        "orientation": "expected_a1_h1_h8_a8_image_order",
        "signed_area_convention": "shoelace on image x,y coordinates; expected negative for a1,h1,h8,a8",
        "side_lengths_px": side_lengths,
        "diagonal_lengths_px": {
            "a1_h8": float(np.linalg.norm(h8 - a1)),
            "h1_a8": float(np.linalg.norm(a8 - h1)),
        },
        "bounds_xy": {
            "min": [float(value) for value in corners_xy.min(axis=0)],
            "max": [float(value) for value in corners_xy.max(axis=0)],
        },
        "centroid_xy": [float(value) for value in corners_xy.mean(axis=0)],
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


def draw_labeled_polygon(
    image_bgr: np.ndarray,
    corners_xy: np.ndarray,
    *,
    color: tuple[int, int, int],
    labels: tuple[str, ...],
    prefix: str = "",
    thickness: int = 2,
) -> None:
    pts = np.round(corners_xy).astype(int)
    cv2.polylines(image_bgr, [pts], isClosed=True, color=color, thickness=thickness)
    for label, pt in zip(labels, pts, strict=True):
        xy = tuple(int(value) for value in pt)
        cv2.circle(image_bgr, xy, 6, color, -1)
        text = f"{prefix}{label}"
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        text_x = int(np.clip(xy[0] + 7, 4, max(4, image_bgr.shape[1] - text_size[0] - 4)))
        text_y = int(np.clip(xy[1] - 7, text_size[1] + 4, max(text_size[1] + 4, image_bgr.shape[0] - 4)))
        cv2.putText(image_bgr, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
        cv2.putText(image_bgr, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)


def add_label(image_bgr: np.ndarray, lines: list[str], *, height_px: int = 58) -> np.ndarray:
    out = image_bgr.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], min(out.shape[0], height_px)), (0, 0, 0), -1)
    for idx, line in enumerate(lines[:3]):
        y = 20 + idx * 17
        cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (255, 255, 255), 1)
    return out


def annotate_candidate_geometry(
    image_bgr: np.ndarray,
    *,
    candidate_corners: np.ndarray,
    profile_corners: np.ndarray,
    piece_square: str,
    title: str,
) -> np.ndarray:
    out = image_bgr.copy()
    draw_labeled_polygon(out, profile_corners, color=(0, 210, 255), labels=CORNER_LABELS, prefix="profile ")
    draw_labeled_polygon(out, candidate_corners, color=(255, 0, 255), labels=CORNER_LABELS, prefix="candidate ")
    for profile_pt, candidate_pt in zip(profile_corners, candidate_corners, strict=True):
        cv2.line(
            out,
            tuple(int(round(value)) for value in profile_pt),
            tuple(int(round(value)) for value in candidate_pt),
            (255, 255, 255),
            1,
        )

    _, _, center = square_center_xy(candidate_corners, piece_square)
    cx, cy = int(round(center[0])), int(round(center[1]))
    cv2.drawMarker(out, (cx, cy), (0, 255, 0), markerType=cv2.MARKER_CROSS, markerSize=22, thickness=2)
    cv2.putText(out, piece_square, (cx + 9, cy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
    cv2.putText(out, piece_square, (cx + 9, cy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return add_label(out, [title, "cyan: base profile, magenta: candidate, green: piece square"])


def render_synthetic_candidate(
    *,
    profile: str,
    corners_xy: np.ndarray,
    reference_path: Path,
    width: int,
    height: int,
    piece_square: str | None,
    gripper_percent: float,
) -> tuple[np.ndarray, dict[str, Any], Any]:
    overrides: dict[str, Any] = {
        "width": int(width),
        "height": int(height),
        "color_mode": ColorMode.BGR,
        "board_corners_xy": tuple(tuple(float(value) for value in row) for row in corners_xy.tolist()),
        "reference_image_path": reference_path,
    }
    if piece_square is not None:
        overrides["piece_square"] = str(piece_square)

    camera_cfg = make_sim_camera_config_from_profile(str(profile), **overrides)
    camera = SimCamera(camera_cfg)
    clipped_gripper_percent = float(np.clip(float(gripper_percent), 0.0, 100.0))
    try:
        camera.connect(warmup=False)
        camera.set_robot_state({"gripper": clipped_gripper_percent})
        synthetic_bgr = camera.read(ColorMode.BGR)
        metadata = camera.calibration_metadata()
    finally:
        if camera.is_connected:
            camera.disconnect()
    return synthetic_bgr, metadata, camera_cfg


def candidate_vs_profile(candidate_corners: np.ndarray, profile_corners: np.ndarray) -> dict[str, Any]:
    deltas = candidate_corners - profile_corners
    distances = np.linalg.norm(deltas, axis=1)
    return {
        "profile_corners_xy": [[float(x), float(y)] for x, y in profile_corners.tolist()],
        "candidate_corners_xy": [[float(x), float(y)] for x, y in candidate_corners.tolist()],
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
        "max_corner_l2_px": float(distances.max()),
        "profile_area_px2": polygon_area_xy(profile_corners),
        "candidate_area_px2": polygon_area_xy(candidate_corners),
        "area_delta_px2": polygon_area_xy(candidate_corners) - polygon_area_xy(profile_corners),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    reference_path = args.reference_image.expanduser().resolve()
    reference_bgr = read_reference_image(reference_path)
    height, width = reference_bgr.shape[:2]
    candidate_corners, corner_input = corners_from_args(args, reference_bgr)
    validation = validate_candidate_corners(
        candidate_corners,
        width=width,
        height=height,
        min_area_ratio=float(args.min_area_ratio),
    )

    profile_values = SIM_CAMERA_CALIBRATION_PROFILES[str(args.profile)]
    profile_corners = np.asarray(profile_values["board_corners_xy"], dtype=float)
    geometry_vs_profile = candidate_vs_profile(candidate_corners, profile_corners)

    synthetic_bgr, metadata, camera_cfg = render_synthetic_candidate(
        profile=str(args.profile),
        corners_xy=candidate_corners,
        reference_path=reference_path,
        width=width,
        height=height,
        piece_square=args.piece_square,
        gripper_percent=args.gripper_percent,
    )
    if synthetic_bgr.shape != reference_bgr.shape:
        raise ValueError(f"Synthetic frame shape {synthetic_bgr.shape} does not match {reference_bgr.shape}")

    file_idx, rank_idx, piece_center = square_center_xy(candidate_corners, str(camera_cfg.piece_square))
    reference_overlay = annotate_candidate_geometry(
        reference_bgr,
        candidate_corners=candidate_corners,
        profile_corners=profile_corners,
        piece_square=str(camera_cfg.piece_square),
        title="real reference manual-corner candidate",
    )
    synthetic_overlay = annotate_candidate_geometry(
        synthetic_bgr,
        candidate_corners=candidate_corners,
        profile_corners=profile_corners,
        piece_square=str(camera_cfg.piece_square),
        title="synthetic SimCamera candidate render",
    )
    alpha = float(np.clip(float(args.overlay_alpha), 0.0, 1.0))
    blend_overlay = cv2.addWeighted(reference_bgr, alpha, synthetic_bgr, 1.0 - alpha, 0.0)
    abs_delta = np.abs(reference_bgr.astype(np.int16) - synthetic_bgr.astype(np.int16)).astype(np.uint8)
    heatmap = cv2.applyColorMap(np.clip(abs_delta.mean(axis=2) * 2.0, 0, 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    side_by_side = np.hstack([reference_overlay, synthetic_overlay])

    artifacts = {
        "reference_candidate_overlay_path": output_dir / "reference_candidate_overlay.jpg",
        "synthetic_candidate_path": output_dir / "synthetic_candidate.jpg",
        "synthetic_candidate_annotated_path": output_dir / "synthetic_candidate_annotated.jpg",
        "side_by_side_path": output_dir / "side_by_side.jpg",
        "blend_overlay_path": output_dir / "blend_overlay.jpg",
        "absolute_difference_heatmap_path": output_dir / "absolute_difference_heatmap.jpg",
        "profile_candidate_path": output_dir / "profile_candidate.json",
        "summary_path": output_dir / "summary.json",
    }
    write_image(artifacts["reference_candidate_overlay_path"], reference_overlay)
    write_image(artifacts["synthetic_candidate_path"], synthetic_bgr)
    write_image(artifacts["synthetic_candidate_annotated_path"], synthetic_overlay)
    write_image(artifacts["side_by_side_path"], side_by_side)
    write_image(artifacts["blend_overlay_path"], blend_overlay)
    write_image(artifacts["absolute_difference_heatmap_path"], heatmap)

    profile_candidate = {
        "schema": "lerobot.sim.manual_corner_profile_candidate.v1",
        "base_profile": str(args.profile),
        "status": "candidate_only_not_canonical",
        "reference_image_path": str(reference_path),
        "corner_labels": list(CORNER_LABELS),
        "board_corners_xy": [[float(x), float(y)] for x, y in candidate_corners.tolist()],
        "sim_camera_profile_overrides": {
            "width": int(width),
            "height": int(height),
            "board_corners_xy": [[float(x), float(y)] for x, y in candidate_corners.tolist()],
            "reference_image_path": str(reference_path),
        },
        "validation": validation,
        "geometry_vs_base_profile": geometry_vs_profile,
    }
    artifacts["profile_candidate_path"].write_text(json.dumps(profile_candidate, indent=2))

    delta = reference_bgr.astype(np.float32) - synthetic_bgr.astype(np.float32)
    summary = {
        "ok": True,
        "scenario": "sim_manual_corner_profile_candidate",
        "profile": str(args.profile),
        "profile_values": jsonable(profile_values),
        "reference_image_path": str(reference_path),
        "output_dir": str(output_dir),
        "corner_input": corner_input,
        "artifacts": {name: str(path) for name, path in artifacts.items()},
        "candidate": profile_candidate,
        "image": {
            "reference": image_stats(reference_bgr),
            "synthetic": image_stats(synthetic_bgr),
            "absolute_difference": image_stats(abs_delta),
            "mean_abs_delta_bgr": [float(value) for value in np.abs(delta).mean(axis=(0, 1))],
            "rmse_bgr": [float(value) for value in np.sqrt(np.mean(delta * delta, axis=(0, 1)))],
            "mean_abs_delta": float(np.abs(delta).mean()),
            "rmse": float(np.sqrt(np.mean(delta * delta))),
        },
        "piece_square": {
            "square": str(camera_cfg.piece_square),
            "file_idx": int(file_idx),
            "rank_idx": int(rank_idx),
            "center_image_xy": [float(value) for value in piece_center],
        },
        "gripper": {
            "requested_percent": float(np.clip(float(args.gripper_percent), 0.0, 100.0)),
            "visible": bool(metadata["gripper_visible"]),
            "track_robot_gripper": bool(metadata["track_robot_gripper"]),
            "tracked_gripper_percent": metadata["tracked_gripper_percent"],
            "current_gripper_opening_px": metadata["current_gripper_opening_px"],
        },
        "camera_metadata": metadata,
        "notes": [
            "This smoke writes a reviewable override candidate only; it does not mutate SIM_CAMERA_CALIBRATION_PROFILES.",
            "The candidate JSON is intentionally shaped so a later UI/profile-loader can consume sim_camera_profile_overrides.",
        ],
    }
    artifacts["summary_path"].write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
