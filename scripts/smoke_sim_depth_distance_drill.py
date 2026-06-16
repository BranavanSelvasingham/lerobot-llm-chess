#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
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
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.cameras.configs import ColorMode  # noqa: E402
from lerobot.sim import (  # noqa: E402
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    SimCamera,
    make_sim_camera_config_from_profile,
)
from lerobot.sim.config import SIM_CAMERA_REFERENCE_BOARD_SIZE_M  # noqa: E402

SCHEMA = "lerobot.sim.depth_distance_drill.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "depth_distance_drill"
DEFAULT_SQUARES = ("a1", "d1", "h1", "a4", "d4", "e4", "h4", "a8", "d8", "h8")
CSV_FIELDNAMES = (
    "perturbation_id",
    "square",
    "file_idx",
    "rank_idx",
    "risk_status",
    "risk_score",
    "camera_to_board_plane_distance_mm",
    "camera_to_board_square_range_mm",
    "camera_to_board_square_z_depth_mm",
    "camera_to_piece_proxy_range_mm",
    "camera_to_piece_proxy_z_depth_mm",
    "piece_proxy_height_above_board_mm",
    "piece_proxy_camera_z_delta_from_board_mm",
    "piece_projected_x_px",
    "piece_projected_y_px",
    "board_projected_x_px",
    "board_projected_y_px",
    "edge_margin_px",
    "gripper_clearance_px",
    "gripper_overlap",
    "range_delta_from_nominal_mm",
    "z_depth_delta_from_nominal_mm",
    "projected_delta_from_nominal_px",
    "translation_delta_x_m",
    "translation_delta_y_m",
    "translation_delta_z_m",
    "rotation_delta_x_deg",
    "rotation_delta_y_deg",
    "rotation_delta_z_deg",
    "limitations",
)


@dataclass(frozen=True)
class PerturbationProfile:
    profile_id: str
    description: str
    translation_delta_m: tuple[float, float, float]
    rotation_delta_deg: tuple[float, float, float]


PERTURBATION_PROFILES: tuple[PerturbationProfile, ...] = (
    PerturbationProfile(
        profile_id="nominal",
        description="Unmodified SimCamera board_to_camera metadata.",
        translation_delta_m=(0.0, 0.0, 0.0),
        rotation_delta_deg=(0.0, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="camera_left_8mm",
        description="Camera-frame x translation proxy: board projects slightly right/left.",
        translation_delta_m=(0.008, 0.0, 0.0),
        rotation_delta_deg=(0.0, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="camera_right_8mm",
        description="Opposite camera-frame x translation proxy.",
        translation_delta_m=(-0.008, 0.0, 0.0),
        rotation_delta_deg=(0.0, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="camera_down_8mm",
        description="Camera-frame y translation proxy: board projects closer to the gripper band.",
        translation_delta_m=(0.0, 0.008, 0.0),
        rotation_delta_deg=(0.0, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="camera_closer_12mm",
        description="Camera-frame z translation proxy with the board 12 mm closer.",
        translation_delta_m=(0.0, 0.0, -0.012),
        rotation_delta_deg=(0.0, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="camera_farther_12mm",
        description="Camera-frame z translation proxy with the board 12 mm farther.",
        translation_delta_m=(0.0, 0.0, 0.012),
        rotation_delta_deg=(0.0, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="pitch_plus_1_25deg",
        description="Small camera-frame x-axis rotation proxy.",
        translation_delta_m=(0.0, 0.0, 0.0),
        rotation_delta_deg=(1.25, 0.0, 0.0),
    ),
    PerturbationProfile(
        profile_id="yaw_plus_1_25deg",
        description="Small camera-frame y-axis rotation proxy.",
        translation_delta_m=(0.0, 0.0, 0.0),
        rotation_delta_deg=(0.0, 1.25, 0.0),
    ),
)


SIMULATOR_ONLY_LIMITATIONS = [
    "Simulator-only drill: no SO-101 motors, serial ports, live cameras, GUI calibration flows, OpenAI calls, or real robot execution paths are used.",
    "Depth/range values come from SimCamera metadata-native pinhole intrinsics and board_to_camera extrinsics, not from real depth sensing.",
    "piece_proxy uses a configurable board-frame height above the square center; it is pickup-depth evidence, not measured physical contact.",
    "gripper_clearance_px uses the synthetic rendered gripper overlay as a 2D occlusion proxy and does not model real gripper jaws or segmentation.",
    "Perturbation profiles are deterministic simulator pose probes; they are not canonical calibration constants.",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free SimCamera depth/distance calibration drill across selected "
            "board squares and deterministic camera-pose perturbations."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
    )
    parser.add_argument(
        "--squares",
        nargs="+",
        default=list(DEFAULT_SQUARES),
        help="Chess squares to sample. Defaults cover center, edges, back rank, and near-gripper rows.",
    )
    parser.add_argument(
        "--piece-proxy-height-mm",
        type=float,
        default=32.0,
        help="Board-frame height used for the pickup/contact proxy point above each square.",
    )
    parser.add_argument(
        "--grasp-percent",
        type=float,
        default=24.0,
        help="Synthetic gripper percentage used when computing gripper overlay clearance.",
    )
    parser.add_argument(
        "--edge-risk-margin-px",
        type=float,
        default=42.0,
        help="Projected points below this image-edge margin increase risk.",
    )
    parser.add_argument(
        "--gripper-risk-clearance-px",
        type=float,
        default=28.0,
        help="Projected points closer than this to a visible gripper finger increase risk.",
    )
    parser.add_argument(
        "--depth-risk-delta-mm",
        type=float,
        default=18.0,
        help="Range/depth change from nominal above this threshold increases risk.",
    )
    parser.add_argument(
        "--pixel-risk-delta-px",
        type=float,
        default=24.0,
        help="Projected pixel shift from nominal above this threshold increases risk.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in CSV_FIELDNAMES})


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise AssertionError(f"OpenCV failed to write {path}")


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return value


def validate_square(square: str) -> str:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square {square!r}; expected a1 through h8.")
    return value


def square_file_rank(square: str) -> tuple[int, int]:
    value = validate_square(square)
    return ord(value[0]) - ord("a"), int(value[1]) - 1


def board_square_center_m(square: str) -> tuple[int, int, np.ndarray]:
    file_idx, rank_idx = square_file_rank(square)
    square_size_m = float(SIM_CAMERA_REFERENCE_BOARD_SIZE_M) / 8.0
    return file_idx, rank_idx, np.array(
        [(file_idx + 0.5) * square_size_m, (rank_idx + 0.5) * square_size_m, 0.0],
        dtype=float,
    )


def rotation_matrix_from_xyz_degrees(rotation_delta_deg: tuple[float, float, float]) -> np.ndarray:
    rx, ry, rz = [math.radians(float(value)) for value in rotation_delta_deg]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rot_x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=float)
    rot_y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=float)
    rot_z = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    return rot_z @ rot_y @ rot_x


def perturbed_extrinsics(base: dict[str, Any], profile: PerturbationProfile) -> dict[str, Any]:
    rotation = np.asarray(base.get("rotation_matrix"), dtype=float)
    translation = np.asarray(base.get("translation_m"), dtype=float)
    if rotation.shape != (3, 3) or translation.shape != (3,):
        raise ValueError("SimCamera board_to_camera_extrinsics must include 3x3 rotation_matrix and 3-vector translation_m.")
    if not np.isfinite(rotation).all() or not np.isfinite(translation).all():
        raise ValueError("SimCamera board_to_camera_extrinsics must contain finite numeric values.")

    delta_rotation = rotation_matrix_from_xyz_degrees(profile.rotation_delta_deg)
    delta_translation = np.asarray(profile.translation_delta_m, dtype=float)
    result = dict(base)
    result["name"] = f"{base.get('name', 'sim_board_to_camera')}_{profile.profile_id}"
    result["rotation_matrix"] = (delta_rotation @ rotation).tolist()
    result["translation_m"] = (delta_rotation @ translation + delta_translation).tolist()
    result["perturbation_profile"] = {
        "profile_id": profile.profile_id,
        "description": profile.description,
        "translation_delta_m": list(profile.translation_delta_m),
        "rotation_delta_deg": list(profile.rotation_delta_deg),
        "composition": (
            "camera-frame proxy: camera_point_perturbed = R_delta @ "
            "(R_base @ board_point + t_base) + translation_delta"
        ),
    }
    return result


def camera_for_profile(
    *,
    profile_name: str,
    perturbation: PerturbationProfile,
    grasp_percent: float,
) -> tuple[SimCamera, dict[str, Any]]:
    base_cfg = make_sim_camera_config_from_profile(profile_name, color_mode=ColorMode.BGR)
    if base_cfg.board_to_camera_extrinsics is None:
        raise ValueError(f"SimCamera profile {profile_name!r} did not resolve board_to_camera_extrinsics.")
    camera_cfg = make_sim_camera_config_from_profile(
        profile_name,
        color_mode=ColorMode.BGR,
        board_to_camera_extrinsics=perturbed_extrinsics(base_cfg.board_to_camera_extrinsics, perturbation),
        metadata_projected_board_geometry=True,
        piece_layout="single_pawn",
        piece_square="e4",
        gripper_visible=True,
    )
    camera = SimCamera(camera_cfg)
    camera.set_robot_state({"gripper": float(np.clip(grasp_percent, 0.0, 100.0))})
    metadata = camera.calibration_metadata()
    return camera, metadata


def camera_metadata_matrices(metadata: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    camera_matrix = np.asarray(metadata.get("camera_matrix_px"), dtype=float)
    board_to_camera = metadata.get("extrinsics", {}).get("board_to_camera", {})
    rotation = np.asarray(board_to_camera.get("rotation_matrix"), dtype=float)
    translation = np.asarray(board_to_camera.get("translation_m"), dtype=float)
    if camera_matrix.shape != (3, 3) or rotation.shape != (3, 3) or translation.shape != (3,):
        raise ValueError("camera_metadata must include camera_matrix_px and extrinsics.board_to_camera.")
    if not (np.isfinite(camera_matrix).all() and np.isfinite(rotation).all() and np.isfinite(translation).all()):
        raise ValueError("camera_metadata camera matrix and board_to_camera extrinsics must be finite.")
    return camera_matrix, rotation, translation


def project_camera_point(camera_matrix: np.ndarray, camera_xyz_m: np.ndarray) -> np.ndarray:
    if float(camera_xyz_m[2]) <= 1e-9:
        raise ValueError(f"Cannot project point behind the camera: {camera_xyz_m.tolist()}")
    homogeneous = camera_matrix @ camera_xyz_m
    image_xy = homogeneous[:2] / homogeneous[2]
    if not np.isfinite(image_xy).all():
        raise ValueError(f"Projection produced non-finite pixel coordinates for {camera_xyz_m.tolist()}")
    return image_xy


def board_plane_distance_m(rotation: np.ndarray, translation: np.ndarray) -> float:
    board_normal_camera = rotation[:, 2]
    normal_norm = float(np.linalg.norm(board_normal_camera))
    if normal_norm <= 1e-12:
        raise ValueError("board_to_camera rotation has a degenerate board normal.")
    return abs(float(np.dot(board_normal_camera / normal_norm, translation)))


def gripper_finger_quads(camera: SimCamera, metadata: dict[str, Any]) -> list[np.ndarray]:
    if not bool(metadata.get("gripper_visible")) or metadata.get("view") != "gripper":
        return []
    height = int(camera.height or 480)
    width = int(camera.width or 640)
    center_x = int(camera.config.gripper_center_x_px or (width // 2))
    y_base = int(camera.config.gripper_y_px or int(height * 0.78))
    metadata_opening = metadata.get("current_gripper_opening_px")
    opening = int(camera.config.gripper_opening_px if metadata_opening is None else metadata_opening)
    finger_w = max(12, int(camera.config.gripper_finger_width_px))
    length = max(40, int(camera.config.gripper_length_px))
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
    return [left, right]


def point_to_gripper_clearance_px(point_xy: np.ndarray, quads: list[np.ndarray]) -> float | None:
    if not quads:
        return None
    distances = [
        float(cv2.pointPolygonTest(quad.astype(np.float32), tuple(point_xy.astype(float)), measureDist=True))
        for quad in quads
    ]
    # pointPolygonTest is positive inside the polygon; expose overlap as negative clearance.
    return -max(distances)


def edge_margin_px(point_xy: np.ndarray, *, width: int, height: int) -> float:
    x, y = float(point_xy[0]), float(point_xy[1])
    return float(min(x, float(width - 1) - x, y, float(height - 1) - y))


def clipped_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 1e-9:
        return 0.0
    return float(np.clip(numerator / denominator, 0.0, 1.0))


def risk_status(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def evaluate_rows(args: argparse.Namespace, squares: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    camera_contract: dict[str, Any] | None = None
    piece_height_m = float(args.piece_proxy_height_mm) / 1000.0
    if piece_height_m <= 0.0 or not math.isfinite(piece_height_m):
        raise ValueError("--piece-proxy-height-mm must be a positive finite value.")

    for perturbation in PERTURBATION_PROFILES:
        camera, metadata = camera_for_profile(
            profile_name=str(args.profile),
            perturbation=perturbation,
            grasp_percent=float(args.grasp_percent),
        )
        camera_matrix, rotation, translation = camera_metadata_matrices(metadata)
        width = int(camera.width or metadata.get("image_size_px", {}).get("width") or 640)
        height = int(camera.height or metadata.get("image_size_px", {}).get("height") or 480)
        gripper_quads = gripper_finger_quads(camera, metadata)
        board_distance = board_plane_distance_m(rotation, translation)

        if camera_contract is None:
            camera_contract = {
                "image_size_px": {"width": width, "height": height},
                "camera_matrix_px": camera_matrix.tolist(),
                "distortion_coefficients": metadata.get("distortion_coefficients"),
                "distortion_model": metadata.get("distortion_model"),
                "coordinate_frame_convention": metadata.get("coordinate_frame_convention"),
                "calibration_metadata_scope": metadata.get("calibration_metadata_scope"),
                "source_model": "simcamera_metadata",
            }

        for square in squares:
            file_idx, rank_idx, board_point_m = board_square_center_m(square)
            piece_point_m = board_point_m + np.array([0.0, 0.0, piece_height_m], dtype=float)
            board_camera_m = rotation @ board_point_m + translation
            piece_camera_m = rotation @ piece_point_m + translation
            board_pixel = project_camera_point(camera_matrix, board_camera_m)
            piece_pixel = project_camera_point(camera_matrix, piece_camera_m)
            gripper_clearance = point_to_gripper_clearance_px(piece_pixel, gripper_quads)
            row = {
                "perturbation_id": perturbation.profile_id,
                "perturbation_description": perturbation.description,
                "square": square,
                "file_idx": file_idx,
                "rank_idx": rank_idx,
                "board_point_m": [float(value) for value in board_point_m.tolist()],
                "piece_proxy_point_m": [float(value) for value in piece_point_m.tolist()],
                "camera_frame_board_xyz_mm": [float(value * 1000.0) for value in board_camera_m.tolist()],
                "camera_frame_piece_proxy_xyz_mm": [float(value * 1000.0) for value in piece_camera_m.tolist()],
                "camera_to_board_plane_distance_mm": float(board_distance * 1000.0),
                "camera_to_board_square_range_mm": float(np.linalg.norm(board_camera_m) * 1000.0),
                "camera_to_board_square_z_depth_mm": float(board_camera_m[2] * 1000.0),
                "camera_to_piece_proxy_range_mm": float(np.linalg.norm(piece_camera_m) * 1000.0),
                "camera_to_piece_proxy_z_depth_mm": float(piece_camera_m[2] * 1000.0),
                "piece_proxy_height_above_board_mm": float(args.piece_proxy_height_mm),
                "piece_proxy_camera_z_delta_from_board_mm": float((board_camera_m[2] - piece_camera_m[2]) * 1000.0),
                "piece_projected_x_px": float(piece_pixel[0]),
                "piece_projected_y_px": float(piece_pixel[1]),
                "board_projected_x_px": float(board_pixel[0]),
                "board_projected_y_px": float(board_pixel[1]),
                "edge_margin_px": edge_margin_px(piece_pixel, width=width, height=height),
                "gripper_clearance_px": gripper_clearance,
                "gripper_overlap": bool(gripper_clearance is not None and gripper_clearance < 0.0),
                "range_delta_from_nominal_mm": 0.0,
                "z_depth_delta_from_nominal_mm": 0.0,
                "projected_delta_from_nominal_px": 0.0,
                "translation_delta_x_m": float(perturbation.translation_delta_m[0]),
                "translation_delta_y_m": float(perturbation.translation_delta_m[1]),
                "translation_delta_z_m": float(perturbation.translation_delta_m[2]),
                "rotation_delta_x_deg": float(perturbation.rotation_delta_deg[0]),
                "rotation_delta_y_deg": float(perturbation.rotation_delta_deg[1]),
                "rotation_delta_z_deg": float(perturbation.rotation_delta_deg[2]),
                "risk_score": 0.0,
                "risk_status": "low",
                "risk_components": {},
                "limitations": SIMULATOR_ONLY_LIMITATIONS,
            }
            raw_rows.append(row)

    nominal_by_square = {
        str(row["square"]): row for row in raw_rows if row["perturbation_id"] == "nominal"
    }
    if len(nominal_by_square) != len(squares):
        raise AssertionError("Nominal depth/distance rows were not generated for every requested square.")

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        nominal = nominal_by_square[str(row["square"])]
        range_delta = float(row["camera_to_piece_proxy_range_mm"]) - float(
            nominal["camera_to_piece_proxy_range_mm"]
        )
        z_delta = float(row["camera_to_piece_proxy_z_depth_mm"]) - float(
            nominal["camera_to_piece_proxy_z_depth_mm"]
        )
        pixel_delta = math.hypot(
            float(row["piece_projected_x_px"]) - float(nominal["piece_projected_x_px"]),
            float(row["piece_projected_y_px"]) - float(nominal["piece_projected_y_px"]),
        )
        gripper_clearance = row.get("gripper_clearance_px")
        edge_risk = clipped_ratio(float(args.edge_risk_margin_px) - float(row["edge_margin_px"]), float(args.edge_risk_margin_px))
        gripper_risk = (
            clipped_ratio(float(args.gripper_risk_clearance_px) - float(gripper_clearance), float(args.gripper_risk_clearance_px))
            if isinstance(gripper_clearance, (int, float))
            else 0.0
        )
        range_risk = clipped_ratio(abs(range_delta), float(args.depth_risk_delta_mm))
        z_risk = clipped_ratio(abs(z_delta), float(args.depth_risk_delta_mm))
        pixel_risk = clipped_ratio(pixel_delta, float(args.pixel_risk_delta_px))
        risk = max(edge_risk, gripper_risk, range_risk, z_risk, pixel_risk)
        row = {
            **row,
            "range_delta_from_nominal_mm": range_delta,
            "z_depth_delta_from_nominal_mm": z_delta,
            "projected_delta_from_nominal_px": pixel_delta,
            "risk_score": risk,
            "risk_status": risk_status(risk),
            "risk_components": {
                "edge_margin": edge_risk,
                "gripper_clearance": gripper_risk,
                "range_delta": range_risk,
                "z_depth_delta": z_risk,
                "projected_pixel_delta": pixel_risk,
            },
        }
        rows.append(row)
    return rows, camera_contract or {}


def aggregate_by_square(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for square in sorted({str(row["square"]) for row in rows}, key=lambda value: (int(value[1]), value[0])):
        square_rows = [row for row in rows if row["square"] == square]
        worst = max(square_rows, key=lambda row: float(row["risk_score"]))
        records.append(
            {
                "square": square,
                "file_idx": int(worst["file_idx"]),
                "rank_idx": int(worst["rank_idx"]),
                "max_risk_score": float(worst["risk_score"]),
                "risk_status": risk_status(float(worst["risk_score"])),
                "worst_perturbation_id": worst["perturbation_id"],
                "nominal_camera_to_piece_proxy_range_mm": next(
                    float(row["camera_to_piece_proxy_range_mm"])
                    for row in square_rows
                    if row["perturbation_id"] == "nominal"
                ),
                "max_abs_range_delta_mm": max(abs(float(row["range_delta_from_nominal_mm"])) for row in square_rows),
                "max_abs_z_depth_delta_mm": max(abs(float(row["z_depth_delta_from_nominal_mm"])) for row in square_rows),
                "max_projected_delta_px": max(float(row["projected_delta_from_nominal_px"]) for row in square_rows),
                "min_edge_margin_px": min(float(row["edge_margin_px"]) for row in square_rows),
                "min_gripper_clearance_px": min(
                    float(row["gripper_clearance_px"])
                    for row in square_rows
                    if isinstance(row.get("gripper_clearance_px"), (int, float))
                ),
            }
        )
    return sorted(records, key=lambda row: (-float(row["max_risk_score"]), str(row["square"])))


def aggregate_by_perturbation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    profile_order = {profile.profile_id: index for index, profile in enumerate(PERTURBATION_PROFILES)}
    for profile_id in sorted({str(row["perturbation_id"]) for row in rows}, key=lambda value: profile_order[value]):
        profile_rows = [row for row in rows if row["perturbation_id"] == profile_id]
        worst = max(profile_rows, key=lambda row: float(row["risk_score"]))
        records.append(
            {
                "perturbation_id": profile_id,
                "description": str(worst["perturbation_description"]),
                "max_risk_score": float(worst["risk_score"]),
                "risk_status": risk_status(float(worst["risk_score"])),
                "worst_square": worst["square"],
                "high_risk_square_count": sum(1 for row in profile_rows if row["risk_status"] == "high"),
                "medium_risk_square_count": sum(1 for row in profile_rows if row["risk_status"] == "medium"),
                "max_abs_range_delta_mm": max(abs(float(row["range_delta_from_nominal_mm"])) for row in profile_rows),
                "max_abs_z_depth_delta_mm": max(abs(float(row["z_depth_delta_from_nominal_mm"])) for row in profile_rows),
                "max_projected_delta_px": max(float(row["projected_delta_from_nominal_px"]) for row in profile_rows),
            }
        )
    return records


def color_for_risk(score: float) -> tuple[int, int, int]:
    clipped = float(np.clip(score, 0.0, 1.0))
    if clipped < 0.5:
        t = clipped / 0.5
        green = np.array([74, 156, 91], dtype=float)
        yellow = np.array([72, 205, 232], dtype=float)
        return tuple(int(value) for value in (green * (1.0 - t) + yellow * t))
    t = (clipped - 0.5) / 0.5
    yellow = np.array([72, 205, 232], dtype=float)
    red = np.array([68, 62, 218], dtype=float)
    return tuple(int(value) for value in (yellow * (1.0 - t) + red * t))


def put_text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    scale: float = 0.46,
    color: tuple[int, int, int] = (245, 245, 245),
    thickness: int = 1,
) -> None:
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def render_overview_png(
    *,
    path: Path,
    square_summary: list[dict[str, Any]],
    perturbation_summary: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    image = np.zeros((760, 1180, 3), dtype=np.uint8)
    image[:, :] = (34, 36, 34)
    put_text(image, "SO-101 Sim Depth/Distance Drill", (32, 34), scale=0.78, color=(255, 255, 255), thickness=2)
    put_text(
        image,
        "Risk combines edge margin, synthetic gripper clearance, depth/range delta, and projected pixel shift.",
        (32, 62),
        scale=0.43,
        color=(214, 226, 226),
    )

    square_by_name = {str(row["square"]): row for row in square_summary}
    board_x, board_y, cell = 42, 104, 58
    for rank_idx in range(7, -1, -1):
        for file_idx in range(8):
            square = f"{chr(ord('a') + file_idx)}{rank_idx + 1}"
            row = square_by_name.get(square)
            x = board_x + file_idx * cell
            y = board_y + (7 - rank_idx) * cell
            if row is None:
                color = (76, 78, 74) if (file_idx + rank_idx) % 2 == 0 else (54, 56, 53)
                score = None
            else:
                score = float(row["max_risk_score"])
                color = color_for_risk(score)
            cv2.rectangle(image, (x, y), (x + cell, y + cell), color, -1)
            cv2.rectangle(image, (x, y), (x + cell, y + cell), (25, 28, 25), 1)
            label_color = (255, 255, 255)
            put_text(image, square, (x + 6, y + 18), scale=0.40, color=label_color)
            if score is not None:
                put_text(image, f"{score:.2f}", (x + 8, y + 43), scale=0.42, color=label_color)

    legend_y = board_y + 8 * cell + 28
    put_text(image, "Board-square max risk", (board_x, board_y - 15), scale=0.52, color=(255, 255, 255))
    for index, (label, score) in enumerate((("low", 0.12), ("medium", 0.50), ("high", 0.88))):
        x = board_x + index * 130
        cv2.rectangle(image, (x, legend_y), (x + 38, legend_y + 18), color_for_risk(score), -1)
        cv2.rectangle(image, (x, legend_y), (x + 38, legend_y + 18), (20, 20, 20), 1)
        put_text(image, label, (x + 48, legend_y + 15), scale=0.42)

    table_x, table_y = 560, 104
    put_text(image, "Pose perturbations", (table_x, table_y - 16), scale=0.56, color=(255, 255, 255))
    put_text(image, "profile", (table_x, table_y + 14), scale=0.40, color=(210, 220, 220))
    put_text(image, "risk", (table_x + 250, table_y + 14), scale=0.40, color=(210, 220, 220))
    put_text(image, "worst", (table_x + 338, table_y + 14), scale=0.40, color=(210, 220, 220))
    put_text(image, "range mm / px", (table_x + 430, table_y + 14), scale=0.40, color=(210, 220, 220))
    for index, row in enumerate(perturbation_summary):
        y = table_y + 38 + index * 42
        risk = float(row["max_risk_score"])
        cv2.rectangle(image, (table_x - 4, y - 22), (1138, y + 11), (45, 48, 46), -1)
        cv2.rectangle(image, (table_x + 246, y - 12), (table_x + 326, y + 4), (26, 28, 27), -1)
        cv2.rectangle(
            image,
            (table_x + 246, y - 12),
            (table_x + 246 + int(round(80.0 * min(1.0, risk))), y + 4),
            color_for_risk(risk),
            -1,
        )
        put_text(image, str(row["perturbation_id"])[:30], (table_x, y), scale=0.39)
        put_text(image, f"{risk:.2f}", (table_x + 330, y), scale=0.39)
        put_text(image, str(row["worst_square"]), (table_x + 385, y), scale=0.39)
        put_text(
            image,
            f"{float(row['max_abs_range_delta_mm']):.1f} / {float(row['max_projected_delta_px']):.1f}",
            (table_x + 462, y),
            scale=0.39,
        )

    top_y = 520
    put_text(image, "Top risky sampled squares", (table_x, top_y), scale=0.56, color=(255, 255, 255))
    for index, row in enumerate(square_summary[:6]):
        y = top_y + 30 + index * 29
        cv2.circle(image, (table_x + 8, y - 5), 7, color_for_risk(float(row["max_risk_score"])), -1)
        put_text(
            image,
            (
                f"{row['square']} {row['risk_status']} risk={float(row['max_risk_score']):.2f} "
                f"pose={row['worst_perturbation_id']} range_delta={float(row['max_abs_range_delta_mm']):.1f}mm "
                f"shift={float(row['max_projected_delta_px']):.1f}px"
            ),
            (table_x + 24, y),
            scale=0.39,
        )

    footer_y = 720
    put_text(
        image,
        f"rows={summary['row_count']} squares={summary['square_count']} profiles={summary['perturbation_profile_count']} "
        f"units=mm/px output={summary['output_dir']}",
        (32, footer_y),
        scale=0.40,
        color=(210, 220, 220),
    )
    write_image(path, image)


def build_summary(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    camera_contract: dict[str, Any],
    output_dir: Path,
    summary_path: Path,
    csv_path: Path,
    png_path: Path,
) -> dict[str, Any]:
    square_summary = aggregate_by_square(rows)
    perturbation_summary = aggregate_by_perturbation(rows)
    missing_paths = [str(path) for path in (csv_path, png_path) if not path.is_file()]
    ok = bool(rows) and not missing_paths
    return {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "profile": str(args.profile),
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "live_camera_skipped": True,
        "skipped_markers": {
            "hardware": "Depth/distance drill uses SimCamera metadata and does not connect to SO-101 motors or serial buses.",
            "camera": "No live capture device is opened; all projection rows are metadata-native simulator calculations.",
            "gui": "No OpenCV display, click calibration, or PySide UI path is invoked.",
            "openai": "No OpenAI or LLM flow is invoked.",
        },
        "deterministic": {
            "subprocesses": 0,
            "random_seed": None,
            "perturbation_profile_ids": [profile.profile_id for profile in PERTURBATION_PROFILES],
            "square_order": [validate_square(square) for square in args.squares],
        },
        "units": {
            "distance": "mm",
            "depth": "mm",
            "translation_delta": "m",
            "rotation_delta": "deg",
            "pixel": "px",
        },
        "thresholds": {
            "edge_risk_margin_px": float(args.edge_risk_margin_px),
            "gripper_risk_clearance_px": float(args.gripper_risk_clearance_px),
            "depth_risk_delta_mm": float(args.depth_risk_delta_mm),
            "pixel_risk_delta_px": float(args.pixel_risk_delta_px),
        },
        "piece_proxy": {
            "height_above_board_mm": float(args.piece_proxy_height_mm),
            "source": "configurable board-frame pickup/contact proxy point",
            "status": "simulator_proxy_not_physical_contact_measurement",
        },
        "gripper_proxy": {
            "grasp_percent": float(args.grasp_percent),
            "source": "SimCamera synthetic gripper overlay polygons",
            "status": "simulator_proxy_not_real_gripper_or_segmentation",
        },
        "camera_contract": camera_contract,
        "row_count": len(rows),
        "square_count": len({row["square"] for row in rows}),
        "perturbation_profile_count": len({row["perturbation_id"] for row in rows}),
        "paths": {
            "json": str(summary_path),
            "csv": str(csv_path),
            "png": str(png_path),
        },
        "missing_artifact_paths": missing_paths,
        "aggregate": {
            "max_risk_score": max(float(row["risk_score"]) for row in rows) if rows else None,
            "high_risk_row_count": sum(1 for row in rows if row["risk_status"] == "high"),
            "medium_risk_row_count": sum(1 for row in rows if row["risk_status"] == "medium"),
            "max_abs_range_delta_mm": max(abs(float(row["range_delta_from_nominal_mm"])) for row in rows) if rows else None,
            "max_abs_z_depth_delta_mm": max(abs(float(row["z_depth_delta_from_nominal_mm"])) for row in rows) if rows else None,
            "max_projected_delta_px": max(float(row["projected_delta_from_nominal_px"]) for row in rows) if rows else None,
            "min_edge_margin_px": min(float(row["edge_margin_px"]) for row in rows) if rows else None,
            "min_gripper_clearance_px": min(
                float(row["gripper_clearance_px"])
                for row in rows
                if isinstance(row.get("gripper_clearance_px"), (int, float))
            )
            if rows
            else None,
        },
        "top_risky_squares": square_summary[:8],
        "top_risky_pose_perturbations": sorted(
            perturbation_summary,
            key=lambda row: (-float(row["max_risk_score"]), str(row["perturbation_id"])),
        )[:8],
        "square_summary": square_summary,
        "perturbation_summary": perturbation_summary,
        "rows": rows,
        "limitations": SIMULATOR_ONLY_LIMITATIONS,
        "notes": [
            "Use this drill before hardware runs to identify board squares and pose perturbations that deserve closer visual review.",
            "The default sampled squares cover near-gripper rows, board center, file edges, and back rank.",
            "This script intentionally does not update canonical calibration constants or invoke the full evidence bundle.",
        ],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    squares = [validate_square(square) for square in args.squares]
    if not squares:
        raise ValueError("At least one --squares value is required.")
    if len(set(squares)) != len(squares):
        raise ValueError(f"--squares contains duplicates: {args.squares!r}")
    args.squares = squares

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "depth_distance_drill_summary.json"
    csv_path = output_dir / "depth_distance_drill_rows.csv"
    png_path = output_dir / "depth_distance_drill_heatmap.png"

    rows, camera_contract = evaluate_rows(args, squares)
    write_csv(csv_path, rows)
    provisional_summary = build_summary(
        args=args,
        rows=rows,
        camera_contract=camera_contract,
        output_dir=output_dir,
        summary_path=summary_path,
        csv_path=csv_path,
        png_path=png_path,
    )
    render_overview_png(
        path=png_path,
        square_summary=provisional_summary["square_summary"],
        perturbation_summary=provisional_summary["perturbation_summary"],
        summary=provisional_summary,
    )
    summary = build_summary(
        args=args,
        rows=rows,
        camera_contract=camera_contract,
        output_dir=output_dir,
        summary_path=summary_path,
        csv_path=csv_path,
        png_path=png_path,
    )
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return 0 if bool(summary["ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
