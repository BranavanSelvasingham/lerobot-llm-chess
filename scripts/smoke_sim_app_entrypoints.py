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
    parser.add_argument(
        "--metadata-out",
        type=Path,
        default=None,
        help="Optional path for the app-facing SimCamera metadata contract sidecar JSON.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="Optional path for the full app-entrypoint smoke summary JSON.",
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


def _finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _finite_matrix(value: Any, *, rows: int, columns: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == rows
        and all(
            isinstance(row, list)
            and len(row) == columns
            and all(_finite_number(item) for item in row)
            for row in value
        )
    )


def _finite_vector(value: Any, *, length: int) -> bool:
    return isinstance(value, list) and len(value) == length and all(_finite_number(item) for item in value)


def _string_field(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_metadata_contract(
    *,
    metadata: dict[str, Any],
    frame: np.ndarray,
    robot_state: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, details: dict[str, Any] | None = None) -> None:
        entry: dict[str, Any] = {"name": name, "ok": bool(ok)}
        if details:
            entry["details"] = details
        checks.append(entry)

    frame_height, frame_width = int(frame.shape[0]), int(frame.shape[1])
    image_size = metadata.get("image_size_px")
    record(
        "image_size_matches_frame",
        isinstance(image_size, dict)
        and image_size.get("width") == frame_width
        and image_size.get("height") == frame_height,
        {"metadata": image_size, "frame_shape": [frame_height, frame_width, int(frame.shape[2])]},
    )

    matrix = metadata.get("camera_matrix_px")
    record("camera_matrix_px_3x3", _finite_matrix(matrix, rows=3, columns=3))

    intrinsics = metadata.get("intrinsics")
    nested_matrix = intrinsics.get("camera_matrix_px") if isinstance(intrinsics, dict) else None
    record(
        "intrinsics_match_camera_matrix",
        isinstance(intrinsics, dict)
        and _string_field(intrinsics.get("schema"))
        and _string_field(intrinsics.get("model"))
        and _finite_matrix(matrix, rows=3, columns=3)
        and nested_matrix == matrix
        and _finite_number(intrinsics.get("fx_px"))
        and _finite_number(intrinsics.get("fy_px"))
        and _finite_number(intrinsics.get("cx_px"))
        and _finite_number(intrinsics.get("cy_px"))
        and _finite_number(intrinsics.get("skew_px"))
        and intrinsics.get("fx_px") == matrix[0][0]
        and intrinsics.get("fy_px") == matrix[1][1]
        and intrinsics.get("cx_px") == matrix[0][2]
        and intrinsics.get("cy_px") == matrix[1][2]
        and intrinsics.get("skew_px") == matrix[0][1],
    )

    coefficients = metadata.get("distortion_coefficients")
    order = metadata.get("distortion_coefficient_order")
    record(
        "distortion_coefficients_match_order",
        isinstance(coefficients, list)
        and isinstance(order, list)
        and len(coefficients) == len(order)
        and len(coefficients) > 0
        and all(_finite_number(value) for value in coefficients)
        and all(_string_field(value) for value in order)
        and _string_field(metadata.get("distortion_model")),
        {"coefficient_count": len(coefficients) if isinstance(coefficients, list) else None},
    )

    extrinsics = metadata.get("extrinsics")
    board_to_camera = extrinsics.get("board_to_camera") if isinstance(extrinsics, dict) else None
    record(
        "extrinsics_board_to_camera_pose",
        isinstance(board_to_camera, dict)
        and _string_field(board_to_camera.get("schema"))
        and _string_field(board_to_camera.get("name"))
        and _string_field(board_to_camera.get("source"))
        and _string_field(board_to_camera.get("from_frame"))
        and _string_field(board_to_camera.get("to_frame"))
        and _finite_matrix(board_to_camera.get("rotation_matrix"), rows=3, columns=3)
        and _finite_vector(board_to_camera.get("translation_m"), length=3),
    )

    convention = metadata.get("coordinate_frame_convention")
    record(
        "coordinate_frame_convention_notes",
        isinstance(convention, dict)
        and _string_field(convention.get("scope"))
        and _string_field(convention.get("image_frame"))
        and _string_field(convention.get("camera_frame"))
        and _string_field(convention.get("board_frame"))
        and _string_field(convention.get("extrinsics"))
        and isinstance(convention.get("board_corners_xy_order"), list)
        and len(convention.get("board_corners_xy_order")) == 4,
    )

    board_corners = metadata.get("board_corners_xy")
    record(
        "board_corners_four_2d_points",
        isinstance(board_corners, list)
        and len(board_corners) == 4
        and all(_finite_vector(corner, length=2) for corner in board_corners),
    )

    record(
        "piece_and_target_metadata",
        _string_field(metadata.get("view"))
        and _string_field(metadata.get("piece_layout"))
        and _string_field(metadata.get("piece_square"))
        and isinstance(metadata.get("gripper_visible"), bool)
        and isinstance(metadata.get("track_robot_gripper"), bool),
        {
            "view": metadata.get("view"),
            "piece_layout": metadata.get("piece_layout"),
            "piece_square": metadata.get("piece_square"),
        },
    )

    metadata_robot_state = metadata.get("robot_joints")
    expected_gripper = robot_state.get("gripper")
    actual_gripper = metadata.get("tracked_gripper_percent")
    record(
        "robot_gripper_state_represented",
        isinstance(metadata_robot_state, dict)
        and bool(metadata_robot_state)
        and "gripper" in metadata_robot_state
        and _finite_number(metadata_robot_state.get("gripper"))
        and _finite_number(expected_gripper)
        and _finite_number(actual_gripper)
        and abs(float(actual_gripper) - float(expected_gripper)) < 1e-9
        and _finite_number(metadata.get("current_gripper_opening_px"))
        and float(metadata.get("current_gripper_opening_px")) > 0.0,
        {"tracked_gripper_percent": actual_gripper, "expected_gripper": expected_gripper},
    )

    failed = [check for check in checks if not check["ok"]]
    contract = {
        "ok": not failed,
        "schema": "lerobot.sim.app_entrypoint_camera_metadata_contract.v1",
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "checks": checks,
    }
    if failed:
        raise AssertionError(f"SimCamera metadata contract failed: {json.dumps(failed, indent=2)}")
    return contract


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
            camera.set_robot_state(moved["after"])
            camera.connect(warmup=True)
            frame = camera.async_read()
            expected_shape = (int(camera_cfg.height), int(camera_cfg.width), 3)
            assert frame.shape == expected_shape, frame.shape
            assert frame.dtype == np.uint8, frame.dtype
            assert len(np.unique(frame.reshape(-1, 3), axis=0)) >= 12
            metadata = camera.calibration_metadata()
            metadata_contract = _check_metadata_contract(
                metadata=metadata,
                frame=frame,
                robot_state=moved["after"],
            )

            frame_out = args.frame_out.expanduser().resolve()
            frame_out.parent.mkdir(parents=True, exist_ok=True)
            ok = cv2.imwrite(str(frame_out), frame)
            assert ok, f"cv2 failed to write {frame_out}"
        finally:
            if camera.is_connected:
                camera.disconnect()
    finally:
        tools.disconnect_robot()

    metadata_out: Path | None = None
    metadata_sidecar_payload = {
        "ok": True,
        "camera_metadata_contract": metadata_contract,
        "camera_metadata": metadata,
        "frame": str(frame_out),
    }
    if args.metadata_out:
        metadata_out = args.metadata_out.expanduser().resolve()
        metadata_out.parent.mkdir(parents=True, exist_ok=True)
        metadata_out.write_text(json.dumps(metadata_sidecar_payload, indent=2) + "\n")

    summary_payload = {
        "ok": True,
        "status": "ok",
        "robot": "sim_so101",
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "skipped_markers": {
            "hardware": "Sim smoke uses KinematicsTools with sim=True and never opens a robot serial port.",
            "gui": "Sim smoke captures a synthetic frame directly and never opens a GUI/display flow.",
            "openai": "Sim smoke exercises local tool entrypoints only and never creates an OpenAI client.",
        },
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
        "metadata": str(metadata_out) if metadata_out else None,
        "shape": [int(value) for value in frame.shape],
        "camera": {
            "width": int(camera_cfg.width),
            "height": int(camera_cfg.height),
            "fps": int(camera_cfg.fps),
            "view": str(camera_cfg.view),
            "piece_square": str(camera_cfg.piece_square),
            "piece_layout": str(camera_cfg.piece_layout),
            "gripper_visible": bool(camera_cfg.gripper_visible),
            "metadata_contract": metadata_contract,
            "metadata": metadata,
        },
    }

    if args.summary_out:
        summary_out = args.summary_out.expanduser().resolve()
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(summary_payload, indent=2) + "\n")

    print(json.dumps(summary_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
