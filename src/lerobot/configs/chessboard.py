#!/usr/bin/env python

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


Square = Literal[
    "a1","a2","a3","a4","a5","a6","a7","a8",
    "b1","b2","b3","b4","b5","b6","b7","b8",
    "c1","c2","c3","c4","c5","c6","c7","c8",
    "d1","d2","d3","d4","d5","d6","d7","d8",
    "e1","e2","e3","e4","e5","e6","e7","e8",
    "f1","f2","f3","f4","f5","f6","f7","f8",
    "g1","g2","g3","g4","g5","g6","g7","g8",
    "h1","h2","h3","h4","h5","h6","h7","h8",
]


@dataclass
class ChessBoardParams:
    """Geometric and semantic parameters of the chessboard."""

    square_size_mm: float = 50.0
    board_size: tuple[int, int] = (8, 8)
    board_height_mm: float = 15.0
    origin_square: Square = "a1"  # world origin aligned to lower-left square in image convention
    # Optional separate X/Y sizes (if board isn't perfectly square)
    square_size_x_mm: float | None = None
    square_size_y_mm: float | None = None
    
    @property
    def effective_square_size_x_mm(self) -> float:
        return self.square_size_x_mm if self.square_size_x_mm is not None else self.square_size_mm
    
    @property
    def effective_square_size_y_mm(self) -> float:
        return self.square_size_y_mm if self.square_size_y_mm is not None else self.square_size_mm


@dataclass
class ChessCalibrationPaths:
    """Filesystem paths for calibration and persistence."""

    root_dir: Path
    camera_to_base_json: Path = field(init=False)
    camera_intrinsics_npz: Path = field(init=False)
    camera_distortion_npz: Path = field(init=False)
    board_pose_json: Path = field(init=False)

    def __post_init__(self):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.camera_to_base_json = self.root_dir / "T_base_camera.json"
        self.camera_intrinsics_npz = self.root_dir / "camera_intrinsics.npz"
        self.camera_distortion_npz = self.root_dir / "camera_distortion.npz"
        self.board_pose_json = self.root_dir / "T_camera_board.json"


@dataclass
class ChessboardConfig:
    """Top-level config to wire chess perception and planning."""

    camera_name: str = "front"
    use_aruco: bool = True
    charuco_dictionary: str | None = None
    params: ChessBoardParams = field(default_factory=ChessBoardParams)
    paths: ChessCalibrationPaths | None = None


