"""Tool: go_birds_eye - move to bird's eye view position for board observation."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools

_SO101_AND_GRIPPER = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "go_birds_eye",
        "description": (
            "Move the robot arm to bird's eye view position to observe the full chessboard. "
            "Use this before analyzing the board state or when you need to see all pieces."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    _ = args
    with tools._lock:
        targets: dict[str, float] = {}
        
        # Load bird's_eye_view from saved_positions.json
        saved_positions_path = tools.home_position_path.with_name("saved_positions.json")
        if not saved_positions_path.is_file():
            raise RuntimeError(
                f"No saved_positions.json found at {saved_positions_path}. "
                "Run setup_birds_eye_view.py first."
            )
        
        try:
            obj = json.loads(saved_positions_path.read_text())
            birds_eye = (obj.get("bird's_eye_view") or {}).get("positions") or {}
            if not isinstance(birds_eye, dict) or not birds_eye:
                raise RuntimeError(
                    "bird's_eye_view position not found in saved_positions.json. "
                    "Run setup_birds_eye_view.py first."
                )
            
            for j in _SO101_AND_GRIPPER:
                if j in birds_eye:
                    targets[j] = float(birds_eye[j])
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse saved_positions.json: {e}")
        
        if not targets:
            raise RuntimeError("No valid joint positions found in bird's_eye_view.")
        
        tools._send_joint_targets_deg(targets)
        
        return {
            "ok": True,
            "position": "bird's_eye_view",
            "targets_deg": targets,
        }
