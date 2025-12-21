"""Tool: nudge_gripper - small position adjustment for alignment."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "nudge_gripper",
        "description": (
            "Make a small adjustment to gripper position for fine alignment. "
            "Use this after move_to_square if the piece is not centered in the camera view. "
            "Directions are relative to the camera view: left/right moves the gripper sideways, "
            "forward/back moves toward/away from the robot base."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["left", "right", "forward", "back", "up", "down"],
                    "description": "Direction to nudge"
                },
                "distance_mm": {
                    "type": "number",
                    "description": "Distance to move in mm (default 10)"
                },
            },
            "required": ["direction"],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    direction = str(args.get("direction", "")).strip().lower()
    distance_mm = float(args.get("distance_mm", 10.0))
    distance_m = distance_mm / 1000.0
    
    with tools._lock:
        tools._require_kin()
        
        # Get current position
        T_now = tools.get_ee_pose()
        xyz_now = T_now[:3, 3].astype(float)
        R_fixed = T_now[:3, :3].astype(float)
        
        # Compute delta based on direction
        # Note: In robot base frame, X is forward, Y is left, Z is up
        delta = np.array([0.0, 0.0, 0.0])
        
        if direction == "forward":
            delta[0] = distance_m
        elif direction == "back":
            delta[0] = -distance_m
        elif direction == "left":
            delta[1] = distance_m
        elif direction == "right":
            delta[1] = -distance_m
        elif direction == "up":
            delta[2] = distance_m
        elif direction == "down":
            delta[2] = -distance_m
        else:
            return {"ok": False, "error": f"Unknown direction: {direction}"}
        
        target_xyz = xyz_now + delta
        
        # Move to new position
        res = tools._move_ee_to(xyz_m=target_xyz, R_fixed=R_fixed, gripper_pos=None)
        
        # Wait for motors to stop
        stopped = tools.wait_until_motors_stopped(timeout_s=3.0)
        
        return {
            "ok": res.get("ok", False),
            "direction": direction,
            "distance_mm": float(distance_mm),
            "from_xyz_mm": [float(x * 1000) for x in xyz_now],
            "to_xyz_mm": [float(x * 1000) for x in target_xyz],
            "motors_stopped": stopped,
        }
