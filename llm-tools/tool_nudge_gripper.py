"""Tool: nudge_gripper - small position adjustment for alignment via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import nudge as skill_nudge

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
    """Execute nudge_gripper via Skill API (nudge)."""
    direction = str(args.get("direction", "")).strip().lower()
    distance_mm = float(args.get("distance_mm", 10.0))
    
    return skill_nudge(tools, direction=direction, distance_mm=distance_mm)
