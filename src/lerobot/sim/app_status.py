#!/usr/bin/env python

from __future__ import annotations

import math
from typing import Any


SIM_CAMERA_STATUS_SCHEMA = "lerobot.sim.app_camera_status.v1"

REQUIRED_SIM_CAMERA_METADATA_PATHS = (
    "image_size_px",
    "camera_matrix_px",
    "intrinsics",
    "distortion_coefficients",
    "extrinsics.board_to_camera",
    "coordinate_frame_convention",
    "board_corners_xy",
    "piece_layout",
    "piece_square",
    "gripper_visible",
    "track_robot_gripper",
    "current_gripper_opening_px",
)


def _dict_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _round_float(value: Any, digits: int = 3) -> float | None:
    if not _finite_number(value):
        return None
    return round(float(value), digits)


def _valid_square(value: Any) -> str | None:
    square = str(value or "").strip().lower()
    if len(square) == 2 and "a" <= square[0] <= "h" and "1" <= square[1] <= "8":
        return square
    return None


def _board_point(corners: list[list[float]], u: float, v: float) -> tuple[float, float]:
    a1, h1, h8, a8 = corners
    bottom_x = a1[0] * (1.0 - u) + h1[0] * u
    bottom_y = a1[1] * (1.0 - u) + h1[1] * u
    top_x = a8[0] * (1.0 - u) + h8[0] * u
    top_y = a8[1] * (1.0 - u) + h8[1] * u
    return bottom_x * (1.0 - v) + top_x * v, bottom_y * (1.0 - v) + top_y * v


def _target_center(metadata: dict[str, Any], square: str | None) -> list[float] | None:
    corners = metadata.get("board_corners_xy")
    if square is None or not isinstance(corners, list) or len(corners) != 4:
        return None

    normalized_corners: list[list[float]] = []
    for corner in corners:
        if not isinstance(corner, list) or len(corner) != 2:
            return None
        x, y = corner
        if not _finite_number(x) or not _finite_number(y):
            return None
        normalized_corners.append([float(x), float(y)])

    file_idx = ord(square[0]) - ord("a")
    rank_idx = int(square[1]) - 1
    x, y = _board_point(
        normalized_corners,
        (file_idx + 0.5) / 8.0,
        (rank_idx + 0.5) / 8.0,
    )
    return [round(float(x), 3), round(float(y), 3)]


def _metadata_contract_status(
    metadata: dict[str, Any],
    metadata_contract: dict[str, Any] | None,
) -> tuple[str, dict[str, bool]]:
    present = {
        path: _dict_path(metadata, path) is not None
        for path in REQUIRED_SIM_CAMERA_METADATA_PATHS
    }
    if isinstance(metadata_contract, dict):
        return ("pass" if bool(metadata_contract.get("ok")) else "fail"), present
    return ("fields_ok" if all(present.values()) else "fields_missing"), present


def summarize_sim_camera_status(
    metadata: dict[str, Any],
    *,
    metadata_contract: dict[str, Any] | None = None,
    selected_calibration: dict[str, Any] | None = None,
    sim_camera_profile: str | None = None,
) -> dict[str, Any]:
    """Build an app-facing SimCamera status payload for UI and headless smoke use."""

    image_size = metadata.get("image_size_px") if isinstance(metadata.get("image_size_px"), dict) else {}
    width = image_size.get("width") if isinstance(image_size, dict) else None
    height = image_size.get("height") if isinstance(image_size, dict) else None
    corners = metadata.get("board_corners_xy")
    board_corner_count = len(corners) if isinstance(corners, list) else 0
    square = _valid_square(metadata.get("piece_square"))
    contract_status, present = _metadata_contract_status(metadata, metadata_contract)
    selection = selected_calibration if isinstance(selected_calibration, dict) else {}
    rank = selection.get("rank")
    candidate_id = selection.get("candidate_id")

    status: dict[str, Any] = {
        "schema": SIM_CAMERA_STATUS_SCHEMA,
        "ok": bool(
            contract_status in {"pass", "fields_ok"}
            and board_corner_count == 4
            and _finite_number(width)
            and _finite_number(height)
            and square is not None
        ),
        "readout": "",
        "profile": sim_camera_profile,
        "view": metadata.get("view"),
        "image_size_px": {
            "width": int(width) if _finite_number(width) else None,
            "height": int(height) if _finite_number(height) else None,
        },
        "board_corner_count": board_corner_count,
        "target": {
            "square": square,
            "center_image_xy": _target_center(metadata, square),
            "piece_layout": metadata.get("piece_layout"),
        },
        "gripper": {
            "visible": metadata.get("gripper_visible"),
            "track_robot_gripper": metadata.get("track_robot_gripper"),
            "tracked_percent": _round_float(metadata.get("tracked_gripper_percent")),
            "current_opening_px": _round_float(metadata.get("current_gripper_opening_px")),
        },
        "metadata_contract": {
            "status": contract_status,
            "ok": True if contract_status == "pass" else False if contract_status == "fail" else None,
            "required_paths_present": present,
        },
        "selected_calibration": {
            "candidate_id": str(candidate_id) if candidate_id else None,
            "rank": int(rank) if isinstance(rank, int) else None,
        },
        "limitations": [
            "Synthetic SimCamera metadata/status evidence only; not physical SO-101 calibration truth.",
            "Target/gripper visibility cues are app-facing simulator metadata, not real-camera segmentation.",
        ],
    }
    status["readout"] = format_sim_camera_status(status)
    return status


def format_sim_camera_status(status: dict[str, Any]) -> str:
    image_size = status.get("image_size_px") if isinstance(status.get("image_size_px"), dict) else {}
    target = status.get("target") if isinstance(status.get("target"), dict) else {}
    gripper = status.get("gripper") if isinstance(status.get("gripper"), dict) else {}
    contract = status.get("metadata_contract") if isinstance(status.get("metadata_contract"), dict) else {}
    selected = status.get("selected_calibration") if isinstance(status.get("selected_calibration"), dict) else {}

    width = image_size.get("width") or "?"
    height = image_size.get("height") or "?"
    square = target.get("square") or "?"
    center = target.get("center_image_xy")
    if isinstance(center, list) and len(center) == 2:
        center_text = f"@({center[0]:.1f},{center[1]:.1f})"
    else:
        center_text = "@(?)"

    tracked = gripper.get("tracked_percent")
    tracked_text = "n/a" if tracked is None else f"{float(tracked):.0f}%"
    opening = gripper.get("current_opening_px")
    opening_text = "n/a" if opening is None else f"{float(opening):.1f}px"
    profile = status.get("profile") or "custom"
    candidate = selected.get("candidate_id")
    rank = selected.get("rank")
    candidate_text = f" | candidate={candidate} rank={rank}" if candidate else ""

    return (
        "Sim calibration: "
        f"profile={profile} view={status.get('view') or '?'} "
        f"frame={width}x{height} corners={status.get('board_corner_count', 0)} "
        f"target={square}{center_text} layout={target.get('piece_layout') or '?'} "
        f"gripper={'visible' if gripper.get('visible') else 'hidden'} "
        f"tracked={tracked_text} opening={opening_text} "
        f"contract={contract.get('status') or 'unknown'}"
        f"{candidate_text}"
    )
