#!/usr/bin/env python3
"""Canonical Skill API for SO-101 chess robot manipulation.

This module provides high-level manipulation primitives that delegate to
the existing deterministic code paths (IK, trajectory, motor execution).

All skill functions return a dict with at minimum:
    - "ok": bool indicating success
    - Additional context-specific fields

Usage:
    # Via SkillContext (owns robot connection):
    ctx = SkillContext(port="/dev/tty.usbmodem...")
    ctx.home()
    ctx.reach_square("e2")
    ctx.grasp()
    
    # Via module-level functions (requires KinematicsTools instance):
    from skills.skill_api import home, reach_square, grasp
    result = home(tools)
    result = reach_square(tools, "e2")
    result = grasp(tools)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np

# Make `src/` importable when running from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_LLM_TOOLS_DIR = _REPO_ROOT / "llm-tools"
if _LLM_TOOLS_DIR.exists() and str(_LLM_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_LLM_TOOLS_DIR))

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SO101_JOINTS: list[str] = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
_SO101_AND_GRIPPER: list[str] = _SO101_JOINTS + ["gripper"]

# Default gripper values
GRIPPER_OPEN = 95.0  # Open position (0-100 scale)
GRIPPER_CLOSED = 0.0  # Fully closed for grasping

# Default heights (meters)
DEFAULT_APPROACH_HEIGHT_M = 0.08  # 80mm above board
DEFAULT_GRASP_HEIGHT_OFFSET_M = 0.0  # At board level for grasping


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _square_to_indices(sq: str) -> tuple[int, int]:
    """Convert chess square notation (e.g. 'e4') to (file_idx, rank_idx)."""
    sq = sq.strip().lower()
    if len(sq) != 2 or sq[0] < "a" or sq[0] > "h" or sq[1] < "1" or sq[1] > "8":
        raise ValueError(f"Invalid square: {sq!r}")
    file_idx = ord(sq[0]) - ord("a")
    rank_idx = int(sq[1]) - 1
    return file_idx, rank_idx


def _get_square_xyz(tools: "KinematicsTools", square: str, height_offset_m: float = 0.0) -> np.ndarray:
    """Get XYZ position for a chess square in robot base frame.
    
    Args:
        tools: KinematicsTools instance
        square: Chess square notation (e.g. 'e4')
        height_offset_m: Height above the board surface (meters)
        
    Returns:
        np.ndarray: XYZ position in meters
    """
    if tools.board_model is None or tools.board_model.T_base_board is None:
        raise RuntimeError("Board model not loaded or missing T_base_board calibration")
    
    fi, ri = _square_to_indices(square)
    p_board = tools.board_model.square_center_in_board(fi, ri)
    
    Tbb = tools.board_model.T_base_board.T
    p_base = (Tbb @ np.hstack([p_board, 1.0]))[:3].astype(float)
    p_base[2] += height_offset_m
    
    return p_base


def _load_saved_position(tools: "KinematicsTools", position_name: str) -> dict[str, float]:
    """Load a named position from saved_positions.json.
    
    Args:
        tools: KinematicsTools instance
        position_name: Name of the position (e.g. 'rest_position', 'bird's_eye_view')
        
    Returns:
        dict mapping joint names to target degrees
    """
    saved_positions_path = tools.home_position_path.with_name("saved_positions.json")
    
    targets: dict[str, float] = {}
    source: str | None = None
    
    if saved_positions_path.is_file():
        try:
            obj = json.loads(saved_positions_path.read_text())
            pos = (obj.get(position_name) or {}).get("positions") or {}
            if isinstance(pos, dict) and pos:
                for j in _SO101_AND_GRIPPER:
                    if j in pos:
                        targets[j] = float(pos[j])
                if targets:
                    source = f"{saved_positions_path}:{position_name}"
        except Exception:
            pass
    
    # Fallback for rest_position: legacy home_position.json
    if not targets and position_name == "rest_position":
        if tools.home_position_path.is_file():
            try:
                obj = json.loads(tools.home_position_path.read_text())
                pos = obj.get("motor_positions") or {}
                for j in _SO101_AND_GRIPPER:
                    if j in pos:
                        targets[j] = float(pos[j])
                if targets:
                    source = str(tools.home_position_path)
            except Exception:
                pass
    
    if not targets:
        raise RuntimeError(
            f"Position '{position_name}' not found. Check saved_positions.json in calibration directory."
        )
    
    return targets


# ---------------------------------------------------------------------------
# Skill API Functions
# ---------------------------------------------------------------------------

def home(tools: "KinematicsTools") -> dict[str, Any]:
    """Move the robot to the saved home (rest) position.
    
    Args:
        tools: KinematicsTools instance
        
    Returns:
        dict with:
            - ok: bool
            - source: str (path to position file)
            - targets_deg: dict of joint targets
    """
    with tools._lock:
        targets = _load_saved_position(tools, "rest_position")
        tools._send_joint_targets_deg(targets)
        
        # Wait for motion to complete
        tools.wait_until_motors_stopped(timeout_s=5.0)
        
        # Reset delta-move accumulator
        try:
            tools._ee_cmd_xyz_m = None
        except Exception:
            pass
        
        return {
            "ok": True,
            "skill": "home",
            "targets_deg": targets,
        }


def reach_square(
    tools: "KinematicsTools",
    square: str,
    *,
    approach_height_mm: float | None = None,
) -> dict[str, Any]:
    """Move gripper to position above a chess square.
    
    Args:
        tools: KinematicsTools instance
        square: Chess square notation (e.g. 'e4')
        approach_height_mm: Height above board in mm (default: 80mm)
        
    Returns:
        dict with:
            - ok: bool
            - square: str
            - target_xyz_mm: list[float]
            - achieved_xyz_mm: list[float]
            - position_err_mm: float
    """
    with tools._lock:
        tools._require_kin()
        
        height_m = (approach_height_mm / 1000.0) if approach_height_mm is not None else DEFAULT_APPROACH_HEIGHT_M
        target_xyz = _get_square_xyz(tools, square, height_offset_m=height_m)
        
        # Preserve current orientation
        T_start = tools.get_ee_pose()
        R_fixed = T_start[:3, :3].astype(float)
        
        # Move to position (don't change gripper)
        res = tools._move_ee_to(xyz_m=target_xyz, R_fixed=R_fixed, gripper_pos=None)
        
        # Wait for motion to complete
        stopped = tools.wait_until_motors_stopped(timeout_s=5.0)
        
        return {
            "ok": res.get("ok", False),
            "skill": "reach_square",
            "square": square,
            "approach_height_mm": height_m * 1000,
            "target_xyz_mm": [float(x * 1000) for x in target_xyz],
            "achieved_xyz_mm": [float(x * 1000) for x in res.get("ee_after_m", target_xyz)],
            "position_err_mm": res.get("achieved_position_err_mm", 0),
            "motors_stopped": stopped,
        }


def reach_pose(
    tools: "KinematicsTools",
    pose: dict[str, Any],
    *,
    frame: str = "world",
) -> dict[str, Any]:
    """Move gripper to an arbitrary pose.
    
    Args:
        tools: KinematicsTools instance
        pose: Dict with position (and optionally orientation):
            - xyz_m or xyz_mm: [x, y, z] position
            - rpy_rad or rpy_deg: [roll, pitch, yaw] (optional)
        frame: Coordinate frame ('world' or 'base')
        
    Returns:
        dict with:
            - ok: bool
            - target_xyz_mm: list[float]
            - achieved_xyz_mm: list[float]
            - position_err_mm: float
    """
    with tools._lock:
        tools._require_kin()
        
        # Parse position
        if "xyz_m" in pose:
            target_xyz = np.array(pose["xyz_m"], dtype=float)
        elif "xyz_mm" in pose:
            target_xyz = np.array(pose["xyz_mm"], dtype=float) / 1000.0
        else:
            raise ValueError("pose must contain 'xyz_m' or 'xyz_mm'")
        
        # Get current orientation as default
        T_start = tools.get_ee_pose()
        R_fixed = T_start[:3, :3].astype(float)
        
        # TODO: Parse orientation from pose if provided
        # For now, we preserve the current orientation
        
        res = tools._move_ee_to(xyz_m=target_xyz, R_fixed=R_fixed, gripper_pos=None)
        stopped = tools.wait_until_motors_stopped(timeout_s=5.0)
        
        return {
            "ok": res.get("ok", False),
            "skill": "reach_pose",
            "frame": frame,
            "target_xyz_mm": [float(x * 1000) for x in target_xyz],
            "achieved_xyz_mm": [float(x * 1000) for x in res.get("ee_after_m", target_xyz)],
            "position_err_mm": res.get("achieved_position_err_mm", 0),
            "motors_stopped": stopped,
        }


def grasp(
    tools: "KinematicsTools",
    *,
    profile: str = "default",
) -> dict[str, Any]:
    """Close the gripper to grasp an object.
    
    Uses stall detection to detect when the gripper has gripped something.
    
    Args:
        tools: KinematicsTools instance
        profile: Grasp profile name ('default', 'gentle', 'firm')
        
    Returns:
        dict with:
            - ok: bool
            - gripped_object: bool (True if stall detected = object gripped)
            - final_position: float (gripper position 0-100)
    """
    with tools._lock:
        # Profile parameters (can be extended)
        target_percent = GRIPPER_CLOSED
        timeout_s = 3.0
        
        if profile == "gentle":
            target_percent = 10.0  # Don't close all the way
            timeout_s = 2.0
        elif profile == "firm":
            target_percent = 0.0
            timeout_s = 4.0
        
        result = tools.close_gripper_until_stall(target_percent=target_percent, timeout_s=timeout_s)
        
        return {
            "ok": result.get("ok", False),
            "skill": "grasp",
            "profile": profile,
            "gripped_object": result.get("stalled", False),
            "final_position": result.get("final_position", 0),
            "target_position": result.get("target_position", target_percent),
        }


def release(
    tools: "KinematicsTools",
    *,
    percent: float = GRIPPER_OPEN,
) -> dict[str, Any]:
    """Open the gripper to release an object.
    
    Args:
        tools: KinematicsTools instance
        percent: How far to open (0-100, default 95)
        
    Returns:
        dict with:
            - ok: bool
            - gripper_percent: float
    """
    with tools._lock:
        percent = float(np.clip(float(percent), 0.0, 100.0))
        tools._send_joint_targets_deg({"gripper": percent})
        stopped = tools.wait_until_motors_stopped(timeout_s=3.0)
        
        return {
            "ok": True,
            "skill": "release",
            "gripper_percent": percent,
            "motors_stopped": stopped,
        }


def place_square(
    tools: "KinematicsTools",
    square: str,
    *,
    retreat_height_mm: float | None = None,
) -> dict[str, Any]:
    """Place a held piece on a chess square and release.
    
    This skill:
    1. Moves to hover above the target square
    2. Lowers to the board
    3. Opens the gripper to release
    4. Retreats upward
    
    Args:
        tools: KinematicsTools instance
        square: Chess square notation (e.g. 'e4')
        retreat_height_mm: Height to retreat to after placing (default: 80mm)
        
    Returns:
        dict with:
            - ok: bool
            - square: str
            - steps: list of step results
    """
    retreat_height_m = (retreat_height_mm / 1000.0) if retreat_height_mm is not None else DEFAULT_APPROACH_HEIGHT_M
    
    steps: list[dict[str, Any]] = []
    
    with tools._lock:
        tools._require_kin()
        
        board_xyz = _get_square_xyz(tools, square, height_offset_m=0.0)
        hover_xyz = _get_square_xyz(tools, square, height_offset_m=retreat_height_m)
        
        T_start = tools.get_ee_pose()
        R_fixed = T_start[:3, :3].astype(float)
        
        # Step 1: Move to hover position
        res1 = tools._move_ee_to(xyz_m=hover_xyz, R_fixed=R_fixed, gripper_pos=None)
        tools.wait_until_motors_stopped(timeout_s=5.0)
        steps.append({"step": "hover", "ok": res1.get("ok", False)})
        
        # Step 2: Lower to board
        res2 = tools._move_ee_to(xyz_m=board_xyz, R_fixed=R_fixed, gripper_pos=None)
        tools.wait_until_motors_stopped(timeout_s=5.0)
        steps.append({"step": "lower", "ok": res2.get("ok", False)})
        
        # Step 3: Release
        tools._send_joint_targets_deg({"gripper": GRIPPER_OPEN})
        tools.wait_until_motors_stopped(timeout_s=3.0)
        steps.append({"step": "release", "ok": True})
        time.sleep(0.2)  # Small delay for gripper to fully open
        
        # Step 4: Retreat
        res4 = tools._move_ee_to(xyz_m=hover_xyz, R_fixed=R_fixed, gripper_pos=None)
        tools.wait_until_motors_stopped(timeout_s=5.0)
        steps.append({"step": "retreat", "ok": res4.get("ok", False)})
        
        all_ok = all(s.get("ok", False) for s in steps)
        
        return {
            "ok": all_ok,
            "skill": "place_square",
            "square": square,
            "retreat_height_mm": retreat_height_m * 1000,
            "steps": steps,
        }


def recover(
    tools: "KinematicsTools",
    reason: str | None = None,
) -> dict[str, Any]:
    """Attempt to recover from an error state.
    
    Current implementation:
    - Opens gripper (release any held object)
    - Returns to home position
    
    Args:
        tools: KinematicsTools instance
        reason: Optional reason for recovery
        
    Returns:
        dict with:
            - ok: bool
            - reason: str
            - steps: list of step results
    """
    steps: list[dict[str, Any]] = []
    
    # Step 1: Open gripper (safe release)
    try:
        with tools._lock:
            tools._send_joint_targets_deg({"gripper": GRIPPER_OPEN})
            tools.wait_until_motors_stopped(timeout_s=3.0)
        steps.append({"step": "open_gripper", "ok": True})
    except Exception as e:
        steps.append({"step": "open_gripper", "ok": False, "error": str(e)})
    
    # Step 2: Go home
    try:
        home_result = home(tools)
        steps.append({"step": "home", "ok": home_result.get("ok", False)})
    except Exception as e:
        steps.append({"step": "home", "ok": False, "error": str(e)})
    
    all_ok = all(s.get("ok", False) for s in steps)
    
    return {
        "ok": all_ok,
        "skill": "recover",
        "reason": reason,
        "steps": steps,
    }


def nudge(
    tools: "KinematicsTools",
    *,
    direction: str,
    distance_mm: float = 10.0,
) -> dict[str, Any]:
    """Make a small position adjustment for fine alignment.
    
    Args:
        tools: KinematicsTools instance
        direction: One of 'left', 'right', 'forward', 'back', 'up', 'down'
        distance_mm: Distance to move in mm (default: 10mm)
        
    Returns:
        dict with:
            - ok: bool
            - direction: str
            - distance_mm: float
            - from_xyz_mm: list[float]
            - to_xyz_mm: list[float]
    """
    with tools._lock:
        tools._require_kin()
        
        # Get current position
        T_now = tools.get_ee_pose()
        xyz_now = T_now[:3, 3].astype(float)
        R_fixed = T_now[:3, :3].astype(float)
        
        distance_m = distance_mm / 1000.0
        
        # Compute delta based on direction
        # In robot base frame: X is forward, Y is left, Z is up
        delta = np.array([0.0, 0.0, 0.0])
        
        if direction == "forward":
            delta[0] = distance_m
        elif direction == "back":
            delta[0] = -distance_m
        elif direction == "left":
            delta[1] = distance_m
        elif direction == "right":
            delta[1] = -distance_m
        elif direction == "up":
            delta[2] = distance_m
        elif direction == "down":
            delta[2] = -distance_m
        else:
            return {"ok": False, "skill": "nudge", "error": f"Unknown direction: {direction}"}
        
        target_xyz = xyz_now + delta
        
        # Move to new position
        res = tools._move_ee_to(xyz_m=target_xyz, R_fixed=R_fixed, gripper_pos=None)
        stopped = tools.wait_until_motors_stopped(timeout_s=3.0)
        
        return {
            "ok": res.get("ok", False),
            "skill": "nudge",
            "direction": direction,
            "distance_mm": float(distance_mm),
            "from_xyz_mm": [float(x * 1000) for x in xyz_now],
            "to_xyz_mm": [float(x * 1000) for x in target_xyz],
            "achieved_xyz_mm": [float(x * 1000) for x in res.get("ee_after_m", target_xyz)],
            "motors_stopped": stopped,
        }


def move_delta(
    tools: "KinematicsTools",
    *,
    dx_mm: float = 0.0,
    dy_mm: float = 0.0,
    dz_mm: float = 0.0,
) -> dict[str, Any]:
    """Move end-effector by a delta in Cartesian space.
    
    Args:
        tools: KinematicsTools instance
        dx_mm: Delta X in mm (forward/back from robot)
        dy_mm: Delta Y in mm (left/right)
        dz_mm: Delta Z in mm (up/down)
        
    Returns:
        dict with:
            - ok: bool
            - delta_mm: dict with dx, dy, dz
            - from_xyz_mm: list[float]
            - to_xyz_mm: list[float]
    """
    with tools._lock:
        tools._require_kin()
        
        # Get current position
        T_now = tools.get_ee_pose()
        xyz_now = T_now[:3, 3].astype(float)
        R_fixed = T_now[:3, :3].astype(float)
        
        delta_m = np.array([dx_mm, dy_mm, dz_mm], dtype=float) / 1000.0
        target_xyz = xyz_now + delta_m
        
        # Apply dz sign correction if configured
        target_xyz[2] = xyz_now[2] + (dz_mm / 1000.0) * float(tools.dz_to_kinematics_sign)
        
        res = tools._move_ee_to(xyz_m=target_xyz, R_fixed=R_fixed, gripper_pos=None, position_only=True)
        stopped = tools.wait_until_motors_stopped(timeout_s=5.0)
        
        return {
            "ok": res.get("ok", False),
            "skill": "move_delta",
            "delta_mm": {"dx": float(dx_mm), "dy": float(dy_mm), "dz": float(dz_mm)},
            "from_xyz_mm": [float(x * 1000) for x in xyz_now],
            "to_xyz_mm": [float(x * 1000) for x in target_xyz],
            "achieved_xyz_mm": [float(x * 1000) for x in res.get("ee_after_m", target_xyz)],
            "position_err_mm": res.get("achieved_position_err_mm", 0),
            "motors_stopped": stopped,
        }


def set_gripper(
    tools: "KinematicsTools",
    *,
    percent: float,
) -> dict[str, Any]:
    """Set gripper to a specific opening percentage.
    
    Args:
        tools: KinematicsTools instance
        percent: Gripper opening (0=closed, 100=open)
        
    Returns:
        dict with:
            - ok: bool
            - percent: float
            - before: float
            - after: float
    """
    import time as time_module
    
    with tools._lock:
        percent = float(np.clip(float(percent), 0.0, 100.0))
        
        # Read before
        try:
            before = tools._read_joints_deg(["gripper"])
            before_val = float(before.get("gripper", 0))
        except Exception:
            before_val = None
        
        tools._send_gripper_percent(percent)
        time_module.sleep(0.25)
        
        # Read after
        try:
            after = tools._read_joints_deg(["gripper"])
            after_val = float(after.get("gripper", 0))
        except Exception:
            after_val = None
        
        return {
            "ok": True,
            "skill": "set_gripper",
            "percent": percent,
            "before": before_val,
            "after": after_val,
        }


def read_joints(
    tools: "KinematicsTools",
    *,
    include_gripper: bool = True,
) -> dict[str, Any]:
    """Read current joint positions.
    
    Args:
        tools: KinematicsTools instance
        include_gripper: Whether to include gripper position
        
    Returns:
        dict with:
            - ok: bool
            - joints: dict mapping joint names to degrees
    """
    with tools._lock:
        tools._require_robot()
        
        names = list(_SO101_JOINTS)
        if include_gripper:
            names.append("gripper")
        
        joints: dict[str, float | None] = {n: None for n in names}
        errors: dict[str, str] = {}
        
        for n in names:
            try:
                q = tools._read_joints_deg([n])
                if n in q:
                    joints[n] = float(q[n])
            except Exception as e:
                errors[n] = str(e)
        
        ok = any(v is not None for v in joints.values())
        
        result: dict[str, Any] = {
            "ok": bool(ok),
            "skill": "read_joints",
            "joints": joints,
        }
        if errors:
            result["errors"] = errors
        
        return result


def move_joints(
    tools: "KinematicsTools",
    targets: dict[str, float],
    *,
    relative: bool = False,
    max_step_deg: float = 15.0,
) -> dict[str, Any]:
    """Move specific joints to target positions.
    
    Args:
        tools: KinematicsTools instance
        targets: Dict mapping joint names to target degrees
        relative: If True, treat values as deltas
        max_step_deg: Safety clamp per-call for body joint deltas
        
    Returns:
        dict with:
            - ok: bool
            - before: dict
            - after: dict
            - sent: dict (actual targets sent after clamping)
    """
    import time as time_module
    
    with tools._lock:
        tools._require_robot()
        
        max_step_deg = float(np.clip(max_step_deg, 1.0, 45.0))
        
        # Read current state
        read_names = list(targets.keys())
        q_before = tools._read_joints_deg(read_names)
        
        # Convert to absolute targets if relative
        targets_abs = dict(targets)
        if relative:
            for j, v in list(targets_abs.items()):
                cur = float(q_before.get(j, 0.0))
                targets_abs[j] = cur + float(v)
        
        # Safety clamp
        targets_safe = dict(targets_abs)
        for j in _SO101_JOINTS:
            if j in targets_safe and j in q_before:
                cur = float(q_before[j])
                des = float(targets_safe[j])
                delta = float(np.clip(des - cur, -max_step_deg, max_step_deg))
                targets_safe[j] = cur + delta
        
        # Clip gripper
        if "gripper" in targets_safe:
            targets_safe["gripper"] = float(np.clip(float(targets_safe["gripper"]), 0.0, 100.0))
        
        action_sent = tools._send_joint_targets_deg(targets_safe)
        time_module.sleep(0.25)
        
        q_after = tools._read_joints_deg(read_names)
        
        return {
            "ok": True,
            "skill": "move_joints",
            "relative": relative,
            "requested": targets,
            "sent": targets_safe,
            "before": q_before,
            "after": q_after,
        }


def scan_board(
    tools: "KinematicsTools",
) -> dict[str, Any]:
    """Move to bird's eye view and return board state.
    
    Note: Board state detection is a stub for now - returns last-known state
    or empty dict. Full vision-based detection would be added here.
    
    Args:
        tools: KinematicsTools instance
        
    Returns:
        dict with:
            - ok: bool
            - position: str ('bird's_eye_view')
            - board_state: dict (stub, empty for now)
    """
    with tools._lock:
        targets = _load_saved_position(tools, "bird's_eye_view")
        tools._send_joint_targets_deg(targets)
        tools.wait_until_motors_stopped(timeout_s=5.0)
        
        # TODO: Integrate with vision system to detect board state
        # For now, return stub
        board_state: dict[str, Any] = {}
        
        return {
            "ok": True,
            "skill": "scan_board",
            "position": "bird's_eye_view",
            "targets_deg": targets,
            "board_state": board_state,  # Stub
        }


# ---------------------------------------------------------------------------
# SkillContext: Convenience wrapper that owns the robot connection
# ---------------------------------------------------------------------------

class SkillContext:
    """Context manager and wrapper for skill execution.
    
    Owns the KinematicsTools instance and provides convenient method access
    to all skills.
    
    Usage:
        ctx = SkillContext(port="/dev/tty.usbmodem...")
        ctx.home()
        ctx.reach_square("e2")
        ctx.grasp()
        ctx.place_square("e4")
        ctx.home()
    """
    
    def __init__(
        self,
        port: str | None = None,
        robot_id: str = "so101_chess",
        urdf_path: str | None = None,
    ):
        """Initialize skill context.
        
        Args:
            port: Robot serial port (required for robot operations)
            robot_id: Calibration ID
            urdf_path: Path to URDF file (optional, will search common paths)
        """
        # Import here to avoid circular imports
        from llm_toolkit import AppConfig, KinematicsTools
        
        cfg = AppConfig(
            port=port,
            robot_id=robot_id,
            urdf_path=urdf_path,
        )
        self._tools = KinematicsTools(cfg)
    
    @property
    def tools(self) -> "KinematicsTools":
        """Access the underlying KinematicsTools instance."""
        return self._tools
    
    def disconnect(self) -> None:
        """Disconnect from the robot."""
        self._tools.disconnect_robot()
    
    def __enter__(self) -> "SkillContext":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
    
    # Skill methods delegate to module-level functions
    
    def home(self) -> dict[str, Any]:
        """Move to home position."""
        return home(self._tools)
    
    def reach_square(
        self,
        square: str,
        *,
        approach_height_mm: float | None = None,
    ) -> dict[str, Any]:
        """Move gripper above a chess square."""
        return reach_square(self._tools, square, approach_height_mm=approach_height_mm)
    
    def reach_pose(
        self,
        pose: dict[str, Any],
        *,
        frame: str = "world",
    ) -> dict[str, Any]:
        """Move gripper to an arbitrary pose."""
        return reach_pose(self._tools, pose, frame=frame)
    
    def grasp(self, *, profile: str = "default") -> dict[str, Any]:
        """Close gripper to grasp."""
        return grasp(self._tools, profile=profile)
    
    def release(self, *, percent: float = GRIPPER_OPEN) -> dict[str, Any]:
        """Open gripper to release."""
        return release(self._tools, percent=percent)
    
    def place_square(
        self,
        square: str,
        *,
        retreat_height_mm: float | None = None,
    ) -> dict[str, Any]:
        """Place piece on a square and release."""
        return place_square(self._tools, square, retreat_height_mm=retreat_height_mm)
    
    def recover(self, reason: str | None = None) -> dict[str, Any]:
        """Attempt recovery from error state."""
        return recover(self._tools, reason=reason)
    
    def scan_board(self) -> dict[str, Any]:
        """Move to bird's eye view and return board state."""
        return scan_board(self._tools)
    
    def nudge(
        self,
        *,
        direction: str,
        distance_mm: float = 10.0,
    ) -> dict[str, Any]:
        """Small position adjustment for fine alignment."""
        return nudge(self._tools, direction=direction, distance_mm=distance_mm)
    
    def move_delta(
        self,
        *,
        dx_mm: float = 0.0,
        dy_mm: float = 0.0,
        dz_mm: float = 0.0,
    ) -> dict[str, Any]:
        """Move end-effector by a delta in Cartesian space."""
        return move_delta(self._tools, dx_mm=dx_mm, dy_mm=dy_mm, dz_mm=dz_mm)
    
    def set_gripper(self, *, percent: float) -> dict[str, Any]:
        """Set gripper to a specific opening percentage."""
        return set_gripper(self._tools, percent=percent)
    
    def read_joints(self, *, include_gripper: bool = True) -> dict[str, Any]:
        """Read current joint positions."""
        return read_joints(self._tools, include_gripper=include_gripper)
    
    def move_joints(
        self,
        targets: dict[str, float],
        *,
        relative: bool = False,
        max_step_deg: float = 15.0,
    ) -> dict[str, Any]:
        """Move specific joints to target positions."""
        return move_joints(self._tools, targets, relative=relative, max_step_deg=max_step_deg)
