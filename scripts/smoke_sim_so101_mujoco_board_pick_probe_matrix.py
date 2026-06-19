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
        "ready_for_model_backed_ik",
        "ready_for_policy_training",
        "physical_authority",
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
        "manual_piece_pose_used_after_reset": summary.get("manual_piece_pose_used_after_reset"),
        "robot_pose_seeded_for_source_fixture": summary.get("robot_pose_seeded_for_source_fixture"),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": summary.get("ready_for_policy_training"),
        "physical_authority": summary.get("observed_evidence_is_physical_so101_authority"),
        "next_required_for_goal": summary.get("next_required_for_goal"),
        "next_required_action_ids": summary.get("next_required_action_ids"),
        "next_required_action_count": summary.get("next_required_action_count"),
        "configuration_error": summary.get("configuration_error"),
        "artifacts": artifacts,
        "model_xml_exists": isinstance(model_xml_path, str) and Path(model_xml_path).is_file(),
        "manifest_json_exists": isinstance(manifest_path, str) and Path(manifest_path).is_file(),
    }

    add_error(errors, f"{case_id}.return_code", record.get("return_code"), expected_return_code)
    add_error(errors, f"{case_id}.ok", observations["ok"], expect_ok)
    add_error(errors, f"{case_id}.status", observations["status"], spec["expected_status"])
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
        ):
            add_error(errors, f"{case_id}.{key}", observations[key], expected)
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
        "ready_for_model_backed_ik": observations.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": observations.get("ready_for_policy_training"),
        "physical_authority": observations.get("physical_authority"),
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
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "verified_pick_place_case_count": len(verified_cases),
        "expected_gap_case_count": len(expected_gap_cases),
        "invalid_task_case_count": len(invalid_task_cases),
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
