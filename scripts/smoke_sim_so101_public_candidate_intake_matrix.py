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
        "candidate_seeded_review_manifest_template_model_authority",
        "candidate_review_observations_parsed_model_file_count",
        "candidate_readme_gripper_mapping_caveat",
        "candidate_readme_base_collision_caveat",
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
    return (
        {
            "case_id": case_id,
            "command": command,
            "return_code": result.returncode,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "summary_path": str(summary_path),
        },
        summary,
    )


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
        "candidate_seeded_review_manifest_template_json",
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
        "| Case | Status | OK | Model Present | Parsed Model Files | Gripper Caveat | Base Collision Caveat | Ready For Model-Backed IK |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        lines.append(
            "| `{case_id}` | `{status}` | `{ok}` | `{model_present}` | `{parsed}` | `{gripper}` | `{base_collision}` | `{ready}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                ok=str(case["ok"]).lower(),
                model_present=str(case["model_present"]).lower(),
                parsed=case["candidate_review_observations_parsed_model_file_count"],
                gripper=str(case["candidate_readme_gripper_mapping_caveat"]).lower(),
                base_collision=str(case["candidate_readme_base_collision_caveat"]).lower(),
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
        child_records.append(record)
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
