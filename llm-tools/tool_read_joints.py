"""Tool: read_joints - read current joint positions via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import read_joints as skill_read_joints

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "read_joints",
        "description": (
            "Read the robot's current joint positions. "
            "Body joints are in degrees. Gripper is in 0..100 units (robot-specific semantics)."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "include_gripper": {"type": "boolean", "description": "Include gripper readback (default true)."},
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute read_joints via Skill API."""
    include_gripper = bool(args.get("include_gripper", True))
    
    result = skill_read_joints(tools, include_gripper=include_gripper)
    
    # Add backward-compatible fields
    result["torque_disabled"] = bool(getattr(tools, "torque_disabled", False))
    
    return result
