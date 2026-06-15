#!/usr/bin/env python

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lerobot.cameras import CameraConfig, ColorMode
from lerobot.robots.config import RobotConfig

BoardCorners = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]

SIM_CAMERA_REFERENCE_WIDTH = 640.0
SIM_CAMERA_REFERENCE_HEIGHT = 480.0
REFERENCE_GRIPPER_BOARD_CORNERS: BoardCorners = ((32.0, 338.0), (594.0, 340.0), (540.0, 20.0), (86.0, 12.0))
OVERVIEW_BOARD_CORNERS: BoardCorners = ((94.0, 420.0), (546.0, 420.0), (546.0, 48.0), (94.0, 48.0))
CURRENT_GRIPPER_REFERENCE_PROFILE = "current_gripper_reference"
CURRENT_GRIPPER_REFERENCE_IMAGE = Path("archive/chess_test_images/current_view.jpg")
SIM_CAMERA_PROFILE_OVERRIDES_SCHEMA = "lerobot.sim.manual_corner_profile_candidate.v1"
SIM_CAMERA_PROFILE_OVERRIDES_STATUS = "candidate_only_not_canonical"
SIM_CAMERA_PROFILE_OVERRIDE_KEYS = frozenset(
    {"width", "height", "board_corners_xy", "reference_image_path"}
)

SIM_CAMERA_CALIBRATION_PROFILES: dict[str, dict[str, Any]] = {
    CURRENT_GRIPPER_REFERENCE_PROFILE: {
        "width": int(SIM_CAMERA_REFERENCE_WIDTH),
        "height": int(SIM_CAMERA_REFERENCE_HEIGHT),
        "fps": 30,
        "color_mode": ColorMode.BGR,
        "view": "gripper",
        "board_corners_xy": REFERENCE_GRIPPER_BOARD_CORNERS,
        "draw_pieces": True,
        "piece_layout": "single_pawn",
        "piece_square": "e4",
        "gripper_visible": True,
        "gripper_center_x_px": 320,
        "gripper_y_px": 374,
        "gripper_opening_px": 56,
        "gripper_finger_width_px": 72,
        "gripper_length_px": 170,
        "track_robot_gripper": True,
        "reference_image_path": CURRENT_GRIPPER_REFERENCE_IMAGE,
    }
}


@CameraConfig.register_subclass("sim_camera")
@dataclass(kw_only=True)
class SimCameraConfig(CameraConfig):
    """Configuration for a calibration-oriented synthetic chessboard camera.

    board_corners_xy order is a1, h1, h8, a8 in image pixels. This matches the
    chess board pose estimator's expected corner order.
    """

    fps: int | None = 30
    width: int | None = 640
    height: int | None = 480
    color_mode: ColorMode = ColorMode.BGR
    view: str = "gripper"
    board_corners_xy: BoardCorners | None = None
    draw_pieces: bool = True
    piece_layout: str = "single_pawn"
    piece_square: str = "e4"
    gripper_visible: bool = True
    gripper_center_x_px: int | None = None
    gripper_y_px: int | None = None
    gripper_opening_px: int = 56
    gripper_finger_width_px: int = 72
    gripper_length_px: int = 170
    track_robot_gripper: bool = True
    reference_image_path: str | Path | None = None

    def __post_init__(self) -> None:
        if self.width is None or self.height is None:
            raise ValueError("SimCameraConfig requires width and height.")
        if self.fps is None:
            self.fps = 30
        if self.color_mode not in (ColorMode.RGB, ColorMode.BGR):
            raise ValueError(f"Unsupported color_mode for SimCameraConfig: {self.color_mode}")
        if self.view not in {"gripper", "overview", "birdseye"}:
            raise ValueError("SimCameraConfig.view must be one of: gripper, overview, birdseye.")
        if self.piece_layout not in {"single_pawn", "starting", "empty"}:
            raise ValueError("SimCameraConfig.piece_layout must be one of: single_pawn, starting, empty.")
        if self.board_corners_xy is not None and len(self.board_corners_xy) != 4:
            raise ValueError("board_corners_xy must contain four (x, y) image corners.")


def make_sim_camera_config_from_profile(profile_name: str, **overrides: Any) -> SimCameraConfig:
    try:
        profile_values = SIM_CAMERA_CALIBRATION_PROFILES[profile_name]
    except KeyError as exc:
        known_profiles = ", ".join(sorted(SIM_CAMERA_CALIBRATION_PROFILES))
        raise ValueError(f"Unknown SimCamera calibration profile {profile_name!r}. Known profiles: {known_profiles}") from exc

    return SimCameraConfig(**{**profile_values, **overrides})


def load_sim_camera_profile_overrides(path: str | Path) -> dict[str, Any]:
    """Load simulator-only camera profile overrides from a manual-corner candidate JSON."""

    json_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(json_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in simulator camera profile override file {json_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read simulator camera profile override file {json_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"Simulator camera profile override file {json_path} must contain a JSON object, "
            f"got {type(payload).__name__}."
        )

    if "sim_camera_profile_overrides" in payload:
        schema = payload.get("schema")
        if schema is not None and schema != SIM_CAMERA_PROFILE_OVERRIDES_SCHEMA:
            raise ValueError(
                f"Unsupported simulator camera profile override schema in {json_path}: {schema!r}. "
                f"Expected {SIM_CAMERA_PROFILE_OVERRIDES_SCHEMA!r}."
            )
        status = payload.get("status")
        if status is not None and status != SIM_CAMERA_PROFILE_OVERRIDES_STATUS:
            raise ValueError(
                f"Unsupported simulator camera profile override status in {json_path}: {status!r}. "
                f"Expected {SIM_CAMERA_PROFILE_OVERRIDES_STATUS!r}."
            )
        overrides = payload["sim_camera_profile_overrides"]
    else:
        overrides = payload

    if not isinstance(overrides, dict):
        raise ValueError(
            f"sim_camera_profile_overrides in {json_path} must be an object, got {type(overrides).__name__}."
        )
    unknown_keys = sorted(set(overrides) - SIM_CAMERA_PROFILE_OVERRIDE_KEYS)
    if unknown_keys:
        allowed = ", ".join(sorted(SIM_CAMERA_PROFILE_OVERRIDE_KEYS))
        raise ValueError(
            f"Unsupported sim_camera_profile_overrides keys in {json_path}: {unknown_keys}. "
            f"Allowed keys: {allowed}."
        )
    if not overrides:
        raise ValueError(f"sim_camera_profile_overrides in {json_path} must contain at least one override.")

    normalized: dict[str, Any] = {}
    if "width" in overrides:
        normalized["width"] = _positive_int_override(overrides["width"], key="width", source=json_path)
    if "height" in overrides:
        normalized["height"] = _positive_int_override(overrides["height"], key="height", source=json_path)
    if "board_corners_xy" in overrides:
        normalized["board_corners_xy"] = _board_corners_override(
            overrides["board_corners_xy"], source=json_path
        )
    if "reference_image_path" in overrides:
        normalized["reference_image_path"] = _reference_image_path_override(
            overrides["reference_image_path"], source=json_path
        )
    return normalized


def _positive_int_override(value: Any, *, key: str, source: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} in {source} must be a positive integer, got {value!r}.")
    if value <= 0:
        raise ValueError(f"{key} in {source} must be positive, got {value!r}.")
    return int(value)


def _board_corners_override(value: Any, *, source: Path) -> BoardCorners:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"board_corners_xy in {source} must contain four [x, y] corners.")

    corners: list[tuple[float, float]] = []
    for index, corner in enumerate(value):
        if not isinstance(corner, (list, tuple)) or len(corner) != 2:
            raise ValueError(f"board_corners_xy[{index}] in {source} must be an [x, y] pair.")
        x, y = corner
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(
            y, (int, float)
        ):
            raise ValueError(f"board_corners_xy[{index}] in {source} must contain numeric x/y values.")
        x_float = float(x)
        y_float = float(y)
        if not math.isfinite(x_float) or not math.isfinite(y_float):
            raise ValueError(f"board_corners_xy[{index}] in {source} must contain finite x/y values.")
        corners.append((x_float, y_float))
    return tuple(corners)  # type: ignore[return-value]


def _reference_image_path_override(value: Any, *, source: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"reference_image_path in {source} must be a non-empty string.")
    return str(Path(value).expanduser())


@RobotConfig.register_subclass("sim_so101")
@dataclass(kw_only=True)
class SimRobotConfig(RobotConfig):
    """Configuration for a virtual SO-101 follower arm.

    MuJoCo is optional. When a model path cannot be loaded, the robot falls back to
    an in-memory joint-state backend with an explicit status message.
    """

    id: str | None = "so101_sim"
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = True
    max_relative_target: float | dict[str, float] | None = None
    initial_positions: dict[str, float] = field(default_factory=dict)
    use_mujoco: bool = True
    mujoco_model_path: str | Path | None = None

    def __post_init__(self) -> None:
        if self.calibration_dir is None:
            self.calibration_dir = Path(tempfile.gettempdir()) / "lerobot_sim" / "calibration"
        super().__post_init__()
