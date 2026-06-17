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
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_depth_capture_plan_bridge_smoke"
SCHEMA = "lerobot.sim.real_depth_capture_plan_manifest_bridge_smoke.v1"
CHECKER = REPO_ROOT / "scripts" / "smoke_sim_reference_capture_manifest.py"
PLANNER = REPO_ROOT / "scripts" / "plan_real_depth_capture_session.py"
CHECK_JSON_NAME = "reference_capture_manifest_check.json"
SUMMARY_JSON_NAME = "real_depth_capture_plan_manifest_bridge_smoke_summary.json"
SUMMARY_CSV_NAME = "real_depth_capture_plan_manifest_bridge_smoke_cases.csv"
README_NAME = "README.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free regression smoke for the reference-capture-manifest "
            "evidence bridge in plan_real_depth_capture_session.py."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child smoke/planner invocations.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def python_command(path: Path) -> str:
    text = str(path.expanduser())
    if path.is_absolute() or "/" in text:
        return text
    return shutil.which(text) or text


def path_within(path: str | Path | None, root: Path) -> bool:
    if path is None:
        return False
    try:
        Path(path).expanduser().resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def run_child(command: list[str], *, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path.write_text(result.stdout)
        stderr_path.write_text(result.stderr)
        exit_code = result.returncode
    except FileNotFoundError as exc:
        stdout_path.write_text("")
        stderr_path.write_text(str(exc) + "\n")
        exit_code = 127
    return {
        "command": command,
        "exit_code": exit_code,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def create_ready_manifest_inputs(output_dir: Path) -> Path:
    input_dir = output_dir / "synthetic_ready_inputs"
    media_dir = input_dir / "local_placeholders"
    sidecar_dir = input_dir / "sidecars"
    media_dir.mkdir(parents=True, exist_ok=True)
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    depth_media = media_dir / "depth_reference_001.media-placeholder"
    pick_place_media = media_dir / "pick_place_001.media-placeholder"
    depth_media.write_text(
        "Synthetic path-existence placeholder for bridge smoke; not image or video content.\n"
    )
    pick_place_media.write_text(
        "Synthetic path-existence placeholder for bridge smoke; not image or video content.\n"
    )

    write_json(
        sidecar_dir / "depth_reference_001.json",
        {
            "schema": "lerobot.sim.reference_capture_depth_sidecar.synthetic.v1",
            "capture_id": "synthetic_depth_reference_001",
            "measured_depth_targets": [
                {
                    "id": "board_center_range",
                    "distance_m": 0.506,
                    "pixel_xy": [320.0, 207.0],
                }
            ],
            "notes": "Synthetic metadata-only sidecar for planner bridge readiness smoke.",
        },
    )
    write_json(
        sidecar_dir / "pick_place_001_metadata.json",
        {
            "schema": "lerobot.sim.reference_pick_place_metadata.synthetic.v1",
            "capture_id": "synthetic_pick_place_001",
            "event_markers": [
                {"id": "pickup", "time_s": 1.0},
                {"id": "release", "time_s": 2.0},
            ],
            "notes": "Synthetic metadata-only sidecar for planner bridge readiness smoke.",
        },
    )

    manifest_path = input_dir / "reference_capture_manifest.ready_bridge_synthetic.json"
    write_json(
        manifest_path,
        {
            "schema": "lerobot.sim.reference_capture_manifest.v1",
            "media_assets_copied_into_repo": False,
            "local_only_no_copy_policy": {
                "enabled": True,
                "operator_acknowledged": True,
                "scope": "synthetic smoke placeholders under output directory only",
            },
            "provenance": {
                "capture_operator": "synthetic-smoke",
                "capture_date_utc": "2026-06-16",
                "source": "deterministic hardware-free bridge smoke",
                "camera_id": "synthetic_bridge_camera",
            },
            "review": {
                "reviewed_by": "synthetic-smoke",
                "review_date_utc": "2026-06-16",
                "review_status": "operator_reviewed",
            },
            "depth_reference_captures": [
                {
                    "capture_id": "synthetic_depth_reference_001",
                    "media_path": "local_placeholders/depth_reference_001.media-placeholder",
                    "depth_sidecar_path": "sidecars/depth_reference_001.json",
                    "measured_depth_targets": [
                        {
                            "id": "board_center_range",
                            "distance_m": 0.506,
                            "pixel_xy": [320.0, 207.0],
                        }
                    ],
                    "board_camera_pose_notes": "Synthetic pose notes for input-readiness bridge smoke only.",
                    "camera_intrinsics_or_capture_metadata": {
                        "status": "synthetic metadata present"
                    },
                }
            ],
            "pick_place_video_captures": [
                {
                    "capture_id": "synthetic_pick_place_001",
                    "media_path": "local_placeholders/pick_place_001.media-placeholder",
                    "capture_metadata_path": "sidecars/pick_place_001_metadata.json",
                    "gripper_arm_visibility_notes": (
                        "Synthetic visibility notes: fingers, wrist, pickup, release, "
                        "and occlusion context named for review only."
                    ),
                    "board_camera_pose_notes": "Synthetic shared board/camera setup notes.",
                }
            ],
        },
    )
    return manifest_path


def path_counts(summary: dict[str, Any]) -> dict[str, int]:
    path_checks = summary.get("path_checks")
    path_checks = [row for row in path_checks if isinstance(row, dict)] if isinstance(path_checks, list) else []
    missing = summary.get("missing_path_checks")
    missing = [row for row in missing if isinstance(row, dict)] if isinstance(missing, list) else []
    return {
        "path_check_count": len(path_checks),
        "media_path_check_count": sum(1 for row in path_checks if row.get("category") == "media"),
        "sidecar_path_check_count": sum(1 for row in path_checks if row.get("category") == "sidecar"),
        "missing_path_count": len(missing),
        "present_path_count": len(path_checks) - len(missing),
    }


def write_ready_suite_summary(*, output_dir: Path, ready_check: dict[str, Any]) -> Path:
    suite_dir = output_dir / "ready_suite_summary"
    suite_dir.mkdir(parents=True, exist_ok=True)
    reference_capture_manifest = {
        "ok": bool(ready_check.get("ok")),
        "status": ready_check.get("status"),
        "summary_path": ready_check.get("summary_path"),
        "csv_path": ready_check.get("csv_path"),
        "readme_path": ready_check.get("readme_path"),
        "output_dir": ready_check.get("output_dir"),
        "artifact_paths": {
            "summary_json": ready_check.get("summary_path"),
            "csv": ready_check.get("csv_path"),
            "readme_md": ready_check.get("readme_path"),
        },
        "source_configuration": {
            "supplied": True,
            "requested_path": ready_check.get("manifest_path"),
            "notes": [
                "Synthetic suite wrapper for planner bridge smoke only.",
                "Media placeholder paths are local to the smoke output directory.",
            ],
        },
        "manifest_path": ready_check.get("manifest_path"),
        "manifest_schema": ready_check.get("manifest_schema"),
        "expected_manifest_schema": ready_check.get("expected_manifest_schema"),
        "ready_for_calibration_grade_simcamera_tuning": bool(
            ready_check.get("ready_for_calibration_grade_simcamera_tuning")
        ),
        "depth_reference_capture_count": int(ready_check.get("depth_reference_capture_count") or 0),
        "pick_place_video_capture_count": int(ready_check.get("pick_place_video_capture_count") or 0),
        "diagnostics": ready_check.get("diagnostics") if isinstance(ready_check.get("diagnostics"), list) else [],
        "gaps": ready_check.get("diagnostics") if isinstance(ready_check.get("diagnostics"), list) else [],
        "media_assets_copied_into_repo": ready_check.get("media_assets_copied_into_repo"),
        "local_only_no_copy_policy": ready_check.get("local_only_no_copy_policy"),
        "provenance_present": ready_check.get("provenance_present"),
        "review_present": ready_check.get("review_present"),
        "path_checks": ready_check.get("path_checks") if isinstance(ready_check.get("path_checks"), list) else [],
        "missing_path_checks": (
            ready_check.get("missing_path_checks")
            if isinstance(ready_check.get("missing_path_checks"), list)
            else []
        ),
        **path_counts(ready_check),
        "notes": [
            "This is an input-readiness gate for local real-reference captures and sidecars.",
            "Readiness does not claim physical calibration accuracy or mutate SimCamera tuning.",
            "Media assets are never copied into the repository or suite artifact directory.",
        ],
    }
    suite_summary = {
        "schema": "lerobot.sim.calibration_regression_summary.synthetic_bridge_smoke.v1",
        "ok": True,
        "status": "ok",
        "output_dir": str(suite_dir),
        "reference_capture_manifest": reference_capture_manifest,
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "robot_motion_skipped": True,
        "openai_skipped": True,
        "notes": [
            "Synthetic wrapper used to exercise plan_real_depth_capture_session.py --calibration-suite-summary-json.",
        ],
    }
    path = suite_dir / "calibration_regression_summary.ready_bridge_synthetic.json"
    write_json(path, suite_summary)
    return path


def run_planner_case(
    *,
    case_id: str,
    scenario_label: str,
    python: str,
    output_dir: Path,
    evidence_arg: str,
    evidence_path: Path,
    selected_manifest_path: Path,
    fixture_manifest_path: Path,
) -> dict[str, Any]:
    plan_dir = output_dir / case_id
    command = [
        python,
        str(PLANNER),
        "--manifest",
        str(selected_manifest_path),
        "--real-capture-fixture-manifest",
        str(fixture_manifest_path),
        "--scenario-label",
        scenario_label,
        "--output-dir",
        str(plan_dir),
        "--python",
        python,
        evidence_arg,
        str(evidence_path),
    ]
    run = run_child(
        command,
        stdout_path=plan_dir / "planner_stdout.json",
        stderr_path=plan_dir / "planner_stderr.txt",
    )
    plan_json = plan_dir / f"{scenario_label}_real_depth_capture_plan.json"
    plan_markdown = plan_dir / f"{scenario_label}_real_depth_capture_plan.md"
    plan_summary: dict[str, Any] = {}
    if plan_json.exists():
        plan_summary = read_json(plan_json)
    evidence = plan_summary.get("reference_capture_manifest_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    next_actions = evidence.get("next_operator_actions")
    next_actions = [row for row in next_actions if isinstance(row, dict)] if isinstance(next_actions, list) else []
    no_copy = evidence.get("no_copy_status")
    no_copy = no_copy if isinstance(no_copy, dict) else {}
    return {
        "case_id": case_id,
        "scenario_label": scenario_label,
        "evidence_arg": evidence_arg,
        "evidence_path": str(evidence_path),
        "planner_run": run,
        "planner_exit_code": run["exit_code"],
        "plan_json": str(plan_json),
        "plan_markdown": str(plan_markdown),
        "plan_json_under_output_dir": path_within(plan_json, output_dir),
        "plan_markdown_under_output_dir": path_within(plan_markdown, output_dir),
        "plan_ok": bool(plan_summary.get("ok")),
        "evidence_source_kind": evidence.get("source_kind"),
        "evidence_status": evidence.get("status"),
        "ready_for_calibration_grade_simcamera_tuning": bool(
            evidence.get("ready_for_calibration_grade_simcamera_tuning")
        ),
        "depth_reference_capture_count": int(evidence.get("depth_reference_capture_count") or 0),
        "pick_place_video_capture_count": int(evidence.get("pick_place_video_capture_count") or 0),
        "path_check_count": int(evidence.get("path_check_count") or 0),
        "media_path_check_count": int(evidence.get("media_path_check_count") or 0),
        "sidecar_path_check_count": int(evidence.get("sidecar_path_check_count") or 0),
        "missing_path_count": int(evidence.get("missing_path_count") or 0),
        "diagnostics": evidence.get("diagnostics") if isinstance(evidence.get("diagnostics"), list) else [],
        "gaps": evidence.get("gaps") if isinstance(evidence.get("gaps"), list) else [],
        "media_assets_copied_into_repo": evidence.get("media_assets_copied_into_repo"),
        "no_copy_status": no_copy.get("status"),
        "provenance_present": evidence.get("provenance_present"),
        "review_present": evidence.get("review_present"),
        "input_readiness_only": bool(evidence.get("input_readiness_only")),
        "physical_calibration_truth": bool(evidence.get("physical_calibration_truth")),
        "caveat": evidence.get("caveat"),
        "next_operator_action_ids": [
            str(row.get("id")) for row in next_actions if isinstance(row.get("id"), str)
        ],
        "next_operator_actions": next_actions,
    }


def add_assertion(assertions: list[dict[str, Any]], name: str, passed: bool, detail: str = "") -> None:
    assertions.append({"name": name, "passed": bool(passed), "detail": detail})


def build_assertions(
    *,
    output_dir: Path,
    missing_run: dict[str, Any],
    missing_check: dict[str, Any],
    ready_run: dict[str, Any],
    ready_check: dict[str, Any],
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    add_assertion(
        assertions,
        "missing_manifest_checker_exited_0",
        missing_run.get("exit_code") == 0,
        str(missing_run.get("stderr_path")),
    )
    add_assertion(
        assertions,
        "missing_manifest_checker_recorded_not_supplied",
        missing_check.get("status") == "reference_capture_manifest_not_supplied",
        str(missing_check.get("status")),
    )
    add_assertion(
        assertions,
        "ready_manifest_checker_exited_0",
        ready_run.get("exit_code") == 0,
        str(ready_run.get("stderr_path")),
    )
    add_assertion(
        assertions,
        "ready_manifest_checker_recorded_ready",
        ready_check.get("status") == "reference_capture_manifest_ready",
        str(ready_check.get("status")),
    )
    add_assertion(
        assertions,
        "ready_manifest_checker_counts_depth_and_pick_place",
        ready_check.get("depth_reference_capture_count") == 1
        and ready_check.get("pick_place_video_capture_count") == 1,
        (
            f"depth={ready_check.get('depth_reference_capture_count')} "
            f"pick_place={ready_check.get('pick_place_video_capture_count')}"
        ),
    )
    add_assertion(
        assertions,
        "ready_manifest_checker_has_no_missing_paths",
        len(ready_check.get("missing_path_checks") if isinstance(ready_check.get("missing_path_checks"), list) else [])
        == 0,
        "missing_path_checks must be empty",
    )
    add_assertion(
        assertions,
        "ready_manifest_checker_no_copy",
        ready_check.get("media_assets_copied_into_repo") is False
        and ready_check.get("copied_media_paths") == [],
        str(ready_check.get("media_assets_copied_into_repo")),
    )

    case_by_id = {case["case_id"]: case for case in cases}
    missing_case = case_by_id["plan_missing_manifest_check"]
    ready_case = case_by_id["plan_ready_suite_summary"]
    for case in cases:
        add_assertion(
            assertions,
            f"{case['case_id']}_planner_exited_0",
            case.get("planner_exit_code") == 0,
            str(case.get("planner_run", {}).get("stderr_path")),
        )
        add_assertion(
            assertions,
            f"{case['case_id']}_planner_wrote_artifacts_under_output_dir",
            case.get("plan_json_under_output_dir") is True
            and case.get("plan_markdown_under_output_dir") is True,
            str(output_dir),
        )
        add_assertion(
            assertions,
            f"{case['case_id']}_planner_reports_input_readiness_not_calibration_truth",
            case.get("input_readiness_only") is True
            and case.get("physical_calibration_truth") is False
            and "physical calibration" in str(case.get("caveat", "")),
            str(case.get("caveat")),
        )

    add_assertion(
        assertions,
        "missing_planner_preserves_reference_capture_manifest_not_supplied",
        missing_case.get("evidence_status") == "reference_capture_manifest_not_supplied",
        str(missing_case.get("evidence_status")),
    )
    add_assertion(
        assertions,
        "missing_planner_records_follow_up_actions",
        {
            "collect_depth_reference",
            "collect_pick_place_video",
            "prepare_sidecars",
            "record_provenance_review",
            "preserve_local_only_no_copy_policy",
        }.issubset(set(missing_case.get("next_operator_action_ids", []))),
        str(missing_case.get("next_operator_action_ids")),
    )
    add_assertion(
        assertions,
        "ready_planner_preserves_suite_ready_evidence",
        ready_case.get("evidence_status") == "reference_capture_manifest_ready"
        and ready_case.get("evidence_source_kind") == "calibration_regression_summary"
        and ready_case.get("ready_for_calibration_grade_simcamera_tuning") is True,
        (
            f"status={ready_case.get('evidence_status')} "
            f"source={ready_case.get('evidence_source_kind')} "
            f"ready={ready_case.get('ready_for_calibration_grade_simcamera_tuning')}"
        ),
    )
    add_assertion(
        assertions,
        "ready_planner_counts_inputs_and_no_missing_paths",
        ready_case.get("depth_reference_capture_count") == 1
        and ready_case.get("pick_place_video_capture_count") == 1
        and ready_case.get("missing_path_count") == 0,
        (
            f"depth={ready_case.get('depth_reference_capture_count')} "
            f"pick_place={ready_case.get('pick_place_video_capture_count')} "
            f"missing_paths={ready_case.get('missing_path_count')}"
        ),
    )
    add_assertion(
        assertions,
        "ready_planner_preserves_no_copy_and_review",
        ready_case.get("media_assets_copied_into_repo") is False
        and ready_case.get("no_copy_status") == "local_only_no_copy_policy_confirmed"
        and ready_case.get("provenance_present") is True
        and ready_case.get("review_present") is True,
        (
            f"no_copy={ready_case.get('no_copy_status')} "
            f"provenance={ready_case.get('provenance_present')} "
            f"review={ready_case.get('review_present')}"
        ),
    )
    add_assertion(
        assertions,
        "ready_planner_records_follow_up_actions",
        {
            "validate_sidecars_and_intake",
            "run_suite_with_reference_capture_manifest",
            "compare_residuals_before_calibration_claims",
        }.issubset(set(ready_case.get("next_operator_action_ids", []))),
        str(ready_case.get("next_operator_action_ids")),
    )
    return assertions


def write_cases_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "evidence_arg",
        "evidence_source_kind",
        "evidence_status",
        "planner_exit_code",
        "plan_ok",
        "ready_for_calibration_grade_simcamera_tuning",
        "depth_reference_capture_count",
        "pick_place_video_capture_count",
        "path_check_count",
        "missing_path_count",
        "media_assets_copied_into_repo",
        "no_copy_status",
        "input_readiness_only",
        "physical_calibration_truth",
        "next_operator_action_ids",
        "plan_json",
        "plan_markdown",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            row = {field: case.get(field, "") for field in fieldnames}
            row["next_operator_action_ids"] = ",".join(case.get("next_operator_action_ids", []))
            writer.writerow(row)


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_escape(value) for value in row) + " |" for row in rows)
    return lines


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    cases = summary.get("cases")
    cases = [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    assertions = summary.get("assertions")
    assertions = (
        [row for row in assertions if isinstance(row, dict)] if isinstance(assertions, list) else []
    )
    lines = [
        "# Real Depth Capture Plan Manifest Bridge Smoke",
        "",
        "This smoke is hardware-free. It does not open cameras, move robot hardware, call OpenAI, copy media, open media, or decode media.",
        "",
        "Synthetic path-existence placeholders and JSON sidecars are created only under the smoke output directory. The ready case proves input-readiness bridge plumbing only; it is not physical calibration truth.",
        "",
        "## Cases",
    ]
    lines.extend(
        markdown_table(
            [
                "Case",
                "Evidence",
                "Status",
                "Planner exit",
                "Ready",
                "Depth",
                "Pick/place",
                "Missing paths",
                "No-copy status",
            ],
            [
                [
                    case.get("case_id"),
                    case.get("evidence_source_kind"),
                    case.get("evidence_status"),
                    case.get("planner_exit_code"),
                    case.get("ready_for_calibration_grade_simcamera_tuning"),
                    case.get("depth_reference_capture_count"),
                    case.get("pick_place_video_capture_count"),
                    case.get("missing_path_count"),
                    case.get("no_copy_status"),
                ]
                for case in cases
            ],
        )
    )
    lines.extend(["", "## Next Operator Actions"])
    for case in cases:
        lines.extend(["", f"### {case.get('case_id')}", ""])
        actions = case.get("next_operator_actions")
        actions = [row for row in actions if isinstance(row, dict)] if isinstance(actions, list) else []
        if not actions:
            lines.append("- No next actions recorded.")
        for action in actions:
            lines.append(f"- `{action.get('id')}`: {action.get('operator_action')}")
    lines.extend(["", "## Assertions"])
    lines.extend(
        markdown_table(
            ["Assertion", "Passed", "Detail"],
            [[row.get("name"), row.get("passed"), row.get("detail")] for row in assertions],
        )
    )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Summary JSON: `{summary.get('summary_path')}`",
            f"- Case CSV: `{summary.get('csv_path')}`",
            f"- Missing checker JSON: `{summary.get('synthetic_inputs', {}).get('missing_manifest_check_json')}`",
            f"- Ready checker JSON: `{summary.get('synthetic_inputs', {}).get('ready_manifest_check_json')}`",
            f"- Ready suite summary JSON: `{summary.get('synthetic_inputs', {}).get('ready_suite_summary_json')}`",
            "",
            "## Caveats",
            "",
            "- `ready_for_calibration_grade_simcamera_tuning: true` means the operator input manifest shape is ready for subsequent review paths.",
            "- It does not prove real SO-101 calibration accuracy, real projection residual quality, or SimCamera tuning correctness.",
            "- Physical calibration claims still require later sidecar validation, intake, and residual comparison artifacts.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    python = python_command(args.python)
    selected_manifest_path = output_dir / "synthetic_inputs" / "selected_real_depth_manifest_not_created.json"
    fixture_manifest_path = output_dir / "synthetic_inputs" / "unused_real_capture_fixture_manifest_not_created.json"

    missing_check_dir = output_dir / "missing_manifest_check"
    missing_run = run_child(
        [python, str(CHECKER), "--output-dir", str(missing_check_dir)],
        stdout_path=missing_check_dir / "checker_stdout.json",
        stderr_path=missing_check_dir / "checker_stderr.txt",
    )
    missing_check_path = missing_check_dir / CHECK_JSON_NAME
    missing_check = read_json(missing_check_path) if missing_check_path.exists() else {}

    ready_manifest_path = create_ready_manifest_inputs(output_dir)
    ready_check_dir = output_dir / "ready_manifest_check"
    ready_run = run_child(
        [
            python,
            str(CHECKER),
            "--manifest-path",
            str(ready_manifest_path),
            "--output-dir",
            str(ready_check_dir),
        ],
        stdout_path=ready_check_dir / "checker_stdout.json",
        stderr_path=ready_check_dir / "checker_stderr.txt",
    )
    ready_check_path = ready_check_dir / CHECK_JSON_NAME
    ready_check = read_json(ready_check_path) if ready_check_path.exists() else {}
    ready_suite_summary_path = write_ready_suite_summary(output_dir=output_dir, ready_check=ready_check)

    cases = [
        run_planner_case(
            case_id="plan_missing_manifest_check",
            scenario_label="missing_reference_capture_manifest_bridge",
            python=python,
            output_dir=output_dir,
            evidence_arg="--capture-manifest-check-json",
            evidence_path=missing_check_path,
            selected_manifest_path=selected_manifest_path,
            fixture_manifest_path=fixture_manifest_path,
        ),
        run_planner_case(
            case_id="plan_ready_suite_summary",
            scenario_label="ready_reference_capture_manifest_bridge",
            python=python,
            output_dir=output_dir,
            evidence_arg="--calibration-suite-summary-json",
            evidence_path=ready_suite_summary_path,
            selected_manifest_path=selected_manifest_path,
            fixture_manifest_path=fixture_manifest_path,
        ),
    ]
    assertions = build_assertions(
        output_dir=output_dir,
        missing_run=missing_run,
        missing_check=missing_check,
        ready_run=ready_run,
        ready_check=ready_check,
        cases=cases,
    )
    failures = [row for row in assertions if not row["passed"]]
    summary_path = output_dir / SUMMARY_JSON_NAME
    csv_path = output_dir / SUMMARY_CSV_NAME
    readme_path = output_dir / README_NAME
    summary = {
        "schema": SCHEMA,
        "ok": not failures,
        "status": "ok" if not failures else "failed",
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "python": python,
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "robot_motion_skipped": True,
        "openai_skipped": True,
        "media_assets_copied_into_repo": False,
        "copied_media_paths": [],
        "media_assets_opened_or_decoded": False,
        "summary_path": str(summary_path),
        "csv_path": str(csv_path),
        "readme_path": str(readme_path),
        "synthetic_inputs": {
            "selected_real_depth_manifest_path": str(selected_manifest_path),
            "unused_real_capture_fixture_manifest_path": str(fixture_manifest_path),
            "ready_manifest_path": str(ready_manifest_path),
            "missing_manifest_check_json": str(missing_check_path),
            "ready_manifest_check_json": str(ready_check_path),
            "ready_suite_summary_json": str(ready_suite_summary_path),
            "placeholders_are_media_content": False,
        },
        "child_runs": {
            "missing_manifest_check": missing_run,
            "ready_manifest_check": ready_run,
        },
        "cases": cases,
        "assertions": assertions,
        "failures": failures,
        "caveats": [
            "This smoke validates planner evidence ingestion and reporting only.",
            "Synthetic readiness is input readiness only, not physical calibration truth.",
            "No photos or videos are copied, opened, decoded, modified, or committed.",
        ],
    }
    write_json(summary_path, summary)
    write_cases_csv(csv_path, cases)
    write_readme(readme_path, summary)
    return summary


def main() -> int:
    args = parse_args()
    summary = build_summary(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
