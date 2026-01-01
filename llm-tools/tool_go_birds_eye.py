"""Tool: go_birds_eye - move to bird's eye view position via Skill API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import scan_board as skill_scan_board

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "go_birds_eye",
        "description": (
            "Move the robot arm to bird's eye view position to observe the full chessboard. "
            "Use this before analyzing the board state or when you need to see all pieces."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Execute go_birds_eye via Skill API (scan_board)."""
    _ = args
    result = skill_scan_board(tools)
    # Rename skill field for backward compatibility
    result["position"] = "bird's_eye_view"
    return result
