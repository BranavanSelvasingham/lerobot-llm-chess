#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "calibration_regression_suite"
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
DEFAULT_BASE_PROFILE = "current_gripper_reference"
SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
BASELINE_CORNERS = [[32, 338], [594, 340], [540, 20], [86, 12]]
PERTURBED_CORNERS = [[34, 337], [592, 342], [538, 22], [88, 14]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the hardware-free simulator calibration regression suite: reference media "
            "inventory, real-reference comparison set, ranked calibration session report, "
            "and perception regression fixture manifest."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child smoke scripts.",
    )
    parser.add_argument("--reference-image", type=Path, default=DEFAULT_REFERENCE_IMAGE)
    parser.add_argument("--base-profile", default=DEFAULT_BASE_PROFILE)
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--select-rank", type=int, default=1)
    parser.add_argument(
        "--include-negative-check",
        action="store_true",
        help=(
            "Also run a deliberate empty-inventory comparison-set check and require it to "
            "fail clearly without making the aggregate suite fail."
        ),
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, f"Expected JSON object, got {type(payload).__name__}."
    return payload, None


def run_child(
    *,
    name: str,
    command: list[str],
    output_dir: Path,
    expected_json_path: Path,
    expected_failure: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{name}_stdout.txt"
    stderr_path = output_dir / f"{name}_stderr.txt"
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)

    payload: dict[str, Any] | None = None
    summary_error: str | None = None
    if expected_json_path.is_file():
        payload, summary_error = read_json_object(expected_json_path)
    elif result.returncode == 0 or not expected_failure:
        summary_error = f"Expected summary JSON was not written: {expected_json_path}"

    payload_ok = bool(payload.get("ok", True)) if payload is not None else False
    if expected_failure:
        ok = result.returncode != 0 and (payload is None or not payload_ok)
    else:
        ok = result.returncode == 0 and payload is not None and payload_ok and summary_error is None

    record = {
        "name": name,
        "ok": ok,
        "expected_failure": expected_failure,
        "command": command,
        "return_code": int(result.returncode),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "expected_output_json_path": str(expected_json_path),
        "summary_loaded": payload is not None,
        "summary_error": summary_error,
        "summary_status": payload.get("status") if payload else None,
    }
    return record, payload


def skipped_child(name: str, reason: str, expected_json_path: Path) -> dict[str, Any]:
    return {
        "name": name,
        "ok": False,
        "status": "skipped",
        "reason": reason,
        "command": None,
        "return_code": None,
        "stdout_path": None,
        "stderr_path": None,
        "expected_output_json_path": str(expected_json_path),
        "summary_loaded": False,
    }


def profile_candidate_payload(
    *,
    label: str,
    corners: list[list[int]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    reference_image = args.reference_image.expanduser().resolve()
    return {
        "schema": "lerobot.sim.manual_corner_profile_candidate.v1",
        "base_profile": str(args.base_profile),
        "status": "candidate_only_not_canonical",
        "reference_image_path": str(reference_image),
        "corner_labels": ["a1", "h1", "h8", "a8"],
        "board_corners_xy": [[float(x), float(y)] for x, y in corners],
        "sim_camera_profile_overrides": {
            "width": 640,
            "height": 480,
            "board_corners_xy": [[float(x), float(y)] for x, y in corners],
            "reference_image_path": str(reference_image),
        },
        "suite_candidate_label": label,
    }


def write_candidate_inputs(args: argparse.Namespace, output_dir: Path) -> dict[str, str]:
    candidates_dir = output_dir / "candidates"
    baseline_path = candidates_dir / "baseline_profile_candidate.json"
    perturbed_path = candidates_dir / "perturbed_profile_candidate.json"
    write_json(
        baseline_path,
        profile_candidate_payload(label="baseline", corners=BASELINE_CORNERS, args=args),
    )
    write_json(
        perturbed_path,
        profile_candidate_payload(label="perturbed", corners=PERTURBED_CORNERS, args=args),
    )
    return {
        "baseline_candidate_path": str(baseline_path),
        "perturbed_candidate_path": str(perturbed_path),
    }


def comparison_artifacts(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    comparisons = summary.get("comparisons")
    if not isinstance(comparisons, list):
        return []
    rows: list[dict[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        details = comparison.get("comparison")
        details = details if isinstance(details, dict) else {}
        rows.append(
            {
                "relative_path": comparison.get("relative_path"),
                "summary_path": details.get("summary_path"),
                "visual_artifact_paths": details.get("visual_artifact_paths"),
                "child_artifact_paths": details.get("child_artifact_paths"),
            }
        )
    return rows


def ranking_summary(session: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not session:
        return []
    ranking = session.get("ranking")
    if not isinstance(ranking, list):
        return []
    slim: list[dict[str, Any]] = []
    for item in ranking:
        if not isinstance(item, dict):
            continue
        slim.append(
            {
                "rank": item.get("rank"),
                "candidate_id": item.get("candidate_id"),
                "rank_score": item.get("rank_score"),
                "total_penalty": item.get("total_penalty"),
                "all_smokes_ok": item.get("all_smokes_ok"),
                "smoke_failures": item.get("smoke_failures"),
                "artifact_paths": item.get("artifact_paths"),
            }
        )
    return slim


def selected_from_session(session: dict[str, Any] | None, select_rank: int) -> dict[str, Any] | None:
    for item in ranking_summary(session):
        if item.get("rank") == select_rank:
            return item
    return None


def selected_fixture_artifacts(fixture: dict[str, Any] | None) -> dict[str, str]:
    if not fixture:
        return {}
    artifacts = fixture.get("artifact_paths")
    if not isinstance(artifacts, dict):
        return {}
    wanted_tokens = (
        "comparison_side_by_side",
        "comparison_heatmap",
        "board_pose_annotated",
        "pick_place_release",
        "pick_place_release_capture",
        "fixture",
        "session_summary",
    )
    return {
        str(key): str(value)
        for key, value in sorted(artifacts.items())
        if isinstance(value, str) and any(token in str(key) for token in wanted_tokens)
    }


def matrix_summary_section(matrix: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    scenarios = matrix.get("scenarios") if matrix else None
    scenario_rows = scenarios if isinstance(scenarios, list) else []
    aggregate_status = matrix.get("aggregate_status") if matrix else None
    aggregate_status = aggregate_status if isinstance(aggregate_status, dict) else {}
    selected_frame_paths: dict[str, dict[str, str]] = {}
    release_frame_paths: dict[str, str] = {}
    piece_visibility_by_scenario: dict[str, dict[str, Any]] = {}
    scenario_ids: list[str] = []
    limitations: list[str] = []

    for scenario in scenario_rows:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str):
            continue
        scenario_ids.append(scenario_id)
        frames = scenario.get("selected_frame_paths")
        if isinstance(frames, dict):
            selected_frame_paths[scenario_id] = {
                str(key): str(value)
                for key, value in sorted(frames.items())
                if isinstance(value, str)
            }
            release_path = frames.get("target_release_open_path")
            if isinstance(release_path, str):
                release_frame_paths[scenario_id] = release_path
        visibility = scenario.get("piece_visibility")
        aggregate = visibility.get("aggregate") if isinstance(visibility, dict) else None
        if isinstance(aggregate, dict):
            piece_visibility_by_scenario[scenario_id] = {
                "available": aggregate.get("available"),
                "all_captures_clear_of_gripper": aggregate.get("all_captures_clear_of_gripper"),
                "min_visible_fraction": aggregate.get("min_visible_fraction"),
                "max_occlusion_fraction": aggregate.get("max_occlusion_fraction"),
                "min_clearance_px": aggregate.get("min_clearance_px"),
                "worst_capture_label": aggregate.get("worst_capture_label"),
                "target_release_open": aggregate.get("target_release_open"),
            }
        for limitation in scenario.get("limitations", []):
            if isinstance(limitation, str) and limitation not in limitations:
                limitations.append(limitation)

    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(matrix.get("ok", False)) if matrix else False,
        "status": matrix.get("status") if matrix else None,
        "aggregate_status": aggregate_status,
        "scenario_count": aggregate_status.get("scenario_count", len(scenario_ids)),
        "scenario_ids": scenario_ids,
        "failed_scenario_ids": aggregate_status.get("failed_scenario_ids", []),
        "selected_frame_paths": selected_frame_paths,
        "release_frame_paths": release_frame_paths,
        "piece_visibility": matrix.get("piece_visibility") if matrix else None,
        "piece_visibility_by_scenario": piece_visibility_by_scenario,
        "limitations": limitations,
    }


def run_negative_empty_inventory(
    *,
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    negative_dir = output_dir / "negative_empty_inventory"
    inventory_path = negative_dir / "empty_inventory.json"
    write_json(
        inventory_path,
        {
            "schema": "lerobot.sim.reference_media_inventory.v1",
            "ok": True,
            "repo_root": str(REPO_ROOT),
            "summary": {
                "media_count": 0,
                "image_count": 0,
                "video_count": 0,
                "currently_wired_media_count": 0,
                "active_current_gripper_reference_detected": False,
                "active_current_gripper_reference_path": "archive/chess_test_images/current_view.jpg",
            },
            "media": [],
            "visibility_gaps": [
                {
                    "category": "simulator_reference",
                    "status": "missing",
                    "note": "Synthetic negative-check inventory intentionally contains no media.",
                }
            ],
            "next_recommended_reference_fixture_inputs": [],
        },
    )
    summary_path = negative_dir / "comparison_set_summary.json"
    return run_child(
        name="negative_empty_inventory_comparison_set",
        command=[
            str(args.python.expanduser()),
            str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_comparison_set.py"),
            "--inventory-json",
            str(inventory_path),
            "--output-dir",
            str(negative_dir),
            "--python",
            str(args.python.expanduser()),
        ],
        output_dir=negative_dir,
        expected_json_path=summary_path,
        expected_failure=True,
    )


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_paths = write_candidate_inputs(args, output_dir)
    python = str(args.python.expanduser())

    inventory_dir = output_dir / "inventory"
    inventory_json_path = inventory_dir / "reference_media_inventory.json"
    inventory_record, inventory = run_child(
        name="inventory",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_inventory.py"),
            "--output-dir",
            str(inventory_dir),
        ],
        output_dir=inventory_dir,
        expected_json_path=inventory_json_path,
    )

    comparison_dir = output_dir / "comparison_set"
    comparison_summary_path = comparison_dir / "comparison_set_summary.json"
    if inventory_json_path.is_file():
        comparison_record, comparison = run_child(
            name="comparison_set",
            command=[
                python,
                str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_comparison_set.py"),
                "--inventory-json",
                str(inventory_json_path),
                "--output-dir",
                str(comparison_dir),
                "--python",
                python,
            ],
            output_dir=comparison_dir,
            expected_json_path=comparison_summary_path,
        )
    else:
        comparison_record = skipped_child("comparison_set", "inventory JSON was not available", comparison_summary_path)
        comparison = None

    session_dir = output_dir / "session"
    session_summary_path = session_dir / "session_summary.json"
    session_record, session = run_child(
        name="calibration_session_report",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_calibration_session_report.py"),
            candidate_paths["baseline_candidate_path"],
            candidate_paths["perturbed_candidate_path"],
            "--output-dir",
            str(session_dir),
            "--python",
            python,
            "--source-square",
            str(args.source_square),
            "--target-square",
            str(args.target_square),
        ],
        output_dir=session_dir,
        expected_json_path=session_summary_path,
    )

    fixture_dir = output_dir / "fixture"
    fixture_summary_path = fixture_dir / "fixture_summary.json"
    if session_record["ok"]:
        fixture_record, fixture = run_child(
            name="perception_regression_fixture",
            command=[
                python,
                str(REPO_ROOT / "scripts" / "smoke_sim_perception_regression_fixture.py"),
                str(session_summary_path),
                "--select-rank",
                str(int(args.select_rank)),
                "--output-dir",
                str(fixture_dir),
                "--source-square",
                str(args.source_square),
                "--target-square",
                str(args.target_square),
            ],
            output_dir=fixture_dir,
            expected_json_path=fixture_summary_path,
        )
    else:
        fixture_record = skipped_child(
            "perception_regression_fixture",
            "ranked session summary did not validate",
            fixture_summary_path,
        )
        fixture = None

    matrix_dir = output_dir / "pick_place_scenario_matrix"
    matrix_summary_path = matrix_dir / "scenario_matrix_summary.json"
    matrix_record, matrix = run_child(
        name="pick_place_scenario_matrix",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_pick_place_scenario_matrix.py"),
            "--output-dir",
            str(matrix_dir),
            "--python",
            python,
            "--sim-camera-profile",
            str(args.base_profile),
        ],
        output_dir=matrix_dir,
        expected_json_path=matrix_summary_path,
    )

    negative_record: dict[str, Any] | None = None
    negative_summary: dict[str, Any] | None = None
    if args.include_negative_check:
        negative_record, negative_summary = run_negative_empty_inventory(args=args, output_dir=output_dir)

    child_records = {
        "inventory": inventory_record,
        "comparison_set": comparison_record,
        "calibration_session_report": session_record,
        "perception_regression_fixture": fixture_record,
        "pick_place_scenario_matrix": matrix_record,
    }
    if negative_record is not None:
        child_records["negative_empty_inventory_comparison_set"] = negative_record

    required_ok = all(record["ok"] for record in child_records.values())
    selected_candidate = selected_from_session(session, int(args.select_rank))
    summary_path = output_dir / "calibration_regression_summary.json"
    artifact_index_path = output_dir / "artifact_index.json"
    summary = {
        "schema": SCHEMA,
        "ok": required_ok,
        "status": "ok" if required_ok else "validation_failed",
        "aggregate_status": {
            "ok": required_ok,
            "failed_children": [
                name for name, record in child_records.items() if not bool(record.get("ok"))
            ],
        },
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "python": python,
        "hardware_skipped": True,
        "gui_skipped": True,
        "skipped_markers": {
            "hardware": "Suite and child smokes use simulator/reference media only; no robot hardware paths are invoked.",
            "gui": "Suite passes explicit non-interactive inputs and does not request OpenCV click/display flows.",
        },
        "candidate_inputs": candidate_paths,
        "child_commands": child_records,
        "inventory": {
            "summary_path": str(inventory_json_path),
            "summary": inventory.get("summary") if inventory else None,
            "next_recommended_reference_fixture_inputs": (
                inventory.get("next_recommended_reference_fixture_inputs") if inventory else None
            ),
            "visibility_gaps": inventory.get("visibility_gaps") if inventory else None,
        },
        "comparison_set": {
            "summary_path": str(comparison_summary_path),
            "status": comparison.get("status") if comparison else None,
            "selected_media_count": comparison.get("selected_media_count") if comparison else None,
            "failed_comparison_count": comparison.get("failed_comparison_count") if comparison else None,
            "artifacts": comparison_artifacts(comparison),
        },
        "calibration_session": {
            "summary_path": str(session_summary_path),
            "candidate_count": session.get("candidate_count") if session else None,
            "ranking": ranking_summary(session),
            "selected_candidate": selected_candidate,
        },
        "perception_fixture": {
            "summary_path": str(fixture_summary_path),
            "status": fixture.get("status") if fixture else None,
            "selected_candidate": fixture.get("selected_candidate") if fixture else None,
            "artifact_paths": selected_fixture_artifacts(fixture),
        },
        "pick_place_scenario_matrix": matrix_summary_section(matrix, matrix_summary_path),
        "selected_candidate": {
            "requested_rank": int(args.select_rank),
            "candidate_id": selected_candidate.get("candidate_id") if selected_candidate else None,
            "rank": selected_candidate.get("rank") if selected_candidate else None,
            "rank_score": selected_candidate.get("rank_score") if selected_candidate else None,
            "artifact_paths": selected_candidate.get("artifact_paths") if selected_candidate else None,
        },
        "negative_check": {
            "included": bool(args.include_negative_check),
            "record": negative_record,
            "summary_path": negative_summary.get("comparison_set_summary_path") if negative_summary else None,
            "status": negative_summary.get("status") if negative_summary else None,
        },
        "artifact_index": {
            "path": str(artifact_index_path),
            "status": None,
            "artifact_count": None,
            "missing_artifact_count": None,
        },
        "notes": [
            "This suite intentionally calls existing smoke scripts as subprocesses instead of duplicating their internals.",
            "It does not mutate simulator rendering, camera profiles, perception algorithms, robot execution, dependencies, or canonical calibration constants.",
        ],
    }
    write_json(summary_path, summary)

    artifact_index_record, artifact_index = run_child(
        name="artifact_index",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_calibration_artifact_index.py"),
            str(summary_path),
            "--output-json",
            str(artifact_index_path),
        ],
        output_dir=output_dir,
        expected_json_path=artifact_index_path,
    )
    child_records["artifact_index"] = artifact_index_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["artifact_index"] = {
        "path": str(artifact_index_path),
        "status": artifact_index.get("status") if artifact_index else None,
        "artifact_count": len(artifact_index.get("artifacts", [])) if artifact_index else None,
        "missing_artifact_count": len(artifact_index.get("missing_artifacts", [])) if artifact_index else None,
        "categories": artifact_index.get("categories") if artifact_index else None,
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
