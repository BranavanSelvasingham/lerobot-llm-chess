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
        "expected_file_count",
        "present_expected_file_count",
        "missing_expected_relative_paths",
        "model_present",
        "model_sha256_observed",
        "model_authority",
        "candidate_review_observations_model_authority",
        "candidate_source_lock_model_authority",
        "candidate_source_lock_status",
        "candidate_source_lock_ready_for_review",
        "candidate_operator_intake_plan_model_authority",
        "candidate_operator_intake_plan_status",
        "candidate_operator_intake_decision_status",
        "candidate_operator_intake_selected_option",
        "candidate_operator_intake_option_count",
        "candidate_review_checklist_model_authority",
        "candidate_review_checklist_row_count",
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
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "operator_decision_status": "vendor_or_external_intake_not_declared",
                "selected_intake_option_id": None,
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
                "parsed_model_file_count": 5,
                "readme_caveats": {
                    "base_collision_meshes_removed": True,
                    "gripper_linear_joint_mapping_not_reflected": True,
                    "onshape_to_robot_generated": True,
                    "relative_mesh_paths_declared": True,
                },
                "missing_exact": [],
                "commit_action_present": False,
                "operator_decision_status": "candidate_intake_decision_recorded_not_authority",
                "selected_intake_option_id": "external_pinned_source_root",
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

    check("model_authority", summary.get("model_authority"), "public_candidate_intake_not_authority")
    check(
        "candidate_review_observations_model_authority",
        summary.get("candidate_review_observations_model_authority"),
        "candidate_review_observations_not_authority",
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
        "candidate_seeded_review_manifest_template_json",
        "candidate_direct_review_manifest_template_json",
        "candidate_review_checklist_json",
        "candidate_review_checklist_csv",
        "candidate_operator_intake_plan_json",
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
    source_lock = summary.get("candidate_source_lock")
    source_lock = source_lock if isinstance(source_lock, dict) else {}
    expected_source_lock_status = (
        "candidate_source_lock_ready_for_review"
        if expect["model_present"] and not missing_paths and commit_action_present is False
        else "candidate_source_lock_incomplete"
    )
    expected_source_lock_ready = expected_source_lock_status == "candidate_source_lock_ready_for_review"
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
    if expected_source_lock_ready:
        if source_lock.get("file_digest_count") != summary.get("expected_file_count"):
            errors.append(f"{case_id}.candidate_source_lock.file_digest_count invalid")
        selected_model = source_lock.get("selected_model")
        selected_model = selected_model if isinstance(selected_model, dict) else {}
        if selected_model.get("sha256") != summary.get("model_sha256_observed"):
            errors.append(f"{case_id}.candidate_source_lock selected model digest mismatch")
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
    if operator_plan.get("ready_for_model_backed_ik") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_plan.ready_for_model_backed_ik not false")
    if operator_plan.get("ready_for_policy_training") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_plan.ready_for_policy_training not false")
    if operator_plan.get("observed_evidence_is_physical_so101_authority") is not False:
        errors.append(f"{case_id}.candidate_operator_intake_plan physical authority not false")
    expected_operator_plan_status = (
        "candidate_locked_operator_decision_required"
        if expected_source_lock_ready
        else "candidate_operator_intake_inputs_incomplete"
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
    if expect["model_present"] and manifest_template.get("model_path") != summary.get("model_path"):
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template.model_path not seeded")
    if manifest_template.get("model_sha256") != "<copy-reviewed-sha256-after-review>":
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template.model_sha256 not placeholder")
    authority = manifest_template.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    if authority.get("reviewed_by") != "<reviewer-or-team>":
        errors.append(f"{case_id}.candidate_seeded_review_manifest_template authority placeholder missing")

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
    if review_checklist.get("row_count") != 8:
        errors.append(f"{case_id}.candidate_review_checklist.row_count invalid")
    checklist_action_ids = review_checklist.get("action_ids")
    checklist_action_ids = checklist_action_ids if isinstance(checklist_action_ids, list) else []
    for required_action_id in (
        "pin_upstream_soarm100_commit",
        "select_single_authoritative_model_variant",
        "review_joint_limits_and_gripper_mapping",
        "review_target_frame_tcp_and_base_board_alignment",
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
        "expected_file_count": summary.get("expected_file_count"),
        "present_expected_file_count": summary.get("present_expected_file_count"),
        "missing_expected_relative_paths": missing_paths,
        "model_present": summary.get("model_present"),
        "model_sha256_observed": summary.get("model_sha256_observed"),
        "model_authority": summary.get("model_authority"),
        "candidate_review_observations_model_authority": summary.get(
            "candidate_review_observations_model_authority"
        ),
        "candidate_source_lock_model_authority": summary.get(
            "candidate_source_lock_model_authority"
        ),
        "candidate_source_lock_status": source_lock.get("status"),
        "candidate_source_lock_ready_for_review": source_lock.get(
            "source_lock_ready_for_review"
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
        "candidate_operator_intake_option_count": len(intake_options),
        "candidate_review_checklist_model_authority": summary.get(
            "candidate_review_checklist_model_authority"
        ),
        "candidate_review_checklist_row_count": review_checklist.get("row_count"),
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
