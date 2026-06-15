#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
LLM_TOOLS_DIR = REPO_ROOT / "llm-tools"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(LLM_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(LLM_TOOLS_DIR))

from lerobot.cameras.configs import ColorMode  # noqa: E402
from lerobot.sim import (  # noqa: E402
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    SimCamera,
    make_sim_camera_config_from_profile,
)
import lerobot.sim.camera as sim_camera_module  # noqa: E402
from llm_toolkit import AppConfig, KinematicsTools  # noqa: E402
from smoke_sim_camera_pose_fixture import (  # noqa: E402
    CORNER_LABELS,
    assert_camera_metadata_contract,
    assert_corners_valid,
    board_point,
    image_stats,
    square_center_xy,
)
from smoke_sim_pick_place_calibration import (  # noqa: E402
    gripper_finger_quads,
    piece_visibility_metric,
    run_tool,
    sync_camera_to_tool_state,
)

SCHEMA = "lerobot.sim.gripper_camera_pov_review.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "gripper_camera_pov_review"
FROZEN_MARKER_TIME_SECONDS = 0.0
METADATA_CONTRACT_KEYS = (
    "image_size_px",
    "camera_matrix_px",
    "intrinsics",
    "distortion_coefficients",
    "extrinsics.board_to_camera",
    "coordinate_frame_convention",
    "board_corners_xy",
    "target_square.center_image_xy",
    "piece_square.center_image_xy",
    "gripper_state",
    "piece_visibility",
)

APPROACH_JOINTS = {
    "shoulder_pan": -6.0,
    "shoulder_lift": -18.0,
    "elbow_flex": 24.0,
    "wrist_flex": -22.0,
    "wrist_roll": 4.0,
}
RELEASE_JOINTS = {
    "shoulder_pan": 6.0,
    "shoulder_lift": -16.0,
    "elbow_flex": 20.0,
    "wrist_flex": -20.0,
    "wrist_roll": -4.0,
}


@dataclass(frozen=True)
class ReviewState:
    state_id: str
    description: str
    phase: str
    gripper_action: str
    gripper_percent: float | None
    joints: dict[str, float] | None
    approach_distance_mm: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a hardware-free gripper-camera POV review bundle showing target-piece "
            "visibility, gripper state, SimCamera metadata, and synthetic occlusion evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
    )
    parser.add_argument("--target-square", default="e4")
    parser.add_argument("--grasp-percent", type=float, default=24.0)
    parser.add_argument(
        "--min-visible-fraction",
        type=float,
        default=0.05,
        help="Minimum synthetic visible fraction required for each review state.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise AssertionError(f"cv2 failed to write {path}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def review_states(*, grasp_percent: float) -> list[ReviewState]:
    grasp = float(np.clip(grasp_percent, 0.0, 100.0))
    return [
        ReviewState(
            state_id="01_open_standoff",
            description="Open gripper before approach, with the target piece centered in the gripper camera view.",
            phase="standoff",
            gripper_action="open_gripper",
            gripper_percent=95.0,
            joints=None,
            approach_distance_mm=80.0,
        ),
        ReviewState(
            state_id="02_open_approach",
            description="Open gripper at the simulated approach pose.",
            phase="approach",
            gripper_action="open_gripper",
            gripper_percent=95.0,
            joints=APPROACH_JOINTS,
            approach_distance_mm=35.0,
        ),
        ReviewState(
            state_id="03_grasp_window",
            description="Partially closed gripper at the synthetic grasp window.",
            phase="grasp_window",
            gripper_action="set_gripper_percent",
            gripper_percent=grasp,
            joints=APPROACH_JOINTS,
            approach_distance_mm=12.0,
        ),
        ReviewState(
            state_id="04_closed_grasp",
            description="Closed gripper state used to expose maximum synthetic occlusion risk.",
            phase="closed",
            gripper_action="close_gripper",
            gripper_percent=0.0,
            joints=APPROACH_JOINTS,
            approach_distance_mm=4.0,
        ),
        ReviewState(
            state_id="05_release_open",
            description="Open gripper after the release-style state, with the target still projected.",
            phase="release",
            gripper_action="open_gripper",
            gripper_percent=95.0,
            joints=RELEASE_JOINTS,
            approach_distance_mm=35.0,
        ),
    ]


def run_state_tools(tools: KinematicsTools, state: ReviewState) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if state.joints:
        move_result = run_tool(tools, "move_joints", {**state.joints, "max_step_deg": 30.0})
        results.append({"tool": "move_joints", "args": state.joints, "result": move_result})

    if state.gripper_action == "open_gripper":
        result = run_tool(tools, "open_gripper")
        results.append({"tool": "open_gripper", "args": {}, "result": result})
    elif state.gripper_action == "close_gripper":
        result = run_tool(tools, "close_gripper")
        results.append({"tool": "close_gripper", "args": {}, "result": result})
    elif state.gripper_action == "set_gripper_percent":
        percent = float(0.0 if state.gripper_percent is None else state.gripper_percent)
        result = run_tool(tools, "set_gripper_percent", {"percent": percent})
        results.append({"tool": "set_gripper_percent", "args": {"percent": percent}, "result": result})
    else:
        raise AssertionError(f"Unknown gripper action: {state.gripper_action}")
    return results


def square_polygon_xy(corners_xy: np.ndarray, square: str) -> tuple[int, int, np.ndarray]:
    file_idx, rank_idx, _center = square_center_xy(corners_xy, square)
    u0 = file_idx / 8.0
    u1 = (file_idx + 1) / 8.0
    v0 = rank_idx / 8.0
    v1 = (rank_idx + 1) / 8.0
    polygon = np.array(
        [
            board_point(corners_xy, u0, v0),
            board_point(corners_xy, u1, v0),
            board_point(corners_xy, u1, v1),
            board_point(corners_xy, u0, v1),
        ],
        dtype=float,
    )
    return file_idx, rank_idx, polygon


def metadata_contract_checks(
    *,
    metadata: dict[str, Any],
    width: int,
    height: int,
    target_projection: dict[str, Any],
    piece_projection: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    base_checks = assert_camera_metadata_contract(metadata, width=width, height=height)
    checks = {
        **base_checks,
        "board_corners_xy": True,
        "target_square.center_image_xy": bool(target_projection.get("center_image_xy")),
        "piece_square.center_image_xy": bool(piece_projection.get("center_image_xy")),
        "gripper_state": finite_number(metadata.get("tracked_gripper_percent"))
        and finite_number(metadata.get("current_gripper_opening_px")),
        "piece_visibility": bool(visibility.get("available")),
        "required_keys": list(METADATA_CONTRACT_KEYS),
    }
    checks["all_required_keys_present"] = all(bool(checks.get(key)) for key in METADATA_CONTRACT_KEYS)
    return checks


def visibility_row(state_id: str, visibility: dict[str, Any]) -> dict[str, Any]:
    occlusion = visibility.get("occlusion") if isinstance(visibility.get("occlusion"), dict) else {}
    clearance = (
        visibility.get("gripper_clearance")
        if isinstance(visibility.get("gripper_clearance"), dict)
        else {}
    )
    piece = visibility.get("piece") if isinstance(visibility.get("piece"), dict) else {}
    return {
        "state_id": state_id,
        "available": visibility.get("available"),
        "status": visibility.get("status"),
        "piece_square": piece.get("square"),
        "piece_center_xy": piece.get("center_xy"),
        "visible_fraction": occlusion.get("visible_fraction"),
        "occlusion_fraction": occlusion.get("occlusion_fraction"),
        "overlap_piece_pixels": occlusion.get("overlap_piece_pixels"),
        "min_clearance_px": clearance.get("min_clearance_px"),
        "clear_of_gripper": clearance.get("clear_of_gripper"),
        "current_gripper_opening_px": clearance.get("current_gripper_opening_px"),
        "tracked_gripper_percent": clearance.get("tracked_gripper_percent"),
    }


def draw_marker(image_bgr: np.ndarray, point_xy: np.ndarray, label: str, color: tuple[int, int, int]) -> None:
    xy = (int(round(float(point_xy[0]))), int(round(float(point_xy[1]))))
    cv2.drawMarker(image_bgr, xy, color, markerType=cv2.MARKER_CROSS, markerSize=24, thickness=2)
    cv2.putText(image_bgr, label, (xy[0] + 9, xy[1] + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3)
    cv2.putText(image_bgr, label, (xy[0] + 9, xy[1] + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)


def add_label_band(image_bgr: np.ndarray, lines: list[str]) -> np.ndarray:
    out = image_bgr.copy()
    height_px = min(out.shape[0], 76)
    cv2.rectangle(out, (0, 0), (out.shape[1], height_px), (0, 0, 0), -1)
    for index, line in enumerate(lines[:4]):
        y = 18 + index * 17
        cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return out


def annotate_frame(
    *,
    frame_bgr: np.ndarray,
    state: ReviewState,
    target_square: str,
    corners_xy: np.ndarray,
    target_polygon_xy: np.ndarray,
    target_center_xy: np.ndarray,
    piece_center_xy: np.ndarray,
    camera: SimCamera,
    metadata: dict[str, Any],
    row: dict[str, Any],
) -> np.ndarray:
    out = frame_bgr.copy()
    cv2.polylines(out, [np.round(corners_xy).astype(np.int32)], isClosed=True, color=(0, 210, 255), thickness=2)
    cv2.polylines(
        out,
        [np.round(target_polygon_xy).astype(np.int32)],
        isClosed=True,
        color=(0, 255, 0),
        thickness=2,
    )
    for label, point in zip(CORNER_LABELS, corners_xy, strict=True):
        xy = (int(round(float(point[0]))), int(round(float(point[1]))))
        cv2.circle(out, xy, 5, (0, 0, 255), -1)
        cv2.putText(out, label, (xy[0] + 6, xy[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1)
    if float(np.linalg.norm(target_center_xy - piece_center_xy)) < 1e-6:
        draw_marker(out, target_center_xy, f"target/piece {target_square}", (0, 255, 0))
    else:
        draw_marker(out, target_center_xy, f"target {target_square}", (0, 255, 0))
        draw_marker(out, piece_center_xy, "piece", (255, 0, 255))

    for quad in gripper_finger_quads(camera, metadata):
        cv2.polylines(out, [np.round(quad).astype(np.int32)], isClosed=True, color=(255, 220, 0), thickness=2)

    visible = row.get("visible_fraction")
    occlusion = row.get("occlusion_fraction")
    clearance = row.get("min_clearance_px")
    return add_label_band(
        out,
        [
            f"{state.state_id} phase={state.phase}",
            f"target={target_square} gripper={row.get('tracked_gripper_percent')}% opening_px={row.get('current_gripper_opening_px')}",
            f"visible={visible} occlusion={occlusion} clearance_px={clearance}",
            "synthetic metadata evidence only",
        ],
    )


def capture_review_state(
    *,
    state: ReviewState,
    tools: KinematicsTools,
    camera: SimCamera,
    profile_name: str,
    output_dir: Path,
    target_square: str,
    min_visible_fraction: float,
) -> dict[str, Any]:
    tool_results = run_state_tools(tools, state)
    joints = sync_camera_to_tool_state(tools, camera)

    original_time = sim_camera_module.time.time
    sim_camera_module.time.time = lambda: FROZEN_MARKER_TIME_SECONDS
    try:
        frame_bgr = camera.read(ColorMode.BGR)
        metadata = camera.calibration_metadata()
    finally:
        sim_camera_module.time.time = original_time

    width = int(camera.width or 640)
    height = int(camera.height or 480)
    expected_shape = (height, width, 3)
    if frame_bgr.shape != expected_shape:
        raise AssertionError(f"{state.state_id} frame shape {frame_bgr.shape} != {expected_shape}")
    if frame_bgr.dtype != np.uint8:
        raise AssertionError(f"{state.state_id} frame dtype {frame_bgr.dtype} != uint8")

    stats = image_stats(frame_bgr)
    if int(stats["unique_colors"]) < 12:
        raise AssertionError(f"{state.state_id} rendered too few unique colors: {stats['unique_colors']}")

    corners_xy = np.asarray(metadata["board_corners_xy"], dtype=float)
    corner_checks = assert_corners_valid(corners_xy, width, height)
    target_file, target_rank, target_center = square_center_xy(corners_xy, target_square)
    piece_square = str(metadata.get("piece_square") or target_square)
    piece_file, piece_rank, piece_center = square_center_xy(corners_xy, piece_square)
    _target_file, _target_rank, target_polygon = square_polygon_xy(corners_xy, target_square)
    visibility = piece_visibility_metric(camera, metadata)
    row = visibility_row(state.state_id, visibility)

    target_projection = {
        "square": target_square,
        "file_idx": target_file,
        "rank_idx": target_rank,
        "center_image_xy": [round(float(value), 3) for value in target_center],
        "polygon_image_xy": [[round(float(x), 3), round(float(y), 3)] for x, y in target_polygon.tolist()],
    }
    piece_projection = {
        "square": piece_square,
        "file_idx": piece_file,
        "rank_idx": piece_rank,
        "center_image_xy": [round(float(value), 3) for value in piece_center],
    }
    contract_checks = metadata_contract_checks(
        metadata=metadata,
        width=width,
        height=height,
        target_projection=target_projection,
        piece_projection=piece_projection,
        visibility=visibility,
    )

    visible_fraction = row.get("visible_fraction")
    visibility_ok = (
        bool(row.get("available"))
        and finite_number(visible_fraction)
        and float(visible_fraction) >= float(min_visible_fraction)
    )

    state_dir = output_dir / "states" / state.state_id
    frame_path = state_dir / "frame.png"
    annotated_path = state_dir / "frame_annotated.png"
    metadata_path = state_dir / "metadata.json"
    annotated = annotate_frame(
        frame_bgr=frame_bgr,
        state=state,
        target_square=target_square,
        corners_xy=corners_xy,
        target_polygon_xy=target_polygon,
        target_center_xy=target_center,
        piece_center_xy=piece_center,
        camera=camera,
        metadata=metadata,
        row=row,
    )
    write_image(frame_path, frame_bgr)
    write_image(annotated_path, annotated)

    payload = {
        "schema": SCHEMA,
        "ok": bool(contract_checks["all_required_keys_present"] and visibility_ok),
        "state_id": state.state_id,
        "description": state.description,
        "phase": state.phase,
        "approach_distance_mm": state.approach_distance_mm,
        "target_square": target_square,
        "profile": profile_name,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "deterministic": {
            "sim_camera_marker_time_seconds": FROZEN_MARKER_TIME_SECONDS,
            "warmup": False,
        },
        "artifacts": {
            "frame_path": str(frame_path),
            "annotated_frame_path": str(annotated_path),
            "metadata_path": str(metadata_path),
        },
        "image": {
            **stats,
            "frame_sha256": file_sha256(frame_path),
            "annotated_frame_sha256": file_sha256(annotated_path),
        },
        "camera_metadata": metadata,
        "metadata_contract_checks": contract_checks,
        "corner_checks": corner_checks,
        "projection": {
            "corner_labels": list(CORNER_LABELS),
            "board_corners_xy": [[round(float(x), 3), round(float(y), 3)] for x, y in corners_xy.tolist()],
            "target_square": target_projection,
            "piece_square": piece_projection,
        },
        "gripper_state": {
            "action": state.gripper_action,
            "requested_percent": state.gripper_percent,
            "tracked_gripper_percent": metadata.get("tracked_gripper_percent"),
            "current_gripper_opening_px": metadata.get("current_gripper_opening_px"),
            "robot_joints": joints,
            "tool_results": tool_results,
        },
        "piece_visibility": visibility,
        "visibility_row": row,
        "visibility_threshold": {
            "min_visible_fraction": float(min_visible_fraction),
            "visible_fraction": visible_fraction,
            "ok": visibility_ok,
        },
        "limitations": [
            "Synthetic-frame geometry only; this does not model physical chess-piece contact or real camera segmentation.",
            "The gripper-camera POV uses existing SimCamera metadata and simulated gripper geometry, not real camera pixels.",
        ],
    }
    write_json(metadata_path, payload)
    return payload


def metadata_contract_summary(states: list[dict[str, Any]]) -> dict[str, Any]:
    by_state: dict[str, dict[str, bool]] = {}
    for state in states:
        checks = state.get("metadata_contract_checks")
        checks = checks if isinstance(checks, dict) else {}
        by_state[str(state.get("state_id"))] = {
            key: bool(checks.get(key))
            for key in METADATA_CONTRACT_KEYS
        }
    return {
        "required_keys": list(METADATA_CONTRACT_KEYS),
        "all_states_include_required_metadata": all(
            all(state_checks.values()) for state_checks in by_state.values()
        ),
        "state_count": len(states),
        "by_state": by_state,
        "scope": (
            "SimCamera intrinsics/extrinsics are stable simulator reference metadata, "
            "not physical SO-101 calibration truth."
        ),
    }


def visibility_summary(states: list[dict[str, Any]], *, min_visible_fraction: float) -> dict[str, Any]:
    rows = [
        state.get("visibility_row")
        for state in states
        if isinstance(state.get("visibility_row"), dict)
    ]
    visible_values = [
        float(row["visible_fraction"])
        for row in rows
        if finite_number(row.get("visible_fraction"))
    ]
    occlusion_values = [
        float(row["occlusion_fraction"])
        for row in rows
        if finite_number(row.get("occlusion_fraction"))
    ]
    clearance_values = [
        float(row["min_clearance_px"])
        for row in rows
        if finite_number(row.get("min_clearance_px"))
    ]
    worst = min(
        (row for row in rows if finite_number(row.get("visible_fraction"))),
        key=lambda row: float(row["visible_fraction"]),
        default=None,
    )
    return {
        "available": bool(rows),
        "state_count": len(states),
        "available_state_count": len(rows),
        "all_states_available": len(rows) == len(states),
        "min_visible_fraction": min(visible_values) if visible_values else None,
        "max_occlusion_fraction": max(occlusion_values) if occlusion_values else None,
        "min_clearance_px": min(clearance_values) if clearance_values else None,
        "worst_state_id": worst.get("state_id") if worst else None,
        "all_states_clear_of_gripper": (
            all(bool(row.get("clear_of_gripper")) for row in rows) if rows else None
        ),
        "threshold": {
            "min_visible_fraction": float(min_visible_fraction),
            "all_states_meet_min_visible_fraction": (
                all(value >= float(min_visible_fraction) for value in visible_values)
                and len(visible_values) == len(states)
            ),
        },
        "states": rows,
        "limitations": [
            "Synthetic geometry only; this does not model physical chess-piece contact or real camera segmentation.",
            "These values are review evidence for camera-first calibration and are not real-world visibility thresholds.",
        ],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_square = str(args.target_square)
    min_visible_fraction = float(np.clip(float(args.min_visible_fraction), 0.0, 1.0))

    camera_cfg = make_sim_camera_config_from_profile(
        str(args.profile),
        color_mode=ColorMode.BGR,
        view="gripper",
        piece_layout="single_pawn",
        piece_square=target_square,
        track_robot_gripper=True,
        gripper_visible=True,
    )
    app_cfg = AppConfig(
        port=None,
        robot_id="so101_sim_gripper_camera_pov_review",
        sim=True,
        camera_width=int(camera_cfg.width),
        camera_height=int(camera_cfg.height),
        camera_fps=int(camera_cfg.fps),
    )
    tools = KinematicsTools(app_cfg)
    camera = SimCamera(camera_cfg)
    state_payloads: list[dict[str, Any]] = []

    try:
        if tools.robot is None or not tools.robot.is_connected:
            raise AssertionError("sim robot did not connect")
        camera.connect(warmup=False)
        for state in review_states(grasp_percent=float(args.grasp_percent)):
            state_payloads.append(
                capture_review_state(
                    state=state,
                    tools=tools,
                    camera=camera,
                    profile_name=str(args.profile),
                    output_dir=output_dir,
                    target_square=target_square,
                    min_visible_fraction=min_visible_fraction,
                )
            )
    finally:
        if camera.is_connected:
            camera.disconnect()
        tools.disconnect_robot()

    frame_paths = {
        state["state_id"]: state["artifacts"]["frame_path"]
        for state in state_payloads
    }
    annotated_frame_paths = {
        state["state_id"]: state["artifacts"]["annotated_frame_path"]
        for state in state_payloads
    }
    metadata_paths = {
        state["state_id"]: state["artifacts"]["metadata_path"]
        for state in state_payloads
    }
    contract = metadata_contract_summary(state_payloads)
    visibility = visibility_summary(state_payloads, min_visible_fraction=min_visible_fraction)
    all_artifacts_exist = all(
        Path(path).is_file()
        for collection in (frame_paths, annotated_frame_paths, metadata_paths)
        for path in collection.values()
    )
    ok = (
        all(bool(state.get("ok")) for state in state_payloads)
        and bool(contract["all_states_include_required_metadata"])
        and bool(visibility["threshold"]["all_states_meet_min_visible_fraction"])
        and all_artifacts_exist
    )

    summary_path = output_dir / "gripper_camera_pov_review_summary.json"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "profile": str(args.profile),
        "target_square": target_square,
        "state_count": len(state_payloads),
        "state_ids": [state["state_id"] for state in state_payloads],
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "skipped_markers": {
            "hardware": "POV review uses SimRobot/KinematicsTools and SimCamera only; no SO-101 motors, serial ports, or camera devices are opened.",
            "gui": "POV review writes images/JSON directly and does not open OpenCV display or calibration click flows.",
            "openai": "POV review uses local simulator paths only; no OpenAI credentials or network calls are required.",
        },
        "deterministic": {
            "sim_camera_marker_time_seconds": FROZEN_MARKER_TIME_SECONDS,
            "warmup": False,
            "states": [state["state_id"] for state in state_payloads],
        },
        "artifacts": {
            "summary_path": str(summary_path),
            "state_dir": str(output_dir / "states"),
            "frame_paths": frame_paths,
            "annotated_frame_paths": annotated_frame_paths,
            "metadata_paths": metadata_paths,
        },
        "frame_paths": frame_paths,
        "annotated_frame_paths": annotated_frame_paths,
        "metadata_paths": metadata_paths,
        "metadata_contract": contract,
        "piece_visibility": visibility,
        "states": state_payloads,
        "limitations": [
            "This artifact is synthetic geometry evidence only and does not model physical chess-piece contact.",
            "Visibility and clearance are derived from existing SimCamera capture metadata and gripper geometry, not from real-camera segmentation.",
            "SimCamera intrinsics/extrinsics are simulator reference metadata for camera-first tooling compatibility, not physical calibration truth.",
        ],
        "real_media_gap_notes": [
            "The current real reference media inventory is limited to archive/chess_test_images/current_view.jpg.",
            "No real-world videos are present for motion, recovery, or timing references.",
            "No reference media currently documents failure modes.",
        ],
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
