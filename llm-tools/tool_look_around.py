"""Tool: look_around - move camera to search for target via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import move_delta as skill_move_delta

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "look_around",
        "description": (
            "Move the gripper-mounted camera one step to search for a target (e.g., a pawn). "
            "Call this tool repeatedly one step at a time (left/right/up/down) and STOP once the target is in view. "
            "This performs a small planar move at the current height (dz=0)."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["left", "right", "up", "down"],
                    "description": "Direction to move the camera view by one step.",
                },
                "step_mm": {
                    "type": "number",
                    "description": "Step size in mm (default 25).",
                },
            },
            "required": ["direction"],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute look_around via Skill API (move_delta)."""
    direction = str(args.get("direction", "")).strip().lower()
    step_mm = float(args.get("step_mm", 25.0))
    if step_mm <= 0:
        step_mm = 25.0
    
    # Map view directions to delta moves:
    # - left/right -> tangential (dy_mm)
    # - up/down -> radial (dx_mm)
    dx_mm = 0.0
    dy_mm = 0.0
    if direction == "left":
        dy_mm = +step_mm
    elif direction == "right":
        dy_mm = -step_mm
    elif direction == "up":
        dx_mm = +step_mm
    elif direction == "down":
        dx_mm = -step_mm
    else:
        return {"ok": False, "error": f"Invalid direction: {direction!r}"}
    
    res = skill_move_delta(tools, dx_mm=dx_mm, dy_mm=dy_mm, dz_mm=0.0)
    
    return {
        "ok": bool(res.get("ok", False)),
        "skill": "look_around",
        "direction": direction,
        "step_mm": float(step_mm),
        "move_args": {"dx_mm": dx_mm, "dy_mm": dy_mm, "dz_mm": 0.0},
        "move_result": res,
        "note": "Call look_around one step at a time and stop when the target is visible.",
    }
