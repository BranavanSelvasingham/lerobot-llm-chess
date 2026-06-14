#!/usr/bin/env python

"""Small simulation backends for hardware-free SO-101 chess development."""

from .camera import SimCamera
from .config import SimCameraConfig, SimRobotConfig

__all__ = [
    "SO101_BODY_JOINTS",
    "SO101_JOINTS",
    "SimCamera",
    "SimCameraConfig",
    "SimRobot",
    "SimRobotConfig",
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
