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
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_bundle_probe_matrix"
SCHEMA = "lerobot.sim.so101_model_bundle_probe_matrix.v1"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_probe.py"
EXPECTED_TARGET_FRAME = "gripper_frame_link"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free matrix over the SO-101 model-bundle probe. "
            "Synthetic model fixtures are generated under the output directory and "
            "are not reviewed physical SO-101 authority."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child probe subprocesses.",
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
        "status",
        "model_request_status",
        "manifest_status",
        "ready_for_model_backed_ik",
        "model_authority",
        "authority_empty",
        "provenance_empty",
        "authority_row_status",
        "provenance_row_status",
        "authority_placeholder_fields",
        "provenance_placeholder_fields",
        "missing_inputs",
        "next_required_action_ids",
        "expected_status",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def synthetic_urdf(robot_name: str) -> str:
    return f"""<?xml version="1.0"?>
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Synthetic SO-101 model-bundle probe matrix fixture; not physical SO-101 authority. -->
<!-- onshape-to-robot provenance marker is fixture evidence only. -->
<robot name="{robot_name}">
  <link name="base_link"/>
  <link name="shoulder_pan_link"/>
  <link name="shoulder_lift_link"/>
  <link name="elbow_flex_link"/>
  <link name="wrist_flex_link"/>
  <link name="{EXPECTED_TARGET_FRAME}"/>

  <joint name="shoulder_pan" type="revolute">
    <parent link="base_link"/>
    <child link="shoulder_pan_link"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1.919862" upper="1.919862" effort="1" velocity="1"/>
  </joint>
  <joint name="shoulder_lift" type="revolute">
    <parent link="shoulder_pan_link"/>
    <child link="shoulder_lift_link"/>
    <axis xyz="0 1 0"/>
    <limit lower="-1.919862" upper="1.919862" effort="1" velocity="1"/>
  </joint>
  <joint name="elbow_flex" type="revolute">
    <parent link="shoulder_lift_link"/>
    <child link="elbow_flex_link"/>
    <axis xyz="0 1 0"/>
    <limit lower="-2.094395" upper="2.094395" effort="1" velocity="1"/>
  </joint>
  <joint name="wrist_flex" type="revolute">
    <parent link="elbow_flex_link"/>
    <child link="wrist_flex_link"/>
    <axis xyz="0 1 0"/>
    <limit lower="-2.094395" upper="2.094395" effort="1" velocity="1"/>
  </joint>
  <joint name="wrist_roll" type="revolute">
    <parent link="wrist_flex_link"/>
    <child link="{EXPECTED_TARGET_FRAME}"/>
    <axis xyz="1 0 0"/>
    <limit lower="-3.141593" upper="3.141593" effort="1" velocity="1"/>
  </joint>
</robot>
"""


def create_fixtures(output_dir: Path) -> dict[str, Path]:
    fixture_dir = output_dir / "fixtures" / "single_source_root"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "LICENSE").write_text(
        "Synthetic fixture license for hardware-free model-bundle probe matrix only.\n"
    )
    model_path = fixture_dir / "so101_synthetic_probe.urdf"
    model_path.write_text(synthetic_urdf("so101_synthetic_probe"))
    return {"model_path": model_path}


def placeholder_authority_args() -> list[str]:
    return [
        "--authority-reviewed-by",
        "TODO",
        "--authority-reviewed-at",
        "TBD",
        "--authority-review-id",
        "TODO",
        "--authority-review-scope",
        "model_identity",
        "--authority-review-scope",
        "provenance",
        "--authority-review-scope",
        "license",
        "--provenance-source-url",
        "TODO",
        "--provenance-export-tool",
        "placeholder-export",
        "--provenance-license",
        "unknown",
    ]


def valid_authority_args() -> list[str]:
    return [
        "--authority-reviewed-by",
        "smoke_sim_so101_model_bundle_probe_matrix",
        "--authority-reviewed-at",
        "2026-06-19",
        "--authority-review-id",
        "probe-matrix-review-fixture",
        "--authority-review-scope",
        "model_identity",
        "--authority-review-scope",
        "provenance",
        "--authority-review-scope",
        "license",
        "--provenance-source-url",
        "https://example.invalid/so101",
        "--provenance-export-tool",
        "onshape-to-robot",
        "--provenance-license",
        "synthetic fixture license",
    ]


def invalid_reviewed_at_args() -> list[str]:
    args = valid_authority_args()
    reviewed_at_index = args.index("--authority-reviewed-at") + 1
    args[reviewed_at_index] = "not-a-date"
    return args


def case_specs(fixtures: dict[str, Path]) -> list[dict[str, Any]]:
    model_path = fixtures["model_path"]
    return [
        {
            "case_id": "missing_model_probe_not_authority",
            "args": [],
            "expect": {
                "status": "candidate_model_missing",
                "model_request_status": "model_not_supplied",
                "authority_empty": True,
                "provenance_empty": True,
                "authority_row_status": "action_required",
                "provenance_row_status": "action_required",
                "missing_inputs": ["model_path", "authority", "provenance"],
                "next_actions": [
                    "select_reviewed_so101_model_path",
                    "record_reviewed_model_source_authority",
                    "record_model_provenance",
                ],
            },
        },
        {
            "case_id": "placeholder_authority_provenance_rejected",
            "args": ["--model-path", str(model_path), *placeholder_authority_args()],
            "expect": {
                "status": "candidate_manifest_needs_review",
                "model_request_status": "model_supplied",
                "authority_empty": True,
                "provenance_empty": True,
                "authority_row_status": "action_required",
                "provenance_row_status": "action_required",
                "authority_placeholder_fields": [
                    "review_id",
                    "reviewed_at",
                    "reviewed_by",
                ],
                "provenance_placeholder_fields": [
                    "export_tool",
                    "license",
                    "source_url",
                ],
                "missing_inputs": ["authority", "provenance"],
                "next_actions": [
                    "record_reviewed_model_source_authority",
                    "record_model_provenance",
                ],
            },
        },
        {
            "case_id": "invalid_reviewed_at_rejected",
            "args": ["--model-path", str(model_path), *invalid_reviewed_at_args()],
            "expect": {
                "status": "candidate_manifest_needs_review",
                "model_request_status": "model_supplied",
                "authority_empty": True,
                "provenance_empty": False,
                "authority_row_status": "action_required",
                "provenance_row_status": "ok",
                "authority_invalid_fields": ["reviewed_at"],
                "missing_inputs": ["authority"],
                "next_actions": ["record_reviewed_model_source_authority"],
            },
        },
        {
            "case_id": "valid_authority_provenance_still_draft_not_ready",
            "args": ["--model-path", str(model_path), *valid_authority_args()],
            "expect": {
                "status": "candidate_manifest_needs_review",
                "model_request_status": "model_supplied",
                "authority_empty": False,
                "provenance_empty": False,
                "authority_row_status": "ok",
                "provenance_row_status": "ok",
                "missing_inputs_absent": ["authority", "provenance"],
                "next_actions_absent": [
                    "record_reviewed_model_source_authority",
                    "record_model_provenance",
                ],
                "missing_inputs": [
                    "base_to_board_transform",
                    "joint_limits_deg",
                    "mesh_assets",
                    "model_sha256",
                    "target_frame_authority",
                    "tcp_offset_m",
                ],
            },
        },
    ]


def run_case(
    *,
    case_id: str,
    case_args: list[str],
    python_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, str]]]:
    case_dir = output_dir / case_id
    summary_path = case_dir / "so101_model_bundle_probe_summary.json"
    candidate_path = case_dir / "so101_model_bundle.candidate.json"
    checklist_path = case_dir / "so101_model_bundle_probe_checklist.csv"
    command = [
        executable_arg(python_path),
        str(PROBE_SCRIPT),
        "--output-dir",
        str(case_dir),
        "--python",
        executable_arg(python_path),
        *case_args,
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / f"{case_id}_stdout.txt"
    stderr_path = case_dir / f"{case_id}_stderr.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    record = {
        "case_id": case_id,
        "command": command,
        "return_code": result.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(summary_path),
        "candidate_manifest_path": str(candidate_path),
        "checklist_path": str(checklist_path),
    }
    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        summary = {
            "ok": False,
            "status": "summary_unavailable",
            "summary_error": f"{type(exc).__name__}: {exc}",
        }
    try:
        candidate = json.loads(candidate_path.read_text())
    except Exception as exc:
        candidate = {
            "schema": None,
            "candidate_error": f"{type(exc).__name__}: {exc}",
        }
    try:
        with checklist_path.open(newline="") as handle:
            rows = {row["requirement_id"]: row for row in csv.DictReader(handle)}
    except Exception:
        rows = {}
    return record, summary, candidate, rows


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def expect_contains(errors: list[str], label: str, values: Any, expected_values: list[str]) -> None:
    values = values if isinstance(values, list) else []
    for expected in expected_values:
        if expected not in values:
            errors.append(f"{label}: expected {expected!r} in {values!r}")


def expect_absent(errors: list[str], label: str, values: Any, absent_values: list[str]) -> None:
    values = values if isinstance(values, list) else []
    for absent in absent_values:
        if absent in values:
            errors.append(f"{label}: expected {absent!r} absent from {values!r}")


def summarize_case(
    record: dict[str, Any],
    summary: dict[str, Any],
    candidate: dict[str, Any],
    checklist_rows: dict[str, dict[str, str]],
    expect: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    authority = candidate.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    provenance = candidate.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    authority_placeholder = candidate.get("authority_placeholder")
    authority_placeholder = (
        authority_placeholder if isinstance(authority_placeholder, dict) else {}
    )
    provenance_placeholder = candidate.get("provenance_placeholder")
    provenance_placeholder = (
        provenance_placeholder if isinstance(provenance_placeholder, dict) else {}
    )
    authority_row = checklist_rows.get("authority") or {}
    provenance_row = checklist_rows.get("provenance") or {}
    missing_inputs = summary.get("missing_inputs")
    missing_inputs = missing_inputs if isinstance(missing_inputs, list) else []
    next_actions = summary.get("next_required_action_ids")
    next_actions = next_actions if isinstance(next_actions, list) else []
    observations = {
        "status": summary.get("status"),
        "model_request_status": summary.get("model_request_status"),
        "manifest_status": summary.get("manifest_status"),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "model_authority": summary.get("model_authority"),
        "authority_empty": not bool(authority),
        "provenance_empty": not bool(provenance),
        "authority_row_status": authority_row.get("status"),
        "provenance_row_status": provenance_row.get("status"),
        "authority_placeholder_fields": authority_placeholder.get("placeholder_fields") or [],
        "authority_invalid_fields": authority_placeholder.get("invalid_fields") or [],
        "provenance_placeholder_fields": provenance_placeholder.get("placeholder_fields") or [],
        "missing_inputs": missing_inputs,
        "next_required_action_ids": next_actions,
    }
    add_error(errors, "return_code", record.get("return_code"), 0)
    add_error(errors, "summary.ok", summary.get("ok"), True)
    add_error(errors, "summary.status", summary.get("status"), expect["status"])
    add_error(
        errors,
        "model_request_status",
        summary.get("model_request_status"),
        expect["model_request_status"],
    )
    add_error(errors, "ready_for_model_backed_ik", summary.get("ready_for_model_backed_ik"), False)
    add_error(errors, "model_authority", summary.get("model_authority"), "draft_candidate_not_reviewed")
    add_error(errors, "authority_empty", observations["authority_empty"], expect["authority_empty"])
    add_error(errors, "provenance_empty", observations["provenance_empty"], expect["provenance_empty"])
    add_error(errors, "authority_row_status", authority_row.get("status"), expect["authority_row_status"])
    add_error(errors, "provenance_row_status", provenance_row.get("status"), expect["provenance_row_status"])
    expect_contains(errors, "missing_inputs", missing_inputs, expect.get("missing_inputs", []))
    expect_contains(errors, "next_required_action_ids", next_actions, expect.get("next_actions", []))
    expect_absent(errors, "missing_inputs", missing_inputs, expect.get("missing_inputs_absent", []))
    expect_absent(
        errors,
        "next_required_action_ids",
        next_actions,
        expect.get("next_actions_absent", []),
    )
    expect_contains(
        errors,
        "authority_placeholder_fields",
        observations["authority_placeholder_fields"],
        expect.get("authority_placeholder_fields", []),
    )
    expect_contains(
        errors,
        "authority_invalid_fields",
        observations["authority_invalid_fields"],
        expect.get("authority_invalid_fields", []),
    )
    expect_contains(
        errors,
        "provenance_placeholder_fields",
        observations["provenance_placeholder_fields"],
        expect.get("provenance_placeholder_fields", []),
    )
    if authority:
        add_error(
            errors,
            "authority.source_authority_status",
            authority.get("source_authority_status"),
            "operator_reviewed",
        )
    if provenance:
        expect_contains(
            errors,
            "provenance.keys",
            sorted(provenance),
            ["export_tool", "license", "source_url"],
        )
    return {
        **record,
        "ok": not errors,
        "errors": errors,
        "observations": observations,
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Model Bundle Probe Matrix",
        "",
        "This hardware-free matrix exercises the SO-101 model-bundle probe draft boundary.",
        "Synthetic URDF fixtures are generated under this output directory and are not reviewed physical SO-101 authority.",
        "",
        "Key checks:",
        "",
        "- Missing model input still emits a draft and keeps model path, authority, and provenance actions open.",
        "- Placeholder authority/provenance inputs stay in placeholder diagnostics and do not populate manifest fields.",
        "- Malformed authority review timestamps keep authority open and do not populate manifest authority fields.",
        "- Valid authority/provenance metadata can populate the draft, but the draft remains non-ready until model digest, meshes, reviewed joint limits, target-frame authority, TCP offset, and base-to-board alignment are supplied.",
        "",
        "Summary:",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_case_ids`: `{summary['failed_case_ids']}`",
        f"- `model_authority`: `{summary['model_authority']}`",
        f"- `observed_evidence_is_physical_so101_authority`: `{str(summary['observed_evidence_is_physical_so101_authority']).lower()}`",
        f"- `ready_for_policy_training`: `{str(summary['ready_for_policy_training']).lower()}`",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = create_fixtures(output_dir)
    cases: list[dict[str, Any]] = []
    for spec in case_specs(fixtures):
        record, probe_summary, candidate, checklist_rows = run_case(
            case_id=spec["case_id"],
            case_args=spec["args"],
            python_path=args.python,
            output_dir=output_dir,
        )
        cases.append(
            summarize_case(
                record,
                probe_summary,
                candidate,
                checklist_rows,
                spec["expect"],
            )
        )
    failed_case_ids = [case["case_id"] for case in cases if not case["ok"]]
    summary_path = output_dir / "so101_model_bundle_probe_matrix_summary.json"
    csv_path = output_dir / "so101_model_bundle_probe_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": not failed_case_ids,
        "status": "ok" if not failed_case_ids else "failed",
        "model_authority": "model_bundle_probe_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": failed_case_ids,
        "cases": cases,
        "summary_json": str(summary_path),
        "cases_csv": str(csv_path),
        "readme_md": str(readme_path),
    }
    write_json(summary_path, summary)
    write_csv(
        csv_path,
        [
            {
                **case,
                **case["observations"],
                "expected_status": next(
                    spec["expect"]["status"]
                    for spec in case_specs(fixtures)
                    if spec["case_id"] == case["case_id"]
                ),
            }
            for case in cases
        ],
    )
    write_readme(readme_path, summary)
    print(
        json.dumps(
            {
                "ok": summary["ok"],
                "status": summary["status"],
                "case_ids": summary["case_ids"],
                "failed_cases": failed_case_ids,
                "summary_json": str(summary_path),
                "cases_csv": str(csv_path),
                "readme_md": str(readme_path),
            },
            sort_keys=True,
        )
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
