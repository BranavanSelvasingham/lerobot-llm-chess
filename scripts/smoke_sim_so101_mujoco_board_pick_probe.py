#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_board_pick_probe"
SUMMARY_NAME = "so101_mujoco_board_pick_probe_summary.json"
ROWS_NAME = "so101_mujoco_board_pick_probe_rows.csv"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.so101_mujoco_board_pick_probe.v1"
SOURCE_SQUARE = "e4"
TARGET_SQUARE = "e5"
CONTACT_FIXTURE_PIECE_RADIUS_M = 0.016
CONTACT_FIXTURE_PIECE_MASS_KG = 0.005
CONTACT_FIXTURE_CONDIM = 6
CONTACT_FIXTURE_FRICTION = (2.0, 0.4, 0.02)
CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M = -0.012
CONTACT_FIXTURE_GRIPPER_CLOSE_M = -0.008
CONTACT_FIXTURE_GRIPPER_KP = 200.0
DEVELOPMENT_MODEL_AUTHORITY = "development_scaffold_not_reviewed"
SOURCE_PAN_RAD = -0.1
TARGET_PAN_RAD = 0.07
LIFT_Z_THRESHOLD_M = 0.02
TARGET_XY_TOLERANCE_M = 0.01
SOURCE_PICK_XY_TOLERANCE_M = 0.02
PLACE_Z_TOLERANCE_M = 0.005
LOWER_JOINT_TARGETS = {
    "shoulder_lift": 0.0,
    "elbow_flex": 0.0,
    "wrist_flex": 0.0,
}
LIFT_JOINT_TARGETS = {
    "shoulder_lift": math.radians(-20.0),
    "elbow_flex": math.radians(10.0),
    "wrist_flex": math.radians(5.0),
}
NEXT_REQUIRED_FOR_GOAL = (
    {
        "priority": 1,
        "missing_input": "reviewed_so101_model_bundle",
        "action_id": "supply_reviewed_so101_model_bundle_manifest",
        "gate": "reviewed_model_authority",
        "title": "Replace generated scaffold with a reviewed SO-101 model bundle",
        "detail": "Supply a reviewed SO-101 URDF/MJCF bundle and mesh roots before treating board-source pickup as physical model truth.",
    },
    {
        "priority": 2,
        "missing_input": "reviewed_tcp_and_base_to_board_alignment",
        "action_id": "calibrate_reviewed_tcp_and_base_to_board_alignment",
        "gate": "reviewed_model_authority",
        "title": "Use reviewed TCP/gripper offset and base-to-board alignment",
        "detail": "Use reviewed TCP/gripper offset and base-to-board alignment for model-backed IK instead of seeded source-pose joint targets.",
    },
    {
        "priority": 3,
        "missing_input": "reviewed_model_backed_board_source_pick_place",
        "action_id": "repeat_board_pick_with_reviewed_model_backed_ik",
        "gate": "scripted_contact_grasp_pick_place",
        "title": "Repeat board-source pick/place with reviewed model-backed IK",
        "detail": "Repeat the board-source pick/place proof with calibrated gripper geometry before treating training rollouts as physical truth.",
    },
)


def next_required_action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [
        str(action["action_id"])
        for action in actions
        if isinstance(action, dict) and "action_id" in action
    ]


def next_required_action_sync_fields(
    *,
    next_required_for_goal: list[dict[str, Any]],
    explicit_action_ids: list[str],
) -> dict[str, Any]:
    derived_action_ids = next_required_action_ids(next_required_for_goal)
    return {
        "next_required_for_goal_action_ids": derived_action_ids,
        "next_required_action_ids_match_next_required": (
            explicit_action_ids == derived_action_ids
        ),
        "next_required_action_ids_missing_from_next_required": [
            action_id
            for action_id in explicit_action_ids
            if action_id not in derived_action_ids
        ],
        "next_required_actions_missing_from_action_ids": [
            action_id
            for action_id in derived_action_ids
            if action_id not in explicit_action_ids
        ],
    }


PICK_PLACE_PHASE_IDS = (
    "source_reset",
    "two_finger_grasp",
    "lift_clearance",
    "transfer_toward_target",
    "release_place",
)
REQUIRED_STAGE_SEQUENCE = (
    "source_reset_piece_on_board",
    "lower_open_at_source",
    "close_on_source_piece_forward",
    "close_on_source_piece_after_settle",
    "lift_from_source_without_manual_piece_pose",
    "transfer_to_target_without_manual_piece_pose",
    "lower_to_target_without_manual_piece_pose",
    "release_on_target_without_manual_piece_pose",
    "retreat_after_release_without_manual_piece_pose",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe board-source pick/place in the development SO-101 MuJoCo chess scene. "
            "This is a scaffold smoke, not reviewed model-backed IK evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-square", default=SOURCE_SQUARE)
    parser.add_argument("--target-square", default=TARGET_SQUARE)
    return parser.parse_args()


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def validate_square(square: str) -> None:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")


def task_configuration_error(args: argparse.Namespace) -> str | None:
    try:
        validate_square(args.source_square)
        validate_square(args.target_square)
    except ValueError as exc:
        return str(exc)
    if args.source_square.strip().lower() == args.target_square.strip().lower():
        return "piece_square and target_square must differ."
    return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stage",
        "sim_time_s",
        "piece_x",
        "piece_y",
        "piece_z",
        "site_x",
        "site_y",
        "site_z",
        "gripper_qpos_m",
        "fixed_finger_contact_count",
        "moving_finger_contact_count",
        "gripper_contact_count",
        "board_contact_count",
        "any_contact_count",
        "piece_z_delta_m",
        "source_xy_error_m",
        "target_xy_error_m",
        "source_to_target_progress_m",
        "manual_piece_pose_set",
        "ok",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def object_id(module: Any, model: Any, kind: Any, name: str) -> int:
    object_id_value = module.mj_name2id(model, kind, name)
    if object_id_value < 0:
        raise AssertionError(f"{name} is missing from generated model.")
    return int(object_id_value)


def joint_qpos_addr(module: Any, model: Any, joint_name: str) -> int:
    joint_id = object_id(module, model, module.mjtObj.mjOBJ_JOINT, joint_name)
    return int(model.jnt_qposadr[joint_id])


def joint_qpos(module: Any, model: Any, data: Any, joint_name: str) -> float:
    return float(data.qpos[joint_qpos_addr(module, model, joint_name)])


def set_joint_qpos(module: Any, model: Any, data: Any, joint_name: str, value: float) -> None:
    data.qpos[joint_qpos_addr(module, model, joint_name)] = float(value)


def actuator_id(module: Any, model: Any, actuator_name: str) -> int | None:
    actuator = module.mj_name2id(model, module.mjtObj.mjOBJ_ACTUATOR, actuator_name)
    return int(actuator) if actuator >= 0 else None


def set_actuator_target(module: Any, model: Any, data: Any, actuator_name: str, value: float) -> None:
    actuator = actuator_id(module, model, actuator_name)
    if actuator is not None:
        data.ctrl[actuator] = float(value)


def set_freejoint_pose(
    module: Any,
    model: Any,
    data: Any,
    joint_name: str,
    *,
    pos: tuple[float, float, float],
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
) -> None:
    qpos_addr = joint_qpos_addr(module, model, joint_name)
    data.qpos[qpos_addr : qpos_addr + 7] = [*pos, *quat]


def site_position(module: Any, model: Any, data: Any, site_name: str) -> tuple[float, float, float]:
    site_id = object_id(module, model, module.mjtObj.mjOBJ_SITE, site_name)
    values = data.site_xpos[site_id]
    return float(values[0]), float(values[1]), float(values[2])


def body_position(module: Any, model: Any, data: Any, body_name: str) -> tuple[float, float, float]:
    body_id = object_id(module, model, module.mjtObj.mjOBJ_BODY, body_name)
    values = data.xpos[body_id]
    return float(values[0]), float(values[1]), float(values[2])


def contact_counts(module: Any, model: Any, data: Any) -> dict[str, int]:
    piece_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "piece_source_collision")
    fixed_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "gripper_fixed_finger_collision")
    moving_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "gripper_moving_finger_collision")
    board_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "chess_board_collision")
    fixed = 0
    moving = 0
    board = 0
    for index in range(data.ncon):
        contact = data.contact[index]
        pair = {int(contact.geom1), int(contact.geom2)}
        if pair == {piece_id, fixed_id}:
            fixed += 1
        if pair == {piece_id, moving_id}:
            moving += 1
        if pair == {piece_id, board_id}:
            board += 1
    return {
        "fixed_finger_contact_count": fixed,
        "moving_finger_contact_count": moving,
        "gripper_contact_count": fixed + moving,
        "board_contact_count": board,
        "any_contact_count": int(data.ncon),
    }


def step(module: Any, model: Any, data: Any, steps: int) -> None:
    for _ in range(steps):
        module.mj_step(model, data)


def set_robot_pose(
    module: Any,
    model: Any,
    data: Any,
    *,
    shoulder_pan: float,
    joint_targets: dict[str, float],
    gripper: float,
) -> None:
    values = {"shoulder_pan": shoulder_pan, **joint_targets, "gripper": gripper}
    for joint, value in values.items():
        set_joint_qpos(module, model, data, joint, value)
        set_actuator_target(module, model, data, f"{joint}_actuator", value)


def set_robot_targets(
    module: Any,
    model: Any,
    data: Any,
    *,
    shoulder_pan: float,
    joint_targets: dict[str, float],
    gripper: float,
) -> None:
    set_actuator_target(module, model, data, "shoulder_pan_actuator", shoulder_pan)
    for joint, value in joint_targets.items():
        set_actuator_target(module, model, data, f"{joint}_actuator", value)
    set_actuator_target(module, model, data, "gripper_actuator", gripper)


def record_stage(
    module: Any,
    model: Any,
    data: Any,
    *,
    stage: str,
    manual_piece_pose_set: bool,
    initial_piece_z: float,
    source_xy: tuple[float, float],
    target_xy: tuple[float, float],
) -> dict[str, Any]:
    piece = body_position(module, model, data, "piece_source")
    site = site_position(module, model, data, "gripper_frame_link")
    contacts = contact_counts(module, model, data)
    source_xy_error = math.hypot(piece[0] - source_xy[0], piece[1] - source_xy[1])
    target_xy_error = math.hypot(piece[0] - target_xy[0], piece[1] - target_xy[1])
    source_to_target_progress = math.hypot(piece[0] - source_xy[0], piece[1] - source_xy[1])
    return {
        "stage": stage,
        "sim_time_s": float(data.time),
        "piece_x": piece[0],
        "piece_y": piece[1],
        "piece_z": piece[2],
        "site_x": site[0],
        "site_y": site[1],
        "site_z": site[2],
        "gripper_qpos_m": joint_qpos(module, model, data, "gripper"),
        **contacts,
        "piece_z_delta_m": piece[2] - initial_piece_z,
        "source_xy_error_m": source_xy_error,
        "target_xy_error_m": target_xy_error,
        "source_to_target_progress_m": source_to_target_progress,
        "manual_piece_pose_set": manual_piece_pose_set,
        "ok": True,
    }


def row_by_stage(rows: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    for row in rows:
        if row.get("stage") == stage:
            return row
    raise AssertionError(f"Missing row for stage {stage!r}.")


def stage_sequence_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed = [str(row.get("stage")) for row in rows if row.get("stage") is not None]
    manual_pose_after_reset = [
        str(row.get("stage"))
        for row in rows[1:]
        if bool(row.get("manual_piece_pose_set", False))
    ]
    errors: list[str] = []
    if observed != list(REQUIRED_STAGE_SEQUENCE):
        errors.append("observed_stage_sequence_mismatch")
    if manual_pose_after_reset:
        errors.append("manual_piece_pose_after_reset_detected")
    return {
        "required_stage_sequence": list(REQUIRED_STAGE_SEQUENCE),
        "observed_stage_sequence": observed,
        "missing_stage_ids": [
            stage for stage in REQUIRED_STAGE_SEQUENCE if stage not in observed
        ],
        "unexpected_stage_ids": [
            stage for stage in observed if stage not in REQUIRED_STAGE_SEQUENCE
        ],
        "stage_sequence_order_ok": observed == list(REQUIRED_STAGE_SEQUENCE),
        "manual_piece_pose_after_reset_stage_ids": manual_pose_after_reset,
        "stage_sequence_contract_ok": not errors,
        "stage_sequence_contract_errors": errors,
    }


def phase_evidence_row(
    *,
    phase_id: str,
    stage: str,
    ok: bool,
    criteria: list[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "phase_id": phase_id,
        "stage": stage,
        "ok": bool(ok),
        "criteria": criteria,
        "metrics": metrics,
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 MuJoCo Board Pick Probe",
        "",
        "This smoke records board-source pick/place in the generated development MJCF scene.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Source square: `{summary.get('source_square')}`",
        f"- Target square: `{summary.get('target_square')}`",
        f"- Source pick started at source: `{summary.get('source_pick_started_at_source')}`",
        f"- Close two-finger contact observed: `{summary.get('close_two_finger_contact_observed')}`",
        f"- Lift verified: `{summary.get('lift_verified')}`",
        f"- Board contact cleared during lift: `{summary.get('board_contact_cleared_during_lift')}`",
        f"- Transfer verified: `{summary.get('transfer_verified')}`",
        f"- Lower contact retained before release: `{summary.get('lower_contact_retained_before_release')}`",
        f"- Place verified: `{summary.get('place_without_manual_piece_pose_verified')}`",
        f"- All required phases verified: `{summary.get('pick_place_all_required_phases_verified')}`",
        f"- Failed phase IDs: `{summary.get('pick_place_failed_phase_ids')}`",
        f"- Stage sequence contract OK: `{summary.get('stage_sequence_contract_ok')}`",
        f"- Manual pose after reset stage IDs: `{summary.get('manual_piece_pose_after_reset_stage_ids')}`",
        f"- Release contact cleared after retreat: `{summary.get('release_contact_cleared_after_retreat')}`",
        f"- Final target XY error m: `{summary.get('final_target_xy_error_m')}`",
        f"- Rows CSV: `{summary['artifacts']['rows_csv']}`",
        "",
        "The setup resets the free piece onto the source board square once, then leaves the piece free.",
        "The robot source pose is seeded in the development scaffold because reviewed model-backed IK is still missing.",
        "A true board-source pick/place result is development evidence only; reviewed SO-101 model authority remains required before serious policy training.",
    ]
    path.write_text("\n".join(lines) + "\n")


def missing_dependency_summary(args: argparse.Namespace, deps: dict[str, bool], missing: list[str]) -> dict[str, Any]:
    summary_path = args.output_dir / SUMMARY_NAME
    rows_path = args.output_dir / ROWS_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    readme_path = args.output_dir / README_NAME
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "missing_runtime_dependencies",
        "missing_dependencies": missing,
        "dependencies": deps,
        "probe_count": 0,
        "model_authority": None,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_square": args.source_square,
        "target_square": args.target_square,
        "source_pick_started_at_source": False,
        "close_two_finger_contact_observed": False,
        "lift_verified": False,
        "board_contact_cleared_during_lift": False,
        "transfer_verified": False,
        "place_without_manual_piece_pose_verified": False,
        "board_source_pick_place_verified": False,
        "lower_contact_retained_before_release": False,
        "lower_board_contact_observed_before_release": False,
        "lower_target_within_tolerance_before_release": False,
        "lower_place_z_within_tolerance_before_release": False,
        "lower_target_xy_error_m": None,
        "lower_place_z_error_m": None,
        "release_contact_cleared_after_retreat": False,
        "final_board_contact_observed": False,
        "manual_piece_pose_used_after_reset": False,
        "robot_pose_seeded_for_source_fixture": False,
        "final_target_xy_error_m": None,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
        "final_place_z_error_m": None,
        "place_z_tolerance_m": PLACE_Z_TOLERANCE_M,
        "pick_place_phase_evidence": [],
        "pick_place_phase_ids": [],
        "pick_place_failed_phase_ids": [],
        "pick_place_phase_count": 0,
        "pick_place_all_required_phases_verified": False,
        "required_stage_sequence": list(REQUIRED_STAGE_SEQUENCE),
        "observed_stage_sequence": [],
        "missing_stage_ids": list(REQUIRED_STAGE_SEQUENCE),
        "unexpected_stage_ids": [],
        "stage_sequence_order_ok": False,
        "manual_piece_pose_after_reset_stage_ids": [],
        "stage_sequence_contract_ok": False,
        "stage_sequence_contract_errors": ["not_run_missing_runtime_dependencies"],
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
    }


def invalid_task_summary(
    *,
    args: argparse.Namespace,
    deps: dict[str, bool],
    summary_path: Path,
    rows_path: Path,
    model_path: Path,
    manifest_path: Path,
    readme_path: Path,
    message: str,
) -> dict[str, Any]:
    next_required_for_goal = [
        {
            "priority": 1,
            "missing_input": "valid_board_pick_task_configuration",
            "action_id": "provide_valid_distinct_source_and_target_squares",
            "gate": "scripted_contact_grasp_pick_place",
            "title": "Provide valid distinct source and target board squares",
            "detail": "Use valid, distinct chess squares before generating the development board-pick probe.",
        }
    ]
    next_required_actions = next_required_action_ids(next_required_for_goal)
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "invalid_task_configuration",
        "dependencies": deps,
        "probe_count": 0,
        "model_authority": DEVELOPMENT_MODEL_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_square": args.source_square,
        "target_square": args.target_square,
        "configuration_error": {
            "type": "ValueError",
            "message": message,
        },
        "source_pick_started_at_source": False,
        "close_two_finger_contact_observed": False,
        "lift_verified": False,
        "board_contact_cleared_during_lift": False,
        "transfer_verified": False,
        "place_without_manual_piece_pose_verified": False,
        "board_source_pick_place_verified": False,
        "lower_contact_retained_before_release": False,
        "lower_board_contact_observed_before_release": False,
        "lower_target_within_tolerance_before_release": False,
        "lower_place_z_within_tolerance_before_release": False,
        "lower_target_xy_error_m": None,
        "lower_place_z_error_m": None,
        "release_contact_cleared_after_retreat": False,
        "final_board_contact_observed": False,
        "manual_piece_pose_used_after_reset": False,
        "robot_pose_seeded_for_source_fixture": False,
        "final_target_xy_error_m": None,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
        "final_place_z_error_m": None,
        "place_z_tolerance_m": PLACE_Z_TOLERANCE_M,
        "piece_reset_to_source_before_run": False,
        "pick_place_phase_evidence": [],
        "pick_place_phase_ids": [],
        "pick_place_failed_phase_ids": [],
        "pick_place_phase_count": 0,
        "pick_place_all_required_phases_verified": False,
        "required_stage_sequence": list(REQUIRED_STAGE_SEQUENCE),
        "observed_stage_sequence": [],
        "missing_stage_ids": list(REQUIRED_STAGE_SEQUENCE),
        "unexpected_stage_ids": [],
        "stage_sequence_order_ok": False,
        "manual_piece_pose_after_reset_stage_ids": [],
        "stage_sequence_contract_ok": False,
        "stage_sequence_contract_errors": ["not_run_invalid_task_configuration"],
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Invalid board-pick task configuration is recorded as a fail-closed probe artifact.",
            "No MuJoCo model generation, contact probe, grasp, lift, transfer, or release is attempted.",
            "This failure is hardware-free and does not claim physical SO-101 evidence.",
        ],
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": next_required_actions,
        "next_required_action_count": len(next_required_actions),
        **next_required_action_sync_fields(
            next_required_for_goal=next_required_for_goal,
            explicit_action_ids=next_required_actions,
        ),
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    deps = {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "mujoco": module_available("mujoco"),
    }
    summary_path = args.output_dir / SUMMARY_NAME
    rows_path = args.output_dir / ROWS_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    readme_path = args.output_dir / README_NAME
    missing = [name for name, available in deps.items() if not available]
    configuration_error = task_configuration_error(args)
    if configuration_error is not None:
        summary = invalid_task_summary(
            args=args,
            deps=deps,
            summary_path=summary_path,
            rows_path=rows_path,
            model_path=model_path,
            manifest_path=manifest_path,
            readme_path=readme_path,
            message=configuration_error,
        )
        write_json(summary_path, summary)
        write_rows(rows_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1
    if missing:
        summary = missing_dependency_summary(args, deps, missing)
        write_json(summary_path, summary)
        write_rows(rows_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    import mujoco

    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        square_center_world_m,
        write_so101_development_mjcf,
    )

    config = SO101DevelopmentMJCFConfig(
        piece_square=args.source_square,
        target_square=args.target_square,
        contact_condim=CONTACT_FIXTURE_CONDIM,
        contact_friction=CONTACT_FIXTURE_FRICTION,
        gripper_min_closure_m=CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M,
        gripper_actuator_kp=CONTACT_FIXTURE_GRIPPER_KP,
        piece_radius_m=CONTACT_FIXTURE_PIECE_RADIUS_M,
        piece_mass_kg=CONTACT_FIXTURE_PIECE_MASS_KG,
    )
    manifest = write_so101_development_mjcf(model_path, config, manifest_path=manifest_path)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)

    gripper_joint_id = object_id(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, "gripper")
    gripper_open_m = float(model.jnt_range[gripper_joint_id][1])
    gripper_close_m = CONTACT_FIXTURE_GRIPPER_CLOSE_M
    source_x, source_y, source_board_z = square_center_world_m(config.piece_square, config)
    target_x, target_y, target_board_z = square_center_world_m(config.target_square, config)
    source_xy = (source_x, source_y)
    target_xy = (target_x, target_y)
    expected_place_z = target_board_z + config.piece_height_m / 2.0

    source_piece_pos = (source_x, source_y, source_board_z + config.piece_height_m / 2.0)
    set_freejoint_pose(mujoco, model, data, "piece_source_freejoint", pos=source_piece_pos)
    set_robot_pose(
        mujoco,
        model,
        data,
        shoulder_pan=SOURCE_PAN_RAD,
        joint_targets=LOWER_JOINT_TARGETS,
        gripper=gripper_open_m,
    )
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    rows = [
        record_stage(
            mujoco,
            model,
            data,
            stage="source_reset_piece_on_board",
            manual_piece_pose_set=True,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    ]

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=SOURCE_PAN_RAD,
        joint_targets=LOWER_JOINT_TARGETS,
        gripper=gripper_open_m,
    )
    step(mujoco, model, data, 100)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lower_open_at_source",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_joint_qpos(mujoco, model, data, "gripper", gripper_close_m)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="close_on_source_piece_forward",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )
    step(mujoco, model, data, 100)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="close_on_source_piece_after_settle",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    lift_start_piece_z = body_position(mujoco, model, data, "piece_source")[2]
    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=SOURCE_PAN_RAD,
        joint_targets=LIFT_JOINT_TARGETS,
        gripper=gripper_close_m,
    )
    step(mujoco, model, data, 500)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lift_from_source_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=TARGET_PAN_RAD,
        joint_targets=LIFT_JOINT_TARGETS,
        gripper=gripper_close_m,
    )
    step(mujoco, model, data, 700)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="transfer_to_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=TARGET_PAN_RAD,
        joint_targets=LOWER_JOINT_TARGETS,
        gripper=gripper_close_m,
    )
    step(mujoco, model, data, 600)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lower_to_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_open_m)
    step(mujoco, model, data, 300)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="release_on_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=TARGET_PAN_RAD,
        joint_targets=LIFT_JOINT_TARGETS,
        gripper=gripper_open_m,
    )
    step(mujoco, model, data, 700)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="retreat_after_release_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    source_reset = row_by_stage(rows, "source_reset_piece_on_board")
    close_settle = row_by_stage(rows, "close_on_source_piece_after_settle")
    lift = row_by_stage(rows, "lift_from_source_without_manual_piece_pose")
    transfer = row_by_stage(rows, "transfer_to_target_without_manual_piece_pose")
    lower = row_by_stage(rows, "lower_to_target_without_manual_piece_pose")
    final = row_by_stage(rows, "retreat_after_release_without_manual_piece_pose")
    source_pick_started_at_source = (
        source_reset["source_xy_error_m"] <= SOURCE_PICK_XY_TOLERANCE_M
        and close_settle["source_xy_error_m"] <= SOURCE_PICK_XY_TOLERANCE_M
    )
    close_two_finger_contact_observed = (
        close_settle["fixed_finger_contact_count"] > 0
        and close_settle["moving_finger_contact_count"] > 0
    )
    board_contact_cleared_during_lift = lift["board_contact_count"] == 0
    lift_without_manual_piece_pose_m = float(lift["piece_z"]) - lift_start_piece_z
    lift_verified = (
        close_two_finger_contact_observed
        and lift["gripper_contact_count"] > 0
        and board_contact_cleared_during_lift
        and lift_without_manual_piece_pose_m >= LIFT_Z_THRESHOLD_M
    )
    transfer_verified = (
        transfer["gripper_contact_count"] > 0
        and transfer["target_xy_error_m"] < close_settle["target_xy_error_m"]
        and transfer["board_contact_count"] == 0
    )
    lower_target_xy_error_m = float(lower["target_xy_error_m"])
    lower_place_z_error_m = abs(float(lower["piece_z"]) - expected_place_z)
    lower_contact_retained_before_release = lower["gripper_contact_count"] > 0
    lower_board_contact_observed_before_release = lower["board_contact_count"] > 0
    lower_target_within_tolerance_before_release = (
        lower_target_xy_error_m <= TARGET_XY_TOLERANCE_M
    )
    lower_place_z_within_tolerance_before_release = (
        lower_place_z_error_m <= PLACE_Z_TOLERANCE_M
    )
    final_target_xy_error_m = float(final["target_xy_error_m"])
    final_place_z_error_m = abs(float(final["piece_z"]) - expected_place_z)
    release_contact_cleared_after_retreat = final["gripper_contact_count"] == 0
    final_board_contact_observed = final["board_contact_count"] > 0
    place_without_manual_piece_pose_verified = (
        lower_contact_retained_before_release
        and lower_board_contact_observed_before_release
        and lower_target_within_tolerance_before_release
        and lower_place_z_within_tolerance_before_release
        and final_board_contact_observed
        and release_contact_cleared_after_retreat
        and final_target_xy_error_m <= TARGET_XY_TOLERANCE_M
        and final_place_z_error_m <= PLACE_Z_TOLERANCE_M
    )
    pick_place_phase_evidence = [
        phase_evidence_row(
            phase_id="source_reset",
            stage="source_reset_piece_on_board",
            ok=bool(source_reset["source_xy_error_m"] <= SOURCE_PICK_XY_TOLERANCE_M),
            criteria=[
                "piece_reset_to_source_before_run",
                "source_xy_error_within_tolerance",
            ],
            metrics={
                "source_xy_error_m": source_reset["source_xy_error_m"],
                "source_pick_xy_tolerance_m": SOURCE_PICK_XY_TOLERANCE_M,
                "manual_piece_pose_set": source_reset["manual_piece_pose_set"],
            },
        ),
        phase_evidence_row(
            phase_id="two_finger_grasp",
            stage="close_on_source_piece_after_settle",
            ok=close_two_finger_contact_observed,
            criteria=[
                "fixed_finger_contact_observed",
                "moving_finger_contact_observed",
                "source_xy_error_within_tolerance_after_close",
            ],
            metrics={
                "fixed_finger_contact_count": close_settle["fixed_finger_contact_count"],
                "moving_finger_contact_count": close_settle["moving_finger_contact_count"],
                "source_xy_error_m": close_settle["source_xy_error_m"],
                "source_pick_xy_tolerance_m": SOURCE_PICK_XY_TOLERANCE_M,
            },
        ),
        phase_evidence_row(
            phase_id="lift_clearance",
            stage="lift_from_source_without_manual_piece_pose",
            ok=lift_verified,
            criteria=[
                "piece_lifted_above_threshold",
                "gripper_contact_retained",
                "board_contact_cleared",
            ],
            metrics={
                "lift_without_manual_piece_pose_m": lift_without_manual_piece_pose_m,
                "lift_z_threshold_m": LIFT_Z_THRESHOLD_M,
                "gripper_contact_count": lift["gripper_contact_count"],
                "board_contact_count": lift["board_contact_count"],
            },
        ),
        phase_evidence_row(
            phase_id="transfer_toward_target",
            stage="transfer_to_target_without_manual_piece_pose",
            ok=transfer_verified,
            criteria=[
                "target_xy_error_decreases",
                "gripper_contact_retained",
                "board_contact_clear_during_transfer",
            ],
            metrics={
                "target_xy_error_m": transfer["target_xy_error_m"],
                "close_target_xy_error_m": close_settle["target_xy_error_m"],
                "source_to_target_progress_m": transfer["source_to_target_progress_m"],
                "gripper_contact_count": transfer["gripper_contact_count"],
                "board_contact_count": transfer["board_contact_count"],
            },
        ),
        phase_evidence_row(
            phase_id="release_place",
            stage="retreat_after_release_without_manual_piece_pose",
            ok=place_without_manual_piece_pose_verified,
            criteria=[
                "lower_contact_retained_before_release",
                "lower_board_contact_observed_before_release",
                "lower_target_xy_error_within_tolerance_before_release",
                "lower_place_z_error_within_tolerance_before_release",
                "final_board_contact_observed",
                "release_contact_cleared_after_retreat",
                "final_target_xy_error_within_tolerance",
                "final_place_z_error_within_tolerance",
            ],
            metrics={
                "lower_contact_retained_before_release": lower_contact_retained_before_release,
                "lower_board_contact_observed_before_release": lower_board_contact_observed_before_release,
                "lower_target_xy_error_m": lower_target_xy_error_m,
                "lower_place_z_error_m": lower_place_z_error_m,
                "final_board_contact_observed": final_board_contact_observed,
                "release_contact_cleared_after_retreat": release_contact_cleared_after_retreat,
                "final_target_xy_error_m": final_target_xy_error_m,
                "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
                "final_place_z_error_m": final_place_z_error_m,
                "place_z_tolerance_m": PLACE_Z_TOLERANCE_M,
            },
        ),
    ]
    pick_place_failed_phase_ids = [
        phase["phase_id"] for phase in pick_place_phase_evidence if not phase["ok"]
    ]
    pick_place_all_required_phases_verified = not pick_place_failed_phase_ids
    stage_sequence = stage_sequence_contract(rows)
    board_source_pick_place_verified = bool(
        source_pick_started_at_source
        and close_two_finger_contact_observed
        and lift_verified
        and transfer_verified
        and place_without_manual_piece_pose_verified
        and pick_place_all_required_phases_verified
        and stage_sequence["stage_sequence_contract_ok"]
    )
    if board_source_pick_place_verified:
        status = "development_board_source_pick_place_verified"
    elif lift_verified:
        status = "development_board_source_lift_verified_place_gap_recorded"
    else:
        status = "development_board_source_pick_gap_recorded"

    next_required_for_goal = [dict(action) for action in NEXT_REQUIRED_FOR_GOAL]
    next_required_actions = next_required_action_ids(next_required_for_goal)
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "dependencies": deps,
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "development_manifest": manifest,
        "probe_count": len(rows),
        "source_square": config.piece_square,
        "target_square": config.target_square,
        "source_world_m": {
            "x": source_x,
            "y": source_y,
            "board_z": source_board_z,
            "expected_piece_center_z": source_piece_pos[2],
        },
        "target_world_m": {
            "x": target_x,
            "y": target_y,
            "board_z": target_board_z,
            "expected_piece_center_z": expected_place_z,
        },
        "contact_fixture": {
            "piece_radius_m": CONTACT_FIXTURE_PIECE_RADIUS_M,
            "piece_mass_kg": CONTACT_FIXTURE_PIECE_MASS_KG,
            "contact_condim": CONTACT_FIXTURE_CONDIM,
            "contact_friction": list(CONTACT_FIXTURE_FRICTION),
            "gripper_min_closure_m": CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M,
            "gripper_close_m": gripper_close_m,
            "gripper_actuator_kp": CONTACT_FIXTURE_GRIPPER_KP,
            "gripper_open_m": gripper_open_m,
        },
        "source_pick_started_at_source": source_pick_started_at_source,
        "source_pick_xy_tolerance_m": SOURCE_PICK_XY_TOLERANCE_M,
        "close_two_finger_contact_observed": close_two_finger_contact_observed,
        "lift_verified": lift_verified,
        "lift_without_manual_piece_pose_m": lift_without_manual_piece_pose_m,
        "lift_z_threshold_m": LIFT_Z_THRESHOLD_M,
        "board_contact_cleared_during_lift": board_contact_cleared_during_lift,
        "transfer_verified": transfer_verified,
        "transfer_target_xy_error_m": transfer["target_xy_error_m"],
        "transfer_source_to_target_progress_m": transfer["source_to_target_progress_m"],
        "lower_contact_retained_before_release": lower_contact_retained_before_release,
        "lower_board_contact_observed_before_release": lower_board_contact_observed_before_release,
        "lower_target_within_tolerance_before_release": lower_target_within_tolerance_before_release,
        "lower_place_z_within_tolerance_before_release": lower_place_z_within_tolerance_before_release,
        "lower_target_xy_error_m": lower_target_xy_error_m,
        "lower_place_z_error_m": lower_place_z_error_m,
        "place_without_manual_piece_pose_verified": place_without_manual_piece_pose_verified,
        "board_source_pick_place_verified": board_source_pick_place_verified,
        "release_contact_cleared_after_retreat": release_contact_cleared_after_retreat,
        "final_board_contact_observed": final_board_contact_observed,
        "final_target_xy_error_m": final_target_xy_error_m,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
        "final_place_z_error_m": final_place_z_error_m,
        "place_z_tolerance_m": PLACE_Z_TOLERANCE_M,
        "pick_place_phase_evidence": pick_place_phase_evidence,
        "pick_place_phase_ids": [
            phase["phase_id"] for phase in pick_place_phase_evidence
        ],
        "pick_place_failed_phase_ids": pick_place_failed_phase_ids,
        "pick_place_phase_count": len(pick_place_phase_evidence),
        "pick_place_all_required_phases_verified": pick_place_all_required_phases_verified,
        **stage_sequence,
        "source_to_target_progress_m": final["source_to_target_progress_m"],
        "piece_reset_to_source_before_run": True,
        "manual_piece_pose_used_after_reset": bool(
            stage_sequence["manual_piece_pose_after_reset_stage_ids"]
        ),
        "robot_pose_seeded_for_source_fixture": True,
        "robot_motion_mode": "seed_source_pose_position_actuator_close_lift_transfer_lower_release_retreat",
        "source_pose_joint_qpos_rad": {
            "shoulder_pan": SOURCE_PAN_RAD,
            **LOWER_JOINT_TARGETS,
        },
        "lift_target_joint_qpos_rad": LIFT_JOINT_TARGETS,
        "transfer_target_joint_qpos_rad": {"shoulder_pan": TARGET_PAN_RAD},
        "rows": rows,
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "This is a generated development MJCF scaffold, not reviewed SO-101 CAD or calibrated model truth.",
            "The piece is enlarged, lightened, and contact-tuned to probe board-source physics before reviewed geometry is available.",
            "The robot source pose is seeded directly in qpos/ctrl; reviewed model-backed IK remains required.",
            "The piece freejoint is reset onto the source square once before the run and is not manually moved after that reset.",
        ],
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": next_required_actions,
        "next_required_action_count": len(next_required_actions),
        **next_required_action_sync_fields(
            next_required_for_goal=next_required_for_goal,
            explicit_action_ids=next_required_actions,
        ),
    }
    write_json(summary_path, summary)
    write_rows(rows_path, rows)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": True, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
