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
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smoke_sim_so101_bundle_ready_forwarding import create_fixtures  # noqa: E402

DEFAULT_OUTPUT_DIR = (
    Path("/private/tmp") / "lerobot_sim" / "so101_reviewed_mujoco_bundle_matrix"
)
SCHEMA = "lerobot.sim.so101_reviewed_mujoco_bundle_matrix.v1"
REVIEWED_MUJOCO_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_reviewed_mujoco_bundle.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a compact hardware-free matrix over the SO-101 reviewed MuJoCo "
            "bundle gate. Fixture manifests are generated under the output directory "
            "and remain non-authoritative automation evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child reviewed-bundle checks.",
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
        "gate_ok",
        "status",
        "manifest_status",
        "ready_for_model_backed_ik",
        "model_authority",
        "physical_so101_model_authority_ready",
        "hardware_free_regression_fixture_ready",
        "reviewed_model_motion_checked",
        "motion_authority_status",
        "physical_reviewed_model_motion_checked",
        "hardware_free_fixture_motion_checked",
        "motion_evidence_not_physical_so101_authority",
        "tcp_offset_status",
        "alignment_status",
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


def case_specs(fixtures: dict[str, Path]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": "missing_manifest_nonfailing",
            "manifest_path": None,
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
            },
        },
        {
            "case_id": "missing_manifest_require_ready_fails",
            "manifest_path": None,
            "require_ready": True,
            "expect": {
                "return_code": 1,
                "gate_ok": False,
                "status": "reviewed_mujoco_bundle_required_but_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
            },
        },
        {
            "case_id": "placeholder_manifest_not_ready",
            "manifest_path": fixtures["placeholder_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
            },
        },
        {
            "case_id": "invalid_tcp_offset_shape_not_ready",
            "manifest_path": fixtures["invalid_tcp_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "tcp_offset_status": "invalid",
                "missing_inputs_contains": ["tcp_offset_m"],
                "tcp_offset_diagnostics_contains": ["missing_axis:z"],
            },
        },
        {
            "case_id": "invalid_base_to_board_transform_not_ready",
            "manifest_path": fixtures["invalid_alignment_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "alignment_status": "invalid",
                "missing_inputs_contains": ["base_to_board_transform"],
                "alignment_diagnostics_contains": ["base_to_board_rotation_rpy_missing"],
            },
        },
        {
            "case_id": "ready_synthetic_fixture_motion_not_physical",
            "manifest_path": fixtures["ready_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_motion_checked",
                "ready_for_model_backed_ik": True,
                "model_authority": (
                    "hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_so101_model_authority_ready": False,
                "hardware_free_regression_fixture_ready": True,
                "reviewed_model_motion_checked": True,
                "motion_authority_status": (
                    "hardware_free_fixture_motion_checked_not_physical_so101_authority"
                ),
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": True,
                "motion_evidence_not_physical_so101_authority": True,
            },
        },
    ]


def run_case(
    *,
    spec: dict[str, Any],
    python_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = str(spec["case_id"])
    case_dir = output_dir / "cases" / case_id
    summary_path = case_dir / "so101_reviewed_mujoco_bundle_summary.json"
    python_executable = executable_arg(python_path)
    command = [
        python_executable,
        str(REVIEWED_MUJOCO_SCRIPT),
        "--output-dir",
        str(case_dir),
        "--python",
        python_executable,
    ]
    manifest_path = spec.get("manifest_path")
    if isinstance(manifest_path, Path):
        command.extend(["--manifest-path", str(manifest_path)])
    if spec.get("require_ready") is True:
        command.append("--require-ready-reviewed-model")

    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / f"{case_id}_stdout.txt"
    stderr_path = case_dir / f"{case_id}_stderr.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)

    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        summary = {
            "ok": False,
            "status": "summary_unavailable",
            "summary_error": f"{type(exc).__name__}: {exc}",
        }

    record = {
        "case_id": case_id,
        "command": command,
        "return_code": result.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(summary_path),
    }
    return record, summary


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def summarize_case(
    *,
    record: dict[str, Any],
    summary: dict[str, Any],
    expect: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    case_id = str(record["case_id"])
    add_error(errors, f"{case_id}.return_code", record.get("return_code"), expect["return_code"])
    add_error(errors, f"{case_id}.gate_ok", summary.get("ok"), expect["gate_ok"])
    for key in (
        "status",
        "ready_for_model_backed_ik",
        "model_authority",
        "physical_so101_model_authority_ready",
        "hardware_free_regression_fixture_ready",
        "reviewed_model_motion_checked",
        "motion_authority_status",
        "physical_reviewed_model_motion_checked",
        "hardware_free_fixture_motion_checked",
        "motion_evidence_not_physical_so101_authority",
    ):
        if key in expect:
            add_error(errors, f"{case_id}.{key}", summary.get(key), expect[key])

    motion_authority = summary.get("motion_authority")
    if not isinstance(motion_authority, dict):
        errors.append(f"{case_id}.motion_authority: expected dict")
    else:
        add_error(
            errors,
            f"{case_id}.motion_authority_status_nested",
            motion_authority.get("status"),
            summary.get("motion_authority_status"),
        )
        add_error(
            errors,
            f"{case_id}.physical_motion_nested",
            motion_authority.get("physical_reviewed_model_motion_checked"),
            summary.get("physical_reviewed_model_motion_checked"),
        )
        add_error(
            errors,
            f"{case_id}.fixture_motion_nested",
            motion_authority.get("hardware_free_fixture_motion_checked"),
            summary.get("hardware_free_fixture_motion_checked"),
        )

    if "missing_inputs_contains" in expect:
        missing_inputs = summary.get("missing_inputs")
        if not isinstance(missing_inputs, list):
            errors.append(f"{case_id}.missing_inputs: expected list, got {missing_inputs!r}")
        else:
            for expected_input in expect["missing_inputs_contains"]:
                if expected_input not in missing_inputs:
                    errors.append(
                        f"{case_id}.missing_inputs: missing {expected_input!r} in {missing_inputs!r}"
                    )
    if "tcp_offset_status" in expect:
        add_error(
            errors,
            f"{case_id}.tcp_offset_status",
            (summary.get("tcp_offset") or {}).get("status"),
            expect["tcp_offset_status"],
        )
    if "alignment_status" in expect:
        add_error(
            errors,
            f"{case_id}.alignment_status",
            (summary.get("base_to_board_alignment") or {}).get("status"),
            expect["alignment_status"],
        )
    for diagnostics_key, summary_key in (
        ("tcp_offset_diagnostics_contains", "tcp_offset"),
        ("alignment_diagnostics_contains", "base_to_board_alignment"),
    ):
        if diagnostics_key not in expect:
            continue
        diagnostics = (summary.get(summary_key) or {}).get("diagnostics")
        diagnostics_text = "\n".join(str(item) for item in diagnostics or [])
        for expected_diagnostic in expect[diagnostics_key]:
            if expected_diagnostic not in diagnostics_text:
                errors.append(
                    f"{case_id}.{summary_key}.diagnostics: missing {expected_diagnostic!r} in {diagnostics!r}"
                )

    if summary.get("ready_for_model_backed_ik") is not True:
        add_error(
            errors,
            f"{case_id}.mujoco_load_absent_when_not_ready",
            "mujoco_model_load" in summary,
            False,
        )
        add_error(
            errors,
            f"{case_id}.simrobot_absent_when_not_ready",
            "sim_robot_mujoco_sync" in summary,
            False,
        )
    if summary.get("ready_for_model_backed_ik") is True:
        model_load = summary.get("mujoco_model_load")
        sim_sync = summary.get("sim_robot_mujoco_sync")
        if not isinstance(model_load, dict) or model_load.get("ok") is not True:
            errors.append(f"{case_id}.mujoco_model_load: expected ok true")
        if not isinstance(sim_sync, dict) or sim_sync.get("ok") is not True:
            errors.append(f"{case_id}.sim_robot_mujoco_sync: expected ok true")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "record": record,
        "summary_path": record["summary_path"],
        "observations": {
            "gate_ok": summary.get("ok"),
            "status": summary.get("status"),
            "manifest_status": summary.get("manifest_status"),
            "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
            "model_authority": summary.get("model_authority"),
            "physical_so101_model_authority_ready": summary.get(
                "physical_so101_model_authority_ready"
            ),
            "hardware_free_regression_fixture_ready": summary.get(
                "hardware_free_regression_fixture_ready"
            ),
            "reviewed_model_motion_checked": summary.get("reviewed_model_motion_checked"),
            "motion_authority_status": summary.get("motion_authority_status"),
            "physical_reviewed_model_motion_checked": summary.get(
                "physical_reviewed_model_motion_checked"
            ),
            "hardware_free_fixture_motion_checked": summary.get(
                "hardware_free_fixture_motion_checked"
            ),
            "motion_evidence_not_physical_so101_authority": summary.get(
                "motion_evidence_not_physical_so101_authority"
            ),
            "missing_inputs": summary.get("missing_inputs"),
            "tcp_offset_status": (summary.get("tcp_offset") or {}).get("status"),
            "tcp_offset_diagnostics": (summary.get("tcp_offset") or {}).get("diagnostics"),
            "alignment_status": (summary.get("base_to_board_alignment") or {}).get("status"),
            "alignment_diagnostics": (summary.get("base_to_board_alignment") or {}).get("diagnostics"),
            "artifacts": summary.get("artifacts"),
        },
    }


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    observations = case["observations"]
    expected = case["expected"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "return_code": case["record"].get("return_code"),
        "expected_return_code": expected.get("return_code"),
        "gate_ok": observations.get("gate_ok"),
        "status": observations.get("status"),
        "manifest_status": observations.get("manifest_status"),
        "ready_for_model_backed_ik": observations.get("ready_for_model_backed_ik"),
        "model_authority": observations.get("model_authority"),
        "physical_so101_model_authority_ready": observations.get(
            "physical_so101_model_authority_ready"
        ),
        "hardware_free_regression_fixture_ready": observations.get(
            "hardware_free_regression_fixture_ready"
        ),
        "reviewed_model_motion_checked": observations.get("reviewed_model_motion_checked"),
        "motion_authority_status": observations.get("motion_authority_status"),
        "physical_reviewed_model_motion_checked": observations.get(
            "physical_reviewed_model_motion_checked"
        ),
        "hardware_free_fixture_motion_checked": observations.get(
            "hardware_free_fixture_motion_checked"
        ),
        "motion_evidence_not_physical_so101_authority": observations.get(
            "motion_evidence_not_physical_so101_authority"
        ),
        "tcp_offset_status": observations.get("tcp_offset_status"),
        "alignment_status": observations.get("alignment_status"),
        "expected_status": expected.get("status"),
        "summary_path": case["summary_path"],
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Reviewed MuJoCo Bundle Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "Synthetic fixture caveat: ready fixture manifests are automation fixtures only. They prove MuJoCo load and SimRobot motion plumbing, not reviewed physical SO-101 authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Gate OK | Ready | Motion | Motion Authority | Physical Motion | Fixture Motion | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{gate_ok}` | `{ready}` | `{motion}` | `{authority}` | `{physical}` | `{fixture}` | `{summary_path}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                gate_ok=obs.get("gate_ok"),
                ready=obs.get("ready_for_model_backed_ik"),
                motion=obs.get("reviewed_model_motion_checked"),
                authority=obs.get("motion_authority_status"),
                physical=obs.get("physical_reviewed_model_motion_checked"),
                fixture=obs.get("hardware_free_fixture_motion_checked"),
                summary_path=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Missing or not-ready manifests must not attempt MuJoCo motion.",
            "- The `--require-ready-reviewed-model` case must fail closed when no ready manifest exists.",
            "- Ready synthetic fixture motion must remain `hardware_free_fixture_motion_checked_not_physical_so101_authority`.",
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

    fixtures = create_fixtures(output_dir)
    cases: list[dict[str, Any]] = []
    for spec in case_specs(fixtures):
        record, summary = run_case(
            spec=spec,
            python_path=args.python,
            output_dir=output_dir,
        )
        cases.append(summarize_case(record=record, summary=summary, expect=spec["expect"]))

    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_reviewed_mujoco_bundle_matrix_summary.json"
    csv_path = output_dir / "so101_reviewed_mujoco_bundle_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "reviewed_mujoco_bundle_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "fixtures": {key: str(normalize_path(value)) for key, value in fixtures.items()},
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "Synthetic fixture manifests live under the smoke output directory and are not physical SO-101 calibration truth.",
            "The ready fixture case exercises reviewed-bundle MuJoCo/SimRobot plumbing only.",
            "This smoke does not open robot hardware, cameras, GUI flows, network resources, or LLM/OpenAI paths.",
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
