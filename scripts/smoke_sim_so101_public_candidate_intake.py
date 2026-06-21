#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

SCHEMA = "lerobot.sim.so101_public_candidate_intake.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_public_candidate_intake"
DEFAULT_REPOSITORY_URL = "https://github.com/TheRobotStudio/SO-ARM100"
DEFAULT_SOURCE_TREE_URL = (
    "https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation/SO101"
)
DEFAULT_MODEL_RELATIVE_PATH = "so101_new_calib.urdf"
EXPECTED_TARGET_FRAME = "gripper_frame_link"
EXPECTED_SO101_JOINTS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
REQUIRED_REVIEW_SCOPES = (
    "model_identity",
    "provenance",
    "license",
    "mesh_assets",
    "joint_limits",
    "gripper_mapping",
    "collision_policy",
    "target_frame",
    "tcp_offset",
    "base_to_board_alignment",
)
UNDECLARED_INTAKE_DECISION = "undeclared"
INTAKE_DECISION_CHOICES = (
    UNDECLARED_INTAKE_DECISION,
    "external_pinned_source_root",
    "vendor_locked_bundle",
)
EXPECTED_RELATIVE_PATHS = (
    "README.md",
    "joints_properties.xml",
    "scene.xml",
    "so101_new_calib.urdf",
    "so101_new_calib.xml",
    "so101_old_calib.urdf",
    "so101_old_calib.xml",
    "assets/base_motor_holder_so101_v1.stl",
    "assets/base_so101_v2.stl",
    "assets/moving_jaw_so101_v1.stl",
    "assets/motor_holder_so101_base_v1.stl",
    "assets/motor_holder_so101_wrist_v1.stl",
    "assets/rotation_pitch_so101_v1.stl",
    "assets/sts3215_03a_no_horn_v1.stl",
    "assets/sts3215_03a_v1.stl",
    "assets/under_arm_so101_v1.stl",
    "assets/upper_arm_so101_v1.stl",
    "assets/waveshare_mounting_plate_so101_v2.stl",
    "assets/wrist_roll_follower_so101_v1.stl",
    "assets/wrist_roll_pitch_so101_v2.stl",
)
LOCKABLE_SUFFIXES = {".md", ".part", ".stl", ".urdf", ".xml"}
MODEL_RELATIVE_PATHS = (
    "scene.xml",
    "so101_new_calib.urdf",
    "so101_new_calib.xml",
    "so101_old_calib.urdf",
    "so101_old_calib.xml",
)
SELECTABLE_MODEL_RELATIVE_PATHS = (
    "so101_new_calib.urdf",
    "so101_new_calib.xml",
    "so101_old_calib.urdf",
    "so101_old_calib.xml",
)
REVIEW_CHECKLIST_FIELDNAMES = (
    "priority",
    "action_id",
    "gate",
    "status",
    "title",
    "detail",
    "candidate_observation",
    "required_review_scope",
    "manifest_fields",
    "authority_boundary",
)
OPERATOR_REQUIREMENT_FIELDNAMES = (
    "option_id",
    "selected",
    "requirement_id",
    "title",
    "required_evidence",
    "manifest_or_review_field",
    "authority_boundary",
)
SOURCE_LOCK_DIGEST_FIELDNAMES = (
    "relative_path",
    "sha256",
    "size_bytes",
    "suffix",
    "expected",
    "selected_model",
    "digest_role",
    "authority_boundary",
)
MODEL_OBSERVATION_FIELDNAMES = (
    "relative_path",
    "path",
    "exists",
    "parse_ok",
    "parse_error",
    "root_tag",
    "model_name",
    "joint_count",
    "joint_limit_or_range_count",
    "mesh_reference_count",
    "selectable_model",
    "selected_model",
    "joint_names",
    "mesh_references",
    "authority_boundary",
)


def command_string(parts: list[str]) -> str:
    return " ".join(parts)


def is_full_git_commit_sha(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[0-9a-fA-F]{40}", value.strip()))


def candidate_operator_command_plan(summary: dict[str, Any]) -> dict[str, Any]:
    upstream = summary.get("upstream")
    upstream = upstream if isinstance(upstream, dict) else {}
    source_lock = summary.get("candidate_source_lock")
    source_lock = source_lock if isinstance(source_lock, dict) else {}
    operator_plan = summary.get("candidate_operator_intake_plan")
    operator_plan = operator_plan if isinstance(operator_plan, dict) else {}
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    upstream_commit = upstream.get("commit")
    upstream_commit_sha_valid = upstream.get("commit_sha_valid") is True
    model_relative_path = summary.get("model_relative_path") or DEFAULT_MODEL_RELATIVE_PATH
    checkout_root = "<local-SO-ARM100-checkout>"
    so101_source_root = f"{checkout_root}/Simulation/SO101"
    selected_source_model_path = f"{so101_source_root}/{model_relative_path}"
    vendored_source_root = "<repo-vendored-SO101-asset-root>"
    vendored_selected_model_path = f"{vendored_source_root}/{model_relative_path}"
    source_reference = (
        f"{upstream.get('source_tree_url') or DEFAULT_SOURCE_TREE_URL} "
        f"commit:{upstream_commit or '<immutable-upstream-commit-sha>'}"
    )
    reviewed_manifest_path = (
        "<reviewed-edited-copy-of-"
        "so101_public_candidate_review_manifest_template.direct.json>"
    )
    selected_option = operator_plan.get("selected_intake_option_id")
    selected_requirement_ids = operator_plan.get(
        "selected_option_review_requirement_ids"
    )
    selected_requirement_ids = (
        selected_requirement_ids if isinstance(selected_requirement_ids, list) else []
    )
    selected_requirements = operator_plan.get("selected_option_review_requirements")
    selected_requirements = (
        selected_requirements if isinstance(selected_requirements, list) else []
    )
    source_lock_ready = source_lock.get("source_lock_ready_for_review") is True
    command_status = (
        "candidate_operator_commands_ready_for_pinned_source_review"
        if upstream_commit_sha_valid
        else "candidate_operator_commands_need_pinned_commit"
    )
    external_commands = [
        {
            "step_id": "clone_soarm100_repository_if_missing",
            "command": command_string(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    str(upstream.get("repository_url") or DEFAULT_REPOSITORY_URL),
                    checkout_root,
                ]
            ),
            "network_required": True,
            "executes_in_smoke": False,
        },
        {
            "step_id": "fetch_pinned_soarm100_commit",
            "command": command_string(
                [
                    "git",
                    "-C",
                    checkout_root,
                    "fetch",
                    "--depth=1",
                    "origin",
                    str(upstream_commit or "<immutable-upstream-commit-sha>"),
                ]
            ),
            "network_required": True,
            "executes_in_smoke": False,
        },
        {
            "step_id": "checkout_pinned_soarm100_commit",
            "command": command_string(
                [
                    "git",
                    "-C",
                    checkout_root,
                    "checkout",
                    "--detach",
                    str(upstream_commit or "<immutable-upstream-commit-sha>"),
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_candidate_intake_on_pinned_checkout",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_public_candidate_intake.py",
                    "--source-root",
                    so101_source_root,
                    "--upstream-commit",
                    str(upstream_commit or "<immutable-upstream-commit-sha>"),
                    "--model-relative-path",
                    str(model_relative_path),
                    "--operator-intake-decision",
                    "external_pinned_source_root",
                    "--output-dir",
                    "/private/tmp/lerobot_sim/so101_public_candidate_intake_external",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_source_inventory_on_candidate_checkout",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_model_source_inventory.py",
                    "--root",
                    so101_source_root,
                    "--output-dir",
                    "/private/tmp/lerobot_sim/soarm100_so101_source_inventory_candidate",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_source_inventory_after_source_authority_review",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_model_source_inventory.py",
                    "--root",
                    so101_source_root,
                    "--authoritative-path",
                    selected_source_model_path,
                    "--authority-reviewed-by",
                    "<reviewer-or-team>",
                    "--authority-reviewed-at",
                    "<review-date-YYYY-MM-DD>",
                    "--authority-review-id",
                    "<stable-source-authority-review-id>",
                    "--authority-source-reference",
                    source_reference,
                    "--authority-license-basis",
                    "<reviewed-license-basis>",
                    "--authority-review-scope",
                    "model_identity",
                    "--authority-review-scope",
                    "provenance",
                    "--authority-review-scope",
                    "license",
                    "--output-dir",
                    "/private/tmp/lerobot_sim/soarm100_so101_source_inventory_reviewed",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_reviewed_bundle_manifest_checker_after_review",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_model_bundle_manifest.py",
                    "--manifest-path",
                    reviewed_manifest_path,
                    "--output-dir",
                    "/private/tmp/lerobot_sim/so101_model_bundle_manifest_reviewed_candidate",
                    "--python",
                    "<python-executable>",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_integrated_reviewed_authority_gate_after_review",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_calibration_regression_suite.py",
                    "--so101-model-source-root",
                    so101_source_root,
                    "--so101-authoritative-model-path",
                    selected_source_model_path,
                    "--so101-source-authority-reviewed-by",
                    "<reviewer-or-team>",
                    "--so101-source-authority-reviewed-at",
                    "<review-date-YYYY-MM-DD>",
                    "--so101-source-authority-review-id",
                    "<stable-source-authority-review-id>",
                    "--so101-source-authority-source-reference",
                    source_reference,
                    "--so101-source-authority-license-basis",
                    "<reviewed-license-basis>",
                    "--so101-source-authority-review-scope",
                    "model_identity",
                    "--so101-source-authority-review-scope",
                    "provenance",
                    "--so101-source-authority-review-scope",
                    "license",
                    "--so101-model-bundle-manifest",
                    reviewed_manifest_path,
                    "--output-dir",
                    "/private/tmp/lerobot_sim/calibration_regression_suite_reviewed_so101_external",
                    "--python",
                    "<python-executable>",
                    "--include-negative-check",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
    ]
    vendor_commands = [
        {
            "step_id": "copy_reviewed_so101_subset_into_repo",
            "command": (
                "copy reviewed Simulation/SO101 files into "
                "<repo-vendored-SO101-asset-root>"
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_candidate_intake_on_vendored_subset",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_public_candidate_intake.py",
                    "--source-root",
                    vendored_source_root,
                    "--upstream-commit",
                    str(upstream_commit or "<immutable-upstream-commit-sha>"),
                    "--model-relative-path",
                    str(model_relative_path),
                    "--operator-intake-decision",
                    "vendor_locked_bundle",
                    "--output-dir",
                    "/private/tmp/lerobot_sim/so101_public_candidate_intake_vendored",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_source_inventory_on_vendored_subset",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_model_source_inventory.py",
                    "--root",
                    vendored_source_root,
                    "--output-dir",
                    "/private/tmp/lerobot_sim/soarm100_so101_source_inventory_vendored_candidate",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_source_inventory_after_vendor_source_authority_review",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_model_source_inventory.py",
                    "--root",
                    vendored_source_root,
                    "--authoritative-path",
                    vendored_selected_model_path,
                    "--authority-reviewed-by",
                    "<reviewer-or-team>",
                    "--authority-reviewed-at",
                    "<review-date-YYYY-MM-DD>",
                    "--authority-review-id",
                    "<stable-source-authority-review-id>",
                    "--authority-source-reference",
                    source_reference,
                    "--authority-license-basis",
                    "<reviewed-license-basis>",
                    "--authority-review-scope",
                    "model_identity",
                    "--authority-review-scope",
                    "provenance",
                    "--authority-review-scope",
                    "license",
                    "--output-dir",
                    "/private/tmp/lerobot_sim/soarm100_so101_source_inventory_reviewed_vendored",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_reviewed_bundle_manifest_checker_after_vendor_review",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_so101_model_bundle_manifest.py",
                    "--manifest-path",
                    reviewed_manifest_path,
                    "--output-dir",
                    "/private/tmp/lerobot_sim/so101_model_bundle_manifest_reviewed_vendored_candidate",
                    "--python",
                    "<python-executable>",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
        {
            "step_id": "run_integrated_reviewed_authority_gate_after_vendor_review",
            "command": command_string(
                [
                    "python",
                    "scripts/smoke_sim_calibration_regression_suite.py",
                    "--so101-model-source-root",
                    vendored_source_root,
                    "--so101-authoritative-model-path",
                    vendored_selected_model_path,
                    "--so101-source-authority-reviewed-by",
                    "<reviewer-or-team>",
                    "--so101-source-authority-reviewed-at",
                    "<review-date-YYYY-MM-DD>",
                    "--so101-source-authority-review-id",
                    "<stable-source-authority-review-id>",
                    "--so101-source-authority-source-reference",
                    source_reference,
                    "--so101-source-authority-license-basis",
                    "<reviewed-license-basis>",
                    "--so101-source-authority-review-scope",
                    "model_identity",
                    "--so101-source-authority-review-scope",
                    "provenance",
                    "--so101-source-authority-review-scope",
                    "license",
                    "--so101-model-bundle-manifest",
                    reviewed_manifest_path,
                    "--output-dir",
                    "/private/tmp/lerobot_sim/calibration_regression_suite_reviewed_so101_vendored",
                    "--python",
                    "<python-executable>",
                    "--include-negative-check",
                ]
            ),
            "network_required": False,
            "executes_in_smoke": False,
        },
    ]
    option_commands = {
        "external_pinned_source_root": external_commands,
        "vendor_locked_bundle": vendor_commands,
    }
    selected_commands = option_commands.get(selected_option, [])
    return {
        "schema": "lerobot.sim.so101_public_candidate_operator_command_plan.v1",
        "ok": True,
        "status": command_status,
        "model_authority": "candidate_operator_command_plan_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_lock_ready_for_review": source_lock_ready,
        "upstream_commit_sha_valid": upstream_commit_sha_valid,
        "selected_intake_option_id": selected_option,
        "selected_option_command_count": len(selected_commands),
        "selected_option_review_requirement_count": len(selected_requirements),
        "selected_option_review_requirement_ids": selected_requirement_ids,
        "selected_option_review_requirements": selected_requirements,
        "external_pinned_source_root_commands": external_commands,
        "vendor_locked_bundle_commands": vendor_commands,
        "selected_option_commands": selected_commands,
        "candidate_artifacts": {
            "source_lock_json": artifacts.get("candidate_source_lock_json"),
            "source_lock_digests_csv": artifacts.get(
                "candidate_source_lock_digests_csv"
            ),
            "model_file_observations_csv": artifacts.get(
                "candidate_model_file_observations_csv"
            ),
            "operator_intake_plan_json": artifacts.get(
                "candidate_operator_intake_plan_json"
            ),
            "operator_intake_requirements_csv": artifacts.get(
                "candidate_operator_intake_requirements_csv"
            ),
            "review_checklist_json": artifacts.get("candidate_review_checklist_json"),
            "review_checklist_csv": artifacts.get("candidate_review_checklist_csv"),
            "direct_review_manifest_template_json": artifacts.get(
                "candidate_direct_review_manifest_template_json"
            ),
        },
        "review_handoff_artifacts": [
            {
                "artifact_id": "candidate_source_lock_json",
                "path": artifacts.get("candidate_source_lock_json"),
                "purpose": "pinned source, selected model, digest, and non-authority lock summary",
                "authority_boundary": "candidate_source_lock_not_authority",
            },
            {
                "artifact_id": "candidate_source_lock_digests_csv",
                "path": artifacts.get("candidate_source_lock_digests_csv"),
                "purpose": "complete expected and extra lockable file digest review rows",
                "authority_boundary": "candidate_source_lock_digest_not_authority",
            },
            {
                "artifact_id": "candidate_operator_intake_requirements_csv",
                "path": artifacts.get("candidate_operator_intake_requirements_csv"),
                "purpose": "selected external or vendor requirement checklist",
                "authority_boundary": "candidate_operator_intake_requirement_not_authority",
            },
            {
                "artifact_id": "candidate_direct_review_manifest_template_json",
                "path": artifacts.get("candidate_direct_review_manifest_template_json"),
                "purpose": "reviewer-editable bundle manifest template",
                "authority_boundary": "candidate_seeded_review_manifest_template_not_authority",
            },
        ],
        "authority_blockers_until_reviewed": [
            "selected source-lock digest rows must be reviewed and copied only into reviewed authority fields",
            "license and provenance review evidence must be recorded for the selected intake option",
            "SO-ARM100 README caveats for gripper linear-joint mapping and removed base collision meshes must be resolved in reviewed fields",
            "reviewed bundle manifest checker must report physical_so101_model_authority_ready",
            "reviewed MuJoCo bundle gate must prove physical reviewed model motion",
        ],
        "limitations": [
            "These commands are an operator checklist; this smoke does not execute network, copy, or vendor steps.",
            "A command plan with a pinned commit is review handoff evidence only, not reviewed physical SO-101 authority.",
            "Source-inventory commands must be rerun with real reviewer metadata before they can satisfy source-authority readiness.",
            "The reviewed bundle manifest checker must still pass after reviewer-edited authority fields are supplied.",
        ],
    }


def candidate_operator_intake_plan(summary: dict[str, Any]) -> dict[str, Any]:
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    upstream = summary.get("upstream")
    upstream = upstream if isinstance(upstream, dict) else {}
    source_lock = summary.get("candidate_source_lock")
    source_lock = source_lock if isinstance(source_lock, dict) else {}
    source_lock_ready = source_lock.get("source_lock_ready_for_review") is True
    upstream_commit = upstream.get("commit")
    intake_decision = summary.get("operator_intake_decision")
    intake_decision = (
        str(intake_decision)
        if intake_decision in INTAKE_DECISION_CHOICES
        else UNDECLARED_INTAKE_DECISION
    )
    selected_intake_option_id = (
        intake_decision if intake_decision != UNDECLARED_INTAKE_DECISION else None
    )
    if selected_intake_option_id is None:
        decision_status = "vendor_or_external_intake_not_declared"
    elif not source_lock_ready:
        decision_status = "candidate_intake_decision_waiting_for_source_lock"
    else:
        decision_status = "candidate_intake_decision_recorded_not_authority"
    selected_model = source_lock.get("selected_model")
    selected_model = selected_model if isinstance(selected_model, dict) else {}
    next_required_action_ids = [
        "declare_vendor_or_external_intake_decision",
        "pin_or_vendor_soarm100_so101_assets",
        "review_candidate_source_lock",
        "edit_direct_review_manifest_template_with_reviewed_values",
        "run_reviewed_bundle_manifest_checker",
    ]
    if selected_intake_option_id is not None:
        next_required_action_ids = [
            action_id
            for action_id in next_required_action_ids
            if action_id != "declare_vendor_or_external_intake_decision"
        ]
    option_review_requirements = {
        "external_pinned_source_root": [
            {
                "requirement_id": "external_checkout_path_declared",
                "title": "Declare the local SO-ARM100/SO101 checkout path",
                "required_evidence": "absolute local source root for the pinned upstream checkout",
                "manifest_or_review_field": "asset_roots",
            },
            {
                "requirement_id": "external_upstream_commit_pinned",
                "title": "Pin the immutable upstream commit",
                "required_evidence": "reviewed SO-ARM100 commit SHA for Simulation/SO101",
                "manifest_or_review_field": "provenance.source_reference",
            },
            {
                "requirement_id": "external_file_digest_lock_reviewed",
                "title": "Review complete lockable file digest handoff",
                "required_evidence": "complete expected SO101 file digest set plus discovered lockable extra file digests from candidate_source_lock",
                "manifest_or_review_field": "mesh_asset_authority",
            },
            {
                "requirement_id": "external_gripper_mapping_reviewed",
                "title": "Review SO-ARM100 gripper mapping caveat",
                "required_evidence": "review record resolving the README gripper linear-joint mapping caveat",
                "manifest_or_review_field": "gripper_mapping_authority",
            },
            {
                "requirement_id": "external_collision_policy_reviewed",
                "title": "Review SO-ARM100 collision policy caveat",
                "required_evidence": "review record resolving the removed base collision mesh policy",
                "manifest_or_review_field": "collision_policy_authority",
            },
            {
                "requirement_id": "external_reviewed_bundle_manifest_supplied",
                "title": "Supply reviewed bundle manifest for external source",
                "required_evidence": "reviewed model bundle manifest with authority fields replaced",
                "manifest_or_review_field": "<reviewed-manifest>",
            },
        ],
        "vendor_locked_bundle": [
            {
                "requirement_id": "vendor_import_path_declared",
                "title": "Declare the vendored SO101 asset root",
                "required_evidence": "repo-local vendored asset path and import commit or review record",
                "manifest_or_review_field": "asset_roots",
            },
            {
                "requirement_id": "vendor_upstream_commit_pinned",
                "title": "Pin the vendored upstream source commit",
                "required_evidence": "reviewed SO-ARM100 commit SHA used for the vendored subset",
                "manifest_or_review_field": "provenance.source_reference",
            },
            {
                "requirement_id": "vendor_license_provenance_reviewed",
                "title": "Review license and provenance for vendored files",
                "required_evidence": "license/provenance review record for copied asset subset",
                "manifest_or_review_field": "provenance.license_basis",
            },
            {
                "requirement_id": "vendor_file_digest_manifest_reviewed",
                "title": "Review vendored file digest manifest",
                "required_evidence": "digest manifest for every vendored SO101 file and every lockable source/asset file retained in the reviewed bundle",
                "manifest_or_review_field": "mesh_asset_authority",
            },
            {
                "requirement_id": "vendor_gripper_mapping_reviewed",
                "title": "Review vendored gripper mapping caveat",
                "required_evidence": "review record resolving the README gripper linear-joint mapping caveat for the vendored subset",
                "manifest_or_review_field": "gripper_mapping_authority",
            },
            {
                "requirement_id": "vendor_collision_policy_reviewed",
                "title": "Review vendored collision policy caveat",
                "required_evidence": "review record resolving the removed base collision mesh policy for the vendored subset",
                "manifest_or_review_field": "collision_policy_authority",
            },
            {
                "requirement_id": "vendor_reviewed_bundle_manifest_supplied",
                "title": "Supply reviewed bundle manifest for vendored source",
                "required_evidence": "reviewed model bundle manifest with authority fields replaced",
                "manifest_or_review_field": "<reviewed-manifest>",
            },
        ],
    }
    selected_option_review_requirements = (
        option_review_requirements.get(selected_intake_option_id, [])
        if selected_intake_option_id is not None
        else []
    )
    return {
        "schema": "lerobot.sim.so101_public_candidate_operator_intake_plan.v1",
        "ok": True,
        "status": (
            "candidate_locked_operator_decision_required"
            if source_lock_ready
            else "candidate_operator_intake_inputs_incomplete"
        ),
        "model_authority": "candidate_operator_intake_plan_not_authority",
        "decision_status": decision_status,
        "selected_intake_option_id": selected_intake_option_id,
        "option_review_requirements": option_review_requirements,
        "selected_option_review_requirements": selected_option_review_requirements,
        "selected_option_review_requirement_count": len(
            selected_option_review_requirements
        ),
        "selected_option_review_requirement_ids": [
            requirement["requirement_id"]
            for requirement in selected_option_review_requirements
        ],
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_lock_ready_for_review": source_lock_ready,
        "source_lock_status": source_lock.get("status"),
        "upstream": {
            "repository_url": upstream.get("repository_url"),
            "source_tree_url": upstream.get("source_tree_url"),
            "commit": upstream_commit,
        },
        "source_root": summary.get("source_root"),
        "selected_model": selected_model,
        "candidate_artifacts": {
            "summary_json": artifacts.get("summary_json"),
            "files_csv": artifacts.get("files_csv"),
            "source_lock_json": artifacts.get("candidate_source_lock_json"),
            "direct_review_manifest_template_json": artifacts.get(
                "candidate_direct_review_manifest_template_json"
            ),
            "review_checklist_json": artifacts.get("candidate_review_checklist_json"),
            "review_checklist_csv": artifacts.get("candidate_review_checklist_csv"),
        },
        "intake_options": [
            {
                "option_id": "external_pinned_source_root",
                "decision": "keep_assets_external_and_reference_local_checkout",
                "required_inputs": [
                    "immutable_upstream_commit",
                    "local_source_root",
                    "complete_expected_file_digest_lock",
                    "reviewed_bundle_manifest",
                ],
                "command_template": [
                    "python",
                    "scripts/smoke_sim_so101_public_candidate_intake.py",
                    "--source-root",
                    "<local-SO-ARM100/Simulation/SO101-checkout>",
                    "--upstream-commit",
                    upstream_commit or "<immutable-upstream-commit>",
                    "--operator-intake-decision",
                    "external_pinned_source_root",
                    "--output-dir",
                    "/private/tmp/lerobot_sim/so101_public_candidate_intake",
                ],
                "authority_boundary": "external_source_root_not_reviewed_authority",
            },
            {
                "option_id": "vendor_locked_bundle",
                "decision": "vendor_reviewed_asset_subset_into_repo",
                "required_inputs": [
                    "license_provenance_review",
                    "pinned_upstream_commit",
                    "file_digest_manifest",
                    "reviewed_model_bundle_manifest",
                    "repo_import_review",
                ],
                "command_template": [
                    "python",
                    "scripts/smoke_sim_so101_public_candidate_intake.py",
                    "--source-root",
                    "<repo-vendored-SO101-asset-root>",
                    "--upstream-commit",
                    upstream_commit or "<immutable-upstream-commit>",
                    "--operator-intake-decision",
                    "vendor_locked_bundle",
                    "--output-dir",
                    "/private/tmp/lerobot_sim/so101_public_candidate_intake_vendored",
                ],
                "authority_boundary": "vendored_files_still_require_reviewed_manifest",
            },
        ],
        "review_flow": [
            "Choose external pinned source root or vendored locked bundle.",
            "Keep the selected upstream commit immutable in review evidence.",
            "Review source lock digests, license/provenance, model variant, mesh roots, joint limits, target frame, gripper/TCP offset, and base-to-board alignment.",
            "Resolve the SO-ARM100 README gripper linear-joint mapping caveat and removed base collision mesh policy in reviewed fields.",
            "Edit the direct review manifest template with reviewed values only.",
            "Run scripts/smoke_sim_so101_model_bundle_manifest.py against the reviewed manifest.",
            "Use the reviewed bundle downstream only when physical_so101_model_authority_ready and ready_for_model_backed_ik are true.",
        ],
        "next_required_action_ids": [
            *next_required_action_ids,
        ],
        "limitations": [
            "This plan does not clone, vendor, copy, or verify remote Git state.",
            "A selected intake option is not reviewed physical SO-101 authority.",
            "Reviewed authority still requires a reviewed bundle manifest and passing reviewed MuJoCo motion evidence.",
        ],
    }


def candidate_operator_intake_requirement_rows(
    operator_intake_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    option_review_requirements = operator_intake_plan.get("option_review_requirements")
    option_review_requirements = (
        option_review_requirements
        if isinstance(option_review_requirements, dict)
        else {}
    )
    selected_option = operator_intake_plan.get("selected_intake_option_id")
    rows: list[dict[str, Any]] = []
    for option_id in INTAKE_DECISION_CHOICES:
        if option_id == UNDECLARED_INTAKE_DECISION:
            continue
        requirements = option_review_requirements.get(option_id)
        requirements = requirements if isinstance(requirements, list) else []
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            rows.append(
                {
                    "option_id": option_id,
                    "selected": option_id == selected_option,
                    "requirement_id": requirement.get("requirement_id"),
                    "title": requirement.get("title"),
                    "required_evidence": requirement.get("required_evidence"),
                    "manifest_or_review_field": requirement.get(
                        "manifest_or_review_field"
                    ),
                    "authority_boundary": (
                        "candidate_operator_intake_requirement_not_authority"
                    ),
                }
            )
    return rows


def candidate_operator_intake_handoff(summary: dict[str, Any]) -> dict[str, Any]:
    operator_plan = summary.get("candidate_operator_intake_plan")
    operator_plan = operator_plan if isinstance(operator_plan, dict) else {}
    operator_command_plan = summary.get("candidate_operator_command_plan")
    operator_command_plan = (
        operator_command_plan if isinstance(operator_command_plan, dict) else {}
    )
    selected_requirement_ids = operator_plan.get(
        "selected_option_review_requirement_ids"
    )
    selected_requirement_ids = (
        selected_requirement_ids if isinstance(selected_requirement_ids, list) else []
    )
    selected_command_requirement_ids = operator_command_plan.get(
        "selected_option_review_requirement_ids"
    )
    selected_command_requirement_ids = (
        selected_command_requirement_ids
        if isinstance(selected_command_requirement_ids, list)
        else []
    )
    return {
        "schema": "lerobot.sim.so101_public_candidate_operator_intake_handoff.v1",
        "model_authority": "candidate_operator_intake_handoff_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "decision_status": operator_plan.get("decision_status"),
        "selected_intake_option_id": operator_plan.get("selected_intake_option_id"),
        "selected_option_review_requirement_count": operator_plan.get(
            "selected_option_review_requirement_count"
        ),
        "selected_option_review_requirement_ids": selected_requirement_ids,
        "selected_option_command_count": operator_command_plan.get(
            "selected_option_command_count"
        ),
        "selected_option_command_requirement_ids": selected_command_requirement_ids,
        "source_lock_ready_for_review": operator_plan.get(
            "source_lock_ready_for_review"
        ),
        "authority_boundary": "candidate_operator_intake_handoff_not_authority",
        "review_instruction": (
            "Use this only to preserve which external-source or vendored-bundle "
            "intake path was selected for review. It is not reviewed SO-101 "
            "model authority."
        ),
    }


def attach_operator_intake_handoff_to_seeded_template(
    summary: dict[str, Any],
) -> dict[str, Any]:
    handoff = candidate_operator_intake_handoff(summary)
    seeded_template = summary.get("candidate_seeded_review_manifest_template")
    seeded_template = seeded_template if isinstance(seeded_template, dict) else {}
    observed_inputs = seeded_template.get("observed_inputs")
    observed_inputs = observed_inputs if isinstance(observed_inputs, dict) else {}
    observed_inputs["candidate_operator_intake_handoff"] = handoff
    seeded_template["observed_inputs"] = observed_inputs
    manifest_template = seeded_template.get("manifest_template")
    manifest_template = manifest_template if isinstance(manifest_template, dict) else {}
    manifest_template["candidate_operator_intake_handoff"] = handoff
    seeded_template["manifest_template"] = manifest_template
    summary["candidate_seeded_review_manifest_template"] = seeded_template
    summary["candidate_operator_intake_handoff"] = handoff
    summary["candidate_operator_intake_handoff_model_authority"] = handoff[
        "model_authority"
    ]
    return handoff


def candidate_reviewed_manifest_rerun_plan(summary: dict[str, Any]) -> dict[str, Any]:
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    source_lock = summary.get("candidate_source_lock")
    source_lock = source_lock if isinstance(source_lock, dict) else {}
    operator_plan = summary.get("candidate_operator_intake_plan")
    operator_plan = operator_plan if isinstance(operator_plan, dict) else {}
    operator_handoff = summary.get("candidate_operator_intake_handoff")
    operator_handoff = operator_handoff if isinstance(operator_handoff, dict) else {}
    selected_requirement_ids = operator_plan.get(
        "selected_option_review_requirement_ids"
    )
    selected_requirement_ids = (
        selected_requirement_ids if isinstance(selected_requirement_ids, list) else []
    )
    source_lock_ready = source_lock.get("source_lock_ready_for_review") is True
    decision_recorded = (
        operator_plan.get("decision_status")
        == "candidate_intake_decision_recorded_not_authority"
    )
    direct_manifest_template_json = artifacts.get(
        "candidate_direct_review_manifest_template_json"
    )
    reviewed_manifest_path = (
        "<reviewed-edited-copy-of-"
        "so101_public_candidate_review_manifest_template.direct.json>"
    )
    checker_output_dir = (
        "/private/tmp/lerobot_sim/so101_model_bundle_manifest_reviewed_candidate"
    )
    command = [
        "python",
        "scripts/smoke_sim_so101_model_bundle_manifest.py",
        "--manifest-path",
        reviewed_manifest_path,
        "--output-dir",
        checker_output_dir,
        "--python",
        "<python-executable>",
    ]
    ready_for_operator_review = bool(source_lock_ready and decision_recorded)
    return {
        "schema": "lerobot.sim.so101_public_candidate_reviewed_manifest_rerun_plan.v1",
        "status": (
            "candidate_reviewed_manifest_rerun_plan_ready"
            if ready_for_operator_review
            else "candidate_reviewed_manifest_rerun_plan_blocked"
        ),
        "model_authority": "candidate_reviewed_manifest_rerun_plan_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_lock_ready_for_review": source_lock_ready,
        "operator_intake_decision_status": operator_plan.get("decision_status"),
        "selected_intake_option_id": operator_plan.get("selected_intake_option_id"),
        "selected_option_review_requirement_ids": selected_requirement_ids,
        "selected_option_command_count": operator_handoff.get(
            "selected_option_command_count"
        ),
        "direct_review_manifest_template_json": direct_manifest_template_json,
        "reviewed_manifest_path_placeholder": reviewed_manifest_path,
        "manifest_checker_command_template": command,
        "expected_manifest_checker_status_before_review": (
            "model_bundle_manifest_needs_follow_up"
        ),
        "required_success_conditions": [
            "reviewer_replaces_all_placeholders_with_reviewed_values",
            "manifest_checker_reports_ready_for_model_backed_ik_true",
            "manifest_checker_reports_physical_so101_model_authority_ready_true",
            "reviewed_mujoco_bundle_gate_loads_model_and_proves_joint_motion",
        ],
        "authority_boundary": "candidate_reviewed_manifest_rerun_plan_not_authority",
        "review_instruction": (
            "Use this as the handoff from public-candidate intake to the "
            "reviewed bundle manifest checker. It does not execute the command "
            "and does not promote candidate observations to reviewed SO-101 "
            "model authority."
        ),
    }


def candidate_review_checklist_handoff(summary: dict[str, Any]) -> dict[str, Any]:
    checklist = summary.get("candidate_review_checklist")
    checklist = checklist if isinstance(checklist, dict) else {}
    direct_actions_by_scope = checklist.get(
        "direct_action_ids_by_required_review_scope"
    )
    direct_actions_by_scope = (
        direct_actions_by_scope if isinstance(direct_actions_by_scope, dict) else {}
    )
    return {
        "schema": "lerobot.sim.so101_public_candidate_review_checklist_handoff.v1",
        "model_authority": "candidate_review_checklist_handoff_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "row_count": checklist.get("row_count"),
        "required_review_scope_coverage_ready": checklist.get(
            "required_review_scope_coverage_ready"
        ),
        "missing_required_review_scope_ids": checklist.get(
            "missing_required_review_scope_ids"
        ),
        "required_review_scopes": checklist.get("required_review_scopes"),
        "gripper_mapping_direct_action_ids": direct_actions_by_scope.get(
            "gripper_mapping"
        ),
        "collision_policy_direct_action_ids": direct_actions_by_scope.get(
            "collision_policy"
        ),
        "authority_boundary": "candidate_review_checklist_handoff_not_authority",
        "review_instruction": (
            "Use this only to preserve candidate review checklist coverage in "
            "the manifest handoff. Reviewed authority must be recorded in the "
            "reviewed manifest fields after review."
        ),
    }


def attach_review_checklist_handoff_to_seeded_template(
    summary: dict[str, Any],
) -> dict[str, Any]:
    handoff = candidate_review_checklist_handoff(summary)
    seeded_template = summary.get("candidate_seeded_review_manifest_template")
    seeded_template = seeded_template if isinstance(seeded_template, dict) else {}
    observed_inputs = seeded_template.get("observed_inputs")
    observed_inputs = observed_inputs if isinstance(observed_inputs, dict) else {}
    observed_inputs["candidate_review_checklist_handoff"] = handoff
    seeded_template["observed_inputs"] = observed_inputs
    manifest_template = seeded_template.get("manifest_template")
    manifest_template = manifest_template if isinstance(manifest_template, dict) else {}
    manifest_template["candidate_review_checklist_handoff"] = handoff
    seeded_template["manifest_template"] = manifest_template
    summary["candidate_seeded_review_manifest_template"] = seeded_template
    summary["candidate_review_checklist_handoff"] = handoff
    summary["candidate_review_checklist_handoff_model_authority"] = handoff[
        "model_authority"
    ]
    return handoff


def candidate_source_lock_digest_rows(
    source_lock: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_model = source_lock.get("selected_model")
    selected_model = selected_model if isinstance(selected_model, dict) else {}
    selected_relative_path = selected_model.get("relative_path")
    selected_model_supported = selected_model.get("supported") is True
    file_digests = source_lock.get("file_digests")
    file_digests = file_digests if isinstance(file_digests, list) else []
    rows: list[dict[str, Any]] = []
    for digest in file_digests:
        if not isinstance(digest, dict):
            continue
        relative_path = digest.get("relative_path")
        expected = digest.get("expected") is True
        is_selected_model = bool(
            selected_model_supported
            and relative_path
            and relative_path == selected_relative_path
        )
        if is_selected_model:
            digest_role = "selected_model_digest"
        elif expected:
            digest_role = "expected_candidate_file_digest"
        else:
            digest_role = "discovered_lockable_candidate_file_digest"
        rows.append(
            {
                "relative_path": relative_path,
                "sha256": digest.get("sha256"),
                "size_bytes": digest.get("size_bytes"),
                "suffix": digest.get("suffix"),
                "expected": expected,
                "selected_model": is_selected_model,
                "digest_role": digest_role,
                "authority_boundary": "candidate_source_lock_digest_not_authority",
            }
        )
    return rows


def candidate_model_observation_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    observations = summary.get("candidate_review_observations")
    observations = observations if isinstance(observations, dict) else {}
    model_observations = observations.get("model_file_observations")
    model_observations = (
        model_observations if isinstance(model_observations, list) else []
    )
    selected_relative_path = summary.get("model_relative_path")
    rows: list[dict[str, Any]] = []
    for observation in model_observations:
        if not isinstance(observation, dict):
            continue
        relative_path = observation.get("relative_path")
        rows.append(
            {
                "relative_path": relative_path,
                "path": observation.get("path"),
                "exists": observation.get("exists"),
                "parse_ok": observation.get("parse_ok"),
                "parse_error": observation.get("parse_error"),
                "root_tag": observation.get("root_tag"),
                "model_name": observation.get("model_name"),
                "joint_count": observation.get("joint_count"),
                "joint_limit_or_range_count": observation.get(
                    "joint_limit_or_range_count"
                ),
                "mesh_reference_count": observation.get("mesh_reference_count"),
                "selectable_model": relative_path in SELECTABLE_MODEL_RELATIVE_PATHS,
                "selected_model": bool(
                    relative_path
                    and selected_relative_path
                    and relative_path == selected_relative_path
                    and relative_path in SELECTABLE_MODEL_RELATIVE_PATHS
                ),
                "joint_names": observation.get("joint_names") or [],
                "mesh_references": observation.get("mesh_references") or [],
                "authority_boundary": "candidate_model_observation_not_authority",
            }
        )
    return rows


def normalize_mesh_reference_for_digest(reference: Any) -> str | None:
    if not isinstance(reference, str):
        return None
    value = reference.strip().replace("\\", "/")
    if not value:
        return None
    if value.startswith("./"):
        value = value[2:]
    if value.startswith("../"):
        return None
    if value.startswith("/"):
        return None
    if value.startswith("assets/"):
        return value
    if "/" not in value and Path(value).suffix:
        return f"assets/{value}"
    return value


def selected_model_observation(summary: dict[str, Any]) -> dict[str, Any]:
    observations = summary.get("candidate_review_observations")
    observations = observations if isinstance(observations, dict) else {}
    model_observations = observations.get("model_file_observations")
    model_observations = (
        model_observations if isinstance(model_observations, list) else []
    )
    selected_relative_path = summary.get("model_relative_path")
    selected = next(
        (
            observation
            for observation in model_observations
            if isinstance(observation, dict)
            and observation.get("relative_path") == selected_relative_path
        ),
        {},
    )
    selected = selected if isinstance(selected, dict) else {}
    file_rows = summary.get("file_rows")
    file_rows = file_rows if isinstance(file_rows, list) else []
    locked_relative_paths = {
        str(row.get("relative_path"))
        for row in file_rows
        if isinstance(row, dict)
        and row.get("expected") is True
        and row.get("exists") is True
        and row.get("sha256")
    }
    mesh_references = selected.get("mesh_references")
    mesh_references = mesh_references if isinstance(mesh_references, list) else []
    joint_names = selected.get("joint_names")
    joint_names = [
        str(joint_name)
        for joint_name in joint_names
        if isinstance(joint_name, str) and joint_name
    ] if isinstance(joint_names, list) else []
    observed_expected_joint_names = [
        joint_name for joint_name in EXPECTED_SO101_JOINTS if joint_name in joint_names
    ]
    missing_expected_joint_names = [
        joint_name
        for joint_name in EXPECTED_SO101_JOINTS
        if joint_name not in observed_expected_joint_names
    ]
    unexpected_joint_names = [
        joint_name for joint_name in joint_names if joint_name not in EXPECTED_SO101_JOINTS
    ]
    if not selected:
        expected_joint_coverage_status = "selected_model_not_observed"
    elif selected.get("parse_ok") is not True:
        expected_joint_coverage_status = "selected_model_not_parseable"
    elif not observed_expected_joint_names:
        expected_joint_coverage_status = "no_expected_so101_joints_observed"
    elif missing_expected_joint_names:
        expected_joint_coverage_status = "partial_expected_so101_joints_observed"
    else:
        expected_joint_coverage_status = "all_expected_so101_joints_observed"
    normalized_mesh_references = [
        normalized
        for normalized in (
            normalize_mesh_reference_for_digest(reference)
            for reference in mesh_references
        )
        if normalized
    ]
    digest_matched_mesh_references = [
        reference
        for reference in normalized_mesh_references
        if reference in locked_relative_paths
    ]
    digest_missing_mesh_references = [
        reference
        for reference in normalized_mesh_references
        if reference not in locked_relative_paths
    ]
    if not normalized_mesh_references:
        mesh_reference_digest_coverage_status = "no_mesh_references_observed"
    elif not digest_missing_mesh_references:
        mesh_reference_digest_coverage_status = "all_observed_mesh_references_locked"
    else:
        mesh_reference_digest_coverage_status = "mesh_reference_digest_gaps"
    return {
        "relative_path": selected.get("relative_path") or selected_relative_path,
        "observed": bool(selected),
        "parse_ok": selected.get("parse_ok") is True,
        "parse_error": selected.get("parse_error"),
        "root_tag": selected.get("root_tag"),
        "model_name": selected.get("model_name"),
        "joint_count": int(selected.get("joint_count") or 0),
        "joint_limit_or_range_count": int(
            selected.get("joint_limit_or_range_count") or 0
        ),
        "expected_joint_names": list(EXPECTED_SO101_JOINTS),
        "observed_expected_joint_names": observed_expected_joint_names,
        "missing_expected_joint_names": missing_expected_joint_names,
        "unexpected_joint_names": unexpected_joint_names[:200],
        "expected_joint_coverage_status": expected_joint_coverage_status,
        "expected_joint_observed_count": len(observed_expected_joint_names),
        "expected_joint_missing_count": len(missing_expected_joint_names),
        "unexpected_joint_count": len(unexpected_joint_names),
        "mesh_reference_count": int(selected.get("mesh_reference_count") or 0),
        "mesh_reference_digest_coverage_status": (
            mesh_reference_digest_coverage_status
        ),
        "mesh_reference_digest_match_count": len(digest_matched_mesh_references),
        "mesh_reference_digest_missing_count": len(digest_missing_mesh_references),
        "mesh_reference_digest_matched_relative_paths": (
            digest_matched_mesh_references[:200]
        ),
        "mesh_reference_digest_missing_relative_paths": (
            digest_missing_mesh_references[:200]
        ),
        "authority_boundary": "candidate_selected_model_observation_not_authority",
    }


def candidate_source_lock(summary: dict[str, Any]) -> dict[str, Any]:
    upstream = summary.get("upstream")
    upstream = upstream if isinstance(upstream, dict) else {}
    file_rows = summary.get("file_rows")
    file_rows = file_rows if isinstance(file_rows, list) else []
    expected_file_rows = [
        row
        for row in file_rows
        if isinstance(row, dict) and row.get("expected") is True
    ]
    present_lockable_rows = [
        {
            "relative_path": row.get("relative_path"),
            "sha256": row.get("sha256"),
            "size_bytes": row.get("size_bytes"),
            "suffix": row.get("suffix"),
            "expected": row.get("expected") is True,
        }
        for row in file_rows
        if row.get("exists") is True
    ]
    extra_lockable_relative_paths = [
        str(row.get("relative_path"))
        for row in present_lockable_rows
        if row.get("expected") is not True and row.get("relative_path")
    ]
    expected_digest_count = sum(
        1 for row in present_lockable_rows if row.get("expected") is True
    )
    upstream_commit_supplied = bool(upstream.get("commit_supplied"))
    upstream_commit_sha_valid = upstream.get("commit_sha_valid") is True
    model_present = summary.get("model_present") is True
    selected_model_supported = summary.get("selected_model_supported") is True
    selected_observation = selected_model_observation(summary)
    model_sha_supplied = bool(summary.get("model_sha256_observed"))
    expected_count = int(summary.get("expected_file_count") or 0)
    present_expected = int(summary.get("present_expected_file_count") or 0)
    complete_expected = expected_count > 0 and present_expected == expected_count
    source_lock_ready_for_review = (
        upstream_commit_sha_valid
        and model_present
        and selected_model_supported
        and model_sha_supplied
        and complete_expected
    )
    missing_inputs: list[str] = []
    if not upstream_commit_supplied:
        missing_inputs.append("upstream_commit")
    elif not upstream_commit_sha_valid:
        missing_inputs.append("immutable_upstream_commit_sha")
    if not complete_expected:
        missing_inputs.append("expected_file_digest_lock")
    if not model_present:
        missing_inputs.append("selected_model_path")
    elif not selected_model_supported:
        missing_inputs.append("selectable_so101_model_path")
    if not model_sha_supplied:
        missing_inputs.append("selected_model_sha256")
    return {
        "schema": "lerobot.sim.so101_public_candidate_source_lock.v1",
        "ok": True,
        "status": (
            "candidate_source_lock_ready_for_review"
            if source_lock_ready_for_review
            else "candidate_source_lock_incomplete"
        ),
        "model_authority": "candidate_source_lock_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_lock_ready_for_review": source_lock_ready_for_review,
        "missing_inputs": missing_inputs,
        "source_root": summary.get("source_root"),
        "upstream": upstream,
        "selected_model": {
            "relative_path": summary.get("model_relative_path"),
            "path": summary.get("model_path"),
            "sha256": summary.get("model_sha256_observed"),
            "supported": selected_model_supported,
            "status": summary.get("selected_model_status"),
            "observation": selected_observation,
        },
        "selectable_model_relative_paths": list(SELECTABLE_MODEL_RELATIVE_PATHS),
        "expected_file_count": expected_count,
        "present_expected_file_count": present_expected,
        "missing_expected_relative_paths": summary.get("missing_expected_relative_paths")
        or [],
        "file_digest_count": len(present_lockable_rows),
        "expected_file_digest_count": expected_digest_count,
        "extra_lockable_file_count": len(extra_lockable_relative_paths),
        "extra_lockable_relative_paths": extra_lockable_relative_paths[:200],
        "file_digests": present_lockable_rows,
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "review_handoff": {
            "candidate_direct_review_manifest_template_json": (
                summary.get("artifacts") or {}
            ).get("candidate_direct_review_manifest_template_json"),
            "candidate_review_checklist_json": (summary.get("artifacts") or {}).get(
                "candidate_review_checklist_json"
            ),
            "candidate_review_checklist_csv": (summary.get("artifacts") or {}).get(
                "candidate_review_checklist_csv"
            ),
            "manifest_checker_command_template": [
                "python",
                "scripts/smoke_sim_so101_model_bundle_manifest.py",
                "--manifest-path",
                "<reviewed-edited-copy-of-candidate_direct_review_manifest_template_json>",
                "--output-dir",
                "/private/tmp/lerobot_sim/so101_model_bundle_manifest_reviewed_candidate",
                "--python",
                "<python-executable>",
            ],
        },
        "next_required_action_ids": [
            "declare_vendor_or_external_intake_decision",
            "review_candidate_source_lock",
            "replace_candidate_template_placeholders_with_reviewed_values",
            "run_reviewed_bundle_manifest_checker",
        ],
        "limitations": [
            "This source lock records candidate file digests and upstream metadata only.",
            "A ready source lock is review handoff readiness, not physical SO-101 authority.",
            "Reviewed authority still requires edited manifest fields and a passing reviewed bundle manifest check.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a deterministic hardware-free intake/lock artifact for a local "
            "pinned SO-ARM100 Simulation/SO101 candidate checkout. This does not "
            "declare reviewed physical SO-101 authority."
        )
    )
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--upstream-repository-url", default=DEFAULT_REPOSITORY_URL)
    parser.add_argument("--upstream-source-tree-url", default=DEFAULT_SOURCE_TREE_URL)
    parser.add_argument("--upstream-commit", default=None)
    parser.add_argument("--model-relative-path", default=DEFAULT_MODEL_RELATIVE_PATH)
    parser.add_argument(
        "--operator-intake-decision",
        choices=INTAKE_DECISION_CHOICES,
        default=UNDECLARED_INTAKE_DECISION,
        help=(
            "Record the operator's candidate intake decision without promoting it "
            "to reviewed SO-101 authority."
        ),
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def relative_path_for(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def discover_lock_files(source_root: Path) -> list[Path]:
    if not source_root.exists() or not source_root.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in LOCKABLE_SUFFIXES:
            continue
        paths.append(path)
    return paths


def build_file_rows(source_root: Path) -> list[dict[str, Any]]:
    expected = set(EXPECTED_RELATIVE_PATHS)
    rows: list[dict[str, Any]] = []
    discovered = {
        relative_path_for(path, source_root): path for path in discover_lock_files(source_root)
    }
    for relative_path in sorted(expected | set(discovered)):
        path = source_root / relative_path
        exists = path.is_file()
        rows.append(
            {
                "relative_path": relative_path,
                "path": str(path),
                "exists": exists,
                "expected": relative_path in expected,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size if exists else None,
                "sha256": sha256_file(path) if exists else None,
            }
        )
    return rows


def read_text_or_empty(path: Path, limit_bytes: int = 512_000) -> str:
    try:
        return path.read_text(errors="replace")[:limit_bytes]
    except OSError:
        return ""


def detect_readme_caveats(readme_text: str) -> dict[str, Any]:
    text = readme_text.lower()
    caveats = {
        "onshape_to_robot_generated": "onshape-to-robot" in text,
        "relative_mesh_paths_declared": "relative" in text and "mesh" in text,
        "base_collision_meshes_removed": "base collision" in text and "removed" in text,
        "gripper_linear_joint_mapping_not_reflected": (
            "linear" in text
            and "joint" in text
            and "mapping" in text
            and "not" in text
            and ("reflected" in text or "implemented" in text)
        ),
    }
    caveats["review_required"] = any(caveats.values())
    caveats["required_follow_up_scopes"] = [
        scope
        for scope, present in (
            ("provenance", caveats["onshape_to_robot_generated"]),
            ("mesh_assets", caveats["relative_mesh_paths_declared"]),
            ("collision_policy", caveats["base_collision_meshes_removed"]),
            ("gripper_mapping", caveats["gripper_linear_joint_mapping_not_reflected"]),
        )
        if present
    ]
    return caveats


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def xml_model_observation(path: Path, source_root: Path) -> dict[str, Any]:
    relative_path = relative_path_for(path, source_root)
    observation: dict[str, Any] = {
        "relative_path": relative_path,
        "path": str(path),
        "exists": path.is_file(),
        "parse_ok": False,
        "parse_error": None,
        "root_tag": None,
        "model_name": None,
        "joint_count": 0,
        "joint_names": [],
        "joint_limit_or_range_count": 0,
        "mesh_reference_count": 0,
        "mesh_references": [],
    }
    if not path.is_file():
        return observation
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        observation["parse_error"] = f"{type(exc).__name__}: {exc}"
        return observation

    root_tag = local_name(root.tag)
    observation["parse_ok"] = True
    observation["root_tag"] = root_tag
    observation["model_name"] = root.attrib.get("name") or root.attrib.get("model")

    joint_names: list[str] = []
    joint_limit_or_range_count = 0
    mesh_references: list[str] = []
    for element in root.iter():
        tag = local_name(element.tag)
        if tag == "joint":
            name = element.attrib.get("name")
            if name:
                joint_names.append(name)
            if element.attrib.get("range") or any(
                local_name(child.tag) == "limit" for child in list(element)
            ):
                joint_limit_or_range_count += 1
        if tag == "mesh":
            filename = (
                element.attrib.get("filename")
                or element.attrib.get("file")
                or element.attrib.get("name")
            )
            if filename:
                mesh_references.append(filename)
        if tag == "geom" and element.attrib.get("mesh"):
            mesh_references.append(str(element.attrib["mesh"]))

    observation["joint_count"] = len(joint_names)
    observation["joint_names"] = joint_names
    observation["joint_limit_or_range_count"] = joint_limit_or_range_count
    observation["mesh_reference_count"] = len(mesh_references)
    observation["mesh_references"] = mesh_references[:200]
    return observation


def build_candidate_review_observations(source_root: Path | None) -> dict[str, Any]:
    if source_root is None or not source_root.is_dir():
        return {
            "model_authority": "candidate_review_observations_not_authority",
            "observed_evidence_is_physical_so101_authority": False,
            "ready_for_model_backed_ik": False,
            "readme_present": False,
            "readme_caveats": {},
            "model_file_observations": [],
            "model_file_count": 0,
            "parsed_model_file_count": 0,
            "review_required_action_ids": [
                "supply_pinned_public_candidate_source_root",
            ],
        }

    readme_path = source_root / "README.md"
    readme_text = read_text_or_empty(readme_path)
    model_observations = [
        xml_model_observation(source_root / relative_path, source_root)
        for relative_path in MODEL_RELATIVE_PATHS
    ]
    parsed_count = sum(1 for item in model_observations if item.get("parse_ok") is True)
    readme_caveats = detect_readme_caveats(readme_text)
    review_required_action_ids = [
        "review_upstream_readme_caveats",
        "review_model_file_variants_and_select_authoritative_model",
        "review_gripper_linear_joint_mapping",
        "review_base_collision_mesh_policy",
        "review_joint_limits_against_physical_so101",
        "review_mesh_references_and_digests",
    ]
    return {
        "model_authority": "candidate_review_observations_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "readme_present": readme_path.is_file(),
        "readme_caveats": readme_caveats,
        "model_file_observations": model_observations,
        "model_file_count": len(model_observations),
        "parsed_model_file_count": parsed_count,
        "review_required_action_ids": review_required_action_ids,
        "limitations": [
            "XML/URDF parsing records review metadata only; it does not validate physical SO-101 correctness.",
            "Detected README caveats keep gripper mapping and collision policy as explicit review items.",
        ],
    }


def candidate_manifest_draft(
    *,
    source_root: Path | None,
    model_path: Path | None,
    model_sha256: str | None,
    upstream_repository_url: str,
    upstream_source_tree_url: str,
    upstream_commit: str | None,
) -> dict[str, Any]:
    return {
        "schema": "lerobot.sim.so101_public_candidate_manifest_draft.v1",
        "model_path": str(model_path) if model_path is not None else None,
        "model_sha256_observed": model_sha256,
        "asset_roots": [str(source_root)] if source_root is not None else [],
        "upstream": {
            "repository_url": upstream_repository_url,
            "source_tree_url": upstream_source_tree_url,
            "commit": upstream_commit,
        },
        "authority": {},
        "provenance": {},
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "ready_for_model_backed_ik": False,
        "observed_evidence_is_physical_so101_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "notes": [
            "This draft records observed intake data only; it is not a reviewed model bundle manifest.",
            "Copy model_sha256_observed into a reviewed bundle manifest only after model identity and source authority are reviewed.",
            "TCP offset, target-frame authority, joint-limit authority, mesh authority, and base-to-board alignment are intentionally not inferred here.",
        ],
    }


def candidate_seeded_review_manifest_template(
    *,
    source_root: Path | None,
    model_path: Path | None,
    model_sha256: str | None,
    upstream_repository_url: str,
    upstream_source_tree_url: str,
    upstream_commit: str | None,
    candidate_review_observations: dict[str, Any],
    file_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    source_reference_parts = [
        upstream_source_tree_url,
        f"commit:{upstream_commit}" if upstream_commit else "commit:<pin-required>",
    ]
    present_lockable_rows = [
        row
        for row in file_rows
        if isinstance(row, dict) and row.get("exists") is True and row.get("sha256")
    ]
    expected_digest_count = sum(
        1 for row in present_lockable_rows if row.get("expected") is True
    )
    extra_lockable_relative_paths = [
        str(row.get("relative_path"))
        for row in present_lockable_rows
        if row.get("expected") is not True and row.get("relative_path")
    ]
    candidate_source_lock_digest_handoff = {
        "digest_row_count": len(present_lockable_rows),
        "expected_file_digest_count": expected_digest_count,
        "extra_lockable_file_count": len(extra_lockable_relative_paths),
        "extra_lockable_relative_paths": extra_lockable_relative_paths[:200],
        "authority_boundary": "candidate_source_lock_digest_not_authority",
        "review_instruction": (
            "Use these observed candidate digests only as review handoff. "
            "Reviewed mesh/file authority must be recorded in reviewed manifest "
            "fields after reviewer acceptance."
        ),
    }
    return {
        "schema": "lerobot.sim.so101_public_candidate_seeded_review_manifest_template.v1",
        "ok": True,
        "status": "candidate_seeded_template_waiting_for_review",
        "model_authority": "candidate_seeded_review_manifest_template_not_authority",
        "ready_for_model_backed_ik": False,
        "physical_so101_model_authority_ready": False,
        "observed_evidence_is_physical_so101_authority": False,
        "physical_so101_truth_claimed": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "source_root": str(source_root) if source_root is not None else None,
        "observed_inputs": {
            "model_path": str(model_path) if model_path is not None else None,
            "model_sha256_observed": model_sha256,
            "asset_roots": [str(source_root)] if source_root is not None else [],
            "upstream": {
                "repository_url": upstream_repository_url,
                "source_tree_url": upstream_source_tree_url,
                "commit": upstream_commit,
            },
            "candidate_source_lock_digest_handoff": (
                candidate_source_lock_digest_handoff
            ),
            "candidate_review_observations": candidate_review_observations,
        },
        "manifest_template": {
            "model_path": str(model_path) if model_path is not None else "<reviewed-so101-model.urdf-or-mjcf>",
            "model_sha256": "<copy-reviewed-sha256-after-review>",
            "asset_roots": [str(source_root)] if source_root is not None else ["<reviewed-mesh-or-asset-root>"],
            "candidate_source_lock_digest_handoff": (
                candidate_source_lock_digest_handoff
            ),
            "authority": {
                "source_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-review-ticket-commit-or-artifact-id>",
                "review_scopes": ["model_identity", "provenance", "license"],
            },
            "provenance": {
                "source_reference": " ".join(source_reference_parts),
                "export_tool": "<review-onshape-to-robot-version-and-any-manual-edits>",
                "license_basis": "<reviewed-license-file-url-or-record>",
            },
            "target_frame": EXPECTED_TARGET_FRAME,
            "target_frame_authority": {
                "target_frame_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-target-frame-review-artifact-id>",
                "review_scope": "target_frame",
                "source": "<reviewed-target-frame-or-tcp-reference-record>",
            },
            "joint_limits_deg": {
                joint: ["<lower-deg-or-mm>", "<upper-deg-or-mm>"]
                for joint in EXPECTED_SO101_JOINTS
            },
            "joint_limit_authority": {
                "joint_limit_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-joint-limit-review-artifact-id>",
                "review_scope": "joint_limits",
                "source": "<reviewed-joint-limit-record>",
            },
            "gripper_mapping_authority": {
                "gripper_mapping_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-gripper-mapping-review-artifact-id>",
                "review_scope": "gripper_mapping",
                "source": "<reviewed-gripper-linear-joint-mapping-record>",
            },
            "mesh_asset_authority": {
                "mesh_asset_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-mesh-asset-review-artifact-id>",
                "review_scope": "mesh_assets",
                "source": "<reviewed-model-export-or-mesh-root-record>",
            },
            "collision_policy_authority": {
                "collision_policy_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-collision-policy-review-artifact-id>",
                "review_scope": "collision_policy",
                "source": "<reviewed-base-collision-mesh-policy-record>",
            },
            "tcp_offset_m": {"x": "<meters>", "y": "<meters>", "z": "<meters>"},
            "tcp_offset_authority": {
                "tcp_offset_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-tcp-offset-review-artifact-id>",
                "review_scope": "tcp_offset",
                "source": "<reviewed-tcp-or-gripper-tip-calibration-record>",
            },
            "base_to_board_transform": {
                "translation_m": {"x": "<meters>", "y": "<meters>", "z": "<meters>"},
                "rotation_rpy_rad": {
                    "roll": "<radians>",
                    "pitch": "<radians>",
                    "yaw": "<radians>",
                },
            },
            "base_to_board_alignment_authority": {
                "base_to_board_alignment_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-base-board-review-artifact-id>",
                "review_scope": "base_to_board_alignment",
                "source": "<reviewed-board-registration-or-calibration-record>",
            },
        },
        "copy_rules": [
            "Do not copy model_sha256_observed into model_sha256 until the model identity and source authority review accepts that exact file.",
            "Do not copy candidate_source_lock_digest_handoff into mesh_asset_authority until every expected and extra lockable file digest retained for the bundle has been reviewed.",
            "Do not treat candidate README caveats or parsed XML/URDF metadata as physical SO-101 truth.",
            "Replace every placeholder authority/provenance/TCP/base-board value before running the manifest checker as a reviewed bundle.",
        ],
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "next_required_action_ids": [
            "review_candidate_seeded_manifest_template",
            "replace_candidate_observations_with_reviewed_manifest_fields",
            "run_so101_model_bundle_manifest_checker",
            "require_physical_so101_model_authority_ready",
        ],
    }


def checklist_status(ready: bool, blocked: bool = False) -> str:
    if blocked:
        return "blocked"
    return "candidate_observed_needs_review" if ready else "missing_candidate_input"


def build_candidate_review_checklist(summary: dict[str, Any]) -> dict[str, Any]:
    observations = summary.get("candidate_review_observations")
    observations = observations if isinstance(observations, dict) else {}
    caveats = observations.get("readme_caveats")
    caveats = caveats if isinstance(caveats, dict) else {}
    parsed_model_file_count = int(observations.get("parsed_model_file_count") or 0)
    model_present = summary.get("model_present") is True
    selected_model_supported = summary.get("selected_model_supported") is True
    upstream = summary.get("upstream")
    upstream = upstream if isinstance(upstream, dict) else {}
    commit_supplied = bool(upstream.get("commit_supplied"))
    commit_sha_valid = upstream.get("commit_sha_valid") is True
    model_sha = summary.get("model_sha256_observed")
    missing_expected = summary.get("missing_expected_relative_paths")
    missing_expected = missing_expected if isinstance(missing_expected, list) else []
    present_expected = int(summary.get("present_expected_file_count") or 0)
    expected_count = int(summary.get("expected_file_count") or 0)
    complete_expected = expected_count > 0 and present_expected == expected_count

    rows = [
        {
            "priority": 1,
            "action_id": "pin_upstream_soarm100_commit",
            "gate": "reviewed_model_authority",
            "status": checklist_status(commit_sha_valid),
            "title": "Pin the SO-ARM100 upstream commit SHA",
            "detail": "Record the immutable 40-character upstream commit SHA used for candidate review.",
            "candidate_observation": {
                "commit": upstream.get("commit"),
                "commit_supplied": commit_supplied,
                "commit_sha_valid": commit_sha_valid,
                "commit_status": upstream.get("commit_status"),
            },
            "required_review_scope": "provenance",
            "manifest_fields": ["provenance.source_reference"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 2,
            "action_id": "lock_candidate_file_digests",
            "gate": "reviewed_model_authority",
            "status": checklist_status(complete_expected),
            "title": "Lock expected candidate file digests",
            "detail": "Review all expected SO101 files and missing-path diagnostics before selecting the bundle.",
            "candidate_observation": {
                "present_expected_file_count": present_expected,
                "expected_file_count": expected_count,
                "missing_expected_relative_paths": missing_expected,
            },
            "required_review_scope": "mesh_assets",
            "manifest_fields": [
                "asset_roots",
                "mesh_asset_authority",
                "collision_policy_authority",
            ],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 3,
            "action_id": "select_single_authoritative_model_variant",
            "gate": "reviewed_model_authority",
            "status": checklist_status(
                model_present and bool(model_sha) and selected_model_supported
            ),
            "title": "Select one SO-101 model variant",
            "detail": "Choose the reviewed new/old calibration URDF or MJCF file and reject other variants for this manifest.",
            "candidate_observation": {
                "model_path": summary.get("model_path"),
                "selected_model_supported": selected_model_supported,
                "selected_model_status": summary.get("selected_model_status"),
                "selectable_model_relative_paths": summary.get(
                    "selectable_model_relative_paths"
                ),
                "model_sha256_observed": model_sha,
                "parsed_model_file_count": parsed_model_file_count,
            },
            "required_review_scope": "model_identity",
            "manifest_fields": ["model_path", "model_sha256"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 4,
            "action_id": "review_source_license_and_export_provenance",
            "gate": "reviewed_model_authority",
            "status": checklist_status(caveats.get("onshape_to_robot_generated") is True),
            "title": "Review source, license, and export provenance",
            "detail": "Review upstream source, license basis, onshape-to-robot generation, and any manual edits.",
            "candidate_observation": {
                "repository_url": upstream.get("repository_url"),
                "source_tree_url": upstream.get("source_tree_url"),
                "onshape_to_robot_generated": caveats.get("onshape_to_robot_generated"),
            },
            "required_review_scope": "provenance,license",
            "manifest_fields": ["authority", "provenance"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 5,
            "action_id": "review_mesh_paths",
            "gate": "reviewed_model_authority",
            "status": checklist_status(
                caveats.get("relative_mesh_paths_declared") is True
            ),
            "title": "Review mesh paths and digest coverage",
            "detail": "Confirm relative mesh paths, asset roots, and digest coverage for the selected SO-101 bundle.",
            "candidate_observation": {
                "relative_mesh_paths_declared": caveats.get("relative_mesh_paths_declared"),
            },
            "required_review_scope": "mesh_assets",
            "manifest_fields": ["asset_roots", "mesh_asset_authority"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 6,
            "action_id": "review_collision_policy",
            "gate": "reviewed_model_authority",
            "status": checklist_status(
                caveats.get("base_collision_meshes_removed") is True
            ),
            "title": "Review collision policy",
            "detail": "Resolve the removed base collision mesh caveat and record the accepted MuJoCo collision policy.",
            "candidate_observation": {
                "base_collision_meshes_removed": caveats.get("base_collision_meshes_removed"),
            },
            "required_review_scope": "collision_policy",
            "manifest_fields": ["collision_policy_authority"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 7,
            "action_id": "review_joint_limits",
            "gate": "reviewed_model_authority",
            "status": checklist_status(parsed_model_file_count > 0),
            "title": "Review joint limits",
            "detail": "Compare parsed joint/range metadata with reviewed physical SO-101 limits.",
            "candidate_observation": {
                "parsed_model_file_count": parsed_model_file_count,
            },
            "required_review_scope": "joint_limits",
            "manifest_fields": [
                "joint_limits_deg",
                "joint_limit_authority",
            ],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 8,
            "action_id": "review_gripper_mapping",
            "gate": "reviewed_model_authority",
            "status": checklist_status(
                caveats.get("gripper_linear_joint_mapping_not_reflected") is True
            ),
            "title": "Review gripper mapping",
            "detail": "Resolve the LeRobot gripper linear-joint mapping caveat before trusting model-backed gripper motion.",
            "candidate_observation": {
                "gripper_linear_joint_mapping_not_reflected": caveats.get(
                    "gripper_linear_joint_mapping_not_reflected"
                ),
            },
            "required_review_scope": "gripper_mapping",
            "manifest_fields": ["gripper_mapping_authority"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 9,
            "action_id": "review_target_frame_authority",
            "gate": "reviewed_model_authority",
            "status": "missing_review_input",
            "title": "Review target frame authority",
            "detail": "Record the reviewed target frame for the selected SO-101 model; do not infer it from the public candidate alone.",
            "candidate_observation": {
                "expected_target_frame": EXPECTED_TARGET_FRAME,
                "candidate_target_frame_needs_review": True,
            },
            "required_review_scope": "target_frame",
            "manifest_fields": [
                "target_frame",
                "target_frame_authority",
            ],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 10,
            "action_id": "review_tcp_offset_authority",
            "gate": "reviewed_model_authority",
            "status": "missing_review_input",
            "title": "Review TCP/gripper offset authority",
            "detail": "Record the calibrated TCP or gripper-tip offset for the selected SO-101 model; the public candidate does not provide physical TCP truth.",
            "candidate_observation": {
                "candidate_does_not_calibrate_tcp": True,
                "expected_target_frame": EXPECTED_TARGET_FRAME,
            },
            "required_review_scope": "tcp_offset",
            "manifest_fields": [
                "tcp_offset_m",
                "tcp_offset_authority",
            ],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 11,
            "action_id": "review_base_to_board_alignment_authority",
            "gate": "reviewed_model_authority",
            "status": "missing_review_input",
            "title": "Review base-to-board alignment authority",
            "detail": "Record the reviewed base-to-board transform for the chess task; do not infer board alignment from the public robot model.",
            "candidate_observation": {
                "candidate_does_not_calibrate_board_alignment": True,
            },
            "required_review_scope": "base_to_board_alignment",
            "manifest_fields": [
                "base_to_board_transform",
                "base_to_board_alignment_authority",
            ],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
        {
            "priority": 12,
            "action_id": "rerun_reviewed_bundle_manifest_checker",
            "gate": "reviewed_model_authority",
            "status": "blocked",
            "title": "Rerun the reviewed bundle manifest checker",
            "detail": "After replacing placeholders with reviewed fields, run the manifest checker and require physical SO-101 authority readiness.",
            "candidate_observation": {
                "seeded_template_model_authority": summary.get(
                    "candidate_seeded_review_manifest_template_model_authority"
                ),
                "ready_for_model_backed_ik": False,
            },
            "required_review_scope": ",".join(REQUIRED_REVIEW_SCOPES),
            "manifest_fields": ["<reviewed-manifest>"],
            "authority_boundary": "candidate_review_checklist_not_authority",
        },
    ]
    action_ids_by_scope: dict[str, list[str]] = {}
    direct_action_ids_by_scope: dict[str, list[str]] = {}
    for row in rows:
        action_id = str(row["action_id"])
        raw_scopes = str(row.get("required_review_scope") or "")
        for scope in raw_scopes.split(","):
            scope = scope.strip()
            if scope:
                action_ids_by_scope.setdefault(scope, []).append(action_id)
                if action_id != "rerun_reviewed_bundle_manifest_checker":
                    direct_action_ids_by_scope.setdefault(scope, []).append(action_id)
    missing_required_scopes = [
        scope for scope in REQUIRED_REVIEW_SCOPES if scope not in action_ids_by_scope
    ]
    return {
        "schema": "lerobot.sim.so101_public_candidate_review_checklist.v1",
        "ok": True,
        "status": "candidate_review_required",
        "model_authority": "candidate_review_checklist_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "row_count": len(rows),
        "action_ids": [str(row["action_id"]) for row in rows],
        "required_review_scopes": list(REQUIRED_REVIEW_SCOPES),
        "action_ids_by_required_review_scope": action_ids_by_scope,
        "direct_action_ids_by_required_review_scope": direct_action_ids_by_scope,
        "missing_required_review_scope_ids": missing_required_scopes,
        "required_review_scope_coverage_ready": not missing_required_scopes,
        "rows": rows,
    }


def build_summary(args: argparse.Namespace, artifacts: dict[str, str]) -> dict[str, Any]:
    source_root = normalize_path(args.source_root) if args.source_root else None
    source_root_supplied = source_root is not None
    source_root_exists = bool(source_root and source_root.exists())
    source_root_is_dir = bool(source_root and source_root.is_dir())
    file_rows = build_file_rows(source_root) if source_root_is_dir and source_root else []
    missing_expected = [
        row["relative_path"]
        for row in file_rows
        if row.get("expected") is True and row.get("exists") is not True
    ]
    model_path = (
        source_root / args.model_relative_path
        if source_root is not None and args.model_relative_path
        else None
    )
    model_row = next(
        (
            row
            for row in file_rows
            if row.get("relative_path") == args.model_relative_path
        ),
        None,
    )
    model_present = bool(model_row and model_row.get("exists") is True)
    selected_model_supported = (
        args.model_relative_path in SELECTABLE_MODEL_RELATIVE_PATHS
    )
    if not args.model_relative_path:
        selected_model_status = "selected_model_not_supplied"
    elif not model_present:
        selected_model_status = "selected_model_missing"
    elif selected_model_supported:
        selected_model_status = "selectable_so101_model_selected"
    else:
        selected_model_status = "selected_model_not_supported"
    selected_model_ready_for_template = model_present and selected_model_supported
    model_sha256 = str(model_row.get("sha256")) if model_present and model_row else None
    upstream_commit_value = str(args.upstream_commit or "").strip()
    upstream_commit_supplied = bool(upstream_commit_value)
    upstream_commit_sha_valid = is_full_git_commit_sha(upstream_commit_value)
    if not upstream_commit_supplied:
        upstream_commit_status = "upstream_commit_not_supplied"
    elif upstream_commit_sha_valid:
        upstream_commit_status = "upstream_commit_sha_pinned"
    else:
        upstream_commit_status = "upstream_commit_not_immutable_sha"
    candidate_review_observations = build_candidate_review_observations(
        source_root if source_root_is_dir else None
    )
    seeded_review_manifest_template = candidate_seeded_review_manifest_template(
        source_root=source_root if source_root_is_dir else None,
        model_path=model_path if selected_model_ready_for_template else None,
        model_sha256=model_sha256 if selected_model_ready_for_template else None,
        upstream_repository_url=args.upstream_repository_url,
        upstream_source_tree_url=args.upstream_source_tree_url,
        upstream_commit=args.upstream_commit,
        candidate_review_observations=candidate_review_observations,
        file_rows=file_rows,
    )

    if not source_root_supplied:
        status = "source_root_not_supplied"
    elif not source_root_exists:
        status = "source_root_unavailable"
    elif not source_root_is_dir:
        status = "source_root_not_directory"
    elif missing_expected or not model_present:
        status = "candidate_intake_incomplete"
    elif not selected_model_supported:
        status = "candidate_intake_model_selection_invalid"
    else:
        status = "candidate_intake_checked"

    next_required_action_ids = [
        "pin_upstream_soarm100_commit",
        "declare_vendor_or_external_intake_decision",
        "review_soarm100_license_and_provenance",
        "declare_single_authoritative_so101_model_path",
        "run_so101_model_bundle_probe",
        "author_review_model_digest_and_mesh_assets",
        "record_reviewed_tcp_and_base_to_board_alignment",
        "supply_reviewed_so101_model_bundle_manifest",
    ]
    if upstream_commit_sha_valid:
        next_required_action_ids = [
            action_id
            for action_id in next_required_action_ids
            if action_id != "pin_upstream_soarm100_commit"
        ]

    return {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "model_authority": "public_candidate_intake_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "network_skipped": True,
        "upstream": {
            "repository_url": args.upstream_repository_url,
            "source_tree_url": args.upstream_source_tree_url,
            "commit": args.upstream_commit,
            "commit_supplied": upstream_commit_supplied,
            "commit_sha_valid": upstream_commit_sha_valid,
            "commit_status": upstream_commit_status,
        },
        "operator_intake_decision": args.operator_intake_decision,
        "source_root": str(source_root) if source_root else None,
        "source_root_supplied": source_root_supplied,
        "source_root_exists": source_root_exists,
        "source_root_is_dir": source_root_is_dir,
        "expected_relative_paths": list(EXPECTED_RELATIVE_PATHS),
        "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
        "discovered_file_count": len(file_rows),
        "present_expected_file_count": sum(
            1 for row in file_rows if row.get("expected") and row.get("exists")
        ),
        "missing_expected_relative_paths": missing_expected,
        "model_relative_path": args.model_relative_path,
        "selectable_model_relative_paths": list(SELECTABLE_MODEL_RELATIVE_PATHS),
        "selected_model_supported": selected_model_supported,
        "selected_model_status": selected_model_status,
        "model_path": str(model_path) if model_path else None,
        "model_present": model_present,
        "model_sha256_observed": model_sha256,
        "candidate_manifest_draft": candidate_manifest_draft(
            source_root=source_root if source_root_is_dir else None,
            model_path=model_path if selected_model_ready_for_template else None,
            model_sha256=model_sha256 if selected_model_ready_for_template else None,
            upstream_repository_url=args.upstream_repository_url,
            upstream_source_tree_url=args.upstream_source_tree_url,
            upstream_commit=args.upstream_commit,
        ),
        "candidate_review_observations_model_authority": candidate_review_observations[
            "model_authority"
        ],
        "candidate_review_observations": candidate_review_observations,
        "candidate_seeded_review_manifest_template_model_authority": (
            seeded_review_manifest_template["model_authority"]
        ),
        "candidate_seeded_review_manifest_template": seeded_review_manifest_template,
        "file_rows": file_rows,
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "next_required_action_ids": next_required_action_ids,
        "artifacts": artifacts,
        "limitations": [
            "This smoke reads a local checkout only; it does not clone, fetch, or verify remote Git state.",
            "Observed file digests are lock evidence for review, not reviewed physical SO-101 authority.",
            "The gripper mapping, TCP offset, collision policy, and base-to-board alignment still require separate review.",
        ],
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Public Candidate Intake",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `model_authority`: `{summary['model_authority']}`",
        f"- `observed_evidence_is_physical_so101_authority`: `{str(summary['observed_evidence_is_physical_so101_authority']).lower()}`",
        f"- `ready_for_model_backed_ik`: `{str(summary['ready_for_model_backed_ik']).lower()}`",
        f"- `source_root`: `{summary.get('source_root') or 'none'}`",
        f"- `upstream_commit`: `{summary['upstream'].get('commit') or 'not supplied'}`",
        f"- `upstream_commit_status`: `{summary['upstream'].get('commit_status')}`",
        f"- `upstream_commit_sha_valid`: `{str(summary['upstream'].get('commit_sha_valid')).lower()}`",
        f"- `model_relative_path`: `{summary['model_relative_path']}`",
        f"- `selected_model_status`: `{summary['selected_model_status']}`",
        f"- `selected_model_supported`: `{str(summary['selected_model_supported']).lower()}`",
        f"- `model_sha256_observed`: `{summary.get('model_sha256_observed') or 'none'}`",
        f"- `candidate_review_observations_model_authority`: `{summary['candidate_review_observations_model_authority']}`",
        f"- `candidate_review_observations_ready_for_model_backed_ik`: `{str(summary['candidate_review_observations']['ready_for_model_backed_ik']).lower()}`",
        f"- `candidate_model_observation_model_authority`: `{summary['candidate_model_observation_model_authority']}`",
        f"- `candidate_model_observation_row_count`: `{summary['candidate_model_observation_row_count']}`",
        f"- `candidate_model_observation_scene_row_count`: `{summary['candidate_model_observation_scene_row_count']}`",
        f"- `candidate_model_observation_selectable_model_row_count`: `{summary['candidate_model_observation_selectable_model_row_count']}`",
        f"- `candidate_model_observation_parsed_selectable_model_row_count`: `{summary['candidate_model_observation_parsed_selectable_model_row_count']}`",
        f"- `candidate_model_observation_selected_model_row_count`: `{summary['candidate_model_observation_selected_model_row_count']}`",
        f"- `candidate_source_lock_model_authority`: `{summary['candidate_source_lock_model_authority']}`",
        f"- `candidate_source_lock_status`: `{summary['candidate_source_lock']['status']}`",
        f"- `candidate_source_lock_ready_for_review`: `{str(summary['candidate_source_lock']['source_lock_ready_for_review']).lower()}`",
        f"- `candidate_source_lock_digest_model_authority`: `{summary['candidate_source_lock_digest_model_authority']}`",
        f"- `candidate_source_lock_digest_row_count`: `{summary['candidate_source_lock_digest_row_count']}`",
        f"- `candidate_source_lock_expected_file_digest_count`: `{summary['candidate_source_lock_expected_file_digest_count']}`",
        f"- `candidate_source_lock_extra_lockable_file_count`: `{summary['candidate_source_lock_extra_lockable_file_count']}`",
        f"- `candidate_source_lock_extra_lockable_relative_paths`: `{', '.join(summary['candidate_source_lock_extra_lockable_relative_paths']) if summary['candidate_source_lock_extra_lockable_relative_paths'] else 'none'}`",
        f"- `candidate_operator_intake_plan_model_authority`: `{summary['candidate_operator_intake_plan_model_authority']}`",
        f"- `candidate_operator_intake_plan_status`: `{summary['candidate_operator_intake_plan_status']}`",
        f"- `candidate_operator_intake_decision_status`: `{summary['candidate_operator_intake_decision_status']}`",
        f"- `candidate_operator_intake_selected_option`: `{summary['candidate_operator_intake_plan'].get('selected_intake_option_id') or 'none'}`",
        f"- `candidate_operator_command_plan_model_authority`: `{summary['candidate_operator_command_plan_model_authority']}`",
        f"- `candidate_operator_command_plan_status`: `{summary['candidate_operator_command_plan_status']}`",
        f"- `candidate_reviewed_manifest_rerun_plan_model_authority`: `{summary['candidate_reviewed_manifest_rerun_plan_model_authority']}`",
        f"- `candidate_reviewed_manifest_rerun_plan_status`: `{summary['candidate_reviewed_manifest_rerun_plan_status']}`",
        f"- `candidate_reviewed_manifest_rerun_plan_selected_option`: `{summary['candidate_reviewed_manifest_rerun_plan'].get('selected_intake_option_id') or 'none'}`",
        f"- `candidate_operator_intake_handoff_model_authority`: `{summary['candidate_operator_intake_handoff_model_authority']}`",
        f"- `candidate_operator_intake_handoff_selected_option`: `{summary['candidate_operator_intake_handoff'].get('selected_intake_option_id') or 'none'}`",
        f"- `candidate_operator_intake_handoff_selected_requirement_ids`: `{', '.join(summary['candidate_operator_intake_handoff'].get('selected_option_review_requirement_ids') or []) if summary['candidate_operator_intake_handoff'].get('selected_option_review_requirement_ids') else 'none'}`",
        f"- `candidate_operator_intake_requirement_model_authority`: `{summary['candidate_operator_intake_requirement_model_authority']}`",
        f"- `candidate_operator_intake_requirement_row_count`: `{summary['candidate_operator_intake_requirement_row_count']}`",
        f"- `candidate_operator_intake_selected_requirement_row_count`: `{summary['candidate_operator_intake_selected_requirement_row_count']}`",
        f"- `candidate_seeded_review_manifest_template_model_authority`: `{summary['candidate_seeded_review_manifest_template_model_authority']}`",
        f"- `candidate_review_checklist_handoff_model_authority`: `{summary['candidate_review_checklist_handoff_model_authority']}`",
        f"- `candidate_review_checklist_handoff_scope_coverage_ready`: `{str(summary['candidate_review_checklist_handoff'].get('required_review_scope_coverage_ready')).lower()}`",
        f"- `candidate_review_checklist_handoff_gripper_mapping_direct_action_ids`: `{', '.join(summary['candidate_review_checklist_handoff'].get('gripper_mapping_direct_action_ids') or []) if summary['candidate_review_checklist_handoff'].get('gripper_mapping_direct_action_ids') else 'none'}`",
        f"- `candidate_review_checklist_handoff_collision_policy_direct_action_ids`: `{', '.join(summary['candidate_review_checklist_handoff'].get('collision_policy_direct_action_ids') or []) if summary['candidate_review_checklist_handoff'].get('collision_policy_direct_action_ids') else 'none'}`",
        f"- `candidate_operator_command_plan_selected_requirement_count`: `{summary['candidate_operator_command_plan'].get('selected_option_review_requirement_count')}`",
        f"- `candidate_operator_command_plan_selected_requirement_ids`: `{', '.join(summary['candidate_operator_command_plan'].get('selected_option_review_requirement_ids') or []) if summary['candidate_operator_command_plan'].get('selected_option_review_requirement_ids') else 'none'}`",
        f"- `candidate_operator_command_plan_review_handoff_artifact_count`: `{len(summary['candidate_operator_command_plan'].get('review_handoff_artifacts') or [])}`",
        f"- `parsed_model_file_count`: `{summary['candidate_review_observations']['parsed_model_file_count']}`",
        f"- `expected_file_count`: `{summary['expected_file_count']}`",
        f"- `present_expected_file_count`: `{summary['present_expected_file_count']}`",
        f"- `missing_expected_relative_paths`: `{', '.join(summary['missing_expected_relative_paths']) if summary['missing_expected_relative_paths'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `files_csv`: `{summary['artifacts']['files_csv']}`",
        f"- `candidate_source_lock_json`: `{summary['artifacts']['candidate_source_lock_json']}`",
        f"- `candidate_source_lock_digests_csv`: `{summary['artifacts']['candidate_source_lock_digests_csv']}`",
        f"- `candidate_model_file_observations_csv`: `{summary['artifacts']['candidate_model_file_observations_csv']}`",
        f"- `candidate_manifest_draft_json`: `{summary['artifacts']['candidate_manifest_draft_json']}`",
        f"- `candidate_seeded_review_manifest_template_json`: `{summary['artifacts']['candidate_seeded_review_manifest_template_json']}`",
        f"- `candidate_direct_review_manifest_template_json`: `{summary['artifacts']['candidate_direct_review_manifest_template_json']}`",
        f"- `candidate_review_checklist_json`: `{summary['artifacts']['candidate_review_checklist_json']}`",
        f"- `candidate_review_checklist_csv`: `{summary['artifacts']['candidate_review_checklist_csv']}`",
        f"- `candidate_operator_intake_plan_json`: `{summary['artifacts']['candidate_operator_intake_plan_json']}`",
        f"- `candidate_operator_command_plan_json`: `{summary['artifacts']['candidate_operator_command_plan_json']}`",
        f"- `candidate_reviewed_manifest_rerun_plan_json`: `{summary['artifacts']['candidate_reviewed_manifest_rerun_plan_json']}`",
        f"- `candidate_operator_intake_requirements_csv`: `{summary['artifacts']['candidate_operator_intake_requirements_csv']}`",
        "",
        "## Next Required Actions",
        "",
    ]
    for action_id in summary["next_required_action_ids"]:
        lines.append(f"- `{action_id}`")
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "This artifact is an intake lock for review. It does not declare reviewed physical SO-101 authority, model-backed IK readiness, or policy-training readiness.",
            "",
            "## Candidate Review Observations",
            "",
            "The `candidate_review_observations` section records README caveats and XML/URDF metadata for reviewer intake only. It is not reviewed physical SO-101 model authority.",
            "",
            "The `candidate_model_file_observations` CSV flattens parsed candidate URDF/MJCF/scene metadata and marks selectable model variants for review. It is not reviewed physical SO-101 model authority.",
            "",
            "## Candidate Source Lock",
            "",
            "The `candidate_source_lock` JSON records the pinned upstream, selected model, expected file digests, and discovered lockable extra file digests as review handoff evidence. It is not reviewed physical SO-101 model authority.",
            "",
            "The `candidate_source_lock_digests` CSV flattens expected candidate files plus discovered lockable extras, marks the selected model digest row, and labels non-expected rows for review. It is not reviewed physical SO-101 model authority.",
            "",
            "## Candidate Operator Intake Plan",
            "",
            "The `candidate_operator_intake_plan` JSON records the unresolved vendor-vs-external-source decision, required inputs, command templates, and review flow. It does not clone, vendor, copy, or promote assets to reviewed physical SO-101 authority.",
            "",
            "The `candidate_operator_command_plan` JSON records explicit clone/fetch/checkout/intake/checker command steps for a pinned upstream checkout or vendored subset. The commands are not executed by this smoke and remain non-authoritative.",
            "",
            "The command plan also carries selected review requirement IDs, handoff artifact paths, and authority blockers so reviewers can trace digest, license/provenance, manifest, and reviewed-MuJoCo prerequisites without treating the plan as authority.",
            "",
            "The `candidate_reviewed_manifest_rerun_plan` JSON is the machine-readable bridge from the selected candidate intake option to `scripts/smoke_sim_so101_model_bundle_manifest.py`. It records the reviewed-manifest placeholder path, command template, and success conditions while staying non-authoritative.",
            "",
            "The `candidate_operator_intake_handoff` is copied into the seeded and direct manifest templates to preserve the selected external-source or vendored-bundle intake path for review. It remains non-authoritative and must not be copied into reviewed authority fields.",
            "",
            "The `candidate_operator_intake_requirements` CSV flattens the external and vendored requirement rows for review tracking. Selected rows only reflect the recorded operator decision and remain non-authoritative.",
            "",
            "## Candidate-Seeded Reviewed Manifest Template",
            "",
            "The `candidate_seeded_review_manifest_template` artifact follows the reviewed bundle manifest shape but keeps placeholder authority fields and remains non-authoritative until a reviewer replaces observations with reviewed values and the manifest checker reports physical authority ready.",
            "",
            "The `candidate_direct_review_manifest_template_json` artifact contains only the nested manifest template object so a reviewer can edit that file directly and pass it to `scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path` after replacing placeholders.",
            "",
            "The direct manifest template also carries non-authoritative candidate digest, operator-intake, and checklist handoffs so reviewers can see the selected source path, digest coverage, and required review-scope coverage while replacing placeholders with reviewed fields.",
            "",
            "## Candidate Review Checklist",
            "",
            "The `candidate_review_checklist` JSON/CSV is the operator queue for replacing public-candidate observations with reviewed bundle-manifest fields. It is not model authority.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "so101_public_candidate_intake_summary.json"
    files_csv_path = output_dir / "so101_public_candidate_intake_files.csv"
    source_lock_path = output_dir / "so101_public_candidate_source_lock.json"
    source_lock_digests_csv_path = (
        output_dir / "so101_public_candidate_source_lock_digests.csv"
    )
    model_observations_csv_path = (
        output_dir / "so101_public_candidate_model_file_observations.csv"
    )
    draft_path = output_dir / "so101_public_candidate_manifest_draft.json"
    seeded_template_path = (
        output_dir / "so101_public_candidate_seeded_review_manifest_template.json"
    )
    direct_template_path = (
        output_dir / "so101_public_candidate_review_manifest_template.direct.json"
    )
    review_checklist_path = output_dir / "so101_public_candidate_review_checklist.json"
    review_checklist_csv_path = output_dir / "so101_public_candidate_review_checklist.csv"
    operator_plan_path = output_dir / "so101_public_candidate_operator_intake_plan.json"
    operator_command_plan_path = (
        output_dir / "so101_public_candidate_operator_command_plan.json"
    )
    reviewed_manifest_rerun_plan_path = (
        output_dir / "so101_public_candidate_reviewed_manifest_rerun_plan.json"
    )
    operator_requirements_csv_path = (
        output_dir / "so101_public_candidate_operator_intake_requirements.csv"
    )
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "files_csv": str(files_csv_path),
        "candidate_source_lock_json": str(source_lock_path),
        "candidate_source_lock_digests_csv": str(source_lock_digests_csv_path),
        "candidate_model_file_observations_csv": str(model_observations_csv_path),
        "candidate_manifest_draft_json": str(draft_path),
        "candidate_seeded_review_manifest_template_json": str(seeded_template_path),
        "candidate_direct_review_manifest_template_json": str(direct_template_path),
        "candidate_review_checklist_json": str(review_checklist_path),
        "candidate_review_checklist_csv": str(review_checklist_csv_path),
        "candidate_operator_intake_plan_json": str(operator_plan_path),
        "candidate_operator_command_plan_json": str(operator_command_plan_path),
        "candidate_reviewed_manifest_rerun_plan_json": str(
            reviewed_manifest_rerun_plan_path
        ),
        "candidate_operator_intake_requirements_csv": str(
            operator_requirements_csv_path
        ),
        "readme_md": str(readme_path),
    }
    summary = build_summary(args, artifacts)
    model_observation_rows = candidate_model_observation_rows(summary)
    selected_model_observation_rows = [
        row for row in model_observation_rows if row.get("selected_model") is True
    ]
    summary["candidate_model_observation_model_authority"] = (
        "candidate_model_observation_not_authority"
    )
    summary["candidate_model_observation_row_count"] = len(model_observation_rows)
    summary["candidate_model_observation_scene_row_count"] = sum(
        1 for row in model_observation_rows if row.get("relative_path") == "scene.xml"
    )
    summary["candidate_model_observation_selectable_model_row_count"] = sum(
        1 for row in model_observation_rows if row.get("selectable_model") is True
    )
    summary["candidate_model_observation_parsed_selectable_model_row_count"] = sum(
        1
        for row in model_observation_rows
        if row.get("selectable_model") is True and row.get("parse_ok") is True
    )
    summary["candidate_model_observation_selected_model_row_count"] = len(
        selected_model_observation_rows
    )
    source_lock = candidate_source_lock(summary)
    summary["candidate_source_lock_model_authority"] = source_lock["model_authority"]
    summary["candidate_source_lock"] = source_lock
    source_lock_digest_rows = candidate_source_lock_digest_rows(source_lock)
    selected_source_lock_digest_rows = [
        row for row in source_lock_digest_rows if row.get("selected_model") is True
    ]
    summary["candidate_source_lock_digest_model_authority"] = (
        "candidate_source_lock_digest_not_authority"
    )
    summary["candidate_source_lock_digest_row_count"] = len(source_lock_digest_rows)
    summary["candidate_source_lock_expected_file_digest_count"] = source_lock.get(
        "expected_file_digest_count"
    )
    summary["candidate_source_lock_extra_lockable_file_count"] = source_lock.get(
        "extra_lockable_file_count"
    )
    summary["candidate_source_lock_extra_lockable_relative_paths"] = source_lock.get(
        "extra_lockable_relative_paths"
    ) or []
    summary["candidate_source_lock_selected_model_digest_row_count"] = len(
        selected_source_lock_digest_rows
    )
    candidate_review_checklist = build_candidate_review_checklist(summary)
    summary["candidate_review_checklist_model_authority"] = candidate_review_checklist[
        "model_authority"
    ]
    summary["candidate_review_checklist"] = candidate_review_checklist
    review_checklist_handoff = attach_review_checklist_handoff_to_seeded_template(
        summary
    )
    operator_intake_plan = candidate_operator_intake_plan(summary)
    summary["candidate_operator_intake_plan_model_authority"] = operator_intake_plan[
        "model_authority"
    ]
    summary["candidate_operator_intake_plan_status"] = operator_intake_plan["status"]
    summary["candidate_operator_intake_decision_status"] = operator_intake_plan[
        "decision_status"
    ]
    summary["candidate_operator_intake_plan"] = operator_intake_plan
    operator_command_plan = candidate_operator_command_plan(summary)
    summary["candidate_operator_command_plan_model_authority"] = (
        operator_command_plan["model_authority"]
    )
    summary["candidate_operator_command_plan_status"] = operator_command_plan["status"]
    summary["candidate_operator_command_plan"] = operator_command_plan
    operator_intake_handoff = attach_operator_intake_handoff_to_seeded_template(
        summary
    )
    reviewed_manifest_rerun_plan = candidate_reviewed_manifest_rerun_plan(summary)
    summary["candidate_reviewed_manifest_rerun_plan"] = (
        reviewed_manifest_rerun_plan
    )
    summary["candidate_reviewed_manifest_rerun_plan_model_authority"] = (
        reviewed_manifest_rerun_plan["model_authority"]
    )
    summary["candidate_reviewed_manifest_rerun_plan_status"] = (
        reviewed_manifest_rerun_plan["status"]
    )
    operator_requirement_rows = candidate_operator_intake_requirement_rows(
        operator_intake_plan
    )
    selected_operator_requirement_rows = [
        row for row in operator_requirement_rows if row.get("selected") is True
    ]
    summary["candidate_operator_intake_requirement_model_authority"] = (
        "candidate_operator_intake_requirement_not_authority"
    )
    summary["candidate_operator_intake_requirement_row_count"] = len(
        operator_requirement_rows
    )
    summary["candidate_operator_intake_selected_requirement_row_count"] = len(
        selected_operator_requirement_rows
    )
    summary["candidate_operator_intake_unselected_requirement_row_count"] = (
        len(operator_requirement_rows) - len(selected_operator_requirement_rows)
    )
    summary["candidate_operator_intake_selected_requirement_row_ids"] = [
        str(row["requirement_id"])
        for row in selected_operator_requirement_rows
        if row.get("requirement_id")
    ]
    write_json(summary_path, summary)
    write_csv(
        model_observations_csv_path,
        model_observation_rows,
        MODEL_OBSERVATION_FIELDNAMES,
    )
    write_json(source_lock_path, source_lock)
    write_csv(
        source_lock_digests_csv_path,
        source_lock_digest_rows,
        SOURCE_LOCK_DIGEST_FIELDNAMES,
    )
    write_json(draft_path, summary["candidate_manifest_draft"])
    write_json(
        seeded_template_path,
        summary["candidate_seeded_review_manifest_template"],
    )
    write_json(
        direct_template_path,
        summary["candidate_seeded_review_manifest_template"]["manifest_template"],
    )
    write_json(review_checklist_path, candidate_review_checklist)
    write_json(operator_plan_path, operator_intake_plan)
    write_json(operator_command_plan_path, operator_command_plan)
    write_json(reviewed_manifest_rerun_plan_path, reviewed_manifest_rerun_plan)
    write_csv(
        operator_requirements_csv_path,
        operator_requirement_rows,
        OPERATOR_REQUIREMENT_FIELDNAMES,
    )
    write_csv(
        review_checklist_csv_path,
        candidate_review_checklist["rows"],
        REVIEW_CHECKLIST_FIELDNAMES,
    )
    write_csv(
        files_csv_path,
        summary["file_rows"],
        (
            "relative_path",
            "path",
            "exists",
            "expected",
            "suffix",
            "size_bytes",
            "sha256",
        ),
    )
    write_markdown(readme_path, summary)
    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "model_authority": summary["model_authority"],
                "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
                "source_root": summary["source_root"],
                "upstream_commit": summary["upstream"]["commit"],
                "model_relative_path": summary["model_relative_path"],
                "model_present": summary["model_present"],
                "model_sha256_observed": summary["model_sha256_observed"],
                "candidate_review_observations_model_authority": summary[
                    "candidate_review_observations_model_authority"
                ],
                "candidate_model_observation_model_authority": summary[
                    "candidate_model_observation_model_authority"
                ],
                "candidate_model_observation_row_count": summary[
                    "candidate_model_observation_row_count"
                ],
                "candidate_model_observation_scene_row_count": summary[
                    "candidate_model_observation_scene_row_count"
                ],
                "candidate_model_observation_selectable_model_row_count": summary[
                    "candidate_model_observation_selectable_model_row_count"
                ],
                "candidate_model_observation_parsed_selectable_model_row_count": summary[
                    "candidate_model_observation_parsed_selectable_model_row_count"
                ],
                "candidate_model_observation_selected_model_row_count": summary[
                    "candidate_model_observation_selected_model_row_count"
                ],
                "candidate_source_lock_model_authority": summary[
                    "candidate_source_lock_model_authority"
                ],
                "candidate_source_lock_status": summary["candidate_source_lock"]["status"],
                "candidate_source_lock_ready_for_review": summary[
                    "candidate_source_lock"
                ]["source_lock_ready_for_review"],
                "candidate_source_lock_digest_model_authority": summary[
                    "candidate_source_lock_digest_model_authority"
                ],
                "candidate_source_lock_digest_row_count": summary[
                    "candidate_source_lock_digest_row_count"
                ],
                "candidate_source_lock_selected_model_digest_row_count": summary[
                    "candidate_source_lock_selected_model_digest_row_count"
                ],
                "candidate_operator_intake_plan_model_authority": summary[
                    "candidate_operator_intake_plan_model_authority"
                ],
                "candidate_operator_intake_plan_status": summary[
                    "candidate_operator_intake_plan_status"
                ],
                "candidate_operator_intake_decision_status": summary[
                    "candidate_operator_intake_decision_status"
                ],
                "candidate_operator_command_plan_model_authority": summary[
                    "candidate_operator_command_plan_model_authority"
                ],
                "candidate_operator_command_plan_status": summary[
                    "candidate_operator_command_plan_status"
                ],
                "candidate_reviewed_manifest_rerun_plan_model_authority": summary[
                    "candidate_reviewed_manifest_rerun_plan_model_authority"
                ],
                "candidate_reviewed_manifest_rerun_plan_status": summary[
                    "candidate_reviewed_manifest_rerun_plan_status"
                ],
                "candidate_reviewed_manifest_rerun_plan_selected_option": (
                    reviewed_manifest_rerun_plan["selected_intake_option_id"]
                ),
                "candidate_reviewed_manifest_rerun_plan_command_template": (
                    reviewed_manifest_rerun_plan[
                        "manifest_checker_command_template"
                    ]
                ),
                "candidate_operator_intake_handoff_model_authority": summary[
                    "candidate_operator_intake_handoff_model_authority"
                ],
                "candidate_operator_intake_handoff_decision_status": (
                    operator_intake_handoff["decision_status"]
                ),
                "candidate_operator_intake_handoff_selected_option": (
                    operator_intake_handoff["selected_intake_option_id"]
                ),
                "candidate_operator_intake_handoff_selected_requirement_ids": (
                    operator_intake_handoff[
                        "selected_option_review_requirement_ids"
                    ]
                ),
                "candidate_operator_intake_selected_option": summary[
                    "candidate_operator_intake_plan"
                ].get("selected_intake_option_id"),
                "candidate_operator_intake_requirement_model_authority": summary[
                    "candidate_operator_intake_requirement_model_authority"
                ],
                "candidate_operator_intake_requirement_row_count": summary[
                    "candidate_operator_intake_requirement_row_count"
                ],
                "candidate_operator_intake_selected_requirement_row_count": summary[
                    "candidate_operator_intake_selected_requirement_row_count"
                ],
                "candidate_operator_intake_selected_requirement_row_ids": summary[
                    "candidate_operator_intake_selected_requirement_row_ids"
                ],
                "candidate_seeded_review_manifest_template_model_authority": summary[
                    "candidate_seeded_review_manifest_template_model_authority"
                ],
                "candidate_review_checklist_model_authority": summary[
                    "candidate_review_checklist_model_authority"
                ],
                "candidate_review_checklist_handoff_model_authority": summary[
                    "candidate_review_checklist_handoff_model_authority"
                ],
                "candidate_review_checklist_handoff_scope_coverage_ready": (
                    review_checklist_handoff[
                        "required_review_scope_coverage_ready"
                    ]
                ),
                "candidate_review_checklist_handoff_gripper_mapping_direct_action_ids": (
                    review_checklist_handoff[
                        "gripper_mapping_direct_action_ids"
                    ]
                ),
                "candidate_review_checklist_handoff_collision_policy_direct_action_ids": (
                    review_checklist_handoff[
                        "collision_policy_direct_action_ids"
                    ]
                ),
                "candidate_review_observations_ready_for_model_backed_ik": summary[
                    "candidate_review_observations"
                ]["ready_for_model_backed_ik"],
                "candidate_review_checklist_ready_for_model_backed_ik": summary[
                    "candidate_review_checklist"
                ]["ready_for_model_backed_ik"],
                "candidate_seeded_review_manifest_template_ready_for_model_backed_ik": summary[
                    "candidate_seeded_review_manifest_template"
                ]["ready_for_model_backed_ik"],
                "candidate_review_checklist_row_count": summary[
                    "candidate_review_checklist"
                ]["row_count"],
                "candidate_review_observations_parsed_model_file_count": summary[
                    "candidate_review_observations"
                ]["parsed_model_file_count"],
                "expected_file_count": summary["expected_file_count"],
                "present_expected_file_count": summary["present_expected_file_count"],
                "missing_expected_relative_paths": summary[
                    "missing_expected_relative_paths"
                ],
                "next_required_action_ids": summary["next_required_action_ids"],
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
