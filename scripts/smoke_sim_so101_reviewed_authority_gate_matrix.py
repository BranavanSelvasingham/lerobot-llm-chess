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
    so101_reviewed_model_authority_blocker_packet,
    so101_reviewed_model_authority_gate_section,
)

DEFAULT_OUTPUT_DIR = (
    Path("/private/tmp") / "lerobot_sim" / "so101_reviewed_authority_gate_matrix"
)
SCHEMA = "lerobot.sim.so101_reviewed_authority_gate_matrix.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free contract matrix over the SO-101 reviewed model "
            "authority gate. Inputs are injected state dictionaries, not reviewed "
            "physical SO-101 evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing output directory before running.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


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
        "source_authority_ready",
        "physical_bundle_ready",
        "source_bundle_consistency_status",
        "source_bundle_consistency_ready",
        "physical_reviewed_model_motion_checked",
        "development_fixture_evidence_not_physical_so101_truth",
        "blockers",
        "next_required_action_ids",
        "blocker_packet_action_required_item_ids",
        "blocker_packet_blocked_by_prior_requirements_item_ids",
        "expected_gate_ready",
        "expected_consistency_status",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def gate_action(action_id: str, gate: str, title: str, detail: str) -> dict[str, str]:
    return {
        "action_id": action_id,
        "gate": gate,
        "title": title,
        "detail": detail,
    }


def source_missing(summary_path: Path) -> dict[str, Any]:
    return {
        "source_authority_gate_status": (
            "source_authority_blocked_missing_authoritative_model"
        ),
        "source_authority_blockers": [
            "scan_or_supply_so101_model_source_root",
            "review_and_declare_authoritative_so101_model_source",
        ],
        "next_required_for_goal": [
            gate_action(
                "scan_or_supply_so101_model_source_root",
                "reviewed_model_authority",
                "Scan or supply SO-101 model source roots",
                "Provide candidate source roots before choosing reviewed authority.",
            ),
            gate_action(
                "review_and_declare_authoritative_so101_model_source",
                "reviewed_model_authority",
                "Review and declare source authority",
                "Declare exactly one reviewed authoritative SO-101 model source.",
            ),
        ],
        "next_required_action_ids": [
            "scan_or_supply_so101_model_source_root",
            "review_and_declare_authoritative_so101_model_source",
        ],
        "selected_authoritative_candidate_path": None,
        "source_configuration": {
            "authoritative_model_paths": [],
            "authoritative_model_roots": [],
        },
        "summary_path": str(summary_path),
    }


def source_ready(summary_path: Path, model_path: Path) -> dict[str, Any]:
    model = normalize_path(model_path)
    return {
        "source_authority_gate_status": "source_authority_ready",
        "source_authority_blockers": [],
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "selected_authoritative_candidate_path": model,
        "source_configuration": {
            "authoritative_model_paths": [model],
            "authoritative_model_roots": [normalize_path(model_path.parent)],
        },
        "summary_path": str(summary_path),
    }


def bundle_missing(summary_path: Path) -> dict[str, Any]:
    return {
        "physical_so101_model_authority_ready": False,
        "physical_authority_gate_status": "model_bundle_manifest_not_supplied",
        "physical_authority_blockers": ["supply_reviewed_so101_model_bundle_manifest"],
        "hardware_free_regression_fixture_ready": False,
        "next_required_for_goal": [
            gate_action(
                "supply_reviewed_so101_model_bundle_manifest",
                "reviewed_model_authority",
                "Supply reviewed SO-101 model bundle manifest",
                "Provide mesh roots, joint limits, target frame, TCP offset, and base alignment.",
            )
        ],
        "next_required_action_ids": ["supply_reviewed_so101_model_bundle_manifest"],
        "model_path": {"path": None},
        "summary_path": str(summary_path),
    }


def bundle_physical_ready(summary_path: Path, model_path: Path | None) -> dict[str, Any]:
    return {
        "physical_so101_model_authority_ready": True,
        "physical_authority_gate_status": "physical_reviewed_authority_ready",
        "physical_authority_blockers": [],
        "hardware_free_regression_fixture_ready": False,
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "model_path": {"path": normalize_path(model_path) if model_path else None},
        "summary_path": str(summary_path),
    }


def bundle_hardware_fixture(summary_path: Path, model_path: Path) -> dict[str, Any]:
    return {
        "physical_so101_model_authority_ready": False,
        "physical_authority_gate_status": "hardware_free_regression_fixture_not_physical",
        "physical_authority_blockers": [
            "synthetic_fixture_authority_not_physical_so101:authority",
            "supply_reviewed_so101_model_bundle_manifest",
        ],
        "hardware_free_regression_fixture_ready": True,
        "next_required_for_goal": [
            gate_action(
                "supply_reviewed_so101_model_bundle_manifest",
                "reviewed_model_authority",
                "Replace fixture bundle with reviewed SO-101 authority",
                "Synthetic fixture readiness cannot close physical SO-101 authority.",
            )
        ],
        "next_required_action_ids": ["supply_reviewed_so101_model_bundle_manifest"],
        "model_path": {"path": normalize_path(model_path)},
        "summary_path": str(summary_path),
    }


def motion_missing(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_mujoco_bundle_not_ready",
        "physical_reviewed_model_motion_checked": False,
        "hardware_free_fixture_motion_checked": False,
        "next_required_for_goal": [
            gate_action(
                "load_reviewed_model_in_mujoco",
                "mujoco_scene_validity",
                "Load reviewed SO-101 model in MuJoCo",
                "Load the reviewed model bundle without fallback behavior.",
            ),
            gate_action(
                "prove_physical_reviewed_model_motion",
                "mujoco_scene_validity",
                "Prove reviewed SO-101 joint motion",
                "Move every reviewed joint in MuJoCo and record motion evidence.",
            ),
        ],
        "summary_path": str(summary_path),
    }


def motion_hardware_fixture(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "hardware_free_fixture_motion_checked",
        "physical_reviewed_model_motion_checked": False,
        "hardware_free_fixture_motion_checked": True,
        "next_required_for_goal": [
            gate_action(
                "prove_physical_reviewed_model_motion",
                "mujoco_scene_validity",
                "Replace fixture motion with reviewed SO-101 motion evidence",
                "Fixture motion is automation coverage only.",
            )
        ],
        "summary_path": str(summary_path),
    }


def motion_physical_ready(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_mujoco_bundle_motion_checked",
        "physical_reviewed_model_motion_checked": True,
        "hardware_free_fixture_motion_checked": False,
        "next_required_for_goal": [],
        "summary_path": str(summary_path),
    }


def case_specs(output_dir: Path) -> list[dict[str, Any]]:
    fixture_dir = output_dir / "contract_state_paths"
    source_model = fixture_dir / "reviewed_source" / "so101_reviewed.urdf"
    source_sibling_model = fixture_dir / "reviewed_source" / "so101_unselected_sibling.xml"
    bundle_model = fixture_dir / "reviewed_bundle" / "so101_reviewed.urdf"
    source_model.parent.mkdir(parents=True, exist_ok=True)
    bundle_model.parent.mkdir(parents=True, exist_ok=True)
    source_model.write_text(
        "contract-state path placeholder only; not physical SO-101 evidence\n"
    )
    source_sibling_model.write_text(
        "same-root unselected placeholder only; not physical SO-101 evidence\n"
    )
    bundle_model.write_text(
        "contract-state path placeholder only; not physical SO-101 evidence\n"
    )

    summary_dir = output_dir / "input_summaries"
    return [
        {
            "case_id": "source_missing_bundle_missing_motion_missing",
            "source": source_missing(summary_dir / "source_missing.json"),
            "bundle": bundle_missing(summary_dir / "bundle_missing.json"),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "not_checked_prerequisites_not_ready",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "scan_or_supply_so101_model_source_root",
                    "supply_reviewed_so101_model_bundle_manifest",
                    "load_reviewed_model_in_mujoco",
                ],
                "actions_contain": [
                    "scan_or_supply_so101_model_source_root",
                    "supply_reviewed_so101_model_bundle_manifest",
                    "load_reviewed_model_in_mujoco",
                ],
                "blocked_prior_contains": [
                    "source_bundle_consistency",
                    "physical_reviewed_mujoco_motion_checked",
                ],
            },
        },
        {
            "case_id": "source_ready_bundle_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_missing(summary_dir / "bundle_missing.json"),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "not_checked_prerequisites_not_ready",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "supply_reviewed_so101_model_bundle_manifest",
                    "load_reviewed_model_in_mujoco",
                ],
                "actions_contain": [
                    "supply_reviewed_so101_model_bundle_manifest",
                    "load_reviewed_model_in_mujoco",
                ],
                "blocked_prior_contains": [
                    "source_bundle_consistency",
                    "physical_reviewed_mujoco_motion_checked",
                ],
            },
        },
        {
            "case_id": "source_missing_physical_bundle_ready",
            "source": source_missing(summary_dir / "source_missing.json"),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "not_checked_prerequisites_not_ready",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "scan_or_supply_so101_model_source_root",
                    "load_reviewed_model_in_mujoco",
                ],
                "actions_contain": [
                    "scan_or_supply_so101_model_source_root",
                    "load_reviewed_model_in_mujoco",
                ],
                "blocked_prior_contains": [
                    "source_bundle_consistency",
                    "physical_reviewed_mujoco_motion_checked",
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_missing_model_path",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready_no_path.json", None),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "bundle_model_path_missing",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "select_reviewed_so101_model_path",
                    "load_reviewed_model_in_mujoco",
                ],
                "actions_contain": [
                    "select_reviewed_so101_model_path",
                    "load_reviewed_model_in_mujoco",
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocked_prior_contains": ["physical_reviewed_mujoco_motion_checked"],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_path_mismatch",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", bundle_model),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_mismatch",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "align_source_inventory_with_bundle_manifest_model_path",
                    "load_reviewed_model_in_mujoco",
                ],
                "actions_contain": [
                    "align_source_inventory_with_bundle_manifest_model_path",
                    "load_reviewed_model_in_mujoco",
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocked_prior_contains": ["physical_reviewed_mujoco_motion_checked"],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_same_root_unselected_model",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(
                summary_dir / "bundle_same_root_unselected.json",
                source_sibling_model,
            ),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_mismatch",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": ["align_source_inventory_with_bundle_manifest_model_path"],
                "actions_contain": ["align_source_inventory_with_bundle_manifest_model_path"],
                "action_required_contains": ["source_bundle_consistency"],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_path_match_motion_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_consistent",
                "consistency_ready": True,
                "development_fixture": True,
                "blockers_contain": [
                    "load_reviewed_model_in_mujoco",
                    "prove_physical_reviewed_model_motion",
                ],
                "actions_contain": [
                    "load_reviewed_model_in_mujoco",
                    "prove_physical_reviewed_model_motion",
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
            },
        },
        {
            "case_id": "source_ready_hardware_free_bundle_fixture",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_hardware_fixture(summary_dir / "bundle_fixture.json", source_model),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "not_checked_prerequisites_not_ready",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "synthetic_fixture_authority_not_physical_so101:authority",
                    "load_reviewed_model_in_mujoco",
                ],
                "actions_contain": [
                    "supply_reviewed_so101_model_bundle_manifest",
                    "load_reviewed_model_in_mujoco",
                ],
                "blocked_prior_contains": [
                    "source_bundle_consistency",
                    "physical_reviewed_mujoco_motion_checked",
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_fixture_motion_not_physical",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_hardware_fixture(summary_dir / "motion_fixture.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_consistent",
                "consistency_ready": True,
                "development_fixture": True,
                "blockers_contain": ["load_reviewed_model_in_mujoco"],
                "actions_contain": [
                    "prove_physical_reviewed_model_motion",
                    "load_reviewed_model_in_mujoco",
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
            },
        },
        {
            "case_id": "all_ready_contract_state",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json"),
            "expect": {
                "ready": True,
                "consistency_status": "source_bundle_model_path_consistent",
                "consistency_ready": True,
                "development_fixture": False,
                "blockers_exact": [],
                "actions_exact": [],
                "action_required_exact": [],
                "blocked_prior_exact": [],
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
    gate = so101_reviewed_model_authority_gate_section(
        spec["source"],
        spec["bundle"],
        spec["motion"],
    )
    gate_summary_path = case_dir / "so101_reviewed_model_authority_gate_summary.json"
    blocker_packet = so101_reviewed_model_authority_blocker_packet(
        {**gate, "summary_path": str(gate_summary_path)}
    )
    expect = spec["expect"]
    errors: list[str] = []

    add_error(errors, "ready", gate.get("ready"), expect["ready"])
    add_error(
        errors,
        "status",
        gate.get("status"),
        "reviewed_model_authority_ready"
        if expect["ready"]
        else "reviewed_model_authority_blocked",
    )
    add_error(
        errors,
        "source_bundle_consistency_status",
        gate.get("source_bundle_consistency_status"),
        expect["consistency_status"],
    )
    add_error(
        errors,
        "source_bundle_consistency_ready",
        gate.get("source_bundle_consistency_ready"),
        expect["consistency_ready"],
    )
    add_error(
        errors,
        "development_fixture_evidence_not_physical_so101_truth",
        gate.get("development_fixture_evidence_not_physical_so101_truth"),
        expect["development_fixture"],
    )
    add_error(
        errors,
        "blocker_packet_model_authority",
        blocker_packet.get("model_authority"),
        "blocker_packet_not_authority",
    )
    add_error(errors, "blocker_packet_ready", blocker_packet.get("ready"), expect["ready"])

    source_bundle_consistency = gate.get("source_bundle_consistency")
    if not isinstance(source_bundle_consistency, dict):
        errors.append("source_bundle_consistency: expected dict")
    else:
        add_error(
            errors,
            "nested_consistency_status",
            source_bundle_consistency.get("status"),
            gate.get("source_bundle_consistency_status"),
        )
        add_error(
            errors,
            "nested_consistency_ready",
            source_bundle_consistency.get("ready"),
            gate.get("source_bundle_consistency_ready"),
        )
        if gate.get("source_bundle_consistency_ready") is True:
            add_error(
                errors,
                "matched_by",
                source_bundle_consistency.get("matched_by"),
                "selected_authoritative_candidate_path",
            )
            add_error(
                errors,
                "selected_path_matches_bundle",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_path_matches_bundle"
                ),
                True,
            )

    if "blockers_exact" in expect:
        add_error(errors, "blockers", gate.get("blockers"), expect["blockers_exact"])
    expect_contains(
        errors,
        "blockers",
        gate.get("blockers"),
        expect.get("blockers_contain", []),
    )
    if "actions_exact" in expect:
        add_error(
            errors,
            "next_required_action_ids",
            gate.get("next_required_action_ids"),
            expect["actions_exact"],
        )
    expect_contains(
        errors,
        "next_required_action_ids",
        gate.get("next_required_action_ids"),
        expect.get("actions_contain", []),
    )
    if "action_required_exact" in expect:
        add_error(
            errors,
            "action_required_item_ids",
            blocker_packet.get("action_required_item_ids"),
            expect["action_required_exact"],
        )
    expect_contains(
        errors,
        "action_required_item_ids",
        blocker_packet.get("action_required_item_ids"),
        expect.get("action_required_contains", []),
    )
    if "blocked_prior_exact" in expect:
        add_error(
            errors,
            "blocked_by_prior_requirements_item_ids",
            blocker_packet.get("blocked_by_prior_requirements_item_ids"),
            expect["blocked_prior_exact"],
        )
    expect_contains(
        errors,
        "blocked_by_prior_requirements_item_ids",
        blocker_packet.get("blocked_by_prior_requirements_item_ids"),
        expect.get("blocked_prior_contains", []),
    )

    case_dir.mkdir(parents=True, exist_ok=True)
    write_json(gate_summary_path, gate)
    blocker_path = case_dir / "so101_reviewed_model_authority_blocker_packet.json"
    write_json(blocker_path, blocker_packet)

    return {
        "case_id": spec["case_id"],
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "summary_path": str(gate_summary_path),
        "blocker_packet_path": str(blocker_path),
        "gate": gate,
        "blocker_packet": blocker_packet,
    }


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    gate = case["gate"]
    blocker_packet = case["blocker_packet"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "gate_status": gate.get("status"),
        "gate_ready": gate.get("ready"),
        "source_authority_ready": gate.get("source_authority_ready"),
        "physical_bundle_ready": gate.get("physical_so101_model_authority_ready"),
        "source_bundle_consistency_status": gate.get("source_bundle_consistency_status"),
        "source_bundle_consistency_ready": gate.get("source_bundle_consistency_ready"),
        "physical_reviewed_model_motion_checked": gate.get(
            "physical_reviewed_model_motion_checked"
        ),
        "development_fixture_evidence_not_physical_so101_truth": gate.get(
            "development_fixture_evidence_not_physical_so101_truth"
        ),
        "blockers": gate.get("blockers"),
        "next_required_action_ids": gate.get("next_required_action_ids"),
        "blocker_packet_action_required_item_ids": blocker_packet.get(
            "action_required_item_ids"
        ),
        "blocker_packet_blocked_by_prior_requirements_item_ids": blocker_packet.get(
            "blocked_by_prior_requirements_item_ids"
        ),
        "expected_gate_ready": case["expected"].get("ready"),
        "expected_consistency_status": case["expected"].get("consistency_status"),
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Reviewed Authority Gate Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "Caveat: this is a contract-state smoke. It injects source, bundle, and motion dictionaries to exercise gate transitions; it is not reviewed physical SO-101 model authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Ready | Consistency | Motion | Fixture Caveat | Actions |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        gate = case["gate"]
        lines.append(
            "| `{case_id}` | `{status}` | `{ready}` | `{consistency}` | `{motion}` | `{fixture}` | `{actions}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                ready=gate.get("ready"),
                consistency=gate.get("source_bundle_consistency_status"),
                motion=gate.get("physical_reviewed_model_motion_checked"),
                fixture=gate.get(
                    "development_fixture_evidence_not_physical_so101_truth"
                ),
                actions=", ".join(gate.get("next_required_action_ids") or []),
            )
        )
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- `all_ready_contract_state` exercises the ready branch only; its placeholder paths are not reviewed physical SO-101 artifacts.",
            "- The matrix artifact reports `model_authority: contract_matrix_not_authority` and `observed_evidence_is_authority: false`.",
            "- Use this smoke to protect gate logic. Use a reviewed model bundle plus MuJoCo motion evidence to close real SO-101 authority.",
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
    summary_path = output_dir / "so101_reviewed_authority_gate_matrix_summary.json"
    csv_path = output_dir / "so101_reviewed_authority_gate_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "contract_matrix_not_authority",
        "observed_evidence_is_authority": False,
        "physical_so101_model_authority_ready": False,
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
            "This matrix injects state dictionaries and does not parse, load, or review a real SO-101 model bundle.",
            "Placeholder paths under the output directory are contract-state fixtures only.",
            "The all-ready case exercises the gate's ready branch and must not be cited as physical SO-101 evidence.",
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
