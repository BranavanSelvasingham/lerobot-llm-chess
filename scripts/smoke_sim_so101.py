#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.robots.utils import make_robot_from_config
from lerobot.sim import SimCameraConfig, SimRobotConfig


def main() -> int:
    reference_image = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
    camera_cfg = SimCameraConfig(
        width=320,
        height=240,
        fps=15,
        view="gripper",
        reference_image_path=reference_image,
    )
    cameras = make_cameras_from_configs({"board": camera_cfg})
    camera = cameras["board"]
    camera.connect()
    frame = camera.read()
    assert frame.shape == (240, 320, 3), frame.shape
    assert frame.dtype == np.uint8, frame.dtype
    assert len(np.unique(frame.reshape(-1, 3), axis=0)) >= 12
    bottom_center = frame[210:240, 125:195]
    assert bottom_center.mean() > frame[:40, :40].mean(), "expected visible gripper occlusion"
    metadata = camera.calibration_metadata()
    assert metadata["view"] == "gripper", metadata
    assert len(metadata["board_corners_xy"]) == 4, metadata
    camera.disconnect()

    robot_cfg = SimRobotConfig(
        cameras={"board": camera_cfg},
        initial_positions={"shoulder_pan": 1.0, "gripper": 80.0},
        use_mujoco=True,
    )
    robot = make_robot_from_config(robot_cfg)
    robot.connect()
    assert robot.is_connected
    assert robot.is_calibrated

    sent = robot.send_action({"shoulder_pan.pos": 12.5, "wrist_roll.pos": 30.0, "gripper.pos": 42.0})
    assert sent == {"shoulder_pan.pos": 12.5, "wrist_roll.pos": 30.0, "gripper.pos": 42.0}, sent

    obs = robot.get_observation()
    assert obs["shoulder_pan.pos"] == 12.5, obs["shoulder_pan.pos"]
    assert obs["wrist_roll.pos"] == 30.0, obs["wrist_roll.pos"]
    assert obs["gripper.pos"] == 42.0, obs["gripper.pos"]
    assert obs["board"].shape == (240, 320, 3), obs["board"].shape
    assert obs["board"].dtype == np.uint8, obs["board"].dtype
    assert robot.cameras["board"].calibration_metadata()["reference_image_path"] == str(reference_image)

    moving = robot.bus.sync_read("Moving")
    assert all(value == 0 for value in moving.values()), moving

    status = robot.sim_status()
    assert status["fallback"] == "joint_state", status
    robot.disconnect()

    print("sim smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
