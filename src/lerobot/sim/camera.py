#!/usr/bin/env python

from __future__ import annotations

import time
from typing import Any

import numpy as np

from lerobot.cameras.camera import Camera
from lerobot.cameras.configs import ColorMode
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config import (
    OVERVIEW_BOARD_CORNERS,
    REFERENCE_GRIPPER_BOARD_CORNERS,
    SIM_CAMERA_CALIBRATION_METADATA_SCOPE,
    SIM_CAMERA_DISTORTION_COEFFICIENT_ORDER,
    SIM_CAMERA_DISTORTION_MODEL,
    SIM_CAMERA_INTRINSICS_MODEL,
    SIM_CAMERA_INTRINSICS_SCHEMA,
    SIM_CAMERA_REFERENCE_BOARD_SIZE_M,
    SIM_CAMERA_REFERENCE_HEIGHT,
    SIM_CAMERA_REFERENCE_WIDTH,
    SimCameraConfig,
    sim_camera_coordinate_frame_convention,
)


class SimCamera(Camera):
    """Synthetic OpenCV-compatible camera for SO-101 chess calibration."""

    def __init__(self, config: SimCameraConfig):
        super().__init__(config)
        self.config = config
        self.color_mode = config.color_mode
        self._connected = False
        self._last_frame: np.ndarray | None = None
        self._frame_index = 0
        self._robot_joints: dict[str, float] = {}

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.width}x{self.height})"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def find_cameras() -> list[dict[str, Any]]:
        return [
            {
                "name": "Synthetic SO-101 chessboard camera",
                "type": "sim_camera",
                "id": "sim://so101/chessboard",
                "view": "gripper",
                "default_stream_profile": {"format": "bgr8", "width": 640, "height": 480, "fps": 30},
            }
        ]

    def connect(self, warmup: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} is already connected.")
        self._connected = True
        if warmup:
            self._last_frame = self.read()

    def read(self, color_mode: ColorMode | None = None) -> np.ndarray:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        frame_bgr = self._render_bgr_frame()
        self._last_frame = frame_bgr
        self._frame_index += 1

        requested_color_mode = self.color_mode if color_mode is None else color_mode
        if requested_color_mode == ColorMode.RGB:
            return frame_bgr[..., ::-1].copy()
        if requested_color_mode == ColorMode.BGR:
            return frame_bgr
        raise ValueError(f"Invalid color mode '{requested_color_mode}'. Expected RGB or BGR.")

    def async_read(self, timeout_ms: float = 200) -> np.ndarray:
        _ = timeout_ms
        return self.read()

    def disconnect(self) -> None:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        self._connected = False
        self._last_frame = None

    def set_robot_state(self, joints: dict[str, float]) -> None:
        self._robot_joints = {str(name): float(value) for name, value in joints.items()}

    def calibration_metadata(self) -> dict[str, Any]:
        width = int(self.width or 640)
        height = int(self.height or 480)
        camera_matrix = self._camera_matrix_px()
        distortion_coefficients = [
            float(value) for value in (self.config.distortion_coefficients or ())
        ]
        gripper_percent = self._robot_joints.get("gripper")
        return {
            "calibration_metadata_scope": SIM_CAMERA_CALIBRATION_METADATA_SCOPE,
            "image_size_px": {"width": width, "height": height},
            "camera_matrix_px": camera_matrix,
            "intrinsics": {
                "schema": SIM_CAMERA_INTRINSICS_SCHEMA,
                "model": SIM_CAMERA_INTRINSICS_MODEL,
                "fx_px": camera_matrix[0][0],
                "fy_px": camera_matrix[1][1],
                "cx_px": camera_matrix[0][2],
                "cy_px": camera_matrix[1][2],
                "skew_px": camera_matrix[0][1],
                "camera_matrix_px": camera_matrix,
            },
            "distortion_model": SIM_CAMERA_DISTORTION_MODEL,
            "distortion_coefficients": distortion_coefficients,
            "distortion_coefficient_order": list(SIM_CAMERA_DISTORTION_COEFFICIENT_ORDER),
            "extrinsics": {
                "board_to_camera": self._board_to_camera_extrinsics(),
            },
            "coordinate_frame_convention": sim_camera_coordinate_frame_convention(),
            "view": self.config.view,
            "board_corners_xy": self._board_corners(width, height).tolist(),
            "board_corners_xy_source": self._board_corners_source(width, height),
            "board_geometry_projection_model": self._board_geometry_projection_model(width, height),
            "piece_layout": self.config.piece_layout,
            "piece_square": self.config.piece_square,
            "gripper_visible": self.config.gripper_visible,
            "track_robot_gripper": self.config.track_robot_gripper,
            "tracked_gripper_percent": gripper_percent,
            "current_gripper_opening_px": self._current_gripper_opening_px(),
            "robot_joints": dict(self._robot_joints),
            "reference_image_path": (
                str(self.config.reference_image_path) if self.config.reference_image_path else None
            ),
        }

    def _camera_matrix_px(self) -> list[list[float]]:
        matrix = self.config.camera_matrix_px
        return [[float(value) for value in row] for row in (matrix or ())]

    def _board_to_camera_extrinsics(self) -> dict[str, Any]:
        extrinsics = self.config.board_to_camera_extrinsics or {}
        return {
            str(key): self._jsonable_metadata_value(value)
            for key, value in extrinsics.items()
        }

    def _jsonable_metadata_value(self, value: Any) -> Any:
        if isinstance(value, tuple):
            return [self._jsonable_metadata_value(item) for item in value]
        if isinstance(value, list):
            return [self._jsonable_metadata_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._jsonable_metadata_value(item)
                for key, item in value.items()
            }
        return value

    def _render_bgr_frame(self) -> np.ndarray:
        height = int(self.height or 480)
        width = int(self.width or 640)
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = self._background(height, width)

        corners = self._board_corners(width, height)
        self._draw_board(frame, corners)
        if self.config.draw_pieces:
            self._draw_pieces(frame, corners)

        if self.config.gripper_visible and self.config.view == "gripper":
            self._draw_gripper(frame)

        self._draw_camera_markers(frame, corners)
        return np.ascontiguousarray(frame)

    def _background(self, height: int, width: int) -> np.ndarray:
        y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
        if self.config.view == "gripper":
            top = np.array([18, 22, 18], dtype=np.float32)
            bottom = np.array([58, 46, 35], dtype=np.float32)
        else:
            top = np.array([36, 42, 44], dtype=np.float32)
            bottom = np.array([70, 62, 50], dtype=np.float32)
        row = top * (1.0 - y) + bottom * y
        return np.repeat(row[:, None, :], width, axis=1).astype(np.uint8)

    def _board_corners(self, width: int, height: int) -> np.ndarray:
        projected = self._metadata_projected_board_corners(width, height)
        if projected is not None:
            return projected
        if self.config.board_corners_xy is not None:
            corners = np.array(self.config.board_corners_xy, dtype=float)
        elif self.config.view == "overview":
            corners = np.array(OVERVIEW_BOARD_CORNERS, dtype=float)
        elif self.config.view == "birdseye":
            margin = 44.0
            corners = np.array(
                [
                    [margin, height - margin],
                    [width - margin, height - margin],
                    [width - margin, margin],
                    [margin, margin],
                ],
                dtype=float,
            )
            return corners
        else:
            corners = np.array(REFERENCE_GRIPPER_BOARD_CORNERS, dtype=float)

        scale = np.array([width / SIM_CAMERA_REFERENCE_WIDTH, height / SIM_CAMERA_REFERENCE_HEIGHT], dtype=float)
        return corners * scale

    def _board_corners_source(self, width: int, height: int) -> str:
        if self._metadata_projected_board_corners(width, height) is not None:
            return "camera_metadata_pinhole_projection"
        if self.config.board_corners_xy is not None:
            return "configured_image_corners"
        if self.config.view == "overview":
            return "overview_profile_image_corners"
        if self.config.view == "birdseye":
            return "birdseye_synthetic_image_corners"
        return "reference_gripper_image_corners"

    def _board_geometry_projection_model(self, width: int, height: int) -> str:
        if self._metadata_projected_board_corners(width, height) is not None:
            return "camera_matrix_px + extrinsics.board_to_camera"
        return "image-space quadrilateral interpolation"

    def _metadata_projected_board_corners(self, width: int, height: int) -> np.ndarray | None:
        if not bool(self.config.metadata_projected_board_geometry) or self.config.view != "gripper":
            return None
        _ = (width, height)
        board_size_m = float(SIM_CAMERA_REFERENCE_BOARD_SIZE_M)
        board_points = np.array(
            [
                [0.0, 0.0, 0.0],
                [board_size_m, 0.0, 0.0],
                [board_size_m, board_size_m, 0.0],
                [0.0, board_size_m, 0.0],
            ],
            dtype=float,
        )
        projected = [self._project_board_point_m(point) for point in board_points]
        if any(point is None for point in projected):
            return None
        corners = np.asarray(projected, dtype=float)
        if corners.shape != (4, 2) or not np.isfinite(corners).all():
            return None
        return corners

    def _project_board_point_m(self, board_point_m: np.ndarray) -> np.ndarray | None:
        try:
            camera_matrix = np.asarray(self.config.camera_matrix_px, dtype=float)
            extrinsics = self.config.board_to_camera_extrinsics or {}
            rotation = np.asarray(extrinsics.get("rotation_matrix"), dtype=float)
            translation = np.asarray(extrinsics.get("translation_m"), dtype=float)
        except (TypeError, ValueError):
            return None
        if camera_matrix.shape != (3, 3) or rotation.shape != (3, 3) or translation.shape != (3,):
            return None
        if not (
            np.isfinite(camera_matrix).all()
            and np.isfinite(rotation).all()
            and np.isfinite(translation).all()
        ):
            return None

        camera_point = rotation @ np.asarray(board_point_m, dtype=float).reshape(3) + translation
        if not np.isfinite(camera_point).all() or float(camera_point[2]) <= 1e-9:
            return None
        homogeneous = camera_matrix @ camera_point
        image_xy = homogeneous[:2] / homogeneous[2]
        return image_xy if np.isfinite(image_xy).all() else None

    def _draw_board(self, frame: np.ndarray, corners: np.ndarray) -> None:
        light = np.array([208, 215, 210], dtype=np.uint8)
        dark = np.array([72, 52, 38], dtype=np.uint8)
        border = np.array([26, 24, 20], dtype=np.uint8)
        self._fill_convex_quad(frame, corners, border)

        inset = self._inset_corners(corners, pixels=3.0)
        for rank in range(8):
            for file in range(8):
                quad = np.array(
                    [
                        self._board_point(inset, file / 8.0, rank / 8.0),
                        self._board_point(inset, (file + 1) / 8.0, rank / 8.0),
                        self._board_point(inset, (file + 1) / 8.0, (rank + 1) / 8.0),
                        self._board_point(inset, file / 8.0, (rank + 1) / 8.0),
                    ],
                    dtype=float,
                )
                color = light if (rank + file) % 2 == 0 else dark
                self._fill_convex_quad(frame, quad, color)

    def _draw_pieces(self, frame: np.ndarray, corners: np.ndarray) -> None:
        if self.config.piece_layout == "empty":
            return
        if self.config.piece_layout == "single_pawn":
            file, rank = self._square_to_file_rank(self.config.piece_square)
            self._draw_piece_at_square(frame, corners, file, rank, is_light=True, radius_scale=0.30)
            return

        for file in range(8):
            self._draw_piece_at_square(frame, corners, file, 1, is_light=True, radius_scale=0.26)
            self._draw_piece_at_square(frame, corners, file, 6, is_light=False, radius_scale=0.26)

        back_rank_radius = {
            0: 0.32,
            1: 0.29,
            2: 0.30,
            3: 0.34,
            4: 0.36,
            5: 0.30,
            6: 0.29,
            7: 0.32,
        }
        for file, radius_scale in back_rank_radius.items():
            self._draw_piece_at_square(frame, corners, file, 0, is_light=True, radius_scale=radius_scale)
            self._draw_piece_at_square(frame, corners, file, 7, is_light=False, radius_scale=radius_scale)

    def _draw_piece_at_square(
        self,
        frame: np.ndarray,
        corners: np.ndarray,
        file: int,
        rank: int,
        *,
        is_light: bool,
        radius_scale: float,
    ) -> None:
        light_piece = np.array([232, 235, 230], dtype=np.uint8)
        dark_piece = np.array([38, 42, 47], dtype=np.uint8)
        light_outline = np.array([128, 138, 142], dtype=np.uint8)
        dark_outline = np.array([178, 186, 190], dtype=np.uint8)
        color = light_piece if is_light else dark_piece
        outline = light_outline if is_light else dark_outline
        center = self._board_point(corners, (file + 0.5) / 8.0, (rank + 0.5) / 8.0)
        next_file = self._board_point(corners, min(1.0, (file + 1.5) / 8.0), (rank + 0.5) / 8.0)
        next_rank = self._board_point(corners, (file + 0.5) / 8.0, min(1.0, (rank + 1.5) / 8.0))
        square_px = max(
            8.0,
            float(min(np.linalg.norm(next_file - center), np.linalg.norm(next_rank - center))),
        )
        cx, cy = int(round(center[0])), int(round(center[1]))
        radius = max(3, int(square_px * radius_scale))
        self._fill_disc(frame, cx, cy, radius + 2, outline)
        self._fill_disc(frame, cx, cy, radius, color)
        highlight = np.array([255, 255, 255], dtype=np.uint8)
        self._fill_disc(frame, cx - radius // 3, cy - radius // 3, max(1, radius // 5), highlight)

    def _fill_disc(self, frame: np.ndarray, cx: int, cy: int, radius: int, color: np.ndarray) -> None:
        height, width = frame.shape[:2]
        x_min = max(0, cx - radius)
        x_max = min(width, cx + radius + 1)
        y_min = max(0, cy - radius)
        y_max = min(height, cy + radius + 1)
        if x_min >= x_max or y_min >= y_max:
            return
        yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius**2
        frame[y_min:y_max, x_min:x_max][mask] = color

    def _draw_gripper(self, frame: np.ndarray) -> None:
        height, width = frame.shape[:2]
        center_x = int(self.config.gripper_center_x_px or (width // 2))
        y_base = int(self.config.gripper_y_px or int(height * 0.78))
        opening = self._current_gripper_opening_px()
        finger_w = max(12, int(self.config.gripper_finger_width_px))
        length = max(40, int(self.config.gripper_length_px))
        left = np.array(
            [
                [center_x - opening // 2 - finger_w, height],
                [center_x - opening // 2 - max(8, finger_w // 5), y_base],
                [center_x - opening // 2 + max(4, finger_w // 8), y_base - length // 5],
                [center_x - opening // 2 - finger_w // 2, height],
            ],
            dtype=float,
        )
        right = left.copy()
        right[:, 0] = 2 * center_x - left[:, 0]
        shadow = np.array([120, 120, 120], dtype=np.uint8)
        plastic = np.array([235, 238, 236], dtype=np.uint8)
        holes = np.array([198, 205, 205], dtype=np.uint8)
        self._fill_convex_quad(frame, left + np.array([4.0, 4.0]), shadow)
        self._fill_convex_quad(frame, right + np.array([-4.0, 4.0]), shadow)
        self._fill_convex_quad(frame, left, plastic)
        self._fill_convex_quad(frame, right, plastic)
        for side in (-1, 1):
            hx = center_x + side * (opening // 2 + finger_w // 2)
            for offset in (44, 88, 132):
                self._fill_disc(frame, hx, height - offset, max(3, finger_w // 12), holes)

    def _current_gripper_opening_px(self) -> int:
        opening = max(10, int(self.config.gripper_opening_px))
        if not self.config.track_robot_gripper or "gripper" not in self._robot_joints:
            return opening
        gripper_pct = float(np.clip(self._robot_joints["gripper"], 0.0, 100.0))
        return max(8, int(opening * (0.20 + 0.80 * (gripper_pct / 100.0))))

    def _draw_camera_markers(self, frame: np.ndarray, corners: np.ndarray) -> None:
        tick = (self._frame_index // max(1, int((self.fps or 30) / 2))) % 2
        color = np.array([30, 210 if tick else 150, 255], dtype=np.uint8)
        x_min = max(0, int(np.min(corners[:, 0])))
        x_max = min(frame.shape[1], int(np.max(corners[:, 0])))
        y_min = max(0, int(np.min(corners[:, 1])))
        y_max = min(frame.shape[0], int(np.max(corners[:, 1])))
        frame[max(0, y_min - 12) : max(0, y_min - 8), x_min:x_max] = color
        now_band = int(time.time()) % 16
        width = max(1, x_max - x_min)
        x = x_min + min(width - 1, now_band * max(1, width // 16))
        frame[y_min:y_max, max(0, x - 1) : min(frame.shape[1], x + 1)] = np.array(
            [80, 170, 240], dtype=np.uint8
        )

    def _fill_convex_quad(self, frame: np.ndarray, pts: np.ndarray, color: np.ndarray) -> None:
        height, width = frame.shape[:2]
        x_min = max(0, int(np.floor(np.min(pts[:, 0]))))
        x_max = min(width, int(np.ceil(np.max(pts[:, 0]))) + 1)
        y_min = max(0, int(np.floor(np.min(pts[:, 1]))))
        y_max = min(height, int(np.ceil(np.max(pts[:, 1]))) + 1)
        if x_min >= x_max or y_min >= y_max:
            return

        yy, xx = np.mgrid[y_min:y_max, x_min:x_max]
        signs = []
        for i in range(4):
            p0 = pts[i]
            p1 = pts[(i + 1) % 4]
            signs.append((xx - p0[0]) * (p1[1] - p0[1]) - (yy - p0[1]) * (p1[0] - p0[0]))
        stacked = np.stack(signs, axis=0)
        mask = np.all(stacked >= -1e-6, axis=0) | np.all(stacked <= 1e-6, axis=0)
        frame[y_min:y_max, x_min:x_max][mask] = color

    def _board_point(self, corners: np.ndarray, u: float, v: float) -> np.ndarray:
        a1, h1, h8, a8 = corners
        bottom = a1 * (1.0 - u) + h1 * u
        top = a8 * (1.0 - u) + h8 * u
        return bottom * (1.0 - v) + top * v

    def _inset_corners(self, corners: np.ndarray, pixels: float) -> np.ndarray:
        center = np.mean(corners, axis=0)
        out = corners.copy()
        for i, pt in enumerate(corners):
            direction = center - pt
            norm = float(np.linalg.norm(direction))
            if norm > 1e-6:
                out[i] = pt + direction / norm * pixels
        return out

    def _square_to_file_rank(self, square: str) -> tuple[int, int]:
        sq = square.strip().lower()
        if len(sq) != 2 or sq[0] < "a" or sq[0] > "h" or sq[1] < "1" or sq[1] > "8":
            raise ValueError(f"Invalid chess square for SimCameraConfig.piece_square: {square!r}")
        return ord(sq[0]) - ord("a"), int(sq[1]) - 1
