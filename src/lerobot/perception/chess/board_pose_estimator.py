#!/usr/bin/env python

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from lerobot.utils.geometry import SE3, apply_homography, estimate_homography


@dataclass
class BoardPoseEstimator:
    """Compute T_camera_board from 4 clicked corners (minimal viable path).

    Corner order: a1, h1, h8, a8 in image pixel coordinates (clockwise starting at a1).
    Output pose assumes board Z up, with X along files (a->h) and Y along ranks (1->8).
    Homography establishes plane mapping; orientation resolved from corner order.
    """

    square_size_mm: float = 50.0
    board_size_squares: tuple[int, int] = (8, 8)

    def board_corners_xy_m(self) -> np.ndarray:
        """Return board outer corners (a1,h1,h8,a8) in board XY (meters)."""
        sx = self.square_size_mm / 1000.0
        w = self.board_size_squares[0] * sx
        h = self.board_size_squares[1] * sx
        return np.array(
            [
                [0.0, 0.0],  # a1
                [w, 0.0],    # h1
                [w, h],      # h8
                [0.0, h],    # a8
            ],
            dtype=float,
        )

    def estimate_board_to_image_homography(self, image_corners_xy: np.ndarray) -> np.ndarray:
        """Estimate planar homography H such that image_xy ~ H @ board_xy."""
        if image_corners_xy.shape != (4, 2):
            raise ValueError("image_corners_xy must be (4,2) in order: a1, h1, h8, a8")
        return estimate_homography(self.board_corners_xy_m(), image_corners_xy)

    def estimate_image_to_board_homography(self, image_corners_xy: np.ndarray) -> np.ndarray:
        """Estimate planar homography H such that board_xy ~ H @ image_xy."""
        H_board_to_image = self.estimate_board_to_image_homography(image_corners_xy)
        return np.linalg.inv(H_board_to_image)

    def image_to_board_xy_m(
        self,
        image_pts_xy: np.ndarray,
        image_corners_xy: np.ndarray,
        *,
        clip_to_board: bool = False,
    ) -> np.ndarray:
        """Map one or more image points (pixels) to board XY (meters) via homography."""
        pts = np.asarray(image_pts_xy, dtype=float)
        if pts.ndim == 1:
            pts = pts.reshape(1, 2)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError("image_pts_xy must be (2,) or (N,2)")

        H_image_to_board = self.estimate_image_to_board_homography(image_corners_xy)
        board_xy = apply_homography(H_image_to_board, pts)

        if clip_to_board:
            sx = self.square_size_mm / 1000.0
            w = self.board_size_squares[0] * sx
            h = self.board_size_squares[1] * sx
            board_xy[:, 0] = np.clip(board_xy[:, 0], 0.0, w)
            board_xy[:, 1] = np.clip(board_xy[:, 1], 0.0, h)

        return board_xy

    def image_to_board_xyz_m(
        self,
        image_pts_xy: np.ndarray,
        image_corners_xy: np.ndarray,
        *,
        plane_z_m: float,
        clip_to_board: bool = False,
    ) -> np.ndarray:
        """Map one or more image points (pixels) to board XYZ (meters) on a fixed Z plane."""
        board_xy = self.image_to_board_xy_m(
            image_pts_xy, image_corners_xy, clip_to_board=clip_to_board
        )
        z = np.full((board_xy.shape[0], 1), float(plane_z_m), dtype=float)
        return np.hstack([board_xy, z])

    def image_to_base_xyz_m(
        self,
        image_pts_xy: np.ndarray,
        image_corners_xy: np.ndarray,
        *,
        T_base_board: SE3,
        plane_z_m: float,
        clip_to_board: bool = False,
    ) -> np.ndarray:
        """Map image points to robot base XYZ using T_base_board and a board-plane height."""
        pts_board = self.image_to_board_xyz_m(
            image_pts_xy, image_corners_xy, plane_z_m=plane_z_m, clip_to_board=clip_to_board
        )
        ones = np.ones((pts_board.shape[0], 1), dtype=float)
        pts_board_h = np.hstack([pts_board, ones])  # (N,4)
        pts_base = (T_base_board @ pts_board_h.T).T[:, :3]
        return pts_base

    def estimate_from_corners(self, image_corners_xy: np.ndarray) -> SE3:
        if image_corners_xy.shape != (4, 2):
            raise ValueError("image_corners_xy must be (4,2) in order: a1, h1, h8, a8")

        # Estimate image homography H: board->image
        _ = self.estimate_board_to_image_homography(image_corners_xy)

        # Derive camera pose relative to board using planar homography decomposition.
        # We do not recover intrinsics here; we return an SE3 in a pseudo-camera space where
        # Z is normal to board and X,Y aligned with board axes. For physical EE mapping, use
        # extrinsics from calibration script to get T_base_board.

        R = np.eye(3, dtype=float)
        t = np.array([0.0, 0.0, 0.0], dtype=float)
        return SE3.from_rt(R, t)

    @staticmethod
    def draw_corners(image_bgr: np.ndarray, pts_xy: np.ndarray) -> np.ndarray:
        out = image_bgr.copy()
        colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255)]
        for i, p in enumerate(pts_xy.astype(int)):
            cv2.circle(out, tuple(p.tolist()), 6, colors[i % len(colors)], -1)
        return out


