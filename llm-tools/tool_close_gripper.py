"""Tool: close_gripper - close the gripper to grasp a piece."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "close_gripper",
        "description": "Close the gripper to grasp a chess piece.",
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
        # Close gripper until it stalls on object or reaches target
        result = tools.close_gripper_until_stall(target_percent=0.0, timeout_s=3.0)
        return {
            "ok": result.get("ok", False),
            "action": "closed",
            "gripped_object": result.get("stalled", False),
            "final_position": result.get("final_position", 0),
            **result
        }
