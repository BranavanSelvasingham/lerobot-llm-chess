"""Tool: set_gripper_percent - set gripper opening percentage via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import set_gripper as skill_set_gripper

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "set_gripper_percent",
        "description": (
            "Set gripper opening percent. NOTE on this robot: 0=fully CLOSED, 100=fully OPEN. "
            "Use ~90-100 to open, ~10-30 to grip a piece."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {"percent": {"type": "number"}},
            "required": ["percent"],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute set_gripper_percent via Skill API (set_gripper)."""
    percent = float(args.get("percent", 0.0))
    
    result = skill_set_gripper(tools, percent=percent)
    
    # Add backward-compatible fields
    result["percent_requested"] = percent
    result["gripper_before"] = {"gripper": result.get("before")}
    result["gripper_after"] = {"gripper": result.get("after")}
    
    # Compute delta and moved
    before = result.get("before")
    after = result.get("after")
    if before is not None and after is not None:
        delta = float(after) - float(before)
        result["delta"] = delta
        result["moved"] = bool(abs(delta) >= 1.0)
    else:
        result["delta"] = None
        result["moved"] = None
    
    return result
