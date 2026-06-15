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


@dataclass(frozen=True)
class RankedSimCameraProfileSelection:
    """Resolved simulator camera overrides selected from a ranked session summary."""

    summary_path: Path
    rank: int
    candidate_id: str
    candidate_path: Path
    base_profile: str
    profile_overrides: dict[str, Any]
    candidate_artifact_dir: str | None = None


def make_sim_camera_config_from_profile(profile_name: str, **overrides: Any) -> SimCameraConfig:
    try:
        profile_values = SIM_CAMERA_CALIBRATION_PROFILES[profile_name]
    except KeyError as exc:
        known_profiles = ", ".join(sorted(SIM_CAMERA_CALIBRATION_PROFILES))
        raise ValueError(f"Unknown SimCamera calibration profile {profile_name!r}. Known profiles: {known_profiles}") from exc

    return SimCameraConfig(**{**profile_values, **overrides})


def select_ranked_sim_camera_profile_overrides(
    summary_path: str | Path,
    *,
    rank: int = 1,
    candidate_id: str | None = None,
) -> RankedSimCameraProfileSelection:
    """Select simulator camera profile overrides from a ranked session_summary.json.

    The selected ranking entry points at an existing profile_candidate.json, which
    is then loaded through load_sim_camera_profile_overrides so summary selection
    has the same validation behavior as direct candidate loading.
    """

    resolved_summary_path = Path(summary_path).expanduser().resolve()
    payload = _load_ranked_session_summary_payload(resolved_summary_path)
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        raise ValueError(f"Ranked simulator calibration summary {resolved_summary_path} must contain a non-empty ranking list.")

    entry: dict[str, Any] | None = None
    if candidate_id is not None:
        candidate_id = str(candidate_id).strip()
        if not candidate_id:
            raise ValueError("sim calibration candidate id must be non-empty.")
        matches = [
            item
            for item in ranking
            if isinstance(item, dict) and str(item.get("candidate_id", "")) == candidate_id
        ]
        if not matches:
            known = ", ".join(
                str(item.get("candidate_id"))
                for item in ranking
                if isinstance(item, dict) and item.get("candidate_id")
            )
            raise ValueError(
                f"Candidate id {candidate_id!r} was not found in ranked simulator calibration summary "
                f"{resolved_summary_path}. Known candidate ids: {known or '(none)'}."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Candidate id {candidate_id!r} appears more than once in ranked simulator calibration summary "
                f"{resolved_summary_path}."
            )
        entry = matches[0]
    else:
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise ValueError(f"sim calibration rank must be a positive integer, got {rank!r}.")
        matches = [item for item in ranking if isinstance(item, dict) and item.get("rank") == rank]
        if matches:
            if len(matches) > 1:
                raise ValueError(
                    f"Rank {rank} appears more than once in ranked simulator calibration summary "
                    f"{resolved_summary_path}."
                )
            entry = matches[0]
        elif rank <= len(ranking) and isinstance(ranking[rank - 1], dict):
            entry = ranking[rank - 1]
        else:
            raise ValueError(
                f"Rank {rank} was not found in ranked simulator calibration summary {resolved_summary_path}; "
                f"available ranks: 1..{len(ranking)}."
            )

    if not isinstance(entry, dict):
        raise ValueError(f"Selected ranking entry in {resolved_summary_path} must be a JSON object.")

    selected_rank = entry.get("rank")
    if isinstance(selected_rank, bool) or not isinstance(selected_rank, int) or selected_rank < 1:
        selected_rank = int(rank)
    selected_candidate_id = entry.get("candidate_id")
    if not isinstance(selected_candidate_id, str) or not selected_candidate_id.strip():
        raise ValueError(f"Selected ranking entry in {resolved_summary_path} must include candidate_id.")

    raw_candidate_path = entry.get("candidate_path")
    if not isinstance(raw_candidate_path, str) or not raw_candidate_path.strip():
        artifact_paths = entry.get("artifact_paths")
        if isinstance(artifact_paths, dict):
            raw_candidate_path = artifact_paths.get("candidate_path")
    if not isinstance(raw_candidate_path, str) or not raw_candidate_path.strip():
        raise ValueError(
            f"Selected ranking entry {selected_candidate_id!r} in {resolved_summary_path} must include candidate_path."
        )
    candidate_path = _resolve_summary_referenced_path(raw_candidate_path, summary_path=resolved_summary_path)
    if not candidate_path.is_file():
        raise ValueError(
            f"Selected candidate {selected_candidate_id!r} from {resolved_summary_path} does not exist: "
            f"{candidate_path}"
        )

    candidate_payload = _load_json_object(candidate_path, label="simulator camera profile candidate")
    base_profile = str(candidate_payload.get("base_profile") or CURRENT_GRIPPER_REFERENCE_PROFILE)
    if base_profile not in SIM_CAMERA_CALIBRATION_PROFILES:
        known_profiles = ", ".join(sorted(SIM_CAMERA_CALIBRATION_PROFILES))
        raise ValueError(
            f"Unknown base profile {base_profile!r} in selected candidate {candidate_path}. "
            f"Known profiles: {known_profiles}"
        )
    profile_overrides = load_sim_camera_profile_overrides(candidate_path)

    candidate_artifact_dir = entry.get("candidate_artifact_dir")
    return RankedSimCameraProfileSelection(
        summary_path=resolved_summary_path,
        rank=int(selected_rank),
        candidate_id=selected_candidate_id,
        candidate_path=candidate_path,
        base_profile=base_profile,
        profile_overrides=profile_overrides,
        candidate_artifact_dir=str(candidate_artifact_dir) if isinstance(candidate_artifact_dir, str) else None,
    )


def load_ranked_sim_camera_profile_overrides(
    summary_path: str | Path,
    *,
    rank: int = 1,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Load selected simulator camera overrides from a ranked session_summary.json."""

    return select_ranked_sim_camera_profile_overrides(
        summary_path, rank=rank, candidate_id=candidate_id
    ).profile_overrides


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


def _load_ranked_session_summary_payload(summary_path: Path) -> dict[str, Any]:
    payload = _load_json_object(summary_path, label="ranked simulator calibration summary")
    scenario = payload.get("scenario")
    if scenario is not None and scenario != "sim_calibration_session_report":
        raise ValueError(
            f"Unsupported ranked simulator calibration summary scenario in {summary_path}: {scenario!r}. "
            "Expected 'sim_calibration_session_report'."
        )
    return payload


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object, got {type(payload).__name__}.")
    return payload


def _resolve_summary_referenced_path(value: str, *, summary_path: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = summary_path.parent / path
    return path.resolve()


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
