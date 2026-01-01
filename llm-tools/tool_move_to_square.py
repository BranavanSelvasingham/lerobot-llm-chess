"""Tool: move_to_square - position gripper above a chess square via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import reach_square as skill_reach_square

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "move_to_square",
        "description": (
            "Move the gripper above a chess square. Use this to position before picking up a piece. "
            "After calling this, check the camera to verify the piece is centered between the gripper jaws. "
            "If not centered, use nudge_gripper to adjust, then close_gripper to grasp."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "square": {
                    "type": "string",
                    "description": "Target square (e.g. 'e4')"
                },
                "height": {
                    "type": "string",
                    "enum": ["hover", "low"],
                    "description": "hover = above piece (~80mm), low = at piece level (~20mm for grasping)"
                },
            },
            "required": ["square"],
            "additionalProperties": False,
        },
    }


def execute(
    tools: "KinematicsTools",
    args: dict[str, Any],
    episode_ctx: Any = None,
) -> dict[str, Any]:
    """Execute move_to_square with optional waypoint-level recording.
    
    Args:
        tools: KinematicsTools instance
        args: Tool arguments (square, height)
        episode_ctx: Optional episode context for waypoint logging
    """
    square = str(args.get("square", "")).strip()
    height = str(args.get("height", "hover")).strip().lower()
    
    with tools._lock:
        tools._require_kin()
        
        if tools.board_model is None or tools.board_model.T_base_board is None:
            raise RuntimeError("Board model not loaded or missing T_base_board")
        
        # Get current orientation to preserve
        T_start = tools.get_ee_pose()
        R_fixed = T_start[:3, :3].astype(float)
        
        # Compute square center in base frame
        fi, ri = _square_to_indices(square)
        p_board = tools.board_model.square_center_in_board(fi, ri)
        
        Tbb = tools.board_model.T_base_board.T
        p_base = (Tbb @ np.hstack([p_board, 1.0]))[:3].astype(float)
        
        # Set height
        if height == "low":
            # At piece level for grasping
            target_z = p_base[2]
            waypoint_name = f"lower_to_{square}"
        else:
            # Hover above (~80mm above board)
            target_z = p_base[2] + 0.08
            waypoint_name = f"hover_above_{square}"
        
        target_xyz = np.array([p_base[0], p_base[1], target_z], dtype=float)
        
        # Log PRE-move observation
        tools.log_waypoint(
            episode_ctx=episode_ctx,
            waypoint_idx=0,
            waypoint_name=waypoint_name,
            target_xyz_m=target_xyz.tolist(),
            target_gripper_pct=None,  # Gripper unchanged
            action_result=None,
            is_pre=True,
        )
        
        # Move to position
        res = tools._move_ee_to(xyz_m=target_xyz, R_fixed=R_fixed, gripper_pos=None)  # Keep gripper as-is
        
        # Wait for motors to stop
        stopped = tools.wait_until_motors_stopped(timeout_s=5.0)
        res["motors_stopped"] = stopped
        
        # Log POST-move observation
        tools.log_waypoint(
            episode_ctx=episode_ctx,
            waypoint_idx=0,
            waypoint_name=waypoint_name,
            target_xyz_m=target_xyz.tolist(),
            target_gripper_pct=None,
            action_result=res,
            is_pre=False,
        )
        
        return {
            "ok": res.get("ok", False),
            "square": square,
            "height": height,
            "target_xyz_mm": [float(x * 1000) for x in target_xyz],
            "achieved_xyz_mm": [float(x * 1000) for x in res.get("ee_after_m", target_xyz)],
            "motors_stopped": stopped,
            "position_err_mm": res.get("achieved_position_err_mm", 0),
        }
