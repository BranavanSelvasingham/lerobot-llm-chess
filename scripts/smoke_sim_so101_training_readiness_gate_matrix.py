#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smoke_sim_calibration_regression_suite import (  # noqa: E402
    SO101_BOARD_PICK_REQUIRED_PHASE_IDS,
    SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE,
    SO101_CONTROL_JOINT_IDS,
    REVIEWED_SO101_MODEL_AUTHORITY,
    SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_SCHEMA,
    SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_ITEM_IDS,
    SO101_REVIEWED_MUJOCO_DOWNSTREAM_PRIORITY_GATE_ID,
    SO101_REVIEWED_MUJOCO_DOWNSTREAM_PRIORITY_ORDER,
    SO101_REVIEWED_MUJOCO_NEXT_DOWNSTREAM_GATE_AFTER_READY,
    SO101_TRAINING_PRIORITY_STAGE_IDS,
    so101_training_readiness_gate_section,
    write_so101_training_readiness_gate_artifacts,
)

DEFAULT_OUTPUT_DIR = (
    Path("/private/tmp") / "lerobot_sim" / "so101_training_readiness_gate_matrix"
)
SCHEMA = "lerobot.sim.so101_training_readiness_gate_matrix.v1"
DEV_AUTHORITY = "development_scaffold_not_reviewed"
BOARD_PICK_DEVELOPMENT_NEXT_REQUIRED_FOR_GOAL = (
    {
        "priority": 1,
        "missing_input": "reviewed_so101_model_bundle",
        "action_id": "supply_reviewed_so101_model_bundle_manifest",
        "gate": "reviewed_model_authority",
    },
    {
        "priority": 2,
        "missing_input": "reviewed_tcp_and_base_to_board_alignment",
        "action_id": "calibrate_reviewed_tcp_and_base_to_board_alignment",
        "gate": "reviewed_model_authority",
    },
    {
        "priority": 3,
        "missing_input": "reviewed_model_backed_board_source_pick_place",
        "action_id": "repeat_board_pick_with_reviewed_model_backed_ik",
        "gate": "scripted_contact_grasp_pick_place",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free contract matrix over the SO-101 serious-training "
            "readiness gate. Inputs are injected state dictionaries and are not "
            "policy-training authority."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing output directory before running.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "case_id",
        "ok",
        "gate_status",
        "gate_ready",
        "reviewed_model_authority_ready",
        "reviewed_model_physical_motion_checked",
        "reviewed_mujoco_downstream_handoff_contract_ok",
        "reviewed_mujoco_downstream_handoff_contract_status",
        "reviewed_mujoco_downstream_handoff_schema",
        "reviewed_mujoco_downstream_handoff_expected_schema",
        "reviewed_mujoco_downstream_handoff_raw_ready",
        "reviewed_mujoco_downstream_handoff_ready",
        "reviewed_mujoco_downstream_handoff_status",
        "reviewed_mujoco_downstream_handoff_model_authority",
        "reviewed_mujoco_downstream_handoff_physical_truth_claimed",
        "reviewed_mujoco_downstream_handoff_policy_training_authority_claimed",
        "reviewed_mujoco_downstream_handoff_development_fixture_evidence_not_policy_training_truth",
        "reviewed_mujoco_downstream_handoff_model_identity_contract_ok",
        "reviewed_mujoco_downstream_handoff_model_identity_status",
        "reviewed_mujoco_downstream_handoff_model_identity_matches",
        "reviewed_mujoco_downstream_handoff_model_path",
        "reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority",
        "reviewed_mujoco_downstream_handoff_physical_motion_checked",
        "reviewed_mujoco_downstream_handoff_hardware_free_fixture_motion_checked",
        "reviewed_mujoco_downstream_handoff_joint_limit_enablement_ok",
        "reviewed_mujoco_downstream_handoff_joint_limit_enablement_status",
        "reviewed_mujoco_downstream_handoff_missing_limited_joints",
        "reviewed_mujoco_downstream_handoff_required_limited_joints",
        "reviewed_mujoco_downstream_handoff_missing_item_ids",
        "reviewed_mujoco_downstream_handoff_missing_inputs",
        "reviewed_mujoco_downstream_handoff_pending_action_ids",
        "reviewed_mujoco_downstream_handoff_ready_has_open_work",
        "reviewed_mujoco_downstream_handoff_contract_blockers",
        "reviewed_mujoco_downstream_handoff_priority_gate_id",
        "reviewed_mujoco_downstream_handoff_priority_gate_order",
        "reviewed_mujoco_downstream_handoff_next_downstream_gate_after_ready",
        "reviewed_mujoco_downstream_handoff_blocks_downstream_gates_until_ready",
        "reviewed_mujoco_downstream_handoff_ready_does_not_imply_policy_training_ready",
        "reviewed_mujoco_downstream_handoff_priority_contract_ok",
        "reviewed_model_backed_board_source_pick_place",
        "board_pick_reviewed_model_authority_ready",
        "board_pick_authority_status",
        "board_pick_authority_blockers",
        "board_pick_detailed_evidence_ready",
        "board_pick_observed_evidence_is_physical_so101_authority",
        "board_pick_observed_evidence_is_policy_training_authority",
        "board_pick_ready_for_policy_training",
        "board_pick_physical_truth_claimed",
        "board_pick_policy_training_claimed",
        "board_pick_policy_authority_claimed",
        "board_pick_next_required_action_ids",
        "board_pick_next_required_for_goal_action_ids",
        "board_pick_next_required_action_ids_match_next_required",
        "board_pick_next_required_action_ids_missing_from_next_required",
        "board_pick_next_required_actions_missing_from_action_ids",
        "board_pick_phase_evidence_ready",
        "board_pick_stage_sequence_ready",
        "board_pick_phase_ids",
        "board_pick_failed_phase_ids",
        "board_pick_phase_count",
        "board_pick_all_required_phases_verified",
        "board_pick_stage_sequence_contract_ok",
        "board_pick_stage_sequence_order_ok",
        "board_pick_observed_stage_sequence",
        "board_pick_missing_stage_ids",
        "board_pick_unexpected_stage_ids",
        "board_pick_stage_sequence_contract_errors",
        "board_pick_manual_piece_pose_after_reset_stage_ids",
        "board_pick_lower_contact_retained_before_release",
        "board_pick_lower_board_contact_observed_before_release",
        "board_pick_lower_target_within_tolerance_before_release",
        "board_pick_lower_place_z_within_tolerance_before_release",
        "board_pick_lower_target_xy_error_m",
        "board_pick_target_xy_tolerance_m",
        "board_pick_lower_target_xy_within_tolerance",
        "board_pick_lower_place_z_error_m",
        "board_pick_lower_place_z_within_tolerance",
        "board_pick_final_place_z_error_m",
        "board_pick_place_z_tolerance_m",
        "board_pick_final_place_z_within_tolerance",
        "rollout_ready_for_policy_training",
        "rollout_status",
        "rollout_training_authority_status",
        "rollout_use",
        "rollout_observed_evidence_is_policy_training_authority",
        "rollout_policy_training_authority_ready",
        "development_fixture_evidence_not_policy_training_truth",
        "next_priority_gate_id",
        "next_priority_action_ids",
        "priority_gate_order",
        "priority_gate_training_blocker_action_ids_by_gate_id",
        "priority_gate_development_evidence_only_not_training_truth_by_gate_id",
        "priority_gate_queue_csv",
        "blockers",
        "expected_gate_ready",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def reviewed_authority_ready(
    summary_path: Path,
    *,
    physical_motion_checked: bool = True,
) -> dict[str, Any]:
    return {
        "status": "reviewed_model_authority_ready",
        "ready": True,
        "physical_reviewed_model_motion_checked": physical_motion_checked,
        "blockers": [],
        "summary_path": str(summary_path),
    }


def reviewed_authority_blocked(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_model_authority_blocked",
        "ready": False,
        "blockers": [
            "supply_reviewed_so101_model_bundle_manifest",
            "prove_physical_reviewed_model_motion",
        ],
        "summary_path": str(summary_path),
    }


def board_pick_phase_evidence(verified: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase_id in SO101_BOARD_PICK_REQUIRED_PHASE_IDS:
        row = {
            "phase_id": phase_id,
            "stage": f"{phase_id}_contract_state_fixture",
            "ok": verified,
            "criteria": [f"{phase_id}_criterion_recorded"],
            "metrics": {f"{phase_id}_metric": 1.0 if verified else 0.0},
        }
        if phase_id == "release_place":
            row["criteria"] = [
                "lower_contact_retained_before_release",
                "lower_board_contact_observed_before_release",
                "lower_target_xy_error_within_tolerance_before_release",
                "lower_place_z_error_within_tolerance_before_release",
                "final_board_contact_observed",
                "release_contact_cleared_after_retreat",
                "final_target_xy_error_within_tolerance",
                "final_place_z_error_within_tolerance",
            ]
            row["metrics"] = {
                "lower_contact_retained_before_release": verified,
                "lower_board_contact_observed_before_release": verified,
                "lower_target_xy_error_m": 0.002 if verified else 0.05,
                "lower_place_z_error_m": 0.001 if verified else 0.02,
            }
        rows.append(row)
    return rows


def board_pick_next_required_fields(
    *,
    reviewed_model_backed_ready: bool,
) -> dict[str, Any]:
    next_required_for_goal = (
        []
        if reviewed_model_backed_ready
        else [dict(action) for action in BOARD_PICK_DEVELOPMENT_NEXT_REQUIRED_FOR_GOAL]
    )
    action_ids = [
        str(action["action_id"])
        for action in next_required_for_goal
        if isinstance(action, dict) and "action_id" in action
    ]
    return {
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": action_ids,
        "next_required_for_goal_action_ids": action_ids,
        "next_required_action_ids_match_next_required": True,
        "next_required_action_ids_missing_from_next_required": [],
        "next_required_actions_missing_from_action_ids": [],
        "next_required_action_count": len(action_ids),
    }


def board_pick_state(
    summary_path: Path,
    *,
    model_authority: str | None,
    ready_for_model_backed_ik: bool,
    seeded_source_pose: bool,
    manual_piece_pose_after_reset: bool = False,
    verified: bool = True,
    stage_sequence_verified: bool = True,
    observed_physical_authority: bool = False,
    ready_for_policy_training: bool = False,
    observed_policy_authority: bool = False,
) -> dict[str, Any]:
    final_target_xy_error_m = 0.002 if verified else 0.05
    target_xy_tolerance_m = 0.01
    lower_target_xy_error_m = 0.002 if verified else 0.05
    lower_place_z_error_m = 0.001 if verified else 0.02
    final_place_z_error_m = 0.001 if verified else 0.02
    place_z_tolerance_m = 0.005
    observed_stage_sequence = (
        list(SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE)
        if stage_sequence_verified
        else list(SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE[:-1])
    )
    missing_stage_ids = (
        []
        if stage_sequence_verified
        else [SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE[-1]]
    )
    manual_stage_ids = (
        ["transfer_to_target_without_manual_piece_pose"]
        if manual_piece_pose_after_reset
        else []
    )
    stage_sequence_contract_errors: list[str] = []
    if not stage_sequence_verified:
        stage_sequence_contract_errors.append("observed_stage_sequence_mismatch")
    if manual_stage_ids:
        stage_sequence_contract_errors.append(
            "manual_piece_pose_after_reset_detected"
        )
    reviewed_model_backed_ready = (
        model_authority == REVIEWED_SO101_MODEL_AUTHORITY
        and ready_for_model_backed_ik
        and not seeded_source_pose
        and not manual_piece_pose_after_reset
        and verified
        and not stage_sequence_contract_errors
        and not ready_for_policy_training
        and not observed_physical_authority
        and not observed_policy_authority
    )
    return {
        "status": (
            "reviewed_model_backed_board_source_pick_place_verified"
            if model_authority == REVIEWED_SO101_MODEL_AUTHORITY
            and ready_for_model_backed_ik
            and not seeded_source_pose
            and not manual_piece_pose_after_reset
            and verified
            else "development_board_source_pick_place_verified"
            if verified
            else "board_source_pick_place_not_verified"
        ),
        "board_source_pick_place_verified": verified,
        "source_pick_started_at_source": verified,
        "close_two_finger_contact_observed": verified,
        "lift_verified": verified,
        "board_contact_cleared_during_lift": verified,
        "transfer_verified": verified,
        "lower_contact_retained_before_release": verified,
        "lower_board_contact_observed_before_release": verified,
        "lower_target_within_tolerance_before_release": verified,
        "lower_place_z_within_tolerance_before_release": verified,
        "lower_target_xy_error_m": lower_target_xy_error_m,
        "lower_place_z_error_m": lower_place_z_error_m,
        "place_without_manual_piece_pose_verified": verified,
        "release_contact_cleared_after_retreat": verified,
        "final_board_contact_observed": verified,
        "final_target_xy_error_m": final_target_xy_error_m,
        "target_xy_tolerance_m": target_xy_tolerance_m,
        "final_place_z_error_m": final_place_z_error_m,
        "place_z_tolerance_m": place_z_tolerance_m,
        "pick_place_phase_evidence": board_pick_phase_evidence(verified),
        "pick_place_phase_ids": list(SO101_BOARD_PICK_REQUIRED_PHASE_IDS),
        "pick_place_failed_phase_ids": [] if verified else list(SO101_BOARD_PICK_REQUIRED_PHASE_IDS),
        "pick_place_phase_count": len(SO101_BOARD_PICK_REQUIRED_PHASE_IDS),
        "pick_place_all_required_phases_verified": verified,
        "required_stage_sequence": list(SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE),
        "observed_stage_sequence": observed_stage_sequence,
        "missing_stage_ids": missing_stage_ids,
        "unexpected_stage_ids": [],
        "stage_sequence_order_ok": stage_sequence_verified,
        "stage_sequence_contract_ok": not stage_sequence_contract_errors,
        "stage_sequence_contract_errors": stage_sequence_contract_errors,
        "manual_piece_pose_after_reset_stage_ids": manual_stage_ids,
        "ready_for_model_backed_ik": ready_for_model_backed_ik,
        "ready_for_policy_training": ready_for_policy_training,
        "observed_evidence_is_physical_so101_authority": observed_physical_authority,
        "observed_evidence_is_policy_training_authority": observed_policy_authority,
        "model_authority": model_authority,
        "robot_pose_seeded_for_source_fixture": seeded_source_pose,
        "manual_piece_pose_used_after_reset": manual_piece_pose_after_reset,
        "summary_path": str(summary_path),
        **board_pick_next_required_fields(
            reviewed_model_backed_ready=reviewed_model_backed_ready
        ),
    }


def rollout_state(
    summary_path: Path,
    *,
    ready_for_policy_training: bool,
    model_authority: str | None,
    blockers: list[str] | None = None,
    status: str | None = None,
    training_authority_status: str | None = None,
    rollout_use: str | None = None,
    observed_policy_authority: bool | None = None,
) -> dict[str, Any]:
    reviewed_ready = (
        ready_for_policy_training and model_authority == REVIEWED_SO101_MODEL_AUTHORITY
    )
    return {
        "status": (
            status
            if status is not None
            else "ok"
            if ready_for_policy_training
            else "not_policy_ready"
        ),
        "ready_for_policy_training": ready_for_policy_training,
        "training_authority_status": (
            training_authority_status
            if training_authority_status is not None
            else "reviewed_policy_training_rollouts_ready"
            if reviewed_ready
            else "development_rollouts_prerequisites_verified_not_policy_ready"
            if model_authority == DEV_AUTHORITY
            else "reviewed_rollouts_not_ready"
        ),
        "model_authority": model_authority,
        "observed_evidence_is_policy_training_authority": (
            observed_policy_authority
            if observed_policy_authority is not None
            else reviewed_ready
        ),
        "rollout_use": (
            rollout_use
            if rollout_use is not None
            else "policy_training"
            if reviewed_ready
            else "debug_imitation_curriculum_only"
        ),
        "serious_policy_training_blockers": blockers
        if blockers is not None
        else ([] if ready_for_policy_training else ["reviewed_model_backed_training_rollouts"]),
        "summary_path": str(summary_path),
    }


def mujoco_scene_state(
    summary_path: Path,
    *,
    model_authority: str | None,
    status: str = "ok",
) -> dict[str, Any]:
    return {
        "status": status,
        "model_authority": model_authority,
        "ready_for_model_backed_ik": model_authority == REVIEWED_SO101_MODEL_AUTHORITY,
        "summary_path": str(summary_path),
    }


def chess_env_state(
    summary_path: Path,
    *,
    model_authority: str | None,
    status: str = "ok",
) -> dict[str, Any]:
    return {
        "status": status,
        "model_authority": model_authority,
        "ready_for_policy_training": model_authority == REVIEWED_SO101_MODEL_AUTHORITY,
        "summary_path": str(summary_path),
    }


def contact_probe_state(summary_path: Path, *, observed: bool = True) -> dict[str, Any]:
    return {
        "status": "ok" if observed else "contact_not_observed",
        "all_board_contacts_observed": observed,
        "summary_path": str(summary_path),
    }


def grasp_probe_state(summary_path: Path, *, verified: bool = True) -> dict[str, Any]:
    return {
        "status": (
            "contact_grasp_lift_place_physics_verified"
            if verified
            else "contact_grasp_lift_place_not_verified"
        ),
        "contact_grasp_lift_place_physics_verified": verified,
        "summary_path": str(summary_path),
    }


def mujoco_joint_limit_enablement_state(
    *,
    missing_limited_joints: list[str] | None = None,
) -> dict[str, Any]:
    missing_limited_joints = sorted(missing_limited_joints or [])
    joint_limited = {
        joint_name: joint_name not in missing_limited_joints
        for joint_name in SO101_CONTROL_JOINT_IDS
    }
    return {
        "ok": not missing_limited_joints,
        "status": (
            "so101_mujoco_joints_limited"
            if not missing_limited_joints
            else "so101_mujoco_joints_unlimited"
        ),
        "joint_limited": joint_limited,
        "missing_limited_joints": missing_limited_joints,
        "limited_joint_count": sum(1 for value in joint_limited.values() if value),
        "required_joint_count": len(SO101_CONTROL_JOINT_IDS),
        "diagnostics": [
            f"mujoco_joint_not_limited:{joint_name}"
            for joint_name in missing_limited_joints
        ],
    }


def reviewed_mujoco_bundle_state(
    summary_path: Path,
    *,
    handoff_ready: bool,
    fixture_handoff_ready: bool = False,
    model_identity_contract_ok: bool | None = None,
    status: str | None = None,
    physical_motion_checked: bool | None = None,
    fixture_motion_checked: bool | None = None,
    reviewed_motion_checked: bool | None = None,
    motion_authority_status: str | None = None,
    physical_model_authority_ready: bool | None = None,
    motion_evidence_not_physical: bool | None = None,
    item_ids: list[str] | None = None,
    item_count: int | None = None,
    missing_inputs: list[str] | None = None,
    next_required_for_goal: list[Any] | None = None,
    next_required_action_ids: list[str] | None = None,
    physical_truth_claimed: bool = False,
    policy_training_authority_claimed: bool = False,
    observed_evidence_is_authority: bool = False,
    observed_evidence_is_policy_training_authority: bool = False,
    development_fixture_evidence_not_physical_truth: bool = True,
    development_fixture_evidence_not_policy_training_truth: bool = True,
    joint_limit_enablement: dict[str, Any] | None = None,
    downstream_handoff_schema: str | None = (
        SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_SCHEMA
    ),
) -> dict[str, Any]:
    physical_motion_checked = (
        handoff_ready if physical_motion_checked is None else physical_motion_checked
    )
    fixture_motion_checked = (
        fixture_handoff_ready
        if fixture_motion_checked is None
        else fixture_motion_checked
    )
    if reviewed_motion_checked is None:
        reviewed_motion_checked = physical_motion_checked or fixture_motion_checked
    if model_identity_contract_ok is None:
        model_identity_contract_ok = handoff_ready or fixture_handoff_ready
    physical_model_authority_ready = (
        handoff_ready
        if physical_model_authority_ready is None
        else physical_model_authority_ready
    )
    motion_evidence_not_physical = (
        fixture_handoff_ready
        if motion_evidence_not_physical is None
        else motion_evidence_not_physical
    )
    motion_authority_status = (
        motion_authority_status
        if motion_authority_status is not None
        else "physical_reviewed_model_motion_checked"
        if handoff_ready
        else "hardware_free_fixture_motion_checked_not_physical_so101_authority"
        if fixture_handoff_ready
        else "not_checked_manifest_not_ready"
    )
    item_ids = (
        list(SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_ITEM_IDS)
        if item_ids is None
        else item_ids
    )
    item_count = len(item_ids) if item_count is None else item_count
    missing_inputs = [] if missing_inputs is None else missing_inputs
    next_required_for_goal = (
        [] if next_required_for_goal is None else next_required_for_goal
    )
    next_required_action_ids = (
        [] if next_required_action_ids is None else next_required_action_ids
    )
    if joint_limit_enablement is None and (handoff_ready or fixture_handoff_ready):
        joint_limit_enablement = mujoco_joint_limit_enablement_state()
    mujoco_motion_inputs = (
        {"mujoco_joint_limit_enablement": joint_limit_enablement}
        if isinstance(joint_limit_enablement, dict)
        else {}
    )
    return {
        "status": (
            "reviewed_mujoco_bundle_motion_checked"
            if handoff_ready or fixture_handoff_ready
            else "reviewed_mujoco_bundle_not_ready"
        ),
        "downstream_handoff_status": (
            status
            if status is not None
            else "physical_reviewed_mujoco_handoff_ready"
            if handoff_ready
            else "fixture_mujoco_handoff_ready_not_physical_authority"
            if fixture_handoff_ready
            else "waiting_for_reviewed_bundle_authority"
        ),
        "downstream_handoff_schema": downstream_handoff_schema,
        "downstream_handoff_ready": handoff_ready,
        "downstream_handoff_model_authority": "downstream_handoff_not_authority",
        "downstream_handoff_model_identity_contract_ok": model_identity_contract_ok,
        "downstream_handoff_model_identity_status": (
            "present" if model_identity_contract_ok else None
        ),
        "downstream_handoff_model_identity_matches": model_identity_contract_ok,
        "downstream_handoff_model_path": (
            "/tmp/synthetic-reviewed-so101.xml"
            if model_identity_contract_ok
            else None
        ),
        "downstream_handoff_declared_model_sha256": (
            "a" * 64 if model_identity_contract_ok else None
        ),
        "downstream_handoff_observed_model_sha256": (
            "a" * 64 if model_identity_contract_ok else None
        ),
        "downstream_handoff_observed_evidence_is_authority": (
            observed_evidence_is_authority
        ),
        "downstream_handoff_physical_so101_truth_claimed": physical_truth_claimed,
        "downstream_handoff_policy_training_authority_claimed": (
            policy_training_authority_claimed
        ),
        "downstream_handoff_development_fixture_evidence_not_physical_so101_truth": (
            development_fixture_evidence_not_physical_truth
        ),
        "downstream_handoff_development_fixture_evidence_not_policy_training_truth": (
            development_fixture_evidence_not_policy_training_truth
        ),
        "downstream_handoff_item_count": item_count,
        "downstream_handoff_item_ids": item_ids,
        "downstream_priority_gate_id": (
            SO101_REVIEWED_MUJOCO_DOWNSTREAM_PRIORITY_GATE_ID
        ),
        "downstream_priority_gate_order": list(
            SO101_REVIEWED_MUJOCO_DOWNSTREAM_PRIORITY_ORDER
        ),
        "next_downstream_gate_after_ready": (
            SO101_REVIEWED_MUJOCO_NEXT_DOWNSTREAM_GATE_AFTER_READY
        ),
        "blocks_downstream_gates_until_ready": True,
        "ready_does_not_imply_policy_training_ready": True,
        "ready_for_policy_training": False,
        "observed_evidence_is_policy_training_authority": (
            observed_evidence_is_policy_training_authority
        ),
        "missing_inputs": missing_inputs,
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": next_required_action_ids,
        "fixture_handoff_ready_not_physical_so101_authority": fixture_handoff_ready,
        "reviewed_model_motion_checked": reviewed_motion_checked,
        "physical_reviewed_model_motion_checked": physical_motion_checked,
        "hardware_free_fixture_motion_checked": fixture_motion_checked,
        "motion_authority_status": motion_authority_status,
        "physical_so101_model_authority_ready": physical_model_authority_ready,
        "motion_evidence_not_physical_so101_authority": motion_evidence_not_physical,
        "mujoco_joint_limit_enablement": joint_limit_enablement,
        "mujoco_motion_inputs": mujoco_motion_inputs,
        "summary_path": str(summary_path),
    }


def case_specs(output_dir: Path) -> list[dict[str, Any]]:
    summaries = output_dir / "input_summaries"
    authority_ready = reviewed_authority_ready(summaries / "authority_ready.json")
    authority_motion_not_checked = reviewed_authority_ready(
        summaries / "authority_motion_not_checked.json",
        physical_motion_checked=False,
    )
    authority_blocked = reviewed_authority_blocked(summaries / "authority_blocked.json")
    board_dev = board_pick_state(
        summaries / "board_dev.json",
        model_authority=DEV_AUTHORITY,
        ready_for_model_backed_ik=False,
        seeded_source_pose=True,
    )
    board_reviewed = board_pick_state(
        summaries / "board_reviewed.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
        ready_for_model_backed_ik=True,
        seeded_source_pose=False,
    )
    board_reviewed_missing_release = {
        **board_pick_state(
            summaries / "board_reviewed_missing_release.json",
            model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
            ready_for_model_backed_ik=True,
            seeded_source_pose=False,
        ),
        "release_contact_cleared_after_retreat": False,
    }
    board_reviewed_missing_final_contact = {
        **board_pick_state(
            summaries / "board_reviewed_missing_final_contact.json",
            model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
            ready_for_model_backed_ik=True,
            seeded_source_pose=False,
        ),
        "final_board_contact_observed": False,
    }
    board_reviewed_target_outside_tolerance = {
        **board_pick_state(
            summaries / "board_reviewed_target_outside_tolerance.json",
            model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
            ready_for_model_backed_ik=True,
            seeded_source_pose=False,
        ),
        "final_target_xy_error_m": 0.05,
    }
    board_reviewed_missing_phase_evidence = {
        **board_pick_state(
            summaries / "board_reviewed_missing_phase_evidence.json",
            model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
            ready_for_model_backed_ik=True,
            seeded_source_pose=False,
        ),
        "pick_place_phase_evidence": [],
        "pick_place_phase_ids": [],
        "pick_place_phase_count": 0,
        "pick_place_all_required_phases_verified": False,
    }
    board_reviewed_missing_stage_sequence = board_pick_state(
        summaries / "board_reviewed_missing_stage_sequence.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
        ready_for_model_backed_ik=True,
        seeded_source_pose=False,
        stage_sequence_verified=False,
    )
    board_reviewed_z_tolerance_missing = {
        **board_pick_state(
            summaries / "board_reviewed_z_tolerance_missing.json",
            model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
            ready_for_model_backed_ik=True,
            seeded_source_pose=False,
        ),
        "place_z_tolerance_m": None,
    }
    board_reviewed_z_outside_tolerance = {
        **board_pick_state(
            summaries / "board_reviewed_z_outside_tolerance.json",
            model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
            ready_for_model_backed_ik=True,
            seeded_source_pose=False,
        ),
        "final_place_z_error_m": 0.025,
    }
    board_reviewed_physical_truth_claimed = board_pick_state(
        summaries / "board_reviewed_physical_truth_claimed.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
        ready_for_model_backed_ik=True,
        seeded_source_pose=False,
        observed_physical_authority=True,
    )
    board_reviewed_policy_training_claimed = board_pick_state(
        summaries / "board_reviewed_policy_training_claimed.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
        ready_for_model_backed_ik=True,
        seeded_source_pose=False,
        ready_for_policy_training=True,
        observed_policy_authority=True,
    )
    rollout_dev_blocked = rollout_state(
        summaries / "rollout_dev_blocked.json",
        ready_for_policy_training=False,
        model_authority=DEV_AUTHORITY,
        blockers=[
            "reviewed_so101_model_bundle",
            "reviewed_tcp_and_base_to_board_alignment",
            "reviewed_model_backed_board_source_pick_place",
        ],
    )
    rollout_reviewed_ready = rollout_state(
        summaries / "rollout_reviewed_ready.json",
        ready_for_policy_training=True,
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
    )
    scene_dev = mujoco_scene_state(
        summaries / "scene_dev.json",
        model_authority=DEV_AUTHORITY,
    )
    scene_reviewed = mujoco_scene_state(
        summaries / "scene_reviewed.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
    )
    env_dev = chess_env_state(
        summaries / "env_dev.json",
        model_authority=DEV_AUTHORITY,
    )
    env_reviewed = chess_env_state(
        summaries / "env_reviewed.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
    )
    contact_ready = contact_probe_state(summaries / "contact_ready.json")
    grasp_ready = grasp_probe_state(summaries / "grasp_ready.json")
    handoff_missing = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_missing.json",
        handoff_ready=False,
    )
    handoff_ready = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_ready.json",
        handoff_ready=True,
    )
    handoff_fixture_ready = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_fixture_ready.json",
        handoff_ready=False,
        fixture_handoff_ready=True,
    )
    handoff_raw_ready_without_physical_motion = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_raw_ready_without_physical_motion.json",
        handoff_ready=True,
        physical_motion_checked=False,
        reviewed_motion_checked=False,
        motion_authority_status="not_checked_manifest_not_ready",
        physical_model_authority_ready=False,
    )
    handoff_ready_with_unlimited_joint = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_ready_unlimited_joint.json",
        handoff_ready=True,
        joint_limit_enablement=mujoco_joint_limit_enablement_state(
            missing_limited_joints=["shoulder_pan"]
        ),
    )
    handoff_ready_with_stale_schema = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_ready_stale_schema.json",
        handoff_ready=True,
        downstream_handoff_schema=(
            "lerobot.sim.so101_reviewed_mujoco_bundle_downstream_handoff.v0"
        ),
    )
    handoff_ready_missing_model_identity = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_ready_missing_model_identity.json",
        handoff_ready=True,
        model_identity_contract_ok=False,
    )
    handoff_incomplete_items = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_incomplete_items.json",
        handoff_ready=True,
        item_ids=["downstream_gate_handoff"],
    )
    handoff_ready_with_missing_input = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_ready_missing_input.json",
        handoff_ready=True,
        missing_inputs=[
            "reviewed_mujoco_downstream_handoff_missing_input_should_fail_closed"
        ],
    )
    handoff_ready_with_pending_action = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_ready_pending_action.json",
        handoff_ready=True,
        next_required_for_goal=[
            {
                "action_id": "rerun_reviewed_mujoco_downstream_handoff",
                "gate": "mujoco_scene_validity",
                "title": "Rerun reviewed MuJoCo downstream handoff",
                "detail": "Pending downstream handoff action must fail closed even with ready status.",
            }
        ],
    )
    handoff_physical_truth_claimed = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_physical_truth_claimed.json",
        handoff_ready=True,
        physical_truth_claimed=True,
    )
    handoff_policy_training_authority_claimed = reviewed_mujoco_bundle_state(
        summaries / "reviewed_mujoco_bundle_policy_training_authority_claimed.json",
        handoff_ready=True,
        policy_training_authority_claimed=True,
    )
    return [
        {
            "case_id": "all_development_evidence_blocked",
            "authority": authority_blocked,
            "reviewed_mujoco_bundle": handoff_missing,
            "mujoco_scene": scene_dev,
            "chess_env": env_dev,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_dev,
            "rollouts": rollout_dev_blocked,
            "expect": {
                "ready": False,
                "reviewed_authority": False,
                "board_pick": False,
                "board_authority": False,
                "board_authority_status": "board_pick_not_reviewed_model_authority",
                "board_authority_blockers_contain": [
                    "use_reviewed_so101_model_authority_for_board_pick",
                    "repeat_board_source_pick_place_with_reviewed_model_backed_ik",
                    "remove_seeded_source_pose_from_board_pick",
                ],
                "board_detail": True,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": [
                    "supply_reviewed_so101_model_bundle_manifest",
                    "reviewed_model_backed_board_source_pick_place",
                ],
                "next_priority_gate": "reviewed_model_authority",
            },
        },
        {
            "case_id": "reviewed_authority_motion_not_checked_rejected",
            "authority": authority_motion_not_checked,
            "reviewed_mujoco_bundle": handoff_missing,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_motion": False,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["load_reviewed_model_in_mujoco"],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_but_downstream_handoff_missing",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_missing,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["make_reviewed_mujoco_downstream_handoff_ready"],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_fixture_handoff_not_training_ready",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_fixture_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": True,
                "reviewed_downstream_fixture_handoff": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["make_reviewed_mujoco_downstream_handoff_ready"],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_raw_handoff_ready_without_physical_motion_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_raw_ready_without_physical_motion,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_motion": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_physical_motion": False,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "repair_physical_reviewed_mujoco_handoff_readiness_flags"
                ],
                "blockers_contain": [
                    "repair_physical_reviewed_mujoco_handoff_readiness_flags",
                    "make_reviewed_mujoco_downstream_handoff_ready",
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_ready_with_unlimited_joint_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready_with_unlimited_joint,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_motion": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_joint_limit_enablement_ok": False,
                "reviewed_handoff_joint_limit_enablement_status": (
                    "so101_mujoco_joints_unlimited"
                ),
                "reviewed_handoff_missing_limited_joints": ["shoulder_pan"],
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "provide_reviewed_mujoco_joint_limit_enablement_evidence"
                ],
                "blockers_contain": [
                    "provide_reviewed_mujoco_joint_limit_enablement_evidence"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_schema_mismatch_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready_with_stale_schema,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_motion": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_schema": (
                    "lerobot.sim.so101_reviewed_mujoco_bundle_downstream_handoff.v0"
                ),
                "reviewed_handoff_expected_schema": (
                    SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_SCHEMA
                ),
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "provide_current_reviewed_mujoco_downstream_handoff_schema"
                ],
                "blockers_contain": [
                    "provide_current_reviewed_mujoco_downstream_handoff_schema"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_missing_model_identity_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready_missing_model_identity,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_motion": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_model_identity_contract_ok": False,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "provide_reviewed_mujoco_model_identity_evidence"
                ],
                "blockers_contain": [
                    "provide_reviewed_mujoco_model_identity_evidence"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_incomplete_handoff_items_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_incomplete_items,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_missing_items": [
                    "base_to_board_alignment",
                    "joint_limits",
                    "mesh_assets",
                    "model_authority",
                    "model_identity",
                    "mujoco_motion",
                    "target_frame",
                    "tcp_offset_m",
                ],
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "provide_complete_reviewed_mujoco_downstream_handoff_items"
                ],
                "blockers_contain": [
                    "provide_complete_reviewed_mujoco_downstream_handoff_items"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_ready_with_missing_input_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready_with_missing_input,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_missing_inputs": [
                    "reviewed_mujoco_downstream_handoff_missing_input_should_fail_closed"
                ],
                "reviewed_handoff_pending_actions": [],
                "reviewed_handoff_ready_has_open_work": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "resolve_ready_reviewed_mujoco_handoff_missing_inputs"
                ],
                "blockers_contain": [
                    "resolve_ready_reviewed_mujoco_handoff_missing_inputs"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_ready_with_pending_action_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready_with_pending_action,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_missing_inputs": [],
                "reviewed_handoff_pending_actions": [
                    "rerun_reviewed_mujoco_downstream_handoff"
                ],
                "reviewed_handoff_ready_has_open_work": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "resolve_ready_reviewed_mujoco_handoff_pending_actions"
                ],
                "blockers_contain": [
                    "resolve_ready_reviewed_mujoco_handoff_pending_actions"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_physical_truth_claim_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_physical_truth_claimed,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_physical_truth_claimed": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "remove_physical_so101_truth_claim_from_downstream_handoff"
                ],
                "blockers_contain": [
                    "remove_physical_so101_truth_claim_from_downstream_handoff"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_handoff_policy_training_authority_claim_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_policy_training_authority_claimed,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "reviewed_downstream_handoff": False,
                "reviewed_downstream_handoff_contract": False,
                "reviewed_handoff_policy_training_authority_claimed": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "handoff_contract_blockers_contain": [
                    "remove_policy_training_authority_claim_from_downstream_handoff"
                ],
                "blockers_contain": [
                    "remove_policy_training_authority_claim_from_downstream_handoff"
                ],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_authority_but_board_still_development",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_dev,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": False,
                "board_authority_status": "board_pick_not_reviewed_model_authority",
                "board_authority_blockers_contain": [
                    "use_reviewed_so101_model_authority_for_board_pick",
                ],
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "reviewed_authority_but_scene_still_development",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_dev,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["load_reviewed_model_in_mujoco"],
                "next_priority_gate": "mujoco_scene_validity",
            },
        },
        {
            "case_id": "reviewed_scene_but_gym_still_development",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_dev,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["wire_reviewed_so101_chess_gymnasium_task"],
                "next_priority_gate": "gymnasium_task_wiring",
            },
        },
        {
            "case_id": "board_draft_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_pick_state(
                summaries / "board_draft.json",
                model_authority="draft_candidate_not_reviewed",
                ready_for_model_backed_ik=True,
                seeded_source_pose=False,
            ),
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": False,
                "board_authority_status": "board_pick_not_reviewed_model_authority",
                "board_authority_blockers_contain": [
                    "use_reviewed_so101_model_authority_for_board_pick",
                ],
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_seeded_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_pick_state(
                summaries / "board_seeded_reviewed.json",
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                ready_for_model_backed_ik=True,
                seeded_source_pose=True,
            ),
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_seeded_source_pose_not_reviewed_ik",
                "board_authority_blockers_contain": [
                    "remove_seeded_source_pose_from_board_pick",
                ],
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_manual_reset_pose_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_pick_state(
                summaries / "board_manual_reset_pose_reviewed.json",
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                ready_for_model_backed_ik=True,
                seeded_source_pose=False,
                manual_piece_pose_after_reset=True,
            ),
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_manual_piece_pose_after_reset",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                    "remove_manual_piece_pose_after_reset_from_board_pick",
                ],
                "board_detail": False,
                "board_phase_ready": True,
                "board_stage_sequence_ready": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_missing_release_detail_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_missing_release,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_missing_final_contact_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_missing_final_contact,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_target_tolerance_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_target_outside_tolerance,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_missing_phase_evidence_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_missing_phase_evidence,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "board_phase_ready": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_missing_stage_sequence_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_missing_stage_sequence,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "board_phase_ready": True,
                "board_stage_sequence_ready": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_z_tolerance_missing_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_z_tolerance_missing,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "board_phase_ready": True,
                "board_place_z_within_tolerance": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_z_tolerance_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_z_outside_tolerance,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_detailed_evidence_incomplete",
                "board_authority_blockers_contain": [
                    "provide_complete_board_pick_detailed_evidence",
                ],
                "board_detail": False,
                "board_phase_ready": True,
                "board_place_z_within_tolerance": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_physical_truth_claim_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_physical_truth_claimed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_physical_truth_claimed",
                "board_authority_blockers_contain": [
                    "remove_physical_so101_truth_claim_from_board_pick",
                ],
                "board_detail": True,
                "board_physical_truth_claimed": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "board_policy_training_claim_reviewed_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed_policy_training_claimed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "board_authority_status": "board_pick_policy_training_authority_claimed",
                "board_authority_blockers_contain": [
                    "remove_policy_training_authority_claim_from_board_pick",
                ],
                "board_detail": True,
                "board_ready_for_policy_training": True,
                "board_policy_authority_claimed": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
                "next_priority_gate": "scripted_contact_grasp_pick_place",
            },
        },
        {
            "case_id": "rollout_raw_ready_development_authority_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_raw_dev.json",
                ready_for_policy_training=True,
                model_authority=DEV_AUTHORITY,
                blockers=["reviewed_model_backed_training_rollouts"],
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "rollout_reviewed_authority_not_ready",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_not_ready.json",
                ready_for_policy_training=False,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                blockers=["reviewed_model_backed_training_rollouts"],
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": False,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "rollout_reviewed_ready_failed_status_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_failed_status.json",
                ready_for_policy_training=True,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                status="failed_rollout_validation",
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_status": "failed_rollout_validation",
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "rollout_reviewed_ready_wrong_authority_status_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_wrong_authority_status.json",
                ready_for_policy_training=True,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                training_authority_status="development_rollouts_prerequisites_verified_not_policy_ready",
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_training_authority_status": "development_rollouts_prerequisites_verified_not_policy_ready",
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "rollout_reviewed_ready_debug_use_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_debug_use.json",
                ready_for_policy_training=True,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                rollout_use="debug_imitation_curriculum_only",
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_use": "debug_imitation_curriculum_only",
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "rollout_reviewed_ready_missing_policy_authority_flag_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_missing_policy_authority_flag.json",
                ready_for_policy_training=True,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                observed_policy_authority=False,
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_observed_policy_authority": False,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "rollout_reviewed_ready_nonempty_blockers_rejected",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_nonempty_blockers.json",
                ready_for_policy_training=True,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                blockers=["reviewed_model_backed_training_rollouts"],
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
                "next_priority_gate": "focused_training_rollouts",
            },
        },
        {
            "case_id": "all_ready_reviewed_contract_state",
            "authority": authority_ready,
            "reviewed_mujoco_bundle": handoff_ready,
            "mujoco_scene": scene_reviewed,
            "chess_env": env_reviewed,
            "contact": contact_ready,
            "grasp": grasp_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": True,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "board_authority_status": "reviewed_model_backed_board_source_pick_place_verified",
                "board_authority_blockers_exact": [],
                "board_detail": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": False,
                "blockers_exact": [],
                "next_priority_gate": None,
            },
        },
    ]


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def expect_contains(errors: list[str], label: str, values: Any, expected_values: list[str]) -> None:
    values = values if isinstance(values, list) else []
    for expected in expected_values:
        if expected not in values:
            errors.append(f"{label}: expected {expected!r} in {values!r}")


def summarize_case(spec: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    gate = so101_training_readiness_gate_section(
        spec["authority"],
        spec["board"],
        spec["rollouts"],
        reviewed_mujoco_bundle=spec["reviewed_mujoco_bundle"],
        mujoco_scene=spec["mujoco_scene"],
        chess_env=spec["chess_env"],
        contact_probe=spec["contact"],
        grasp_probe=spec["grasp"],
    )
    expect = spec["expect"]
    errors: list[str] = []
    add_error(errors, "ready", gate.get("ready"), expect["ready"])
    add_error(
        errors,
        "status",
        gate.get("status"),
        "serious_training_ready" if expect["ready"] else "serious_training_blocked",
    )
    add_error(
        errors,
        "reviewed_model_authority_ready",
        gate.get("reviewed_model_authority_ready"),
        expect["reviewed_authority"],
    )
    if "reviewed_motion" in expect:
        add_error(
            errors,
            "reviewed_model_physical_motion_checked",
            gate.get("reviewed_model_physical_motion_checked"),
            expect["reviewed_motion"],
        )
    if "reviewed_downstream_handoff" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_ready",
            gate.get("reviewed_mujoco_downstream_handoff_ready"),
            expect["reviewed_downstream_handoff"],
        )
    if "reviewed_downstream_handoff_contract" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_contract_ok",
            gate.get("reviewed_mujoco_downstream_handoff_contract_ok"),
            expect["reviewed_downstream_handoff_contract"],
        )
    if "reviewed_handoff_model_identity_contract_ok" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_model_identity_contract_ok",
            gate.get(
                "reviewed_mujoco_downstream_handoff_model_identity_contract_ok"
            ),
            expect["reviewed_handoff_model_identity_contract_ok"],
        )
    if "reviewed_handoff_schema" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_schema",
            gate.get("reviewed_mujoco_downstream_handoff_schema"),
            expect["reviewed_handoff_schema"],
        )
    if "reviewed_handoff_expected_schema" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_expected_schema",
            gate.get("reviewed_mujoco_downstream_handoff_expected_schema"),
            expect["reviewed_handoff_expected_schema"],
        )
    if "reviewed_downstream_fixture_handoff" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority",
            gate.get(
                "reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority"
            ),
            expect["reviewed_downstream_fixture_handoff"],
        )
    if "reviewed_handoff_physical_motion" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_physical_motion_checked",
            gate.get("reviewed_mujoco_downstream_handoff_physical_motion_checked"),
            expect["reviewed_handoff_physical_motion"],
        )
    if "reviewed_handoff_joint_limit_enablement_ok" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_joint_limit_enablement_ok",
            gate.get(
                "reviewed_mujoco_downstream_handoff_joint_limit_enablement_ok"
            ),
            expect["reviewed_handoff_joint_limit_enablement_ok"],
        )
    if "reviewed_handoff_joint_limit_enablement_status" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_joint_limit_enablement_status",
            gate.get(
                "reviewed_mujoco_downstream_handoff_joint_limit_enablement_status"
            ),
            expect["reviewed_handoff_joint_limit_enablement_status"],
        )
    if "reviewed_handoff_missing_limited_joints" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_missing_limited_joints",
            gate.get("reviewed_mujoco_downstream_handoff_missing_limited_joints"),
            expect["reviewed_handoff_missing_limited_joints"],
        )
    if "reviewed_handoff_missing_items" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_missing_item_ids",
            gate.get("reviewed_mujoco_downstream_handoff_missing_item_ids"),
            expect["reviewed_handoff_missing_items"],
        )
    if "reviewed_handoff_missing_inputs" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_missing_inputs",
            gate.get("reviewed_mujoco_downstream_handoff_missing_inputs"),
            expect["reviewed_handoff_missing_inputs"],
        )
    if "reviewed_handoff_pending_actions" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_pending_action_ids",
            gate.get("reviewed_mujoco_downstream_handoff_pending_action_ids"),
            expect["reviewed_handoff_pending_actions"],
        )
    if "reviewed_handoff_ready_has_open_work" in expect:
        add_error(
            errors,
            "reviewed_mujoco_downstream_handoff_ready_has_open_work",
            gate.get("reviewed_mujoco_downstream_handoff_ready_has_open_work"),
            expect["reviewed_handoff_ready_has_open_work"],
        )
    add_error(
        errors,
        "reviewed_mujoco_downstream_handoff_physical_truth_claimed",
        gate.get("reviewed_mujoco_downstream_handoff_physical_truth_claimed"),
        expect.get("reviewed_handoff_physical_truth_claimed", False),
    )
    add_error(
        errors,
        "reviewed_mujoco_downstream_handoff_policy_training_authority_claimed",
        gate.get(
            "reviewed_mujoco_downstream_handoff_policy_training_authority_claimed"
        ),
        expect.get("reviewed_handoff_policy_training_authority_claimed", False),
    )
    add_error(
        errors,
        "reviewed_mujoco_downstream_handoff_development_fixture_evidence_not_policy_training_truth",
        gate.get(
            "reviewed_mujoco_downstream_handoff_development_fixture_evidence_not_policy_training_truth"
        ),
        expect.get(
            "reviewed_handoff_development_fixture_evidence_not_policy_training_truth",
            True,
        ),
    )
    add_error(
        errors,
        "reviewed_model_backed_board_source_pick_place",
        gate.get("reviewed_model_backed_board_source_pick_place"),
        expect["board_pick"],
    )
    add_error(
        errors,
        "board_pick_reviewed_model_authority_ready",
        gate.get("board_pick_reviewed_model_authority_ready"),
        expect["board_authority"],
    )
    if "board_authority_status" in expect:
        add_error(
            errors,
            "board_pick_authority_status",
            gate.get("board_pick_authority_status"),
            expect["board_authority_status"],
        )
    if "board_authority_blockers_exact" in expect:
        add_error(
            errors,
            "board_pick_authority_blockers",
            gate.get("board_pick_authority_blockers"),
            expect["board_authority_blockers_exact"],
        )
    expect_contains(
        errors,
        "board_pick_authority_blockers",
        gate.get("board_pick_authority_blockers"),
        expect.get("board_authority_blockers_contain", []),
    )
    add_error(
        errors,
        "board_pick_next_required_action_ids_match_next_required",
        gate.get("board_pick_next_required_action_ids_match_next_required"),
        True,
    )
    add_error(
        errors,
        "board_pick_next_required_action_ids_missing_from_next_required",
        gate.get("board_pick_next_required_action_ids_missing_from_next_required"),
        [],
    )
    add_error(
        errors,
        "board_pick_next_required_actions_missing_from_action_ids",
        gate.get("board_pick_next_required_actions_missing_from_action_ids"),
        [],
    )
    add_error(
        errors,
        "board_pick_next_required_action_ids",
        gate.get("board_pick_next_required_action_ids"),
        gate.get("board_pick_next_required_for_goal_action_ids"),
    )
    if "board_detail" in expect:
        add_error(
            errors,
            "board_pick_detailed_evidence_ready",
            gate.get("board_pick_detailed_evidence_ready"),
            expect["board_detail"],
        )
        if expect["board_detail"] is True:
            add_error(
                errors,
                "board_pick_phase_evidence_ready",
                gate.get("board_pick_phase_evidence_ready"),
                True,
            )
            add_error(
                errors,
                "board_pick_stage_sequence_ready",
                gate.get("board_pick_stage_sequence_ready"),
                True,
            )
            add_error(
                errors,
                "board_pick_phase_ids",
                gate.get("board_pick_phase_ids"),
                list(SO101_BOARD_PICK_REQUIRED_PHASE_IDS),
            )
            add_error(
                errors,
                "board_pick_failed_phase_ids",
                gate.get("board_pick_failed_phase_ids"),
                [],
            )
            add_error(
                errors,
                "board_pick_phase_count",
                gate.get("board_pick_phase_count"),
                len(SO101_BOARD_PICK_REQUIRED_PHASE_IDS),
            )
            add_error(
                errors,
                "board_pick_all_required_phases_verified",
                gate.get("board_pick_all_required_phases_verified"),
                True,
            )
            add_error(
                errors,
                "board_pick_final_place_z_within_tolerance",
                gate.get("board_pick_final_place_z_within_tolerance"),
                True,
            )
            add_error(
                errors,
                "board_pick_lower_contact_retained_before_release",
                gate.get("board_pick_lower_contact_retained_before_release"),
                True,
            )
            add_error(
                errors,
                "board_pick_lower_board_contact_observed_before_release",
                gate.get("board_pick_lower_board_contact_observed_before_release"),
                True,
            )
            add_error(
                errors,
                "board_pick_lower_target_within_tolerance_before_release",
                gate.get("board_pick_lower_target_within_tolerance_before_release"),
                True,
            )
            add_error(
                errors,
                "board_pick_lower_place_z_within_tolerance_before_release",
                gate.get("board_pick_lower_place_z_within_tolerance_before_release"),
                True,
            )
            add_error(
                errors,
                "board_pick_lower_target_xy_within_tolerance",
                gate.get("board_pick_lower_target_xy_within_tolerance"),
                True,
            )
            add_error(
                errors,
                "board_pick_lower_place_z_within_tolerance",
                gate.get("board_pick_lower_place_z_within_tolerance"),
                True,
            )
            add_error(
                errors,
                "board_pick_observed_stage_sequence",
                gate.get("board_pick_observed_stage_sequence"),
                list(SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE),
            )
            add_error(
                errors,
                "board_pick_missing_stage_ids",
                gate.get("board_pick_missing_stage_ids"),
                [],
            )
            add_error(
                errors,
                "board_pick_manual_piece_pose_after_reset_stage_ids",
                gate.get("board_pick_manual_piece_pose_after_reset_stage_ids"),
                [],
            )
    if "board_phase_ready" in expect:
        add_error(
            errors,
            "board_pick_phase_evidence_ready",
            gate.get("board_pick_phase_evidence_ready"),
            expect["board_phase_ready"],
        )
    if "board_stage_sequence_ready" in expect:
        add_error(
            errors,
            "board_pick_stage_sequence_ready",
            gate.get("board_pick_stage_sequence_ready"),
            expect["board_stage_sequence_ready"],
        )
    if "board_place_z_within_tolerance" in expect:
        add_error(
            errors,
            "board_pick_final_place_z_within_tolerance",
            gate.get("board_pick_final_place_z_within_tolerance"),
            expect["board_place_z_within_tolerance"],
        )
    if "board_physical_truth_claimed" in expect:
        add_error(
            errors,
            "board_pick_physical_truth_claimed",
            gate.get("board_pick_physical_truth_claimed"),
            expect["board_physical_truth_claimed"],
        )
        add_error(
            errors,
            "board_pick_observed_evidence_is_physical_so101_authority",
            gate.get("board_pick_observed_evidence_is_physical_so101_authority"),
            expect["board_physical_truth_claimed"],
        )
    if "board_ready_for_policy_training" in expect:
        add_error(
            errors,
            "board_pick_ready_for_policy_training",
            gate.get("board_pick_ready_for_policy_training"),
            expect["board_ready_for_policy_training"],
        )
        add_error(
            errors,
            "board_pick_policy_training_claimed",
            gate.get("board_pick_policy_training_claimed"),
            expect["board_ready_for_policy_training"],
        )
    if "board_policy_authority_claimed" in expect:
        add_error(
            errors,
            "board_pick_policy_authority_claimed",
            gate.get("board_pick_policy_authority_claimed"),
            expect["board_policy_authority_claimed"],
        )
        add_error(
            errors,
            "board_pick_observed_evidence_is_policy_training_authority",
            gate.get("board_pick_observed_evidence_is_policy_training_authority"),
            expect["board_policy_authority_claimed"],
        )
    if "rollout_raw" in expect:
        add_error(
            errors,
            "rollout_ready_for_policy_training",
            gate.get("rollout_ready_for_policy_training"),
            expect["rollout_raw"],
        )
    if "rollout_status" in expect:
        add_error(
            errors,
            "rollout_status",
            gate.get("rollout_status"),
            expect["rollout_status"],
        )
    if "rollout_training_authority_status" in expect:
        add_error(
            errors,
            "rollout_training_authority_status",
            gate.get("rollout_training_authority_status"),
            expect["rollout_training_authority_status"],
        )
    if "rollout_use" in expect:
        add_error(
            errors,
            "rollout_use",
            gate.get("rollout_use"),
            expect["rollout_use"],
        )
    if "rollout_observed_policy_authority" in expect:
        add_error(
            errors,
            "rollout_observed_evidence_is_policy_training_authority",
            gate.get("rollout_observed_evidence_is_policy_training_authority"),
            expect["rollout_observed_policy_authority"],
        )
    add_error(
        errors,
        "rollout_policy_training_authority_ready",
        gate.get("rollout_policy_training_authority_ready"),
        expect["rollout_authority"],
    )
    add_error(
        errors,
        "development_fixture_evidence_not_policy_training_truth",
        gate.get("development_fixture_evidence_not_policy_training_truth"),
        expect["development_caveat"],
    )
    add_error(errors, "blocker_count", gate.get("blocker_count"), len(gate.get("blockers") or []))
    add_error(
        errors,
        "priority_gate_order",
        gate.get("priority_gate_order"),
        list(SO101_TRAINING_PRIORITY_STAGE_IDS),
    )
    queue = gate.get("priority_gate_queue")
    if not isinstance(queue, list):
        errors.append("priority_gate_queue: expected list")
    else:
        add_error(errors, "priority_gate_queue_count", len(queue), len(SO101_TRAINING_PRIORITY_STAGE_IDS))
        add_error(
            errors,
            "priority_gate_queue_ids",
            [stage.get("gate_id") for stage in queue],
            list(SO101_TRAINING_PRIORITY_STAGE_IDS),
        )
        for stage in queue:
            if not isinstance(stage, dict):
                errors.append("priority_gate_queue.stage: expected dict")
                continue
            gate_id = stage.get("gate_id")
            training_ready = stage.get("training_ready") is True
            automation_ready = stage.get("automation_evidence_ready") is True
            blocker_action_ids = stage.get("training_blocker_action_ids")
            if not isinstance(blocker_action_ids, list):
                errors.append(
                    f"priority_gate_queue.{gate_id}.training_blocker_action_ids: expected list"
                )
            elif training_ready and blocker_action_ids:
                errors.append(
                    f"priority_gate_queue.{gate_id}.training_blocker_action_ids: expected empty list when training ready"
                )
            elif not training_ready and not blocker_action_ids:
                errors.append(
                    f"priority_gate_queue.{gate_id}.training_blocker_action_ids: expected non-empty list while not training ready"
                )
            add_error(
                errors,
                f"priority_gate_queue.{gate_id}.automation_evidence_is_training_authority",
                stage.get("automation_evidence_is_training_authority"),
                training_ready,
            )
            add_error(
                errors,
                f"priority_gate_queue.{gate_id}.development_evidence_only_not_training_truth",
                stage.get("development_evidence_only_not_training_truth"),
                automation_ready and not training_ready,
            )
        add_error(
            errors,
            "priority_gate_training_blocker_action_ids_by_gate_id",
            gate.get("priority_gate_training_blocker_action_ids_by_gate_id"),
            {
                str(stage.get("gate_id")): stage.get("training_blocker_action_ids")
                for stage in queue
                if isinstance(stage, dict)
            },
        )
        add_error(
            errors,
            "priority_gate_development_evidence_only_not_training_truth_by_gate_id",
            gate.get("priority_gate_development_evidence_only_not_training_truth_by_gate_id"),
            {
                str(stage.get("gate_id")): stage.get(
                    "development_evidence_only_not_training_truth"
                )
                for stage in queue
                if isinstance(stage, dict)
            },
        )
    add_error(
        errors,
        "next_priority_gate_id",
        gate.get("next_priority_gate_id"),
        expect.get("next_priority_gate"),
    )
    if expect.get("next_priority_gate") is None:
        add_error(errors, "next_priority_action_ids", gate.get("next_priority_action_ids"), [])
    elif not gate.get("next_priority_action_ids"):
        errors.append("next_priority_action_ids: expected non-empty list")
    if "blockers_exact" in expect:
        add_error(errors, "blockers", gate.get("blockers"), expect["blockers_exact"])
    expect_contains(
        errors,
        "blockers",
        gate.get("blockers"),
        expect.get("blockers_contain", []),
    )
    expect_contains(
        errors,
        "reviewed_mujoco_downstream_handoff_contract_blockers",
        gate.get("reviewed_mujoco_downstream_handoff_contract_blockers"),
        expect.get("handoff_contract_blockers_contain", []),
    )

    summary_path = case_dir / "so101_training_readiness_gate.json"
    case_dir.mkdir(parents=True, exist_ok=True)
    write_json(summary_path, gate)
    artifact_payload = write_so101_training_readiness_gate_artifacts(case_dir, gate)
    artifact_paths = artifact_payload.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    priority_queue_csv_path = artifact_paths.get("priority_gate_queue_csv")
    if not isinstance(priority_queue_csv_path, str) or not Path(priority_queue_csv_path).is_file():
        errors.append("priority_gate_queue_csv: expected existing artifact path")
        priority_queue_csv_rows: list[dict[str, Any]] = []
    else:
        with Path(priority_queue_csv_path).open(newline="") as handle:
            priority_queue_csv_rows = list(csv.DictReader(handle))
        add_error(
            errors,
            "priority_gate_queue_csv_row_count",
            len(priority_queue_csv_rows),
            len(SO101_TRAINING_PRIORITY_STAGE_IDS),
        )
        add_error(
            errors,
            "priority_gate_queue_csv_gate_ids",
            [row.get("gate_id") for row in priority_queue_csv_rows],
            list(SO101_TRAINING_PRIORITY_STAGE_IDS),
        )
        for row in priority_queue_csv_rows:
            gate_id = row.get("gate_id")
            if "training_blocker_action_ids" not in row:
                errors.append(
                    f"priority_gate_queue_csv.{gate_id}.training_blocker_action_ids: missing column"
                )
            if "automation_evidence_is_training_authority" not in row:
                errors.append(
                    f"priority_gate_queue_csv.{gate_id}.automation_evidence_is_training_authority: missing column"
                )
            if "development_evidence_only_not_training_truth" not in row:
                errors.append(
                    f"priority_gate_queue_csv.{gate_id}.development_evidence_only_not_training_truth: missing column"
                )
    return {
        "case_id": spec["case_id"],
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "summary_path": str(summary_path),
        "artifacts": artifact_paths,
        "gate": gate,
    }


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    gate = case["gate"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "gate_status": gate.get("status"),
        "gate_ready": gate.get("ready"),
        "reviewed_model_authority_ready": gate.get("reviewed_model_authority_ready"),
        "reviewed_model_physical_motion_checked": gate.get(
            "reviewed_model_physical_motion_checked"
        ),
        "reviewed_mujoco_downstream_handoff_contract_ok": gate.get(
            "reviewed_mujoco_downstream_handoff_contract_ok"
        ),
        "reviewed_mujoco_downstream_handoff_contract_status": gate.get(
            "reviewed_mujoco_downstream_handoff_contract_status"
        ),
        "reviewed_mujoco_downstream_handoff_schema": gate.get(
            "reviewed_mujoco_downstream_handoff_schema"
        ),
        "reviewed_mujoco_downstream_handoff_expected_schema": gate.get(
            "reviewed_mujoco_downstream_handoff_expected_schema"
        ),
        "reviewed_mujoco_downstream_handoff_raw_ready": gate.get(
            "reviewed_mujoco_downstream_handoff_raw_ready"
        ),
        "reviewed_mujoco_downstream_handoff_ready": gate.get(
            "reviewed_mujoco_downstream_handoff_ready"
        ),
        "reviewed_mujoco_downstream_handoff_status": gate.get(
            "reviewed_mujoco_downstream_handoff_status"
        ),
        "reviewed_mujoco_downstream_handoff_model_authority": gate.get(
            "reviewed_mujoco_downstream_handoff_model_authority"
        ),
        "reviewed_mujoco_downstream_handoff_model_identity_contract_ok": gate.get(
            "reviewed_mujoco_downstream_handoff_model_identity_contract_ok"
        ),
        "reviewed_mujoco_downstream_handoff_model_identity_status": gate.get(
            "reviewed_mujoco_downstream_handoff_model_identity_status"
        ),
        "reviewed_mujoco_downstream_handoff_model_identity_matches": gate.get(
            "reviewed_mujoco_downstream_handoff_model_identity_matches"
        ),
        "reviewed_mujoco_downstream_handoff_model_path": gate.get(
            "reviewed_mujoco_downstream_handoff_model_path"
        ),
        "reviewed_mujoco_downstream_handoff_physical_truth_claimed": gate.get(
            "reviewed_mujoco_downstream_handoff_physical_truth_claimed"
        ),
        "reviewed_mujoco_downstream_handoff_policy_training_authority_claimed": gate.get(
            "reviewed_mujoco_downstream_handoff_policy_training_authority_claimed"
        ),
        "reviewed_mujoco_downstream_handoff_development_fixture_evidence_not_policy_training_truth": gate.get(
            "reviewed_mujoco_downstream_handoff_development_fixture_evidence_not_policy_training_truth"
        ),
        "reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority": gate.get(
            "reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority"
        ),
        "reviewed_mujoco_downstream_handoff_physical_motion_checked": gate.get(
            "reviewed_mujoco_downstream_handoff_physical_motion_checked"
        ),
        "reviewed_mujoco_downstream_handoff_hardware_free_fixture_motion_checked": gate.get(
            "reviewed_mujoco_downstream_handoff_hardware_free_fixture_motion_checked"
        ),
        "reviewed_mujoco_downstream_handoff_joint_limit_enablement_ok": gate.get(
            "reviewed_mujoco_downstream_handoff_joint_limit_enablement_ok"
        ),
        "reviewed_mujoco_downstream_handoff_joint_limit_enablement_status": gate.get(
            "reviewed_mujoco_downstream_handoff_joint_limit_enablement_status"
        ),
        "reviewed_mujoco_downstream_handoff_missing_limited_joints": gate.get(
            "reviewed_mujoco_downstream_handoff_missing_limited_joints"
        ),
        "reviewed_mujoco_downstream_handoff_required_limited_joints": gate.get(
            "reviewed_mujoco_downstream_handoff_required_limited_joints"
        ),
        "reviewed_mujoco_downstream_handoff_missing_item_ids": gate.get(
            "reviewed_mujoco_downstream_handoff_missing_item_ids"
        ),
        "reviewed_mujoco_downstream_handoff_missing_inputs": gate.get(
            "reviewed_mujoco_downstream_handoff_missing_inputs"
        ),
        "reviewed_mujoco_downstream_handoff_pending_action_ids": gate.get(
            "reviewed_mujoco_downstream_handoff_pending_action_ids"
        ),
        "reviewed_mujoco_downstream_handoff_ready_has_open_work": gate.get(
            "reviewed_mujoco_downstream_handoff_ready_has_open_work"
        ),
        "reviewed_mujoco_downstream_handoff_contract_blockers": gate.get(
            "reviewed_mujoco_downstream_handoff_contract_blockers"
        ),
        "reviewed_mujoco_downstream_handoff_priority_gate_id": gate.get(
            "reviewed_mujoco_downstream_handoff_priority_gate_id"
        ),
        "reviewed_mujoco_downstream_handoff_priority_gate_order": gate.get(
            "reviewed_mujoco_downstream_handoff_priority_gate_order"
        ),
        "reviewed_mujoco_downstream_handoff_next_downstream_gate_after_ready": gate.get(
            "reviewed_mujoco_downstream_handoff_next_downstream_gate_after_ready"
        ),
        "reviewed_mujoco_downstream_handoff_blocks_downstream_gates_until_ready": gate.get(
            "reviewed_mujoco_downstream_handoff_blocks_downstream_gates_until_ready"
        ),
        "reviewed_mujoco_downstream_handoff_ready_does_not_imply_policy_training_ready": gate.get(
            "reviewed_mujoco_downstream_handoff_ready_does_not_imply_policy_training_ready"
        ),
        "reviewed_mujoco_downstream_handoff_priority_contract_ok": gate.get(
            "reviewed_mujoco_downstream_handoff_priority_contract_ok"
        ),
        "reviewed_model_backed_board_source_pick_place": gate.get(
            "reviewed_model_backed_board_source_pick_place"
        ),
        "board_pick_reviewed_model_authority_ready": gate.get(
            "board_pick_reviewed_model_authority_ready"
        ),
        "board_pick_authority_status": gate.get("board_pick_authority_status"),
        "board_pick_authority_blockers": gate.get("board_pick_authority_blockers"),
        "board_pick_detailed_evidence_ready": gate.get("board_pick_detailed_evidence_ready"),
        "board_pick_observed_evidence_is_physical_so101_authority": gate.get(
            "board_pick_observed_evidence_is_physical_so101_authority"
        ),
        "board_pick_observed_evidence_is_policy_training_authority": gate.get(
            "board_pick_observed_evidence_is_policy_training_authority"
        ),
        "board_pick_ready_for_policy_training": gate.get(
            "board_pick_ready_for_policy_training"
        ),
        "board_pick_physical_truth_claimed": gate.get(
            "board_pick_physical_truth_claimed"
        ),
        "board_pick_policy_training_claimed": gate.get(
            "board_pick_policy_training_claimed"
        ),
        "board_pick_policy_authority_claimed": gate.get(
            "board_pick_policy_authority_claimed"
        ),
        "board_pick_next_required_action_ids": gate.get(
            "board_pick_next_required_action_ids"
        ),
        "board_pick_next_required_for_goal_action_ids": gate.get(
            "board_pick_next_required_for_goal_action_ids"
        ),
        "board_pick_next_required_action_ids_match_next_required": gate.get(
            "board_pick_next_required_action_ids_match_next_required"
        ),
        "board_pick_next_required_action_ids_missing_from_next_required": gate.get(
            "board_pick_next_required_action_ids_missing_from_next_required"
        ),
        "board_pick_next_required_actions_missing_from_action_ids": gate.get(
            "board_pick_next_required_actions_missing_from_action_ids"
        ),
        "board_pick_phase_evidence_ready": gate.get("board_pick_phase_evidence_ready"),
        "board_pick_stage_sequence_ready": gate.get("board_pick_stage_sequence_ready"),
        "board_pick_phase_ids": gate.get("board_pick_phase_ids"),
        "board_pick_failed_phase_ids": gate.get("board_pick_failed_phase_ids"),
        "board_pick_phase_count": gate.get("board_pick_phase_count"),
        "board_pick_all_required_phases_verified": gate.get(
            "board_pick_all_required_phases_verified"
        ),
        "board_pick_stage_sequence_contract_ok": gate.get(
            "board_pick_stage_sequence_contract_ok"
        ),
        "board_pick_stage_sequence_order_ok": gate.get(
            "board_pick_stage_sequence_order_ok"
        ),
        "board_pick_observed_stage_sequence": gate.get(
            "board_pick_observed_stage_sequence"
        ),
        "board_pick_missing_stage_ids": gate.get("board_pick_missing_stage_ids"),
        "board_pick_unexpected_stage_ids": gate.get("board_pick_unexpected_stage_ids"),
        "board_pick_stage_sequence_contract_errors": gate.get(
            "board_pick_stage_sequence_contract_errors"
        ),
        "board_pick_manual_piece_pose_after_reset_stage_ids": gate.get(
            "board_pick_manual_piece_pose_after_reset_stage_ids"
        ),
        "board_pick_lower_contact_retained_before_release": gate.get(
            "board_pick_lower_contact_retained_before_release"
        ),
        "board_pick_lower_board_contact_observed_before_release": gate.get(
            "board_pick_lower_board_contact_observed_before_release"
        ),
        "board_pick_lower_target_within_tolerance_before_release": gate.get(
            "board_pick_lower_target_within_tolerance_before_release"
        ),
        "board_pick_lower_place_z_within_tolerance_before_release": gate.get(
            "board_pick_lower_place_z_within_tolerance_before_release"
        ),
        "board_pick_lower_target_xy_error_m": gate.get("board_pick_lower_target_xy_error_m"),
        "board_pick_target_xy_tolerance_m": gate.get("board_pick_target_xy_tolerance_m"),
        "board_pick_lower_target_xy_within_tolerance": gate.get(
            "board_pick_lower_target_xy_within_tolerance"
        ),
        "board_pick_lower_place_z_error_m": gate.get("board_pick_lower_place_z_error_m"),
        "board_pick_lower_place_z_within_tolerance": gate.get(
            "board_pick_lower_place_z_within_tolerance"
        ),
        "board_pick_final_place_z_error_m": gate.get("board_pick_final_place_z_error_m"),
        "board_pick_place_z_tolerance_m": gate.get("board_pick_place_z_tolerance_m"),
        "board_pick_final_place_z_within_tolerance": gate.get(
            "board_pick_final_place_z_within_tolerance"
        ),
        "rollout_ready_for_policy_training": gate.get("rollout_ready_for_policy_training"),
        "rollout_status": gate.get("rollout_status"),
        "rollout_training_authority_status": gate.get("rollout_training_authority_status"),
        "rollout_use": gate.get("rollout_use"),
        "rollout_observed_evidence_is_policy_training_authority": gate.get(
            "rollout_observed_evidence_is_policy_training_authority"
        ),
        "rollout_policy_training_authority_ready": gate.get(
            "rollout_policy_training_authority_ready"
        ),
        "development_fixture_evidence_not_policy_training_truth": gate.get(
            "development_fixture_evidence_not_policy_training_truth"
        ),
        "next_priority_gate_id": gate.get("next_priority_gate_id"),
        "next_priority_action_ids": gate.get("next_priority_action_ids"),
        "priority_gate_order": gate.get("priority_gate_order"),
        "priority_gate_training_blocker_action_ids_by_gate_id": gate.get(
            "priority_gate_training_blocker_action_ids_by_gate_id"
        ),
        "priority_gate_development_evidence_only_not_training_truth_by_gate_id": gate.get(
            "priority_gate_development_evidence_only_not_training_truth_by_gate_id"
        ),
        "priority_gate_queue_csv": case.get("artifacts", {}).get("priority_gate_queue_csv"),
        "blockers": gate.get("blockers"),
        "expected_gate_ready": case["expected"].get("ready"),
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Training Readiness Gate Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "Caveat: this is a contract-state smoke. It injects reviewed-authority, board-pick, and rollout dictionaries to exercise serious-training gate transitions; it is not policy-training authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Ready | Next Gate | Handoff Contract | Handoff | Board Pick | Board Authority Status | Rollout Authority | Fixture Caveat | Blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        gate = case["gate"]
        lines.append(
            "| `{case_id}` | `{status}` | `{ready}` | `{next_gate}` | `{handoff_contract}` | `{handoff}` | `{board}` | `{board_status}` | `{rollout}` | `{fixture}` | `{blockers}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                ready=gate.get("ready"),
                next_gate=gate.get("next_priority_gate_id") or "none",
                handoff_contract=gate.get(
                    "reviewed_mujoco_downstream_handoff_contract_ok"
                ),
                handoff=gate.get("reviewed_mujoco_downstream_handoff_ready"),
                board=gate.get("reviewed_model_backed_board_source_pick_place"),
                board_status=gate.get("board_pick_authority_status"),
                rollout=gate.get("rollout_policy_training_authority_ready"),
                fixture=gate.get("development_fixture_evidence_not_policy_training_truth"),
                blockers=", ".join(gate.get("blockers") or []),
            )
        )
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- `all_ready_reviewed_contract_state` exercises the ready branch only; its injected dictionaries are not reviewed robot evidence.",
            "- `priority_gate_queue` preserves reviewed authority, reviewed MuJoCo handoff and scene validity, Gymnasium task wiring, scripted pick/place, then training rollout order.",
            "- Each case writes `so101_training_readiness_gate_priority_queue.csv` so the prioritized missing-gate order is reviewable without parsing nested JSON.",
            "- Draft, development, and fixture-only model-authority labels are rejected even when raw readiness booleans are true.",
            "- Reviewed-MuJoCo downstream handoff readiness requires a complete current-schema summary-level handoff contract; raw-ready, fixture-only, stale-schema, incomplete, or physical-truth-claiming handoffs cannot unblock training.",
            "- Board-pick readiness requires detailed source-start, contact, lift, transfer, place, release, final-board-contact, and target-tolerance evidence without physical SO-101 truth or policy-training authority overclaims.",
            "- Reviewed rollout readiness requires status `ok`, reviewed-policy-ready authority status, `policy_training` use, policy-authority evidence, and no serious-policy blockers.",
            "- Use this smoke to protect training-readiness gate logic. Use reviewed SO-101 model-backed pick/place and rollout evidence before serious training.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve(strict=False)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        summarize_case(spec, output_dir / "cases" / spec["case_id"])
        for spec in case_specs(output_dir)
    ]
    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_training_readiness_gate_matrix_summary.json"
    csv_path = output_dir / "so101_training_readiness_gate_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "training_readiness_contract_matrix_not_authority",
        "observed_evidence_is_policy_training_authority": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "This matrix injects state dictionaries and does not load a reviewed SO-101 model or train a policy.",
            "The all-ready case exercises the gate's ready branch and must not be cited as serious policy-training evidence.",
            "Development or draft model-authority strings remain blocked even when raw readiness booleans are true.",
        ],
    }
    write_json(summary_path, summary)
    write_csv(csv_path, [flatten_case(case) for case in cases])
    write_readme(readme_path, summary)

    print(
        json.dumps(
            {
                "ok": ok,
                "status": summary["status"],
                "summary_json": str(summary_path),
                "cases_csv": str(csv_path),
                "readme_md": str(readme_path),
                "case_ids": summary["case_ids"],
                "failed_cases": summary["failed_case_ids"],
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
