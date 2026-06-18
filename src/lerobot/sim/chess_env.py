#!/usr/bin/env python

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from lerobot.configs.chessboard import ChessBoardParams

from .config import CURRENT_GRIPPER_REFERENCE_PROFILE, make_sim_camera_config_from_profile
from .robot import DEFAULT_JOINT_POSITIONS_DEG, JOINT_LIMITS_DEG, SO101_JOINTS, SimRobot

try:  # Gymnasium is a project dependency, but keep import-time diagnostics explicit.
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover - exercised in dependency-light shells.
    gym = None
    spaces = None


SO101_CHESS_ENV_SCHEMA = "lerobot.sim.so101_chess_env.v1"
SO101_CHESS_SCENE_SCHEMA = "lerobot.sim.so101_chess_scene.v1"


def gymnasium_available() -> bool:
    return gym is not None and spaces is not None


def dependency_status() -> dict[str, bool]:
    return {
        "gymnasium": gymnasium_available(),
        "mujoco": importlib.util.find_spec("mujoco") is not None,
    }


def square_to_indices(square: str) -> tuple[int, int]:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(value[0]) - ord("a"), int(value[1]) - 1


def square_index(square: str) -> int:
    file_idx, rank_idx = square_to_indices(square)
    return rank_idx * 8 + file_idx


def square_center_m(square: str, board_params: ChessBoardParams) -> np.ndarray:
    file_idx, rank_idx = square_to_indices(square)
    sx = board_params.effective_square_size_x_mm / 1000.0
    sy = board_params.effective_square_size_y_mm / 1000.0
    return np.array(
        [
            (file_idx + 0.5) * sx,
            (rank_idx + 0.5) * sy,
            board_params.board_height_mm / 1000.0,
        ],
        dtype=np.float32,
    )


def _clip_joint_targets(targets: dict[str, float]) -> dict[str, float]:
    clipped: dict[str, float] = {}
    for joint, value in targets.items():
        lo, hi = JOINT_LIMITS_DEG[joint]
        clipped[joint] = float(np.clip(float(value), lo, hi))
    return clipped


def _joint_array(targets: dict[str, float]) -> np.ndarray:
    return np.array([float(targets[joint]) for joint in SO101_JOINTS], dtype=np.float32)


@dataclass(kw_only=True)
class SO101ChessEnvConfig:
    """Configuration for the first training-facing SO-101 chess simulator env.

    The environment is intentionally honest about its maturity: it can run with
    the existing in-memory joint backend, and it reports whether a real MuJoCo
    model was loaded. The board/piece scene is symbolic until a reviewed MJCF
    robot/world bundle is supplied and contact validation is added.
    """

    source_square: str = "e4"
    target_square: str = "e5"
    max_steps: int = 96
    action_scale_deg: float = 8.0
    waypoint_tolerance_deg: float = 1.0
    use_mujoco: bool = True
    mujoco_model_path: str | Path | None = None
    sim_camera_profile: str = CURRENT_GRIPPER_REFERENCE_PROFILE
    include_camera: bool = False
    initial_positions: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_JOINT_POSITIONS_DEG))
    board_params: ChessBoardParams = field(default_factory=ChessBoardParams)
    task_pool: tuple[tuple[str, str], ...] = ()
    sample_task_on_reset: bool = False
    board_origin_m: tuple[float, float, float] = (0.12, -0.20, 0.0)
    open_gripper_percent: float = 95.0
    closed_gripper_percent: float = 0.0
    piece_radius_m: float = 0.014
    piece_height_m: float = 0.038

    def __post_init__(self) -> None:
        square_to_indices(self.source_square)
        square_to_indices(self.target_square)
        if self.source_square == self.target_square:
            raise ValueError("source_square and target_square must differ.")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive.")
        if self.action_scale_deg <= 0:
            raise ValueError("action_scale_deg must be positive.")
        if self.waypoint_tolerance_deg <= 0:
            raise ValueError("waypoint_tolerance_deg must be positive.")
        for source, target in self.task_pool:
            square_to_indices(source)
            square_to_indices(target)
            if source == target:
                raise ValueError(f"task_pool contains identical source/target square {source!r}.")


@dataclass(frozen=True)
class ScriptedJointWaypoint:
    name: str
    square: str
    targets_deg: dict[str, float]
    carries_piece: bool


def square_joint_pose(
    square: str,
    *,
    hover: bool,
    gripper_percent: float,
) -> dict[str, float]:
    """Return a deterministic joint-space scaffold pose for a board square.

    This is not calibrated IK. It gives the Gymnasium environment a repeatable
    scriptable curriculum surface while the reviewed MuJoCo/MJCF model bundle,
    TCP offset, and base-to-board alignment are still being validated.
    """

    file_idx, rank_idx = square_to_indices(square)
    pan = (file_idx - 3.5) * 9.0
    lift = -44.0 + (rank_idx - 3.5) * 2.2
    elbow = 70.0 if hover else 84.0
    wrist_flex = -42.0 if hover else -54.0
    return _clip_joint_targets(
        {
            "shoulder_pan": pan,
            "shoulder_lift": lift,
            "elbow_flex": elbow,
            "wrist_flex": wrist_flex,
            "wrist_roll": 0.0,
            "gripper": gripper_percent,
        }
    )


def scripted_pick_place_waypoints(config: SO101ChessEnvConfig) -> tuple[ScriptedJointWaypoint, ...]:
    source = config.source_square
    target = config.target_square
    open_grip = config.open_gripper_percent
    closed_grip = config.closed_gripper_percent
    return (
        ScriptedJointWaypoint(
            "source_hover_open",
            source,
            square_joint_pose(source, hover=True, gripper_percent=open_grip),
            carries_piece=False,
        ),
        ScriptedJointWaypoint(
            "source_touch_open",
            source,
            square_joint_pose(source, hover=False, gripper_percent=open_grip),
            carries_piece=False,
        ),
        ScriptedJointWaypoint(
            "source_touch_grasp",
            source,
            square_joint_pose(source, hover=False, gripper_percent=closed_grip),
            carries_piece=True,
        ),
        ScriptedJointWaypoint(
            "source_hover_carry",
            source,
            square_joint_pose(source, hover=True, gripper_percent=closed_grip),
            carries_piece=True,
        ),
        ScriptedJointWaypoint(
            "target_hover_carry",
            target,
            square_joint_pose(target, hover=True, gripper_percent=closed_grip),
            carries_piece=True,
        ),
        ScriptedJointWaypoint(
            "target_touch_carry",
            target,
            square_joint_pose(target, hover=False, gripper_percent=closed_grip),
            carries_piece=True,
        ),
        ScriptedJointWaypoint(
            "target_touch_release",
            target,
            square_joint_pose(target, hover=False, gripper_percent=open_grip),
            carries_piece=False,
        ),
        ScriptedJointWaypoint(
            "target_hover_open",
            target,
            square_joint_pose(target, hover=True, gripper_percent=open_grip),
            carries_piece=False,
        ),
    )


def action_toward_targets(
    current_targets_deg: dict[str, float],
    target_targets_deg: dict[str, float],
    *,
    action_scale_deg: float,
) -> np.ndarray:
    deltas = []
    for joint in SO101_JOINTS:
        delta_deg = float(target_targets_deg[joint]) - float(current_targets_deg[joint])
        deltas.append(np.clip(delta_deg / action_scale_deg, -1.0, 1.0))
    return np.array(deltas, dtype=np.float32)


class SO101ChessEnv(gym.Env if gym is not None else object):  # type: ignore[misc]
    metadata = {"render_modes": []}

    def __init__(self, config: SO101ChessEnvConfig | None = None):
        self.config = config or SO101ChessEnvConfig()
        self.default_source_square = self.config.source_square
        self.default_target_square = self.config.target_square
        self.waypoints = scripted_pick_place_waypoints(self.config)
        self.step_count = 0
        self.phase_index = 0
        self.holding_piece = False
        self.piece_square = self.config.source_square
        self.robot: SimRobot | None = None

        if spaces is not None:
            lows = np.array([JOINT_LIMITS_DEG[joint][0] for joint in SO101_JOINTS], dtype=np.float32)
            highs = np.array([JOINT_LIMITS_DEG[joint][1] for joint in SO101_JOINTS], dtype=np.float32)
            self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(len(SO101_JOINTS),), dtype=np.float32)
            self.observation_space = spaces.Dict(
                {
                    "joint_positions_deg": spaces.Box(low=lows, high=highs, dtype=np.float32),
                    "source_square_xyz_m": spaces.Box(low=-np.inf, high=np.inf, shape=(3,), dtype=np.float32),
                    "target_square_xyz_m": spaces.Box(low=-np.inf, high=np.inf, shape=(3,), dtype=np.float32),
                    "piece_square_index": spaces.Box(low=0, high=63, shape=(1,), dtype=np.int64),
                    "holding_piece": spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32),
                    "phase_index": spaces.Box(low=0, high=len(self.waypoints), shape=(1,), dtype=np.int64),
                    "mujoco_active": spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32),
                }
            )

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        if gym is not None:
            super().reset(seed=seed)
        self._apply_reset_task_options(options or {}, seed=seed)
        self._ensure_robot()
        assert self.robot is not None
        self.step_count = 0
        self.phase_index = 0
        self.holding_piece = False
        self.piece_square = self.config.source_square
        self.robot.send_action({f"{joint}.pos": value for joint, value in self.config.initial_positions.items()})
        self._sync_mujoco_piece_to_square(self.piece_square, reason="reset")
        return self._observation(), self._info()

    def step(self, action: np.ndarray | Iterable[float]):
        self._ensure_robot()
        assert self.robot is not None
        self.step_count += 1

        action_array = np.asarray(list(action), dtype=np.float32)
        if action_array.shape != (len(SO101_JOINTS),):
            raise ValueError(f"Expected action shape {(len(SO101_JOINTS),)}, got {action_array.shape}.")
        action_array = np.clip(action_array, -1.0, 1.0)

        current = self._joint_positions()
        targets = {
            joint: float(current[joint] + action_array[index] * self.config.action_scale_deg)
            for index, joint in enumerate(SO101_JOINTS)
        }
        self.robot.send_action({f"{joint}.pos": value for joint, value in _clip_joint_targets(targets).items()})

        phase_bonus = self._advance_phase_if_reached()
        success = self.piece_square == self.config.target_square and not self.holding_piece
        truncated = self.step_count >= self.config.max_steps and not success
        reward = self._reward(success=success, phase_bonus=phase_bonus)
        return self._observation(), reward, success, truncated, self._info()

    def close(self) -> None:
        if self.robot is not None and self.robot.is_connected:
            self.robot.disconnect()

    def scene_state(self) -> dict[str, Any]:
        source_xyz = square_center_m(self.config.source_square, self.config.board_params)
        target_xyz = square_center_m(self.config.target_square, self.config.board_params)
        piece_xyz = square_center_m(self.piece_square, self.config.board_params)
        mujoco_piece = self._mujoco_piece_status()
        return {
            "schema": SO101_CHESS_SCENE_SCHEMA,
            "contact_model": "symbolic_piece_transfer_until_reviewed_mujoco_scene",
            "board": {
                "square_size_m": self.config.board_params.effective_square_size_x_mm / 1000.0,
                "size": list(self.config.board_params.board_size),
                "height_m": self.config.board_params.board_height_mm / 1000.0,
            },
            "piece": {
                "square": self.piece_square,
                "center_xyz_m": piece_xyz.astype(float).tolist(),
                "radius_m": float(self.config.piece_radius_m),
                "height_m": float(self.config.piece_height_m),
                "held_by_gripper": bool(self.holding_piece),
                "mujoco_freejoint": mujoco_piece,
            },
            "task": {
                "source_square": self.config.source_square,
                "source_xyz_m": source_xyz.astype(float).tolist(),
                "target_square": self.config.target_square,
                "target_xyz_m": target_xyz.astype(float).tolist(),
            },
        }

    def _ensure_robot(self) -> None:
        if self.robot is not None:
            return
        cameras = {}
        if self.config.include_camera:
            cameras["board"] = make_sim_camera_config_from_profile(self.config.sim_camera_profile)
        robot_cfg = self._robot_config(cameras)
        robot = SimRobot(robot_cfg)
        robot.connect()
        self.robot = robot

    def _robot_config(self, cameras: dict[str, Any]):
        from .config import SimRobotConfig

        return SimRobotConfig(
            cameras=cameras,
            initial_positions=dict(self.config.initial_positions),
            use_mujoco=bool(self.config.use_mujoco),
            mujoco_model_path=self.config.mujoco_model_path,
        )

    def _joint_positions(self) -> dict[str, float]:
        assert self.robot is not None
        obs = self.robot.get_observation()
        return {joint: float(obs[f"{joint}.pos"]) for joint in SO101_JOINTS}

    def _observation(self) -> dict[str, np.ndarray]:
        joints = self._joint_positions()
        sim_status = self.robot.sim_status() if self.robot is not None else {}
        return {
            "joint_positions_deg": _joint_array(joints),
            "source_square_xyz_m": square_center_m(self.config.source_square, self.config.board_params),
            "target_square_xyz_m": square_center_m(self.config.target_square, self.config.board_params),
            "piece_square_index": np.array([square_index(self.piece_square)], dtype=np.int64),
            "holding_piece": np.array([1.0 if self.holding_piece else 0.0], dtype=np.float32),
            "phase_index": np.array([self.phase_index], dtype=np.int64),
            "mujoco_active": np.array([1.0 if sim_status.get("ok") else 0.0], dtype=np.float32),
        }

    def _info(self) -> dict[str, Any]:
        sim_status = self.robot.sim_status() if self.robot is not None else {}
        waypoint = self.waypoints[min(self.phase_index, len(self.waypoints) - 1)]
        return {
            "schema": SO101_CHESS_ENV_SCHEMA,
            "dependencies": dependency_status(),
            "sim_status": sim_status,
            "scene_state": self.scene_state(),
            "step_count": self.step_count,
            "current_waypoint": {
                "index": self.phase_index,
                "name": waypoint.name,
                "square": waypoint.square,
                "targets_deg": dict(waypoint.targets_deg),
            },
            "task": {
                "source_square": self.config.source_square,
                "target_square": self.config.target_square,
                "task_pool_size": len(self.config.task_pool),
                "sample_task_on_reset": bool(self.config.sample_task_on_reset),
            },
        }

    def _apply_reset_task_options(self, options: dict[str, Any], *, seed: int | None) -> None:
        source_square = options.get("source_square")
        target_square = options.get("target_square")
        task = options.get("task")
        if task is not None:
            if isinstance(task, dict):
                source_square = task.get("source_square", task.get("source", source_square))
                target_square = task.get("target_square", task.get("target", target_square))
            elif isinstance(task, (list, tuple)) and len(task) == 2:
                source_square, target_square = task
            else:
                raise ValueError("reset option 'task' must be a dict or a 2-item sequence.")

        sample_task = bool(options.get("sample_task", self.config.sample_task_on_reset))
        task_pool = options.get("task_pool", self.config.task_pool)
        if sample_task:
            normalized_pool = self._normalize_task_pool(task_pool)
            if not normalized_pool:
                raise ValueError("sample_task requested but no task_pool was supplied.")
            rng = getattr(self, "np_random", None)
            if rng is None:
                rng = np.random.default_rng(seed)
            choice_index = int(rng.integers(0, len(normalized_pool)))
            source_square, target_square = normalized_pool[choice_index]

        if source_square is None:
            source_square = self.default_source_square
        if target_square is None:
            target_square = self.default_target_square
        self._set_task(str(source_square).lower(), str(target_square).lower())

    @staticmethod
    def _normalize_task_pool(task_pool: Any) -> tuple[tuple[str, str], ...]:
        if task_pool is None:
            return ()
        normalized: list[tuple[str, str]] = []
        for item in task_pool:
            if isinstance(item, dict):
                source = item.get("source_square", item.get("source"))
                target = item.get("target_square", item.get("target"))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                source, target = item
            else:
                raise ValueError(f"Invalid task pool item: {item!r}")
            if source is None or target is None:
                raise ValueError(f"Task pool item must include source and target squares: {item!r}")
            source_value = str(source).lower()
            target_value = str(target).lower()
            square_to_indices(source_value)
            square_to_indices(target_value)
            if source_value == target_value:
                raise ValueError(f"Task pool item has identical source/target square {source_value!r}.")
            normalized.append((source_value, target_value))
        return tuple(normalized)

    def _set_task(self, source_square: str, target_square: str) -> None:
        square_to_indices(source_square)
        square_to_indices(target_square)
        if source_square == target_square:
            raise ValueError("source_square and target_square must differ.")
        self.config.source_square = source_square
        self.config.target_square = target_square
        self.waypoints = scripted_pick_place_waypoints(self.config)

    def _advance_phase_if_reached(self) -> float:
        if self.phase_index >= len(self.waypoints):
            return 0.0

        joints = self._joint_positions()
        phase_bonus = 0.0
        while self.phase_index < len(self.waypoints):
            waypoint = self.waypoints[self.phase_index]
            err = self._joint_error_deg(joints, waypoint.targets_deg)
            if err > self.config.waypoint_tolerance_deg:
                break
            self.holding_piece = bool(waypoint.carries_piece)
            self.piece_square = waypoint.square if self.holding_piece else self.piece_square
            if waypoint.name == "target_touch_release":
                self.piece_square = self.config.target_square
                self.holding_piece = False
                self._sync_mujoco_piece_to_square(self.piece_square, reason="target_release")
            self.phase_index += 1
            phase_bonus += 1.0
        return phase_bonus

    def _reward(self, *, success: bool, phase_bonus: float) -> float:
        if self.phase_index >= len(self.waypoints):
            distance_penalty = 0.0
        else:
            joints = self._joint_positions()
            target = self.waypoints[self.phase_index].targets_deg
            distance_penalty = self._joint_error_deg(joints, target) / max(1.0, math.sqrt(len(SO101_JOINTS)))
        return float(phase_bonus - 0.01 * distance_penalty + (10.0 if success else 0.0))

    @staticmethod
    def _joint_error_deg(current: dict[str, float], target: dict[str, float]) -> float:
        error = 0.0
        for joint in SO101_JOINTS:
            error += (float(target[joint]) - float(current[joint])) ** 2
        return math.sqrt(error)

    def _piece_world_center_m(self, square: str) -> tuple[float, float, float]:
        board_xyz = square_center_m(square, self.config.board_params)
        return (
            float(self.config.board_origin_m[0] + board_xyz[0]),
            float(self.config.board_origin_m[1] + board_xyz[1]),
            float(self.config.board_origin_m[2] + board_xyz[2] + self.config.piece_height_m / 2.0),
        )

    def _sync_mujoco_piece_to_square(self, square: str, *, reason: str) -> dict[str, Any]:
        if self.robot is None:
            return {"ok": False, "reason": "robot_not_connected", "sync_reason": reason}
        set_pose = getattr(self.robot, "set_mujoco_freejoint_pose", None)
        if not callable(set_pose):
            return {"ok": False, "reason": "robot_does_not_expose_freejoint_pose_api", "sync_reason": reason}
        return set_pose("piece_source_freejoint", self._piece_world_center_m(square), reason=reason)

    def _mujoco_piece_status(self) -> dict[str, Any] | None:
        if self.robot is None:
            return None
        get_pose = getattr(self.robot, "mujoco_freejoint_pose", None)
        if not callable(get_pose):
            return None
        status = get_pose("piece_source_freejoint")
        return status if isinstance(status, dict) else None


__all__ = [
    "SO101_CHESS_ENV_SCHEMA",
    "SO101_CHESS_SCENE_SCHEMA",
    "SO101ChessEnv",
    "SO101ChessEnvConfig",
    "ScriptedJointWaypoint",
    "action_toward_targets",
    "dependency_status",
    "gymnasium_available",
    "scripted_pick_place_waypoints",
    "square_center_m",
    "square_index",
    "square_joint_pose",
    "square_to_indices",
]
