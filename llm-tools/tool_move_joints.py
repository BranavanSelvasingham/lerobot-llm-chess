from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

import numpy as np

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
    with tools._lock:
        tools._require_robot()

        relative = bool(args.get("relative", False))
        max_step_deg = float(args.get("max_step_deg", 15.0))
        max_step_deg = float(np.clip(max_step_deg, 1.0, 45.0))
        sleep_s = float(args.get("sleep_s", 0.25))
        sleep_s = float(np.clip(sleep_s, 0.0, 2.0))

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

        # Read current state
        read_names = [j for j in _BODY_JOINTS if (j in targets)]
        if "gripper" in targets:
            read_names.append("gripper")
        q_before = tools._read_joints_deg(read_names)  # type: ignore[attr-defined]

        # Convert to absolute targets if relative
        if relative:
            for j, v in list(targets.items()):
                cur = float(q_before.get(j, 0.0))
                targets[j] = cur + float(v)

        # Safety clamp: limit body joint step size per call
        targets_safe = dict(targets)
        for j in _BODY_JOINTS:
            if j in targets_safe and j in q_before:
                cur = float(q_before[j])
                des = float(targets_safe[j])
                delta = float(np.clip(des - cur, -max_step_deg, max_step_deg))
                targets_safe[j] = cur + delta

        # Clip gripper to 0..100
        if "gripper" in targets_safe:
            targets_safe["gripper"] = float(np.clip(float(targets_safe["gripper"]), 0.0, 100.0))

        # Send
        action_sent = tools._send_joint_targets_deg(targets_safe)  # type: ignore[attr-defined]

        if sleep_s > 0:
            time.sleep(sleep_s)

        q_after = tools._read_joints_deg(read_names)  # type: ignore[attr-defined]

        return {
            "ok": True,
            "relative": relative,
            "requested": targets,
            "sent": targets_safe,
            "action_sent": action_sent,
            "before": q_before,
            "after": q_after,
        }
