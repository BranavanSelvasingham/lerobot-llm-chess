#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
LLM_TOOLS_DIR = REPO_ROOT / "llm-tools"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(LLM_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(LLM_TOOLS_DIR))

from lerobot.cameras.configs import ColorMode
from lerobot.sim import (
    SIM_CAMERA_CALIBRATION_PROFILES,
    SimCamera,
    SimCameraConfig,
    load_sim_camera_profile_overrides,
    make_sim_camera_config_from_profile,
)
from llm_toolkit import AppConfig, KinematicsTools


SOURCE_HOVER_JOINTS = {
    "shoulder_pan": -8.0,
    "shoulder_lift": -18.0,
    "elbow_flex": 24.0,
    "wrist_flex": -22.0,
    "wrist_roll": 6.0,
}
TARGET_HOVER_JOINTS = {
    "shoulder_pan": 8.0,
    "shoulder_lift": -16.0,
    "elbow_flex": 20.0,
    "wrist_flex": -20.0,
    "wrist_roll": -6.0,
}
PIECE_VISIBILITY_SCHEMA = "lerobot.sim.pick_place_piece_visibility.v1"
PIECE_RADIUS_SCALE = 0.30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a hardware-free scripted SO-101 chess pickup calibration scenario."
    )
    parser.add_argument(
        "--frame-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "sim" / "pick_place_calibration",
        help="Directory for before/after frame artifacts and summary JSON.",
    )
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--grasp-percent", type=float, default=24.0)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument(
        "--sim-camera-profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=None,
        help="Named simulator camera calibration profile. When set, profile dimensions and metadata are used.",
    )
    parser.add_argument(
        "--sim-camera-profile-overrides",
        type=Path,
        default=None,
        help=(
            "Simulator-only profile_candidate.json with sim_camera_profile_overrides. "
            "Composes with --sim-camera-profile."
        ),
    )
    return parser.parse_args()


def assert_tool_ok(name: str, result: dict[str, Any]) -> dict[str, Any]:
    assert result.get("ok") is True, f"{name} failed: {result}"
    return result


def run_tool(tools: KinematicsTools, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    result = tools.execute_tool(name, args or {})
    return assert_tool_ok(name, result)


def sync_camera_to_tool_state(tools: KinematicsTools, camera: SimCamera) -> dict[str, float]:
    joints_result = run_tool(tools, "read_joints", {"include_gripper": True})
    joints = {
        str(name): float(value)
        for name, value in joints_result["joints"].items()
        if value is not None
    }
    camera.set_robot_state(joints)
    return joints


def square_file_rank(square: str) -> tuple[int, int]:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(value[0]) - ord("a"), int(value[1]) - 1


def board_point(corners: np.ndarray, u: float, v: float) -> np.ndarray:
    a1, h1, h8, a8 = corners
    bottom = a1 * (1.0 - u) + h1 * u
    top = a8 * (1.0 - u) + h8 * u
    return bottom * (1.0 - v) + top * v


def point_to_segment_distance(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    segment = end - start
    segment_len_sq = float(np.dot(segment, segment))
    if segment_len_sq <= 1e-12:
        return float(np.linalg.norm(point - start))
    t = float(np.clip(np.dot(point - start, segment) / segment_len_sq, 0.0, 1.0))
    projection = start + segment * t
    return float(np.linalg.norm(point - projection))


def circle_to_quad_clearance(center: np.ndarray, radius: float, quad: np.ndarray) -> float:
    signed_distance = float(cv2.pointPolygonTest(quad.astype(np.float32), tuple(center), measureDist=True))
    if signed_distance >= 0.0:
        return -float(radius)
    edge_distance = min(
        point_to_segment_distance(center, quad[index], quad[(index + 1) % len(quad)])
        for index in range(len(quad))
    )
    return float(edge_distance - radius)


def gripper_finger_quads(camera: SimCamera, metadata: dict[str, Any]) -> list[np.ndarray]:
    if not bool(metadata.get("gripper_visible")) or metadata.get("view") != "gripper":
        return []
    height = int(camera.height or 480)
    width = int(camera.width or 640)
    center_x = int(camera.config.gripper_center_x_px or (width // 2))
    y_base = int(camera.config.gripper_y_px or int(height * 0.78))
    opening = int(metadata.get("current_gripper_opening_px") or camera.config.gripper_opening_px)
    finger_w = max(12, int(camera.config.gripper_finger_width_px))
    length = max(40, int(camera.config.gripper_length_px))
    left = np.array(
        [
            [center_x - opening // 2 - finger_w, height],
            [center_x - opening // 2 - max(8, finger_w // 5), y_base],
            [center_x - opening // 2 + max(4, finger_w // 8), y_base - length // 5],
            [center_x - opening // 2 - finger_w // 2, height],
        ],
        dtype=float,
    )
    right = left.copy()
    right[:, 0] = 2 * center_x - left[:, 0]
    return [left, right]


def unavailable_piece_visibility(reason: str) -> dict[str, Any]:
    return {
        "schema": PIECE_VISIBILITY_SCHEMA,
        "method": "synthetic_geometry_from_capture_metadata_v1",
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "limitations": [
            "Synthetic-frame geometry only; this does not model physical chess-piece contact or real camera segmentation.",
        ],
    }


def piece_visibility_metric(camera: SimCamera, metadata: dict[str, Any]) -> dict[str, Any]:
    if metadata.get("piece_layout") != "single_pawn":
        return unavailable_piece_visibility("piece_layout is not single_pawn")
    if not bool(camera.config.draw_pieces):
        return unavailable_piece_visibility("draw_pieces is disabled")

    try:
        file_idx, rank_idx = square_file_rank(str(metadata.get("piece_square") or ""))
        corners = np.asarray(metadata.get("board_corners_xy"), dtype=float)
    except (TypeError, ValueError) as exc:
        return unavailable_piece_visibility(str(exc))

    if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
        return unavailable_piece_visibility("board_corners_xy is missing or invalid")

    center = board_point(corners, (file_idx + 0.5) / 8.0, (rank_idx + 0.5) / 8.0)
    next_file = board_point(corners, min(1.0, (file_idx + 1.5) / 8.0), (rank_idx + 0.5) / 8.0)
    next_rank = board_point(corners, (file_idx + 0.5) / 8.0, min(1.0, (rank_idx + 1.5) / 8.0))
    square_px = max(8.0, float(min(np.linalg.norm(next_file - center), np.linalg.norm(next_rank - center))))
    radius = max(3, int(square_px * PIECE_RADIUS_SCALE))

    quads = gripper_finger_quads(camera, metadata)
    if not quads:
        return {
            "schema": PIECE_VISIBILITY_SCHEMA,
            "method": "synthetic_geometry_from_capture_metadata_v1",
            "available": True,
            "status": "no_visible_gripper",
            "piece": {
                "square": metadata.get("piece_square"),
                "center_xy": [round(float(center[0]), 3), round(float(center[1]), 3)],
                "radius_px": int(radius),
            },
            "gripper_clearance": {
                "available": False,
                "reason": "gripper is not visible in this capture metadata",
            },
            "occlusion": {
                "available": True,
                "overlap_piece_pixels": 0,
                "piece_area_pixels": int(round(math.pi * radius * radius)),
                "occlusion_fraction": 0.0,
                "visible_fraction": 1.0,
            },
            "limitations": [
                "Synthetic-frame geometry only; this does not model physical chess-piece contact or real camera segmentation.",
            ],
        }

    height = int(camera.height or 480)
    width = int(camera.width or 640)
    x_min = max(0, int(math.floor(center[0] - radius - 2)))
    x_max = min(width, int(math.ceil(center[0] + radius + 3)))
    y_min = max(0, int(math.floor(center[1] - radius - 2)))
    y_max = min(height, int(math.ceil(center[1] + radius + 3)))
    if x_min >= x_max or y_min >= y_max:
        return unavailable_piece_visibility("piece disc falls outside the frame")

    yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
    piece_mask = (xx - float(center[0])) ** 2 + (yy - float(center[1])) ** 2 <= float(radius * radius)
    gripper_mask = np.zeros((y_max - y_min, x_max - x_min), dtype=np.uint8)
    shifted_quads = [np.round(quad - np.array([x_min, y_min], dtype=float)).astype(np.int32) for quad in quads]
    cv2.fillPoly(gripper_mask, shifted_quads, 1)
    piece_area = int(np.count_nonzero(piece_mask))
    overlap_pixels = int(np.count_nonzero(piece_mask & (gripper_mask > 0)))
    occlusion_fraction = float(overlap_pixels / piece_area) if piece_area else 0.0
    visible_fraction = max(0.0, 1.0 - occlusion_fraction)
    clearances = [circle_to_quad_clearance(center, float(radius), quad) for quad in quads]
    min_clearance = min(clearances) if clearances else None
    clear_of_gripper = overlap_pixels == 0 and (min_clearance is None or min_clearance > 0.0)

    return {
        "schema": PIECE_VISIBILITY_SCHEMA,
        "method": "synthetic_geometry_from_capture_metadata_v1",
        "available": True,
        "status": "clear" if clear_of_gripper else "gripper_overlap",
        "piece": {
            "square": metadata.get("piece_square"),
            "center_xy": [round(float(center[0]), 3), round(float(center[1]), 3)],
            "radius_px": int(radius),
            "area_pixels": piece_area,
        },
        "gripper_clearance": {
            "available": True,
            "clear_of_gripper": bool(clear_of_gripper),
            "min_clearance_px": round(float(min_clearance), 3) if min_clearance is not None else None,
            "current_gripper_opening_px": metadata.get("current_gripper_opening_px"),
            "tracked_gripper_percent": metadata.get("tracked_gripper_percent"),
            "finger_quad_count": len(quads),
        },
        "occlusion": {
            "available": True,
            "overlap_piece_pixels": overlap_pixels,
            "piece_area_pixels": piece_area,
            "occlusion_fraction": round(occlusion_fraction, 6),
            "visible_fraction": round(visible_fraction, 6),
        },
        "limitations": [
            "Synthetic-frame geometry only; this does not model physical chess-piece contact or real camera segmentation.",
        ],
    }


def summarize_piece_visibility(captures: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for capture in captures:
        metric = capture.get("piece_visibility")
        if not isinstance(metric, dict) or not metric.get("available"):
            continue
        occlusion = metric.get("occlusion") if isinstance(metric.get("occlusion"), dict) else {}
        clearance = metric.get("gripper_clearance") if isinstance(metric.get("gripper_clearance"), dict) else {}
        rows.append(
            {
                "label": capture.get("label"),
                "path": capture.get("path"),
                "visible_fraction": occlusion.get("visible_fraction"),
                "occlusion_fraction": occlusion.get("occlusion_fraction"),
                "min_clearance_px": clearance.get("min_clearance_px"),
                "clear_of_gripper": clearance.get("clear_of_gripper"),
                "status": metric.get("status"),
            }
        )

    visible_values = [float(row["visible_fraction"]) for row in rows if row.get("visible_fraction") is not None]
    occlusion_values = [float(row["occlusion_fraction"]) for row in rows if row.get("occlusion_fraction") is not None]
    clearance_values = [float(row["min_clearance_px"]) for row in rows if row.get("min_clearance_px") is not None]
    worst = min(
        (row for row in rows if row.get("visible_fraction") is not None),
        key=lambda row: float(row["visible_fraction"]),
        default=None,
    )
    release = next((row for row in rows if row.get("label") == "target_release_open"), None)
    return {
        "schema": PIECE_VISIBILITY_SCHEMA,
        "method": "synthetic_geometry_from_capture_metadata_v1",
        "available": bool(rows),
        "capture_count": len(captures),
        "available_capture_count": len(rows),
        "all_captures_available": len(rows) == len(captures),
        "all_captures_clear_of_gripper": (
            all(bool(row.get("clear_of_gripper")) for row in rows) if rows else None
        ),
        "min_visible_fraction": min(visible_values) if visible_values else None,
        "max_occlusion_fraction": max(occlusion_values) if occlusion_values else None,
        "min_clearance_px": min(clearance_values) if clearance_values else None,
        "worst_capture_label": worst.get("label") if worst else None,
        "target_release_open": release,
        "captures": rows,
        "limitations": [
            "Synthetic-frame geometry only; this does not model physical chess-piece contact or real camera segmentation.",
        ],
    }


def save_capture(
    *,
    tools: KinematicsTools,
    camera: SimCamera,
    frame_dir: Path,
    index: int,
    label: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    joints = sync_camera_to_tool_state(tools, camera)
    frame = camera.async_read()
    assert frame.shape == (int(camera.height), int(camera.width), 3), frame.shape
    assert frame.dtype == np.uint8, frame.dtype
    assert len(np.unique(frame.reshape(-1, 3), axis=0)) >= 12

    metadata = camera.calibration_metadata()
    visibility = piece_visibility_metric(camera, metadata)
    frame_path = frame_dir / f"{index:02d}_{label}.jpg"
    ok = cv2.imwrite(str(frame_path), frame)
    assert ok, f"cv2 failed to write {frame_path}"

    return frame, {
        "label": label,
        "path": str(frame_path),
        "joints": joints,
        "metadata": metadata,
        "piece_visibility": visibility,
        "mean_bgr": [float(x) for x in frame.mean(axis=(0, 1))],
        "unique_colors": int(len(np.unique(frame.reshape(-1, 3), axis=0))),
    }


def gripper_frame_delta(before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
    y0 = int(before.shape[0] * 0.60)
    before_crop = before[y0:, :, :].astype(np.int16)
    after_crop = after[y0:, :, :].astype(np.int16)
    delta = np.abs(after_crop - before_crop)
    changed_pixels = int(np.count_nonzero(np.any(delta > 8, axis=2)))
    return {
        "mean_abs_delta": float(delta.mean()),
        "changed_pixels": changed_pixels,
    }


def assert_joint_near(result: dict[str, Any], joint: str, expected: float) -> None:
    actual = float(result["after"][joint])
    assert abs(actual - expected) < 1e-6, (joint, actual, expected, result)


def assert_capture_square(capture: dict[str, Any], expected_square: str) -> None:
    metadata = capture["metadata"]
    assert metadata["piece_layout"] == "single_pawn", metadata
    assert metadata["piece_square"] == expected_square, (capture["label"], metadata, expected_square)


def main() -> int:
    args = parse_args()
    source_square = str(args.source_square)
    target_square = str(args.target_square)
    frame_dir = args.frame_dir.expanduser().resolve()
    frame_dir.mkdir(parents=True, exist_ok=True)

    try:
        camera_overrides = (
            load_sim_camera_profile_overrides(args.sim_camera_profile_overrides)
            if args.sim_camera_profile_overrides
            else {}
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.sim_camera_profile:
        camera_cfg = make_sim_camera_config_from_profile(
            str(args.sim_camera_profile),
            color_mode=ColorMode.BGR,
            view="gripper",
            piece_layout="single_pawn",
            piece_square=source_square,
            track_robot_gripper=True,
            **camera_overrides,
        )
    else:
        camera_values = {
            "width": int(args.width),
            "height": int(args.height),
            "fps": int(args.fps),
            "color_mode": ColorMode.BGR,
            "view": "gripper",
            "piece_layout": "single_pawn",
            "piece_square": source_square,
            "track_robot_gripper": True,
        }
        camera_cfg = SimCameraConfig(**{**camera_values, **camera_overrides})

    cfg = AppConfig(
        port=None,
        robot_id="so101_sim_pick_place_calibration",
        sim=True,
        camera_width=int(camera_cfg.width),
        camera_height=int(camera_cfg.height),
        camera_fps=int(camera_cfg.fps),
    )

    tools = KinematicsTools(cfg)
    camera = SimCamera(camera_cfg)
    tool_results: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []

    try:
        assert tools.robot is not None, "sim robot was not created"
        assert tools.robot.is_connected, "sim robot did not connect"
        camera.connect(warmup=True)

        tool_results.append({"tool": "open_gripper", "result": run_tool(tools, "open_gripper")})
        open_frame, open_capture = save_capture(
            tools=tools,
            camera=camera,
            frame_dir=frame_dir,
            index=1,
            label="source_open",
        )
        captures.append(open_capture)

        source_move = run_tool(
            tools,
            "move_joints",
            {**SOURCE_HOVER_JOINTS, "max_step_deg": 30.0},
        )
        tool_results.append({"tool": "move_joints_source_hover", "result": source_move})
        assert_joint_near(source_move, "shoulder_pan", SOURCE_HOVER_JOINTS["shoulder_pan"])
        assert_joint_near(source_move, "wrist_roll", SOURCE_HOVER_JOINTS["wrist_roll"])
        _, source_hover_capture = save_capture(
            tools=tools,
            camera=camera,
            frame_dir=frame_dir,
            index=2,
            label="source_hover_open",
        )
        captures.append(source_hover_capture)

        grasp_percent = float(np.clip(float(args.grasp_percent), 0.0, 100.0))
        set_gripper = run_tool(tools, "set_gripper_percent", {"percent": grasp_percent})
        tool_results.append({"tool": "set_gripper_percent", "result": set_gripper})
        assert abs(float(set_gripper["after"]) - grasp_percent) < 1e-6, set_gripper
        pinch_frame, pinch_capture = save_capture(
            tools=tools,
            camera=camera,
            frame_dir=frame_dir,
            index=3,
            label="source_pinched",
        )
        captures.append(pinch_capture)

        close_gripper = run_tool(tools, "close_gripper")
        tool_results.append({"tool": "close_gripper", "result": close_gripper})
        closed_frame, closed_capture = save_capture(
            tools=tools,
            camera=camera,
            frame_dir=frame_dir,
            index=4,
            label="source_closed",
        )
        captures.append(closed_capture)

        target_move = run_tool(
            tools,
            "move_joints",
            {**TARGET_HOVER_JOINTS, "max_step_deg": 30.0},
        )
        tool_results.append({"tool": "move_joints_target_hover", "result": target_move})
        assert_joint_near(target_move, "shoulder_pan", TARGET_HOVER_JOINTS["shoulder_pan"])
        assert_joint_near(target_move, "wrist_roll", TARGET_HOVER_JOINTS["wrist_roll"])
        _, target_hover_capture = save_capture(
            tools=tools,
            camera=camera,
            frame_dir=frame_dir,
            index=5,
            label="target_hover_closed",
        )
        captures.append(target_hover_capture)

        release = run_tool(tools, "open_gripper")
        tool_results.append({"tool": "open_gripper_release", "result": release})
        camera.config.piece_square = target_square
        release_frame, release_capture = save_capture(
            tools=tools,
            camera=camera,
            frame_dir=frame_dir,
            index=6,
            label="target_release_open",
        )
        captures.append(release_capture)

        open_meta = open_capture["metadata"]
        pinch_meta = pinch_capture["metadata"]
        closed_meta = closed_capture["metadata"]
        release_meta = release_capture["metadata"]
        for capture in (open_capture, source_hover_capture, pinch_capture, closed_capture):
            assert_capture_square(capture, source_square)
        assert_capture_square(release_capture, target_square)

        assert open_meta["tracked_gripper_percent"] == 95.0, open_meta
        assert closed_meta["tracked_gripper_percent"] == 0.0, closed_meta
        assert release_meta["tracked_gripper_percent"] == 95.0, release_meta
        assert open_meta["current_gripper_opening_px"] > pinch_meta["current_gripper_opening_px"], (
            open_meta,
            pinch_meta,
        )
        assert pinch_meta["current_gripper_opening_px"] > closed_meta["current_gripper_opening_px"], (
            pinch_meta,
            closed_meta,
        )
        assert release_meta["current_gripper_opening_px"] > closed_meta["current_gripper_opening_px"], (
            release_meta,
            closed_meta,
        )

        pinch_delta = gripper_frame_delta(open_frame, pinch_frame)
        close_delta = gripper_frame_delta(pinch_frame, closed_frame)
        release_delta = gripper_frame_delta(closed_frame, release_frame)
        min_changed_pixels = int(camera_cfg.width * camera_cfg.height * 0.005)
        assert pinch_delta["changed_pixels"] > min_changed_pixels, pinch_delta
        assert close_delta["changed_pixels"] > min_changed_pixels, close_delta
        assert release_delta["changed_pixels"] > min_changed_pixels, release_delta

        sim_status = tools.robot.sim_status() if hasattr(tools.robot, "sim_status") else {}
        summary_path = frame_dir / "summary.json"
        summary = {
            "ok": True,
            "scenario": "sim_pick_place_calibration",
            "source_square": source_square,
            "target_square": target_square,
            "sim_camera_profile": args.sim_camera_profile,
            "sim_camera_profile_overrides": (
                str(args.sim_camera_profile_overrides.expanduser().resolve())
                if args.sim_camera_profile_overrides
                else None
            ),
            "profile_overrides": camera_overrides,
            "summary_path": str(summary_path),
            "piece_square_transition": {
                "source_capture_labels": [
                    open_capture["label"],
                    source_hover_capture["label"],
                    pinch_capture["label"],
                    closed_capture["label"],
                ],
                "source_square": source_square,
                "release_capture_label": release_capture["label"],
                "release_square": release_meta["piece_square"],
            },
            "frame_dir": str(frame_dir),
            "captures": captures,
            "piece_visibility": summarize_piece_visibility(captures),
            "tool_results": tool_results,
            "frame_deltas": {
                "open_to_pinched": pinch_delta,
                "pinched_to_closed": close_delta,
                "closed_to_released": release_delta,
            },
            "sim_status": sim_status,
            "notes": [
                "Joint-state simulation does not model chess-piece contact; close_gripper should reach its target without reporting a gripped object.",
                "Synthetic frames currently visualize board, piece, and gripper opening, while joint-space pick/place movement is asserted through tool readbacks and metadata.",
                "piece_visibility is a synthetic geometry signal from capture metadata; it is evidence-only and not a real-camera segmentation score.",
            ],
        }
        summary_path.write_text(json.dumps(summary, indent=2))
    finally:
        if camera.is_connected:
            camera.disconnect()
        tools.disconnect_robot()

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
