"""Tool: move_joints - directly command joint targets via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import move_joints as skill_move_joints

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


_BODY_JOINTS: list[str] = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "move_joints",
        "description": (
            "Directly command joint targets (joint-space control). "
            "More reliable than IK for this robot. "
            "To extend/retract: change shoulder_lift and elbow_flex in OPPOSITE directions (~5° each), adjust wrist_flex to keep gripper down. "
            "To move left/right: change shoulder_pan alone. "
            "Body joints are degrees, gripper is 0..100. "
            "Use small changes and check camera feedback."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "shoulder_pan": {"type": "number"},
                "shoulder_lift": {"type": "number"},
                "elbow_flex": {"type": "number"},
                "wrist_flex": {"type": "number"},
                "wrist_roll": {"type": "number"},
                "gripper": {"type": "number"},
                "relative": {
                    "type": "boolean",
                    "description": "If true, treat provided values as deltas (degrees or gripper units).",
                },
                "max_step_deg": {
                    "type": "number",
                    "description": "Safety clamp per-call for body joint deltas in degrees (default 15).",
                },
                "sleep_s": {
                    "type": "number",
                    "description": "Seconds to wait before reading back joints (default 0.25).",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute move_joints via Skill API."""
    relative = bool(args.get("relative", False))
    max_step_deg = float(args.get("max_step_deg", 15.0))
    max_step_deg = float(np.clip(max_step_deg, 1.0, 45.0))
    
    # Build target dict from provided keys
    targets: dict[str, float] = {}
    for j in _BODY_JOINTS + ["gripper"]:
        if j in args and args[j] is not None:
            try:
                targets[j] = float(args[j])
            except Exception:
                pass
    
    if not targets:
        return {"ok": False, "error": "No joint targets provided."}
    
    result = skill_move_joints(tools, targets, relative=relative, max_step_deg=max_step_deg)
    
    # Add backward-compatible fields
    result["action_sent"] = {"targets": result.get("sent", {})}
    
    return result
