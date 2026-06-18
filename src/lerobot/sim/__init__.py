#!/usr/bin/env python

"""Small simulation backends for hardware-free SO-101 chess development."""

from .camera import SimCamera
from .app_status import (
    SIM_CAMERA_STATUS_SCHEMA,
    format_sim_camera_status,
    summarize_sim_camera_status,
)
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
from .session_picker import (
    RankedSimCalibrationCandidate,
    RankedSimCalibrationSession,
    load_ranked_sim_calibration_session,
)

__all__ = [
    "CURRENT_GRIPPER_REFERENCE_PROFILE",
    "SO101_BODY_JOINTS",
    "SO101ChessEnv",
    "SO101ChessEnvConfig",
    "SO101DevelopmentMJCFConfig",
    "SO101_JOINTS",
    "SO101_DEV_MJCF_AUTHORITY",
    "SO101_DEV_MJCF_SCHEMA",
    "SIM_CAMERA_CALIBRATION_PROFILES",
    "RankedSimCalibrationCandidate",
    "RankedSimCalibrationSession",
    "RankedSimCameraProfileSelection",
    "SIM_CAMERA_STATUS_SCHEMA",
    "SimCamera",
    "SimCameraConfig",
    "SimRobot",
    "SimRobotConfig",
    "action_toward_targets",
    "build_so101_development_mjcf",
    "write_so101_development_mjcf",
    "format_sim_camera_status",
    "load_ranked_sim_calibration_session",
    "load_ranked_sim_camera_profile_overrides",
    "load_sim_camera_profile_overrides",
    "make_sim_camera_config_from_profile",
    "select_ranked_sim_camera_profile_overrides",
    "scripted_pick_place_waypoints",
    "square_index",
    "square_to_indices",
    "summarize_sim_camera_status",
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
    if name in {
        "SO101ChessEnv",
        "SO101ChessEnvConfig",
        "action_toward_targets",
        "scripted_pick_place_waypoints",
        "square_index",
        "square_to_indices",
    }:
        from .chess_env import (
            SO101ChessEnv,
            SO101ChessEnvConfig,
            action_toward_targets,
            scripted_pick_place_waypoints,
            square_index,
            square_to_indices,
        )

        values = {
            "SO101ChessEnv": SO101ChessEnv,
            "SO101ChessEnvConfig": SO101ChessEnvConfig,
            "action_toward_targets": action_toward_targets,
            "scripted_pick_place_waypoints": scripted_pick_place_waypoints,
            "square_index": square_index,
            "square_to_indices": square_to_indices,
        }
        return values[name]
    if name in {
        "SO101DevelopmentMJCFConfig",
        "SO101_DEV_MJCF_AUTHORITY",
        "SO101_DEV_MJCF_SCHEMA",
        "build_so101_development_mjcf",
        "write_so101_development_mjcf",
    }:
        from .mujoco_scene import (
            SO101_DEV_MJCF_AUTHORITY,
            SO101_DEV_MJCF_SCHEMA,
            SO101DevelopmentMJCFConfig,
            build_so101_development_mjcf,
            write_so101_development_mjcf,
        )

        values = {
            "SO101DevelopmentMJCFConfig": SO101DevelopmentMJCFConfig,
            "SO101_DEV_MJCF_AUTHORITY": SO101_DEV_MJCF_AUTHORITY,
            "SO101_DEV_MJCF_SCHEMA": SO101_DEV_MJCF_SCHEMA,
            "build_so101_development_mjcf": build_so101_development_mjcf,
            "write_so101_development_mjcf": write_so101_development_mjcf,
        }
        return values[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
