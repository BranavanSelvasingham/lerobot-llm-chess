from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def _square_to_indices(sq: str) -> tuple[int, int]:
    sq = sq.strip().lower()
    if len(sq) != 2 or sq[0] < "a" or sq[0] > "h" or sq[1] < "1" or sq[1] > "8":
        raise ValueError(f"Invalid square: {sq!r}")
    file_idx = ord(sq[0]) - ord("a")
    rank_idx = int(sq[1]) - 1
    return file_idx, rank_idx


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "move_piece",
        "description": "Pick a piece at from_square and place it at to_square (uses chess_board_model calibration).",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "from_square": {"type": "string"},
                "to_square": {"type": "string"},
                "hover_height_m": {"type": "number"},
                "transit_height_m": {"type": "number"},
            },
            "required": ["from_square", "to_square"],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    from_square = str(args.get("from_square", "")).strip()
    to_square = str(args.get("to_square", "")).strip()
    hover_height_m = float(args.get("hover_height_m", 0.08))
    transit_height_m = float(args.get("transit_height_m", 0.15))

    with tools._lock:
        tools._require_kin()

        if tools.board_model is None:
            raise RuntimeError("Board model not loaded")
        if tools.board_model.T_base_board is None:
            raise RuntimeError(
                f"Board model missing T_base_board (run calibration). Expected at {tools.chess_board_model_path}"
            )

        # Fixed orientation for the whole move = current orientation.
        T_start = tools.get_ee_pose()
        R_fixed = T_start[:3, :3].astype(float)

        # Compute square centers in base frame.
        fi_s, ri_s = _square_to_indices(from_square)
        fi_d, ri_d = _square_to_indices(to_square)

        p_src_board = tools.board_model.square_center_in_board(fi_s, ri_s)
        p_dst_board = tools.board_model.square_center_in_board(fi_d, ri_d)

        Tbb = tools.board_model.T_base_board.T
        p_src_base = (Tbb @ np.hstack([p_src_board, 1.0]))[:3].astype(float)
        p_dst_base = (Tbb @ np.hstack([p_dst_board, 1.0]))[:3].astype(float)

        src_hover = p_src_base.copy()
        src_hover[2] += float(hover_height_m)
        dst_hover = p_dst_base.copy()
        dst_hover[2] += float(hover_height_m)

        high = np.array(
            [
                float(src_hover[0]),
                float(src_hover[1]),
                float(max(src_hover[2], dst_hover[2], float(transit_height_m))),
            ],
            dtype=float,
        )

        # Gripper values on this robot: 0=closed, 100=open
        open_value = 95.0
        grasp_close = 0.0  # Fully closed to grip piece

        waypoints: list[tuple[np.ndarray, float]] = [
            (src_hover, open_value),
            (p_src_base, open_value),
            (p_src_base, grasp_close),
            (src_hover, grasp_close),
            (high, grasp_close),
            (dst_hover, grasp_close),
            (p_dst_base, grasp_close),
            (p_dst_base, open_value),
            (dst_hover, open_value),
        ]

        results: list[dict[str, Any]] = []
        prev_gripper = open_value
        
        for idx, (xyz, g) in enumerate(waypoints, start=1):
            res = tools._move_ee_to(xyz_m=xyz, R_fixed=R_fixed, gripper_pos=g)
            res["waypoint_index"] = idx
            res["waypoint_gripper"] = float(g)
            results.append(res)
            
            # For gripper close (grasp), use stall detection
            if g < prev_gripper and g == grasp_close:
                # This is a grasp action - wait for stall
                grip_result = tools.close_gripper_until_stall(target_percent=g, timeout_s=3.0)
                res["grip_result"] = grip_result
                res["gripped_object"] = grip_result.get("stalled", False)
            else:
                # Regular move - wait for motors to stop
                stopped = tools.wait_until_motors_stopped(timeout_s=5.0)
                res["motors_stopped"] = stopped
            
            prev_gripper = g
            
            # Small extra settle time
            time.sleep(0.1)

        return {
            "ok": True,
            "from": from_square,
            "to": to_square,
            "hover_height_m": float(hover_height_m),
            "transit_height_m": float(transit_height_m),
            "waypoints_executed": len(results),
            "waypoints": results,
        }
