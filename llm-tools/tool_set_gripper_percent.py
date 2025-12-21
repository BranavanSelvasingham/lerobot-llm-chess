from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

import numpy as np

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
    with tools._lock:
        pct_req = float(args.get("percent", 0.0))
        pct = float(np.clip(pct_req, 0.0, 100.0))

        # Readback before/after so logs reflect physical reality.
        before: dict[str, Any]
        after: dict[str, Any]
        try:
            before = tools._read_joints_deg(["gripper"])  # type: ignore[attr-defined]
        except Exception as e:
            before = {"_error": str(e)}

        send_info = tools._send_gripper_percent(pct)  # returns action actually sent

        # Give the bus/motor some time to move before reading again.
        time.sleep(0.25)
        try:
            after = tools._read_joints_deg(["gripper"])  # type: ignore[attr-defined]
        except Exception as e:
            after = {"_error": str(e)}

        moved = None
        delta = None
        try:
            if isinstance(before.get("gripper"), (int, float)) and isinstance(after.get("gripper"), (int, float)):
                delta = float(after["gripper"]) - float(before["gripper"])
                moved = bool(abs(delta) >= 1.0)
        except Exception:
            pass

        result: dict[str, Any] = {
            "ok": True,
            "percent_requested": float(pct_req),
            "percent": float(pct),
            "gripper_before": before,
            "gripper_after": after,
            "delta": delta,
            "moved": moved,
            **(send_info if isinstance(send_info, dict) else {"send_info": send_info}),
        }
        if moved is False:
            result["warning"] = (
                "Gripper readback did not change >= 1.0 (in 0..100 units). "
                "This may indicate torque disabled, motor unplugged, a stalled gripper, "
                "or that the robot clips the goal position."
            )
        return result
