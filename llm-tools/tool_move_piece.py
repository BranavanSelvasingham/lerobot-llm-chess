"""Tool: move_piece - pick and place chess piece via Skill API."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import (
    reach_square as skill_reach_square,
    grasp as skill_grasp,
    release as skill_release,
    place_square as skill_place_square,
)

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


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
    """Execute move_piece as a sequence of Skill API calls."""
    from_square = str(args.get("from_square", "")).strip()
    to_square = str(args.get("to_square", "")).strip()
    hover_height_m = float(args.get("hover_height_m", 0.08))
    transit_height_m = float(args.get("transit_height_m", 0.15))
    
    hover_height_mm = hover_height_m * 1000
    transit_height_mm = transit_height_m * 1000
    
    results: list[dict[str, Any]] = []
    
    # Step 1: Open gripper
    res = skill_release(tools, percent=95.0)
    res["waypoint_index"] = 1
    res["waypoint"] = "open_gripper"
    results.append(res)
    
    # Step 2: Move to hover above source square
    res = skill_reach_square(tools, from_square, approach_height_mm=hover_height_mm)
    res["waypoint_index"] = 2
    res["waypoint"] = f"hover_above_{from_square}"
    results.append(res)
    
    # Step 3: Lower to grasp height
    res = skill_reach_square(tools, from_square, approach_height_mm=20.0)  # Low for grasping
    res["waypoint_index"] = 3
    res["waypoint"] = f"lower_to_{from_square}"
    results.append(res)
    
    # Step 4: Grasp
    res = skill_grasp(tools, profile="default")
    res["waypoint_index"] = 4
    res["waypoint"] = "grasp"
    results.append(res)
    time.sleep(0.1)
    
    # Step 5: Lift to transit height
    res = skill_reach_square(tools, from_square, approach_height_mm=transit_height_mm)
    res["waypoint_index"] = 5
    res["waypoint"] = f"lift_from_{from_square}"
    results.append(res)
    
    # Step 6: Move to hover above destination
    res = skill_reach_square(tools, to_square, approach_height_mm=transit_height_mm)
    res["waypoint_index"] = 6
    res["waypoint"] = f"transit_to_{to_square}"
    results.append(res)
    
    # Step 7: Lower to place height
    res = skill_reach_square(tools, to_square, approach_height_mm=20.0)
    res["waypoint_index"] = 7
    res["waypoint"] = f"lower_to_{to_square}"
    results.append(res)
    
    # Step 8: Release
    res = skill_release(tools, percent=95.0)
    res["waypoint_index"] = 8
    res["waypoint"] = "release"
    results.append(res)
    time.sleep(0.1)
    
    # Step 9: Retreat
    res = skill_reach_square(tools, to_square, approach_height_mm=hover_height_mm)
    res["waypoint_index"] = 9
    res["waypoint"] = f"retreat_from_{to_square}"
    results.append(res)
    
    return {
        "ok": True,
        "skill": "move_piece",
        "from": from_square,
        "to": to_square,
        "hover_height_m": float(hover_height_m),
        "transit_height_m": float(transit_height_m),
        "waypoints_executed": len(results),
        "waypoints": results,
    }
