"""Skill API layer for SO-101 chess robot manipulation.

This module provides high-level manipulation primitives that abstract away
the details of kinematics, motor control, and trajectory execution.

Usage:
    from skills import SkillContext
    
    ctx = SkillContext(port="/dev/tty.usbmodem...")
    ctx.home()
    ctx.reach_square("e2", approach_height_mm=80)
    ctx.grasp()
    ctx.place_square("e4", retreat_height_mm=80)
    ctx.home()
"""

from skills.skill_api import (
    SkillContext,
    # High-level chess skills
    home,
    reach_square,
    reach_pose,
    grasp,
    release,
    place_square,
    recover,
    scan_board,
    # Motion skills
    nudge,
    move_delta,
    # Gripper skills
    set_gripper,
    # Joint-level skills
    read_joints,
    move_joints,
)

__all__ = [
    "SkillContext",
    # High-level chess skills
    "home",
    "reach_square",
    "reach_pose",
    "grasp",
    "release",
    "place_square",
    "recover",
    "scan_board",
    # Motion skills
    "nudge",
    "move_delta",
    # Gripper skills
    "set_gripper",
    # Joint-level skills
    "read_joints",
    "move_joints",
]
