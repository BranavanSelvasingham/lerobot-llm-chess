from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

import numpy as np

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
    with tools._lock:
        tools._require_robot()

        # Read before
        before = tools._read_joints_deg(list(_ALL_MOTORS))

        # Parse targets (absolute)
        requested: dict[str, float] = {}
        for j in _ALL_MOTORS:
            requested[j] = float(args[j])
        requested["gripper"] = float(np.clip(float(requested["gripper"]), 0.0, 100.0))

        max_step_deg = float(args.get("max_step_deg", 15.0))
        max_step_deg = float(np.clip(max_step_deg, 1.0, 45.0))
        max_step_gripper = float(args.get("max_step_gripper", 35.0))
        max_step_gripper = float(np.clip(max_step_gripper, 1.0, 100.0))

        # Safety clamp: limit per-call deltas so the LLM can iterate without huge jumps.
        targets_sent: dict[str, float] = dict(requested)
        for j in _ALL_MOTORS:
            cur = float(before.get(j, 0.0))
            des = float(requested.get(j, cur))
            if j == "gripper":
                delta = float(np.clip(des - cur, -max_step_gripper, max_step_gripper))
                targets_sent[j] = float(np.clip(cur + delta, 0.0, 100.0))
            else:
                delta = float(np.clip(des - cur, -max_step_deg, max_step_deg))
                targets_sent[j] = cur + delta

        action_sent = tools._send_joint_targets_deg(targets_sent)

        sleep_s = float(args.get("sleep_s", 0.35))
        sleep_s = float(np.clip(sleep_s, 0.0, 2.0))
        if sleep_s > 0:
            time.sleep(sleep_s)

        after = tools._read_joints_deg(list(_ALL_MOTORS))

        delta: dict[str, float] = {}
        moved: dict[str, bool] = {}
        for j in _ALL_MOTORS:
            b = float(before.get(j, 0.0))
            a = float(after.get(j, 0.0))
            d = float(a - b)
            delta[j] = d
            thresh = 1.0 if j == "gripper" else 0.5
            moved[j] = abs(d) >= thresh

        return {
            "ok": True,
            "torque_disabled": bool(getattr(tools, "torque_disabled", False)),
            "requested": requested,
            "sent": targets_sent,
            "action_sent": action_sent,
            "before": before,
            "after": after,
            "delta": delta,
            "moved": moved,
        }

