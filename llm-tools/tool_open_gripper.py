"""Tool: open_gripper - fully open the gripper."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "open_gripper",
        "description": "Fully open the gripper to release a piece or prepare to pick one up.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    _ = args
    with tools._lock:
        # 95% open (leaving small margin)
        tools._send_joint_targets_deg({"gripper": 95.0})
        # Wait for gripper to finish moving
        stopped = tools.wait_until_motors_stopped(timeout_s=3.0)
        return {"ok": True, "gripper_percent": 95.0, "action": "opened", "motors_stopped": stopped}
