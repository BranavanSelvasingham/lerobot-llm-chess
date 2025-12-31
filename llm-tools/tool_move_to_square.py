"""Tool: move_to_square - position gripper above a chess square via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import reach_square as skill_reach_square

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "move_to_square",
        "description": (
            "Move the gripper above a chess square. Use this to position before picking up a piece. "
            "After calling this, check the camera to verify the piece is centered between the gripper jaws. "
            "If not centered, use nudge_gripper to adjust, then close_gripper to grasp."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "square": {
                    "type": "string",
                    "description": "Target square (e.g. 'e4')"
                },
                "height": {
                    "type": "string",
                    "enum": ["hover", "low"],
                    "description": "hover = above piece (~80mm), low = at piece level (~20mm for grasping)"
                },
            },
            "required": ["square"],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute move_to_square via Skill API (reach_square)."""
    square = str(args.get("square", "")).strip()
    height = str(args.get("height", "hover")).strip().lower()
    
    # Map height parameter to approach_height_mm
    if height == "low":
        # At piece level for grasping (~20mm above board surface)
        approach_height_mm = 20.0
    else:
        # Hover above (~80mm above board)
        approach_height_mm = 80.0
    
    result = skill_reach_square(tools, square, approach_height_mm=approach_height_mm)
    
    # Add backward-compatible fields
    result["height"] = height
    
    return result
