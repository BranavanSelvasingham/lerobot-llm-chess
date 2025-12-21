from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


_SO101_JOINTS: list[str] = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


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
    with tools._lock:
        tools._require_robot()
        include_gripper = bool(args.get("include_gripper", True))

        names = list(_SO101_JOINTS)
        if include_gripper:
            names.append("gripper")

        # Robust read: try each joint so one overloaded motor doesn't wipe the whole snapshot.
        joints: dict[str, float | None] = {n: None for n in names}
        errors: dict[str, str] = {}
        for n in names:
            try:
                q = tools._read_joints_deg([n])  # type: ignore[attr-defined]
                if n in q:
                    joints[n] = float(q[n])
            except Exception as e:
                errors[n] = str(e)

        ok = any(v is not None for v in joints.values())
        out: dict[str, Any] = {
            "ok": bool(ok),
            "torque_disabled": bool(getattr(tools, "torque_disabled", False)),
            "joints": joints,
        }
        if errors:
            out["errors"] = errors
        if not ok and errors:
            out["error"] = "Failed to read any joints."
        return out
