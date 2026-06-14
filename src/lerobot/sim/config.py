#!/usr/bin/env python

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lerobot.cameras import CameraConfig, ColorMode
from lerobot.robots.config import RobotConfig

BoardCorners = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]


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
