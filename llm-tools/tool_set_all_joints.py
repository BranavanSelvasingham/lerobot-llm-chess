"""Tool: set_all_joints - set all joint positions at once via Skill API."""

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


_ALL_MOTORS: list[str] = [
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
        "name": "set_all_joints",
        "description": (
            "Set absolute targets for ALL 6 motors at once (joint-space control). "
            "PREFERRED for board movement: copy CURRENT_JOINTS, then change shoulder_lift and elbow_flex in OPPOSITE directions (~5° each) to extend/retract, adjust wrist_flex to keep gripper down. "
            "Body joints are degrees. Gripper is 0..100 (0=closed, 100=open). "
            "Safety: clamps per-call deltas (15° body, 35 gripper). Returns before/after for closed-loop control."
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
                "max_step_deg": {
                    "type": "number",
                    "description": "Max body-joint change per call in degrees (default 15).",
                },
                "max_step_gripper": {
                    "type": "number",
                    "description": "Max gripper change per call in 0..100 units (default 35).",
                },
                "sleep_s": {
                    "type": "number",
                    "description": "Seconds to wait before reading back joints (default 0.35).",
                },
            },
            "required": list(_ALL_MOTORS),
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute set_all_joints via Skill API (move_joints)."""
    max_step_deg = float(args.get("max_step_deg", 15.0))
    max_step_deg = float(np.clip(max_step_deg, 1.0, 45.0))
    
    # Parse targets (absolute)
    targets: dict[str, float] = {}
    for j in _ALL_MOTORS:
        targets[j] = float(args[j])
    targets["gripper"] = float(np.clip(float(targets["gripper"]), 0.0, 100.0))
    
    result = skill_move_joints(tools, targets, relative=False, max_step_deg=max_step_deg)
    
    # Add backward-compatible fields
    result["torque_disabled"] = bool(getattr(tools, "torque_disabled", False))
    result["action_sent"] = {"targets": result.get("sent", {})}
    
    # Compute delta and moved
    before = result.get("before", {})
    after = result.get("after", {})
    delta: dict[str, float] = {}
    moved: dict[str, bool] = {}
    for j in _ALL_MOTORS:
        b = float(before.get(j, 0.0))
        a = float(after.get(j, 0.0))
        d = float(a - b)
        delta[j] = d
        thresh = 1.0 if j == "gripper" else 0.5
        moved[j] = abs(d) >= thresh
    
    result["delta"] = delta
    result["moved"] = moved
    
    return result
