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
SOURCE_MODEL_SHA256 = "a" * 64
BUNDLE_MODEL_SHA256 = "b" * 64
UNSET = object()


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
        "reviewed_model_authority_ready",
        "source_authority_ready",
        "physical_bundle_ready",
        "source_bundle_consistency_status",
        "source_bundle_consistency_ready",
        "selected_authoritative_candidate_declared_by_authoritative_path",
        "selected_authoritative_candidate_within_authoritative_root",
        "selected_authoritative_candidate_covered_by_source_configuration",
        "bundle_model_observed_sha256_missing",
        "bundle_model_observed_sha256_matches_declared",
        "reviewed_mujoco_motion_bundle_consistency_status",
        "reviewed_mujoco_motion_bundle_consistency_ready",
        "reviewed_mujoco_motion_model_path_matches_bundle",
        "reviewed_mujoco_motion_model_sha256_matches_bundle",
        "reviewed_mujoco_motion_model_observed_sha256_missing",
        "reviewed_mujoco_motion_model_observed_sha256_matches_declared",
        "physical_reviewed_model_motion_checked",
        "physical_reviewed_model_motion_reported",
        "physical_reviewed_model_motion_status_ready",
        "physical_reviewed_model_motion_child_ready",
        "reviewed_mujoco_bundle_status",
        "reviewed_mujoco_motion_authority_status",
        "development_fixture_evidence_not_physical_so101_truth",
        "development_fixture_evidence_present",
        "blockers",
        "next_required_action_ids",
        "blocker_packet_action_required_item_ids",
        "blocker_packet_blocked_by_prior_requirements_item_ids",
        "blocker_packet_next_action_ids",
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


def source_ready(
    summary_path: Path,
    model_path: Path,
    *,
    sha256: str | None = SOURCE_MODEL_SHA256,
) -> dict[str, Any]:
    model = normalize_path(model_path)
    return {
        "source_authority_gate_status": "source_authority_ready",
        "source_authority_blockers": [],
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "selected_authoritative_candidate_path": model,
        "selected_authoritative_candidate_sha256": sha256,
        "source_configuration": {
            "authoritative_model_paths": [model],
            "authoritative_model_roots": [normalize_path(model_path.parent)],
        },
        "summary_path": str(summary_path),
    }


def source_ready_missing_selected_path(summary_path: Path, model_path: Path) -> dict[str, Any]:
    model = normalize_path(model_path)
    return {
        "source_authority_gate_status": "source_authority_ready",
        "source_authority_blockers": [],
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "selected_authoritative_candidate_path": None,
        "selected_authoritative_candidate_sha256": SOURCE_MODEL_SHA256,
        "source_configuration": {
            "authoritative_model_paths": [model],
            "authoritative_model_roots": [normalize_path(model_path.parent)],
        },
        "summary_path": str(summary_path),
    }


def source_ready_unconfigured_selection(summary_path: Path, model_path: Path) -> dict[str, Any]:
    model = normalize_path(model_path)
    return {
        "source_authority_gate_status": "source_authority_ready",
        "source_authority_blockers": [],
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "selected_authoritative_candidate_path": model,
        "selected_authoritative_candidate_sha256": SOURCE_MODEL_SHA256,
        "source_configuration": {
            "authoritative_model_paths": [],
            "authoritative_model_roots": [],
        },
        "summary_path": str(summary_path),
    }


def source_ready_mismatched_selection(
    summary_path: Path,
    selected_model_path: Path,
    declared_model_path: Path,
) -> dict[str, Any]:
    selected_model = normalize_path(selected_model_path)
    declared_model = normalize_path(declared_model_path)
    return {
        "source_authority_gate_status": "source_authority_ready",
        "source_authority_blockers": [],
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "selected_authoritative_candidate_path": selected_model,
        "selected_authoritative_candidate_sha256": SOURCE_MODEL_SHA256,
        "source_configuration": {
            "authoritative_model_paths": [declared_model],
            "authoritative_model_roots": [],
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


def bundle_physical_ready(
    summary_path: Path,
    model_path: Path | None,
    *,
    sha256: str | None = SOURCE_MODEL_SHA256,
    declared_sha256: Any = UNSET,
    observed_sha256: Any = UNSET,
    fixture_ready: bool = False,
) -> dict[str, Any]:
    declared = sha256 if declared_sha256 is UNSET else declared_sha256
    observed = sha256 if observed_sha256 is UNSET else observed_sha256
    diagnostics: list[str] = []
    if not declared:
        diagnostics.append("model_sha256_missing")
    elif observed and observed != declared:
        diagnostics.append("model_sha256_mismatch")
    matches = bool(declared and observed and declared == observed)
    return {
        "physical_so101_model_authority_ready": True,
        "physical_authority_gate_status": "physical_reviewed_authority_ready",
        "physical_authority_blockers": [],
        "hardware_free_regression_fixture_ready": fixture_ready,
        "next_required_for_goal": [],
        "next_required_action_ids": [],
        "model_path": {"path": normalize_path(model_path) if model_path else None},
        "model_identity": {
            "status": "present" if declared and observed else "missing",
            "declared_sha256": declared,
            "observed_sha256": observed,
            "matches": matches,
            "diagnostics": diagnostics,
        },
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
        "model_identity": {
            "status": "present",
            "declared_sha256": SOURCE_MODEL_SHA256,
            "observed_sha256": SOURCE_MODEL_SHA256,
            "matches": True,
            "diagnostics": [],
        },
        "summary_path": str(summary_path),
    }


def motion_missing(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_mujoco_bundle_not_ready",
        "motion_authority_status": "not_checked_manifest_not_ready",
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
        "motion_authority_status": (
            "hardware_free_fixture_motion_checked_not_physical_so101_authority"
        ),
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


def motion_physical_ready(
    summary_path: Path,
    *,
    model_path: Path | None = None,
    sha256: str | None = SOURCE_MODEL_SHA256,
    declared_sha256: Any = UNSET,
    observed_sha256: Any = UNSET,
    fixture_motion_checked: bool = False,
) -> dict[str, Any]:
    declared = sha256 if declared_sha256 is UNSET else declared_sha256
    observed = sha256 if observed_sha256 is UNSET else observed_sha256
    return {
        "status": "reviewed_mujoco_bundle_motion_checked",
        "motion_authority_status": "physical_reviewed_model_motion_checked",
        "physical_reviewed_model_motion_checked": True,
        "hardware_free_fixture_motion_checked": fixture_motion_checked,
        "model_path": {"path": normalize_path(model_path) if model_path else None},
        "model_identity": {
            "declared_sha256": declared,
            "observed_sha256": observed,
            "matches": bool(declared and observed and declared == observed),
        },
        "next_required_for_goal": [],
        "summary_path": str(summary_path),
    }


def motion_inconsistent_status(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_mujoco_bundle_not_ready",
        "motion_authority_status": "not_checked_manifest_not_ready",
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
            "case_id": "source_ready_missing_selected_path_physical_bundle_ready",
            "source": source_ready_missing_selected_path(
                summary_dir / "source_ready_missing_selected_path.json",
                source_model,
            ),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_authoritative_model_path_missing",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "select_reviewed_authoritative_so101_source_model_path"
                ],
                "actions_contain": [
                    "select_reviewed_authoritative_so101_source_model_path"
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "select_reviewed_authoritative_so101_source_model_path"
                ],
                "selected_path_matches_bundle": False,
                "selected_digest_matches_bundle": True,
            },
        },
        {
            "case_id": "source_ready_unconfigured_selection_physical_bundle_ready",
            "source": source_ready_unconfigured_selection(
                summary_dir / "source_ready_unconfigured_selection.json",
                source_model,
            ),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_authoritative_model_selection_unconfigured",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "declare_reviewed_authoritative_so101_source_path_or_root"
                ],
                "actions_contain": [
                    "declare_reviewed_authoritative_so101_source_path_or_root"
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "declare_reviewed_authoritative_so101_source_path_or_root"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": True,
                "selected_declared_by_path": False,
                "selected_within_root": False,
                "selected_covered_by_source_configuration": False,
            },
        },
        {
            "case_id": "source_ready_selection_outside_authority_physical_bundle_ready",
            "source": source_ready_mismatched_selection(
                summary_dir / "source_ready_selection_outside_authority.json",
                source_model,
                source_sibling_model,
            ),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_authoritative_model_selection_mismatch",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "align_selected_so101_source_model_with_authoritative_declaration"
                ],
                "actions_contain": [
                    "align_selected_so101_source_model_with_authoritative_declaration"
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "align_selected_so101_source_model_with_authoritative_declaration"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": True,
                "selected_declared_by_path": False,
                "selected_within_root": False,
                "selected_covered_by_source_configuration": False,
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
                "blocker_packet_next_actions_contain": [
                    "select_reviewed_so101_model_path"
                ],
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
                "blocker_packet_next_actions_contain": [
                    "align_source_inventory_with_bundle_manifest_model_path"
                ],
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
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_mismatch",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": ["align_source_inventory_with_bundle_manifest_model_path"],
                "actions_contain": ["align_source_inventory_with_bundle_manifest_model_path"],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "align_source_inventory_with_bundle_manifest_model_path"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_path_match_motion_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_missing(summary_dir / "motion_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
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
            "case_id": "source_ready_physical_bundle_digest_missing",
            "source": source_ready(
                summary_dir / "source_ready_missing_digest.json",
                source_model,
                sha256=None,
            ),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_digest_missing",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": ["record_reviewed_so101_model_file_sha256"],
                "actions_contain": ["record_reviewed_so101_model_file_sha256"],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "record_reviewed_so101_model_file_sha256"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": False,
            },
        },
        {
            "case_id": "source_ready_physical_bundle_malformed_source_digest",
            "source": source_ready(
                summary_dir / "source_ready_malformed_digest.json",
                source_model,
                sha256="not-a-sha256-digest",
            ),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_digest_missing",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": ["record_reviewed_so101_model_file_sha256"],
                "actions_contain": ["record_reviewed_so101_model_file_sha256"],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "record_reviewed_so101_model_file_sha256"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": False,
            },
        },
        {
            "case_id": "source_ready_physical_bundle_declared_digest_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(
                summary_dir / "bundle_declared_digest_missing.json",
                source_model,
                declared_sha256=None,
                observed_sha256=SOURCE_MODEL_SHA256,
            ),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_digest_missing",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": ["record_reviewed_so101_model_file_sha256"],
                "actions_contain": ["record_reviewed_so101_model_file_sha256"],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "record_reviewed_so101_model_file_sha256"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": False,
                "bundle_declared_sha256": None,
                "bundle_observed_sha256": SOURCE_MODEL_SHA256,
                "bundle_model_sha256": None,
            },
        },
        {
            "case_id": "source_ready_physical_bundle_observed_digest_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(
                summary_dir / "bundle_observed_digest_missing.json",
                source_model,
                declared_sha256=SOURCE_MODEL_SHA256,
                observed_sha256=None,
            ),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "bundle_model_observed_digest_missing",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "verify_reviewed_so101_bundle_model_file_sha256"
                ],
                "actions_contain": [
                    "verify_reviewed_so101_bundle_model_file_sha256"
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "verify_reviewed_so101_bundle_model_file_sha256"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": True,
                "bundle_declared_sha256": SOURCE_MODEL_SHA256,
                "bundle_observed_sha256": None,
                "bundle_model_sha256": SOURCE_MODEL_SHA256,
                "bundle_observed_sha256_missing": True,
                "bundle_observed_sha256_matches_declared": False,
            },
        },
        {
            "case_id": "source_ready_physical_bundle_observed_digest_mismatch",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(
                summary_dir / "bundle_observed_digest_mismatch.json",
                source_model,
                declared_sha256=SOURCE_MODEL_SHA256,
                observed_sha256=BUNDLE_MODEL_SHA256,
            ),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "bundle_model_observed_digest_mismatch",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": [
                    "inspect_reviewed_so101_bundle_model_file_sha256"
                ],
                "actions_contain": [
                    "inspect_reviewed_so101_bundle_model_file_sha256"
                ],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "inspect_reviewed_so101_bundle_model_file_sha256"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": True,
                "bundle_declared_sha256": SOURCE_MODEL_SHA256,
                "bundle_observed_sha256": BUNDLE_MODEL_SHA256,
                "bundle_model_sha256": SOURCE_MODEL_SHA256,
                "bundle_observed_sha256_missing": False,
                "bundle_observed_sha256_matches_declared": False,
            },
        },
        {
            "case_id": "source_ready_physical_bundle_digest_mismatch",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(
                summary_dir / "bundle_digest_mismatch.json",
                source_model,
                sha256=BUNDLE_MODEL_SHA256,
            ),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_digest_mismatch",
                "consistency_ready": False,
                "development_fixture": True,
                "blockers_contain": ["align_source_inventory_with_bundle_manifest_model_digest"],
                "actions_contain": ["align_source_inventory_with_bundle_manifest_model_digest"],
                "action_required_contains": ["source_bundle_consistency"],
                "blocker_packet_next_actions_contain": [
                    "align_source_inventory_with_bundle_manifest_model_digest"
                ],
                "selected_path_matches_bundle": True,
                "selected_digest_matches_bundle": False,
            },
        },
        {
            "case_id": "source_ready_physical_bundle_motion_status_inconsistent",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_inconsistent_status(summary_dir / "motion_inconsistent.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "development_fixture": True,
                "motion_reported": True,
                "motion_status_ready": False,
                "reviewed_mujoco_bundle_status": "reviewed_mujoco_bundle_not_ready",
                "reviewed_mujoco_motion_authority_status": "not_checked_manifest_not_ready",
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
            "case_id": "source_ready_physical_bundle_motion_model_path_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_model_path_missing.json"),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "motion_bundle_consistency_status": (
                    "reviewed_mujoco_motion_model_path_missing"
                ),
                "motion_bundle_consistency_ready": False,
                "development_fixture": True,
                "motion_child_ready": True,
                "motion_path_matches_bundle": False,
                "motion_digest_matches_bundle": True,
                "blockers_contain": [
                    "rerun_reviewed_mujoco_motion_with_bundle_model_path"
                ],
                "actions_contain": [
                    "rerun_reviewed_mujoco_motion_with_bundle_model_path"
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
                "blocker_packet_next_actions_contain": [
                    "rerun_reviewed_mujoco_motion_with_bundle_model_path"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_motion_model_digest_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(
                summary_dir / "motion_model_digest_missing.json",
                model_path=source_model,
                sha256=None,
            ),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "motion_bundle_consistency_status": (
                    "reviewed_mujoco_motion_model_digest_missing"
                ),
                "motion_bundle_consistency_ready": False,
                "development_fixture": True,
                "motion_child_ready": True,
                "motion_path_matches_bundle": True,
                "motion_digest_matches_bundle": False,
                "blockers_contain": [
                    "record_reviewed_mujoco_motion_model_sha256"
                ],
                "actions_contain": [
                    "record_reviewed_mujoco_motion_model_sha256"
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
                "blocker_packet_next_actions_contain": [
                    "record_reviewed_mujoco_motion_model_sha256"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_motion_model_observed_digest_missing",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(
                summary_dir / "motion_model_observed_digest_missing.json",
                model_path=source_model,
                declared_sha256=SOURCE_MODEL_SHA256,
                observed_sha256=None,
            ),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "motion_bundle_consistency_status": (
                    "reviewed_mujoco_motion_model_observed_digest_missing"
                ),
                "motion_bundle_consistency_ready": False,
                "development_fixture": True,
                "motion_child_ready": True,
                "motion_path_matches_bundle": True,
                "motion_digest_matches_bundle": True,
                "motion_observed_sha256_missing": True,
                "motion_observed_sha256_matches_declared": False,
                "blockers_contain": [
                    "verify_reviewed_mujoco_motion_model_file_sha256"
                ],
                "actions_contain": [
                    "verify_reviewed_mujoco_motion_model_file_sha256"
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
                "blocker_packet_next_actions_contain": [
                    "verify_reviewed_mujoco_motion_model_file_sha256"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_motion_model_observed_digest_mismatch",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(
                summary_dir / "motion_model_observed_digest_mismatch.json",
                model_path=source_model,
                declared_sha256=SOURCE_MODEL_SHA256,
                observed_sha256=BUNDLE_MODEL_SHA256,
            ),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "motion_bundle_consistency_status": (
                    "reviewed_mujoco_motion_model_observed_digest_mismatch"
                ),
                "motion_bundle_consistency_ready": False,
                "development_fixture": True,
                "motion_child_ready": True,
                "motion_path_matches_bundle": True,
                "motion_digest_matches_bundle": True,
                "motion_observed_sha256_missing": False,
                "motion_observed_sha256_matches_declared": False,
                "blockers_contain": [
                    "inspect_reviewed_mujoco_motion_model_file_sha256"
                ],
                "actions_contain": [
                    "inspect_reviewed_mujoco_motion_model_file_sha256"
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
                "blocker_packet_next_actions_contain": [
                    "inspect_reviewed_mujoco_motion_model_file_sha256"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_motion_model_path_mismatch",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(
                summary_dir / "motion_model_path_mismatch.json",
                model_path=bundle_model,
            ),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "motion_bundle_consistency_status": (
                    "reviewed_mujoco_motion_model_path_mismatch"
                ),
                "motion_bundle_consistency_ready": False,
                "development_fixture": True,
                "motion_child_ready": True,
                "motion_path_matches_bundle": False,
                "motion_digest_matches_bundle": True,
                "blockers_contain": [
                    "align_reviewed_mujoco_motion_with_bundle_model_path"
                ],
                "actions_contain": [
                    "align_reviewed_mujoco_motion_with_bundle_model_path"
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
                "blocker_packet_next_actions_contain": [
                    "align_reviewed_mujoco_motion_with_bundle_model_path"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_bundle_motion_model_digest_mismatch",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(
                summary_dir / "motion_model_digest_mismatch.json",
                model_path=source_model,
                sha256=BUNDLE_MODEL_SHA256,
            ),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "motion_bundle_consistency_status": (
                    "reviewed_mujoco_motion_model_digest_mismatch"
                ),
                "motion_bundle_consistency_ready": False,
                "development_fixture": True,
                "motion_child_ready": True,
                "motion_path_matches_bundle": True,
                "motion_digest_matches_bundle": False,
                "blockers_contain": [
                    "align_reviewed_mujoco_motion_with_bundle_model_digest"
                ],
                "actions_contain": [
                    "align_reviewed_mujoco_motion_with_bundle_model_digest"
                ],
                "action_required_contains": ["physical_reviewed_mujoco_motion_checked"],
                "blocker_packet_next_actions_contain": [
                    "align_reviewed_mujoco_motion_with_bundle_model_digest"
                ],
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
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
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
            "case_id": "source_ready_physical_bundle_with_fixture_ready_conflict",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(
                summary_dir / "bundle_ready_fixture_conflict.json",
                source_model,
                fixture_ready=True,
            ),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "development_fixture": True,
                "development_fixture_present": True,
                "blockers_contain": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
                "actions_contain": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
                "action_required_contains": ["development_fixture_authority_boundary"],
                "blocker_packet_next_actions_contain": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
            },
        },
        {
            "case_id": "source_ready_physical_motion_with_fixture_motion_conflict",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(
                summary_dir / "motion_ready_fixture_conflict.json",
                model_path=source_model,
                fixture_motion_checked=True,
            ),
            "expect": {
                "ready": False,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
                "consistency_ready": True,
                "development_fixture": True,
                "development_fixture_present": True,
                "blockers_contain": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
                "actions_contain": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
                "action_required_contains": ["development_fixture_authority_boundary"],
                "blocker_packet_next_actions_contain": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
            },
        },
        {
            "case_id": "all_ready_contract_state",
            "source": source_ready(summary_dir / "source_ready.json", source_model),
            "bundle": bundle_physical_ready(summary_dir / "bundle_ready.json", source_model),
            "motion": motion_physical_ready(summary_dir / "motion_ready.json", model_path=source_model),
            "expect": {
                "ready": True,
                "consistency_status": "source_bundle_model_path_and_digest_consistent",
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
        "reviewed_model_authority_ready",
        gate.get("reviewed_model_authority_ready"),
        expect["ready"],
    )
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
    if "motion_reported" in expect:
        add_error(
            errors,
            "physical_reviewed_model_motion_reported",
            gate.get("physical_reviewed_model_motion_reported"),
            expect["motion_reported"],
        )
    if "motion_status_ready" in expect:
        add_error(
            errors,
            "physical_reviewed_model_motion_status_ready",
            gate.get("physical_reviewed_model_motion_status_ready"),
            expect["motion_status_ready"],
        )
    if "motion_child_ready" in expect:
        add_error(
            errors,
            "physical_reviewed_model_motion_child_ready",
            gate.get("physical_reviewed_model_motion_child_ready"),
            expect["motion_child_ready"],
        )
    if "development_fixture_present" in expect:
        add_error(
            errors,
            "development_fixture_evidence_present",
            gate.get("development_fixture_evidence_present"),
            expect["development_fixture_present"],
        )
    if "reviewed_mujoco_bundle_status" in expect:
        add_error(
            errors,
            "reviewed_mujoco_bundle_status",
            gate.get("reviewed_mujoco_bundle_status"),
            expect["reviewed_mujoco_bundle_status"],
        )
    if "reviewed_mujoco_motion_authority_status" in expect:
        add_error(
            errors,
            "reviewed_mujoco_motion_authority_status",
            gate.get("reviewed_mujoco_motion_authority_status"),
            expect["reviewed_mujoco_motion_authority_status"],
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
                "selected_authoritative_candidate_path_and_sha256",
            )
            add_error(
                errors,
                "selected_path_matches_bundle",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_path_matches_bundle"
                ),
                True,
            )
            add_error(
                errors,
                "selected_digest_matches_bundle",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_sha256_matches_bundle"
                ),
                True,
            )
            add_error(
                errors,
                "selected_covered_by_source_configuration",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_covered_by_source_configuration"
                ),
                True,
            )
        if "selected_path_matches_bundle" in expect:
            add_error(
                errors,
                "selected_path_matches_bundle",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_path_matches_bundle"
                ),
                expect["selected_path_matches_bundle"],
            )
        if "selected_digest_matches_bundle" in expect:
            add_error(
                errors,
                "selected_digest_matches_bundle",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_sha256_matches_bundle"
                ),
                expect["selected_digest_matches_bundle"],
            )
        if "selected_declared_by_path" in expect:
            add_error(
                errors,
                "selected_declared_by_path",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_declared_by_authoritative_path"
                ),
                expect["selected_declared_by_path"],
            )
        if "selected_within_root" in expect:
            add_error(
                errors,
                "selected_within_root",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_within_authoritative_root"
                ),
                expect["selected_within_root"],
            )
        if "selected_covered_by_source_configuration" in expect:
            add_error(
                errors,
                "selected_covered_by_source_configuration",
                source_bundle_consistency.get(
                    "selected_authoritative_candidate_covered_by_source_configuration"
                ),
                expect["selected_covered_by_source_configuration"],
            )
        if "bundle_declared_sha256" in expect:
            add_error(
                errors,
                "bundle_declared_sha256",
                source_bundle_consistency.get("bundle_model_declared_sha256"),
                expect["bundle_declared_sha256"],
            )
        if "bundle_observed_sha256" in expect:
            add_error(
                errors,
                "bundle_observed_sha256",
                source_bundle_consistency.get("bundle_model_observed_sha256"),
                expect["bundle_observed_sha256"],
            )
        if "bundle_model_sha256" in expect:
            add_error(
                errors,
                "bundle_model_sha256",
                source_bundle_consistency.get("bundle_model_sha256"),
                expect["bundle_model_sha256"],
            )
        if "bundle_observed_sha256_missing" in expect:
            add_error(
                errors,
                "bundle_observed_sha256_missing",
                source_bundle_consistency.get("bundle_model_observed_sha256_missing"),
                expect["bundle_observed_sha256_missing"],
            )
        if "bundle_observed_sha256_matches_declared" in expect:
            add_error(
                errors,
                "bundle_observed_sha256_matches_declared",
                source_bundle_consistency.get(
                    "bundle_model_observed_sha256_matches_declared"
                ),
                expect["bundle_observed_sha256_matches_declared"],
            )

    motion_bundle_consistency = gate.get("reviewed_mujoco_motion_bundle_consistency")
    if not isinstance(motion_bundle_consistency, dict):
        errors.append("reviewed_mujoco_motion_bundle_consistency: expected dict")
    else:
        add_error(
            errors,
            "nested_motion_bundle_consistency_status",
            motion_bundle_consistency.get("status"),
            gate.get("reviewed_mujoco_motion_bundle_consistency_status"),
        )
        add_error(
            errors,
            "nested_motion_bundle_consistency_ready",
            motion_bundle_consistency.get("ready"),
            gate.get("reviewed_mujoco_motion_bundle_consistency_ready"),
        )
        if gate.get("ready") is True:
            add_error(
                errors,
                "motion_path_matches_bundle",
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_path_matches_bundle"
                ),
                True,
            )
            add_error(
                errors,
                "motion_digest_matches_bundle",
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_sha256_matches_bundle"
                ),
                True,
            )
        if "motion_bundle_consistency_status" in expect:
            add_error(
                errors,
                "reviewed_mujoco_motion_bundle_consistency_status",
                gate.get("reviewed_mujoco_motion_bundle_consistency_status"),
                expect["motion_bundle_consistency_status"],
            )
        if "motion_bundle_consistency_ready" in expect:
            add_error(
                errors,
                "reviewed_mujoco_motion_bundle_consistency_ready",
                gate.get("reviewed_mujoco_motion_bundle_consistency_ready"),
                expect["motion_bundle_consistency_ready"],
            )
        if "motion_path_matches_bundle" in expect:
            add_error(
                errors,
                "motion_path_matches_bundle",
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_path_matches_bundle"
                ),
                expect["motion_path_matches_bundle"],
            )
        if "motion_digest_matches_bundle" in expect:
            add_error(
                errors,
                "motion_digest_matches_bundle",
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_sha256_matches_bundle"
                ),
                expect["motion_digest_matches_bundle"],
            )
        if "motion_observed_sha256_missing" in expect:
            add_error(
                errors,
                "motion_observed_sha256_missing",
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_observed_sha256_missing"
                ),
                expect["motion_observed_sha256_missing"],
            )
        if "motion_observed_sha256_matches_declared" in expect:
            add_error(
                errors,
                "motion_observed_sha256_matches_declared",
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_observed_sha256_matches_declared"
                ),
                expect["motion_observed_sha256_matches_declared"],
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
    if "blocker_packet_next_actions_exact" in expect:
        add_error(
            errors,
            "blocker_packet_next_action_ids",
            blocker_packet.get("next_action_ids"),
            expect["blocker_packet_next_actions_exact"],
        )
    expect_contains(
        errors,
        "blocker_packet_next_action_ids",
        blocker_packet.get("next_action_ids"),
        expect.get("blocker_packet_next_actions_contain", []),
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
    consistency = gate.get("source_bundle_consistency")
    consistency = consistency if isinstance(consistency, dict) else {}
    motion_consistency = gate.get("reviewed_mujoco_motion_bundle_consistency")
    motion_consistency = (
        motion_consistency if isinstance(motion_consistency, dict) else {}
    )
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "gate_status": gate.get("status"),
        "gate_ready": gate.get("ready"),
        "reviewed_model_authority_ready": gate.get("reviewed_model_authority_ready"),
        "source_authority_ready": gate.get("source_authority_ready"),
        "physical_bundle_ready": gate.get("physical_so101_model_authority_ready"),
        "source_bundle_consistency_status": gate.get("source_bundle_consistency_status"),
        "source_bundle_consistency_ready": gate.get("source_bundle_consistency_ready"),
        "selected_authoritative_candidate_declared_by_authoritative_path": (
            consistency.get(
                "selected_authoritative_candidate_declared_by_authoritative_path"
            )
        ),
        "selected_authoritative_candidate_within_authoritative_root": consistency.get(
            "selected_authoritative_candidate_within_authoritative_root"
        ),
        "selected_authoritative_candidate_covered_by_source_configuration": (
            consistency.get(
                "selected_authoritative_candidate_covered_by_source_configuration"
            )
        ),
        "bundle_model_observed_sha256_missing": consistency.get(
            "bundle_model_observed_sha256_missing"
        ),
        "bundle_model_observed_sha256_matches_declared": consistency.get(
            "bundle_model_observed_sha256_matches_declared"
        ),
        "reviewed_mujoco_motion_bundle_consistency_status": gate.get(
            "reviewed_mujoco_motion_bundle_consistency_status"
        ),
        "reviewed_mujoco_motion_bundle_consistency_ready": gate.get(
            "reviewed_mujoco_motion_bundle_consistency_ready"
        ),
        "reviewed_mujoco_motion_model_path_matches_bundle": motion_consistency.get(
            "reviewed_mujoco_motion_model_path_matches_bundle"
        ),
        "reviewed_mujoco_motion_model_sha256_matches_bundle": motion_consistency.get(
            "reviewed_mujoco_motion_model_sha256_matches_bundle"
        ),
        "reviewed_mujoco_motion_model_observed_sha256_missing": (
            motion_consistency.get(
                "reviewed_mujoco_motion_model_observed_sha256_missing"
            )
        ),
        "reviewed_mujoco_motion_model_observed_sha256_matches_declared": (
            motion_consistency.get(
                "reviewed_mujoco_motion_model_observed_sha256_matches_declared"
            )
        ),
        "physical_reviewed_model_motion_checked": gate.get(
            "physical_reviewed_model_motion_checked"
        ),
        "physical_reviewed_model_motion_reported": gate.get(
            "physical_reviewed_model_motion_reported"
        ),
        "physical_reviewed_model_motion_status_ready": gate.get(
            "physical_reviewed_model_motion_status_ready"
        ),
        "physical_reviewed_model_motion_child_ready": gate.get(
            "physical_reviewed_model_motion_child_ready"
        ),
        "reviewed_mujoco_bundle_status": gate.get("reviewed_mujoco_bundle_status"),
        "reviewed_mujoco_motion_authority_status": gate.get(
            "reviewed_mujoco_motion_authority_status"
        ),
        "development_fixture_evidence_not_physical_so101_truth": gate.get(
            "development_fixture_evidence_not_physical_so101_truth"
        ),
        "development_fixture_evidence_present": gate.get(
            "development_fixture_evidence_present"
        ),
        "blockers": gate.get("blockers"),
        "next_required_action_ids": gate.get("next_required_action_ids"),
        "blocker_packet_action_required_item_ids": blocker_packet.get(
            "action_required_item_ids"
        ),
        "blocker_packet_blocked_by_prior_requirements_item_ids": blocker_packet.get(
            "blocked_by_prior_requirements_item_ids"
        ),
        "blocker_packet_next_action_ids": blocker_packet.get("next_action_ids"),
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
