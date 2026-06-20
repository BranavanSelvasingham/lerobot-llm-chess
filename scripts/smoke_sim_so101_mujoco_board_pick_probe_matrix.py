#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_board_pick_probe_matrix"
SCHEMA = "lerobot.sim.so101_mujoco_board_pick_probe_matrix.v1"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_board_pick_probe.py"
PROBE_SUMMARY_NAME = "so101_mujoco_board_pick_probe_summary.json"
EXPECTED_PHASE_IDS = [
    "source_reset",
    "two_finger_grasp",
    "lift_clearance",
    "transfer_toward_target",
    "release_place",
]
EXPECTED_STAGE_SEQUENCE = [
    "source_reset_piece_on_board",
    "lower_open_at_source",
    "close_on_source_piece_forward",
    "close_on_source_piece_after_settle",
    "lift_from_source_without_manual_piece_pose",
    "transfer_to_target_without_manual_piece_pose",
    "lower_to_target_without_manual_piece_pose",
    "release_on_target_without_manual_piece_pose",
    "retreat_after_release_without_manual_piece_pose",
]
PHASE_OBSERVATION_KEYS = {
    "source_reset": "source_pick_started_at_source",
    "two_finger_grasp": "close_two_finger_contact_observed",
    "lift_clearance": "lift_verified",
    "transfer_toward_target": "transfer_verified",
    "release_place": "place_without_manual_piece_pose_verified",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a focused hardware-free matrix over the development SO-101 MuJoCo "
            "board-source pick/place probe. Cases capture both the one currently "
            "verified seeded fixture and expected gap cases so this cannot be "
            "mistaken for reviewed model-backed IK."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child board-pick checks.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing output directory before running.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def executable_arg(path: Path) -> str:
    raw = str(path)
    expanded = path.expanduser()
    if expanded.is_absolute():
        return str(expanded)
    if "/" in raw:
        return str((REPO_ROOT / expanded).absolute())
    return raw


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
        "return_code",
        "expected_return_code",
        "status",
        "expected_status",
        "model_authority",
        "source_square",
        "target_square",
        "source_pick_started_at_source",
        "close_two_finger_contact_observed",
        "lift_verified",
        "board_contact_cleared_during_lift",
        "transfer_verified",
        "place_without_manual_piece_pose_verified",
        "board_source_pick_place_verified",
        "release_contact_cleared_after_retreat",
        "final_board_contact_observed",
        "final_target_within_tolerance",
        "final_target_xy_error_m",
        "target_xy_tolerance_m",
        "final_place_z_error_m",
        "place_z_tolerance_m",
        "pick_place_phase_ids",
        "pick_place_failed_phase_ids",
        "pick_place_phase_count",
        "pick_place_all_required_phases_verified",
        "phase_evidence_contract_ok",
        "phase_evidence_contract_errors",
        "stage_sequence_probe_contract_ok",
        "stage_sequence_probe_contract_errors",
        "stage_sequence_contract_ok",
        "stage_sequence_contract_errors",
        "observed_stage_sequence",
        "manual_piece_pose_after_reset_stage_ids",
        "ready_for_model_backed_ik",
        "ready_for_policy_training",
        "physical_authority",
        "development_fixture_evidence_not_physical_so101_truth",
        "development_fixture_evidence_not_policy_training_truth",
        "next_required_action_ids",
        "configuration_error",
        "model_xml_exists",
        "manifest_json_exists",
        "summary_path",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:
        return {
            "ok": False,
            "status": f"{label}_unavailable",
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": f"{label}_not_json_object",
            "diagnostics": ["expected_json_object"],
        }
    return payload


def case_specs() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "seeded_fixture_e4_e5_pick_place_verified",
            "source_square": "e4",
            "target_square": "e5",
            "expected_status": "development_board_source_pick_place_verified",
            "expect_close_two_finger_contact": True,
            "expect_lift": True,
            "expect_board_contact_cleared_during_lift": True,
            "expect_transfer": True,
            "expect_place": True,
            "expect_board_pick_place": True,
            "expect_release_contact_cleared_after_retreat": True,
            "expect_final_board_contact": True,
            "expect_final_target_within_tolerance": True,
        },
        {
            "case_id": "alternate_target_e4_d5_records_place_gap",
            "source_square": "e4",
            "target_square": "d5",
            "expected_status": "development_board_source_lift_verified_place_gap_recorded",
            "expect_close_two_finger_contact": True,
            "expect_lift": True,
            "expect_board_contact_cleared_during_lift": True,
            "expect_transfer": True,
            "expect_place": False,
            "expect_board_pick_place": False,
            "expect_release_contact_cleared_after_retreat": True,
            "expect_final_board_contact": True,
            "expect_final_target_within_tolerance": False,
        },
        {
            "case_id": "alternate_source_d4_e5_records_pick_gap",
            "source_square": "d4",
            "target_square": "e5",
            "expected_status": "development_board_source_pick_gap_recorded",
            "expect_close_two_finger_contact": False,
            "expect_lift": False,
            "expect_board_contact_cleared_during_lift": False,
            "expect_transfer": False,
            "expect_place": False,
            "expect_board_pick_place": False,
            "expect_release_contact_cleared_after_retreat": True,
            "expect_final_board_contact": True,
            "expect_final_target_within_tolerance": False,
        },
        {
            "case_id": "reversed_source_e5_e4_records_pick_gap",
            "source_square": "e5",
            "target_square": "e4",
            "expected_status": "development_board_source_pick_gap_recorded",
            "expect_close_two_finger_contact": False,
            "expect_lift": False,
            "expect_board_contact_cleared_during_lift": False,
            "expect_transfer": False,
            "expect_place": False,
            "expect_board_pick_place": False,
            "expect_release_contact_cleared_after_retreat": True,
            "expect_final_board_contact": True,
            "expect_final_target_within_tolerance": False,
        },
        {
            "case_id": "invalid_source_square_rejected",
            "source_square": "z9",
            "target_square": "e5",
            "expected_status": "invalid_task_configuration",
            "expect_ok": False,
            "expected_error_contains": "Invalid chess square",
        },
        {
            "case_id": "invalid_target_square_rejected",
            "source_square": "e4",
            "target_square": "z9",
            "expected_status": "invalid_task_configuration",
            "expect_ok": False,
            "expected_error_contains": "Invalid chess square",
        },
        {
            "case_id": "same_source_target_rejected",
            "source_square": "e4",
            "target_square": "e4",
            "expected_status": "invalid_task_configuration",
            "expect_ok": False,
            "expected_error_contains": "piece_square and target_square must differ",
        },
    ]


def run_child(
    *,
    case_dir: Path,
    command: list[str],
    expected_summary_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / "stdout.txt"
    stderr_path = case_dir / "stderr.txt"
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    summary = read_json_object(expected_summary_path, label="summary")
    return {
        "command": command,
        "return_code": result.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(expected_summary_path),
    }, summary


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def add_contains_errors(
    errors: list[str],
    label: str,
    actual: Any,
    expected_values: list[str],
) -> None:
    if not isinstance(actual, list):
        errors.append(f"{label}: expected list containing {expected_values!r}, got {actual!r}")
        return
    missing = [value for value in expected_values if value not in actual]
    if missing:
        errors.append(f"{label}: missing {missing!r} from {actual!r}")


def phase_evidence_contract_errors(
    *,
    case_id: str,
    observations: dict[str, Any],
    expect_ok: bool,
) -> list[str]:
    errors: list[str] = []
    phase_evidence = observations["pick_place_phase_evidence"]
    phase_ids = observations["pick_place_phase_ids"]
    failed_phase_ids = observations["pick_place_failed_phase_ids"]
    phase_count = observations["pick_place_phase_count"]

    if not expect_ok:
        if phase_evidence != []:
            errors.append(f"{case_id}.phase_contract.evidence: expected empty list")
        if phase_ids != []:
            errors.append(f"{case_id}.phase_contract.phase_ids: expected empty list")
        if failed_phase_ids != []:
            errors.append(f"{case_id}.phase_contract.failed_phase_ids: expected empty list")
        if phase_count != 0:
            errors.append(f"{case_id}.phase_contract.phase_count: expected 0")
        if observations["pick_place_all_required_phases_verified"] is not False:
            errors.append(
                f"{case_id}.phase_contract.all_required: expected False for invalid task"
            )
        return errors

    if not isinstance(phase_evidence, list):
        return [f"{case_id}.phase_contract.evidence: expected list"]
    if not isinstance(phase_ids, list):
        errors.append(f"{case_id}.phase_contract.phase_ids: expected list")
    if not isinstance(failed_phase_ids, list):
        errors.append(f"{case_id}.phase_contract.failed_phase_ids: expected list")
    if len(phase_evidence) != len(EXPECTED_PHASE_IDS):
        errors.append(
            f"{case_id}.phase_contract.evidence_count: expected {len(EXPECTED_PHASE_IDS)}, got {len(phase_evidence)}"
        )

    row_phase_ids: list[str] = []
    row_failed_phase_ids: list[str] = []
    row_all_ok = True
    for index, expected_phase_id in enumerate(EXPECTED_PHASE_IDS):
        if index >= len(phase_evidence):
            break
        row = phase_evidence[index]
        if not isinstance(row, dict):
            errors.append(f"{case_id}.phase_contract.{expected_phase_id}: expected dict")
            row_all_ok = False
            continue
        phase_id = row.get("phase_id")
        row_phase_ids.append(str(phase_id))
        if phase_id != expected_phase_id:
            errors.append(
                f"{case_id}.phase_contract.phase_id[{index}]: expected {expected_phase_id!r}, got {phase_id!r}"
            )
        ok = row.get("ok")
        if not isinstance(ok, bool):
            errors.append(f"{case_id}.phase_contract.{expected_phase_id}.ok: expected bool")
            row_all_ok = False
            continue
        if not ok:
            row_all_ok = False
            row_failed_phase_ids.append(expected_phase_id)
        observation_key = PHASE_OBSERVATION_KEYS[expected_phase_id]
        expected_ok = observations[observation_key]
        if ok != expected_ok:
            errors.append(
                f"{case_id}.phase_contract.{expected_phase_id}.ok: expected to match {observation_key}={expected_ok!r}, got {ok!r}"
            )

    if phase_ids != row_phase_ids:
        errors.append(
            f"{case_id}.phase_contract.phase_ids: expected row ids {row_phase_ids!r}, got {phase_ids!r}"
        )
    if failed_phase_ids != row_failed_phase_ids:
        errors.append(
            f"{case_id}.phase_contract.failed_phase_ids: expected {row_failed_phase_ids!r}, got {failed_phase_ids!r}"
        )
    if phase_count != len(phase_evidence):
        errors.append(
            f"{case_id}.phase_contract.phase_count: expected {len(phase_evidence)}, got {phase_count!r}"
        )
    if observations["pick_place_all_required_phases_verified"] != row_all_ok:
        errors.append(
            f"{case_id}.phase_contract.all_required: expected {row_all_ok!r}, got {observations['pick_place_all_required_phases_verified']!r}"
        )
    if observations["board_source_pick_place_verified"] != row_all_ok:
        errors.append(
            f"{case_id}.phase_contract.board_pick_place: expected {row_all_ok!r}, got {observations['board_source_pick_place_verified']!r}"
        )
    return errors


def stage_sequence_contract_errors(
    *,
    case_id: str,
    observations: dict[str, Any],
    expect_ok: bool,
) -> list[str]:
    errors: list[str] = []
    required_stage_sequence = observations["required_stage_sequence"]
    observed_stage_sequence = observations["observed_stage_sequence"]
    missing_stage_ids = observations["missing_stage_ids"]
    unexpected_stage_ids = observations["unexpected_stage_ids"]
    stage_sequence_order_ok = observations["stage_sequence_order_ok"]
    manual_pose_after_reset = observations["manual_piece_pose_after_reset_stage_ids"]
    probe_contract_ok = observations["stage_sequence_probe_contract_ok"]
    probe_contract_errors = observations["stage_sequence_probe_contract_errors"]

    if required_stage_sequence != EXPECTED_STAGE_SEQUENCE:
        errors.append(
            f"{case_id}.stage_sequence.required: expected {EXPECTED_STAGE_SEQUENCE!r}, got {required_stage_sequence!r}"
        )
    if not isinstance(probe_contract_errors, list):
        errors.append(f"{case_id}.stage_sequence.probe_errors: expected list")

    if expect_ok:
        expected_values = (
            ("observed", observed_stage_sequence, EXPECTED_STAGE_SEQUENCE),
            ("missing", missing_stage_ids, []),
            ("unexpected", unexpected_stage_ids, []),
            ("manual_pose_after_reset", manual_pose_after_reset, []),
        )
        for name, observed, expected in expected_values:
            if observed != expected:
                errors.append(
                    f"{case_id}.stage_sequence.{name}: expected {expected!r}, got {observed!r}"
                )
        if stage_sequence_order_ok is not True:
            errors.append(f"{case_id}.stage_sequence.order_ok: expected True")
        if probe_contract_ok is not True:
            errors.append(f"{case_id}.stage_sequence.probe_contract_ok: expected True")
        if probe_contract_errors != []:
            errors.append(
                f"{case_id}.stage_sequence.probe_errors: expected [], got {probe_contract_errors!r}"
            )
        return errors

    expected_invalid_values = (
        ("observed", observed_stage_sequence, []),
        ("missing", missing_stage_ids, EXPECTED_STAGE_SEQUENCE),
        ("unexpected", unexpected_stage_ids, []),
        ("manual_pose_after_reset", manual_pose_after_reset, []),
    )
    for name, observed, expected in expected_invalid_values:
        if observed != expected:
            errors.append(
                f"{case_id}.stage_sequence.{name}: expected {expected!r}, got {observed!r}"
            )
    if stage_sequence_order_ok is not False:
        errors.append(f"{case_id}.stage_sequence.order_ok: expected False")
    if probe_contract_ok is not False:
        errors.append(f"{case_id}.stage_sequence.probe_contract_ok: expected False")
    if not probe_contract_errors:
        errors.append(f"{case_id}.stage_sequence.probe_errors: expected fail-closed marker")
    return errors


def summarize_case(
    *,
    spec: dict[str, Any],
    record: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(spec["case_id"])
    errors: list[str] = []
    final_error = summary.get("final_target_xy_error_m")
    tolerance = summary.get("target_xy_tolerance_m")
    final_target_within_tolerance = (
        isinstance(final_error, (int, float))
        and isinstance(tolerance, (int, float))
        and float(final_error) <= float(tolerance)
    )
    expect_ok = bool(spec.get("expect_ok", True))
    expected_return_code = 0 if expect_ok else 1
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    model_xml_path = artifacts.get("model_xml")
    manifest_path = artifacts.get("manifest_json")
    observations = {
        "return_code": record.get("return_code"),
        "ok": summary.get("ok"),
        "status": summary.get("status"),
        "model_authority": summary.get("model_authority"),
        "source_square": summary.get("source_square"),
        "target_square": summary.get("target_square"),
        "source_pick_started_at_source": summary.get("source_pick_started_at_source"),
        "close_two_finger_contact_observed": summary.get("close_two_finger_contact_observed"),
        "lift_verified": summary.get("lift_verified"),
        "board_contact_cleared_during_lift": summary.get("board_contact_cleared_during_lift"),
        "transfer_verified": summary.get("transfer_verified"),
        "place_without_manual_piece_pose_verified": summary.get(
            "place_without_manual_piece_pose_verified"
        ),
        "board_source_pick_place_verified": summary.get("board_source_pick_place_verified"),
        "release_contact_cleared_after_retreat": summary.get("release_contact_cleared_after_retreat"),
        "final_board_contact_observed": summary.get("final_board_contact_observed"),
        "final_target_xy_error_m": final_error,
        "target_xy_tolerance_m": tolerance,
        "final_target_within_tolerance": final_target_within_tolerance,
        "final_place_z_error_m": summary.get("final_place_z_error_m"),
        "place_z_tolerance_m": summary.get("place_z_tolerance_m"),
        "pick_place_phase_evidence": summary.get("pick_place_phase_evidence"),
        "pick_place_phase_ids": summary.get("pick_place_phase_ids"),
        "pick_place_failed_phase_ids": summary.get("pick_place_failed_phase_ids"),
        "pick_place_phase_count": summary.get("pick_place_phase_count"),
        "pick_place_all_required_phases_verified": summary.get(
            "pick_place_all_required_phases_verified"
        ),
        "required_stage_sequence": summary.get("required_stage_sequence"),
        "observed_stage_sequence": summary.get("observed_stage_sequence"),
        "missing_stage_ids": summary.get("missing_stage_ids"),
        "unexpected_stage_ids": summary.get("unexpected_stage_ids"),
        "stage_sequence_order_ok": summary.get("stage_sequence_order_ok"),
        "manual_piece_pose_after_reset_stage_ids": summary.get(
            "manual_piece_pose_after_reset_stage_ids"
        ),
        "stage_sequence_probe_contract_ok": summary.get("stage_sequence_contract_ok"),
        "stage_sequence_probe_contract_errors": summary.get(
            "stage_sequence_contract_errors"
        ),
        "manual_piece_pose_used_after_reset": summary.get("manual_piece_pose_used_after_reset"),
        "robot_pose_seeded_for_source_fixture": summary.get("robot_pose_seeded_for_source_fixture"),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": summary.get("ready_for_policy_training"),
        "physical_authority": summary.get("observed_evidence_is_physical_so101_authority"),
        "development_fixture_evidence_not_physical_so101_truth": summary.get(
            "development_fixture_evidence_not_physical_so101_truth"
        ),
        "development_fixture_evidence_not_policy_training_truth": summary.get(
            "development_fixture_evidence_not_policy_training_truth"
        ),
        "next_required_for_goal": summary.get("next_required_for_goal"),
        "next_required_action_ids": summary.get("next_required_action_ids"),
        "next_required_action_count": summary.get("next_required_action_count"),
        "configuration_error": summary.get("configuration_error"),
        "artifacts": artifacts,
        "model_xml_exists": isinstance(model_xml_path, str) and Path(model_xml_path).is_file(),
        "manifest_json_exists": isinstance(manifest_path, str) and Path(manifest_path).is_file(),
    }
    phase_contract_errors = phase_evidence_contract_errors(
        case_id=case_id,
        observations=observations,
        expect_ok=expect_ok,
    )
    observations["phase_evidence_contract_errors"] = phase_contract_errors
    observations["phase_evidence_contract_ok"] = not phase_contract_errors
    stage_contract_errors = stage_sequence_contract_errors(
        case_id=case_id,
        observations=observations,
        expect_ok=expect_ok,
    )
    observations["stage_sequence_contract_errors"] = stage_contract_errors
    observations["stage_sequence_contract_ok"] = not stage_contract_errors

    add_error(errors, f"{case_id}.return_code", record.get("return_code"), expected_return_code)
    add_error(errors, f"{case_id}.ok", observations["ok"], expect_ok)
    add_error(errors, f"{case_id}.status", observations["status"], spec["expected_status"])
    errors.extend(phase_contract_errors)
    errors.extend(stage_contract_errors)
    add_error(
        errors,
        f"{case_id}.model_authority",
        observations["model_authority"],
        "development_scaffold_not_reviewed",
    )
    add_error(errors, f"{case_id}.source_square", observations["source_square"], spec["source_square"])
    add_error(errors, f"{case_id}.target_square", observations["target_square"], spec["target_square"])
    add_error(
        errors,
        f"{case_id}.ready_for_model_backed_ik",
        observations["ready_for_model_backed_ik"],
        False,
    )
    add_error(
        errors,
        f"{case_id}.ready_for_policy_training",
        observations["ready_for_policy_training"],
        False,
    )
    add_error(errors, f"{case_id}.physical_authority", observations["physical_authority"], False)
    add_error(
        errors,
        f"{case_id}.development_fixture_evidence_not_physical_so101_truth",
        observations["development_fixture_evidence_not_physical_so101_truth"],
        True,
    )
    add_error(
        errors,
        f"{case_id}.development_fixture_evidence_not_policy_training_truth",
        observations["development_fixture_evidence_not_policy_training_truth"],
        True,
    )

    if expect_ok:
        add_error(
            errors,
            f"{case_id}.source_pick_started_at_source",
            observations["source_pick_started_at_source"],
            True,
        )
        add_error(
            errors,
            f"{case_id}.close_two_finger_contact_observed",
            observations["close_two_finger_contact_observed"],
            spec["expect_close_two_finger_contact"],
        )
        add_error(errors, f"{case_id}.lift_verified", observations["lift_verified"], spec["expect_lift"])
        add_error(
            errors,
            f"{case_id}.board_contact_cleared_during_lift",
            observations["board_contact_cleared_during_lift"],
            spec["expect_board_contact_cleared_during_lift"],
        )
        add_error(
            errors,
            f"{case_id}.transfer_verified",
            observations["transfer_verified"],
            spec["expect_transfer"],
        )
        add_error(
            errors,
            f"{case_id}.place_without_manual_piece_pose_verified",
            observations["place_without_manual_piece_pose_verified"],
            spec["expect_place"],
        )
        add_error(
            errors,
            f"{case_id}.board_source_pick_place_verified",
            observations["board_source_pick_place_verified"],
            spec["expect_board_pick_place"],
        )
        add_error(
            errors,
            f"{case_id}.release_contact_cleared_after_retreat",
            observations["release_contact_cleared_after_retreat"],
            spec["expect_release_contact_cleared_after_retreat"],
        )
        add_error(
            errors,
            f"{case_id}.final_board_contact_observed",
            observations["final_board_contact_observed"],
            spec["expect_final_board_contact"],
        )
        add_error(
            errors,
            f"{case_id}.final_target_within_tolerance",
            observations["final_target_within_tolerance"],
            spec["expect_final_target_within_tolerance"],
        )
        add_error(
            errors,
            f"{case_id}.pick_place_phase_ids",
            observations["pick_place_phase_ids"],
            EXPECTED_PHASE_IDS,
        )
        add_error(
            errors,
            f"{case_id}.pick_place_phase_count",
            observations["pick_place_phase_count"],
            len(EXPECTED_PHASE_IDS),
        )
        add_error(
            errors,
            f"{case_id}.pick_place_all_required_phases_verified",
            observations["pick_place_all_required_phases_verified"],
            spec["expect_board_pick_place"],
        )
        phase_evidence = observations["pick_place_phase_evidence"]
        if not isinstance(phase_evidence, list):
            errors.append(f"{case_id}.pick_place_phase_evidence: expected list")
        elif len(phase_evidence) != len(EXPECTED_PHASE_IDS):
            errors.append(
                f"{case_id}.pick_place_phase_evidence: expected {len(EXPECTED_PHASE_IDS)} rows, got {len(phase_evidence)}"
            )
        else:
            phase_ids = [
                phase.get("phase_id") for phase in phase_evidence if isinstance(phase, dict)
            ]
            add_error(errors, f"{case_id}.phase_evidence_ids", phase_ids, EXPECTED_PHASE_IDS)
            for phase in phase_evidence:
                if not isinstance(phase, dict):
                    errors.append(f"{case_id}.phase_evidence: expected dict rows")
                    continue
                if not isinstance(phase.get("criteria"), list) or not phase["criteria"]:
                    errors.append(
                        f"{case_id}.{phase.get('phase_id')}.criteria: expected non-empty list"
                    )
                if not isinstance(phase.get("metrics"), dict) or not phase["metrics"]:
                    errors.append(
                        f"{case_id}.{phase.get('phase_id')}.metrics: expected non-empty dict"
                    )
        if spec["expect_board_pick_place"]:
            add_error(
                errors,
                f"{case_id}.pick_place_failed_phase_ids",
                observations["pick_place_failed_phase_ids"],
                [],
            )
        elif not observations["pick_place_failed_phase_ids"]:
            errors.append(f"{case_id}.pick_place_failed_phase_ids: expected at least one failed phase")
        add_error(
            errors,
            f"{case_id}.manual_piece_pose_used_after_reset",
            observations["manual_piece_pose_used_after_reset"],
            False,
        )
        add_error(
            errors,
            f"{case_id}.robot_pose_seeded_for_source_fixture",
            observations["robot_pose_seeded_for_source_fixture"],
            True,
        )
        if not observations["next_required_for_goal"]:
            errors.append(f"{case_id}.next_required_for_goal: expected non-empty list")
        add_contains_errors(
            errors,
            f"{case_id}.next_required_action_ids",
            observations["next_required_action_ids"],
            [
                "supply_reviewed_so101_model_bundle_manifest",
                "calibrate_reviewed_tcp_and_base_to_board_alignment",
                "repeat_board_pick_with_reviewed_model_backed_ik",
            ],
        )
        add_error(
            errors,
            f"{case_id}.next_required_action_count",
            observations["next_required_action_count"],
            3,
        )
        for key in ("summary_json", "rows_csv", "model_xml", "manifest_json", "readme"):
            artifact_path = artifacts.get(key)
            if not isinstance(artifact_path, str) or not Path(artifact_path).is_file():
                errors.append(f"{case_id}.artifacts.{key}: expected existing path")
    else:
        for key, expected in (
            ("source_pick_started_at_source", False),
            ("close_two_finger_contact_observed", False),
            ("lift_verified", False),
            ("board_contact_cleared_during_lift", False),
            ("transfer_verified", False),
            ("place_without_manual_piece_pose_verified", False),
            ("board_source_pick_place_verified", False),
            ("release_contact_cleared_after_retreat", False),
            ("final_board_contact_observed", False),
            ("manual_piece_pose_used_after_reset", False),
            ("robot_pose_seeded_for_source_fixture", False),
            ("pick_place_all_required_phases_verified", False),
        ):
            add_error(errors, f"{case_id}.{key}", observations[key], expected)
        add_error(errors, f"{case_id}.pick_place_phase_ids", observations["pick_place_phase_ids"], [])
        add_error(
            errors,
            f"{case_id}.pick_place_failed_phase_ids",
            observations["pick_place_failed_phase_ids"],
            [],
        )
        add_error(errors, f"{case_id}.pick_place_phase_count", observations["pick_place_phase_count"], 0)
        configuration_error = observations["configuration_error"]
        if not isinstance(configuration_error, dict):
            errors.append(f"{case_id}.configuration_error: expected dict, got {configuration_error!r}")
        else:
            message = configuration_error.get("message")
            expected_error = str(spec.get("expected_error_contains", ""))
            if expected_error not in str(message):
                errors.append(
                    f"{case_id}.configuration_error.message: expected to contain {expected_error!r}, got {message!r}"
                )
        add_contains_errors(
            errors,
            f"{case_id}.next_required_action_ids",
            observations["next_required_action_ids"],
            ["provide_valid_distinct_source_and_target_squares"],
        )
        add_error(
            errors,
            f"{case_id}.next_required_action_count",
            observations["next_required_action_count"],
            1,
        )
        for key in ("summary_json", "rows_csv", "readme"):
            artifact_path = artifacts.get(key)
            if not isinstance(artifact_path, str) or not Path(artifact_path).is_file():
                errors.append(f"{case_id}.artifacts.{key}: expected existing path")
        for key in ("model_xml", "manifest_json"):
            artifact_path = artifacts.get(key)
            if not isinstance(artifact_path, str):
                errors.append(f"{case_id}.artifacts.{key}: expected planned path string")
            elif Path(artifact_path).is_file():
                errors.append(f"{case_id}.artifacts.{key}: expected no generated file")
    if not isinstance(artifacts, dict):
        errors.append(f"{case_id}.artifacts: expected dict")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "record": record,
        "summary_path": record["summary_path"],
        "expected": {
            "return_code": expected_return_code,
            "status": spec["expected_status"],
            "source_square": spec["source_square"],
            "target_square": spec["target_square"],
            "board_source_pick_place_verified": spec.get("expect_board_pick_place", False),
        },
        "observations": observations,
    }


def run_case(
    *,
    output_dir: Path,
    python_path: Path,
    spec: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(spec["case_id"])
    case_dir = output_dir / "cases" / case_id
    command = [
        executable_arg(python_path),
        str(PROBE_SCRIPT),
        "--output-dir",
        str(case_dir),
        "--source-square",
        str(spec["source_square"]),
        "--target-square",
        str(spec["target_square"]),
    ]
    record, summary = run_child(
        case_dir=case_dir,
        command=command,
        expected_summary_path=case_dir / PROBE_SUMMARY_NAME,
    )
    record["case_id"] = case_id
    return summarize_case(spec=spec, record=record, summary=summary)


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    observations = case["observations"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "return_code": observations.get("return_code"),
        "expected_return_code": case["expected"]["return_code"],
        "status": observations.get("status"),
        "expected_status": case["expected"]["status"],
        "model_authority": observations.get("model_authority"),
        "source_square": observations.get("source_square"),
        "target_square": observations.get("target_square"),
        "source_pick_started_at_source": observations.get("source_pick_started_at_source"),
        "close_two_finger_contact_observed": observations.get("close_two_finger_contact_observed"),
        "lift_verified": observations.get("lift_verified"),
        "board_contact_cleared_during_lift": observations.get("board_contact_cleared_during_lift"),
        "transfer_verified": observations.get("transfer_verified"),
        "place_without_manual_piece_pose_verified": observations.get(
            "place_without_manual_piece_pose_verified"
        ),
        "board_source_pick_place_verified": observations.get("board_source_pick_place_verified"),
        "release_contact_cleared_after_retreat": observations.get("release_contact_cleared_after_retreat"),
        "final_board_contact_observed": observations.get("final_board_contact_observed"),
        "final_target_within_tolerance": observations.get("final_target_within_tolerance"),
        "final_target_xy_error_m": observations.get("final_target_xy_error_m"),
        "target_xy_tolerance_m": observations.get("target_xy_tolerance_m"),
        "final_place_z_error_m": observations.get("final_place_z_error_m"),
        "place_z_tolerance_m": observations.get("place_z_tolerance_m"),
        "pick_place_phase_ids": observations.get("pick_place_phase_ids"),
        "pick_place_failed_phase_ids": observations.get("pick_place_failed_phase_ids"),
        "pick_place_phase_count": observations.get("pick_place_phase_count"),
        "pick_place_all_required_phases_verified": observations.get(
            "pick_place_all_required_phases_verified"
        ),
        "phase_evidence_contract_ok": observations.get("phase_evidence_contract_ok"),
        "phase_evidence_contract_errors": observations.get("phase_evidence_contract_errors"),
        "stage_sequence_probe_contract_ok": observations.get(
            "stage_sequence_probe_contract_ok"
        ),
        "stage_sequence_probe_contract_errors": observations.get(
            "stage_sequence_probe_contract_errors"
        ),
        "stage_sequence_contract_ok": observations.get("stage_sequence_contract_ok"),
        "stage_sequence_contract_errors": observations.get("stage_sequence_contract_errors"),
        "observed_stage_sequence": observations.get("observed_stage_sequence"),
        "manual_piece_pose_after_reset_stage_ids": observations.get(
            "manual_piece_pose_after_reset_stage_ids"
        ),
        "ready_for_model_backed_ik": observations.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": observations.get("ready_for_policy_training"),
        "physical_authority": observations.get("physical_authority"),
        "development_fixture_evidence_not_physical_so101_truth": observations.get(
            "development_fixture_evidence_not_physical_so101_truth"
        ),
        "development_fixture_evidence_not_policy_training_truth": observations.get(
            "development_fixture_evidence_not_policy_training_truth"
        ),
        "next_required_action_ids": observations.get("next_required_action_ids"),
        "configuration_error": observations.get("configuration_error"),
        "model_xml_exists": observations.get("model_xml_exists"),
        "manifest_json_exists": observations.get("manifest_json_exists"),
        "summary_path": case["summary_path"],
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 MuJoCo Board Pick Probe Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `verified_pick_place_case_count`: `{summary['verified_pick_place_case_count']}`",
        f"- `expected_gap_case_count`: `{summary['expected_gap_case_count']}`",
        f"- `invalid_task_case_count`: `{summary['invalid_task_case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "This matrix validates the current board-source pick/place development fixture and records its placement limits. It is not reviewed model-backed IK or physical SO-101 grasp authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Source | Target | Board Pick/Place | Final Target Within Tolerance | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{source}` | `{target}` | `{pick_place}` | `{target_ok}` | `{summary}` |".format(
                case_id=case["case_id"],
                status=obs.get("status"),
                source=obs.get("source_square"),
                target=obs.get("target_square"),
                pick_place=obs.get("board_source_pick_place_verified"),
                target_ok=obs.get("final_target_within_tolerance"),
                summary=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- All cases use generated `development_scaffold_not_reviewed` MJCF.",
            "- The passing case uses direct seeded source pose plus a scripted actuator sequence.",
            "- Gap cases are expected evidence that the fixture does not replace reviewed model-backed IK.",
            "- `ready_for_model_backed_ik` and `ready_for_policy_training` must remain false.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        run_case(output_dir=output_dir, python_path=args.python, spec=spec)
        for spec in case_specs()
    ]
    ok = all(case["ok"] for case in cases)
    verified_cases = [
        case for case in cases if case["observations"].get("board_source_pick_place_verified") is True
    ]
    invalid_task_cases = [
        case for case in cases if case["observations"].get("status") == "invalid_task_configuration"
    ]
    expected_gap_cases = [
        case
        for case in cases
        if case["observations"].get("board_source_pick_place_verified") is False
        and case["observations"].get("status") != "invalid_task_configuration"
    ]
    phase_contract_error_count = sum(
        len(case["observations"].get("phase_evidence_contract_errors") or [])
        for case in cases
    )
    stage_contract_error_count = sum(
        len(case["observations"].get("stage_sequence_contract_errors") or [])
        for case in cases
    )
    summary_path = output_dir / "so101_mujoco_board_pick_probe_matrix_summary.json"
    csv_path = output_dir / "so101_mujoco_board_pick_probe_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "so101_mujoco_board_pick_probe_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "verified_pick_place_case_count": len(verified_cases),
        "expected_gap_case_count": len(expected_gap_cases),
        "invalid_task_case_count": len(invalid_task_cases),
        "phase_evidence_contract_ok": phase_contract_error_count == 0,
        "phase_evidence_contract_error_count": phase_contract_error_count,
        "expected_stage_sequence": EXPECTED_STAGE_SEQUENCE,
        "stage_sequence_contract_ok": stage_contract_error_count == 0,
        "stage_sequence_contract_error_count": stage_contract_error_count,
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "verified_pick_place_case_ids": [case["case_id"] for case in verified_cases],
        "expected_gap_case_ids": [case["case_id"] for case in expected_gap_cases],
        "invalid_task_case_ids": [case["case_id"] for case in invalid_task_cases],
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "Generated development board-pick scenes are approximate and non-authoritative.",
            "The verified case uses a seeded source pose and scripted actuator sequence.",
            "Gap cases show the fixture is not generalized model-backed IK.",
            "Invalid task cases must fail closed without generating a model XML or manifest.",
            "Reviewed TCP/gripper offset and base-to-board alignment remain required.",
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
