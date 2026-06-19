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
    Path("/private/tmp") / "lerobot_sim" / "so101_model_bundle_manifest_matrix"
)
SCHEMA = "lerobot.sim.so101_model_bundle_manifest_matrix.v1"
MANIFEST_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_manifest.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free contract matrix over the SO-101 model bundle "
            "manifest gate. Fixture manifests are generated under the output "
            "directory and are not reviewed physical SO-101 evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child manifest checks.",
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
        "ready_for_model_backed_ik",
        "model_authority",
        "physical_so101_model_authority_ready",
        "hardware_free_regression_fixture_ready",
        "physical_authority_gate_status",
        "model_path_status",
        "model_identity_status",
        "authority_status",
        "provenance_status",
        "asset_roots_status",
        "joint_limits_status",
        "mesh_assets_status",
        "target_frame_status",
        "tcp_offset_status",
        "alignment_status",
        "contract_checker_status",
        "authority_review_open_work_fields",
        "joint_limits_review_open_work_fields",
        "mesh_assets_review_open_work_fields",
        "target_frame_review_open_work_fields",
        "tcp_offset_review_open_work_fields",
        "alignment_review_open_work_fields",
        "missing_inputs",
        "next_required_action_ids",
        "review_packet_status",
        "review_requirements_status",
        "review_requirements_url_fields",
        "bundle_intake_status",
        "bundle_intake_action_ids",
        "bundle_intake_related_requirement_ids_by_action_id",
        "bundle_intake_field_check_diagnostics_by_action_id",
        "contract_preflight_intake_manifest_fields",
        "contract_preflight_intake_required_inputs",
        "synthetic_fixture_authority_fields",
        "expected_ready",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def expect_contains(errors: list[str], label: str, values: Any, expected: list[str]) -> None:
    values = values if isinstance(values, list) else []
    for item in expected:
        if item not in values:
            errors.append(f"{label}: expected {item!r} in {values!r}")


def nested_status(summary: dict[str, Any], key: str) -> Any:
    value = summary.get(key)
    return value.get("status") if isinstance(value, dict) else None


def review_open_work_fields(summary: dict[str, Any], key: str) -> list[str]:
    value = summary.get(key)
    value = value if isinstance(value, dict) else {}
    review = value.get("review")
    review = review if isinstance(review, dict) else value
    fields = review.get("review_evidence_open_work_fields")
    return fields if isinstance(fields, list) else []


def field_check_status(summary: dict[str, Any], requirement_id: str) -> str | None:
    for check in summary.get("field_checks") or []:
        if isinstance(check, dict) and check.get("requirement_id") == requirement_id:
            return "ok" if check.get("ok") is True else "action_required"
    return None


def review_requirement_by_id(
    review_requirements: dict[str, Any],
    requirement_id: str,
) -> dict[str, Any]:
    for requirement in review_requirements.get("requirements") or []:
        if (
            isinstance(requirement, dict)
            and requirement.get("requirement_id") == requirement_id
        ):
            return requirement
    return {}


def bundle_intake_action_by_id(
    bundle_intake: dict[str, Any],
    action_id: str,
) -> dict[str, Any]:
    for action in bundle_intake.get("actions") or []:
        if isinstance(action, dict) and action.get("action_id") == action_id:
            return action
    return {}


def assert_review_requirements_url_policy(
    errors: list[str],
    case_id: str,
    review_requirements: dict[str, Any],
) -> list[str]:
    expected_url_fields = ["cad_url", "license_url", "repository_url", "source_url"]
    url_policy = review_requirements.get("url_field_policy")
    url_policy = url_policy if isinstance(url_policy, dict) else {}
    add_error(
        errors,
        f"{case_id}.review_requirements.url_field_policy.http_url_fields",
        url_policy.get("http_url_fields"),
        expected_url_fields,
    )
    add_error(
        errors,
        f"{case_id}.review_requirements.url_field_policy.required_schemes",
        url_policy.get("required_schemes"),
        ["http", "https"],
    )
    expect_contains(
        errors,
        f"{case_id}.review_requirements.url_field_policy.non_url_source_handle_fields",
        url_policy.get("non_url_source_handle_fields"),
        ["source_path", "source_reference"],
    )

    provenance_requirement = review_requirement_by_id(review_requirements, "provenance")
    provenance_url_policy = provenance_requirement.get("url_field_policy")
    provenance_url_policy = (
        provenance_url_policy if isinstance(provenance_url_policy, dict) else {}
    )
    add_error(
        errors,
        f"{case_id}.review_requirements.provenance.url_field_policy.http_url_fields",
        provenance_url_policy.get("http_url_fields"),
        expected_url_fields,
    )
    add_error(
        errors,
        f"{case_id}.review_requirements.provenance.url_field_policy.required_schemes",
        provenance_url_policy.get("required_schemes"),
        ["http", "https"],
    )
    return expected_url_fields


def case_specs(fixtures: dict[str, Path]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": "missing_manifest_nonfailing",
            "manifest_path": None,
            "expect": {
                "status": "model_bundle_manifest_not_supplied",
                "ready": False,
                "model_authority": "reviewed_bundle_required",
                "physical_ready": False,
                "fixture_ready": False,
                "missing_inputs": ["--manifest-path"],
                "next_actions": ["supply_reviewed_so101_model_bundle_manifest"],
            },
        },
        {
            "case_id": "ready_synthetic_fixture_manifest_not_physical_authority",
            "manifest_path": fixtures["ready_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_ready_for_model_backed_ik",
                "ready": True,
                "model_authority": (
                    "hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_ready": False,
                "fixture_ready": True,
                "physical_authority_gate_status": (
                    "hardware_free_fixture_ready_not_physical_authority"
                ),
                "missing_inputs_exact": [],
                "synthetic_fields_contain": [
                    "authority",
                    "provenance",
                    "joint_limits",
                    "mesh_assets",
                    "target_frame",
                    "tcp_offset",
                    "base_to_board_alignment",
                ],
            },
        },
        {
            "case_id": "missing_model_file_not_ready",
            "manifest_path": fixtures["missing_model_file_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "model_authority": (
                    "incomplete_hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_ready": False,
                "fixture_ready": False,
                "model_path_status": "unavailable",
                "model_identity_status": "invalid",
                "mesh_assets_status": "missing",
                "missing_inputs": [
                    "model_path",
                    "model_sha256",
                    "mesh_assets",
                    "non_blocking_contract_checker_result",
                ],
                "next_actions": [
                    "select_reviewed_so101_model_path",
                    "record_reviewed_so101_model_file_sha256",
                    "resolve_so101_mesh_assets",
                    "clear_model_contract_and_asset_preflight",
                ],
            },
        },
        {
            "case_id": "placeholder_alignment_manifest_not_ready",
            "manifest_path": fixtures["placeholder_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "model_authority": (
                    "incomplete_hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_ready": False,
                "fixture_ready": False,
                "missing_inputs": ["base_to_board_transform"],
                "alignment_status": "placeholder_only",
            },
        },
        {
            "case_id": "placeholder_review_metadata_not_ready",
            "manifest_path": fixtures["placeholder_review_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "physical_ready": False,
                "fixture_ready": False,
                "authority_status": "needs_review",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "needs_review",
                "alignment_status": "needs_review",
                "missing_inputs": [
                    "authority",
                    "joint_limit_authority",
                    "mesh_asset_authority",
                    "target_frame_authority",
                    "tcp_offset_authority",
                    "base_to_board_alignment_authority",
                ],
            },
        },
        {
            "case_id": "thin_review_metadata_not_ready",
            "manifest_path": fixtures["thin_review_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "authority_status": "needs_review",
                "missing_inputs": ["authority", "joint_limit_authority"],
            },
        },
        {
            "case_id": "invalid_review_url_not_ready",
            "manifest_path": fixtures["invalid_review_url_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "authority_status": "needs_review",
                "missing_inputs": ["authority", "mesh_asset_authority"],
            },
        },
        {
            "case_id": "generic_review_scope_not_ready",
            "manifest_path": fixtures["generic_review_scope_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "authority_status": "needs_review",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "needs_review",
                "alignment_status": "needs_review",
                "missing_inputs": [
                    "authority",
                    "joint_limit_authority",
                    "mesh_asset_authority",
                    "target_frame_authority",
                    "tcp_offset_authority",
                    "base_to_board_alignment_authority",
                ],
            },
        },
        {
            "case_id": "pending_review_metadata_not_ready",
            "manifest_path": fixtures["pending_review_metadata_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "physical_ready": False,
                "fixture_ready": False,
                "authority_status": "needs_review",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "needs_review",
                "alignment_status": "needs_review",
                "missing_inputs": [
                    "authority",
                    "joint_limit_authority",
                    "mesh_asset_authority",
                    "target_frame_authority",
                    "tcp_offset_authority",
                    "base_to_board_alignment_authority",
                ],
                "authority_open_work_fields": [
                    "missing_inputs",
                    "next_required_action_ids",
                ],
                "review_open_work_fields": ["next_required_action_ids"],
            },
        },
        {
            "case_id": "weak_review_manifest_not_ready",
            "manifest_path": fixtures["weak_review_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "authority_status": "needs_review",
                "provenance_status": "needs_review",
                "missing_inputs": ["authority", "provenance"],
            },
        },
        {
            "case_id": "placeholder_provenance_not_ready",
            "manifest_path": fixtures["placeholder_provenance_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "provenance_status": "needs_review",
                "missing_inputs": ["provenance"],
            },
        },
        {
            "case_id": "invalid_provenance_url_not_ready",
            "manifest_path": fixtures["invalid_provenance_url_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "provenance_status": "needs_review",
                "missing_inputs": ["provenance"],
            },
        },
        {
            "case_id": "reviewed_status_with_fixture_provenance_not_physical_authority",
            "manifest_path": fixtures["fixture_provenance_reviewed_authority_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_ready_for_model_backed_ik",
                "ready": True,
                "model_authority": (
                    "hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_ready": False,
                "fixture_ready": True,
                "missing_inputs_exact": [],
                "synthetic_fields_contain": ["provenance"],
            },
        },
        {
            "case_id": "weak_joint_limit_authority_not_ready",
            "manifest_path": fixtures["weak_joint_limits_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "joint_limits_status": "needs_review",
                "missing_inputs": ["joint_limit_authority"],
            },
        },
        {
            "case_id": "weak_mesh_asset_authority_not_ready",
            "manifest_path": fixtures["weak_mesh_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "mesh_assets_status": "needs_review",
                "missing_inputs": ["mesh_asset_authority"],
            },
        },
        {
            "case_id": "weak_target_frame_authority_not_ready",
            "manifest_path": fixtures["weak_target_frame_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "target_frame_status": "needs_review",
                "missing_inputs": ["target_frame_authority"],
            },
        },
        {
            "case_id": "wrong_target_frame_not_ready",
            "manifest_path": fixtures["wrong_target_frame_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "target_frame_status": "invalid",
                "missing_inputs": ["target_frame"],
            },
        },
        {
            "case_id": "weak_tcp_offset_authority_not_ready",
            "manifest_path": fixtures["weak_tcp_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "tcp_offset_status": "needs_review",
                "missing_inputs": ["tcp_offset_authority"],
            },
        },
        {
            "case_id": "invalid_tcp_offset_shape_not_ready",
            "manifest_path": fixtures["invalid_tcp_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "tcp_offset_status": "invalid",
                "missing_inputs": ["tcp_offset_m"],
            },
        },
        {
            "case_id": "weak_alignment_authority_not_ready",
            "manifest_path": fixtures["weak_alignment_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "alignment_status": "needs_review",
                "missing_inputs": ["base_to_board_alignment_authority"],
            },
        },
        {
            "case_id": "invalid_alignment_transform_not_ready",
            "manifest_path": fixtures["invalid_alignment_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "alignment_status": "invalid",
                "missing_inputs": ["base_to_board_transform"],
            },
        },
        {
            "case_id": "mismatched_model_sha_not_ready",
            "manifest_path": fixtures["mismatched_model_sha_manifest_path"],
            "expect": {
                "status": "model_bundle_manifest_needs_follow_up",
                "ready": False,
                "model_identity_status": "invalid",
                "missing_inputs": ["model_sha256"],
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
    summary_path = case_dir / "so101_model_bundle_manifest_summary.json"
    python_executable = executable_arg(python_path)
    command = [
        python_executable,
        str(MANIFEST_SCRIPT),
        "--output-dir",
        str(case_dir),
        "--python",
        python_executable,
    ]
    manifest_path = spec.get("manifest_path")
    if isinstance(manifest_path, Path):
        command.extend(["--manifest-path", str(manifest_path)])

    case_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_path = case_dir / f"{case_id}_stdout.txt"
    stderr_path = case_dir / f"{case_id}_stderr.txt"
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


def summarize_case(
    *,
    spec: dict[str, Any],
    record: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(spec["case_id"])
    expect = spec["expect"]
    errors: list[str] = []
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    bundle_intake = summary.get("bundle_intake_checklist")
    bundle_intake = bundle_intake if isinstance(bundle_intake, dict) else {}
    contract_preflight_intake = bundle_intake_action_by_id(
        bundle_intake,
        "clear_model_contract_and_asset_preflight",
    )
    review_requirements = summary.get("review_requirements")
    review_requirements = review_requirements if isinstance(review_requirements, dict) else {}
    review_requirements_url_fields = assert_review_requirements_url_policy(
        errors,
        case_id,
        review_requirements,
    )

    add_error(errors, f"{case_id}.return_code", record.get("return_code"), 0)
    add_error(errors, f"{case_id}.ok", summary.get("ok"), True)
    add_error(errors, f"{case_id}.status", summary.get("status"), expect["status"])
    add_error(
        errors,
        f"{case_id}.ready_for_model_backed_ik",
        summary.get("ready_for_model_backed_ik"),
        expect["ready"],
    )
    if "model_authority" in expect:
        add_error(
            errors,
            f"{case_id}.model_authority",
            summary.get("model_authority"),
            expect["model_authority"],
        )
    add_error(
        errors,
        f"{case_id}.physical_so101_model_authority_ready",
        summary.get("physical_so101_model_authority_ready"),
        expect.get("physical_ready", False),
    )
    add_error(
        errors,
        f"{case_id}.hardware_free_regression_fixture_ready",
        summary.get("hardware_free_regression_fixture_ready"),
        expect.get("fixture_ready", False),
    )
    if "physical_authority_gate_status" in expect:
        add_error(
            errors,
            f"{case_id}.physical_authority_gate_status",
            summary.get("physical_authority_gate_status"),
            expect["physical_authority_gate_status"],
        )

    for key, summary_key in (
        ("model_path_status", ("model_path",)),
        ("model_identity_status", ("model_identity",)),
        ("authority_status", ("authority",)),
        ("provenance_status", ("provenance",)),
        ("asset_roots_status", ("asset_roots",)),
        ("joint_limits_status", ("joint_limits",)),
        ("mesh_assets_status", ("mesh_assets",)),
        ("target_frame_status", ("target_frame",)),
        ("tcp_offset_status", ("tcp_offset",)),
        ("alignment_status", ("base_to_board_alignment",)),
    ):
        if key in expect:
            nested = summary.get(summary_key[0])
            actual = nested.get("status") if isinstance(nested, dict) else None
            add_error(errors, f"{case_id}.{key}", actual, expect[key])

    missing_inputs = summary.get("missing_inputs")
    if "missing_inputs_exact" in expect:
        add_error(
            errors,
            f"{case_id}.missing_inputs",
            missing_inputs,
            expect["missing_inputs_exact"],
        )
    else:
        expect_contains(
            errors,
            f"{case_id}.missing_inputs",
            missing_inputs,
            expect.get("missing_inputs", []),
        )
    next_required_action_ids = summary.get("next_required_action_ids")
    expect_contains(
        errors,
        f"{case_id}.next_required_action_ids",
        next_required_action_ids,
        expect.get("next_actions", []),
    )
    if isinstance(next_required_action_ids, list) and next_required_action_ids:
        for action_id in next_required_action_ids:
            action = bundle_intake_action_by_id(bundle_intake, str(action_id))
            if not isinstance(action.get("related_requirement_ids"), list) or not action.get(
                "related_requirement_ids"
            ):
                errors.append(
                    f"{case_id}.bundle_intake.{action_id}.related_requirement_ids: expected non-empty list"
                )
            if not isinstance(action.get("field_check_context"), list) or not action.get(
                "field_check_context"
            ):
                errors.append(
                    f"{case_id}.bundle_intake.{action_id}.field_check_context: expected non-empty list"
                )
    if (
        "clear_model_contract_and_asset_preflight"
        in (next_required_action_ids if isinstance(next_required_action_ids, list) else [])
    ):
        add_error(
            errors,
            f"{case_id}.contract_preflight_intake.manifest_fields",
            contract_preflight_intake.get("manifest_fields"),
            ["model_path", "asset_roots", "target_frame"],
        )
        expect_contains(
            errors,
            f"{case_id}.contract_preflight_intake.required_inputs",
            contract_preflight_intake.get("required_inputs"),
            [
                "contract checker non-blocking",
                "SO-101 joints visible",
                "target frame visible",
                "mesh asset preflight non-blocking",
            ],
        )
    expect_contains(
        errors,
        f"{case_id}.synthetic_fixture_authority_fields",
        summary.get("synthetic_fixture_authority_fields"),
        expect.get("synthetic_fields_contain", []),
    )
    if "authority_open_work_fields" in expect:
        expect_contains(
            errors,
            f"{case_id}.authority_review_open_work_fields",
            review_open_work_fields(summary, "authority"),
            expect["authority_open_work_fields"],
        )
    if "review_open_work_fields" in expect:
        for label, summary_key in (
            ("joint_limits", "joint_limits"),
            ("mesh_assets", "mesh_assets"),
            ("target_frame", "target_frame"),
            ("tcp_offset", "tcp_offset"),
            ("alignment", "base_to_board_alignment"),
        ):
            expect_contains(
                errors,
                f"{case_id}.{label}_review_open_work_fields",
                review_open_work_fields(summary, summary_key),
                expect["review_open_work_fields"],
            )

    review_packet = summary.get("review_packet")
    review_packet = review_packet if isinstance(review_packet, dict) else {}
    if summary.get("ready_for_model_backed_ik") is True:
        add_error(
            errors,
            f"{case_id}.next_required_action_ids_when_ready",
            next_required_action_ids,
            [],
        )
    add_error(
        errors,
        f"{case_id}.review_packet_observed_evidence_is_authority",
        review_packet.get("observed_evidence_is_authority"),
        False,
    )
    add_error(
        errors,
        f"{case_id}.review_packet_development_fixture_boundary",
        review_packet.get("development_fixture_evidence_not_physical_so101_truth"),
        True,
    )

    for artifact_key in (
        "summary_json",
        "checklist_csv",
        "readme_md",
        "review_packet_json",
        "review_packet_csv",
        "review_requirements_json",
        "review_requirements_csv",
        "bundle_intake_checklist_json",
        "bundle_intake_checklist_csv",
        "reviewed_manifest_template_json",
    ):
        artifact_path = artifacts.get(artifact_key)
        if not isinstance(artifact_path, str) or not Path(artifact_path).is_file():
            errors.append(f"{case_id}.artifacts.{artifact_key}: expected existing file")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "record": record,
        "summary_path": record["summary_path"],
        "observations": {
            "status": summary.get("status"),
            "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
            "model_authority": summary.get("model_authority"),
            "physical_so101_model_authority_ready": summary.get(
                "physical_so101_model_authority_ready"
            ),
            "hardware_free_regression_fixture_ready": summary.get(
                "hardware_free_regression_fixture_ready"
            ),
            "physical_authority_gate_status": summary.get(
                "physical_authority_gate_status"
            ),
            "model_path_status": nested_status(summary, "model_path"),
            "model_identity_status": nested_status(summary, "model_identity"),
            "authority_status": nested_status(summary, "authority"),
            "provenance_status": nested_status(summary, "provenance"),
            "asset_roots_status": nested_status(summary, "asset_roots"),
            "joint_limits_status": nested_status(summary, "joint_limits"),
            "mesh_assets_status": nested_status(summary, "mesh_assets"),
            "target_frame_status": nested_status(summary, "target_frame"),
            "tcp_offset_status": nested_status(summary, "tcp_offset"),
            "alignment_status": nested_status(summary, "base_to_board_alignment"),
            "contract_checker_status": (summary.get("contract_checker") or {}).get(
                "status"
            ),
            "authority_review_open_work_fields": review_open_work_fields(
                summary, "authority"
            ),
            "joint_limits_review_open_work_fields": review_open_work_fields(
                summary, "joint_limits"
            ),
            "mesh_assets_review_open_work_fields": review_open_work_fields(
                summary, "mesh_assets"
            ),
            "target_frame_review_open_work_fields": review_open_work_fields(
                summary, "target_frame"
            ),
            "tcp_offset_review_open_work_fields": review_open_work_fields(
                summary, "tcp_offset"
            ),
            "alignment_review_open_work_fields": review_open_work_fields(
                summary, "base_to_board_alignment"
            ),
            "missing_inputs": missing_inputs,
            "next_required_action_ids": next_required_action_ids,
            "review_packet_status": summary.get("review_packet_status"),
            "review_requirements_status": review_requirements.get("status"),
            "review_requirements_url_fields": review_requirements_url_fields,
            "bundle_intake_status": bundle_intake.get("status"),
            "bundle_intake_action_ids": bundle_intake.get("action_ids"),
            "bundle_intake_related_requirement_ids_by_action_id": {
                action.get("action_id"): action.get("related_requirement_ids")
                for action in bundle_intake.get("actions") or []
                if isinstance(action, dict) and isinstance(action.get("action_id"), str)
            },
            "bundle_intake_field_check_diagnostics_by_action_id": {
                action.get("action_id"): action.get("field_check_diagnostics")
                for action in bundle_intake.get("actions") or []
                if isinstance(action, dict) and isinstance(action.get("action_id"), str)
            },
            "contract_preflight_intake_manifest_fields": (
                contract_preflight_intake.get("manifest_fields")
            ),
            "contract_preflight_intake_required_inputs": (
                contract_preflight_intake.get("required_inputs")
            ),
            "synthetic_fixture_authority_fields": summary.get(
                "synthetic_fixture_authority_fields"
            ),
            "field_check_status_by_requirement_id": {
                requirement_id: field_check_status(summary, requirement_id)
                for requirement_id in (
                    "manifest_path",
                    "model_path",
                    "model_sha256",
                    "asset_roots",
                    "authority",
                    "provenance",
                    "joint_limits_deg",
                    "mesh_assets",
                    "target_frame",
                    "tcp_offset_m",
                    "base_to_board_transform",
                    "contract_checker_result",
                )
            },
        },
    }


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    obs = case["observations"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "return_code": case["record"].get("return_code"),
        "status": obs.get("status"),
        "ready_for_model_backed_ik": obs.get("ready_for_model_backed_ik"),
        "model_authority": obs.get("model_authority"),
        "physical_so101_model_authority_ready": obs.get(
            "physical_so101_model_authority_ready"
        ),
        "hardware_free_regression_fixture_ready": obs.get(
            "hardware_free_regression_fixture_ready"
        ),
        "physical_authority_gate_status": obs.get("physical_authority_gate_status"),
        "model_path_status": obs.get("model_path_status"),
        "model_identity_status": obs.get("model_identity_status"),
        "authority_status": obs.get("authority_status"),
        "provenance_status": obs.get("provenance_status"),
        "asset_roots_status": obs.get("asset_roots_status"),
        "joint_limits_status": obs.get("joint_limits_status"),
        "mesh_assets_status": obs.get("mesh_assets_status"),
        "target_frame_status": obs.get("target_frame_status"),
        "tcp_offset_status": obs.get("tcp_offset_status"),
        "alignment_status": obs.get("alignment_status"),
        "contract_checker_status": obs.get("contract_checker_status"),
        "authority_review_open_work_fields": obs.get(
            "authority_review_open_work_fields"
        ),
        "joint_limits_review_open_work_fields": obs.get(
            "joint_limits_review_open_work_fields"
        ),
        "mesh_assets_review_open_work_fields": obs.get(
            "mesh_assets_review_open_work_fields"
        ),
        "target_frame_review_open_work_fields": obs.get(
            "target_frame_review_open_work_fields"
        ),
        "tcp_offset_review_open_work_fields": obs.get(
            "tcp_offset_review_open_work_fields"
        ),
        "alignment_review_open_work_fields": obs.get(
            "alignment_review_open_work_fields"
        ),
        "missing_inputs": obs.get("missing_inputs"),
        "next_required_action_ids": obs.get("next_required_action_ids"),
        "review_packet_status": obs.get("review_packet_status"),
        "review_requirements_status": obs.get("review_requirements_status"),
        "review_requirements_url_fields": obs.get("review_requirements_url_fields"),
        "bundle_intake_status": obs.get("bundle_intake_status"),
        "bundle_intake_action_ids": obs.get("bundle_intake_action_ids"),
        "bundle_intake_related_requirement_ids_by_action_id": obs.get(
            "bundle_intake_related_requirement_ids_by_action_id"
        ),
        "bundle_intake_field_check_diagnostics_by_action_id": obs.get(
            "bundle_intake_field_check_diagnostics_by_action_id"
        ),
        "contract_preflight_intake_manifest_fields": obs.get(
            "contract_preflight_intake_manifest_fields"
        ),
        "contract_preflight_intake_required_inputs": obs.get(
            "contract_preflight_intake_required_inputs"
        ),
        "synthetic_fixture_authority_fields": obs.get(
            "synthetic_fixture_authority_fields"
        ),
        "expected_ready": case["expected"].get("ready"),
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Model Bundle Manifest Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "Synthetic fixture caveat: ready fixture manifests exercise manifest-gate plumbing only; they are not reviewed physical SO-101 authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Ready | Authority | Physical | Fixture | Missing Inputs | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{ready}` | `{authority}` | `{physical}` | `{fixture}` | `{missing}` | `{summary_path}` |".format(
                case_id=case["case_id"],
                status=obs.get("status"),
                ready=obs.get("ready_for_model_backed_ik"),
                authority=obs.get("model_authority"),
                physical=obs.get("physical_so101_model_authority_ready"),
                fixture=obs.get("hardware_free_regression_fixture_ready"),
                missing=", ".join(obs.get("missing_inputs") or []),
                summary_path=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- Placeholder review metadata, generic review scopes, invalid review URLs, weak field-specific authority, placeholder or malformed provenance, wrong target frame, invalid TCP/alignment, and model SHA mismatch all remain not ready.",
            "- The ready synthetic fixture cases may set `ready_for_model_backed_ik: true` but must keep `physical_so101_model_authority_ready: false`.",
            "- Review packets, intake checklists, and generated templates are operator intake only and never promote fixture evidence into physical SO-101 truth.",
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
        record, case_summary = run_case(
            spec=spec,
            python_path=args.python,
            output_dir=output_dir,
        )
        cases.append(summarize_case(spec=spec, record=record, summary=case_summary))

    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_model_bundle_manifest_matrix_summary.json"
    csv_path = output_dir / "so101_model_bundle_manifest_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "model_bundle_manifest_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_policy_training": False,
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
            "This matrix injects generated local fixture manifests and does not review a real SO-101 model bundle.",
            "Ready fixture cases exercise the manifest state machine only and remain non-physical SO-101 truth.",
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
