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


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_scene"
SUMMARY_NAME = "so101_mujoco_scene_summary.json"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
STEPS_NAME = "so101_mujoco_scene_env_steps.csv"
README_NAME = "README.md"
SO101_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
REQUIRED_MODEL_JOINTS: tuple[str, ...] = (*SO101_JOINTS, "piece_source_freejoint")
REQUIRED_LIMITED_JOINTS: tuple[str, ...] = SO101_JOINTS
REQUIRED_BODIES: tuple[str, ...] = ("chess_board", "piece_source")
REQUIRED_GRIPPER_COLLISION_GEOMS: tuple[str, ...] = (
    "gripper_fixed_finger_collision",
    "gripper_moving_finger_collision",
)
REQUIRED_GEOMS: tuple[str, ...] = (
    "chess_board_collision",
    "piece_source_collision",
    *REQUIRED_GRIPPER_COLLISION_GEOMS,
    "target_square_marker",
)
REQUIRED_SITES: tuple[str, ...] = ("gripper_frame_link",)
DEVELOPMENT_MODEL_AUTHORITY = "development_scaffold_not_reviewed"
DOWNSTREAM_HANDOFF_MODEL_AUTHORITY = "downstream_handoff_not_authority"
DOWNSTREAM_HANDOFF_SCHEMA = "lerobot.sim.so101_reviewed_mujoco_bundle_downstream_handoff.v1"
DOWNSTREAM_HANDOFF_PRIORITY_GATE_ID = "reviewed_mujoco_handoff"
EXPECTED_DOWNSTREAM_HANDOFF_ITEM_IDS: tuple[str, ...] = (
    "model_authority",
    "model_identity",
    "target_frame",
    "tcp_offset_m",
    "base_to_board_alignment",
    "joint_limits",
    "mesh_assets",
    "mujoco_motion",
    "downstream_gate_handoff",
)
EXPECTED_DOWNSTREAM_HANDOFF_GATES: tuple[str, ...] = (
    "mujoco_scene_validity",
    "gymnasium_task_wiring",
    "reviewed_model_backed_contact_grasp_pick_place",
)
NEXT_DOWNSTREAM_GATE_AFTER_READY = EXPECTED_DOWNSTREAM_HANDOFF_GATES[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate and validate a development-only SO-101 MuJoCo chess scene. "
            "This proves MuJoCo plumbing, board/piece collision geoms, joint sync, "
            "and Gymnasium environment reset/step without claiming reviewed model authority."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--max-steps", type=int, default=96)
    parser.add_argument(
        "--reviewed-mujoco-handoff-json",
        type=Path,
        default=None,
        help=(
            "Optional reviewed MuJoCo downstream handoff JSON from "
            "smoke_sim_so101_reviewed_mujoco_bundle.py. The generated scene stays "
            "development-only; this intake records whether reviewed scene work is "
            "blocked by the handoff gate."
        ),
    )
    parser.add_argument(
        "--require-reviewed-mujoco-handoff",
        action="store_true",
        help="Fail closed unless --reviewed-mujoco-handoff-json is present and downstream_handoff_ready is true.",
    )
    return parser.parse_args()


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def write_steps(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "step",
        "waypoint",
        "phase_index",
        "reward",
        "terminated",
        "truncated",
        "piece_square",
        "holding_piece",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def handoff_intake_result(
    *,
    requested: bool,
    required: bool,
    path: str | None,
    status: str,
    intake_ok: bool,
    ready: bool,
    source_status: Any = None,
    model_authority: Any = None,
    observed_evidence_is_authority: Any = None,
    physical_truth_claimed: Any = None,
    policy_training_authority_claimed: Any = None,
    fixture_ready: bool = False,
    item_ids: list[str] | None = None,
    blockers: list[str] | None = None,
    schema: Any = None,
    contract_ok: bool = False,
    motion_authority_status: Any = None,
    physical_motion_checked: bool = False,
    fixture_motion_checked: bool = False,
    motion_evidence_not_physical: Any = None,
    physical_model_authority_ready: Any = None,
    model_identity_contract_ok: bool = False,
    model_identity_status: Any = None,
    model_identity_matches: Any = None,
    reviewed_model_path: Any = None,
    reviewed_model_declared_sha256: Any = None,
    reviewed_model_observed_sha256: Any = None,
    joint_limit_enablement_ok: bool = False,
    joint_limit_enablement_status: Any = None,
    missing_limited_joints: list[str] | None = None,
    missing_inputs: list[str] | None = None,
    pending_action_ids: list[str] | None = None,
    ready_handoff_has_open_work: bool = False,
    gates_unblocked_when_physical_ready: list[str] | None = None,
    blocked_gates_until_physical_ready: list[str] | None = None,
    priority_gate_id: Any = None,
    priority_gate_order: list[str] | None = None,
    next_downstream_gate_after_ready: Any = None,
    blocks_downstream_gates_until_ready: Any = None,
    ready_does_not_imply_policy_training_ready: Any = None,
    priority_contract_ok: bool = False,
) -> dict[str, Any]:
    return {
        "reviewed_mujoco_handoff_requested": requested,
        "reviewed_mujoco_handoff_required": required,
        "reviewed_mujoco_handoff_path": path,
        "reviewed_mujoco_handoff_intake_status": status,
        "reviewed_mujoco_handoff_intake_ok": intake_ok,
        "reviewed_mujoco_handoff_contract_ok": contract_ok,
        "reviewed_mujoco_handoff_ready": ready,
        "reviewed_mujoco_handoff_source_status": source_status,
        "reviewed_mujoco_handoff_schema": schema,
        "reviewed_mujoco_handoff_model_authority": model_authority,
        "reviewed_mujoco_handoff_observed_evidence_is_authority": (
            observed_evidence_is_authority
        ),
        "reviewed_mujoco_handoff_physical_truth_claimed": physical_truth_claimed,
        "reviewed_mujoco_handoff_policy_training_authority_claimed": (
            policy_training_authority_claimed
        ),
        "reviewed_mujoco_fixture_handoff_ready_not_physical_so101_authority": (
            fixture_ready
        ),
        "reviewed_mujoco_handoff_motion_authority_status": motion_authority_status,
        "reviewed_mujoco_handoff_physical_motion_checked": physical_motion_checked,
        "reviewed_mujoco_handoff_hardware_free_fixture_motion_checked": (
            fixture_motion_checked
        ),
        "reviewed_mujoco_handoff_motion_evidence_not_physical_so101_authority": (
            motion_evidence_not_physical
        ),
        "reviewed_mujoco_handoff_physical_so101_model_authority_ready": (
            physical_model_authority_ready
        ),
        "reviewed_mujoco_handoff_model_identity_contract_ok": (
            model_identity_contract_ok
        ),
        "reviewed_mujoco_handoff_model_identity_status": model_identity_status,
        "reviewed_mujoco_handoff_model_identity_matches": model_identity_matches,
        "reviewed_mujoco_handoff_model_path": reviewed_model_path,
        "reviewed_mujoco_handoff_declared_model_sha256": (
            reviewed_model_declared_sha256
        ),
        "reviewed_mujoco_handoff_observed_model_sha256": (
            reviewed_model_observed_sha256
        ),
        "reviewed_mujoco_handoff_joint_limit_enablement_ok": (
            joint_limit_enablement_ok
        ),
        "reviewed_mujoco_handoff_joint_limit_enablement_status": (
            joint_limit_enablement_status
        ),
        "reviewed_mujoco_handoff_missing_limited_joints": (
            missing_limited_joints or []
        ),
        "reviewed_mujoco_handoff_missing_inputs": missing_inputs or [],
        "reviewed_mujoco_handoff_pending_action_ids": pending_action_ids or [],
        "reviewed_mujoco_handoff_ready_has_open_work": ready_handoff_has_open_work,
        "reviewed_mujoco_handoff_gates_unblocked_when_physical_ready": (
            gates_unblocked_when_physical_ready or []
        ),
        "reviewed_mujoco_handoff_blocked_gates_until_physical_ready": (
            blocked_gates_until_physical_ready or []
        ),
        "reviewed_mujoco_handoff_priority_gate_id": priority_gate_id,
        "reviewed_mujoco_handoff_priority_gate_order": priority_gate_order or [],
        "reviewed_mujoco_handoff_next_downstream_gate_after_ready": (
            next_downstream_gate_after_ready
        ),
        "reviewed_mujoco_handoff_blocks_downstream_gates_until_ready": (
            blocks_downstream_gates_until_ready
        ),
        "reviewed_mujoco_handoff_ready_does_not_imply_policy_training_ready": (
            ready_does_not_imply_policy_training_ready
        ),
        "reviewed_mujoco_handoff_priority_contract_ok": priority_contract_ok,
        "reviewed_mujoco_handoff_item_ids": item_ids or [],
        "reviewed_mujoco_handoff_blockers": blockers or [],
    }


def reviewed_handoff_intake(
    path: Path | None,
    *,
    required: bool,
) -> dict[str, Any]:
    if path is None:
        return handoff_intake_result(
            requested=False,
            required=required,
            path=None,
            status="not_requested",
            intake_ok=not required,
            ready=False,
            blockers=["supply_reviewed_mujoco_downstream_handoff"] if required else [],
        )

    resolved = path.expanduser().resolve(strict=False)
    if not resolved.is_file():
        return handoff_intake_result(
            requested=True,
            required=required,
            path=str(resolved),
            status="handoff_json_missing",
            intake_ok=False,
            ready=False,
            blockers=["supply_reviewed_mujoco_downstream_handoff"],
        )

    try:
        payload = json.loads(resolved.read_text())
    except Exception as exc:
        return handoff_intake_result(
            requested=True,
            required=required,
            path=str(resolved),
            status="handoff_json_parse_error",
            intake_ok=False,
            ready=False,
            blockers=[f"{type(exc).__name__}: {exc}"],
        )
    if not isinstance(payload, dict):
        return handoff_intake_result(
            requested=True,
            required=required,
            path=str(resolved),
            status="handoff_json_not_object",
            intake_ok=False,
            ready=False,
            blockers=["handoff_json_not_object"],
        )

    item_ids = payload.get("handoff_item_ids")
    item_ids = [str(item) for item in item_ids] if isinstance(item_ids, list) else []
    missing_item_ids = sorted(set(EXPECTED_DOWNSTREAM_HANDOFF_ITEM_IDS) - set(item_ids))
    handoff_item_count = payload.get("handoff_item_count")
    item_count_ok = (
        isinstance(handoff_item_count, int)
        and handoff_item_count == len(item_ids)
        and handoff_item_count >= len(EXPECTED_DOWNSTREAM_HANDOFF_ITEM_IDS)
    )
    raw_ready = payload.get("downstream_handoff_ready") is True
    physical_motion_checked = payload.get("physical_reviewed_model_motion_checked") is True
    fixture_motion_checked = payload.get("hardware_free_fixture_motion_checked") is True
    fixture_ready = (
        payload.get("fixture_handoff_ready_not_physical_so101_authority") is True
    )
    raw_missing_inputs = payload.get("missing_inputs")
    handoff_missing_inputs = unique_strings(
        raw_missing_inputs if isinstance(raw_missing_inputs, list) else []
    )
    handoff_next_required = payload.get("next_required_for_goal")
    handoff_next_required_action_ids = unique_strings(
        [
            action.get("action_id") if isinstance(action, dict) else action
            for action in handoff_next_required
        ]
        if isinstance(handoff_next_required, list)
        else []
    )
    raw_explicit_action_ids = payload.get("next_required_action_ids")
    handoff_explicit_action_ids = unique_strings(
        raw_explicit_action_ids if isinstance(raw_explicit_action_ids, list) else []
    )
    handoff_pending_action_ids = unique_strings(
        [
            *handoff_explicit_action_ids,
            *handoff_next_required_action_ids,
        ]
    )
    raw_gates_unblocked = payload.get("gates_unblocked_when_physical_handoff_ready")
    gates_unblocked = unique_strings(
        raw_gates_unblocked if isinstance(raw_gates_unblocked, list) else []
    )
    raw_blocked_gates = payload.get("blocked_gates_until_physical_handoff_ready")
    blocked_gates = unique_strings(
        raw_blocked_gates if isinstance(raw_blocked_gates, list) else []
    )
    expected_gates = list(EXPECTED_DOWNSTREAM_HANDOFF_GATES)
    expected_blocked_gates = [] if raw_ready else expected_gates
    gate_contract_ok = (
        gates_unblocked == expected_gates and blocked_gates == expected_blocked_gates
    )
    raw_priority_gate_order = payload.get("downstream_priority_gate_order")
    priority_gate_order = unique_strings(
        raw_priority_gate_order if isinstance(raw_priority_gate_order, list) else []
    )
    priority_gate_id = payload.get("downstream_priority_gate_id")
    next_downstream_gate_after_ready = payload.get("next_downstream_gate_after_ready")
    blocks_downstream_gates_until_ready = payload.get(
        "blocks_downstream_gates_until_ready"
    )
    ready_does_not_imply_policy_training_ready = payload.get(
        "ready_does_not_imply_policy_training_ready"
    )
    priority_contract_ok = (
        priority_gate_id == DOWNSTREAM_HANDOFF_PRIORITY_GATE_ID
        and priority_gate_order == expected_gates
        and next_downstream_gate_after_ready == NEXT_DOWNSTREAM_GATE_AFTER_READY
        and blocks_downstream_gates_until_ready is True
        and ready_does_not_imply_policy_training_ready is True
    )
    ready_handoff_has_open_work = (raw_ready or fixture_ready) and bool(
        handoff_missing_inputs or handoff_pending_action_ids
    )
    motion_authority_status = payload.get("motion_authority_status")
    physical_model_authority_ready = payload.get("physical_so101_model_authority_ready")
    policy_training_authority_claimed = payload.get("policy_training_authority_claimed")
    motion_evidence_not_physical = payload.get(
        "motion_evidence_not_physical_so101_authority"
    )
    calibration_inputs = payload.get("calibration_inputs")
    calibration_inputs = (
        calibration_inputs if isinstance(calibration_inputs, dict) else {}
    )
    nested_model_path = calibration_inputs.get("model_path")
    nested_model_path = nested_model_path if isinstance(nested_model_path, dict) else {}
    nested_model_identity = calibration_inputs.get("model_identity")
    nested_model_identity = (
        nested_model_identity if isinstance(nested_model_identity, dict) else {}
    )
    reviewed_model_identity = payload.get("reviewed_model_identity")
    reviewed_model_identity = (
        reviewed_model_identity if isinstance(reviewed_model_identity, dict) else {}
    )
    reviewed_model_path = payload.get("reviewed_model_path") or reviewed_model_identity.get(
        "model_path"
    ) or nested_model_path.get("path")
    reviewed_model_declared_sha256 = (
        payload.get("reviewed_model_declared_sha256")
        or reviewed_model_identity.get("declared_sha256")
        or nested_model_identity.get("declared_sha256")
    )
    reviewed_model_observed_sha256 = (
        payload.get("reviewed_model_observed_sha256")
        or reviewed_model_identity.get("observed_sha256")
        or nested_model_identity.get("observed_sha256")
    )
    reviewed_model_identity_status = (
        payload.get("reviewed_model_identity_status")
        or reviewed_model_identity.get("status")
        or nested_model_identity.get("status")
    )
    reviewed_model_identity_matches = (
        payload.get("reviewed_model_identity_matches")
        if "reviewed_model_identity_matches" in payload
        else reviewed_model_identity.get("matches")
        if "matches" in reviewed_model_identity
        else nested_model_identity.get("matches")
    )
    reviewed_model_identity_contract_ok = (
        payload.get("reviewed_model_identity_contract_ok") is True
        and isinstance(reviewed_model_path, str)
        and bool(reviewed_model_path)
        and reviewed_model_identity_status == "present"
        and reviewed_model_identity_matches is True
        and isinstance(reviewed_model_declared_sha256, str)
        and isinstance(reviewed_model_observed_sha256, str)
        and bool(reviewed_model_declared_sha256)
        and reviewed_model_declared_sha256 == reviewed_model_observed_sha256
    )
    mujoco_motion_inputs = payload.get("mujoco_motion_inputs")
    mujoco_motion_inputs = (
        mujoco_motion_inputs if isinstance(mujoco_motion_inputs, dict) else {}
    )
    joint_limit_enablement = mujoco_motion_inputs.get("mujoco_joint_limit_enablement")
    joint_limit_enablement = (
        joint_limit_enablement if isinstance(joint_limit_enablement, dict) else {}
    )
    joint_limit_enablement_status = joint_limit_enablement.get("status")
    raw_missing_limited_joints = joint_limit_enablement.get("missing_limited_joints")
    missing_limited_joints = unique_strings(
        raw_missing_limited_joints
        if isinstance(raw_missing_limited_joints, list)
        else []
    )
    joint_limit_enablement_ok = (
        joint_limit_enablement.get("ok") is True
        and joint_limit_enablement_status == "so101_mujoco_joints_limited"
        and missing_limited_joints == []
    )
    physical_ready_contract_ok = (
        not raw_ready
        or (
            physical_motion_checked
            and payload.get("status") == "physical_reviewed_mujoco_handoff_ready"
            and motion_authority_status == "physical_reviewed_model_motion_checked"
            and physical_model_authority_ready is True
            and fixture_ready is False
            and fixture_motion_checked is False
            and motion_evidence_not_physical is False
        )
    )
    fixture_contract_ok = (
        not fixture_ready
        or (
            raw_ready is False
            and physical_motion_checked is False
            and fixture_motion_checked is True
            and motion_authority_status
            == "hardware_free_fixture_motion_checked_not_physical_so101_authority"
            and motion_evidence_not_physical is True
        )
    )
    contract_ok = (
        payload.get("schema") == DOWNSTREAM_HANDOFF_SCHEMA
        and payload.get("model_authority") == DOWNSTREAM_HANDOFF_MODEL_AUTHORITY
        and payload.get("observed_evidence_is_authority") is False
        and payload.get("physical_so101_truth_claimed") is False
        and policy_training_authority_claimed is False
        and payload.get("development_fixture_evidence_not_physical_so101_truth") is True
        and item_count_ok
        and not missing_item_ids
        and payload.get("downstream_handoff_ready") == physical_motion_checked
        and payload.get("reviewed_model_motion_checked") == (
            physical_motion_checked or fixture_motion_checked
        )
        and gate_contract_ok
        and priority_contract_ok
        and not ready_handoff_has_open_work
        and (not (raw_ready or fixture_ready) or joint_limit_enablement_ok)
        and (not (raw_ready or fixture_ready) or reviewed_model_identity_contract_ok)
        and physical_ready_contract_ok
        and fixture_contract_ok
    )
    ready = contract_ok and raw_ready
    if not contract_ok:
        intake_status = "handoff_contract_invalid"
    elif ready:
        intake_status = "reviewed_mujoco_handoff_ready_for_scene_intake"
    elif fixture_ready:
        intake_status = "fixture_handoff_not_physical_so101_authority"
    else:
        intake_status = "reviewed_mujoco_handoff_not_ready"
    blockers = []
    if payload.get("model_authority") != DOWNSTREAM_HANDOFF_MODEL_AUTHORITY:
        blockers.append("repair_reviewed_mujoco_downstream_handoff_authority")
    if payload.get("observed_evidence_is_authority") is not False:
        blockers.append("mark_downstream_handoff_as_non_authority_snapshot")
    if payload.get("physical_so101_truth_claimed") is True:
        blockers.append("remove_physical_so101_truth_claim_from_downstream_handoff")
    if policy_training_authority_claimed is not False:
        blockers.append("remove_policy_training_authority_claim_from_downstream_handoff")
    if payload.get("development_fixture_evidence_not_physical_so101_truth") is not True:
        blockers.append("mark_downstream_handoff_development_fixture_boundary")
    if payload.get("schema") != DOWNSTREAM_HANDOFF_SCHEMA:
        blockers.append("provide_current_reviewed_mujoco_downstream_handoff_schema")
    if missing_item_ids:
        blockers.append("provide_complete_reviewed_mujoco_downstream_handoff_items")
    if not item_count_ok:
        blockers.append("fix_reviewed_mujoco_downstream_handoff_item_count")
    if gates_unblocked != expected_gates:
        blockers.append("provide_reviewed_mujoco_downstream_handoff_unblocked_gate_list")
    if blocked_gates != expected_blocked_gates:
        blockers.append("provide_reviewed_mujoco_downstream_handoff_blocked_gate_list")
    if priority_gate_id != DOWNSTREAM_HANDOFF_PRIORITY_GATE_ID:
        blockers.append("provide_reviewed_mujoco_downstream_priority_gate_id")
    if priority_gate_order != expected_gates:
        blockers.append("provide_reviewed_mujoco_downstream_priority_gate_order")
    if next_downstream_gate_after_ready != NEXT_DOWNSTREAM_GATE_AFTER_READY:
        blockers.append("provide_reviewed_mujoco_next_downstream_gate")
    if blocks_downstream_gates_until_ready is not True:
        blockers.append("mark_reviewed_mujoco_handoff_blocks_downstream_gates")
    if ready_does_not_imply_policy_training_ready is not True:
        blockers.append("mark_reviewed_mujoco_handoff_not_policy_training_ready")
    if (raw_ready or fixture_ready) and handoff_missing_inputs:
        blockers.append("resolve_ready_reviewed_mujoco_handoff_missing_inputs")
    if (raw_ready or fixture_ready) and handoff_pending_action_ids:
        blockers.append("resolve_ready_reviewed_mujoco_handoff_pending_actions")
    if (raw_ready or fixture_ready) and not joint_limit_enablement_ok:
        blockers.append("provide_reviewed_mujoco_joint_limit_enablement_evidence")
    if (raw_ready or fixture_ready) and not reviewed_model_identity_contract_ok:
        blockers.append("provide_reviewed_mujoco_model_identity_evidence")
    if raw_ready and not physical_ready_contract_ok:
        blockers.append("repair_physical_reviewed_mujoco_handoff_readiness_flags")
    if fixture_ready and not fixture_contract_ok:
        blockers.append("repair_fixture_reviewed_mujoco_handoff_flags")
    if not contract_ok:
        blockers.append("provide_valid_reviewed_mujoco_downstream_handoff")
    if not ready:
        blockers.append("make_reviewed_mujoco_downstream_handoff_ready")
    return handoff_intake_result(
        requested=True,
        required=required,
        path=str(resolved),
        status=intake_status,
        intake_ok=contract_ok and (ready or not required),
        ready=ready,
        source_status=payload.get("status"),
        model_authority=payload.get("model_authority"),
        observed_evidence_is_authority=payload.get("observed_evidence_is_authority"),
        physical_truth_claimed=payload.get("physical_so101_truth_claimed"),
        policy_training_authority_claimed=policy_training_authority_claimed,
        fixture_ready=fixture_ready,
        item_ids=item_ids,
        blockers=blockers,
        schema=payload.get("schema"),
        contract_ok=contract_ok,
        motion_authority_status=motion_authority_status,
        physical_motion_checked=physical_motion_checked,
        fixture_motion_checked=fixture_motion_checked,
        motion_evidence_not_physical=motion_evidence_not_physical,
        physical_model_authority_ready=physical_model_authority_ready,
        model_identity_contract_ok=reviewed_model_identity_contract_ok,
        model_identity_status=reviewed_model_identity_status,
        model_identity_matches=reviewed_model_identity_matches,
        reviewed_model_path=reviewed_model_path,
        reviewed_model_declared_sha256=reviewed_model_declared_sha256,
        reviewed_model_observed_sha256=reviewed_model_observed_sha256,
        joint_limit_enablement_ok=joint_limit_enablement_ok,
        joint_limit_enablement_status=joint_limit_enablement_status,
        missing_limited_joints=missing_limited_joints,
        missing_inputs=handoff_missing_inputs,
        pending_action_ids=handoff_pending_action_ids,
        ready_handoff_has_open_work=ready_handoff_has_open_work,
        gates_unblocked_when_physical_ready=gates_unblocked,
        blocked_gates_until_physical_ready=blocked_gates,
        priority_gate_id=priority_gate_id,
        priority_gate_order=priority_gate_order,
        next_downstream_gate_after_ready=next_downstream_gate_after_ready,
        blocks_downstream_gates_until_ready=blocks_downstream_gates_until_ready,
        ready_does_not_imply_policy_training_ready=ready_does_not_imply_policy_training_ready,
        priority_contract_ok=priority_contract_ok,
    )


def joint_positions_from_obs(obs: dict[str, Any]) -> dict[str, float]:
    joints = obs["joint_positions_deg"]
    return {joint: float(joints[index]) for index, joint in enumerate(SO101_JOINTS)}


def run_scripted_env(env: Any, action_toward_targets: Any, *, max_steps: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    obs, info = env.reset()
    rows: list[dict[str, Any]] = []
    terminated = False
    truncated = False
    total_reward = 0.0
    for step_index in range(max_steps):
        phase_index = int(obs["phase_index"][0])
        waypoint = env.waypoints[min(phase_index, len(env.waypoints) - 1)]
        action = action_toward_targets(
            joint_positions_from_obs(obs),
            waypoint.targets_deg,
            action_scale_deg=env.config.action_scale_deg,
        )
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        scene = info["scene_state"]
        rows.append(
            {
                "step": step_index + 1,
                "waypoint": waypoint.name,
                "phase_index": int(obs["phase_index"][0]),
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "piece_square": scene["piece"]["square"],
                "holding_piece": bool(scene["piece"]["held_by_gripper"]),
            }
        )
        if terminated or truncated:
            break
    scene = info["scene_state"]
    result = {
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "steps": len(rows),
        "total_reward": float(total_reward),
        "final_phase_index": int(obs["phase_index"][0]),
        "final_piece_square": scene["piece"]["square"],
        "final_holding_piece": bool(scene["piece"]["held_by_gripper"]),
        "scripted_pick_place_complete": bool(
            terminated
            and scene["piece"]["square"] == env.config.target_square
            and not scene["piece"]["held_by_gripper"]
        ),
        "final_sim_status": info["sim_status"],
        "final_scene_state": scene,
    }
    return result, rows


def mujoco_names(module: Any, model: Any, obj_type: Any, count: int) -> list[str]:
    names: list[str] = []
    for index in range(count):
        name = module.mj_id2name(model, obj_type, index)
        if name:
            names.append(str(name))
    return names


def validate_loaded_model(model_path: Path) -> dict[str, Any]:
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    joint_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
    geom_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom)
    body_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
    site_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_SITE, model.nsite)
    square_geoms = [name for name in geom_names if name.startswith("square_")]
    joint_set = set(joint_names)
    geom_set = set(geom_names)
    body_set = set(body_names)
    site_set = set(site_names)
    limited_joint_evidence: dict[str, dict[str, Any]] = {}
    missing_limited_joints: list[str] = []
    unlimited_required_joints: list[str] = []
    invalid_required_joint_ranges: list[str] = []
    for joint_name in REQUIRED_LIMITED_JOINTS:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id < 0:
            missing_limited_joints.append(joint_name)
            continue
        joint_range = [
            float(model.jnt_range[joint_id][0]),
            float(model.jnt_range[joint_id][1]),
        ]
        limited = bool(model.jnt_limited[joint_id])
        finite_range = all(math.isfinite(value) for value in joint_range)
        nonzero_range = joint_range[1] > joint_range[0]
        if not limited:
            unlimited_required_joints.append(joint_name)
        if not finite_range or not nonzero_range:
            invalid_required_joint_ranges.append(joint_name)
        limited_joint_evidence[joint_name] = {
            "limited": limited,
            "range": joint_range,
            "finite_range": finite_range,
            "nonzero_range": nonzero_range,
        }
    missing_required_geoms = sorted(set(REQUIRED_GEOMS) - geom_set)
    missing_gripper_collision_geoms = sorted(
        set(REQUIRED_GRIPPER_COLLISION_GEOMS) - geom_set
    )
    return {
        "ok": (
            set(REQUIRED_MODEL_JOINTS).issubset(joint_set)
            and set(REQUIRED_BODIES).issubset(body_set)
            and set(REQUIRED_GEOMS).issubset(geom_set)
            and set(REQUIRED_SITES).issubset(site_set)
            and len(square_geoms) == 64
            and not missing_limited_joints
            and not unlimited_required_joints
            and not invalid_required_joint_ranges
        ),
        "model_path": str(model_path),
        "nq": int(model.nq),
        "nv": int(model.nv),
        "required_model_joints": list(REQUIRED_MODEL_JOINTS),
        "required_limited_joints": list(REQUIRED_LIMITED_JOINTS),
        "joint_names": joint_names,
        "missing_joints": sorted(set(REQUIRED_MODEL_JOINTS) - joint_set),
        "limited_joint_evidence": limited_joint_evidence,
        "missing_limited_joints": missing_limited_joints,
        "unlimited_required_joints": unlimited_required_joints,
        "invalid_required_joint_ranges": invalid_required_joint_ranges,
        "required_bodies": list(REQUIRED_BODIES),
        "body_names": body_names,
        "missing_bodies": sorted(set(REQUIRED_BODIES) - body_set),
        "required_sites": list(REQUIRED_SITES),
        "site_names": site_names,
        "missing_required_sites": sorted(set(REQUIRED_SITES) - site_set),
        "required_geoms": list(REQUIRED_GEOMS),
        "required_gripper_collision_geoms": list(REQUIRED_GRIPPER_COLLISION_GEOMS),
        "geom_count": len(geom_names),
        "body_count": len(body_names),
        "square_geom_count": len(square_geoms),
        "missing_required_geoms": missing_required_geoms,
        "missing_gripper_collision_geoms": missing_gripper_collision_geoms,
    }


def validate_sim_robot(model_path: Path) -> dict[str, Any]:
    from lerobot.sim import SimRobot, SimRobotConfig

    robot = SimRobot(
        SimRobotConfig(
            cameras={},
            use_mujoco=True,
            mujoco_model_path=model_path,
            initial_positions={"gripper": 95.0},
        )
    )
    robot.connect()
    try:
        initial_status = robot.sim_status()
        sent = robot.send_action(
            {
                "shoulder_pan.pos": 12.0,
                "shoulder_lift.pos": -24.0,
                "elbow_flex.pos": 52.0,
                "wrist_flex.pos": -30.0,
                "wrist_roll.pos": 35.0,
                "gripper.pos": 80.0,
            }
        )
        after_status = robot.sim_status()
        backend = getattr(robot, "_mujoco_backend", None)
        qpos_snapshot: list[float] = []
        if backend is not None:
            qpos_snapshot = [float(value) for value in backend.data.qpos[: min(8, len(backend.data.qpos))]]
        return {
            "ok": bool(initial_status.get("ok")) and bool(after_status.get("ok")) and not after_status.get("missing_joints"),
            "initial_status": initial_status,
            "after_status": after_status,
            "sent_action": sent,
            "qpos_snapshot": qpos_snapshot,
        }
    finally:
        robot.disconnect()


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Development MuJoCo Scene Smoke",
        "",
        "This smoke validates a generated development-only MJCF scene.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Model authority: `{summary['model_authority']}`",
        f"- MuJoCo model load ok: `{summary['mujoco_model_load'].get('ok')}`",
        f"- SimRobot MuJoCo sync ok: `{summary['sim_robot_mujoco_sync'].get('ok')}`",
        f"- Env scripted pick/place complete: `{summary['env_scripted_pick_place'].get('scripted_pick_place_complete')}`",
        f"- Reviewed MuJoCo handoff intake: `{summary.get('reviewed_mujoco_handoff_intake_status')}`",
        f"- Reviewed MuJoCo handoff ready: `{summary.get('reviewed_mujoco_handoff_ready')}`",
        f"- Generated model: `{summary['artifacts']['model_xml']}`",
        "",
        "This is not a reviewed SO-101 model bundle and must not be used as IK truth.",
    ]
    path.write_text("\n".join(lines) + "\n")


def invalid_task_summary(
    *,
    args: argparse.Namespace,
    deps: dict[str, bool],
    handoff_intake: dict[str, Any],
    summary_path: Path,
    model_path: Path,
    manifest_path: Path,
    steps_path: Path,
    readme_path: Path,
    message: str,
) -> dict[str, Any]:
    summary = {
        "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
        "ok": False,
        "status": "invalid_task_configuration",
        "model_authority": DEVELOPMENT_MODEL_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "mujoco_scene_validity_status": "invalid_task_configuration",
        "source_square": args.source_square,
        "target_square": args.target_square,
        "max_steps": args.max_steps,
        **handoff_intake,
        "configuration_error": {
            "type": "ValueError",
            "message": message,
        },
        "dependencies": deps,
        "mujoco_model_load": {
            "ok": False,
            "status": "not_attempted_invalid_task_configuration",
        },
        "sim_robot_mujoco_sync": {
            "ok": False,
            "status": "not_attempted_invalid_task_configuration",
        },
        "env_scripted_pick_place": {
            "scripted_pick_place_complete": False,
            "status": "not_attempted_invalid_task_configuration",
        },
        "artifacts": {
            "summary_json": str(summary_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Invalid task configuration is recorded as a fail-closed scene gate artifact.",
            "No MuJoCo model, SimRobot sync, or Gymnasium scripted movement is attempted.",
            "This failure is hardware-free and does not claim physical SO-101 evidence.",
        ],
        "next_required_for_goal": [
            "Provide valid, distinct source and target chess squares before generating the MuJoCo scene.",
        ],
    }
    write_json(summary_path, summary)
    write_steps(steps_path, [])
    write_readme(readme_path, summary)
    return summary


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    handoff_intake = reviewed_handoff_intake(
        args.reviewed_mujoco_handoff_json,
        required=bool(args.require_reviewed_mujoco_handoff),
    )
    deps = {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "gymnasium": module_available("gymnasium"),
        "mujoco": module_available("mujoco"),
    }
    missing = [name for name, available in deps.items() if not available]
    summary_path = args.output_dir / SUMMARY_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    steps_path = args.output_dir / STEPS_NAME
    readme_path = args.output_dir / README_NAME
    if args.require_reviewed_mujoco_handoff and not handoff_intake.get(
        "reviewed_mujoco_handoff_ready"
    ):
        summary = {
            "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
            "ok": False,
            "status": "reviewed_mujoco_handoff_required_but_not_ready",
            "model_authority": DEVELOPMENT_MODEL_AUTHORITY,
            "observed_evidence_is_physical_so101_authority": False,
            "ready_for_model_backed_ik": False,
            "ready_for_policy_training": False,
            "mujoco_scene_validity_status": "reviewed_handoff_required_but_not_ready",
            "source_square": args.source_square,
            "target_square": args.target_square,
            "max_steps": args.max_steps,
            **handoff_intake,
            "dependencies": deps,
            "mujoco_model_load": {
                "ok": False,
                "status": "not_attempted_reviewed_handoff_not_ready",
            },
            "sim_robot_mujoco_sync": {
                "ok": False,
                "status": "not_attempted_reviewed_handoff_not_ready",
            },
            "env_scripted_pick_place": {
                "scripted_pick_place_complete": False,
                "status": "not_attempted_reviewed_handoff_not_ready",
            },
            "artifacts": {
                "summary_json": str(summary_path),
                "model_xml": str(model_path),
                "manifest_json": str(manifest_path),
                "steps_csv": str(steps_path),
                "readme": str(readme_path),
            },
            "limitations": [
                "Reviewed MuJoCo handoff was required, so the development scene was not generated.",
                "This failure is hardware-free and does not claim physical SO-101 evidence.",
            ],
            "next_required_for_goal": handoff_intake.get(
                "reviewed_mujoco_handoff_blockers"
            )
            or ["make_reviewed_mujoco_downstream_handoff_ready"],
        }
        write_json(summary_path, summary)
        write_steps(steps_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1
    if missing:
        summary = {
            "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
            "ok": False,
            "status": "missing_runtime_dependencies",
            "model_authority": DEVELOPMENT_MODEL_AUTHORITY,
            "observed_evidence_is_physical_so101_authority": False,
            "ready_for_model_backed_ik": False,
            "ready_for_policy_training": False,
            "mujoco_scene_validity_status": "missing_runtime_dependencies",
            "missing_dependencies": missing,
            "dependencies": deps,
            **handoff_intake,
            "artifacts": {
                "summary_json": str(summary_path),
                "model_xml": str(model_path),
                "manifest_json": str(manifest_path),
                "steps_csv": str(steps_path),
                "readme": str(readme_path),
            },
        }
        write_json(summary_path, summary)
        write_steps(steps_path, [])
        write_readme(readme_path, {**summary, "mujoco_model_load": {}, "sim_robot_mujoco_sync": {}, "env_scripted_pick_place": {}})
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    from lerobot.sim import SO101ChessEnv, SO101ChessEnvConfig, action_toward_targets
    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        write_so101_development_mjcf,
    )

    try:
        if args.max_steps <= 0:
            raise ValueError("max_steps must be positive.")
        config = SO101DevelopmentMJCFConfig(piece_square=args.source_square, target_square=args.target_square)
    except ValueError as exc:
        summary = invalid_task_summary(
            args=args,
            deps=deps,
            handoff_intake=handoff_intake,
            summary_path=summary_path,
            model_path=model_path,
            manifest_path=manifest_path,
            steps_path=steps_path,
            readme_path=readme_path,
            message=str(exc),
        )
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    manifest = write_so101_development_mjcf(model_path, config, manifest_path=manifest_path)
    model_load = validate_loaded_model(model_path)
    sim_robot_sync = validate_sim_robot(model_path)
    env = SO101ChessEnv(
        SO101ChessEnvConfig(
            source_square=args.source_square,
            target_square=args.target_square,
            max_steps=args.max_steps,
            use_mujoco=True,
            mujoco_model_path=model_path,
        )
    )
    try:
        env_result, rows = run_scripted_env(env, action_toward_targets, max_steps=args.max_steps)
    finally:
        env.close()

    write_steps(steps_path, rows)
    ok = bool(model_load.get("ok")) and bool(sim_robot_sync.get("ok")) and bool(env_result.get("scripted_pick_place_complete"))
    summary = {
        "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
        "ok": ok,
        "status": "ok" if ok else "failed",
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "mujoco_scene_validity_status": "development_scene_validated_not_physical_authority",
        "source_square": args.source_square,
        "target_square": args.target_square,
        "max_steps": args.max_steps,
        **handoff_intake,
        "scene_uses_reviewed_mujoco_handoff": False,
        "square_geom_count": model_load.get("square_geom_count"),
        "target_frame_site_present": not bool(model_load.get("missing_required_sites")),
        "target_marker_present": "target_square_marker" not in set(model_load.get("missing_required_geoms") or []),
        "dependencies": deps,
        "development_manifest": manifest,
        "mujoco_model_load": model_load,
        "sim_robot_mujoco_sync": sim_robot_sync,
        "env_scripted_pick_place": env_result,
        "artifacts": {
            "summary_json": str(summary_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Generated development MJCF is approximate and non-authoritative.",
            "No reviewed mesh assets, source provenance, calibrated TCP offset, or base-to-board alignment are supplied.",
            "Passing this smoke proves MuJoCo plumbing and scene collision availability, not physical SO-101 IK accuracy.",
        ],
        "next_required_for_goal": [
            "Supply reviewed SO-101 URDF/MJCF/Xacro/XML model path.",
            "Supply mesh asset roots and pass asset preflight.",
            "Fill reviewed authority/provenance, TCP offset, and base-to-board transform in the model bundle manifest.",
            *handoff_intake.get("reviewed_mujoco_handoff_blockers", []),
        ],
    }
    write_json(summary_path, summary)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": ok, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
