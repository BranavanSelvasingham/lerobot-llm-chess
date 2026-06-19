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

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_chess_env_matrix"
SCHEMA = "lerobot.sim.so101_chess_env_matrix.v1"
SCENE_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_scene.py"
ENV_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_chess_env.py"
ENV_SUMMARY_NAME = "so101_chess_env_summary.json"
SCENE_SUMMARY_NAME = "so101_mujoco_scene_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a focused hardware-free matrix over the SO-101 Gymnasium chess "
            "environment gate. Cases distinguish joint-state fallback, fail-closed "
            "required MuJoCo backend behavior, and development-MuJoCo task wiring."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child scene/env checks.",
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
        "env_ok",
        "status",
        "model_authority",
        "max_steps",
        "gymnasium_required",
        "mujoco_backend_required",
        "mujoco_backend_loaded",
        "joint_state_fallback_active",
        "sim_status_ok",
        "sim_fallback",
        "sim_status_reason",
        "configuration_error",
        "gymnasium_task_wiring_status",
        "training_authority_status",
        "ready_for_model_backed_ik",
        "ready_for_policy_training",
        "scripted_pick_place_complete",
        "expected_status",
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


def create_development_scene(output_dir: Path, python_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    scene_dir = output_dir / "development_scene"
    summary_path = scene_dir / SCENE_SUMMARY_NAME
    command = [
        executable_arg(python_path),
        str(SCENE_SCRIPT),
        "--output-dir",
        str(scene_dir),
    ]
    return run_child(case_dir=scene_dir, command=command, expected_summary_path=summary_path)


def case_specs(development_model_path: str | None, invalid_model_path: str) -> list[dict[str, Any]]:
    return [
        {
            "case_id": "fallback_without_model_allowed",
            "args": [],
            "expect": {
                "return_code": 0,
                "env_ok": True,
                "status": "ok",
                "model_authority": "joint_state_fallback_no_reviewed_model",
                "gymnasium_required": False,
                "mujoco_backend_required": False,
                "mujoco_backend_loaded": False,
                "joint_state_fallback_active": True,
                "sim_status_ok": False,
                "sim_fallback": "joint_state",
                "gymnasium_task_wiring_status": "joint_state_fallback_env_scripted",
                "training_authority_status": "joint_state_fallback_env_verified_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": True,
            },
        },
        {
            "case_id": "gymnasium_required_fallback_allowed",
            "args": ["--require-gymnasium"],
            "expect": {
                "return_code": 0,
                "env_ok": True,
                "status": "ok",
                "model_authority": "joint_state_fallback_no_reviewed_model",
                "gymnasium_required": True,
                "mujoco_backend_required": False,
                "mujoco_backend_loaded": False,
                "joint_state_fallback_active": True,
                "sim_status_ok": False,
                "sim_fallback": "joint_state",
                "gymnasium_task_wiring_status": "joint_state_fallback_env_scripted",
                "training_authority_status": "joint_state_fallback_env_verified_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": True,
            },
        },
        {
            "case_id": "require_mujoco_without_model_fails",
            "args": ["--require-gymnasium", "--require-mujoco"],
            "expect": {
                "return_code": 1,
                "env_ok": False,
                "status": "failed_requirements",
                "model_authority": "joint_state_fallback_no_reviewed_model",
                "gymnasium_required": True,
                "mujoco_backend_required": True,
                "mujoco_backend_loaded": False,
                "joint_state_fallback_active": True,
                "sim_status_ok": False,
                "sim_fallback": "joint_state",
                "gymnasium_task_wiring_status": "failed_requirements",
                "training_authority_status": "requirements_failed_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": True,
                "hard_failures_contain": ["mujoco_backend_required_but_not_loaded"],
            },
        },
        {
            "case_id": "require_mujoco_invalid_model_path_fails",
            "args": [
                "--require-gymnasium",
                "--require-mujoco",
                "--mujoco-model-path",
                invalid_model_path,
            ],
            "expect": {
                "return_code": 1,
                "env_ok": False,
                "status": "failed_requirements",
                "model_authority": "joint_state_fallback_no_reviewed_model",
                "gymnasium_required": True,
                "mujoco_backend_required": True,
                "mujoco_backend_loaded": False,
                "joint_state_fallback_active": True,
                "sim_status_ok": False,
                "sim_fallback": "joint_state",
                "sim_status_reason_contains": "MuJoCo model path does not exist",
                "gymnasium_task_wiring_status": "failed_requirements",
                "training_authority_status": "requirements_failed_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": True,
                "hard_failures_contain": ["mujoco_backend_required_but_not_loaded"],
            },
        },
        {
            "case_id": "invalid_max_steps_rejected",
            "args": ["--max-steps", "0"],
            "expect": {
                "return_code": 1,
                "env_ok": False,
                "status": "invalid_task_configuration",
                "model_authority": "invalid_task_configuration_not_authority",
                "max_steps": 0,
                "gymnasium_required": False,
                "mujoco_backend_required": False,
                "mujoco_backend_loaded": False,
                "joint_state_fallback_active": False,
                "sim_status_ok": False,
                "sim_fallback": None,
                "sim_status_reason_contains": "max_steps must be positive",
                "configuration_error_contains": "max_steps must be positive",
                "gymnasium_task_wiring_status": "invalid_task_configuration",
                "training_authority_status": "requirements_failed_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": False,
                "hard_failures_contain": ["invalid_task_configuration"],
            },
        },
        {
            "case_id": "short_budget_scripted_pick_place_incomplete_fails",
            "args": ["--max-steps", "1"],
            "expect": {
                "return_code": 1,
                "env_ok": False,
                "status": "failed_requirements",
                "model_authority": "joint_state_fallback_no_reviewed_model",
                "max_steps": 1,
                "gymnasium_required": False,
                "mujoco_backend_required": False,
                "mujoco_backend_loaded": False,
                "joint_state_fallback_active": True,
                "sim_status_ok": False,
                "sim_fallback": "joint_state",
                "gymnasium_task_wiring_status": "failed_requirements",
                "training_authority_status": "requirements_failed_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": False,
                "hard_failures_contain": ["scripted_pick_place_incomplete"],
            },
        },
        {
            "case_id": "development_mujoco_required_not_policy_ready",
            "args": [
                "--require-gymnasium",
                "--require-mujoco",
                "--mujoco-model-path",
                development_model_path or "",
            ],
            "expect": {
                "return_code": 0,
                "env_ok": True,
                "status": "ok",
                "model_authority": "development_scaffold_not_reviewed",
                "max_steps": 96,
                "gymnasium_required": True,
                "mujoco_backend_required": True,
                "mujoco_backend_loaded": True,
                "joint_state_fallback_active": False,
                "sim_status_ok": True,
                "sim_fallback": None,
                "gymnasium_task_wiring_status": "development_mujoco_env_scripted",
                "training_authority_status": "development_mujoco_env_verified_not_policy_ready",
                "ready_for_model_backed_ik": False,
                "ready_for_policy_training": False,
                "scripted_pick_place_complete": True,
            },
        },
    ]


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def summarize_case(
    *,
    case_id: str,
    record: dict[str, Any],
    summary: dict[str, Any],
    expect: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    sim_status = summary.get("sim_status") if isinstance(summary.get("sim_status"), dict) else {}
    config = summary.get("config") if isinstance(summary.get("config"), dict) else {}
    configuration_error = (
        summary.get("configuration_error")
        if isinstance(summary.get("configuration_error"), dict)
        else {}
    )
    scripted = (
        summary.get("scripted_pick_place")
        if isinstance(summary.get("scripted_pick_place"), dict)
        else {}
    )
    observations = {
        "env_ok": summary.get("ok"),
        "status": summary.get("status"),
        "model_authority": summary.get("model_authority"),
        "max_steps": config.get("max_steps"),
        "gymnasium_required": summary.get("gymnasium_required"),
        "mujoco_backend_required": summary.get("mujoco_backend_required"),
        "mujoco_backend_loaded": summary.get("mujoco_backend_loaded"),
        "joint_state_fallback_active": summary.get("joint_state_fallback_active"),
        "sim_status_ok": sim_status.get("ok"),
        "sim_fallback": sim_status.get("fallback"),
        "sim_status_reason": sim_status.get("reason"),
        "configuration_error": configuration_error,
        "gymnasium_task_wiring_status": summary.get("gymnasium_task_wiring_status"),
        "training_authority_status": summary.get("training_authority_status"),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": summary.get("ready_for_policy_training"),
        "scripted_pick_place_complete": scripted.get("scripted_pick_place_complete"),
        "hard_failures": summary.get("hard_failures"),
        "training_authority_blockers": summary.get("training_authority_blockers"),
        "artifacts": summary.get("artifacts"),
    }
    add_error(errors, f"{case_id}.return_code", record.get("return_code"), expect["return_code"])
    for key, expected in expect.items():
        if key in {
            "return_code",
            "hard_failures_contain",
            "sim_status_reason_contains",
            "configuration_error_contains",
        }:
            continue
        add_error(errors, f"{case_id}.{key}", observations.get(key), expected)
    reason_contains = expect.get("sim_status_reason_contains")
    if isinstance(reason_contains, str) and reason_contains not in str(observations.get("sim_status_reason")):
        errors.append(
            f"{case_id}.sim_status_reason: expected {reason_contains!r} in {observations.get('sim_status_reason')!r}"
        )
    configuration_error_contains = expect.get("configuration_error_contains")
    configuration_error_message = observations["configuration_error"].get("message")
    if (
        isinstance(configuration_error_contains, str)
        and configuration_error_contains not in str(configuration_error_message)
    ):
        errors.append(
            f"{case_id}.configuration_error: expected {configuration_error_contains!r} in {configuration_error_message!r}"
        )
    for required_failure in expect.get("hard_failures_contain", []):
        hard_failures = observations.get("hard_failures")
        if not isinstance(hard_failures, list) or required_failure not in hard_failures:
            errors.append(f"{case_id}.hard_failures missing {required_failure!r}")
    blockers = observations.get("training_authority_blockers")
    if not isinstance(blockers, list):
        errors.append(f"{case_id}.training_authority_blockers: expected list")
    elif "reviewed_so101_model_bundle" not in blockers:
        errors.append(f"{case_id}.training_authority_blockers missing reviewed_so101_model_bundle")
    artifacts = observations.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append(f"{case_id}.artifacts: expected dict")
    else:
        for key in ("summary_json", "steps_csv", "readme"):
            artifact_path = artifacts.get(key)
            if not isinstance(artifact_path, str) or not Path(artifact_path).is_file():
                errors.append(f"{case_id}.artifacts.{key}: expected existing path")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "record": record,
        "summary_path": record["summary_path"],
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
        str(ENV_SCRIPT),
        "--output-dir",
        str(case_dir),
        *[str(value) for value in spec["args"]],
    ]
    record, summary = run_child(
        case_dir=case_dir,
        command=command,
        expected_summary_path=case_dir / ENV_SUMMARY_NAME,
    )
    record["case_id"] = case_id
    return summarize_case(
        case_id=case_id,
        record=record,
        summary=summary,
        expect=spec["expect"],
    )


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    observations = case["observations"]
    expected = case["expected"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "return_code": case["record"].get("return_code"),
        "expected_return_code": expected.get("return_code"),
        "env_ok": observations.get("env_ok"),
        "status": observations.get("status"),
        "model_authority": observations.get("model_authority"),
        "max_steps": observations.get("max_steps"),
        "gymnasium_required": observations.get("gymnasium_required"),
        "mujoco_backend_required": observations.get("mujoco_backend_required"),
        "mujoco_backend_loaded": observations.get("mujoco_backend_loaded"),
        "joint_state_fallback_active": observations.get("joint_state_fallback_active"),
        "sim_status_ok": observations.get("sim_status_ok"),
        "sim_fallback": observations.get("sim_fallback"),
        "sim_status_reason": observations.get("sim_status_reason"),
        "configuration_error": observations.get("configuration_error"),
        "gymnasium_task_wiring_status": observations.get("gymnasium_task_wiring_status"),
        "training_authority_status": observations.get("training_authority_status"),
        "ready_for_model_backed_ik": observations.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": observations.get("ready_for_policy_training"),
        "scripted_pick_place_complete": observations.get("scripted_pick_place_complete"),
        "expected_status": expected.get("status"),
        "summary_path": case["summary_path"],
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Chess Env Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "This matrix is hardware-free Gymnasium wiring evidence only. It does not claim reviewed physical SO-101 authority or policy-training readiness.",
        "",
        "## Cases",
        "",
        "| Case | Status | Env OK | MuJoCo Required | MuJoCo Loaded | Fallback | Task Wiring | Training Authority | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{env_ok}` | `{required}` | `{loaded}` | `{fallback}` | `{wiring}` | `{authority}` | `{summary_path}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                env_ok=obs.get("env_ok"),
                required=obs.get("mujoco_backend_required"),
                loaded=obs.get("mujoco_backend_loaded"),
                fallback=obs.get("joint_state_fallback_active"),
                wiring=obs.get("gymnasium_task_wiring_status"),
                authority=obs.get("training_authority_status"),
                summary_path=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Joint-state fallback is allowed only when MuJoCo is not required.",
            "- `--require-mujoco` must fail closed when no MuJoCo model path is supplied or the supplied model path cannot load.",
            "- Development MJCF task wiring remains `development_scaffold_not_reviewed` and `ready_for_policy_training: false`.",
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

    scene_record, scene_summary = create_development_scene(output_dir, args.python)
    scene_artifacts = scene_summary.get("artifacts") if isinstance(scene_summary.get("artifacts"), dict) else {}
    development_model_path = scene_artifacts.get("model_xml")
    if not isinstance(development_model_path, str) or not Path(development_model_path).is_file():
        development_model_path = None

    invalid_model_path = str(output_dir / "missing_models" / "so101_missing.xml")
    cases = [
        run_case(output_dir=output_dir, python_path=args.python, spec=spec)
        for spec in case_specs(development_model_path, invalid_model_path)
    ]
    scene_ok = bool(scene_summary.get("ok")) and development_model_path is not None
    ok = scene_ok and all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_chess_env_matrix_summary.json"
    csv_path = output_dir / "so101_chess_env_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "so101_chess_env_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "development_scene": {
            "ok": scene_ok,
            "record": scene_record,
            "summary_path": scene_record["summary_path"],
            "model_path": development_model_path,
            "model_authority": scene_summary.get("model_authority"),
            "ready_for_model_backed_ik": scene_summary.get("ready_for_model_backed_ik"),
        },
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
            "Joint-state fallback verifies Gymnasium API plumbing only.",
            "Development MuJoCo model loading verifies generated MJCF task wiring only.",
            "No case supplies reviewed physical SO-101 model authority or policy-training readiness.",
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
