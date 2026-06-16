#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import json
import math
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SCHEMA = "lerobot.sim.ik_reachability_drill.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "ik_reachability_drill"
ROBOT_METADATA_PATH = REPO_ROOT / "src" / "lerobot" / "sim" / "robot.py"
MODEL_SUFFIXES = {".urdf", ".xml", ".mjcf", ".xacro"}
DEFAULT_BOARD_ORIGIN_BASE_M = (0.10, -0.175, 0.09)
DEFAULT_SQUARE_SIZE_M = 0.05
DEFAULT_MIN_RADIUS_M = 0.08
DEFAULT_MAX_RADIUS_M = 0.45
DEFAULT_MIN_Z_M = -0.10
DEFAULT_MAX_Z_M = 0.35
DEFAULT_MAX_EE_STEP_M = 0.05
IK_RESIDUAL_TOLERANCE_MM = 20.0

CSV_FIELDNAMES = (
    "command_id",
    "command_type",
    "source_waypoint",
    "square",
    "description",
    "target_x_m",
    "target_y_m",
    "target_z_m",
    "start_x_m",
    "start_y_m",
    "start_z_m",
    "delta_x_m",
    "delta_y_m",
    "delta_z_m",
    "delta_norm_m",
    "radial_radius_m",
    "radial_theta_deg",
    "estimated_pan_deg",
    "gripper",
    "envelope_feasible",
    "feasibility",
    "physical_ik_status",
    "violations",
    "violated_limits",
    "unknown_fields",
    "ik_residual_mm",
    "fk_residual_mm",
    "max_joint_limit_overrun_deg",
    "joint_solution_deg",
    "notes",
)


@dataclass(frozen=True)
class CommandSample:
    command_id: str
    command_type: str
    description: str
    target_xyz_m: tuple[float, float, float]
    source_waypoint: str
    square: str | None = None
    start_xyz_m: tuple[float, float, float] | None = None
    delta_xyz_m: tuple[float, float, float] | None = None
    radial_radius_m: float | None = None
    radial_theta_deg: float | None = None
    gripper: float | None = None
    joint_seed_deg: dict[str, float] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic, hardware-free SO-101 IK/reachability drill. "
            "When no repo-local kinematic model is available, the drill reports "
            "model_unavailable diagnostics and falls back to command-envelope and "
            "joint-limit checks without pretending true IK was solved."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Optional URDF path for a model-backed IK attempt. The fallback remains available without it.",
    )
    parser.add_argument(
        "--board-origin-base-m",
        nargs=3,
        type=float,
        default=list(DEFAULT_BOARD_ORIGIN_BASE_M),
        metavar=("X", "Y", "Z"),
        help=(
            "Synthetic board a1-corner origin in the robot base frame. This is a deterministic "
            "simulator proxy, not a physical calibration."
        ),
    )
    parser.add_argument("--square-size-m", type=float, default=DEFAULT_SQUARE_SIZE_M)
    parser.add_argument("--min-radius-m", type=float, default=DEFAULT_MIN_RADIUS_M)
    parser.add_argument("--max-radius-m", type=float, default=DEFAULT_MAX_RADIUS_M)
    parser.add_argument("--min-z-m", type=float, default=DEFAULT_MIN_Z_M)
    parser.add_argument("--max-z-m", type=float, default=DEFAULT_MAX_Z_M)
    parser.add_argument("--max-ee-step-m", type=float, default=DEFAULT_MAX_EE_STEP_M)
    parser.add_argument(
        "--target-frame",
        default="gripper_frame_link",
        help="URDF target frame to use only when a model-backed IK path is available.",
    )
    return parser.parse_args()


def load_sim_robot_metadata() -> dict[str, Any]:
    tree = ast.parse(ROBOT_METADATA_PATH.read_text())
    assignments: dict[str, Any] = {}
    desired_names = {"JOINT_LIMITS_DEG", "SO101_BODY_JOINTS", "DEFAULT_JOINT_POSITIONS_DEG"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in desired_names:
                    assignments[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in desired_names and node.value is not None:
                assignments[node.target.id] = ast.literal_eval(node.value)
    missing = {
        key
        for key in ("JOINT_LIMITS_DEG", "SO101_BODY_JOINTS", "DEFAULT_JOINT_POSITIONS_DEG")
        if key not in assignments
    }
    if missing:
        raise KeyError(f"Could not read simulator robot metadata from {ROBOT_METADATA_PATH}: {sorted(missing)}")
    body_joints = tuple(str(joint) for joint in assignments["SO101_BODY_JOINTS"])
    joint_limits = {
        str(name): (float(bounds[0]), float(bounds[1]))
        for name, bounds in assignments["JOINT_LIMITS_DEG"].items()
    }
    default_positions = {
        str(name): float(value) for name, value in assignments["DEFAULT_JOINT_POSITIONS_DEG"].items()
    }
    return {
        "source_path": str(ROBOT_METADATA_PATH),
        "body_joints": body_joints,
        "all_joints": (*body_joints, "gripper"),
        "joint_limits_deg": joint_limits,
        "default_joint_positions_deg": default_positions,
    }


def scan_model_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    skip_parts = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
    for path in sorted(REPO_ROOT.rglob("*")):
        if any(part in skip_parts for part in path.relative_to(REPO_ROOT).parts):
            continue
        if not path.is_file() or path.suffix.lower() not in MODEL_SUFFIXES:
            continue
        suffix = path.suffix.lower()
        candidates.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(REPO_ROOT)),
                "suffix": suffix,
                "kind": "urdf" if suffix == ".urdf" else "mujoco_xml" if suffix in {".xml", ".mjcf"} else "xacro",
                "usable_for_model_backed_ik": suffix == ".urdf",
            }
        )
    return candidates


def read_model_references() -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for path in (REPO_ROOT / "README.md", REPO_ROOT / "SO101_ROBOT_SPECIFICATIONS.md"):
        if not path.is_file():
            continue
        for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            lowered = line.lower()
            if ".urdf" in lowered or ".mjcf" in lowered or "mujoco" in lowered:
                references.append(
                    {
                        "path": str(path),
                        "line": line_no,
                        "text": line.strip(),
                    }
                )
    return references


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def inventory_kinematic_model(args: argparse.Namespace) -> dict[str, Any]:
    candidates = scan_model_candidates()
    explicit_model_path = args.model_path.expanduser() if args.model_path is not None else None
    explicit_record = None
    if explicit_model_path is not None:
        explicit_record = {
            "path": str(explicit_model_path),
            "exists": explicit_model_path.is_file(),
            "suffix": explicit_model_path.suffix.lower(),
            "usable_for_model_backed_ik": explicit_model_path.is_file()
            and explicit_model_path.suffix.lower() == ".urdf",
        }

    usable_urdfs = [candidate for candidate in candidates if candidate["usable_for_model_backed_ik"]]
    selected_path: str | None = None
    selected_source = None
    if explicit_record is not None and explicit_record["usable_for_model_backed_ik"]:
        selected_path = str(explicit_model_path)
        selected_source = "explicit_model_path"
    elif usable_urdfs:
        selected_path = str(REPO_ROOT / usable_urdfs[0]["relative_path"])
        selected_source = "repo_scan"

    if selected_path is None:
        status = "missing_model" if explicit_model_path is None else "model_unavailable"
        reason = (
            "No repo-local SO-101 URDF/MuJoCo/xacro model source was found."
            if not candidates
            else "Model source exists, but no direct URDF candidate is available for RobotKinematics IK."
        )
        if explicit_record is not None and not explicit_record["exists"]:
            reason = f"Explicit model path does not exist: {explicit_model_path}"
    else:
        status = "model_candidate_found"
        reason = "A URDF candidate is available for an optional model-backed IK attempt."

    return {
        "status": status,
        "reason": reason,
        "selected_model_path": selected_path,
        "selected_model_source": selected_source,
        "repo_local_model_count": len(candidates),
        "repo_local_candidates": candidates,
        "explicit_model_path": explicit_record,
        "readme_or_spec_references": read_model_references(),
        "import_status": {
            "placo": module_available("placo"),
            "mujoco": module_available("mujoco"),
        },
        "checked_suffixes": sorted(MODEL_SUFFIXES),
        "model_backed_ik_requires": [
            "repo-local SO-101 URDF readable by placo.RobotWrapper",
            "target frame name such as gripper_frame_link",
            "joint name order matching simulator/body joints",
        ],
    }


def validate_finite_vector(values: tuple[float, ...], *, label: str) -> tuple[float, ...]:
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError(f"{label} must contain only finite numeric values: {values!r}")
    return tuple(float(value) for value in values)


def square_to_file_rank(square: str) -> tuple[int, int]:
    value = square.lower().strip()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square {square!r}; expected a1 through h8.")
    return ord(value[0]) - ord("a"), int(value[1]) - 1


def square_center_base_m(
    square: str,
    *,
    board_origin_base_m: tuple[float, float, float],
    square_size_m: float,
    z_offset_m: float = 0.0,
) -> tuple[float, float, float]:
    file_idx, rank_idx = square_to_file_rank(square)
    return (
        board_origin_base_m[0] + (file_idx + 0.5) * square_size_m,
        board_origin_base_m[1] + (rank_idx + 0.5) * square_size_m,
        board_origin_base_m[2] + z_offset_m,
    )


def radial_target(radius_m: float, theta_deg: float, z_m: float) -> tuple[float, float, float]:
    theta = math.radians(theta_deg)
    return (radius_m * math.cos(theta), radius_m * math.sin(theta), z_m)


def vector_add(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def build_command_samples(args: argparse.Namespace, metadata: dict[str, Any]) -> list[CommandSample]:
    board_origin = validate_finite_vector(tuple(args.board_origin_base_m), label="--board-origin-base-m")
    square_size_m = float(args.square_size_m)
    if not math.isfinite(square_size_m) or square_size_m <= 0.0:
        raise ValueError("--square-size-m must be a positive finite value.")

    default_positions = dict(metadata["default_joint_positions_deg"])
    e4_hover = square_center_base_m(
        "e4", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=0.075
    )
    d4_hover = square_center_base_m(
        "d4", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=0.075
    )
    d4_grasp = square_center_base_m(
        "d4", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=0.028
    )
    a1_hover = square_center_base_m(
        "a1", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=0.060
    )
    h8_hover = square_center_base_m(
        "h8", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=0.060
    )
    a4_hover = square_center_base_m(
        "a4", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=0.065
    )

    e4_radius = math.hypot(e4_hover[0], e4_hover[1])
    e4_theta = math.degrees(math.atan2(e4_hover[1], e4_hover[0]))
    a4_radius = math.hypot(a4_hover[0], a4_hover[1])
    a4_theta = math.degrees(math.atan2(a4_hover[1], a4_hover[0]))

    return [
        CommandSample(
            command_id="absolute_e4_pick_hover",
            command_type="absolute_target",
            square="e4",
            source_waypoint="e4_piece_hover",
            description="Absolute hover above an e4 piece proxy.",
            target_xyz_m=e4_hover,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="absolute_d4_grasp_window",
            command_type="absolute_target",
            square="d4",
            source_waypoint="d4_grasp_window",
            description="Absolute lower grasp-window target over d4.",
            target_xyz_m=d4_grasp,
            gripper=18.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="absolute_a1_corner_hover",
            command_type="absolute_target",
            square="a1",
            source_waypoint="a1_corner_hover",
            description="Absolute hover at the near a1 board corner.",
            target_xyz_m=a1_hover,
            gripper=40.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="absolute_h8_far_corner_hover",
            command_type="absolute_target",
            square="h8",
            source_waypoint="h8_far_corner_hover",
            description="Absolute hover at the far h8 board corner.",
            target_xyz_m=h8_hover,
            gripper=40.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="absolute_near_base_dead_zone",
            command_type="absolute_target",
            square=None,
            source_waypoint="near_base_probe",
            description="Synthetic near-base target that should trip the radial dead-zone envelope.",
            target_xyz_m=(0.045, 0.0, board_origin[2] + 0.055),
            gripper=30.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="absolute_below_board_probe",
            command_type="absolute_target",
            square="e4",
            source_waypoint="e4_below_board_probe",
            description="Synthetic below-board target that should trip the z envelope.",
            target_xyz_m=square_center_base_m(
                "e4", board_origin_base_m=board_origin, square_size_m=square_size_m, z_offset_m=-0.210
            ),
            gripper=30.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="absolute_over_height_probe",
            command_type="absolute_target",
            square="d4",
            source_waypoint="d4_over_height_probe",
            description="Synthetic high target that should trip the z envelope.",
            target_xyz_m=(d4_hover[0], d4_hover[1], 0.390),
            gripper=30.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="delta_e4_file_step_20mm",
            command_type="delta_xyz",
            square="e4",
            source_waypoint="e4_piece_hover",
            description="Small +x policy delta from e4 hover.",
            start_xyz_m=e4_hover,
            delta_xyz_m=(0.020, 0.0, 0.0),
            target_xyz_m=vector_add(e4_hover, (0.020, 0.0, 0.0)),
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="delta_e4_rank_up_lift_32mm",
            command_type="delta_xyz",
            square="e4",
            source_waypoint="e4_piece_hover",
            description="Small diagonal rank/lift delta from e4 hover.",
            start_xyz_m=e4_hover,
            delta_xyz_m=(0.0, 0.020, 0.025),
            target_xyz_m=vector_add(e4_hover, (0.0, 0.020, 0.025)),
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="delta_e4_large_policy_step_90mm",
            command_type="delta_xyz",
            square="e4",
            source_waypoint="e4_piece_hover",
            description="Large single-step policy delta that exceeds the EE step clamp default.",
            start_xyz_m=e4_hover,
            delta_xyz_m=(0.090, 0.0, 0.0),
            target_xyz_m=vector_add(e4_hover, (0.090, 0.0, 0.0)),
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="delta_d4_drop_toward_piece_65mm",
            command_type="delta_xyz",
            square="d4",
            source_waypoint="d4_piece_hover",
            description="Downward delta from d4 hover that exceeds the EE step clamp default.",
            start_xyz_m=d4_hover,
            delta_xyz_m=(0.0, 0.0, -0.065),
            target_xyz_m=vector_add(d4_hover, (0.0, 0.0, -0.065)),
            gripper=24.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="delta_h8_lateral_escape_72mm",
            command_type="delta_xyz",
            square="h8",
            source_waypoint="h8_far_corner_hover",
            description="Large h8 escape delta combining a far board target with excessive step size.",
            start_xyz_m=h8_hover,
            delta_xyz_m=(0.060, 0.040, 0.0),
            target_xyz_m=vector_add(h8_hover, (0.060, 0.040, 0.0)),
            gripper=40.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="radial_e4_hover",
            command_type="radial",
            square="e4",
            source_waypoint="e4_radial_hover",
            description="Radial command matching the synthetic e4 hover bearing.",
            target_xyz_m=radial_target(e4_radius, e4_theta, e4_hover[2]),
            radial_radius_m=e4_radius,
            radial_theta_deg=e4_theta,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="radial_a4_left_edge_hover",
            command_type="radial",
            square="a4",
            source_waypoint="a4_radial_hover",
            description="Radial command matching the synthetic a4 left-edge bearing.",
            target_xyz_m=radial_target(a4_radius, a4_theta, a4_hover[2]),
            radial_radius_m=a4_radius,
            radial_theta_deg=a4_theta,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="radial_e4_outward_30mm",
            command_type="radial",
            square="e4",
            source_waypoint="e4_radial_outward",
            description="Radial outward command near e4 by 30 mm.",
            target_xyz_m=radial_target(e4_radius + 0.030, e4_theta, e4_hover[2]),
            radial_radius_m=e4_radius + 0.030,
            radial_theta_deg=e4_theta,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="radial_pan_over_limit",
            command_type="radial",
            square=None,
            source_waypoint="pan_limit_probe",
            description="Radial command whose bearing exceeds the shoulder_pan joint limit metadata.",
            target_xyz_m=radial_target(0.300, 125.0, e4_hover[2]),
            radial_radius_m=0.300,
            radial_theta_deg=125.0,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="radial_radius_too_far",
            command_type="radial",
            square=None,
            source_waypoint="radius_limit_probe",
            description="Radial command beyond the documented SO-101 fallback reach envelope.",
            target_xyz_m=radial_target(0.520, 22.0, e4_hover[2]),
            radial_radius_m=0.520,
            radial_theta_deg=22.0,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
        CommandSample(
            command_id="radial_radius_too_close",
            command_type="radial",
            square=None,
            source_waypoint="near_base_radial_probe",
            description="Radial command inside the documented SO-101 fallback dead-zone envelope.",
            target_xyz_m=radial_target(0.055, 0.0, e4_hover[2]),
            radial_radius_m=0.055,
            radial_theta_deg=0.0,
            gripper=35.0,
            joint_seed_deg=default_positions,
        ),
    ]


def jsonable_float(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return value


def limit_overrun(value: float, lower: float, upper: float) -> float:
    if value < lower:
        return lower - value
    if value > upper:
        return value - upper
    return 0.0


def check_joint_limits(
    values_deg: dict[str, float],
    joint_limits_deg: dict[str, tuple[float, float]],
) -> tuple[list[dict[str, Any]], float]:
    violations: list[dict[str, Any]] = []
    max_overrun = 0.0
    for joint, value in sorted(values_deg.items()):
        if joint not in joint_limits_deg:
            continue
        lower, upper = joint_limits_deg[joint]
        overrun = limit_overrun(float(value), lower, upper)
        max_overrun = max(max_overrun, overrun)
        if overrun > 0.0:
            violations.append(
                {
                    "joint": joint,
                    "value_deg": float(value),
                    "limit_deg": [lower, upper],
                    "overrun_deg": overrun,
                }
            )
    return violations, max_overrun


def try_load_model_solver(
    inventory: dict[str, Any],
    metadata: dict[str, Any],
    *,
    target_frame: str,
) -> tuple[Any | None, dict[str, Any]]:
    selected = inventory.get("selected_model_path")
    if not selected:
        return None, {
            "available": False,
            "status": inventory["status"],
            "reason": inventory["reason"],
        }
    path = Path(str(selected))
    if path.suffix.lower() != ".urdf":
        return None, {
            "available": False,
            "status": "model_unavailable",
            "reason": f"Selected model is not a URDF supported by RobotKinematics: {path}",
        }
    if not path.is_file():
        return None, {
            "available": False,
            "status": "model_unavailable",
            "reason": f"Selected URDF path does not exist: {path}",
        }
    try:
        from lerobot.model.kinematics import RobotKinematics

        solver = RobotKinematics(
            str(path),
            target_frame_name=target_frame,
            joint_names=list(metadata["body_joints"]),
        )
    except Exception as exc:
        return None, {
            "available": False,
            "status": "model_unavailable",
            "reason": f"Failed to initialize RobotKinematics from {path}: {type(exc).__name__}: {exc}",
        }
    return solver, {
        "available": True,
        "status": "model_available",
        "model_path": str(path),
        "target_frame": target_frame,
        "joint_names": list(metadata["body_joints"]),
    }


def run_model_ik(
    solver: Any,
    command: CommandSample,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    try:
        import numpy as np
    except Exception as exc:
        return {
            "physical_ik_status": "model_unavailable",
            "model_error": f"numpy unavailable for model-backed IK: {type(exc).__name__}: {exc}",
        }

    body_joints = list(metadata["body_joints"])
    default_positions = metadata["default_joint_positions_deg"]
    q_current = np.array([float(default_positions[name]) for name in body_joints], dtype=float)
    target_pose = np.eye(4, dtype=float)
    target_pose[:3, 3] = np.array(command.target_xyz_m, dtype=float)
    try:
        q_target = solver.inverse_kinematics(
            q_current,
            target_pose,
            position_weight=1.0,
            orientation_weight=0.0,
        )
        fk_pose = solver.forward_kinematics(q_target)
        residual_mm = float(np.linalg.norm(fk_pose[:3, 3] - target_pose[:3, 3]) * 1000.0)
    except Exception as exc:
        return {
            "physical_ik_status": "ik_error",
            "model_error": f"{type(exc).__name__}: {exc}",
        }
    joint_solution = {joint: float(q_target[index]) for index, joint in enumerate(body_joints)}
    joint_violations, max_overrun = check_joint_limits(joint_solution, metadata["joint_limits_deg"])
    return {
        "physical_ik_status": "model_ik_solved" if residual_mm <= IK_RESIDUAL_TOLERANCE_MM else "model_ik_residual_high",
        "ik_residual_mm": residual_mm,
        "fk_residual_mm": residual_mm,
        "joint_solution_deg": joint_solution,
        "model_joint_limit_violations": joint_violations,
        "model_joint_limit_max_overrun_deg": max_overrun,
    }


def evaluate_command(
    command: CommandSample,
    *,
    args: argparse.Namespace,
    metadata: dict[str, Any],
    model_solver: Any | None,
    model_status: dict[str, Any],
) -> dict[str, Any]:
    target = validate_finite_vector(command.target_xyz_m, label=f"{command.command_id}.target_xyz_m")
    start = (
        validate_finite_vector(command.start_xyz_m, label=f"{command.command_id}.start_xyz_m")
        if command.start_xyz_m is not None
        else None
    )
    delta = (
        validate_finite_vector(command.delta_xyz_m, label=f"{command.command_id}.delta_xyz_m")
        if command.delta_xyz_m is not None
        else None
    )

    radius_m = math.hypot(target[0], target[1])
    estimated_pan_deg = math.degrees(math.atan2(target[1], target[0])) if radius_m > 1e-12 else 0.0
    delta_norm_m = math.sqrt(sum(value * value for value in delta)) if delta is not None else None

    violations: list[dict[str, Any]] = []
    if radius_m < float(args.min_radius_m):
        violations.append(
            {
                "field": "radial_distance_m",
                "violation": "below_min_radius",
                "value": radius_m,
                "limit": float(args.min_radius_m),
            }
        )
    if radius_m > float(args.max_radius_m):
        violations.append(
            {
                "field": "radial_distance_m",
                "violation": "above_max_radius",
                "value": radius_m,
                "limit": float(args.max_radius_m),
            }
        )
    if target[2] < float(args.min_z_m):
        violations.append(
            {
                "field": "target_z_m",
                "violation": "below_min_z",
                "value": target[2],
                "limit": float(args.min_z_m),
            }
        )
    if target[2] > float(args.max_z_m):
        violations.append(
            {
                "field": "target_z_m",
                "violation": "above_max_z",
                "value": target[2],
                "limit": float(args.max_z_m),
            }
        )
    if delta_norm_m is not None and delta_norm_m > float(args.max_ee_step_m):
        violations.append(
            {
                "field": "delta_norm_m",
                "violation": "above_max_ee_step",
                "value": delta_norm_m,
                "limit": float(args.max_ee_step_m),
            }
        )
    if start is not None and delta is not None:
        expected_target = (start[0] + delta[0], start[1] + delta[1], start[2] + delta[2])
        mismatch = math.sqrt(sum((target[index] - expected_target[index]) ** 2 for index in range(3)))
        if mismatch > 1e-9:
            violations.append(
                {
                    "field": "target_xyz_m",
                    "violation": "delta_target_mismatch",
                    "value": mismatch,
                    "limit": 1e-9,
                }
            )

    proxy_joint_values = {"shoulder_pan": estimated_pan_deg}
    if command.gripper is not None:
        proxy_joint_values["gripper"] = float(command.gripper)
    if command.joint_seed_deg:
        proxy_joint_values.update({name: float(value) for name, value in command.joint_seed_deg.items()})
        proxy_joint_values["shoulder_pan_target_bearing_proxy"] = estimated_pan_deg

    # Check bearing against shoulder_pan explicitly because the seed shoulder_pan may be valid.
    joint_limit_input = dict(command.joint_seed_deg or {})
    joint_limit_input["shoulder_pan"] = estimated_pan_deg
    if command.gripper is not None:
        joint_limit_input["gripper"] = float(command.gripper)
    joint_violations, max_joint_overrun = check_joint_limits(joint_limit_input, metadata["joint_limits_deg"])
    for violation in joint_violations:
        violations.append(
            {
                "field": f"joint_limit_deg.{violation['joint']}",
                "violation": "joint_limit_exceeded",
                **violation,
            }
        )

    physical_ik_status = "model_unavailable"
    ik_residual_mm = None
    fk_residual_mm = None
    joint_solution_deg = None
    notes: list[str] = []
    unknown_fields = [
        "joint_solution_deg",
        "ik_residual_mm",
        "fk_residual_mm",
        "true_cartesian_reachability",
        "link_collision",
        "self_collision",
        "tcp_offset",
        "torque_margin",
    ]

    if model_solver is not None and model_status.get("available"):
        model_result = run_model_ik(model_solver, command, metadata)
        physical_ik_status = str(model_result.get("physical_ik_status", "ik_error"))
        ik_residual_mm = model_result.get("ik_residual_mm")
        fk_residual_mm = model_result.get("fk_residual_mm")
        joint_solution_deg = model_result.get("joint_solution_deg")
        max_joint_overrun = max(
            max_joint_overrun,
            float(model_result.get("model_joint_limit_max_overrun_deg") or 0.0),
        )
        for violation in model_result.get("model_joint_limit_violations") or []:
            violations.append(
                {
                    "field": f"model_joint_solution_deg.{violation['joint']}",
                    "violation": "joint_limit_exceeded",
                    **violation,
                }
            )
        if physical_ik_status in {"model_ik_solved", "model_ik_residual_high"}:
            unknown_fields = ["link_collision", "self_collision", "tcp_offset", "torque_margin"]
        else:
            notes.append(str(model_result.get("model_error", "model-backed IK did not produce a solution")))
    else:
        notes.append(
            "No usable SO-101 model is available, so this row is envelope-only and not physical IK truth."
        )

    envelope_feasible = not violations
    if violations:
        feasibility = "blocked"
    elif physical_ik_status == "model_ik_solved" and max_joint_overrun <= 0.0:
        feasibility = "feasible_model_solved"
    elif physical_ik_status == "model_ik_residual_high":
        feasibility = "blocked_model_ik_residual"
    elif physical_ik_status == "ik_error":
        feasibility = "unknown_model_error"
    else:
        feasibility = "unknown_model_unavailable"

    return {
        "command_id": command.command_id,
        "command_type": command.command_type,
        "source_waypoint": command.source_waypoint,
        "square": command.square,
        "description": command.description,
        "target_x_m": target[0],
        "target_y_m": target[1],
        "target_z_m": target[2],
        "start_x_m": start[0] if start is not None else None,
        "start_y_m": start[1] if start is not None else None,
        "start_z_m": start[2] if start is not None else None,
        "delta_x_m": delta[0] if delta is not None else None,
        "delta_y_m": delta[1] if delta is not None else None,
        "delta_z_m": delta[2] if delta is not None else None,
        "delta_norm_m": delta_norm_m,
        "radial_radius_m": jsonable_float(command.radial_radius_m) if command.radial_radius_m is not None else radius_m,
        "radial_theta_deg": jsonable_float(command.radial_theta_deg)
        if command.radial_theta_deg is not None
        else estimated_pan_deg,
        "estimated_pan_deg": estimated_pan_deg,
        "gripper": command.gripper,
        "envelope_feasible": envelope_feasible,
        "feasibility": feasibility,
        "physical_ik_status": physical_ik_status,
        "violations": violations,
        "violated_limits": joint_violations,
        "unknown_fields": unknown_fields,
        "ik_residual_mm": ik_residual_mm,
        "fk_residual_mm": fk_residual_mm,
        "max_joint_limit_overrun_deg": max_joint_overrun,
        "joint_solution_deg": joint_solution_deg,
        "notes": notes,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in CSV_FIELDNAMES})


def png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def write_rgb_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    if len(pixels) != width * height * 3:
        raise ValueError("RGB pixel buffer size does not match image dimensions.")
    scanlines = bytearray()
    stride = width * 3
    for y in range(height):
        scanlines.append(0)
        start = y * stride
        scanlines.extend(pixels[start : start + stride])
    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)),
            png_chunk(b"IEND", b""),
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def draw_rect(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    for y in range(y0, y1):
        row = y * width * 3
        for x in range(x0, x1):
            offset = row + x * 3
            pixels[offset : offset + 3] = bytes(color)


def draw_circle(
    pixels: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    rr = radius * radius
    for y in range(max(0, cy - radius), min(height, cy + radius + 1)):
        for x in range(max(0, cx - radius), min(width, cx + radius + 1)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= rr:
                offset = (y * width + x) * 3
                pixels[offset : offset + 3] = bytes(color)


def feasibility_color(status: str) -> tuple[int, int, int]:
    if status == "blocked":
        return (207, 72, 72)
    if status == "feasible_model_solved":
        return (65, 160, 89)
    if status.startswith("unknown"):
        return (92, 132, 194)
    return (196, 154, 68)


def worst_status(statuses: list[str]) -> str:
    if "blocked" in statuses:
        return "blocked"
    if any(status.startswith("unknown") for status in statuses):
        return "unknown_model_unavailable"
    if "feasible_model_solved" in statuses:
        return "feasible_model_solved"
    return statuses[0] if statuses else "unknown_model_unavailable"


def render_heatmap_png(path: Path, rows: list[dict[str, Any]]) -> None:
    width, height = 620, 500
    pixels = bytearray([34, 36, 38] * width * height)
    board_x, board_y, cell = 42, 44, 50
    rows_by_square: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        square = row.get("square")
        if isinstance(square, str) and square:
            rows_by_square.setdefault(square, []).append(row)

    for rank_idx in range(8):
        for file_idx in range(8):
            square = f"{chr(ord('a') + file_idx)}{rank_idx + 1}"
            y = board_y + (7 - rank_idx) * cell
            x = board_x + file_idx * cell
            base = (221, 216, 203) if (file_idx + rank_idx) % 2 == 0 else (116, 128, 118)
            square_rows = rows_by_square.get(square, [])
            if square_rows:
                status = worst_status([str(row["feasibility"]) for row in square_rows])
                color = feasibility_color(status)
                mixed = tuple(int(base[index] * 0.35 + color[index] * 0.65) for index in range(3))
            else:
                mixed = base
            draw_rect(pixels, width, height, x, y, x + cell - 2, y + cell - 2, mixed)

    # Off-board command samples, arranged as a compact status strip.
    strip_x, strip_y = 480, 52
    for idx, row in enumerate([row for row in rows if not row.get("square")]):
        x = strip_x + (idx % 3) * 34
        y = strip_y + (idx // 3) * 34
        draw_rect(pixels, width, height, x, y, x + 24, y + 24, feasibility_color(str(row["feasibility"])))

    # Minimal legend: green/blue/red boxes in a fixed order.
    legend_y = 414
    for idx, status in enumerate(("feasible_model_solved", "unknown_model_unavailable", "blocked")):
        draw_rect(
            pixels,
            width,
            height,
            44 + idx * 70,
            legend_y,
            92 + idx * 70,
            legend_y + 28,
            feasibility_color(status),
        )
    write_rgb_png(path, width, height, pixels)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_status[str(row["feasibility"])] = by_status.get(str(row["feasibility"]), 0) + 1
        by_type[str(row["command_type"])] = by_type.get(str(row["command_type"]), 0) + 1
    blocked_rows = [row for row in rows if row["feasibility"] == "blocked"]
    return {
        "row_count": len(rows),
        "counts_by_feasibility": by_status,
        "counts_by_command_type": by_type,
        "blocked_command_ids": [str(row["command_id"]) for row in blocked_rows],
        "unknown_model_unavailable_command_ids": [
            str(row["command_id"]) for row in rows if row["feasibility"] == "unknown_model_unavailable"
        ],
        "max_joint_limit_overrun_deg": max(float(row["max_joint_limit_overrun_deg"]) for row in rows),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_sim_robot_metadata()
    inventory = inventory_kinematic_model(args)
    model_solver, model_status = try_load_model_solver(
        inventory,
        metadata,
        target_frame=str(args.target_frame),
    )

    commands = build_command_samples(args, metadata)
    rows = [
        evaluate_command(
            command,
            args=args,
            metadata=metadata,
            model_solver=model_solver,
            model_status=model_status,
        )
        for command in commands
    ]

    csv_path = output_dir / "ik_reachability_drill_rows.csv"
    png_path = output_dir / "ik_reachability_drill_heatmap.png"
    summary_path = output_dir / "ik_reachability_drill_summary.json"
    write_csv(csv_path, rows)
    render_heatmap_png(png_path, rows)

    row_summary = summarize(rows)
    status = (
        "ok_model_backed"
        if model_status.get("available")
        else "model_unavailable_fallback_complete"
    )
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "model_diagnostic": inventory,
        "model_solver": model_status,
        "fallback_command_envelope": {
            "source": "deterministic simulator proxy plus src/lerobot/sim/robot.py joint limits",
            "board_origin_base_m": [float(value) for value in args.board_origin_base_m],
            "square_size_m": float(args.square_size_m),
            "min_radius_m": float(args.min_radius_m),
            "max_radius_m": float(args.max_radius_m),
            "min_z_m": float(args.min_z_m),
            "max_z_m": float(args.max_z_m),
            "max_ee_step_m": float(args.max_ee_step_m),
            "ik_truth_when_model_unavailable": (
                "unknown_model_unavailable rows passed only envelope/joint-limit checks; "
                "they are not proven physically reachable."
            ),
        },
        "joint_metadata": metadata,
        "summary": row_summary,
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(csv_path),
            "heatmap_png": str(png_path),
        },
        "rows": rows,
        "next_model_inputs_needed": [
            "Repo-local SO-101 URDF or MuJoCo/MJCF source with calibrated link lengths and joint axes.",
            "End-effector target frame name and TCP/gripper-tip offset used for chess-piece contact.",
            "Verified simulator-to-real joint name/order mapping for shoulder_pan through wrist_roll and gripper.",
            "Calibrated T_base_board or equivalent board pose in the robot base frame.",
            "Collision geometry or conservative self/table/board collision checks.",
            "Residual thresholds from physical validation captures to distinguish reachable, marginal, and blocked commands.",
        ],
        "limitations": [
            "This script does not connect to motors, serial ports, cameras, GUI flows, OpenAI paths, or real robot execution.",
            "Fallback envelope checks are intentionally conservative proxies and do not replace model-backed IK/FK residuals.",
            "Bearing-to-shoulder_pan checks use target atan2 as a simple limit proxy, not as a solved joint action.",
            "The default board origin is a deterministic simulator proxy, not measured physical calibration.",
        ],
    }
    write_json(summary_path, summary)

    print(
        json.dumps(
            {
                "ok": True,
                "status": status,
                "row_count": row_summary["row_count"],
                "counts_by_feasibility": row_summary["counts_by_feasibility"],
                "model_status": inventory["status"],
                "summary_json": str(summary_path),
                "rows_csv": str(csv_path),
                "heatmap_png": str(png_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
