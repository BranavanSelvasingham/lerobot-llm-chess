# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Helper to recalibrate your device (robot or teleoperator).

Example:

```shell
lerobot-calibrate \
    --robot.type=so101_follower \
    --robot.port=/dev/tty.usbmodemXXXX \
    --robot.id=so101_chess \
    --robot.use_degrees=true \
    --prune_pose_files=true \
    --record_standard_poses=true
```
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from pprint import pformat
from typing import Any

import draccus

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig  # noqa: F401
from lerobot.robots import (  # noqa: F401
    Robot,
    RobotConfig,
    hope_jr,
    koch_follower,
    make_robot_from_config,
    so101_follower,
    viperx,
)
from lerobot.utils.utils import init_logging


# Pose artifacts that become confusing / stale after (re)calibration.
# These are safe to delete because they are derived from calibrated joint coordinates.
_POSE_ARTIFACT_FILENAMES: tuple[str, ...] = (
    "home_joints.npy",
    "home_position.json",
    "saved_positions.json",
    "chess_corner_motors.json",
    "chess_coordinate_system.json",
)

# A small set of "standard" SO-101 poses we can record right after calibration.
_SO101_STANDARD_POSES: tuple[tuple[str, str], ...] = (
    ("rest_position", "Saved position: rest_position"),
    ("ready_position", "Saved position: ready_position"),
    ("bird's_eye_view", "A bird's eye view of the chess board"),
)


def _extract_motor_positions_from_observation(obs: dict[str, Any]) -> dict[str, float]:
    """Extract {motor_name: position} from a robot observation dict."""
    motor_positions: dict[str, float] = {}
    for k, v in (obs or {}).items():
        if not isinstance(k, str) or not k.endswith(".pos"):
            continue
        name = k.removesuffix(".pos")
        try:
            motor_positions[name] = float(v)
        except Exception:
            continue
    return motor_positions


def _guess_motor_order(device: Any, motor_positions: dict[str, float]) -> list[str]:
    """Best-effort stable motor ordering for pose files."""
    try:
        bus = getattr(device, "bus", None)
        motors = getattr(bus, "motors", None)
        if isinstance(motors, dict) and motors:
            return list(motors.keys())
    except Exception:
        pass
    return sorted(motor_positions.keys())


def _delete_pose_artifacts(calibration_dir: Path) -> dict[str, Any]:
    removed: list[str] = []
    failed: dict[str, str] = {}
    for fname in _POSE_ARTIFACT_FILENAMES:
        p = calibration_dir / fname
        try:
            if p.exists():
                p.unlink()
                removed.append(fname)
        except Exception as e:
            failed[fname] = str(e)
    return {"removed": removed, "failed": failed}


def _record_so101_standard_poses(device: Robot, calibration_dir: Path, *, overwrite: bool) -> Path:
    """Interactively record a few standard SO-101 poses into saved_positions.json."""
    out_path = calibration_dir / "saved_positions.json"
    if out_path.exists() and not overwrite:
        raise FileExistsError(
            f"{out_path} already exists. Use --pose_file_overwrite=true or delete it first."
        )

    now = datetime.now().isoformat(timespec="seconds")
    poses_out: dict[str, Any] = {"_meta": {"recorded_at": now, "robot_id": str(getattr(device, "id", ""))}}
    for pose_name, desc in _SO101_STANDARD_POSES:
        input(f"\nMove robot to '{pose_name}' ({desc}) then press ENTER to record... ")
        obs = device.get_observation()
        mp = _extract_motor_positions_from_observation(obs)
        if not mp:
            raise RuntimeError("Failed to read motor positions from observation after recording prompt.")
        motor_order = _guess_motor_order(device, mp)
        poses_out[pose_name] = {
            "description": desc,
            "positions": mp,
            "motor_order": motor_order,
            "timestamp": now,
        }

    # Write JSON
    out_path.write_text(json.dumps(poses_out, indent=2))
    return out_path


@dataclass
class CalibrateConfig:
    robot: RobotConfig
    # If true, delete stale pose files that are expressed in calibrated joint coordinates.
    prune_pose_files: bool = False
    # If true, interactively record a small set of SO-101 standard poses (saved_positions.json).
    record_standard_poses: bool = False
    # When recording, overwrite saved_positions.json if it exists.
    pose_file_overwrite: bool = True
    # Skip firmware version check (use if motors have slightly different firmware versions).
    skip_firmware_check: bool = False

    def __post_init__(self):
        if not isinstance(self.robot, RobotConfig):
            raise ValueError("`robot` must be provided (e.g. --robot.type=so101_follower).")
        self.device = self.robot


@draccus.wrap()
def calibrate(cfg: CalibrateConfig):
    init_logging()
    logging.info(pformat(asdict(cfg)))

    # Avoid writing calibration to "None.json" when users forget --robot.id.
    if getattr(cfg.device, "id", None) in (None, ""):
        raise ValueError(
            "Missing --robot.id. Please set a stable id (e.g. --robot.id=so101_chess) "
            "so the calibration is saved under a predictable filename."
        )

    device = make_robot_from_config(cfg.device)

    device.connect(calibrate=False, skip_firmware_check=cfg.skip_firmware_check)
    device.calibrate()

    # Optional: prune stale pose artifacts and/or record standard poses (robots only).
    try:
        if isinstance(device, Robot):
            calib_dir = Path(device.calibration_dir)

            if cfg.prune_pose_files:
                res = _delete_pose_artifacts(calib_dir)
                if res["removed"]:
                    logging.info(f"Removed pose artifacts from {calib_dir}: {res['removed']}")
                if res["failed"]:
                    logging.warning(f"Failed to remove some pose artifacts: {res['failed']}")

            if cfg.record_standard_poses:
                # This is designed for SO-101 (degrees + gripper 0..100). Warn if the robot isn't in degrees mode.
                try:
                    use_degrees = bool(getattr(getattr(device, "config", None), "use_degrees", True))
                    if not use_degrees:
                        logging.warning(
                            "Recording standard poses while use_degrees=False. "
                            "Pose values may not match chess tools that assume degrees."
                        )
                except Exception:
                    pass

                saved_path = _record_so101_standard_poses(device, calib_dir, overwrite=cfg.pose_file_overwrite)
                logging.info(f"Recorded standard poses to {saved_path}")
    finally:
        device.disconnect()


def main():
    calibrate()


if __name__ == "__main__":
    main()
