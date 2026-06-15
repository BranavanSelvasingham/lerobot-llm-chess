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
    frame_path = frame_dir / f"{index:02d}_{label}.jpg"
    ok = cv2.imwrite(str(frame_path), frame)
    assert ok, f"cv2 failed to write {frame_path}"

    return frame, {
        "label": label,
        "path": str(frame_path),
        "joints": joints,
        "metadata": metadata,
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
