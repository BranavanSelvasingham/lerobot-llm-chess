#!/usr/bin/env python

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config import SimRobotConfig

try:
    from lerobot.robots.utils import ensure_safe_goal_position
except ModuleNotFoundError as exc:  # pragma: no cover - dependency-light sim runtime.
    if exc.name != "torch":
        raise

    def ensure_safe_goal_position(
        goal_present_pos: dict[str, tuple[float, float]], max_relative_target: float | dict[str, float]
    ) -> dict[str, float]:
        if isinstance(max_relative_target, float):
            diff_cap = dict.fromkeys(goal_present_pos, max_relative_target)
        elif isinstance(max_relative_target, dict):
            diff_cap = max_relative_target
        else:
            raise TypeError(max_relative_target)

        safe_goal_positions = {}
        for key, (goal_pos, present_pos) in goal_present_pos.items():
            max_diff = diff_cap[key]
            diff = goal_pos - present_pos
            safe_goal_positions[key] = present_pos + min(max(diff, -max_diff), max_diff)
        return safe_goal_positions

try:
    from lerobot.motors import Motor, MotorNormMode
except ModuleNotFoundError as exc:  # pragma: no cover - dependency-light sim runtime.
    if exc.name != "torch":
        raise

    class MotorNormMode(str, Enum):
        RANGE_0_100 = "range_0_100"
        DEGREES = "degrees"

    @dataclass(frozen=True)
    class Motor:
        id: int
        model: str
        norm_mode: MotorNormMode


try:
    from lerobot.robots.robot import Robot
except ModuleNotFoundError as exc:  # pragma: no cover - dependency-light sim runtime.
    if exc.name != "torch":
        raise

    class Robot:
        """Small simulator-only stand-in for the LeRobot base class.

        The full base class imports the training stack through motor utilities.
        The SO-101 simulator only needs calibration path bookkeeping for
        hardware-free Gymnasium/MuJoCo smoke tests.
        """

        def __init__(self, config: SimRobotConfig):
            self.robot_type = getattr(self, "name", "sim_so101")
            self.id = config.id
            self.calibration_dir = Path(config.calibration_dir)
            self.calibration_dir.mkdir(parents=True, exist_ok=True)
            self.calibration_fpath = self.calibration_dir / f"{self.id}.json"
            self.calibration = {}

SO101_BODY_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
)
SO101_JOINTS: tuple[str, ...] = (*SO101_BODY_JOINTS, "gripper")

DEFAULT_JOINT_POSITIONS_DEG: dict[str, float] = {
    "shoulder_pan": 0.0,
    "shoulder_lift": 0.0,
    "elbow_flex": 0.0,
    "wrist_flex": 0.0,
    "wrist_roll": 0.0,
    "gripper": 95.0,
}

JOINT_LIMITS_DEG: dict[str, tuple[float, float]] = {
    "shoulder_pan": (-110.0, 110.0),
    "shoulder_lift": (-110.0, 110.0),
    "elbow_flex": (-120.0, 120.0),
    "wrist_flex": (-120.0, 120.0),
    "wrist_roll": (-180.0, 180.0),
    "gripper": (0.0, 100.0),
}


@dataclass
class _MujocoBackend:
    module: Any
    model: Any
    data: Any
    joint_qpos_addr: dict[str, int]
    gripper_qpos_addr: int | None = None
    gripper_qpos_range: tuple[float, float] | None = None


class _SimSO101Bus:
    """Small in-memory subset of the Feetech bus API used by KinematicsTools."""

    def __init__(self, initial_positions: dict[str, float]):
        self.motors = {
            "shoulder_pan": Motor(1, "sts3215", MotorNormMode.DEGREES),
            "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),
            "elbow_flex": Motor(3, "sts3215", MotorNormMode.DEGREES),
            "wrist_flex": Motor(4, "sts3215", MotorNormMode.DEGREES),
            "wrist_roll": Motor(5, "sts3215", MotorNormMode.DEGREES),
            "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
        }
        self.is_connected = False
        self.positions_deg = dict(DEFAULT_JOINT_POSITIONS_DEG)
        self.positions_deg.update({k: float(v) for k, v in initial_positions.items() if k in SO101_JOINTS})
        self.goal_positions_deg = dict(self.positions_deg)
        self.torque_enabled = dict.fromkeys(SO101_JOINTS, 1)
        self.lock = dict.fromkeys(SO101_JOINTS, 1)
        self.goal_velocity = dict.fromkeys(SO101_JOINTS, 500)

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self) -> None:
        self.is_connected = True

    def disconnect(self, disable_torque: bool = True) -> None:
        if disable_torque:
            self.disable_torque()
        self.is_connected = False

    def configure_motors(self) -> None:
        return

    def disable_torque(self, motors: list[str] | None = None) -> None:
        for name in self._names(motors):
            self.torque_enabled[name] = 0

    def enable_torque(self, motors: list[str] | None = None) -> None:
        for name in self._names(motors):
            self.torque_enabled[name] = 1

    def sync_read(
        self, data_name: str, motors: list[str] | tuple[str, ...] | None = None, normalize: bool = True
    ) -> dict[str, Any]:
        _ = normalize
        return {name: self._read_value(data_name, name) for name in self._names(motors)}

    def read(self, data_name: str, motor: str, normalize: bool = True, **kwargs: Any) -> Any:
        _ = normalize
        _ = kwargs
        self._validate_motor(motor)
        return self._read_value(data_name, motor)

    def sync_write(
        self,
        data_name: str,
        values: dict[str, float] | float | int,
        motors: list[str] | tuple[str, ...] | None = None,
        normalize: bool = True,
        **kwargs: Any,
    ) -> None:
        _ = normalize
        _ = kwargs
        if isinstance(values, dict):
            items = values.items()
        else:
            items = ((name, values) for name in self._names(motors))

        for motor, value in items:
            self.write(data_name, motor, value, normalize=normalize)

    def write(
        self,
        data_name: str,
        motor: str,
        value: float | int,
        normalize: bool = True,
        **kwargs: Any,
    ) -> None:
        _ = normalize
        _ = kwargs
        self._validate_motor(motor)
        if data_name in {"Goal_Position", "Present_Position"}:
            clipped = _clip_joint(motor, float(value))
            self.goal_positions_deg[motor] = clipped
            self.positions_deg[motor] = clipped
        elif data_name == "Torque_Enable":
            self.torque_enabled[motor] = int(value)
        elif data_name == "Lock":
            self.lock[motor] = int(value)
        elif data_name == "Goal_Velocity":
            self.goal_velocity[motor] = int(value)

    def _read_value(self, data_name: str, motor: str) -> Any:
        self._validate_motor(motor)
        if data_name == "Present_Position":
            return float(self.positions_deg[motor])
        if data_name == "Goal_Position":
            return float(self.goal_positions_deg[motor])
        if data_name == "Torque_Enable":
            return int(self.torque_enabled[motor])
        if data_name == "Lock":
            return int(self.lock[motor])
        if data_name == "Goal_Velocity":
            return int(self.goal_velocity[motor])
        if data_name == "Moving":
            return 0
        if data_name in {"Present_Velocity", "Present_Load", "Present_Current", "Status"}:
            return 0
        if data_name == "Present_Voltage":
            return 740
        if data_name == "Present_Temperature":
            return 25
        if data_name in {
            "Max_Torque_Limit",
            "Torque_Limit",
            "Protection_Current",
            "Protective_Torque",
            "Protection_Time",
            "Overload_Torque",
            "Goal_Time",
            "CW_Dead_Zone",
            "CCW_Dead_Zone",
            "Minimum_Startup_Force",
            "Operating_Mode",
        }:
            return 0
        raise KeyError(f"Sim bus register '{data_name}' is not implemented.")

    def _names(self, motors: list[str] | tuple[str, ...] | None = None) -> list[str]:
        names = list(self.motors) if motors is None else list(motors)
        for name in names:
            self._validate_motor(name)
        return names

    def _validate_motor(self, name: str) -> None:
        if name not in self.motors:
            raise KeyError(f"Unknown SO-101 sim motor '{name}'. Expected one of {list(self.motors)}.")


class SimRobot(Robot):
    """Virtual SO-101 robot with optional MuJoCo model loading and safe fallback state."""

    config_class = SimRobotConfig
    name = "sim_so101"

    def __init__(self, config: SimRobotConfig):
        super().__init__(config)
        self.config = config
        self.bus = _SimSO101Bus(config.initial_positions)
        self.cameras = make_cameras_from_configs(config.cameras)
        self._mujoco_backend: _MujocoBackend | None = None
        self.mujoco_status: dict[str, Any] = {
            "ok": False,
            "enabled": bool(config.use_mujoco),
            "fallback": "joint_state",
            "reason": "MuJoCo backend has not been initialized.",
        }

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {f"{motor}.pos": float for motor in self.bus.motors}

    @property
    def _cameras_ft(self) -> dict[str, tuple[int, int, int]]:
        return {
            cam: (int(self.config.cameras[cam].height), int(self.config.cameras[cam].width), 3)
            for cam in self.cameras
        }

    @property
    def observation_features(self) -> dict[str, type | tuple[int, int, int]]:
        return {**self._motors_ft, **self._cameras_ft}

    @property
    def action_features(self) -> dict[str, type]:
        return self._motors_ft

    @property
    def is_connected(self) -> bool:
        return self.bus.is_connected and all(cam.is_connected for cam in self.cameras.values())

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self, calibrate: bool = True) -> None:
        _ = calibrate
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        self.bus.connect()
        self._sync_cameras_to_state()
        for cam in self.cameras.values():
            cam.connect()
        self.configure()

    def calibrate(self) -> None:
        return

    def configure(self) -> None:
        self._initialize_mujoco()
        self._sync_mujoco_from_bus()

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        obs_dict = {f"{motor}.pos": val for motor, val in self.bus.sync_read("Present_Position").items()}
        self._sync_cameras_to_state()
        for cam_key, cam in self.cameras.items():
            obs_dict[cam_key] = cam.async_read()
        return obs_dict

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        requested = {
            key.removesuffix(".pos"): float(val)
            for key, val in action.items()
            if key.endswith(".pos")
        }
        unknown = sorted(set(requested) - set(SO101_JOINTS))
        if unknown:
            raise ValueError(f"Unknown SO-101 sim joint(s): {unknown}")

        goal_pos = {name: _clip_joint(name, value) for name, value in requested.items()}
        if self.config.max_relative_target is not None:
            present_pos = self.bus.sync_read("Present_Position", list(goal_pos))
            goal_present_pos = {key: (g_pos, present_pos[key]) for key, g_pos in goal_pos.items()}
            goal_pos = ensure_safe_goal_position(goal_present_pos, self.config.max_relative_target)

        self.bus.sync_write("Goal_Position", goal_pos)
        self._sync_mujoco_from_bus()
        self._sync_cameras_to_state()
        return {f"{motor}.pos": val for motor, val in goal_pos.items()}

    def disconnect(self) -> None:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        for cam in self.cameras.values():
            cam.disconnect()
        self.bus.disconnect(disable_torque=False)

    def sim_status(self) -> dict[str, Any]:
        return dict(self.mujoco_status)

    def set_mujoco_freejoint_pose(
        self,
        joint_name: str,
        position_xyz_m: tuple[float, float, float] | list[float],
        *,
        quat_wxyz: tuple[float, float, float, float] | list[float] = (1.0, 0.0, 0.0, 0.0),
        reason: str = "manual",
    ) -> dict[str, Any]:
        backend = self._mujoco_backend
        if backend is None:
            return {"ok": False, "joint_name": joint_name, "reason": "mujoco_backend_unavailable", "sync_reason": reason}
        try:
            joint_id = backend.module.mj_name2id(
                backend.model,
                backend.module.mjtObj.mjOBJ_JOINT,
                joint_name,
            )
            if joint_id < 0:
                return {"ok": False, "joint_name": joint_name, "reason": "joint_not_found", "sync_reason": reason}
            qpos_addr = int(backend.model.jnt_qposadr[joint_id])
            backend.data.qpos[qpos_addr : qpos_addr + 7] = [
                float(position_xyz_m[0]),
                float(position_xyz_m[1]),
                float(position_xyz_m[2]),
                float(quat_wxyz[0]),
                float(quat_wxyz[1]),
                float(quat_wxyz[2]),
                float(quat_wxyz[3]),
            ]
            qvel_addr = int(backend.model.jnt_dofadr[joint_id])
            backend.data.qvel[qvel_addr : qvel_addr + 6] = 0.0
            backend.module.mj_forward(backend.model, backend.data)
            return {
                "ok": True,
                "joint_name": joint_name,
                "qpos_addr": qpos_addr,
                "position_xyz_m": [float(v) for v in position_xyz_m],
                "quat_wxyz": [float(v) for v in quat_wxyz],
                "sync_reason": reason,
            }
        except Exception as e:
            return {
                "ok": False,
                "joint_name": joint_name,
                "reason": f"{type(e).__name__}: {e}",
                "sync_reason": reason,
            }

    def mujoco_freejoint_pose(self, joint_name: str) -> dict[str, Any]:
        backend = self._mujoco_backend
        if backend is None:
            return {"ok": False, "joint_name": joint_name, "reason": "mujoco_backend_unavailable"}
        try:
            joint_id = backend.module.mj_name2id(
                backend.model,
                backend.module.mjtObj.mjOBJ_JOINT,
                joint_name,
            )
            if joint_id < 0:
                return {"ok": False, "joint_name": joint_name, "reason": "joint_not_found"}
            qpos_addr = int(backend.model.jnt_qposadr[joint_id])
            qpos = backend.data.qpos[qpos_addr : qpos_addr + 7]
            return {
                "ok": True,
                "joint_name": joint_name,
                "qpos_addr": qpos_addr,
                "position_xyz_m": [float(qpos[0]), float(qpos[1]), float(qpos[2])],
                "quat_wxyz": [float(qpos[3]), float(qpos[4]), float(qpos[5]), float(qpos[6])],
            }
        except Exception as e:
            return {"ok": False, "joint_name": joint_name, "reason": f"{type(e).__name__}: {e}"}

    def _initialize_mujoco(self) -> None:
        if not self.config.use_mujoco:
            self.mujoco_status = {
                "ok": False,
                "enabled": False,
                "fallback": "joint_state",
                "reason": "MuJoCo disabled by SimRobotConfig.use_mujoco=False.",
            }
            return

        model_path = self.config.mujoco_model_path
        if model_path is None:
            self.mujoco_status = {
                "ok": False,
                "enabled": True,
                "fallback": "joint_state",
                "reason": "No MuJoCo model path configured; using in-memory joint state.",
            }
            return

        path = Path(model_path).expanduser()
        if not path.is_file():
            self.mujoco_status = {
                "ok": False,
                "enabled": True,
                "fallback": "joint_state",
                "reason": f"MuJoCo model path does not exist: {path}",
            }
            return

        try:
            import mujoco
        except Exception as e:
            self.mujoco_status = {
                "ok": False,
                "enabled": True,
                "fallback": "joint_state",
                "reason": f"MuJoCo Python package is not installed or failed to import: {e}",
            }
            return

        try:
            model = mujoco.MjModel.from_xml_path(str(path))
            data = mujoco.MjData(model)
            joint_qpos_addr: dict[str, int] = {}
            for joint in SO101_BODY_JOINTS:
                joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
                if joint_id >= 0:
                    joint_qpos_addr[joint] = int(model.jnt_qposadr[joint_id])
            gripper_qpos_addr: int | None = None
            gripper_qpos_range: tuple[float, float] | None = None
            gripper_joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "gripper")
            if gripper_joint_id >= 0:
                gripper_qpos_addr = int(model.jnt_qposadr[gripper_joint_id])
                gripper_qpos_range = (
                    float(model.jnt_range[gripper_joint_id][0]),
                    float(model.jnt_range[gripper_joint_id][1]),
                )
            self._mujoco_backend = _MujocoBackend(
                mujoco,
                model,
                data,
                joint_qpos_addr,
                gripper_qpos_addr=gripper_qpos_addr,
                gripper_qpos_range=gripper_qpos_range,
            )
            mapped_joints = sorted(joint_qpos_addr)
            if gripper_qpos_addr is not None:
                mapped_joints.append("gripper")
            self.mujoco_status = {
                "ok": True,
                "enabled": True,
                "fallback": None,
                "model_path": str(path),
                "mapped_joints": mapped_joints,
                "missing_joints": [j for j in SO101_JOINTS if j not in mapped_joints],
                "gripper_qpos_range": list(gripper_qpos_range) if gripper_qpos_range else None,
            }
        except Exception as e:
            self._mujoco_backend = None
            self.mujoco_status = {
                "ok": False,
                "enabled": True,
                "fallback": "joint_state",
                "reason": f"MuJoCo failed to load model '{path}': {type(e).__name__}: {e}",
            }

    def _sync_mujoco_from_bus(self) -> None:
        backend = self._mujoco_backend
        if backend is None:
            return
        try:
            for joint, qpos_addr in backend.joint_qpos_addr.items():
                backend.data.qpos[qpos_addr] = np.deg2rad(self.bus.positions_deg[joint])
            if backend.gripper_qpos_addr is not None and backend.gripper_qpos_range is not None:
                lo, hi = backend.gripper_qpos_range
                opening = np.clip(self.bus.positions_deg["gripper"], 0.0, 100.0) / 100.0
                backend.data.qpos[backend.gripper_qpos_addr] = lo + opening * (hi - lo)
            backend.module.mj_forward(backend.model, backend.data)
        except Exception as e:
            self.mujoco_status = {
                "ok": False,
                "enabled": True,
                "fallback": "joint_state",
                "reason": f"MuJoCo state sync failed; using joint-state fallback: {type(e).__name__}: {e}",
            }
            self._mujoco_backend = None

    def _sync_cameras_to_state(self) -> None:
        joints = dict(self.bus.positions_deg)
        for cam in self.cameras.values():
            set_robot_state = getattr(cam, "set_robot_state", None)
            if callable(set_robot_state):
                set_robot_state(joints)


def _clip_joint(name: str, value: float) -> float:
    lo, hi = JOINT_LIMITS_DEG[name]
    return float(np.clip(value, lo, hi))
