#!/usr/bin/env python

"""Small simulation backends for hardware-free SO-101 chess development."""

from .camera import SimCamera
from .config import (
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    RankedSimCameraProfileSelection,
    SimCameraConfig,
    SimRobotConfig,
    load_ranked_sim_camera_profile_overrides,
    load_sim_camera_profile_overrides,
    make_sim_camera_config_from_profile,
    select_ranked_sim_camera_profile_overrides,
)

__all__ = [
    "CURRENT_GRIPPER_REFERENCE_PROFILE",
    "SO101_BODY_JOINTS",
    "SO101_JOINTS",
    "SIM_CAMERA_CALIBRATION_PROFILES",
    "RankedSimCameraProfileSelection",
    "SimCamera",
    "SimCameraConfig",
    "SimRobot",
    "SimRobotConfig",
    "load_ranked_sim_camera_profile_overrides",
    "load_sim_camera_profile_overrides",
    "make_sim_camera_config_from_profile",
    "select_ranked_sim_camera_profile_overrides",
]


def __getattr__(name: str):
    if name in {"SO101_BODY_JOINTS", "SO101_JOINTS", "SimRobot"}:
        from .robot import SO101_BODY_JOINTS, SO101_JOINTS, SimRobot

        values = {
            "SO101_BODY_JOINTS": SO101_BODY_JOINTS,
            "SO101_JOINTS": SO101_JOINTS,
            "SimRobot": SimRobot,
        }
        return values[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
