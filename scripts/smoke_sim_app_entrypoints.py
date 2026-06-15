#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    select_ranked_sim_camera_profile_overrides,
)
from llm_toolkit import AppConfig, KinematicsTools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test the chess UI/tool simulator entrypoints without hardware."
    )
    parser.add_argument(
        "--frame-out",
        type=Path,
        default=REPO_ROOT / "artifacts" / "sim" / "smoke_sim_app_frame.jpg",
        help="Path for a captured synthetic camera frame artifact.",
    )
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
    parser.add_argument(
        "--sim-calibration-session-summary",
        type=Path,
        default=None,
        help=(
            "Ranked simulator calibration session_summary.json. Selects a candidate "
            "profile override by rank or candidate id."
        ),
    )
    parser.add_argument(
        "--sim-calibration-rank",
        type=int,
        default=1,
        help="1-based ranking entry to select from --sim-calibration-session-summary.",
    )
    parser.add_argument(
        "--sim-calibration-candidate-id",
        default=None,
        help="Candidate id to select from --sim-calibration-session-summary. When set, rank is ignored.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.sim_camera_profile_overrides and args.sim_calibration_session_summary:
        print(
            "ERROR: --sim-calibration-session-summary cannot be combined with "
            "--sim-camera-profile-overrides",
            file=sys.stderr,
        )
        return 2
    if (args.sim_calibration_rank != 1 or args.sim_calibration_candidate_id) and not args.sim_calibration_session_summary:
        print(
            "ERROR: --sim-calibration-rank and --sim-calibration-candidate-id require "
            "--sim-calibration-session-summary",
            file=sys.stderr,
        )
        return 2

    selected_calibration: dict[str, object] | None = None
    sim_camera_profile = str(args.sim_camera_profile) if args.sim_camera_profile else None
    try:
        if args.sim_camera_profile_overrides:
            camera_overrides = load_sim_camera_profile_overrides(args.sim_camera_profile_overrides)
        elif args.sim_calibration_session_summary:
            selection = select_ranked_sim_camera_profile_overrides(
                args.sim_calibration_session_summary,
                rank=int(args.sim_calibration_rank),
                candidate_id=str(args.sim_calibration_candidate_id) if args.sim_calibration_candidate_id else None,
            )
            if sim_camera_profile is not None and sim_camera_profile != selection.base_profile:
                raise ValueError(
                    f"--sim-camera-profile {sim_camera_profile!r} does not match selected candidate "
                    f"base_profile {selection.base_profile!r}"
                )
            sim_camera_profile = selection.base_profile
            camera_overrides = selection.profile_overrides
            selected_calibration = {
                "summary_path": str(selection.summary_path),
                "rank": int(selection.rank),
                "candidate_id": selection.candidate_id,
                "candidate_path": str(selection.candidate_path),
                "candidate_artifact_dir": selection.candidate_artifact_dir,
                "base_profile": selection.base_profile,
            }
        else:
            camera_overrides = {}
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    cfg = AppConfig(
        port=None,
        robot_id="so101_sim_smoke",
        sim=True,
        camera_width=int(args.width),
        camera_height=int(args.height),
        camera_fps=int(args.fps),
    )

    tools = KinematicsTools(cfg)
    try:
        assert tools.robot is not None, "sim robot was not created"
        assert tools.robot.is_connected, "sim robot did not connect"

        joints = tools.execute_tool("read_joints", {"include_gripper": True})
        assert joints.get("ok") is True, joints
        assert joints["joints"]["gripper"] is not None, joints

        moved = tools.execute_tool(
            "move_joints",
            {
                "shoulder_pan": 7.0,
                "wrist_roll": 12.0,
                "gripper": 55.0,
                "max_step_deg": 15.0,
            },
        )
        assert moved.get("ok") is True, moved
        assert abs(float(moved["after"]["shoulder_pan"]) - 7.0) < 1e-6, moved
        assert abs(float(moved["after"]["gripper"]) - 55.0) < 1e-6, moved

        if sim_camera_profile:
            camera_cfg = make_sim_camera_config_from_profile(
                sim_camera_profile, **camera_overrides
            )
        else:
            camera_values = {
                "width": int(args.width),
                "height": int(args.height),
                "fps": int(args.fps),
                "color_mode": ColorMode.BGR,
                "view": "gripper",
            }
            camera_cfg = SimCameraConfig(**{**camera_values, **camera_overrides})
        camera = SimCamera(camera_cfg)
        try:
            camera.connect(warmup=True)
            frame = camera.async_read()
            expected_shape = (int(camera_cfg.height), int(camera_cfg.width), 3)
            assert frame.shape == expected_shape, frame.shape
            assert frame.dtype == np.uint8, frame.dtype
            assert len(np.unique(frame.reshape(-1, 3), axis=0)) >= 12
            metadata = camera.calibration_metadata()

            frame_out = args.frame_out.expanduser().resolve()
            frame_out.parent.mkdir(parents=True, exist_ok=True)
            ok = cv2.imwrite(str(frame_out), frame)
            assert ok, f"cv2 failed to write {frame_out}"
        finally:
            if camera.is_connected:
                camera.disconnect()
    finally:
        tools.disconnect_robot()

    print(
        json.dumps(
            {
                "ok": True,
                "robot": "sim_so101",
                "sim_camera_profile": sim_camera_profile,
                "sim_camera_profile_overrides": (
                    str(args.sim_camera_profile_overrides.expanduser().resolve())
                    if args.sim_camera_profile_overrides
                    else None
                ),
                "sim_calibration_session_summary": (
                    str(args.sim_calibration_session_summary.expanduser().resolve())
                    if args.sim_calibration_session_summary
                    else None
                ),
                "selected_calibration": selected_calibration,
                "profile_overrides": camera_overrides,
                "frame": str(frame_out),
                "shape": [int(value) for value in frame.shape],
                "camera": {
                    "width": int(camera_cfg.width),
                    "height": int(camera_cfg.height),
                    "fps": int(camera_cfg.fps),
                    "view": str(camera_cfg.view),
                    "piece_square": str(camera_cfg.piece_square),
                    "piece_layout": str(camera_cfg.piece_layout),
                    "gripper_visible": bool(camera_cfg.gripper_visible),
                    "metadata": metadata,
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
