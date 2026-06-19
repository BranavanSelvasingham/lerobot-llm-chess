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

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_training_rollouts_matrix"
SCHEMA = "lerobot.sim.so101_training_rollouts_matrix.v1"
BOARD_PICK_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_board_pick_probe.py"
ROLLOUT_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_training_rollouts.py"
BOARD_PICK_SUMMARY_NAME = "so101_mujoco_board_pick_probe_summary.json"
ROLLOUT_SUMMARY_NAME = "so101_training_rollouts_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free matrix over SO-101 development training rollouts. "
            "Cases prove debug rollouts require an explicit board-pick prerequisite "
            "and remain non-authoritative policy-training evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child smoke checks.",
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
        "rollout_ok",
        "episode_count",
        "transition_count",
        "all_scripted_pick_place_complete",
        "all_mujoco_fallback_free",
        "all_mujoco_piece_release_synced",
        "development_prerequisites_satisfied",
        "board_pick_prerequisite_status",
        "board_pick_failed_checks",
        "ready_for_policy_training",
        "policy_authority",
        "rollout_use",
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


def run_valid_board_pick_prerequisite(output_dir: Path, python_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    prereq_dir = output_dir / "prerequisites" / "valid_board_pick"
    command = [
        executable_arg(python_path),
        str(BOARD_PICK_SCRIPT),
        "--output-dir",
        str(prereq_dir),
    ]
    return run_child(
        case_dir=prereq_dir,
        command=command,
        expected_summary_path=prereq_dir / BOARD_PICK_SUMMARY_NAME,
    )


def write_failed_board_pick_prerequisite(path: Path) -> None:
    payload = {
        "schema": "lerobot.sim.so101_training_rollouts_matrix.bad_board_pick_prerequisite.v1",
        "ok": True,
        "status": "development_board_source_pick_gap_recorded",
        "model_authority": "development_scaffold_not_reviewed",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "board_source_pick_place_verified": False,
        "source_pick_started_at_source": True,
        "close_two_finger_contact_observed": False,
        "lift_verified": False,
        "board_contact_cleared_during_lift": False,
        "transfer_verified": False,
        "place_without_manual_piece_pose_verified": False,
        "release_contact_cleared_after_retreat": True,
        "manual_piece_pose_used_after_reset": False,
        "robot_pose_seeded_for_source_fixture": True,
        "source_square": "d4",
        "target_square": "e5",
    }
    write_json(path, payload)


def write_incomplete_final_board_pick_prerequisite(path: Path) -> None:
    payload = {
        "schema": "lerobot.sim.so101_training_rollouts_matrix.incomplete_board_pick_prerequisite.v1",
        "ok": True,
        "status": "development_board_source_pick_place_verified",
        "model_authority": "development_scaffold_not_reviewed",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "board_source_pick_place_verified": True,
        "source_pick_started_at_source": True,
        "close_two_finger_contact_observed": True,
        "lift_verified": True,
        "board_contact_cleared_during_lift": True,
        "transfer_verified": True,
        "place_without_manual_piece_pose_verified": True,
        "release_contact_cleared_after_retreat": True,
        "final_board_contact_observed": False,
        "final_target_xy_error_m": 0.05,
        "target_xy_tolerance_m": 0.01,
        "manual_piece_pose_used_after_reset": False,
        "robot_pose_seeded_for_source_fixture": True,
        "source_square": "e4",
        "target_square": "e5",
    }
    write_json(path, payload)


def case_specs(
    output_dir: Path,
    valid_prerequisite: Path,
    failed_prerequisite: Path,
    incomplete_final_prerequisite: Path,
) -> list[dict[str, Any]]:
    return [
        {
            "case_id": "valid_development_default_curriculum_debug_rollouts",
            "prerequisite_path": valid_prerequisite,
            "tasks": [],
            "max_steps": 96,
            "expected_return_code": 0,
            "expected_status": "ok",
            "expected_rollout_ok": True,
            "expected_development_prerequisites_satisfied": True,
            "expected_board_pick_prerequisite_status": "development_board_pick_prerequisite_verified",
            "expected_all_complete": True,
            "expected_release_synced": True,
            "expected_episode_count": 5,
            "expect_transition_count_positive": True,
            "expected_model_authority": "development_scaffold_not_reviewed",
            "expected_rollout_use": "debug_imitation_curriculum_only",
            "expected_all_fallback_free": True,
            "expected_model_artifacts": True,
        },
        {
            "case_id": "missing_board_pick_prerequisite_fails_closed",
            "prerequisite_path": output_dir / "prerequisites" / "missing_board_pick_summary.json",
            "tasks": ["e4:e5"],
            "max_steps": 96,
            "expected_return_code": 1,
            "expected_status": "failed_prerequisite_or_rollout_check",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "missing",
            "expected_all_complete": True,
            "expected_release_synced": True,
            "expected_episode_count": 1,
            "expect_transition_count_positive": True,
            "expected_model_authority": "development_scaffold_not_reviewed",
            "expected_rollout_use": "debug_imitation_curriculum_only",
            "expected_all_fallback_free": True,
            "expected_model_artifacts": True,
        },
        {
            "case_id": "failed_board_pick_prerequisite_fails_closed",
            "prerequisite_path": failed_prerequisite,
            "tasks": ["e4:e5"],
            "max_steps": 96,
            "expected_return_code": 1,
            "expected_status": "failed_prerequisite_or_rollout_check",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "development_board_pick_prerequisite_failed",
            "expected_all_complete": True,
            "expected_release_synced": True,
            "expected_episode_count": 1,
            "expect_transition_count_positive": True,
            "expected_model_authority": "development_scaffold_not_reviewed",
            "expected_rollout_use": "debug_imitation_curriculum_only",
            "expected_all_fallback_free": True,
            "expected_model_artifacts": True,
        },
        {
            "case_id": "incomplete_final_board_pick_prerequisite_fails_closed",
            "prerequisite_path": incomplete_final_prerequisite,
            "tasks": ["e4:e5"],
            "max_steps": 96,
            "expected_return_code": 1,
            "expected_status": "failed_prerequisite_or_rollout_check",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "development_board_pick_prerequisite_failed",
            "expected_board_pick_failed_checks_contain": [
                "final_board_contact_observed",
                "final_target_xy_within_tolerance",
            ],
            "expected_all_complete": True,
            "expected_release_synced": True,
            "expected_episode_count": 1,
            "expect_transition_count_positive": True,
            "expected_model_authority": "development_scaffold_not_reviewed",
            "expected_rollout_use": "debug_imitation_curriculum_only",
            "expected_all_fallback_free": True,
            "expected_model_artifacts": True,
        },
        {
            "case_id": "short_budget_records_incomplete_rollout",
            "prerequisite_path": valid_prerequisite,
            "tasks": ["e4:e5"],
            "max_steps": 2,
            "expected_return_code": 1,
            "expected_status": "failed_prerequisite_or_rollout_check",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": True,
            "expected_board_pick_prerequisite_status": "development_board_pick_prerequisite_verified",
            "expected_all_complete": False,
            "expected_release_synced": False,
            "expected_episode_count": 1,
            "expect_transition_count_positive": True,
            "expected_model_authority": "development_scaffold_not_reviewed",
            "expected_rollout_use": "debug_imitation_curriculum_only",
            "expected_all_fallback_free": True,
            "expected_model_artifacts": True,
        },
        {
            "case_id": "invalid_task_syntax_fails_closed",
            "prerequisite_path": valid_prerequisite,
            "tasks": ["e4-e5"],
            "max_steps": 96,
            "expected_return_code": 1,
            "expected_status": "invalid_task_configuration",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "not_checked_invalid_task_configuration",
            "expected_all_complete": False,
            "expected_release_synced": False,
            "expected_episode_count": 0,
            "expect_transition_count_positive": False,
            "expected_model_authority": "invalid_task_configuration_not_authority",
            "expected_rollout_use": "not_collected_invalid_task_configuration",
            "expected_all_fallback_free": False,
            "expected_model_artifacts": False,
            "expected_configuration_error_contains": "Task must be SOURCE:TARGET",
        },
        {
            "case_id": "invalid_task_square_fails_closed",
            "prerequisite_path": valid_prerequisite,
            "tasks": ["z9:e5"],
            "max_steps": 96,
            "expected_return_code": 1,
            "expected_status": "invalid_task_configuration",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "not_checked_invalid_task_configuration",
            "expected_all_complete": False,
            "expected_release_synced": False,
            "expected_episode_count": 0,
            "expect_transition_count_positive": False,
            "expected_model_authority": "invalid_task_configuration_not_authority",
            "expected_rollout_use": "not_collected_invalid_task_configuration",
            "expected_all_fallback_free": False,
            "expected_model_artifacts": False,
            "expected_configuration_error_contains": "Invalid chess square",
        },
        {
            "case_id": "same_source_target_task_fails_closed",
            "prerequisite_path": valid_prerequisite,
            "tasks": ["e4:e4"],
            "max_steps": 96,
            "expected_return_code": 1,
            "expected_status": "invalid_task_configuration",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "not_checked_invalid_task_configuration",
            "expected_all_complete": False,
            "expected_release_synced": False,
            "expected_episode_count": 0,
            "expect_transition_count_positive": False,
            "expected_model_authority": "invalid_task_configuration_not_authority",
            "expected_rollout_use": "not_collected_invalid_task_configuration",
            "expected_all_fallback_free": False,
            "expected_model_artifacts": False,
            "expected_configuration_error_contains": "source_square and target_square must differ",
        },
        {
            "case_id": "nonpositive_step_budget_fails_closed",
            "prerequisite_path": valid_prerequisite,
            "tasks": ["e4:e5"],
            "max_steps": 0,
            "expected_return_code": 1,
            "expected_status": "invalid_task_configuration",
            "expected_rollout_ok": False,
            "expected_development_prerequisites_satisfied": False,
            "expected_board_pick_prerequisite_status": "not_checked_invalid_task_configuration",
            "expected_all_complete": False,
            "expected_release_synced": False,
            "expected_episode_count": 0,
            "expect_transition_count_positive": False,
            "expected_model_authority": "invalid_task_configuration_not_authority",
            "expected_rollout_use": "not_collected_invalid_task_configuration",
            "expected_all_fallback_free": False,
            "expected_model_artifacts": False,
            "expected_configuration_error_contains": "max_steps must be positive",
        },
    ]


def summarize_case(
    *,
    spec: dict[str, Any],
    record: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(spec["case_id"])
    errors: list[str] = []
    board_pick = summary.get("board_pick_prerequisite")
    board_pick = board_pick if isinstance(board_pick, dict) else {}
    blockers = summary.get("serious_policy_training_blockers")
    blockers = blockers if isinstance(blockers, list) else []
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    model_xml_path = artifacts.get("model_xml")
    manifest_path = artifacts.get("manifest_json")
    observations = {
        "return_code": record.get("return_code"),
        "ok": summary.get("ok"),
        "status": summary.get("status"),
        "model_authority": summary.get("model_authority"),
        "observed_evidence_is_physical_so101_authority": summary.get(
            "observed_evidence_is_physical_so101_authority"
        ),
        "observed_evidence_is_policy_training_authority": summary.get(
            "observed_evidence_is_policy_training_authority"
        ),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": summary.get("ready_for_policy_training"),
        "training_authority_status": summary.get("training_authority_status"),
        "rollout_use": summary.get("rollout_use"),
        "episode_count": summary.get("episode_count"),
        "transition_count": summary.get("transition_count"),
        "all_scripted_pick_place_complete": summary.get("all_scripted_pick_place_complete"),
        "all_mujoco_fallback_free": summary.get("all_mujoco_fallback_free"),
        "all_mujoco_piece_release_synced": summary.get("all_mujoco_piece_release_synced"),
        "development_prerequisites_satisfied": summary.get("development_prerequisites_satisfied"),
        "board_pick_prerequisite_status": board_pick.get("status"),
        "board_pick_prerequisite_ok": board_pick.get("ok"),
        "board_pick_failed_checks": board_pick.get("failed_checks"),
        "serious_policy_training_blockers": blockers,
        "configuration_error": summary.get("configuration_error"),
        "artifacts": artifacts,
        "model_xml_exists": isinstance(model_xml_path, str) and Path(model_xml_path).is_file(),
        "manifest_json_exists": isinstance(manifest_path, str) and Path(manifest_path).is_file(),
    }

    add_error(errors, f"{case_id}.return_code", observations["return_code"], spec["expected_return_code"])
    add_error(errors, f"{case_id}.ok", observations["ok"], spec["expected_rollout_ok"])
    add_error(errors, f"{case_id}.status", observations["status"], spec["expected_status"])
    add_error(
        errors,
        f"{case_id}.model_authority",
        observations["model_authority"],
        spec["expected_model_authority"],
    )
    add_error(
        errors,
        f"{case_id}.physical_authority",
        observations["observed_evidence_is_physical_so101_authority"],
        False,
    )
    add_error(
        errors,
        f"{case_id}.policy_authority",
        observations["observed_evidence_is_policy_training_authority"],
        False,
    )
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
    add_error(
        errors,
        f"{case_id}.development_prerequisites_satisfied",
        observations["development_prerequisites_satisfied"],
        spec["expected_development_prerequisites_satisfied"],
    )
    add_error(
        errors,
        f"{case_id}.board_pick_prerequisite_status",
        observations["board_pick_prerequisite_status"],
        spec["expected_board_pick_prerequisite_status"],
    )
    for failed_check in spec.get("expected_board_pick_failed_checks_contain", []):
        failed_checks = observations["board_pick_failed_checks"]
        if not isinstance(failed_checks, list) or failed_check not in failed_checks:
            errors.append(
                f"{case_id}.board_pick_failed_checks: expected {failed_check!r} in {failed_checks!r}"
            )
    add_error(
        errors,
        f"{case_id}.all_scripted_pick_place_complete",
        observations["all_scripted_pick_place_complete"],
        spec["expected_all_complete"],
    )
    add_error(
        errors,
        f"{case_id}.all_mujoco_fallback_free",
        observations["all_mujoco_fallback_free"],
        spec["expected_all_fallback_free"],
    )
    add_error(
        errors,
        f"{case_id}.all_mujoco_piece_release_synced",
        observations["all_mujoco_piece_release_synced"],
        spec["expected_release_synced"],
    )
    add_error(errors, f"{case_id}.episode_count", observations["episode_count"], spec["expected_episode_count"])
    if spec["expect_transition_count_positive"] and not (
        isinstance(observations["transition_count"], int) and observations["transition_count"] > 0
    ):
        errors.append(f"{case_id}.transition_count: expected positive int")
    if not spec["expect_transition_count_positive"]:
        add_error(errors, f"{case_id}.transition_count", observations["transition_count"], 0)
    add_error(
        errors,
        f"{case_id}.rollout_use",
        observations["rollout_use"],
        spec["expected_rollout_use"],
    )
    if "expected_configuration_error_contains" in spec:
        configuration_error = observations["configuration_error"]
        if not isinstance(configuration_error, dict):
            errors.append(f"{case_id}.configuration_error: expected dict, got {configuration_error!r}")
        else:
            message = configuration_error.get("message")
            expected = str(spec["expected_configuration_error_contains"])
            if expected not in str(message):
                errors.append(f"{case_id}.configuration_error.message: expected {expected!r} in {message!r}")
    if "reviewed_model_backed_board_source_pick_place" not in blockers:
        errors.append(f"{case_id}.serious_policy_training_blockers: missing reviewed_model_backed_board_source_pick_place")
    for key in ("summary_json", "transitions_jsonl", "episodes_csv", "readme"):
        artifact_path = artifacts.get(key)
        if not isinstance(artifact_path, str) or not Path(artifact_path).is_file():
            errors.append(f"{case_id}.artifacts.{key}: expected existing path")
    for key in ("model_xml", "manifest_json"):
        artifact_path = artifacts.get(key)
        if not isinstance(artifact_path, str):
            errors.append(f"{case_id}.artifacts.{key}: expected path string")
        elif spec["expected_model_artifacts"] and not Path(artifact_path).is_file():
            errors.append(f"{case_id}.artifacts.{key}: expected existing path")
        elif not spec["expected_model_artifacts"] and Path(artifact_path).is_file():
            errors.append(f"{case_id}.artifacts.{key}: expected no generated file")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "record": record,
        "summary_path": record["summary_path"],
        "expected": {
            "return_code": spec["expected_return_code"],
            "status": spec["expected_status"],
            "rollout_ok": spec["expected_rollout_ok"],
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
        str(ROLLOUT_SCRIPT),
        "--development-board-pick-summary-json",
        str(spec["prerequisite_path"]),
        "--output-dir",
        str(case_dir),
        "--max-steps",
        str(spec["max_steps"]),
    ]
    for task in spec["tasks"]:
        command.extend(["--task", str(task)])
    record, summary = run_child(
        case_dir=case_dir,
        command=command,
        expected_summary_path=case_dir / ROLLOUT_SUMMARY_NAME,
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
        "rollout_ok": observations.get("ok"),
        "episode_count": observations.get("episode_count"),
        "transition_count": observations.get("transition_count"),
        "all_scripted_pick_place_complete": observations.get("all_scripted_pick_place_complete"),
        "all_mujoco_fallback_free": observations.get("all_mujoco_fallback_free"),
        "all_mujoco_piece_release_synced": observations.get("all_mujoco_piece_release_synced"),
        "development_prerequisites_satisfied": observations.get("development_prerequisites_satisfied"),
        "board_pick_prerequisite_status": observations.get("board_pick_prerequisite_status"),
        "board_pick_failed_checks": observations.get("board_pick_failed_checks"),
        "ready_for_policy_training": observations.get("ready_for_policy_training"),
        "policy_authority": observations.get("observed_evidence_is_policy_training_authority"),
        "rollout_use": observations.get("rollout_use"),
        "configuration_error": observations.get("configuration_error"),
        "model_xml_exists": observations.get("model_xml_exists"),
        "manifest_json_exists": observations.get("manifest_json_exists"),
        "summary_path": case["summary_path"],
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Training Rollouts Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `passed_rollout_case_count`: `{summary['passed_rollout_case_count']}`",
        f"- `expected_failure_case_count`: `{summary['expected_failure_case_count']}`",
        f"- `invalid_task_case_count`: `{summary['invalid_task_case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "This matrix validates development rollout collection and fail-closed boundaries. It is not policy-training authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Rollout OK | Prerequisite | Episodes | Transitions | Complete | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{rollout_ok}` | `{prereq}` | `{episodes}` | `{transitions}` | `{complete}` | `{summary}` |".format(
                case_id=case["case_id"],
                status=obs.get("status"),
                rollout_ok=obs.get("ok"),
                prereq=obs.get("board_pick_prerequisite_status"),
                episodes=obs.get("episode_count"),
                transitions=obs.get("transition_count"),
                complete=obs.get("all_scripted_pick_place_complete"),
                summary=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Passing rollout cases use generated `development_scaffold_not_reviewed` MJCF.",
            "- Missing, failed, or incomplete-final board-pick prerequisites must keep rollout status non-OK.",
            "- Invalid rollout task configurations must write summary/CSV/README artifacts without generating model XML or manifests.",
            "- Short-budget rollouts must record incomplete episodes instead of becoming policy-ready.",
            "- `ready_for_policy_training` and policy authority flags must remain false.",
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

    prereq_record, prereq_summary = run_valid_board_pick_prerequisite(output_dir, args.python)
    failed_prerequisite = output_dir / "prerequisites" / "failed_board_pick_summary.json"
    write_failed_board_pick_prerequisite(failed_prerequisite)
    incomplete_final_prerequisite = (
        output_dir / "prerequisites" / "incomplete_final_board_pick_summary.json"
    )
    write_incomplete_final_board_pick_prerequisite(incomplete_final_prerequisite)

    valid_prerequisite = Path(prereq_record["summary_path"])
    cases = [
        run_case(output_dir=output_dir, python_path=args.python, spec=spec)
        for spec in case_specs(
            output_dir,
            valid_prerequisite,
            failed_prerequisite,
            incomplete_final_prerequisite,
        )
    ]
    ok = all(case["ok"] for case in cases) and prereq_summary.get("ok") is True
    passed_rollout_cases = [
        case for case in cases if case["observations"].get("ok") is True
    ]
    expected_failure_cases = [
        case for case in cases if case["observations"].get("ok") is False
    ]
    invalid_task_cases = [
        case for case in cases if case["observations"].get("status") == "invalid_task_configuration"
    ]
    summary_path = output_dir / "so101_training_rollouts_matrix_summary.json"
    csv_path = output_dir / "so101_training_rollouts_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "so101_training_rollouts_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "valid_board_pick_prerequisite": {
            "record": prereq_record,
            "summary_path": prereq_record["summary_path"],
            "ok": prereq_summary.get("ok"),
            "status": prereq_summary.get("status"),
        },
        "case_count": len(cases),
        "passed_rollout_case_count": len(passed_rollout_cases),
        "expected_failure_case_count": len(expected_failure_cases),
        "invalid_task_case_count": len(invalid_task_cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "passed_rollout_case_ids": [case["case_id"] for case in passed_rollout_cases],
        "expected_failure_case_ids": [case["case_id"] for case in expected_failure_cases],
        "invalid_task_case_ids": [case["case_id"] for case in invalid_task_cases],
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "Development rollout cases use symbolic task transfer and generated MJCF.",
            "The board-pick prerequisite is still seeded development fixture evidence.",
            "Invalid task cases fail closed before model generation or rollout collection.",
            "This matrix is not reviewed SO-101 policy-training authority.",
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
