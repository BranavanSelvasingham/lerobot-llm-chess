#!/usr/bin/env python

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Tuple

import draccus
import numpy as np

from lerobot.configs.chessboard import ChessBoardParams
from lerobot.utils.geometry import SE3


@dataclass
class BoardModel:
    """Holds board geometry and persistent transforms.

    - params: physical dimensions and conventions
    - T_base_board: transform from board frame to robot base
    """

    params: ChessBoardParams
    T_base_board: SE3 | None = None

    def save(self, fpath: Path) -> None:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "params": asdict(self.params),
            "T_base_board": self.T_base_board.T.tolist() if self.T_base_board is not None else None,
        }
        with open(fpath, "w") as f, draccus.config_type("json"):
            draccus.dump(payload, f, indent=2)

    @staticmethod
    def load(fpath: Path) -> "BoardModel":
        with open(fpath) as f, draccus.config_type("json"):
            obj = draccus.load(dict, f)
        params = ChessBoardParams(**obj["params"]) if obj.get("params") else ChessBoardParams()
        T = np.array(obj["T_base_board"], dtype=float) if obj.get("T_base_board") is not None else None
        T_bb = SE3(T) if T is not None else None
        return BoardModel(params=params, T_base_board=T_bb)

    def square_center_in_board(self, file_idx: int, rank_idx: int) -> np.ndarray:
        """Return center of square (file, rank) in board frame (meters).

        file_idx: 0..7 for a..h; rank_idx: 0..7 for 1..8
        Board frame convention: origin at a1 corner, +x to files (a->h), +y to ranks (1->8), z up.
        """
        sx = self.params.effective_square_size_x_mm / 1000.0
        sy = self.params.effective_square_size_y_mm / 1000.0
        x = (file_idx + 0.5) * sx
        y = (rank_idx + 0.5) * sy
        z = self.params.board_height_mm / 1000.0
        return np.array([x, y, z], dtype=float)


