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
INTAKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_public_candidate_intake.py"
MANIFEST_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_manifest.py"
DEFAULT_OUTPUT_DIR = (
    Path("/private/tmp") / "lerobot_sim" / "so101_public_candidate_intake_matrix"
)
SCHEMA = "lerobot.sim.so101_public_candidate_intake_matrix.v1"
PINNED_FIXTURE_COMMIT = "fda892cba81032c46c40976a48c9ceadbf40a9ca"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run hardware-free matrix cases for the SO-ARM100/SO101 public "
            "candidate intake smoke. Synthetic files are generated under the "
            "output directory and are not reviewed physical SO-101 truth."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child intake subprocesses.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def executable_arg(path: Path) -> str:
    raw = str(path)
    if path.is_absolute() or "/" in raw:
        return str(normalize_path(path))
    return raw


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "case_id",
        "ok",
        "status",
        "source_root",
        "upstream_commit",
        "upstream_commit_sha_valid",
        "upstream_commit_status",
        "expected_file_count",
        "present_expected_file_count",
        "missing_expected_relative_paths",
        "model_present",
        "selected_model_supported",
        "selected_model_status",
        "model_sha256_observed",
        "model_authority",
        "candidate_review_observations_model_authority",
        "candidate_model_observation_model_authority",
        "candidate_model_observation_row_count",
        "candidate_model_observation_scene_row_count",
        "candidate_model_observation_selectable_model_row_count",
        "candidate_model_observation_parsed_selectable_model_row_count",
        "candidate_model_observation_selected_model_row_count",
        "candidate_source_lock_model_authority",
        "candidate_source_lock_status",
        "candidate_source_lock_ready_for_review",
        "candidate_source_lock_digest_model_authority",
        "candidate_source_lock_digest_row_count",
        "candidate_source_lock_expected_file_digest_count",
        "candidate_source_lock_extra_lockable_file_count",
        "candidate_source_lock_extra_lockable_relative_paths",
        "candidate_source_lock_selected_model_digest_row_count",
        "candidate_source_lock_selected_model_observation_authority",
        "candidate_source_lock_selected_model_observation_observed",
        "candidate_source_lock_selected_model_observation_parse_ok",
        "candidate_source_lock_selected_model_observation_root_tag",
        "candidate_source_lock_selected_model_observation_joint_count",
        "candidate_source_lock_selected_model_expected_joint_coverage_status",
        "candidate_source_lock_selected_model_expected_joint_observed_count",
        "candidate_source_lock_selected_model_expected_joint_missing_count",
        "candidate_source_lock_selected_model_unexpected_joint_count",
        "candidate_source_lock_selected_model_observation_mesh_reference_count",
        "candidate_source_lock_selected_model_mesh_reference_digest_coverage_status",
        "candidate_source_lock_selected_model_mesh_reference_digest_match_count",
        "candidate_source_lock_selected_model_mesh_reference_digest_missing_count",
        "candidate_direct_template_digest_handoff_authority",
        "candidate_direct_template_digest_handoff_row_count",
        "candidate_direct_template_digest_handoff_expected_file_count",
        "candidate_direct_template_digest_handoff_extra_lockable_file_count",
        "candidate_direct_template_digest_handoff_extra_lockable_relative_paths",
        "candidate_operator_intake_plan_model_authority",
        "candidate_operator_intake_plan_status",
        "candidate_operator_intake_decision_status",
        "candidate_operator_intake_selected_option",
        "candidate_operator_command_plan_model_authority",
        "candidate_operator_command_plan_status",
        "candidate_operator_command_plan_selected_option_command_count",
        "candidate_reviewed_manifest_rerun_plan_model_authority",
        "candidate_reviewed_manifest_rerun_plan_status",
        "candidate_reviewed_manifest_rerun_plan_selected_option",
        "candidate_reviewed_manifest_rerun_plan_source_lock_ready",
        "candidate_reviewed_manifest_rerun_plan_command_template",
        "candidate_reviewed_manifest_rerun_plan_required_success_conditions",
        "candidate_operator_intake_option_count",
        "candidate_operator_intake_selected_requirement_count",
        "candidate_operator_intake_selected_requirement_ids",
        "candidate_operator_intake_requirement_model_authority",
        "candidate_operator_intake_requirement_row_count",
        "candidate_operator_intake_selected_requirement_row_count",
        "candidate_operator_intake_unselected_requirement_row_count",
        "candidate_operator_intake_selected_requirement_row_ids",
        "candidate_operator_intake_handoff_model_authority",
        "candidate_operator_intake_handoff_decision_status",
        "candidate_operator_intake_handoff_selected_option",
        "candidate_operator_intake_handoff_selected_requirement_ids",
        "candidate_operator_intake_handoff_selected_command_count",
        "candidate_review_checklist_model_authority",
        "candidate_review_checklist_row_count",
        "candidate_review_checklist_scope_coverage_ready",
        "candidate_review_checklist_missing_required_review_scope_ids",
        "candidate_review_checklist_gripper_mapping_direct_action_ids",
        "candidate_review_checklist_collision_policy_direct_action_ids",
        "candidate_direct_template_checklist_handoff_authority",
        "candidate_direct_template_checklist_handoff_scope_coverage_ready",
        "candidate_direct_template_checklist_handoff_missing_required_scope_ids",
        "candidate_direct_template_checklist_handoff_gripper_mapping_direct_action_ids",
        "candidate_direct_template_checklist_handoff_collision_policy_direct_action_ids",
        "candidate_seeded_review_manifest_template_model_authority",
        "candidate_review_observations_parsed_model_file_count",
        "candidate_readme_gripper_mapping_caveat",
        "candidate_readme_base_collision_caveat",
        "seeded_template_manifest_checker_status",
        "seeded_template_manifest_checker_ready_for_model_backed_ik",
        "seeded_template_manifest_checker_physical_ready",
        "seeded_template_manifest_checker_missing_inputs",
        "ready_for_model_backed_ik",
        "observed_evidence_is_physical_so101_authority",
        "next_required_action_ids",
        "summary_path",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def create_complete_fixture(root: Path) -> Path:
    source_root = root / "complete_so101"
    for relative_path in EXPECTED_RELATIVE_PATHS:
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".urdf":
            path.write_text(
                "<?xml version=\"1.0\"?>\n"
                "<!-- synthetic public candidate intake fixture only -->\n"
                "<robot name=\"so101_new_calib\">\n"
                "  <link name=\"base_link\"/>\n"
                "  <link name=\"gripper_frame_link\"/>\n"
                "  <joint name=\"shoulder_pan\" type=\"revolute\">\n"
                "    <parent link=\"base_link\"/>\n"
                "    <child link=\"gripper_frame_link\"/>\n"
                "    <limit lower=\"-1.0\" upper=\"1.0\" effort=\"1.0\" velocity=\"1.0\"/>\n"
                "  </joint>\n"
                "</robot>\n"
            )
        elif path.suffix == ".xml":
            path.write_text(
                "<?xml version=\"1.0\"?>\n"
                "<!-- synthetic public candidate intake fixture only -->\n"
                "<mujoco model=\"so101_fixture\">\n"
                "  <worldbody>\n"
                "    <body name=\"base\">\n"
                "      <joint name=\"fixture_joint\" type=\"hinge\" range=\"-1 1\"/>\n"
                "      <geom type=\"mesh\" mesh=\"assets/base_so101_v2.stl\"/>\n"
                "    </body>\n"
                "  </worldbody>\n"
                "</mujoco>\n"
            )
        elif path.suffix == ".md":
            path.write_text(
                "# Synthetic SO101 fixture\n\n"
                "This fixture is for hardware-free public candidate intake matrix testing only.\n"
                "Files are generated with onshape-to-robot and modified to use relative mesh paths.\n"
                "Base collision meshes were removed due to collision issues.\n"
                "The LeRobot linear joint mapping is not reflected in these URDF/MuJoCo files.\n"
            )
        else:
            path.write_bytes(f"synthetic fixture bytes for {relative_path}\n".encode())
    return source_root


def case_specs(fixtures_dir: Path) -> list[dict[str, Any]]:
    complete_root = create_complete_fixture(fixtures_dir)
    incomplete_root = fixtures_dir / "incomplete_so101"
    shutil.copytree(complete_root, incomplete_root)
    (incomplete_root / "assets" / "wrist_roll_pitch_so101_v2.stl").unlink()
    extra_lockable_root = fixtures_dir / "extra_lockable_so101"
    shutil.copytree(complete_root, extra_lockable_root)
    extra_lockable_path = extra_lockable_root / "assets" / "base_so101_v2.part"
    extra_lockable_path.write_bytes(b"synthetic upstream CAD source bytes\n")
    missing_root = fixtures_dir / "missing_so101"
    return [
        {
            "case_id": "source_root_not_supplied",
            "args": [],
            "expect": {
                "status": "source_root_not_supplied",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": 0,
                "model_present": False,
                "parsed_model_file_count": 0,
                "commit_action_present": True,
            },
        },
        {
            "case_id": "source_root_unavailable",
            "args": [
                "--source-root",
                str(missing_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
            ],
            "expect": {
                "status": "source_root_unavailable",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": 0,
                "model_present": False,
                "parsed_model_file_count": 0,
                "commit_action_present": False,
            },
        },
        {
            "case_id": "candidate_intake_incomplete",
            "args": [
                "--source-root",
                str(incomplete_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
            ],
            "expect": {
                "status": "candidate_intake_incomplete",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS) - 1,
                "model_present": True,
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_contains": ["assets/wrist_roll_pitch_so101_v2.stl"],
                "commit_action_present": False,
            },
        },
        {
            "case_id": "candidate_intake_invalid_model_selection",
            "args": [
                "--source-root",
                str(complete_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
                "--model-relative-path",
                "README.md",
            ],
            "expect": {
                "status": "candidate_intake_model_selection_invalid",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": False,
                "selected_model_status": "selected_model_not_supported",
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "upstream_commit_sha_valid": True,
                "upstream_commit_status": "upstream_commit_sha_pinned",
                "source_lock_status": "candidate_source_lock_incomplete",
                "source_lock_ready_for_review": False,
                "operator_plan_status": "candidate_operator_intake_inputs_incomplete",
                "operator_decision_status": "vendor_or_external_intake_not_declared",
                "selected_intake_option_id": None,
                "selected_requirement_count": 0,
                "selected_requirement_ids": [],
            },
        },
        {
            "case_id": "candidate_intake_unpinned_commit_ref",
            "args": [
                "--source-root",
                str(complete_root),
                "--upstream-commit",
                "main",
            ],
            "expect": {
                "status": "candidate_intake_checked",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": True,
                "selected_model_status": "selectable_so101_model_selected",
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": True,
                "upstream_commit_sha_valid": False,
                "upstream_commit_status": "upstream_commit_not_immutable_sha",
                "source_lock_status": "candidate_source_lock_incomplete",
                "source_lock_ready_for_review": False,
                "operator_plan_status": "candidate_operator_intake_inputs_incomplete",
                "operator_decision_status": "vendor_or_external_intake_not_declared",
                "selected_intake_option_id": None,
                "selected_requirement_count": 0,
                "selected_requirement_ids": [],
            },
        },
        {
            "case_id": "candidate_intake_checked",
            "args": [
                "--source-root",
                str(complete_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
            ],
            "expect": {
                "status": "candidate_intake_checked",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": True,
                "selected_model_status": "selectable_so101_model_selected",
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "upstream_commit_sha_valid": True,
                "upstream_commit_status": "upstream_commit_sha_pinned",
                "source_lock_status": "candidate_source_lock_ready_for_review",
                "source_lock_ready_for_review": True,
                "operator_plan_status": "candidate_locked_operator_decision_required",
                "operator_decision_status": "vendor_or_external_intake_not_declared",
                "selected_intake_option_id": None,
                "selected_requirement_count": 0,
                "selected_requirement_ids": [],
            },
        },
        {
            "case_id": "candidate_intake_extra_lockable_source_file",
            "args": [
                "--source-root",
                str(extra_lockable_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
            ],
            "expect": {
                "status": "candidate_intake_checked",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": True,
                "selected_model_status": "selectable_so101_model_selected",
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "upstream_commit_sha_valid": True,
                "upstream_commit_status": "upstream_commit_sha_pinned",
                "source_lock_status": "candidate_source_lock_ready_for_review",
                "source_lock_ready_for_review": True,
                "operator_plan_status": "candidate_locked_operator_decision_required",
                "operator_decision_status": "vendor_or_external_intake_not_declared",
                "selected_intake_option_id": None,
                "selected_requirement_count": 0,
                "selected_requirement_ids": [],
                "extra_lockable_relative_paths": ["assets/base_so101_v2.part"],
            },
        },
        {
            "case_id": "candidate_intake_checked_mjcf_model_selection",
            "args": [
                "--source-root",
                str(complete_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
                "--model-relative-path",
                "so101_new_calib.xml",
            ],
            "expect": {
                "status": "candidate_intake_checked",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": True,
                "selected_model_status": "selectable_so101_model_selected",
                "parsed_model_file_count": 5,
                "selected_model_root_tag": "mujoco",
                "selected_model_expected_joint_coverage_status": (
                    "no_expected_so101_joints_observed"
                ),
                "selected_model_expected_joint_observed_count": 0,
                "selected_model_expected_joint_missing_count": 6,
                "selected_model_unexpected_joint_count": 1,
                "selected_model_mesh_reference_count": 1,
                "selected_model_mesh_digest_coverage_status": (
                    "all_observed_mesh_references_locked"
                ),
                "selected_model_mesh_digest_match_count": 1,
                "selected_model_mesh_digest_missing_count": 0,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "upstream_commit_sha_valid": True,
                "upstream_commit_status": "upstream_commit_sha_pinned",
                "source_lock_status": "candidate_source_lock_ready_for_review",
                "source_lock_ready_for_review": True,
                "operator_plan_status": "candidate_locked_operator_decision_required",
                "operator_decision_status": "vendor_or_external_intake_not_declared",
                "selected_intake_option_id": None,
                "selected_requirement_count": 0,
                "selected_requirement_ids": [],
            },
        },
        {
            "case_id": "candidate_intake_checked_external_decision",
            "args": [
                "--source-root",
                str(complete_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
                "--operator-intake-decision",
                "external_pinned_source_root",
            ],
            "expect": {
                "status": "candidate_intake_checked",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": True,
                "selected_model_status": "selectable_so101_model_selected",
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "upstream_commit_sha_valid": True,
                "upstream_commit_status": "upstream_commit_sha_pinned",
                "source_lock_status": "candidate_source_lock_ready_for_review",
                "source_lock_ready_for_review": True,
                "operator_plan_status": "candidate_locked_operator_decision_required",
                "operator_decision_status": "candidate_intake_decision_recorded_not_authority",
                "selected_intake_option_id": "external_pinned_source_root",
                "selected_requirement_count": 6,
                "selected_requirement_ids": [
                    "external_checkout_path_declared",
                    "external_upstream_commit_pinned",
                    "external_file_digest_lock_reviewed",
                    "external_gripper_mapping_reviewed",
                    "external_collision_policy_reviewed",
                    "external_reviewed_bundle_manifest_supplied",
                ],
            },
        },
        {
            "case_id": "candidate_intake_checked_vendor_decision",
            "args": [
                "--source-root",
                str(complete_root),
                "--upstream-commit",
                PINNED_FIXTURE_COMMIT,
                "--operator-intake-decision",
                "vendor_locked_bundle",
            ],
            "expect": {
                "status": "candidate_intake_checked",
                "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "present_expected_file_count": len(EXPECTED_RELATIVE_PATHS),
                "model_present": True,
                "selected_model_supported": True,
                "selected_model_status": "selectable_so101_model_selected",
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "upstream_commit_sha_valid": True,
                "upstream_commit_status": "upstream_commit_sha_pinned",
                "source_lock_status": "candidate_source_lock_ready_for_review",
                "source_lock_ready_for_review": True,
                "operator_plan_status": "candidate_locked_operator_decision_required",
                "operator_decision_status": "candidate_intake_decision_recorded_not_authority",
                "selected_intake_option_id": "vendor_locked_bundle",
                "selected_requirement_count": 7,
                "selected_requirement_ids": [
                    "vendor_import_path_declared",
                    "vendor_upstream_commit_pinned",
                    "vendor_license_provenance_reviewed",
                    "vendor_file_digest_manifest_reviewed",
                    "vendor_gripper_mapping_reviewed",
                    "vendor_collision_policy_reviewed",
                    "vendor_reviewed_bundle_manifest_supplied",
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_dir = output_dir / case_id
    summary_path = case_dir / "so101_public_candidate_intake_summary.json"
    command = [
        executable_arg(python_path),
        str(INTAKE_SCRIPT),
        "--output-dir",
        str(case_dir),
        *case_args,
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    case_dir.mkdir(parents=True, exist_ok=True)
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
        "artifacts": summary.get("artifacts") if isinstance(summary, dict) else {},
    }
    seeded_preview = run_seeded_template_manifest_preview(
        case_dir=case_dir,
        summary=summary,
        python_path=python_path,
    )
    record["seeded_template_manifest_preview"] = seeded_preview
    return (
        record,
        summary,
    )


def run_seeded_template_manifest_preview(
    *,
    case_dir: Path,
    summary: dict[str, Any],
    python_path: Path,
) -> dict[str, Any]:
    seeded_template = summary.get("candidate_seeded_review_manifest_template")
    seeded_template = seeded_template if isinstance(seeded_template, dict) else {}
    manifest_template = seeded_template.get("manifest_template")
    if not isinstance(manifest_template, dict):
        return {
            "attempted": False,
            "reason": "candidate_seeded_review_manifest_template_unavailable",
        }

    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    direct_artifact_path = artifacts.get("candidate_direct_review_manifest_template_json")
    direct_manifest_path = (
        Path(direct_artifact_path)
        if isinstance(direct_artifact_path, str)
        else case_dir / "so101_public_candidate_review_manifest_template.direct.json"
    )
    preview_dir = case_dir / "so101_public_candidate_seeded_review_manifest_checker_preview"
    if not direct_manifest_path.is_file():
        write_json(direct_manifest_path, manifest_template)
    command = [
        executable_arg(python_path),
        str(MANIFEST_CHECKER_PATH),
        "--manifest-path",
        str(direct_manifest_path),
        "--output-dir",
        str(preview_dir),
        "--python",
        executable_arg(python_path),
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / "seeded_manifest_checker_stdout.txt"
    stderr_path = case_dir / "seeded_manifest_checker_stderr.txt"
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    preview_summary_path = preview_dir / "so101_model_bundle_manifest_summary.json"
    try:
        preview_summary = json.loads(preview_summary_path.read_text())
    except Exception as exc:
        preview_summary = {
            "ok": False,
            "status": "seeded_template_manifest_checker_summary_unavailable",
            "summary_error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "attempted": True,
        "command": command,
        "return_code": result.returncode,
        "direct_manifest_path": str(direct_manifest_path),
        "summary_path": str(preview_summary_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary": preview_summary,
    }


def summarize_case(record: dict[str, Any], summary: dict[str, Any], expect: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    case_id = str(record["case_id"])

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            errors.append(f"{case_id}.{label}: expected {expected!r}, got {actual!r}")

    check("return_code", record.get("return_code"), 0)
    check("ok", summary.get("ok"), True)
    for key in (
        "status",
        "expected_file_count",
        "present_expected_file_count",
        "model_present",
    ):
        check(key, summary.get(key), expect[key])
    expected_selected_model_supported = expect.get("selected_model_supported", True)
    expected_selected_model_status = expect.get("selected_model_status")
    if expected_selected_model_status is None:
        if not expect["model_present"]:
            expected_selected_model_status = "selected_model_missing"
        elif expected_selected_model_supported:
            expected_selected_model_status = "selectable_so101_model_selected"
        else:
            expected_selected_model_status = "selected_model_not_supported"
    check(
        "selected_model_supported",
        summary.get("selected_model_supported"),
        expected_selected_model_supported,
    )
    check(
        "selected_model_status",
        summary.get("selected_model_status"),
        expected_selected_model_status,
    )

    check("model_authority", summary.get("model_authority"), "public_candidate_intake_not_authority")
    check(
        "candidate_review_observations_model_authority",
        summary.get("candidate_review_observations_model_authority"),
        "candidate_review_observations_not_authority",
    )
    expected_model_observation_row_count = 5 if expect["parsed_model_file_count"] else 0
    expected_model_observation_scene_row_count = (
        1 if expect["parsed_model_file_count"] else 0
    )
    expected_model_observation_selectable_model_row_count = (
        4 if expect["parsed_model_file_count"] else 0
    )
    expected_selected_model_observation_row_count = (
        1 if expect["model_present"] and expected_selected_model_supported else 0
    )
    check(
        "candidate_model_observation_model_authority",
        summary.get("candidate_model_observation_model_authority"),
        "candidate_model_observation_not_authority",
    )
    check(
        "candidate_model_observation_row_count",
        summary.get("candidate_model_observation_row_count"),
        expected_model_observation_row_count,
    )
    check(
        "candidate_model_observation_scene_row_count",
        summary.get("candidate_model_observation_scene_row_count"),
        expected_model_observation_scene_row_count,
    )
    check(
        "candidate_model_observation_selectable_model_row_count",
        summary.get("candidate_model_observation_selectable_model_row_count"),
        expected_model_observation_selectable_model_row_count,
    )
    check(
        "candidate_model_observation_parsed_selectable_model_row_count",
        summary.get("candidate_model_observation_parsed_selectable_model_row_count"),
        expected_model_observation_selectable_model_row_count,
    )
    check(
        "candidate_model_observation_selected_model_row_count",
        summary.get("candidate_model_observation_selected_model_row_count"),
        expected_selected_model_observation_row_count,
    )
    check("ready_for_model_backed_ik", summary.get("ready_for_model_backed_ik"), False)
    check(
        "observed_evidence_is_physical_so101_authority",
        summary.get("observed_evidence_is_physical_so101_authority"),
        False,
    )
    check("ready_for_policy_training", summary.get("ready_for_policy_training"), False)
    check("hardware_skipped", summary.get("hardware_skipped"), True)
    check("gui_skipped", summary.get("gui_skipped"), True)
    check("openai_skipped", summary.get("openai_skipped"), True)
    check("network_skipped", summary.get("network_skipped"), True)

    next_actions = summary.get("next_required_action_ids")
    next_actions = next_actions if isinstance(next_actions, list) else []
    commit_action_present = "pin_upstream_soarm100_commit" in next_actions
    check("commit_action_present", commit_action_present, expect["commit_action_present"])
    upstream = summary.get("upstream")
    upstream = upstream if isinstance(upstream, dict) else {}
    expected_commit_sha_valid = expect.get("upstream_commit_sha_valid")
    if expected_commit_sha_valid is None:
        expected_commit_sha_valid = expect["commit_action_present"] is False
    check(
        "upstream.commit_sha_valid",
        upstream.get("commit_sha_valid"),
        expected_commit_sha_valid,
    )
    expected_commit_status = expect.get("upstream_commit_status")
    if expected_commit_status is None:
        expected_commit_status = (
            "upstream_commit_sha_pinned"
            if expected_commit_sha_valid
            else "upstream_commit_not_supplied"
        )
    check("upstream.commit_status", upstream.get("commit_status"), expected_commit_status)

    missing_paths = summary.get("missing_expected_relative_paths")
    missing_paths = missing_paths if isinstance(missing_paths, list) else []
    if "missing_exact" in expect:
        check("missing_expected_relative_paths", missing_paths, expect["missing_exact"])
    for expected_missing in expect.get("missing_contains", []):
        if expected_missing not in missing_paths:
            errors.append(
                f"{case_id}.missing_expected_relative_paths missing {expected_missing!r}"
            )

    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    for artifact_key in (
        "summary_json",
        "files_csv",
        "candidate_manifest_draft_json",
        "candidate_source_lock_json",
        "candidate_source_lock_digests_csv",
        "candidate_model_file_observations_csv",
        "candidate_seeded_review_manifest_template_json",
        "candidate_direct_review_manifest_template_json",
        "candidate_review_checklist_json",
        "candidate_review_checklist_csv",
        "candidate_operator_intake_plan_json",
        "candidate_operator_command_plan_json",
        "candidate_operator_intake_requirements_csv",
        "readme_md",
    ):
        artifact_path = artifacts.get(artifact_key)
        if not isinstance(artifact_path, str) or not Path(artifact_path).is_file():
            errors.append(f"{case_id}.artifacts.{artifact_key} missing: {artifact_path!r}")

    draft = summary.get("candidate_manifest_draft")
    draft = draft if isinstance(draft, dict) else {}
    if draft.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_manifest_draft.ready_for_model_backed_ik not false")
    if draft.get("authority") != {} or draft.get("provenance") != {}:
        errors.append(f"{case_id}.candidate_manifest_draft authority/provenance not empty")
    if expect["model_present"] and not summary.get("model_sha256_observed"):
        errors.append(f"{case_id}.model_sha256_observed missing")

    seeded_template = summary.get("candidate_seeded_review_manifest_template")
    seeded_template = seeded_template if isinstance(seeded_template, dict) else {}
    if (
        summary.get("candidate_seeded_review_manifest_template_model_authority")
        != "candidate_seeded_review_manifest_template_not_authority"
    ):
        errors.append(
            f"{case_id}.candidate_seeded_review_manifest_template_model_authority invalid"
        )
    if seeded_template.get("model_authority") != "candidate_seeded_review_manifest_template_not_authority":
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template.model_authority invalid")
    if seeded_template.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template.ready_for_model_backed_ik not false")
    if seeded_template.get("physical_so101_model_authority_ready") is not False:
        errors.append(
            f"{case_id}.candidate_seeded_review_manifest_template.physical authority not false"
        )
    summary_required_scopes = summary.get("review_required_scopes")
    summary_required_scopes = (
        summary_required_scopes if isinstance(summary_required_scopes, list) else []
    )
    seeded_required_scopes = seeded_template.get("review_required_scopes")
    seeded_required_scopes = (
        seeded_required_scopes if isinstance(seeded_required_scopes, list) else []
    )
    for required_scope in ("gripper_mapping", "collision_policy"):
        if required_scope not in summary_required_scopes:
            errors.append(
                f"{case_id}.review_required_scopes missing {required_scope!r}"
            )
        if required_scope not in seeded_required_scopes:
            errors.append(
                f"{case_id}.candidate_seeded_review_manifest_template.review_required_scopes missing {required_scope!r}"
            )
    source_lock = summary.get("candidate_source_lock")
    source_lock = source_lock if isinstance(source_lock, dict) else {}
    expected_source_lock_ready = bool(
        expect.get(
            "source_lock_ready_for_review",
            (
                expect["model_present"]
                and expected_selected_model_supported
                and not missing_paths
                and commit_action_present is False
            ),
        )
    )
    expected_source_lock_status = expect.get(
        "source_lock_status",
        (
            "candidate_source_lock_ready_for_review"
            if expected_source_lock_ready
            else "candidate_source_lock_incomplete"
        ),
    )
    if summary.get("candidate_source_lock_model_authority") != "candidate_source_lock_not_authority":
        errors.append(f"{case_id}.candidate_source_lock_model_authority invalid")
    if source_lock.get("model_authority") != "candidate_source_lock_not_authority":
        errors.append(f"{case_id}.candidate_source_lock.model_authority invalid")
    if source_lock.get("status") != expected_source_lock_status:
        errors.append(
            f"{case_id}.candidate_source_lock.status expected "
            f"{expected_source_lock_status!r}, got {source_lock.get('status')!r}"
        )
    if source_lock.get("source_lock_ready_for_review") is not expected_source_lock_ready:
        errors.append(f"{case_id}.candidate_source_lock.source_lock_ready_for_review invalid")
    if source_lock.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(f"{case_id}.candidate_source_lock physical authority not false")
    if source_lock.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_source_lock.ready_for_model_backed_ik not false")
    selected_model = source_lock.get("selected_model")
    selected_model = selected_model if isinstance(selected_model, dict) else {}
    selected_model_observation = selected_model.get("observation")
    selected_model_observation = (
        selected_model_observation
        if isinstance(selected_model_observation, dict)
        else {}
    )
    if expect["model_present"] and expected_selected_model_supported:
        if selected_model_observation.get("authority_boundary") != (
            "candidate_selected_model_observation_not_authority"
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model observation authority invalid"
            )
        if selected_model_observation.get("observed") is not True:
            errors.append(
                f"{case_id}.candidate_source_lock selected model observation missing"
            )
        if selected_model_observation.get("parse_ok") is not True:
            errors.append(
                f"{case_id}.candidate_source_lock selected model observation parse failed"
            )
        expected_selected_root_tag = expect.get("selected_model_root_tag")
        if expected_selected_root_tag is None:
            expected_selected_root_tag = "robot"
        if selected_model_observation.get("root_tag") != expected_selected_root_tag:
            errors.append(
                f"{case_id}.candidate_source_lock selected model observation root tag "
                f"expected {expected_selected_root_tag!r}, got "
                f"{selected_model_observation.get('root_tag')!r}"
            )
        expected_joint_coverage_status = expect.get(
            "selected_model_expected_joint_coverage_status",
            "partial_expected_so101_joints_observed",
        )
        if (
            selected_model_observation.get("expected_joint_coverage_status")
            != expected_joint_coverage_status
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model expected joint coverage "
                f"expected {expected_joint_coverage_status!r}, got "
                f"{selected_model_observation.get('expected_joint_coverage_status')!r}"
            )
        expected_joint_observed_count = int(
            expect.get("selected_model_expected_joint_observed_count", 1)
        )
        if (
            selected_model_observation.get("expected_joint_observed_count")
            != expected_joint_observed_count
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model expected joint observed count "
                f"expected {expected_joint_observed_count!r}, got "
                f"{selected_model_observation.get('expected_joint_observed_count')!r}"
            )
        expected_joint_missing_count = int(
            expect.get("selected_model_expected_joint_missing_count", 5)
        )
        if (
            selected_model_observation.get("expected_joint_missing_count")
            != expected_joint_missing_count
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model expected joint missing count "
                f"expected {expected_joint_missing_count!r}, got "
                f"{selected_model_observation.get('expected_joint_missing_count')!r}"
            )
        expected_unexpected_joint_count = int(
            expect.get("selected_model_unexpected_joint_count", 0)
        )
        if (
            selected_model_observation.get("unexpected_joint_count")
            != expected_unexpected_joint_count
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model unexpected joint count "
                f"expected {expected_unexpected_joint_count!r}, got "
                f"{selected_model_observation.get('unexpected_joint_count')!r}"
            )
        expected_mesh_reference_count = int(
            expect.get("selected_model_mesh_reference_count", 0)
        )
        if (
            selected_model_observation.get("mesh_reference_count")
            != expected_mesh_reference_count
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model mesh reference count "
                f"expected {expected_mesh_reference_count!r}, got "
                f"{selected_model_observation.get('mesh_reference_count')!r}"
            )
        expected_mesh_coverage_status = expect.get(
            "selected_model_mesh_digest_coverage_status",
            "no_mesh_references_observed",
        )
        if (
            selected_model_observation.get("mesh_reference_digest_coverage_status")
            != expected_mesh_coverage_status
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model mesh digest status "
                f"expected {expected_mesh_coverage_status!r}, got "
                f"{selected_model_observation.get('mesh_reference_digest_coverage_status')!r}"
            )
        expected_mesh_digest_match_count = int(
            expect.get("selected_model_mesh_digest_match_count", 0)
        )
        if (
            selected_model_observation.get("mesh_reference_digest_match_count")
            != expected_mesh_digest_match_count
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model mesh digest match count "
                f"expected {expected_mesh_digest_match_count!r}, got "
                f"{selected_model_observation.get('mesh_reference_digest_match_count')!r}"
            )
        expected_mesh_digest_missing_count = int(
            expect.get("selected_model_mesh_digest_missing_count", 0)
        )
        if (
            selected_model_observation.get("mesh_reference_digest_missing_count")
            != expected_mesh_digest_missing_count
        ):
            errors.append(
                f"{case_id}.candidate_source_lock selected model mesh digest missing count "
                f"expected {expected_mesh_digest_missing_count!r}, got "
                f"{selected_model_observation.get('mesh_reference_digest_missing_count')!r}"
            )
    elif expect["model_present"] and not expected_selected_model_supported:
        if selected_model_observation.get("observed") is not False:
            errors.append(
                f"{case_id}.candidate_source_lock unsupported selected model should not be observed"
            )
        if selected_model_observation.get("mesh_reference_digest_coverage_status") != (
            "no_mesh_references_observed"
        ):
            errors.append(
                f"{case_id}.candidate_source_lock unsupported selected model mesh digest status invalid"
            )
        if (
            selected_model_observation.get("expected_joint_coverage_status")
            != "selected_model_not_observed"
        ):
            errors.append(
                f"{case_id}.candidate_source_lock unsupported selected model joint coverage status invalid"
            )
        if selected_model_observation.get("expected_joint_observed_count") != 0:
            errors.append(
                f"{case_id}.candidate_source_lock unsupported selected model observed joint count invalid"
            )
        if selected_model_observation.get("expected_joint_missing_count") != 6:
            errors.append(
                f"{case_id}.candidate_source_lock unsupported selected model missing joint count invalid"
            )
        if selected_model_observation.get("unexpected_joint_count") != 0:
            errors.append(
                f"{case_id}.candidate_source_lock unsupported selected model unexpected joint count invalid"
            )
    expected_extra_lockable_paths = list(
        expect.get("extra_lockable_relative_paths", [])
    )
    expected_extra_lockable_count = len(expected_extra_lockable_paths)
    expected_expected_digest_row_count = int(
        summary.get("present_expected_file_count") or 0
    )
    expected_digest_row_count = (
        expected_expected_digest_row_count + expected_extra_lockable_count
    )
    expected_selected_digest_row_count = (
        1 if expect["model_present"] and expected_selected_model_supported else 0
    )
    if (
        summary.get("candidate_source_lock_digest_model_authority")
        != "candidate_source_lock_digest_not_authority"
    ):
        errors.append(f"{case_id}.candidate_source_lock_digest_model_authority invalid")
    if summary.get("candidate_source_lock_digest_row_count") != expected_digest_row_count:
        errors.append(
            f"{case_id}.candidate_source_lock_digest_row_count expected "
            f"{expected_digest_row_count!r}, got "
            f"{summary.get('candidate_source_lock_digest_row_count')!r}"
        )
    if (
        summary.get("candidate_source_lock_expected_file_digest_count")
        != expected_expected_digest_row_count
    ):
        errors.append(
            f"{case_id}.candidate_source_lock_expected_file_digest_count expected "
            f"{expected_expected_digest_row_count!r}, got "
            f"{summary.get('candidate_source_lock_expected_file_digest_count')!r}"
        )
    if (
        summary.get("candidate_source_lock_extra_lockable_file_count")
        != expected_extra_lockable_count
    ):
        errors.append(
            f"{case_id}.candidate_source_lock_extra_lockable_file_count expected "
            f"{expected_extra_lockable_count!r}, got "
            f"{summary.get('candidate_source_lock_extra_lockable_file_count')!r}"
        )
    if (
        summary.get("candidate_source_lock_extra_lockable_relative_paths")
        != expected_extra_lockable_paths
    ):
        errors.append(
            f"{case_id}.candidate_source_lock_extra_lockable_relative_paths expected "
            f"{expected_extra_lockable_paths!r}, got "
            f"{summary.get('candidate_source_lock_extra_lockable_relative_paths')!r}"
        )
    if (
        summary.get("candidate_source_lock_selected_model_digest_row_count")
        != expected_selected_digest_row_count
    ):
        errors.append(
            f"{case_id}.candidate_source_lock_selected_model_digest_row_count expected "
            f"{expected_selected_digest_row_count!r}, got "
            f"{summary.get('candidate_source_lock_selected_model_digest_row_count')!r}"
        )
    if expected_source_lock_ready:
        if source_lock.get("file_digest_count") != expected_digest_row_count:
            errors.append(f"{case_id}.candidate_source_lock.file_digest_count invalid")
        if source_lock.get("expected_file_digest_count") != expected_expected_digest_row_count:
            errors.append(
                f"{case_id}.candidate_source_lock.expected_file_digest_count invalid"
            )
        if source_lock.get("extra_lockable_file_count") != expected_extra_lockable_count:
            errors.append(
                f"{case_id}.candidate_source_lock.extra_lockable_file_count invalid"
            )
        if source_lock.get("extra_lockable_relative_paths") != expected_extra_lockable_paths:
            errors.append(
                f"{case_id}.candidate_source_lock.extra_lockable_relative_paths invalid"
            )
        if selected_model.get("sha256") != summary.get("model_sha256_observed"):
            errors.append(f"{case_id}.candidate_source_lock selected model digest mismatch")
    elif expect["model_present"] and not expected_selected_model_supported:
        missing_inputs = source_lock.get("missing_inputs")
        missing_inputs = missing_inputs if isinstance(missing_inputs, list) else []
        if "selectable_so101_model_path" not in missing_inputs:
            errors.append(
                f"{case_id}.candidate_source_lock missing selectable model diagnostic"
            )
    observed_inputs = seeded_template.get("observed_inputs")
    observed_inputs = observed_inputs if isinstance(observed_inputs, dict) else {}
    digest_handoff = observed_inputs.get("candidate_source_lock_digest_handoff")
    digest_handoff = digest_handoff if isinstance(digest_handoff, dict) else {}
    operator_plan = summary.get("candidate_operator_intake_plan")
    operator_plan = operator_plan if isinstance(operator_plan, dict) else {}
    if (
        summary.get("candidate_operator_intake_plan_model_authority")
        != "candidate_operator_intake_plan_not_authority"
    ):
        errors.append(f"{case_id}.candidate_operator_intake_plan_model_authority invalid")
    if operator_plan.get("model_authority") != "candidate_operator_intake_plan_not_authority":
        errors.append(f"{case_id}.candidate_operator_intake_plan.model_authority invalid")
    expected_operator_decision_status = expect.get(
        "operator_decision_status", "vendor_or_external_intake_not_declared"
    )
    expected_selected_option = expect.get("selected_intake_option_id")
    if operator_plan.get("decision_status") != expected_operator_decision_status:
        errors.append(f"{case_id}.candidate_operator_intake_plan.decision_status invalid")
    if operator_plan.get("selected_intake_option_id") != expected_selected_option:
        errors.append(
            f"{case_id}.candidate_operator_intake_plan.selected_intake_option_id "
            f"expected {expected_selected_option!r}, got "
            f"{operator_plan.get('selected_intake_option_id')!r}"
        )
    expected_requirement_count = int(expect.get("selected_requirement_count", 0))
    expected_requirement_ids = expect.get("selected_requirement_ids", [])
    selected_requirement_ids = operator_plan.get("selected_option_review_requirement_ids")
    selected_requirement_ids = (
        selected_requirement_ids if isinstance(selected_requirement_ids, list) else []
    )
    if operator_plan.get("selected_option_review_requirement_count") != expected_requirement_count:
        errors.append(
            f"{case_id}.candidate_operator_intake_plan.selected_option_review_requirement_count invalid"
        )
    if selected_requirement_ids != expected_requirement_ids:
        errors.append(
            f"{case_id}.candidate_operator_intake_plan.selected_option_review_requirement_ids "
            f"expected {expected_requirement_ids!r}, got {selected_requirement_ids!r}"
        )
    if (
        summary.get("candidate_operator_intake_requirement_model_authority")
        != "candidate_operator_intake_requirement_not_authority"
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_requirement_model_authority invalid"
        )
    expected_requirement_row_count = 13
    if summary.get("candidate_operator_intake_requirement_row_count") != expected_requirement_row_count:
        errors.append(
            f"{case_id}.candidate_operator_intake_requirement_row_count invalid"
        )
    if (
        summary.get("candidate_operator_intake_selected_requirement_row_count")
        != expected_requirement_count
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_selected_requirement_row_count invalid"
        )
    if (
        summary.get("candidate_operator_intake_unselected_requirement_row_count")
        != expected_requirement_row_count - expected_requirement_count
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_unselected_requirement_row_count invalid"
        )
    selected_requirement_row_ids = summary.get(
        "candidate_operator_intake_selected_requirement_row_ids"
    )
    selected_requirement_row_ids = (
        selected_requirement_row_ids
        if isinstance(selected_requirement_row_ids, list)
        else []
    )
    if selected_requirement_row_ids != expected_requirement_ids:
        errors.append(
            f"{case_id}.candidate_operator_intake_selected_requirement_row_ids "
            f"expected {expected_requirement_ids!r}, got {selected_requirement_row_ids!r}"
        )
    operator_handoff = summary.get("candidate_operator_intake_handoff")
    operator_handoff = operator_handoff if isinstance(operator_handoff, dict) else {}
    if (
        summary.get("candidate_operator_intake_handoff_model_authority")
        != "candidate_operator_intake_handoff_not_authority"
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_handoff_model_authority invalid"
        )
    if (
        operator_handoff.get("model_authority")
        != "candidate_operator_intake_handoff_not_authority"
    ):
        errors.append(f"{case_id}.candidate_operator_intake_handoff.model_authority invalid")
    if operator_handoff.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_handoff physical authority not false")
    if operator_handoff.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_handoff.ready_for_model_backed_ik not false")
    if operator_handoff.get("decision_status") != expected_operator_decision_status:
        errors.append(f"{case_id}.candidate_operator_intake_handoff.decision_status invalid")
    if operator_handoff.get("selected_intake_option_id") != expected_selected_option:
        errors.append(
            f"{case_id}.candidate_operator_intake_handoff.selected_intake_option_id invalid"
        )
    if (
        operator_handoff.get("selected_option_review_requirement_count")
        != expected_requirement_count
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_handoff.selected_option_review_requirement_count invalid"
        )
    if (
        operator_handoff.get("selected_option_review_requirement_ids")
        != expected_requirement_ids
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_handoff.selected_option_review_requirement_ids invalid"
        )
    if operator_plan.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_plan.ready_for_model_backed_ik not false")
    if operator_plan.get("ready_for_policy_training") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_plan.ready_for_policy_training not false")
    if operator_plan.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_plan physical authority not false")
    expected_operator_plan_status = expect.get(
        "operator_plan_status",
        (
            "candidate_locked_operator_decision_required"
            if expected_source_lock_ready
            else "candidate_operator_intake_inputs_incomplete"
        ),
    )
    if operator_plan.get("status") != expected_operator_plan_status:
        errors.append(
            f"{case_id}.candidate_operator_intake_plan.status expected "
            f"{expected_operator_plan_status!r}, got {operator_plan.get('status')!r}"
        )
    if operator_plan.get("source_lock_ready_for_review") is not expected_source_lock_ready:
        errors.append(
            f"{case_id}.candidate_operator_intake_plan.source_lock_ready_for_review invalid"
        )
    operator_command_plan = summary.get("candidate_operator_command_plan")
    operator_command_plan = (
        operator_command_plan if isinstance(operator_command_plan, dict) else {}
    )
    if (
        summary.get("candidate_operator_command_plan_model_authority")
        != "candidate_operator_command_plan_not_authority"
    ):
        errors.append(
            f"{case_id}.candidate_operator_command_plan_model_authority invalid"
        )
    if (
        operator_command_plan.get("model_authority")
        != "candidate_operator_command_plan_not_authority"
    ):
        errors.append(f"{case_id}.candidate_operator_command_plan.model_authority invalid")
    expected_command_plan_status = (
        "candidate_operator_commands_ready_for_pinned_source_review"
        if expected_commit_sha_valid
        else "candidate_operator_commands_need_pinned_commit"
    )
    if operator_command_plan.get("status") != expected_command_plan_status:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.status expected "
            f"{expected_command_plan_status!r}, got {operator_command_plan.get('status')!r}"
        )
    if (
        summary.get("candidate_operator_command_plan_status")
        != expected_command_plan_status
    ):
        errors.append(
            f"{case_id}.candidate_operator_command_plan_status expected "
            f"{expected_command_plan_status!r}, got "
            f"{summary.get('candidate_operator_command_plan_status')!r}"
        )
    if operator_command_plan.get("ready_for_model_backed_ik") is not False:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.ready_for_model_backed_ik not false"
        )
    if operator_command_plan.get("ready_for_policy_training") is not False:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.ready_for_policy_training not false"
        )
    if (
        operator_command_plan.get("observed_evidence_is_physical_so101_authority")
        is not False
    ):
        errors.append(f"{case_id}.candidate_operator_command_plan physical authority not false")
    if operator_command_plan.get("source_lock_ready_for_review") is not expected_source_lock_ready:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.source_lock_ready_for_review invalid"
        )
    if operator_command_plan.get("upstream_commit_sha_valid") is not expected_commit_sha_valid:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.upstream_commit_sha_valid invalid"
        )
    if operator_command_plan.get("selected_intake_option_id") != expected_selected_option:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.selected_intake_option_id invalid"
        )
    expected_selected_command_count = 0
    if expected_selected_option == "external_pinned_source_root":
        expected_selected_command_count = 9
    elif expected_selected_option == "vendor_locked_bundle":
        expected_selected_command_count = 7
    if (
        operator_command_plan.get("selected_option_command_count")
        != expected_selected_command_count
    ):
        errors.append(
            f"{case_id}.candidate_operator_command_plan.selected_option_command_count invalid"
        )
    if (
        operator_handoff.get("selected_option_command_count")
        != expected_selected_command_count
    ):
        errors.append(
            f"{case_id}.candidate_operator_intake_handoff.selected_option_command_count invalid"
        )
    if (
        operator_command_plan.get("selected_option_review_requirement_count")
        != expected_requirement_count
    ):
        errors.append(
            f"{case_id}.candidate_operator_command_plan.selected_option_review_requirement_count invalid"
        )
    if (
        operator_command_plan.get("selected_option_review_requirement_ids")
        != expected_requirement_ids
    ):
        errors.append(
            f"{case_id}.candidate_operator_command_plan.selected_option_review_requirement_ids invalid"
        )
    command_plan_requirements = operator_command_plan.get(
        "selected_option_review_requirements"
    )
    command_plan_requirements = (
        command_plan_requirements
        if isinstance(command_plan_requirements, list)
        else []
    )
    if len(command_plan_requirements) != expected_requirement_count:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.selected_option_review_requirements count invalid"
        )
    review_handoff_artifacts = operator_command_plan.get("review_handoff_artifacts")
    review_handoff_artifacts = (
        review_handoff_artifacts if isinstance(review_handoff_artifacts, list) else []
    )
    handoff_artifact_ids = {
        str(artifact.get("artifact_id"))
        for artifact in review_handoff_artifacts
        if isinstance(artifact, dict)
    }
    required_handoff_artifact_ids = {
        "candidate_source_lock_json",
        "candidate_source_lock_digests_csv",
        "candidate_operator_intake_requirements_csv",
        "candidate_direct_review_manifest_template_json",
    }
    if not required_handoff_artifact_ids <= handoff_artifact_ids:
        errors.append(
            f"{case_id}.candidate_operator_command_plan.review_handoff_artifacts "
            f"missing {sorted(required_handoff_artifact_ids - handoff_artifact_ids)!r}"
        )
    for artifact in review_handoff_artifacts:
        if not isinstance(artifact, dict):
            continue
        if not artifact.get("path"):
            errors.append(
                f"{case_id}.candidate_operator_command_plan.review_handoff_artifacts missing path"
            )
        if artifact.get("authority_boundary") in {None, "", "reviewed"}:
            errors.append(
                f"{case_id}.candidate_operator_command_plan.review_handoff_artifacts invalid authority boundary"
            )
    blockers_until_reviewed = operator_command_plan.get("authority_blockers_until_reviewed")
    blockers_until_reviewed = (
        blockers_until_reviewed if isinstance(blockers_until_reviewed, list) else []
    )
    for blocker_fragment in (
        "gripper linear-joint mapping",
        "license and provenance review evidence",
        "reviewed bundle manifest checker",
        "reviewed MuJoCo bundle gate",
        "pinned upstream commit",
    ):
        if not any(blocker_fragment in str(blocker) for blocker in blockers_until_reviewed):
            errors.append(
                f"{case_id}.candidate_operator_command_plan.authority_blockers_until_reviewed "
                f"missing {blocker_fragment!r}"
            )
    for command_key, minimum_count in (
        ("external_pinned_source_root_commands", 9),
        ("vendor_locked_bundle_commands", 7),
    ):
        commands = operator_command_plan.get(command_key)
        commands = commands if isinstance(commands, list) else []
        if len(commands) < minimum_count:
            errors.append(
                f"{case_id}.candidate_operator_command_plan.{command_key} too short"
            )
        for command in commands:
            if not isinstance(command, dict):
                errors.append(
                    f"{case_id}.candidate_operator_command_plan.{command_key} has invalid row"
                )
                continue
            if command.get("executes_in_smoke") is not False:
                errors.append(
                    f"{case_id}.candidate_operator_command_plan.{command_key} executes in smoke"
                )
            if not command.get("step_id") or not command.get("command"):
                errors.append(
                    f"{case_id}.candidate_operator_command_plan.{command_key} missing step/command"
                )
        step_ids = {
            str(command.get("step_id"))
            for command in commands
            if isinstance(command, dict) and command.get("step_id")
        }
        required_step_ids = (
            {
                "verify_checked_out_soarm100_commit_matches_pin",
                "run_source_inventory_on_candidate_checkout",
                "run_source_inventory_after_source_authority_review",
                "run_integrated_reviewed_authority_gate_after_review",
            }
            if command_key == "external_pinned_source_root_commands"
            else {
                "verify_vendored_so101_source_lock_matches_pin",
                "run_source_inventory_on_vendored_subset",
                "run_source_inventory_after_vendor_source_authority_review",
                "run_integrated_reviewed_authority_gate_after_vendor_review",
            }
        )
        if not required_step_ids <= step_ids:
            errors.append(
                f"{case_id}.candidate_operator_command_plan.{command_key} "
                f"missing source inventory steps {sorted(required_step_ids - step_ids)!r}"
            )
    rerun_plan = summary.get("candidate_reviewed_manifest_rerun_plan")
    rerun_plan = rerun_plan if isinstance(rerun_plan, dict) else {}
    expected_rerun_plan_status = (
        "candidate_reviewed_manifest_rerun_plan_ready"
        if expected_source_lock_ready and expected_selected_option is not None
        else "candidate_reviewed_manifest_rerun_plan_blocked"
    )
    if (
        summary.get("candidate_reviewed_manifest_rerun_plan_model_authority")
        != "candidate_reviewed_manifest_rerun_plan_not_authority"
    ):
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan_model_authority invalid"
        )
    if rerun_plan.get("model_authority") != "candidate_reviewed_manifest_rerun_plan_not_authority":
        errors.append(f"{case_id}.candidate_reviewed_manifest_rerun_plan.model_authority invalid")
    if rerun_plan.get("status") != expected_rerun_plan_status:
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan.status expected "
            f"{expected_rerun_plan_status!r}, got {rerun_plan.get('status')!r}"
        )
    if rerun_plan.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan physical authority not false"
        )
    if rerun_plan.get("ready_for_model_backed_ik") is not False:
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan ready_for_model_backed_ik not false"
        )
    if rerun_plan.get("source_lock_ready_for_review") is not expected_source_lock_ready:
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan source lock readiness invalid"
        )
    if rerun_plan.get("selected_intake_option_id") != expected_selected_option:
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan selected option invalid"
        )
    if rerun_plan.get("selected_option_review_requirement_ids") != expected_requirement_ids:
        errors.append(
            f"{case_id}.candidate_reviewed_manifest_rerun_plan requirement ids invalid"
        )
    rerun_command = rerun_plan.get("manifest_checker_command_template")
    rerun_command = rerun_command if isinstance(rerun_command, list) else []
    for required_token in (
        "scripts/smoke_sim_so101_model_bundle_manifest.py",
        "--manifest-path",
        "--output-dir",
    ):
        if required_token not in rerun_command:
            errors.append(
                f"{case_id}.candidate_reviewed_manifest_rerun_plan command missing {required_token!r}"
            )
    success_conditions = rerun_plan.get("required_success_conditions")
    success_conditions = success_conditions if isinstance(success_conditions, list) else []
    for required_condition in (
        "reviewed_manifest_records_gripper_mapping_authority",
        "reviewed_manifest_records_collision_policy_authority",
        "manifest_checker_reports_ready_for_model_backed_ik_true",
        "manifest_checker_reports_physical_so101_model_authority_ready_true",
        "reviewed_mujoco_bundle_gate_loads_model_and_proves_joint_motion",
    ):
        if required_condition not in success_conditions:
            errors.append(
                f"{case_id}.candidate_reviewed_manifest_rerun_plan missing success condition {required_condition!r}"
            )
    intake_options = operator_plan.get("intake_options")
    intake_options = intake_options if isinstance(intake_options, list) else []
    option_ids = [
        str(option.get("option_id"))
        for option in intake_options
        if isinstance(option, dict)
    ]
    for required_option_id in ("external_pinned_source_root", "vendor_locked_bundle"):
        if required_option_id not in option_ids:
            errors.append(
                f"{case_id}.candidate_operator_intake_plan missing option {required_option_id!r}"
            )
    for option in intake_options:
        if not isinstance(option, dict):
            continue
        option_id = str(option.get("option_id"))
        command_template = option.get("command_template")
        command_template = command_template if isinstance(command_template, list) else []
        if option_id in {"external_pinned_source_root", "vendor_locked_bundle"}:
            if "--operator-intake-decision" not in command_template:
                errors.append(
                    f"{case_id}.candidate_operator_intake_plan option {option_id!r} "
                    "command_template missing --operator-intake-decision"
                )
            if option_id not in [str(part) for part in command_template]:
                errors.append(
                    f"{case_id}.candidate_operator_intake_plan option {option_id!r} "
                    "command_template missing selected option value"
                )
    operator_next_actions = operator_plan.get("next_required_action_ids")
    operator_next_actions = (
        operator_next_actions if isinstance(operator_next_actions, list) else []
    )
    required_operator_action_ids = ["run_reviewed_bundle_manifest_checker"]
    if expected_selected_option is None:
        required_operator_action_ids.append("declare_vendor_or_external_intake_decision")
    for required_action_id in required_operator_action_ids:
        if required_action_id not in operator_next_actions:
            errors.append(
                f"{case_id}.candidate_operator_intake_plan missing action {required_action_id!r}"
            )
    if expected_selected_option is not None and "declare_vendor_or_external_intake_decision" in operator_next_actions:
        errors.append(
            f"{case_id}.candidate_operator_intake_plan kept decision action after selected option"
        )
    manifest_template = seeded_template.get("manifest_template")
    manifest_template = manifest_template if isinstance(manifest_template, dict) else {}
    if (
        expect["model_present"]
        and expected_selected_model_supported
        and manifest_template.get("model_path") != summary.get("model_path")
    ):
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template.model_path not seeded")
    if not expected_selected_model_supported and manifest_template.get("model_path") == summary.get("model_path"):
        errors.append(
            f"{case_id}.candidate_seeded_review_manifest_template seeded unsupported model_path"
        )
    if manifest_template.get("model_sha256") != "<copy-reviewed-sha256-after-review>":
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template.model_sha256 not placeholder")
    direct_digest_handoff = manifest_template.get(
        "candidate_source_lock_digest_handoff"
    )
    direct_digest_handoff = (
        direct_digest_handoff if isinstance(direct_digest_handoff, dict) else {}
    )
    for handoff_name, handoff in (
        ("observed_inputs", digest_handoff),
        ("manifest_template", direct_digest_handoff),
    ):
        if handoff.get("authority_boundary") != "candidate_source_lock_digest_not_authority":
            errors.append(
                f"{case_id}.candidate_seeded_review_manifest_template.{handoff_name} "
                "digest handoff authority invalid"
            )
        if handoff.get("digest_row_count") != expected_digest_row_count:
            errors.append(
                f"{case_id}.candidate_seeded_review_manifest_template.{handoff_name} "
                f"digest_row_count expected {expected_digest_row_count!r}, got "
                f"{handoff.get('digest_row_count')!r}"
            )
        if (
            handoff.get("expected_file_digest_count")
            != expected_expected_digest_row_count
        ):
            errors.append(
                f"{case_id}.candidate_seeded_review_manifest_template.{handoff_name} "
                "expected_file_digest_count invalid"
            )
        if handoff.get("extra_lockable_file_count") != expected_extra_lockable_count:
            errors.append(
                f"{case_id}.candidate_seeded_review_manifest_template.{handoff_name} "
                "extra_lockable_file_count invalid"
            )
        if handoff.get("extra_lockable_relative_paths") != expected_extra_lockable_paths:
            errors.append(
                f"{case_id}.candidate_seeded_review_manifest_template.{handoff_name} "
                "extra_lockable_relative_paths invalid"
            )
    authority = manifest_template.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    if authority.get("reviewed_by") != "<reviewer-or-team>":
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template authority placeholder missing")
    seeded_operator_handoff = observed_inputs.get("candidate_operator_intake_handoff")
    seeded_operator_handoff = (
        seeded_operator_handoff if isinstance(seeded_operator_handoff, dict) else {}
    )
    direct_operator_handoff = manifest_template.get("candidate_operator_intake_handoff")
    direct_operator_handoff = (
        direct_operator_handoff if isinstance(direct_operator_handoff, dict) else {}
    )
    for handoff_name, handoff in (
        ("candidate_seeded_review_manifest_template.observed_inputs", seeded_operator_handoff),
        ("candidate_seeded_review_manifest_template.manifest_template", direct_operator_handoff),
    ):
        if (
            handoff.get("model_authority")
            != "candidate_operator_intake_handoff_not_authority"
        ):
            errors.append(f"{case_id}.{handoff_name}.candidate_operator_intake_handoff model_authority invalid")
        if handoff.get("decision_status") != expected_operator_decision_status:
            errors.append(f"{case_id}.{handoff_name}.candidate_operator_intake_handoff decision_status invalid")
        if handoff.get("selected_intake_option_id") != expected_selected_option:
            errors.append(f"{case_id}.{handoff_name}.candidate_operator_intake_handoff selected option invalid")
        if handoff.get("selected_option_review_requirement_ids") != expected_requirement_ids:
            errors.append(f"{case_id}.{handoff_name}.candidate_operator_intake_handoff requirement ids invalid")
        if handoff.get("ready_for_model_backed_ik") is not False:
            errors.append(f"{case_id}.{handoff_name}.candidate_operator_intake_handoff ready_for_model_backed_ik not false")

    review_checklist = summary.get("candidate_review_checklist")
    review_checklist = review_checklist if isinstance(review_checklist, dict) else {}
    if summary.get("candidate_review_checklist_model_authority") != "candidate_review_checklist_not_authority":
        errors.append(f"{case_id}.candidate_review_checklist_model_authority invalid")
    if review_checklist.get("model_authority") != "candidate_review_checklist_not_authority":
        errors.append(f"{case_id}.candidate_review_checklist.model_authority invalid")
    if review_checklist.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_review_checklist.ready_for_model_backed_ik not false")
    if review_checklist.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(f"{case_id}.candidate_review_checklist physical authority not false")
    if review_checklist.get("row_count") != 12:
        errors.append(f"{case_id}.candidate_review_checklist.row_count invalid")
    if review_checklist.get("required_review_scope_coverage_ready") is not True:
        errors.append(
            f"{case_id}.candidate_review_checklist.required_review_scope_coverage_ready not true"
        )
    if review_checklist.get("missing_required_review_scope_ids") != []:
        errors.append(
            f"{case_id}.candidate_review_checklist.missing_required_review_scope_ids not empty"
        )
    checklist_required_scopes = review_checklist.get("required_review_scopes")
    checklist_required_scopes = (
        checklist_required_scopes
        if isinstance(checklist_required_scopes, list)
        else []
    )
    checklist_actions_by_scope = review_checklist.get(
        "action_ids_by_required_review_scope"
    )
    checklist_actions_by_scope = (
        checklist_actions_by_scope
        if isinstance(checklist_actions_by_scope, dict)
        else {}
    )
    checklist_direct_actions_by_scope = review_checklist.get(
        "direct_action_ids_by_required_review_scope"
    )
    checklist_direct_actions_by_scope = (
        checklist_direct_actions_by_scope
        if isinstance(checklist_direct_actions_by_scope, dict)
        else {}
    )
    expected_actions_by_scope = {
        "gripper_mapping": ["review_gripper_mapping"],
        "collision_policy": ["review_collision_policy"],
    }
    for required_scope, expected_action_ids in expected_actions_by_scope.items():
        if required_scope not in checklist_required_scopes:
            errors.append(
                f"{case_id}.candidate_review_checklist.required_review_scopes missing {required_scope!r}"
            )
        expected_all_action_ids = [
            *expected_action_ids,
            "rerun_reviewed_bundle_manifest_checker",
        ]
        if checklist_actions_by_scope.get(required_scope) != expected_all_action_ids:
            errors.append(
                f"{case_id}.candidate_review_checklist.action_ids_by_required_review_scope[{required_scope!r}] "
                f"expected {expected_all_action_ids!r}, got {checklist_actions_by_scope.get(required_scope)!r}"
            )
        if checklist_direct_actions_by_scope.get(required_scope) != expected_action_ids:
            errors.append(
                f"{case_id}.candidate_review_checklist.direct_action_ids_by_required_review_scope[{required_scope!r}] "
                f"expected {expected_action_ids!r}, got {checklist_direct_actions_by_scope.get(required_scope)!r}"
            )
    seeded_checklist_handoff = observed_inputs.get(
        "candidate_review_checklist_handoff"
    )
    seeded_checklist_handoff = (
        seeded_checklist_handoff
        if isinstance(seeded_checklist_handoff, dict)
        else {}
    )
    direct_checklist_handoff = manifest_template.get(
        "candidate_review_checklist_handoff"
    )
    direct_checklist_handoff = (
        direct_checklist_handoff
        if isinstance(direct_checklist_handoff, dict)
        else {}
    )
    for handoff_name, handoff in (
        ("candidate_seeded_review_manifest_template.observed_inputs", seeded_checklist_handoff),
        ("candidate_seeded_review_manifest_template.manifest_template", direct_checklist_handoff),
    ):
        if (
            handoff.get("model_authority")
            != "candidate_review_checklist_handoff_not_authority"
        ):
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff model_authority invalid")
        if handoff.get("observed_evidence_is_physical_so101_authority") is not False:
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff physical authority not false")
        if handoff.get("ready_for_model_backed_ik") is not False:
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff ready_for_model_backed_ik not false")
        if handoff.get("row_count") != review_checklist.get("row_count"):
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff row_count invalid")
        if (
            handoff.get("required_review_scope_coverage_ready")
            is not review_checklist.get("required_review_scope_coverage_ready")
        ):
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff scope coverage invalid")
        if (
            handoff.get("missing_required_review_scope_ids")
            != review_checklist.get("missing_required_review_scope_ids")
        ):
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff missing scope ids invalid")
        if (
            handoff.get("gripper_mapping_direct_action_ids")
            != checklist_direct_actions_by_scope.get("gripper_mapping")
        ):
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff gripper actions invalid")
        if (
            handoff.get("collision_policy_direct_action_ids")
            != checklist_direct_actions_by_scope.get("collision_policy")
        ):
            errors.append(f"{case_id}.{handoff_name}.candidate_review_checklist_handoff collision actions invalid")
    checklist_action_ids = review_checklist.get("action_ids")
    checklist_action_ids = checklist_action_ids if isinstance(checklist_action_ids, list) else []
    for required_action_id in (
        "pin_upstream_soarm100_commit",
        "select_single_authoritative_model_variant",
        "review_mesh_paths",
        "review_collision_policy",
        "review_joint_limits",
        "review_gripper_mapping",
        "review_target_frame_authority",
        "review_tcp_offset_authority",
        "review_base_to_board_alignment_authority",
        "rerun_reviewed_bundle_manifest_checker",
    ):
        if required_action_id not in checklist_action_ids:
            errors.append(
                f"{case_id}.candidate_review_checklist missing action {required_action_id!r}"
            )

    preview_record = record.get("seeded_template_manifest_preview")
    preview_record = preview_record if isinstance(preview_record, dict) else {}
    preview_summary = preview_record.get("summary")
    preview_summary = preview_summary if isinstance(preview_summary, dict) else {}
    if preview_record.get("attempted") is not True:
        errors.append(f"{case_id}.seeded_template_manifest_checker_preview not attempted")
    if preview_record.get("return_code") != 0:
        errors.append(
            f"{case_id}.seeded_template_manifest_checker_preview return_code "
            f"{preview_record.get('return_code')!r}"
        )
    if preview_summary.get("ok") is not True:
        errors.append(f"{case_id}.seeded_template_manifest_checker_preview ok not true")
    if preview_summary.get("model_authority") != "reviewed_bundle_required":
        errors.append(
            f"{case_id}.seeded_template_manifest_checker_preview model_authority invalid"
        )
    if preview_summary.get("ready_for_model_backed_ik") is not False:
        errors.append(
            f"{case_id}.seeded_template_manifest_checker_preview ready_for_model_backed_ik not false"
        )
    if preview_summary.get("physical_so101_model_authority_ready") is not False:
        errors.append(
            f"{case_id}.seeded_template_manifest_checker_preview physical authority not false"
        )
    preview_missing_inputs = preview_summary.get("missing_inputs")
    preview_missing_inputs = (
        preview_missing_inputs if isinstance(preview_missing_inputs, list) else []
    )
    if "model_sha256" not in preview_missing_inputs:
        errors.append(
            f"{case_id}.seeded_template_manifest_checker_preview missing model_sha256 not reported"
        )
    if "authority" not in preview_missing_inputs:
        errors.append(
            f"{case_id}.seeded_template_manifest_checker_preview missing authority not reported"
        )

    observations = summary.get("candidate_review_observations")
    observations = observations if isinstance(observations, dict) else {}
    if observations.get("model_authority") != "candidate_review_observations_not_authority":
        errors.append(f"{case_id}.candidate_review_observations.model_authority invalid")
    if observations.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_review_observations.ready_for_model_backed_ik not false")
    if observations.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(
            f"{case_id}.candidate_review_observations observed physical authority not false"
        )
    check(
        "candidate_review_observations.parsed_model_file_count",
        observations.get("parsed_model_file_count"),
        expect["parsed_model_file_count"],
    )
    readme_caveats = observations.get("readme_caveats")
    readme_caveats = readme_caveats if isinstance(readme_caveats, dict) else {}
    for caveat_key, expected_value in expect.get("readme_caveats", {}).items():
        if readme_caveats.get(caveat_key) is not expected_value:
            errors.append(
                f"{case_id}.candidate_review_observations.readme_caveats."
                f"{caveat_key}: expected {expected_value!r}, got {readme_caveats.get(caveat_key)!r}"
            )
    if expect["model_present"]:
        model_file_observations = observations.get("model_file_observations")
        model_file_observations = (
            model_file_observations if isinstance(model_file_observations, list) else []
        )
        parsed_files = [item for item in model_file_observations if item.get("parse_ok") is True]
        if not parsed_files:
            errors.append(f"{case_id}.candidate_review_observations parsed files missing")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": summary.get("status"),
        "source_root": summary.get("source_root"),
        "upstream_commit": (summary.get("upstream") or {}).get("commit")
        if isinstance(summary.get("upstream"), dict)
        else None,
        "upstream_commit_sha_valid": upstream.get("commit_sha_valid"),
        "upstream_commit_status": upstream.get("commit_status"),
        "expected_file_count": summary.get("expected_file_count"),
        "present_expected_file_count": summary.get("present_expected_file_count"),
        "missing_expected_relative_paths": missing_paths,
        "model_present": summary.get("model_present"),
        "selected_model_supported": summary.get("selected_model_supported"),
        "selected_model_status": summary.get("selected_model_status"),
        "model_sha256_observed": summary.get("model_sha256_observed"),
        "model_authority": summary.get("model_authority"),
        "candidate_review_observations_model_authority": summary.get(
            "candidate_review_observations_model_authority"
        ),
        "candidate_model_observation_model_authority": summary.get(
            "candidate_model_observation_model_authority"
        ),
        "candidate_model_observation_row_count": summary.get(
            "candidate_model_observation_row_count"
        ),
        "candidate_model_observation_scene_row_count": summary.get(
            "candidate_model_observation_scene_row_count"
        ),
        "candidate_model_observation_selectable_model_row_count": summary.get(
            "candidate_model_observation_selectable_model_row_count"
        ),
        "candidate_model_observation_parsed_selectable_model_row_count": summary.get(
            "candidate_model_observation_parsed_selectable_model_row_count"
        ),
        "candidate_model_observation_selected_model_row_count": summary.get(
            "candidate_model_observation_selected_model_row_count"
        ),
        "candidate_source_lock_model_authority": summary.get(
            "candidate_source_lock_model_authority"
        ),
        "candidate_source_lock_status": source_lock.get("status"),
        "candidate_source_lock_ready_for_review": source_lock.get(
            "source_lock_ready_for_review"
        ),
        "candidate_source_lock_digest_model_authority": summary.get(
            "candidate_source_lock_digest_model_authority"
        ),
        "candidate_source_lock_digest_row_count": summary.get(
            "candidate_source_lock_digest_row_count"
        ),
        "candidate_source_lock_expected_file_digest_count": summary.get(
            "candidate_source_lock_expected_file_digest_count"
        ),
        "candidate_source_lock_extra_lockable_file_count": summary.get(
            "candidate_source_lock_extra_lockable_file_count"
        ),
        "candidate_source_lock_extra_lockable_relative_paths": summary.get(
            "candidate_source_lock_extra_lockable_relative_paths"
        ),
        "candidate_source_lock_selected_model_digest_row_count": summary.get(
            "candidate_source_lock_selected_model_digest_row_count"
        ),
        "candidate_source_lock_selected_model_observation_authority": (
            selected_model_observation.get("authority_boundary")
        ),
        "candidate_source_lock_selected_model_observation_observed": (
            selected_model_observation.get("observed")
        ),
        "candidate_source_lock_selected_model_observation_parse_ok": (
            selected_model_observation.get("parse_ok")
        ),
        "candidate_source_lock_selected_model_observation_root_tag": (
            selected_model_observation.get("root_tag")
        ),
        "candidate_source_lock_selected_model_observation_joint_count": (
            selected_model_observation.get("joint_count")
        ),
        "candidate_source_lock_selected_model_expected_joint_coverage_status": (
            selected_model_observation.get("expected_joint_coverage_status")
        ),
        "candidate_source_lock_selected_model_expected_joint_observed_count": (
            selected_model_observation.get("expected_joint_observed_count")
        ),
        "candidate_source_lock_selected_model_expected_joint_missing_count": (
            selected_model_observation.get("expected_joint_missing_count")
        ),
        "candidate_source_lock_selected_model_unexpected_joint_count": (
            selected_model_observation.get("unexpected_joint_count")
        ),
        "candidate_source_lock_selected_model_observation_mesh_reference_count": (
            selected_model_observation.get("mesh_reference_count")
        ),
        "candidate_source_lock_selected_model_mesh_reference_digest_coverage_status": (
            selected_model_observation.get("mesh_reference_digest_coverage_status")
        ),
        "candidate_source_lock_selected_model_mesh_reference_digest_match_count": (
            selected_model_observation.get("mesh_reference_digest_match_count")
        ),
        "candidate_source_lock_selected_model_mesh_reference_digest_missing_count": (
            selected_model_observation.get("mesh_reference_digest_missing_count")
        ),
        "candidate_direct_template_digest_handoff_authority": (
            direct_digest_handoff.get("authority_boundary")
        ),
        "candidate_direct_template_digest_handoff_row_count": (
            direct_digest_handoff.get("digest_row_count")
        ),
        "candidate_direct_template_digest_handoff_expected_file_count": (
            direct_digest_handoff.get("expected_file_digest_count")
        ),
        "candidate_direct_template_digest_handoff_extra_lockable_file_count": (
            direct_digest_handoff.get("extra_lockable_file_count")
        ),
        "candidate_direct_template_digest_handoff_extra_lockable_relative_paths": (
            direct_digest_handoff.get("extra_lockable_relative_paths")
        ),
        "candidate_operator_intake_plan_model_authority": summary.get(
            "candidate_operator_intake_plan_model_authority"
        ),
        "candidate_operator_intake_plan_status": operator_plan.get("status"),
        "candidate_operator_intake_decision_status": operator_plan.get(
            "decision_status"
        ),
        "candidate_operator_intake_selected_option": operator_plan.get(
            "selected_intake_option_id"
        ),
        "candidate_operator_command_plan_model_authority": summary.get(
            "candidate_operator_command_plan_model_authority"
        ),
        "candidate_operator_command_plan_status": operator_command_plan.get("status"),
        "candidate_operator_command_plan_selected_option_command_count": (
            operator_command_plan.get("selected_option_command_count")
        ),
        "candidate_reviewed_manifest_rerun_plan_model_authority": summary.get(
            "candidate_reviewed_manifest_rerun_plan_model_authority"
        ),
        "candidate_reviewed_manifest_rerun_plan_status": rerun_plan.get("status"),
        "candidate_reviewed_manifest_rerun_plan_selected_option": rerun_plan.get(
            "selected_intake_option_id"
        ),
        "candidate_reviewed_manifest_rerun_plan_source_lock_ready": rerun_plan.get(
            "source_lock_ready_for_review"
        ),
        "candidate_reviewed_manifest_rerun_plan_command_template": rerun_plan.get(
            "manifest_checker_command_template"
        ),
        "candidate_reviewed_manifest_rerun_plan_required_success_conditions": rerun_plan.get(
            "required_success_conditions"
        ),
        "candidate_operator_intake_option_count": len(intake_options),
        "candidate_operator_intake_selected_requirement_count": operator_plan.get(
            "selected_option_review_requirement_count"
        ),
        "candidate_operator_intake_selected_requirement_ids": selected_requirement_ids,
        "candidate_operator_intake_requirement_model_authority": summary.get(
            "candidate_operator_intake_requirement_model_authority"
        ),
        "candidate_operator_intake_requirement_row_count": summary.get(
            "candidate_operator_intake_requirement_row_count"
        ),
        "candidate_operator_intake_selected_requirement_row_count": summary.get(
            "candidate_operator_intake_selected_requirement_row_count"
        ),
        "candidate_operator_intake_unselected_requirement_row_count": summary.get(
            "candidate_operator_intake_unselected_requirement_row_count"
        ),
        "candidate_operator_intake_selected_requirement_row_ids": (
            selected_requirement_row_ids
        ),
        "candidate_operator_intake_handoff_model_authority": summary.get(
            "candidate_operator_intake_handoff_model_authority"
        ),
        "candidate_operator_intake_handoff_decision_status": (
            operator_handoff.get("decision_status")
        ),
        "candidate_operator_intake_handoff_selected_option": (
            operator_handoff.get("selected_intake_option_id")
        ),
        "candidate_operator_intake_handoff_selected_requirement_ids": (
            operator_handoff.get("selected_option_review_requirement_ids")
        ),
        "candidate_operator_intake_handoff_selected_command_count": (
            operator_handoff.get("selected_option_command_count")
        ),
        "candidate_review_checklist_model_authority": summary.get(
            "candidate_review_checklist_model_authority"
        ),
        "candidate_review_checklist_row_count": review_checklist.get("row_count"),
        "candidate_review_checklist_scope_coverage_ready": review_checklist.get(
            "required_review_scope_coverage_ready"
        ),
        "candidate_review_checklist_missing_required_review_scope_ids": (
            review_checklist.get("missing_required_review_scope_ids")
        ),
        "candidate_review_checklist_gripper_mapping_direct_action_ids": (
            (
                review_checklist.get("direct_action_ids_by_required_review_scope")
                or {}
            ).get("gripper_mapping")
        ),
        "candidate_review_checklist_collision_policy_direct_action_ids": (
            (
                review_checklist.get("direct_action_ids_by_required_review_scope")
                or {}
            ).get("collision_policy")
        ),
        "candidate_direct_template_checklist_handoff_authority": (
            direct_checklist_handoff.get("model_authority")
        ),
        "candidate_direct_template_checklist_handoff_scope_coverage_ready": (
            direct_checklist_handoff.get("required_review_scope_coverage_ready")
        ),
        "candidate_direct_template_checklist_handoff_missing_required_scope_ids": (
            direct_checklist_handoff.get("missing_required_review_scope_ids")
        ),
        "candidate_direct_template_checklist_handoff_gripper_mapping_direct_action_ids": (
            direct_checklist_handoff.get("gripper_mapping_direct_action_ids")
        ),
        "candidate_direct_template_checklist_handoff_collision_policy_direct_action_ids": (
            direct_checklist_handoff.get("collision_policy_direct_action_ids")
        ),
        "candidate_seeded_review_manifest_template_model_authority": summary.get(
            "candidate_seeded_review_manifest_template_model_authority"
        ),
        "candidate_review_observations_parsed_model_file_count": observations.get(
            "parsed_model_file_count"
        ),
        "candidate_readme_gripper_mapping_caveat": readme_caveats.get(
            "gripper_linear_joint_mapping_not_reflected"
        ),
        "candidate_readme_base_collision_caveat": readme_caveats.get(
            "base_collision_meshes_removed"
        ),
        "seeded_template_manifest_checker_status": preview_summary.get("status"),
        "seeded_template_manifest_checker_ready_for_model_backed_ik": preview_summary.get(
            "ready_for_model_backed_ik"
        ),
        "seeded_template_manifest_checker_physical_ready": preview_summary.get(
            "physical_so101_model_authority_ready"
        ),
        "seeded_template_manifest_checker_missing_inputs": preview_missing_inputs,
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "observed_evidence_is_physical_so101_authority": summary.get(
            "observed_evidence_is_physical_so101_authority"
        ),
        "next_required_action_ids": next_actions,
        "summary_path": record.get("summary_path"),
        "errors": errors,
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Public Candidate Intake Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_case_ids`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['summary_json']}`",
        f"- `cases_csv`: `{summary['cases_csv']}`",
        "",
        "## Cases",
        "",
        "| Case | Status | OK | Model Present | Parsed Model Files | Gripper Caveat | Base Collision Caveat | Seeded Template Checker | Ready For Model-Backed IK |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        lines.append(
            "| `{case_id}` | `{status}` | `{ok}` | `{model_present}` | `{parsed}` | `{gripper}` | `{base_collision}` | `{checker}` | `{ready}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                ok=str(case["ok"]).lower(),
                model_present=str(case["model_present"]).lower(),
                parsed=case["candidate_review_observations_parsed_model_file_count"],
                gripper=str(case["candidate_readme_gripper_mapping_caveat"]).lower(),
                base_collision=str(case["candidate_readme_base_collision_caveat"]).lower(),
                checker=case["seeded_template_manifest_checker_status"],
                ready=str(case["ready_for_model_backed_ik"]).lower(),
            )
        )
    lines.extend(
        [
            "",
            "Synthetic fixture files are hardware-free matrix data only. They do not prove reviewed physical SO-101 authority.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def compact_child_record(record: dict[str, Any]) -> dict[str, Any]:
    compact = dict(record)
    preview = compact.get("seeded_template_manifest_preview")
    preview = preview if isinstance(preview, dict) else {}
    preview_summary = preview.get("summary")
    preview_summary = preview_summary if isinstance(preview_summary, dict) else {}
    compact["seeded_template_manifest_preview"] = {
        "attempted": preview.get("attempted"),
        "return_code": preview.get("return_code"),
        "direct_manifest_path": preview.get("direct_manifest_path"),
        "summary_path": preview.get("summary_path"),
        "stdout_path": preview.get("stdout_path"),
        "stderr_path": preview.get("stderr_path"),
        "summary_status": preview_summary.get("status"),
        "summary_model_authority": preview_summary.get("model_authority"),
        "summary_ready_for_model_backed_ik": preview_summary.get(
            "ready_for_model_backed_ik"
        ),
        "summary_physical_so101_model_authority_ready": preview_summary.get(
            "physical_so101_model_authority_ready"
        ),
        "summary_missing_inputs": preview_summary.get("missing_inputs"),
    }
    return compact


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir = output_dir / "fixtures"
    cases: list[dict[str, Any]] = []
    child_records: list[dict[str, Any]] = []
    for spec in case_specs(fixtures_dir):
        record, child_summary = run_case(
            case_id=spec["case_id"],
            case_args=spec["args"],
            python_path=args.python,
            output_dir=output_dir,
        )
        child_records.append(compact_child_record(record))
        cases.append(summarize_case(record, child_summary, spec["expect"]))

    failed_case_ids = [case["case_id"] for case in cases if not case["ok"]]
    cases_with_extra_lockable_files = [
        case["case_id"]
        for case in cases
        if int(case.get("candidate_source_lock_extra_lockable_file_count") or 0) > 0
    ]
    summary_path = output_dir / "so101_public_candidate_intake_matrix_summary.json"
    csv_path = output_dir / "so101_public_candidate_intake_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": not failed_case_ids,
        "status": "ok" if not failed_case_ids else "failed",
        "model_authority": "public_candidate_intake_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "network_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": failed_case_ids,
        "cases_with_extra_lockable_files": cases_with_extra_lockable_files,
        "case_count_with_extra_lockable_files": len(cases_with_extra_lockable_files),
        "cases": cases,
        "child_records": child_records,
        "summary_json": str(summary_path),
        "cases_csv": str(csv_path),
        "readme_md": str(readme_path),
    }
    write_json(summary_path, summary)
    write_csv(csv_path, cases)
    write_readme(readme_path, summary)
    print(
        json.dumps(
            {
                "ok": summary["ok"],
                "status": summary["status"],
                "case_count": summary["case_count"],
                "case_count_with_extra_lockable_files": summary[
                    "case_count_with_extra_lockable_files"
                ],
                "failed_case_ids": summary["failed_case_ids"],
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
