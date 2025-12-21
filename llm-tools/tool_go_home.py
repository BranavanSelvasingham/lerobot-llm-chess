from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


_SO101_AND_GRIPPER: list[str] = [
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
        "name": "go_home",
        "description": "Move the robot to the saved home pose.",
        "strict": False,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    _ = args
    with tools._lock:
        targets: dict[str, float] = {}
        source: str | None = None

        # Prefer the standard pose library (recorded via `lerobot-calibrate --record_standard_poses=true`).
        saved_positions_path = tools.home_position_path.with_name("saved_positions.json")
        if saved_positions_path.is_file():
            try:
                obj = json.loads(saved_positions_path.read_text())
                rest = (obj.get("rest_position") or {}).get("positions") or {}
                if isinstance(rest, dict) and rest:
                    for j in _SO101_AND_GRIPPER:
                        if j in rest:
                            targets[j] = float(rest[j])
                    if targets:
                        source = f"{saved_positions_path}:rest_position"
            except Exception:
                targets = {}

        # Fallback: legacy home_position.json.
        if not targets and tools.home_position_path.is_file():
            obj = json.loads(tools.home_position_path.read_text())
            pos = obj.get("motor_positions") or {}
            for j in _SO101_AND_GRIPPER:
                if j in pos:
                    targets[j] = float(pos[j])
            if targets:
                source = str(tools.home_position_path)

        if not targets:
            raise RuntimeError(
                "No base pose found. Record standard poses (saved_positions.json) "
                "or create home_position.json in the SO-101 calibration directory."
            )

        tools._send_joint_targets_deg(targets)
        # Reset delta-move accumulator so future delta commands start from the new physical pose.
        try:
            tools._ee_cmd_xyz_m = None  # type: ignore[attr-defined]
        except Exception:
            pass
        return {"ok": True, "source": source, "targets_deg": targets}
