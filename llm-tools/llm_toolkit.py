#!/usr/bin/env python3

"""Kinematics-backed tool layer for `chess_robot_ui_llm_v2.py`.

This module contains:
- Connection + calibration loading for the SO-101 follower arm
- FK/IK helpers for end-effector motion
- Tool dispatch + tool schemas (schemas are defined per-tool in separate files)

The per-tool implementations live alongside this file:
- `tool_move_gripper_delta.py`
- `tool_set_gripper_percent.py`
- `tool_go_home.py`
- `tool_move_piece.py`

This file intentionally contains **no UI code**.
"""

from __future__ import annotations

import math
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from xml.etree import ElementTree as ET

import numpy as np

# Make `src/` importable when running from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from lerobot.configs.chessboard import ChessBoardParams
from lerobot.model.kinematics import RobotKinematics
from lerobot.perception.chess.board_model import BoardModel
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.utils.constants import HF_LEROBOT_CALIBRATION, ROBOTS


_SO101_JOINTS: list[str] = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


@dataclass(frozen=True)
class AppConfig:
    port: str | None
    robot_id: str = "so101_chess"
    urdf_path: str | None = None

    # UI-related settings (kept here for convenience)
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30

    # LLM-related settings
    model: str = "gpt-5.2"
    api_key: str | None = None


def _so101_calibration_dir() -> Path:
    return Path(HF_LEROBOT_CALIBRATION) / ROBOTS / "so101_follower"


def _resolve_urdf_path(user_path: str | None) -> str | None:
    """Try user path first, then common local paths.

    The URDF may be present but gitignored locally.
    """

    env_path = os.getenv("SO101_URDF")
    candidates: list[Path] = []

    if user_path:
        candidates.append(Path(user_path).expanduser())
    if env_path:
        candidates.append(Path(env_path).expanduser())

    # Common local paths
    candidates += [
        Path.cwd() / "so101_new_calib.nomesh.urdf",
        Path.cwd() / "so101_kinematics.urdf",
        Path.cwd() / "so101_new_calib.urdf",
        Path.cwd() / "SO101" / "so101_new_calib.urdf",
        _REPO_ROOT / "so101_new_calib.nomesh.urdf",
        _REPO_ROOT / "so101_kinematics.urdf",
        _REPO_ROOT / "so101_new_calib.urdf",
        _REPO_ROOT / "SO101" / "so101_new_calib.urdf",
    ]

    for p in candidates:
        try:
            if p.is_file():
                return str(p)
        except Exception:
            continue
    return None


class KinematicsTools:
    """Kinematics-backed tool context (robot + IK + chess board transform)."""

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

        self._lock = Lock()

        self.robot: SO101Follower | None = None
        self.kin: RobotKinematics | None = None
        self.board_model: BoardModel | None = None

        # Resolved URDF used for kinematics (if available).
        self.urdf_path_resolved: str | None = None
        self._urdf_summary_cache: dict[str, Any] | None = None

        # Safety state: when True, we refuse to send motion commands until torque is re-enabled.
        self.torque_disabled: bool = False

        self.calib_dir: Path = _so101_calibration_dir()
        self.board_view_calib_path: Path = self.calib_dir / "board_view_calibration.json"
        self.workspace_estimate_path: Path = self.calib_dir / "workspace_estimate.json"
        self.home_position_path: Path = self.calib_dir / "home_position.json"
        self.chess_board_model_path: Path = self.calib_dir / "chess_board_model.json"

        # Semantic mapping: user wants +dz to mean "up".
        self.dz_to_kinematics_sign: float = 1.0

        # Optional EE bounds in meters.
        self.ee_min_m: np.ndarray | None = None
        self.ee_max_m: np.ndarray | None = None

        # Last commanded EE position (meters). This is used to make repeated small delta moves accumulate
        # even if the motors don't move for tiny commands (deadband / stiction).
        self._ee_cmd_xyz_m: np.ndarray | None = None

        self._load_board_view_calibration()
        self._load_workspace_bounds()

        if cfg.port:
            self.connect_robot(cfg.port)

        self.load_kinematics(cfg.urdf_path)
        self.load_board_model()

    # -----------------------------
    # Calibration helpers
    # -----------------------------

    def _load_board_view_calibration(self) -> None:
        try:
            if self.board_view_calib_path.is_file():
                obj = json.loads(self.board_view_calib_path.read_text())
                s = obj.get("dz_to_kinematics_sign")
                if s is not None:
                    self.dz_to_kinematics_sign = float(s)
        except Exception:
            # Keep default
            pass

    def set_invert_z(self, invert: bool) -> None:
        self.dz_to_kinematics_sign = -1.0 if invert else 1.0
        try:
            payload: dict[str, Any] = {}
            if self.board_view_calib_path.is_file():
                payload = json.loads(self.board_view_calib_path.read_text())
            payload["dz_to_kinematics_sign"] = float(self.dz_to_kinematics_sign)
            payload["dz_to_kinematics_set_at"] = datetime.now().isoformat(timespec="seconds")
            self.board_view_calib_path.parent.mkdir(parents=True, exist_ok=True)
            self.board_view_calib_path.write_text(json.dumps(payload, indent=2))
        except Exception:
            pass

    def _load_workspace_bounds(self) -> None:
        """Load EE bounds (meters) from cached FK sampling if available."""
        try:
            if not self.workspace_estimate_path.is_file():
                return
            obj = json.loads(self.workspace_estimate_path.read_text())
            p = obj.get("ee_percentiles_mm") or {}
            # Use percentiles with a margin; this keeps the clamp conservative.
            margin_m = 0.05
            min_m = np.array([p.get("x_p5"), p.get("y_p5"), p.get("z_p5")], dtype=float) / 1000.0
            max_m = np.array([p.get("x_p95"), p.get("y_p95"), p.get("z_p95")], dtype=float) / 1000.0
            if np.any(~np.isfinite(min_m)) or np.any(~np.isfinite(max_m)):
                return
            self.ee_min_m = min_m - margin_m
            self.ee_max_m = max_m + margin_m
        except Exception:
            # Bounds are optional
            self.ee_min_m = None
            self.ee_max_m = None

    # -----------------------------
    # Robot / kinematics setup
    # -----------------------------

    def connect_robot(self, port: str) -> None:
        with self._lock:
            if self.robot is not None and self.robot.is_connected:
                return

            robot_cfg = SO101FollowerConfig(port=port, id=self.cfg.robot_id, cameras={}, use_degrees=True)
            self.robot = SO101Follower(robot_cfg)
            # Avoid interactive calibration in a GUI.
            self.robot.connect(calibrate=False, skip_firmware_check=True)

            # Ensure our calibration dir follows the actual robot instance.
            self.calib_dir = self.robot.calibration_dir
            self.board_view_calib_path = self.calib_dir / "board_view_calibration.json"
            self.workspace_estimate_path = self.calib_dir / "workspace_estimate.json"
            self.home_position_path = self.calib_dir / "home_position.json"
            self.chess_board_model_path = self.calib_dir / "chess_board_model.json"

            self._load_board_view_calibration()
            self._load_workspace_bounds()
            self.torque_disabled = False
            
            # Set a reasonable default speed (not max)
            self.set_motor_speed(500)
    
    def set_motor_speed(self, speed: int = 500) -> None:
        """Set motor movement speed for all motors.
        
        Args:
            speed: Speed value (0-4095). Lower = slower. 
                   Recommended: 200-800 for smooth moves, 0 = max speed.
        """
        if self.robot is None or not self.robot.is_connected:
            return
        try:
            # Goal_Velocity controls servo speed (0 = max, higher = slower but capped)
            # For STS3215: speed is in steps/sec, ~0-4095 range
            speed = max(0, min(4095, int(speed)))
            self.robot.bus.sync_write("Goal_Velocity", speed, normalize=False)
        except Exception as e:
            print(f"Warning: Could not set motor speed: {e}")
    
    def close_gripper_until_stall(self, target_percent: float = 0.0, timeout_s: float = 3.0) -> dict:
        """Close gripper until it stalls (grips object) or reaches target.
        
        Returns dict with final position and whether stall was detected.
        """
        if self.robot is None or not self.robot.is_connected:
            return {"ok": False, "error": "Robot not connected"}
        
        import time
        
        # Send close command
        self._send_joint_targets_deg({"gripper": target_percent})
        
        start = time.time()
        last_pos = None
        stall_count = 0
        stall_threshold = 3  # Number of consecutive same-position reads to detect stall
        
        while (time.time() - start) < timeout_s:
            try:
                # Read current gripper position
                obs = self.robot.get_observation()
                current_pos = obs.get("gripper.pos", 0)
                
                # Check if gripper has stopped moving (stalled on object)
                if last_pos is not None:
                    if abs(current_pos - last_pos) < 0.5:  # Less than 0.5 degree change
                        stall_count += 1
                        if stall_count >= stall_threshold:
                            # Gripper has stalled - gripping something
                            return {
                                "ok": True,
                                "stalled": True,
                                "final_position": float(current_pos),
                                "target_position": float(target_percent),
                            }
                    else:
                        stall_count = 0
                
                # Check if reached target
                if abs(current_pos - target_percent) < 2.0:
                    return {
                        "ok": True,
                        "stalled": False,
                        "final_position": float(current_pos),
                        "target_position": float(target_percent),
                    }
                
                last_pos = current_pos
                
            except Exception as e:
                pass
            
            time.sleep(0.05)
        
        # Timeout - return current state
        try:
            obs = self.robot.get_observation()
            final = obs.get("gripper.pos", 0)
        except:
            final = 0
            
        return {
            "ok": True,
            "stalled": True,  # Assume stalled on timeout
            "final_position": float(final),
            "target_position": float(target_percent),
            "timeout": True,
        }

    def wait_until_motors_stopped(self, timeout_s: float = 5.0, poll_interval_s: float = 0.05) -> bool:
        """Wait until all motors have stopped moving.
        
        Args:
            timeout_s: Maximum time to wait (seconds)
            poll_interval_s: How often to check (seconds)
            
        Returns:
            True if motors stopped, False if timeout
        """
        if self.robot is None or not self.robot.is_connected:
            return True
        
        import time
        start = time.time()
        motors = list(self.robot.bus.motors.keys())
        
        while (time.time() - start) < timeout_s:
            try:
                # Read Moving register for all motors
                moving_status = self.robot.bus.sync_read("Moving", motors, normalize=False)
                
                # Check if any motor is still moving (Moving=1 means moving)
                any_moving = any(v != 0 for v in moving_status.values())
                
                if not any_moving:
                    return True
                    
            except Exception:
                # If read fails, fall back to small delay
                pass
            
            time.sleep(poll_interval_s)
        
        return False  # Timeout

    def disconnect_robot(self) -> None:
        with self._lock:
            if self.robot is None:
                return
            try:
                if self.robot.is_connected:
                    self.robot.disconnect()
            finally:
                self.robot = None
                self.torque_disabled = False

    def disable_torque(self, motors: list[str] | None = None) -> dict[str, Any]:
        """Disable torque on motors (E-stop like behavior)."""
        with self._lock:
            robot = self._require_robot()
            bus = robot.bus
            names = motors or list(bus.motors)

            per_motor: dict[str, Any] = {}
            for m in names:
                try:
                    bus.write("Torque_Enable", m, 0, num_retry=3)
                    # also unlock EEPROM writes like the bus helper does
                    try:
                        bus.write("Lock", m, 0, num_retry=1)
                    except Exception:
                        pass
                except Exception as e:
                    per_motor[m] = {"ok": False, "error": str(e)}
                    continue

                # Verify torque state best-effort
                try:
                    te = bus.read("Torque_Enable", m, normalize=False)
                    per_motor[m] = {"ok": True, "Torque_Enable": te}
                except Exception as e:
                    per_motor[m] = {"ok": True, "Torque_Enable": {"_error": str(e)}}

            # Consider torque disabled if *most* motors report disabled.
            disabled_count = 0
            for v in per_motor.values():
                te = v.get("Torque_Enable")
                if isinstance(te, (int, float)) and int(te) == 0:
                    disabled_count += 1
            self.torque_disabled = bool(disabled_count >= max(1, int(0.7 * len(names))))

            ok = all(v.get("ok") is True for v in per_motor.values()) and self.torque_disabled
            return {
                "ok": ok,
                "torque_disabled": bool(self.torque_disabled),
                "motors": names,
                "per_motor": per_motor,
            }

    def enable_torque(self, motors: list[str] | None = None) -> dict[str, Any]:
        """Re-enable torque on motors."""
        with self._lock:
            robot = self._require_robot()
            bus = robot.bus
            names = motors or list(bus.motors)

            per_motor: dict[str, Any] = {}
            for m in names:
                try:
                    bus.write("Torque_Enable", m, 1, num_retry=3)
                    try:
                        bus.write("Lock", m, 1, num_retry=1)
                    except Exception:
                        pass
                except Exception as e:
                    per_motor[m] = {"ok": False, "error": str(e)}
                    continue

                try:
                    te = bus.read("Torque_Enable", m, normalize=False)
                    per_motor[m] = {"ok": True, "Torque_Enable": te}
                except Exception as e:
                    per_motor[m] = {"ok": True, "Torque_Enable": {"_error": str(e)}}

            enabled_count = 0
            for v in per_motor.values():
                te = v.get("Torque_Enable")
                if isinstance(te, (int, float)) and int(te) == 1:
                    enabled_count += 1
            self.torque_disabled = not bool(enabled_count >= max(1, int(0.7 * len(names))))

            ok = all(v.get("ok") is True for v in per_motor.values()) and (not self.torque_disabled)
            return {
                "ok": ok,
                "torque_disabled": bool(self.torque_disabled),
                "motors": names,
                "per_motor": per_motor,
            }

    def read_motor_diagnostics(self, motors: list[str] | None = None) -> dict[str, Any]:
        """Read motor status / overload-relevant registers for debugging."""
        with self._lock:
            robot = self._require_robot()
            names = motors or list(robot.bus.motors)

            # Registers chosen to help debug stalls/overload/torque issues.
            regs = [
                "Torque_Enable",
                "Goal_Position",
                "Present_Position",
                "Present_Velocity",
                "Present_Load",
                "Present_Current",
                "Present_Voltage",
                "Present_Temperature",
                "Status",
                "Moving",
                # Protection / limits (may be model-dependent)
                "Max_Torque_Limit",
                "Torque_Limit",
                "Protection_Current",
                "Protective_Torque",
                "Protection_Time",
                "Overload_Torque",
            ]

            raw: dict[str, Any] = {}
            norm: dict[str, Any] = {}
            for r in regs:
                raw[r] = self._try_read_bus_register(r, motors=names, normalize=False)
                norm[r] = self._try_read_bus_register(r, motors=names, normalize=True)

            return {
                "ok": True,
                "motors": names,
                "torque_disabled": bool(self.torque_disabled),
                "raw": raw,
                "normalized": norm,
            }

    def load_kinematics(self, urdf_path: str | None) -> None:
        resolved = _resolve_urdf_path(urdf_path)
        if not resolved:
            self.kin = None
            self.urdf_path_resolved = None
            self._urdf_summary_cache = None
            return

        self.urdf_path_resolved = str(resolved)
        self._urdf_summary_cache = None

        try:
            # Exclude the gripper jaw DOF; keep body joints only.
            self.kin = RobotKinematics(
                urdf_path=resolved,
                target_frame_name="gripper_frame_link",
                joint_names=_SO101_JOINTS,
            )
        except Exception:
            self.kin = None

    def urdf_summary(self) -> dict[str, Any]:
        """Return a compact URDF-derived summary for LLM reasoning.

        This is intentionally small: only joints relevant to the SO-101 arm control.
        """
        with self._lock:
            if self._urdf_summary_cache is not None:
                return dict(self._urdf_summary_cache)

            urdf_path = self.urdf_path_resolved or _resolve_urdf_path(self.cfg.urdf_path)
            if not urdf_path:
                out = {"ok": False, "error": "URDF not found (kinematics unavailable)."}
                self._urdf_summary_cache = dict(out)
                return out

            try:
                root = ET.parse(str(urdf_path)).getroot()
            except Exception as e:
                out = {"ok": False, "error": f"Failed to parse URDF: {e}", "urdf_path": str(urdf_path)}
                self._urdf_summary_cache = dict(out)
                return out

            joints_by_name: dict[str, dict[str, Any]] = {}
            for j in root.findall("joint"):
                name = str(j.attrib.get("name", "")).strip()
                if not name:
                    continue

                jtype = str(j.attrib.get("type", "")).strip()
                parent_el = j.find("parent")
                child_el = j.find("child")
                origin_el = j.find("origin")
                axis_el = j.find("axis")
                limit_el = j.find("limit")

                parent_link = str(parent_el.attrib.get("link", "")) if parent_el is not None else ""
                child_link = str(child_el.attrib.get("link", "")) if child_el is not None else ""

                def _parse_vec(attr: str, default: str) -> list[float]:
                    raw = default
                    if origin_el is not None and attr in origin_el.attrib:
                        raw = str(origin_el.attrib.get(attr, default))
                    if axis_el is not None and attr in axis_el.attrib:
                        raw = str(axis_el.attrib.get(attr, default))
                    parts = [p for p in raw.replace(",", " ").split() if p]
                    vals = [float(p) for p in parts[:3]]
                    while len(vals) < 3:
                        vals.append(0.0)
                    return vals

                origin_xyz_m = _parse_vec("xyz", "0 0 0")
                origin_rpy_rad = _parse_vec("rpy", "0 0 0")
                axis = _parse_vec("xyz", "0 0 0") if axis_el is not None else [0.0, 0.0, 0.0]

                limit_lower_rad = None
                limit_upper_rad = None
                effort = None
                velocity = None
                if limit_el is not None:
                    if "lower" in limit_el.attrib:
                        limit_lower_rad = float(limit_el.attrib["lower"])
                    if "upper" in limit_el.attrib:
                        limit_upper_rad = float(limit_el.attrib["upper"])
                    if "effort" in limit_el.attrib:
                        effort = float(limit_el.attrib["effort"])
                    if "velocity" in limit_el.attrib:
                        velocity = float(limit_el.attrib["velocity"])

                joints_by_name[name] = {
                    "name": name,
                    "type": jtype,
                    "parent": parent_link,
                    "child": child_link,
                    "origin_xyz_m": origin_xyz_m,
                    "origin_rpy_rad": origin_rpy_rad,
                    "origin_offset_norm_m": float(np.linalg.norm(np.array(origin_xyz_m, dtype=float))),
                    "axis": axis,
                    "limit_lower_rad": limit_lower_rad,
                    "limit_upper_rad": limit_upper_rad,
                    "limit_lower_deg": (math.degrees(limit_lower_rad) if limit_lower_rad is not None else None),
                    "limit_upper_deg": (math.degrees(limit_upper_rad) if limit_upper_rad is not None else None),
                    "effort": effort,
                    "velocity": velocity,
                }

            ordered: list[dict[str, Any]] = []
            missing: list[str] = []
            for name in _SO101_JOINTS + ["gripper"]:
                if name in joints_by_name:
                    ordered.append(joints_by_name[name])
                else:
                    missing.append(name)

            out = {
                "ok": True,
                "urdf_path": str(urdf_path),
                "target_frame_name": "gripper_frame_link",
                "joints": ordered,
                "missing_in_urdf": missing,
                "note": (
                    "URDF geometry/limits are a MODEL; real calibration and motor ranges may differ. "
                    "Use CURRENT_JOINTS + images to validate signs and safe ranges."
                ),
            }
            self._urdf_summary_cache = dict(out)
            return out

    def joint_effects_mm_per_deg(self, eps_deg: float = 3.0) -> dict[str, Any]:
        """Return per-joint local sensitivity of EE position (finite difference FK).

        Useful as an actionable, URDF-derived hint for which joint to tweak.
        """
        with self._lock:
            kin = self._require_kin()
            eps = float(np.clip(float(eps_deg), 0.5, 10.0))

            q_now = self._read_joints_deg(_SO101_JOINTS)
            q = np.array([q_now[j] for j in _SO101_JOINTS], dtype=float)
            T0 = kin.forward_kinematics(q)
            xyz0 = T0[:3, 3].astype(float)

            effects: dict[str, Any] = {}
            for i, j in enumerate(_SO101_JOINTS):
                qp = q.copy()
                qm = q.copy()
                qp[i] += eps
                qm[i] -= eps
                xp = kin.forward_kinematics(qp)[:3, 3].astype(float)
                xm = kin.forward_kinematics(qm)[:3, 3].astype(float)
                dxyz_mm_per_deg = ((xp - xm) / (2.0 * eps)) * 1000.0
                effects[j] = {
                    "dxyz_mm_per_deg": dxyz_mm_per_deg.tolist(),
                    "dxyz_mm_for_5deg": (dxyz_mm_per_deg * 5.0).tolist(),
                }

            return {
                "ok": True,
                "eps_deg": eps,
                "ee_xyz_m": xyz0.tolist(),
                "effects": effects,
                "note": (
                    "These are local sensitivities from the URDF kinematics model. "
                    "They are most reliable for small joint changes near the current pose."
                ),
            }

    def load_board_model(self) -> None:
        try:
            if self.chess_board_model_path.is_file():
                self.board_model = BoardModel.load(self.chess_board_model_path)
            else:
                # Still create a default model (missing T_base_board means move_piece can't run).
                self.board_model = BoardModel(params=ChessBoardParams())
        except Exception:
            self.board_model = BoardModel(params=ChessBoardParams())

    # -----------------------------
    # Low-level kinematics helpers
    # -----------------------------

    def _require_robot(self) -> SO101Follower:
        if self.robot is None or not self.robot.is_connected:
            raise RuntimeError("Robot not connected (run with --port)")
        return self.robot

    def _require_kin(self) -> RobotKinematics:
        if self.kin is None:
            raise RuntimeError("Kinematics not available (URDF/placo missing)")
        return self.kin

    def _read_joints_deg(self, joint_names: list[str]) -> dict[str, float]:
        robot = self._require_robot()
        bus = robot.bus
        # Prefer sync_read; fall back if protocol doesn't support it.
        try:
            vals = bus.sync_read("Present_Position", joint_names, normalize=True)
            return {name: float(vals[name]) for name in joint_names}
        except Exception:
            out: dict[str, float] = {}
            for j in joint_names:
                try:
                    out[j] = float(bus.read("Present_Position", j, normalize=True))
                except Exception:
                    # Leave unread joints out; callers that need strict reads should validate presence.
                    continue
            return out

    def _send_joint_targets_deg(self, targets_deg: dict[str, float]) -> dict[str, Any]:
        robot = self._require_robot()
        action = {f"{name}.pos": float(val) for name, val in targets_deg.items()}
        return robot.send_action(action)

    def _try_read_bus_register(
        self, data_name: str, *, motors: list[str] | None = None, normalize: bool = True
    ) -> dict[str, Any]:
        """Best-effort read of a bus register (sync_read → per-motor read).

        Returns a mapping motor->value. If a motor read fails, its value is {"_error": "..."}.
        """
        robot = self._require_robot()
        bus = robot.bus
        names = motors if motors is not None else list(bus.motors)
        try:
            vals = bus.sync_read(data_name, names, normalize=normalize)
            return {m: vals[m] for m in names}
        except Exception as e_sync:
            out: dict[str, Any] = {}
            for m in names:
                try:
                    out[m] = bus.read(data_name, m, normalize=normalize)
                except Exception as e_read:
                    out[m] = {
                        "_error": f"sync_read={type(e_sync).__name__}: {e_sync}; read={type(e_read).__name__}: {e_read}"
                    }
            return out

    def _send_gripper_percent(self, percent: float) -> dict[str, Any]:
        """Send gripper command in normalized 0..100 units.

        Returns the action actually sent (may be clipped by robot safety limits).
        """
        percent = float(np.clip(float(percent), 0.0, 100.0))
        action_sent = self._send_joint_targets_deg({"gripper": percent})
        return {"target_percent": percent, "action_sent": action_sent}

    def get_ee_pose(self) -> np.ndarray:
        kin = self._require_kin()
        q = self._read_joints_deg(_SO101_JOINTS)
        q_arr = np.array([q[j] for j in _SO101_JOINTS], dtype=float)
        return kin.forward_kinematics(q_arr)

    def _clamp_xyz(self, xyz_m: np.ndarray, *, clamp_mask: np.ndarray | None = None) -> np.ndarray:
        """Clamp xyz to optional workspace bounds.

        Args:
            xyz_m: Position in meters (shape (3,))
            clamp_mask: Optional boolean mask (shape (3,)) indicating which axes are allowed to be clamped.
                This is useful for delta-moves: if dz=0, we should not "pull" Z into bounds.
        """
        xyz = np.array(xyz_m, dtype=float).reshape(3)
        if self.ee_min_m is None or self.ee_max_m is None:
            return xyz

        clamped = np.clip(xyz, self.ee_min_m, self.ee_max_m)
        if clamp_mask is not None:
            mask = np.array(clamp_mask, dtype=bool).reshape(3)
            clamped = np.where(mask, clamped, xyz)
        return clamped

    def _ik_to_targets(
        self, *, T_target: np.ndarray, q_seed_deg: np.ndarray, position_only: bool = False
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute IK and verify via FK.

        Returns:
            (q_solution_deg, achieved_xyz_m) - the IK solution and FK-verified position.
        """
        kin = self._require_kin()

        # Use zero orientation weight for pure position moves (e.g., delta moves)
        orient_w = 0.0 if position_only else 0.02

        q_sol = kin.inverse_kinematics(q_seed_deg, T_target, position_weight=1.0, orientation_weight=orient_w)

        # Verify solution via FK
        T_achieved = kin.forward_kinematics(q_sol)
        xyz_achieved = T_achieved[:3, 3].astype(float)

        return q_sol, xyz_achieved

    def _move_ee_delta_jacobian(
        self,
        *,
        delta_xyz_m: np.ndarray,
        gripper_pos: float | None,
        max_joint_delta_deg: float = 5.0,
    ) -> dict[str, Any]:
        """Move EE by a delta using Jacobian-based control.

        This is more stable than full IK for small delta moves because it
        keeps the arm in roughly the same configuration instead of potentially
        jumping to a different IK solution.

        Args:
            delta_xyz_m: Desired EE position change [dx, dy, dz] in meters.
            gripper_pos: Gripper position (0-100), or None to keep current.
            max_joint_delta_deg: Maximum joint change per axis (degrees).
        """
        robot = self._require_robot()
        bus = robot.bus
        kin = self._require_kin()
        motors_all = list(bus.motors)

        # Pre-flight diagnostics (helps explain "stall" cases).
        diag_before: dict[str, Any] = {
            "Torque_Enable": self._try_read_bus_register("Torque_Enable", motors=motors_all, normalize=False),
            "Status": self._try_read_bus_register("Status", motors=motors_all, normalize=False),
            "Moving": self._try_read_bus_register("Moving", motors=motors_all, normalize=False),
            "Present_Current": self._try_read_bus_register("Present_Current", motors=motors_all, normalize=False),
            "Present_Load": self._try_read_bus_register("Present_Load", motors=motors_all, normalize=False),
            "Present_Voltage": self._try_read_bus_register("Present_Voltage", motors=motors_all, normalize=False),
            "Present_Temperature": self._try_read_bus_register("Present_Temperature", motors=motors_all, normalize=False),
            "Goal_Velocity": self._try_read_bus_register("Goal_Velocity", motors=motors_all, normalize=False),
            "Goal_Time": self._try_read_bus_register("Goal_Time", motors=motors_all, normalize=False),
            "Torque_Limit": self._try_read_bus_register("Torque_Limit", motors=motors_all, normalize=False),
            "Max_Torque_Limit": self._try_read_bus_register("Max_Torque_Limit", motors=motors_all, normalize=False),
            "CW_Dead_Zone": self._try_read_bus_register("CW_Dead_Zone", motors=motors_all, normalize=False),
            "CCW_Dead_Zone": self._try_read_bus_register("CCW_Dead_Zone", motors=motors_all, normalize=False),
            "Minimum_Startup_Force": self._try_read_bus_register("Minimum_Startup_Force", motors=motors_all, normalize=False),
            "Operating_Mode": self._try_read_bus_register("Operating_Mode", motors=motors_all, normalize=False),
        }

        # If any motor has torque disabled (common after overload protection), try to re-enable once.
        torque_reenabled: dict[str, Any] | None = None
        te = diag_before.get("Torque_Enable") or {}
        if isinstance(te, dict) and "_error" not in te:
            disabled = [m for m, v in te.items() if int(v) == 0]
            if disabled:
                try:
                    bus.enable_torque(disabled)
                    torque_reenabled = {"ok": True, "motors": disabled}
                    # Refresh key bits after re-enable
                    diag_before["Torque_Enable_after_reenable"] = self._try_read_bus_register(
                        "Torque_Enable", motors=motors_all, normalize=False
                    )
                except Exception as e:
                    torque_reenabled = {"ok": False, "motors": disabled, "error": f"{type(e).__name__}: {e}"}

        # Read start state
        q_start = self._read_joints_deg(_SO101_JOINTS)
        q_arr = np.array([q_start[j] for j in _SO101_JOINTS], dtype=float)
        T_start = kin.forward_kinematics(q_arr)
        xyz_start = T_start[:3, 3].astype(float)

        # Define a single absolute goal in Cartesian space.
        # IMPORTANT: do NOT clamp axes that were not requested (e.g. dz=0 must not pull Z).
        delta_xyz_m = np.array(delta_xyz_m, dtype=float).reshape(3)
        xyz_goal_raw = xyz_start + delta_xyz_m
        clamp_mask = np.abs(delta_xyz_m) > 1e-12
        xyz_goal = self._clamp_xyz(xyz_goal_raw, clamp_mask=clamp_mask)

        # Closed-loop: multiple small Jacobian steps toward the goal.
        max_iters = 4
        pos_tol_m = 0.002  # 2mm
        max_step_m = 0.02  # 20mm per internal step
        per_iter_sleep_s = 0.30
        stall_min_progress_m = 0.0005  # 0.5mm

        xyz_prev = xyz_start
        q_prev_arr = q_arr
        q_after: dict[str, float] = q_start
        targets_deg: dict[str, float] = {j: float(q_prev_arr[i]) for i, j in enumerate(_SO101_JOINTS)}
        action_sent: dict[str, Any] | None = None
        xyz_expected = xyz_start
        stall_count = 0
        iters_done = 0

        for _iter in range(max_iters):
            remaining = xyz_goal - xyz_prev
            remaining_norm = float(np.linalg.norm(remaining))
            if remaining_norm < pos_tol_m:
                break

            step = remaining
            if remaining_norm > max_step_m:
                step = step * (max_step_m / remaining_norm)

            # Compute joint deltas using Jacobian for this step
            q_new = kin.jacobian_delta_ik(q_prev_arr, step, max_joint_delta_deg=max_joint_delta_deg)

            # Expected EE pose if targets are achieved (FK on the kinematic model)
            T_expected = kin.forward_kinematics(q_new)
            xyz_expected = T_expected[:3, 3].astype(float)

            targets_deg = {j: float(q_new[i]) for i, j in enumerate(_SO101_JOINTS)}
            if gripper_pos is not None:
                targets_deg["gripper"] = float(np.clip(float(gripper_pos), 0.0, 100.0))

            action_sent = self._send_joint_targets_deg(targets_deg)

            # Wait and observe what actually happened
            time.sleep(per_iter_sleep_s)
            q_after = self._read_joints_deg(_SO101_JOINTS)
            q_after_arr = np.array([q_after[j] for j in _SO101_JOINTS], dtype=float)
            T_after = kin.forward_kinematics(q_after_arr)
            xyz_after = T_after[:3, 3].astype(float)

            iters_done += 1
            progress = float(np.linalg.norm(xyz_after - xyz_prev))
            if progress < stall_min_progress_m:
                stall_count += 1
                if stall_count >= 2:
                    xyz_prev = xyz_after
                    q_prev_arr = q_after_arr
                    break
            else:
                stall_count = 0

            xyz_prev = xyz_after
            q_prev_arr = q_after_arr

        final_err_m = float(np.linalg.norm(xyz_goal - xyz_prev))
        diag_after: dict[str, Any] = {
            "Torque_Enable": self._try_read_bus_register("Torque_Enable", motors=motors_all, normalize=False),
            "Status": self._try_read_bus_register("Status", motors=motors_all, normalize=False),
            "Moving": self._try_read_bus_register("Moving", motors=motors_all, normalize=False),
            "Present_Current": self._try_read_bus_register("Present_Current", motors=motors_all, normalize=False),
            "Present_Load": self._try_read_bus_register("Present_Load", motors=motors_all, normalize=False),
            "Present_Voltage": self._try_read_bus_register("Present_Voltage", motors=motors_all, normalize=False),
            "Present_Temperature": self._try_read_bus_register("Present_Temperature", motors=motors_all, normalize=False),
            "Goal_Position": self._try_read_bus_register("Goal_Position", motors=motors_all, normalize=True),
            "Goal_Time": self._try_read_bus_register("Goal_Time", motors=motors_all, normalize=False),
            "Goal_Velocity": self._try_read_bus_register("Goal_Velocity", motors=motors_all, normalize=False),
        }
        return {
            "ok": True,
            "xyz_target_m": xyz_goal.tolist(),
            "xyz_target_raw_m": xyz_goal_raw.tolist(),
            "xyz_jacobian_expected_m": xyz_expected.tolist(),
            "ee_before_m": xyz_start.tolist(),
            "ee_after_m": xyz_prev.tolist(),
            "ee_delta_m": (xyz_prev - xyz_start).tolist(),
            "ee_delta_requested_m": delta_xyz_m.tolist(),
            "final_position_err_mm": float(final_err_m * 1000.0),
            "iters": int(iters_done),
            "stalled": bool(stall_count >= 2 and final_err_m > pos_tol_m),
            "action_sent": action_sent,
            "joint_targets_deg": targets_deg,
            "joint_before_deg": q_start,
            "joint_after_deg": q_after,
            "torque_reenabled": torque_reenabled,
            "motor_diag_before": diag_before,
            "motor_diag_after": diag_after,
            "robot_connected": bool(robot.is_connected),
        }

    def _move_ee_to(
        self,
        *,
        xyz_m: np.ndarray,
        R_fixed: np.ndarray | None,
        gripper_pos: float | None,
        position_only: bool = False,
        max_ik_iters: int = 3,
        position_tol_m: float = 0.005,
        clamp_mask: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """Move EE to absolute xyz (meters) using IK. Returns a rich result dict.

        Args:
            xyz_m: Target position in meters.
            R_fixed: Fixed orientation (if None, uses current orientation).
            gripper_pos: Gripper position (0-100).
            position_only: If True, ignores orientation in IK (better for delta moves).
            max_ik_iters: Max IK refinement iterations if FK verification fails.
            position_tol_m: Acceptable position error (meters) for IK verification.
        """

        robot = self._require_robot()
        kin = self._require_kin()

        q_now = self._read_joints_deg(_SO101_JOINTS)
        q_seed = np.array([q_now[j] for j in _SO101_JOINTS], dtype=float)

        T_now = kin.forward_kinematics(q_seed)
        xyz0 = T_now[:3, 3].astype(float)
        R0 = T_now[:3, :3].astype(float)

        xyz_target_raw = np.array(xyz_m, dtype=float).reshape(3)
        xyz_target = self._clamp_xyz(xyz_target_raw, clamp_mask=clamp_mask)
        R_use = R0 if R_fixed is None else np.array(R_fixed, dtype=float).reshape(3, 3)

        T = np.eye(4, dtype=float)
        T[:3, :3] = R_use
        T[:3, 3] = xyz_target

        # Iterative IK with FK verification
        q_best = q_seed.copy()
        xyz_ik_best = xyz0.copy()
        best_err = float("inf")

        for _iter in range(max_ik_iters):
            q_sol, xyz_ik = self._ik_to_targets(
                T_target=T, q_seed_deg=q_best, position_only=position_only
            )

            err = float(np.linalg.norm(xyz_ik - xyz_target))
            if err < best_err:
                best_err = err
                q_best = q_sol
                xyz_ik_best = xyz_ik

            if err < position_tol_m:
                break

            # Use the current solution as seed for next iteration
            # (placo solver state is already updated, so next call refines)

        targets_deg = {j: float(q_best[i]) for i, j in enumerate(_SO101_JOINTS)}
        if gripper_pos is not None:
            targets_deg["gripper"] = float(np.clip(float(gripper_pos), 0.0, 100.0))

        action_sent = self._send_joint_targets_deg(targets_deg)

        # Predicted IK quality (in-model).
        ik_ok = best_err < 0.010

        # Wait for motion to settle before reading back.
        # The arm can take >0.25s for moderate joint deltas; reading too early
        # causes false "miss" detections and thrashing correction loops.
        try:
            max_joint_delta_deg = 0.0
            for j in _SO101_JOINTS:
                if j in targets_deg and j in q_now:
                    max_joint_delta_deg = max(
                        max_joint_delta_deg, abs(float(targets_deg[j]) - float(q_now[j]))
                    )
            # Conservative speed estimate (deg/s). Tweak if needed.
            deg_per_s = 25.0
            sleep_s = float(np.clip(max_joint_delta_deg / deg_per_s, 0.25, 1.20))
        except Exception:
            sleep_s = 0.35
        time.sleep(sleep_s)
        q_after = self._read_joints_deg(_SO101_JOINTS)
        q_after_arr = np.array([q_after[j] for j in _SO101_JOINTS], dtype=float)
        T_after = kin.forward_kinematics(q_after_arr)
        xyz1 = T_after[:3, 3].astype(float)

        achieved_err_m = float(np.linalg.norm(xyz1 - xyz_target))
        achieved_ok = achieved_err_m < 0.015

        # Only trust commanded reference if the robot actually reached the target-ish.
        # This prevents accumulating toward unreachable targets or reading back too early.
        if achieved_ok:
            self._ee_cmd_xyz_m = xyz_target.copy()
        else:
            self._ee_cmd_xyz_m = None

        return {
            "ok": bool(achieved_ok),
            "ik_ok": bool(achieved_ok),
            "ik_ok_predicted": bool(ik_ok),
            "xyz_target_m": xyz_target.tolist(),
            "xyz_target_raw_m": xyz_target_raw.tolist(),
            "xyz_ik_verified_m": xyz_ik_best.tolist(),
            "ik_position_err_mm": float(best_err * 1000.0),
            "achieved_position_err_mm": float(achieved_err_m * 1000.0),
            "ee_before_m": xyz0.tolist(),
            "ee_after_m": xyz1.tolist(),
            "ee_delta_m": (xyz1 - xyz0).tolist(),
            "action_sent": action_sent,
            "joint_targets_deg": targets_deg,
            "joint_after_deg": q_after,
            "robot_connected": bool(robot.is_connected),
        }

    # -----------------------------
    # Tool dispatch + schemas
    # -----------------------------

    def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        name = str(name)
        args = dict(args or {})

        # When torque is off, allow only safe introspection + torque recovery tools.
        if self.torque_disabled and name not in {"read_joints", "read_motor_diagnostics", "enable_torque", "disable_torque"}:
            return {
                "ok": False,
                "error": "Torque is disabled. Re-enable torque before running tools.",
                "tool": name,
            }

        if name == "move_gripper_delta":
            from tool_move_gripper_delta import execute as exec_tool

            return exec_tool(self, args)
        if name == "set_gripper_percent":
            from tool_set_gripper_percent import execute as exec_tool

            return exec_tool(self, args)
        if name == "open_gripper":
            from tool_open_gripper import execute as exec_tool

            return exec_tool(self, args)
        if name == "close_gripper":
            from tool_close_gripper import execute as exec_tool

            return exec_tool(self, args)
        if name == "go_home":
            from tool_go_home import execute as exec_tool

            return exec_tool(self, args)
        if name == "go_birds_eye":
            from tool_go_birds_eye import execute as exec_tool

            return exec_tool(self, args)
        if name == "move_piece":
            from tool_move_piece import execute as exec_tool

            return exec_tool(self, args)
        if name == "move_to_square":
            from tool_move_to_square import execute as exec_tool

            return exec_tool(self, args)
        if name == "nudge_gripper":
            from tool_nudge_gripper import execute as exec_tool

            return exec_tool(self, args)
        if name == "look_around":
            from tool_look_around import execute as exec_tool

            return exec_tool(self, args)
        if name == "read_joints":
            from tool_read_joints import execute as exec_tool

            return exec_tool(self, args)
        if name == "move_joints":
            from tool_move_joints import execute as exec_tool

            return exec_tool(self, args)
        if name == "set_all_joints":
            from tool_set_all_joints import execute as exec_tool

            return exec_tool(self, args)
        if name == "read_motor_diagnostics":
            # Expose diagnostics as an LLM tool as well.
            motors = args.get("motors")
            motors_list = None
            if isinstance(motors, list) and all(isinstance(x, str) for x in motors):
                motors_list = [str(x) for x in motors]
            return self.read_motor_diagnostics(motors=motors_list)
        if name == "disable_torque":
            motors = args.get("motors")
            motors_list = None
            if isinstance(motors, list) and all(isinstance(x, str) for x in motors):
                motors_list = [str(x) for x in motors]
            return self.disable_torque(motors=motors_list)
        if name == "enable_torque":
            motors = args.get("motors")
            motors_list = None
            if isinstance(motors, list) and all(isinstance(x, str) for x in motors):
                motors_list = [str(x) for x in motors]
            return self.enable_torque(motors=motors_list)

        return {"ok": False, "error": f"Unknown tool: {name}"}

    def tool_schemas(self) -> list[dict[str, Any]]:
        from tool_go_home import schema as schema_go_home
        from tool_go_birds_eye import schema as schema_go_birds_eye
        from tool_move_piece import schema as schema_move_piece
        from tool_move_to_square import schema as schema_move_to_square
        from tool_nudge_gripper import schema as schema_nudge_gripper
        from tool_open_gripper import schema as schema_open_gripper
        from tool_close_gripper import schema as schema_close_gripper

        # Chess tools - includes fine control for visual alignment
        return [
            schema_go_birds_eye(),   # Observe full board
            schema_go_home(),        # Rest position
            schema_move_to_square(), # Position above a square
            schema_nudge_gripper(),  # Fine adjustment for alignment
            schema_open_gripper(),   # Release piece
            schema_close_gripper(),  # Grasp piece
            schema_move_piece(),     # Full pick and place (when alignment not needed)
        ]
