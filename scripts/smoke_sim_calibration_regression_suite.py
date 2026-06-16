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
ARTIFACT_ENTRYPOINT_NAME = "README.md"
ARTIFACT_REPORT_NAME = "artifact_index_report.md"
VISUAL_REVIEW_SUMMARY_NAME = "visual_review_summary.json"
REFERENCE_CAPTURE_CHECKLIST_NAME = "reference_capture_checklist.json"
REAL_PROJECTION_INTAKE_NAME = "real_projection_intake.json"
EVIDENCE_BUNDLE_DIR_NAME = "evidence_bundle"
EVIDENCE_BUNDLE_MD_NAME = "sim_evidence_bundle.md"
EVIDENCE_BUNDLE_JSON_NAME = "sim_evidence_bundle.json"
IK_REACHABILITY_SUMMARY_NAME = "ik_reachability_drill_summary.json"
BASELINE_CORNERS = [[32, 338], [594, 340], [540, 20], [86, 12]]
PERTURBED_CORNERS = [[34, 337], [592, 342], [538, 22], [88, 14]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the hardware-free simulator calibration regression suite: reference media "
            "inventory, real-reference comparison set, ranked calibration session report, "
            "perception regression fixture manifest, and SimCamera pose fixture."
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
    parser.add_argument(
        "--reference-media-manifest",
        type=Path,
        default=None,
        help=(
            "Optional repo-local reference-media manifest passed only to the inventory child. "
            "Default suite and CI behavior remain manifest-free."
        ),
    )
    parser.add_argument(
        "--ik-model-path",
        type=Path,
        default=None,
        help=(
            "Optional SO-101 kinematic model path forwarded to the IK reachability child. "
            "Default suite behavior remains model-free and non-failing."
        ),
    )
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
    parser.add_argument(
        "--skip-artifact-index-report",
        action="store_true",
        help="Do not render the optional Markdown artifact-index report at the end of the suite.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def markdown_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def write_artifact_entrypoint_readme(output_dir: Path, summary: dict[str, Any]) -> Path:
    markers = summary.get("skipped_markers")
    markers = markers if isinstance(markers, dict) else {}
    manifest = summary.get("reference_media_manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    manifest_supplied = bool(manifest.get("supplied"))
    visual_review = summary.get("visual_review")
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    recording = visual_review.get("recording")
    recording = recording if isinstance(recording, dict) else {}
    readme_path = output_dir / ARTIFACT_ENTRYPOINT_NAME
    lines = [
        "# Simulator Calibration Regression Artifacts",
        "",
        f"Open `{ARTIFACT_REPORT_NAME}` first. It is the review report for this artifact bundle.",
        f"Open `{EVIDENCE_BUNDLE_DIR_NAME}/{EVIDENCE_BUNDLE_MD_NAME}` for the focused "
        "depth-calibration evidence bundle.",
        "For image-first inspection, open `visual_review/gripper_camera_pov_annotated_contact_sheet.png` "
        "and `visual_review/pick_place_sequence_distance_annotated_contact_sheet.png`.",
        "",
        "Core summaries and metric tables:",
        "",
        "- `calibration_regression_summary.json`",
        "- `artifact_index.json`",
        f"- `{EVIDENCE_BUNDLE_DIR_NAME}/{EVIDENCE_BUNDLE_MD_NAME}`",
        f"- `{EVIDENCE_BUNDLE_DIR_NAME}/{EVIDENCE_BUNDLE_JSON_NAME}`",
        "- `inventory/reference_media_inventory.json`",
        "- `comparison_set/comparison_set_summary.json`",
        "- `session/session_summary.json`",
        "- `fixture/fixture_summary.json`",
        "- `sim_camera_pose_fixture/sim_camera_pose_fixture_summary.json`",
        "- `ik_reachability_drill/ik_reachability_drill_summary.json`",
        "- `ik_reachability_drill/ik_reachability_drill_rows.csv`",
        "- `ik_reachability_drill/ik_reachability_drill_heatmap.png`",
        "- `gripper_camera_pov_review/gripper_camera_pov_review_summary.json`",
        "- `pick_place_scenario_matrix/scenario_matrix_summary.json`",
        "- `app_entrypoint/smoke_sim_app_entrypoints_summary.json`",
        "- `app_entrypoint/smoke_sim_app_metadata.json`",
        "- `visual_review/visual_review_summary.json`",
        "- `visual_review/pick_place_depth_distance_metrics.json`",
        "- `visual_review/pick_place_depth_distance_metrics.csv`",
        "- `visual_review/pick_place_depth_distance_scorecard.png`",
        "- `visual_review/pick_place_depth_distance_scorecard.json`",
        "- `visual_review/pick_place_perceived_depth_comparison.json`",
        "- `visual_review/pick_place_perceived_depth_comparison.csv`",
        "- `visual_review/pick_place_pnp_residual_diagnostics.json`",
        "- `visual_review/pick_place_pnp_residual_diagnostics.csv`",
        "- `visual_review/pick_place_metadata_native_depth_view.png`",
        "- `visual_review/pick_place_metadata_native_depth_view.json`",
        "- `visual_review/pick_place_metadata_native_depth_view.csv`",
        "- `real_projection_intake/real_projection_intake.json`",
        "- `real_projection_intake/real_projection_intake.csv`",
        "- `real_projection_intake/real_projection_intake_contact_sheet.png`",
        "- `real_projection_intake/real_projection_residuals.json` when real_capture sidecars are comparable",
        "- `real_projection_intake/real_projection_residuals.csv` when real_capture sidecars are comparable",
        "- `real_projection_intake/real_projection_residual_overlay_contact_sheet.png` when real_capture sidecars are comparable",
        "- `reference_capture_checklist/reference_capture_checklist.json`",
        "- `reference_capture_checklist/reference_capture_checklist.md`",
        "- `negative_empty_inventory/comparison_set_summary.json`",
        "",
        "Review markers:",
        "",
        (
            f"- `hardware_skipped: {markdown_bool(summary.get('hardware_skipped'))}`: "
            f"{markers.get('hardware', '')}"
        ),
        (
            f"- `gui_skipped: {markdown_bool(summary.get('gui_skipped'))}`: "
            f"{markers.get('gui', '')}"
        ),
        (
            f"- `openai_skipped: {markdown_bool(summary.get('openai_skipped'))}`: "
            f"{markers.get('openai', '')}"
        ),
        (
            f"- `reference_media_manifest.supplied: {markdown_bool(manifest_supplied)}`"
            f"; status: `{manifest.get('status')}`; path: `{manifest.get('path')}`."
        ),
        (
            f"- Manifest-declared media selected for comparison: "
            f"`{manifest.get('selected_declared_media_count')}`."
        ),
        "- Real-media gap: the current inventory is limited to `archive/chess_test_images/current_view.jpg`.",
        "- Reference capture checklist status: "
        f"`{summary.get('reference_capture_checklist', {}).get('status')}`.",
        "- No real-world videos are present for motion, recovery, or timing references.",
        "- No reference media currently documents failure modes.",
        (
            "- SimCamera pose metadata includes `image_size_px`, `camera_matrix_px`, "
            "`intrinsics`, `distortion_coefficients`, and `extrinsics.board_to_camera`."
        ),
        (
            "- Gripper-camera POV evidence records target center, projected square geometry, "
            "gripper opening, and synthetic visibility/occlusion/clearance rows."
        ),
        (
            "- IK reachability evidence records deterministic Cartesian/delta/radial command "
            "feasibility with summary JSON, rows CSV, and a heatmap PNG; missing repo-local "
            "SO-101 models remain an explicit non-failing fallback diagnostic."
        ),
        (
            "- App-entrypoint metadata evidence runs `smoke_sim_app_entrypoints.py --sim` "
            "compatibility paths against a synthetic SimCamera frame."
        ),
        (
            "- Visual review contact sheets are stable PNG evidence generated from existing "
            "suite frames under `visual_review/`."
        ),
        (
            "- Pick/place sequence evidence shows approach, grasp/contact, lift/transfer, "
            "place/release, and retreat using simulator gripper-camera frames."
        ),
        (
            "- Pick/place depth/distance evidence records simulator-ground-truth camera-to-board, "
            "camera-to-piece, target world/pixel coordinates, projection residuals, and a "
            "labeled gripper-to-piece board-plane proxy; perceived depth is explicitly marked "
            "`not_implemented`."
        ),
        (
            "- Pick/place depth-distance scorecard evidence writes a PNG plus JSON that combines "
            "SimCamera ground truth, the metadata-derived rendered-corner PnP baseline, mm/px "
            "residual severity, and the explicit missing real-camera/depth-sensor reference."
        ),
        (
            "- Pick/place perceived-depth comparison evidence records a metadata-derived "
            "rendered-board-corner PnP baseline beside the simulator ground truth, including "
            "estimated camera-to-piece/board distances and residuals."
        ),
        (
            "- Pick/place PnP residual diagnostics compare simulator ground-truth "
            "extrinsics, rendered-board-corner PnP, and metadata-projected 3D board corners "
            "with source comparability labels."
        ),
        (
            "- Pick/place metadata-native depth view projects known board, piece, and target "
            "points through SimCamera `camera_matrix_px` and `extrinsics.board_to_camera`, "
            "reports camera-frame z/depth/range in millimeters, and does not use rendered "
            "overlay corners as depth authority."
        ),
        (
            "- Real projection intake links selected real reference media to the metadata-native "
            "projection/depth view, writes JSON/CSV plus a contact-sheet PNG, and reports "
            "`real_depth_comparable` only when real_capture=true intrinsics, pose, and depth "
            "sidecars can be compared; otherwise it reports `missing_real_depth_reference`."
        ),
        (
            f"- Optional visual review recording produced: `{markdown_bool(recording.get('produced'))}`; "
            f"skipped reason: `{recording.get('skipped_reason')}`."
        ),
        "- Those extrinsics are simulator reference metadata, not physical calibration truth.",
        "",
        "This bundle does not replace later physical SO-101 validation.",
        "",
    ]
    readme_path.write_text("\n".join(lines))
    return readme_path


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


def manifest_status_section(
    *,
    requested_manifest: Path | None,
    inventory: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
) -> dict[str, Any]:
    manifest_summary = inventory.get("manifest_summary") if inventory else None
    manifest_summary = manifest_summary if isinstance(manifest_summary, dict) else {}
    inventory_summary = inventory.get("summary") if inventory else None
    inventory_summary = inventory_summary if isinstance(inventory_summary, dict) else {}
    selected_media = comparison.get("selected_media") if comparison else None
    selected_rows = selected_media if isinstance(selected_media, list) else []
    declared_selected = [
        row
        for row in selected_rows
        if isinstance(row, dict)
        and isinstance(row.get("manifest_validation"), dict)
        and row["manifest_validation"].get("declared") is True
    ]
    requested_path = str(requested_manifest) if requested_manifest is not None else None
    return {
        "supplied": bool(manifest_summary.get("supplied", requested_manifest is not None)),
        "requested_path": requested_path,
        "path": manifest_summary.get("path", requested_path),
        "ok": manifest_summary.get("ok"),
        "status": manifest_summary.get("status"),
        "declared_media_count": manifest_summary.get("declared_media_count"),
        "valid_media_count": manifest_summary.get("valid_media_count"),
        "matched_media_count": manifest_summary.get("matched_media_count"),
        "manifest_declared_media_count": inventory_summary.get("manifest_declared_media_count"),
        "selected_declared_media_count": len(declared_selected),
        "selected_declared_media": [
            {
                "relative_path": row.get("relative_path"),
                "capture_id": (
                    row.get("declared_metadata", {}).get("capture_id")
                    if isinstance(row.get("declared_metadata"), dict)
                    else None
                ),
                "declared_target_categories": (
                    row.get("declared_metadata", {}).get("declared_target_categories")
                    if isinstance(row.get("declared_metadata"), dict)
                    else None
                ),
                "failure_mode": (
                    row.get("declared_metadata", {}).get("failure_mode")
                    if isinstance(row.get("declared_metadata"), dict)
                    else None
                ),
                "manifest_validation": row.get("manifest_validation"),
            }
            for row in declared_selected
        ],
        "issue_count": manifest_summary.get("issue_count"),
        "issues": manifest_summary.get("issues"),
    }


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


def sim_camera_pose_fixture_section(pose_fixture: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    artifacts = pose_fixture.get("artifacts") if pose_fixture else None
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    frame_paths = artifacts.get("frame_paths")
    annotated_frame_paths = artifacts.get("annotated_frame_paths")
    metadata_paths = artifacts.get("metadata_paths")
    cases = pose_fixture.get("cases") if pose_fixture else None
    case_rows = cases if isinstance(cases, list) else []
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(pose_fixture.get("ok", False)) if pose_fixture else False,
        "status": pose_fixture.get("status") if pose_fixture else None,
        "case_count": pose_fixture.get("case_count") if pose_fixture else None,
        "case_ids": pose_fixture.get("case_ids") if pose_fixture else None,
        "frame_paths": frame_paths if isinstance(frame_paths, dict) else {},
        "annotated_frame_paths": annotated_frame_paths if isinstance(annotated_frame_paths, dict) else {},
        "metadata_paths": metadata_paths if isinstance(metadata_paths, dict) else {},
        "hardware_skipped": pose_fixture.get("hardware_skipped") if pose_fixture else None,
        "gui_skipped": pose_fixture.get("gui_skipped") if pose_fixture else None,
        "metadata_contract": pose_fixture.get("metadata_contract") if pose_fixture else None,
        "comparisons_to_nominal": pose_fixture.get("comparisons_to_nominal") if pose_fixture else None,
        "cases": [
            {
                "case_id": case.get("case_id"),
                "view": case.get("view"),
                "profile": case.get("profile"),
                "target_square": (
                    case.get("projection", {}).get("target_square", {}).get("square")
                    if isinstance(case.get("projection"), dict)
                    else None
                ),
                "piece_square": (
                    case.get("projection", {}).get("piece_square", {}).get("square")
                    if isinstance(case.get("projection"), dict)
                    else None
                ),
                "unique_colors": (
                    case.get("image", {}).get("unique_colors") if isinstance(case.get("image"), dict) else None
                ),
                "metadata_contract_checks": (
                    case.get("metadata_contract_checks")
                    if isinstance(case.get("metadata_contract_checks"), dict)
                    else None
                ),
            }
            for case in case_rows
            if isinstance(case, dict)
        ],
    }


def app_entrypoint_metadata_section(
    app_entrypoint: dict[str, Any] | None,
    *,
    summary_path: Path,
    frame_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    app_entrypoint = app_entrypoint if isinstance(app_entrypoint, dict) else {}
    camera = app_entrypoint.get("camera")
    camera = camera if isinstance(camera, dict) else {}
    contract = camera.get("metadata_contract")
    contract = contract if isinstance(contract, dict) else {}
    app_camera_status = app_entrypoint.get("app_camera_status")
    if not isinstance(app_camera_status, dict):
        app_camera_status = camera.get("app_camera_status")
    app_camera_status = app_camera_status if isinstance(app_camera_status, dict) else None
    checks = contract.get("checks")
    check_rows = [check for check in checks if isinstance(check, dict)] if isinstance(checks, list) else []
    contract_checks = {
        str(check.get("name")): bool(check.get("ok"))
        for check in check_rows
        if isinstance(check.get("name"), str)
    }
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(app_entrypoint.get("ok", False)),
        "status": app_entrypoint.get("status") or ("ok" if app_entrypoint.get("ok") is True else None),
        "sim_camera_profile": app_entrypoint.get("sim_camera_profile"),
        "frame_path": app_entrypoint.get("frame") if isinstance(app_entrypoint.get("frame"), str) else str(frame_path),
        "metadata_path": (
            app_entrypoint.get("metadata")
            if isinstance(app_entrypoint.get("metadata"), str)
            else str(metadata_path)
        ),
        "hardware_skipped": app_entrypoint.get("hardware_skipped", True),
        "gui_skipped": app_entrypoint.get("gui_skipped", True),
        "openai_skipped": app_entrypoint.get("openai_skipped", True),
        "skipped_markers": app_entrypoint.get("skipped_markers"),
        "metadata_contract": contract,
        "metadata_contract_checks": contract_checks,
        "app_camera_status": app_camera_status,
        "camera": {
            "width": camera.get("width"),
            "height": camera.get("height"),
            "fps": camera.get("fps"),
            "view": camera.get("view"),
            "piece_square": camera.get("piece_square"),
            "piece_layout": camera.get("piece_layout"),
            "gripper_visible": camera.get("gripper_visible"),
        },
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


def gripper_camera_pov_section(pov: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    artifacts = pov.get("artifacts") if pov else None
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    frame_paths = artifacts.get("frame_paths")
    annotated_frame_paths = artifacts.get("annotated_frame_paths")
    metadata_paths = artifacts.get("metadata_paths")
    states = pov.get("states") if pov else None
    state_rows = states if isinstance(states, list) else []
    visibility_by_state: dict[str, dict[str, Any]] = {}
    projection_by_state: dict[str, dict[str, Any]] = {}
    gripper_by_state: dict[str, dict[str, Any]] = {}
    for state in state_rows:
        if not isinstance(state, dict):
            continue
        state_id = state.get("state_id")
        if not isinstance(state_id, str):
            continue
        visibility = state.get("visibility_row")
        if isinstance(visibility, dict):
            visibility_by_state[state_id] = {
                "available": visibility.get("available"),
                "status": visibility.get("status"),
                "piece_square": visibility.get("piece_square"),
                "piece_center_xy": visibility.get("piece_center_xy"),
                "visible_fraction": visibility.get("visible_fraction"),
                "occlusion_fraction": visibility.get("occlusion_fraction"),
                "min_clearance_px": visibility.get("min_clearance_px"),
                "clear_of_gripper": visibility.get("clear_of_gripper"),
                "current_gripper_opening_px": visibility.get("current_gripper_opening_px"),
                "tracked_gripper_percent": visibility.get("tracked_gripper_percent"),
            }
        projection = state.get("projection")
        if isinstance(projection, dict):
            target_square = projection.get("target_square")
            piece_square = projection.get("piece_square")
            projection_by_state[state_id] = {
                "target_square": target_square if isinstance(target_square, dict) else None,
                "piece_square": piece_square if isinstance(piece_square, dict) else None,
            }
        gripper_state = state.get("gripper_state")
        if isinstance(gripper_state, dict):
            gripper_by_state[state_id] = {
                "action": gripper_state.get("action"),
                "requested_percent": gripper_state.get("requested_percent"),
                "tracked_gripper_percent": gripper_state.get("tracked_gripper_percent"),
                "current_gripper_opening_px": gripper_state.get("current_gripper_opening_px"),
            }

    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(pov.get("ok", False)) if pov else False,
        "status": pov.get("status") if pov else None,
        "target_square": pov.get("target_square") if pov else None,
        "state_count": pov.get("state_count") if pov else None,
        "state_ids": pov.get("state_ids") if pov else None,
        "frame_paths": frame_paths if isinstance(frame_paths, dict) else {},
        "annotated_frame_paths": annotated_frame_paths if isinstance(annotated_frame_paths, dict) else {},
        "metadata_paths": metadata_paths if isinstance(metadata_paths, dict) else {},
        "hardware_skipped": pov.get("hardware_skipped") if pov else None,
        "gui_skipped": pov.get("gui_skipped") if pov else None,
        "openai_skipped": pov.get("openai_skipped") if pov else None,
        "metadata_contract": pov.get("metadata_contract") if pov else None,
        "piece_visibility": pov.get("piece_visibility") if pov else None,
        "visibility_by_state": visibility_by_state,
        "projection_by_state": projection_by_state,
        "gripper_by_state": gripper_by_state,
        "limitations": pov.get("limitations") if pov else None,
    }


def ik_reachability_section(ik: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    ik = ik if isinstance(ik, dict) else {}
    artifacts = ik.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    row_summary = ik.get("summary")
    row_summary = row_summary if isinstance(row_summary, dict) else {}
    model_diagnostic = ik.get("model_diagnostic")
    model_diagnostic = model_diagnostic if isinstance(model_diagnostic, dict) else {}
    model_solver = ik.get("model_solver")
    model_solver = model_solver if isinstance(model_solver, dict) else {}
    explicit_model_path = model_diagnostic.get("explicit_model_path")
    configured_model_path = None
    if isinstance(explicit_model_path, dict):
        candidate_path = explicit_model_path.get("path")
        configured_model_path = candidate_path if isinstance(candidate_path, str) else None
    elif isinstance(explicit_model_path, str):
        configured_model_path = explicit_model_path
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(ik.get("ok", False)),
        "status": ik.get("status"),
        "row_count": row_summary.get("row_count"),
        "counts_by_feasibility": row_summary.get("counts_by_feasibility"),
        "configured_model_path": configured_model_path,
        "configured_model_request": explicit_model_path,
        "artifacts": {
            "summary_json": artifacts.get("summary_json") if isinstance(artifacts.get("summary_json"), str) else str(summary_path),
            "rows_csv": artifacts.get("rows_csv"),
            "heatmap_png": artifacts.get("heatmap_png"),
        },
        "model_diagnostic": {
            "status": model_diagnostic.get("status"),
            "reason": model_diagnostic.get("reason"),
            "selected_model_path": model_diagnostic.get("selected_model_path"),
            "selected_model_source": model_diagnostic.get("selected_model_source"),
            "repo_local_model_count": model_diagnostic.get("repo_local_model_count"),
        },
        "model_solver": {
            "available": model_solver.get("available"),
            "status": model_solver.get("status"),
            "target_frame": model_solver.get("target_frame"),
            "solver_backend": model_solver.get("solver_backend"),
            "reason": model_solver.get("reason"),
        },
        "hardware_skipped": ik.get("hardware_skipped"),
        "gui_skipped": ik.get("gui_skipped"),
        "openai_skipped": ik.get("openai_skipped"),
        "limitations": ik.get("limitations"),
    }


def visual_review_section(visual_review: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    contact_sheets = visual_review.get("contact_sheets")
    contact_sheets = contact_sheets if isinstance(contact_sheets, list) else []
    contact_sheet_paths = visual_review.get("contact_sheet_paths")
    contact_sheet_paths = contact_sheet_paths if isinstance(contact_sheet_paths, dict) else {}
    frame_sequences = visual_review.get("frame_sequences")
    frame_sequences = frame_sequences if isinstance(frame_sequences, list) else []
    distance_metrics = visual_review.get("distance_metrics")
    distance_metrics = distance_metrics if isinstance(distance_metrics, dict) else {}
    perceived_depth_comparison = visual_review.get("perceived_depth_comparison")
    perceived_depth_comparison = (
        perceived_depth_comparison if isinstance(perceived_depth_comparison, dict) else {}
    )
    pnp_residual_diagnostics = visual_review.get("pnp_residual_diagnostics")
    pnp_residual_diagnostics = (
        pnp_residual_diagnostics if isinstance(pnp_residual_diagnostics, dict) else {}
    )
    metadata_native_depth_view = visual_review.get("metadata_native_depth_view")
    metadata_native_depth_view = (
        metadata_native_depth_view if isinstance(metadata_native_depth_view, dict) else {}
    )
    depth_distance_scorecard = visual_review.get("depth_distance_scorecard")
    depth_distance_scorecard = (
        depth_distance_scorecard if isinstance(depth_distance_scorecard, dict) else {}
    )
    recordings = visual_review.get("recordings")
    recordings = recordings if isinstance(recordings, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(visual_review.get("ok", False)),
        "status": visual_review.get("status"),
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet_paths": {
            str(key): str(value)
            for key, value in sorted(contact_sheet_paths.items())
            if isinstance(value, str)
        },
        "contact_sheets": contact_sheets,
        "frame_sequences": frame_sequences,
        "distance_metrics": distance_metrics,
        "perceived_depth_comparison": perceived_depth_comparison,
        "pnp_residual_diagnostics": pnp_residual_diagnostics,
        "metadata_native_depth_view": metadata_native_depth_view,
        "depth_distance_scorecard": depth_distance_scorecard,
        "app_entrypoint_frame": visual_review.get("app_entrypoint_frame"),
        "recording": visual_review.get("recording"),
        "recordings": recordings,
        "hardware_skipped": visual_review.get("hardware_skipped"),
        "gui_skipped": visual_review.get("gui_skipped"),
        "openai_skipped": visual_review.get("openai_skipped"),
        "notes": visual_review.get("notes"),
    }


def reference_capture_checklist_section(checklist: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    checklist = checklist if isinstance(checklist, dict) else {}
    counts = checklist.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    media_summary = checklist.get("media_summary")
    media_summary = media_summary if isinstance(media_summary, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(checklist.get("ok", False)),
        "status": checklist.get("status"),
        "markdown_path": checklist.get("markdown_path"),
        "represented_media_count": media_summary.get("represented_media_count"),
        "represented_media": media_summary.get("represented_media"),
        "video_count": media_summary.get("video_count"),
        "requirement_count": counts.get("requirement_count"),
        "represented_requirement_count": counts.get("represented_requirement_count"),
        "partial_requirement_count": counts.get("partial_requirement_count"),
        "missing_requirement_count": counts.get("missing_requirement_count"),
        "action_item_count": counts.get("action_item_count"),
        "hardware_skipped": checklist.get("hardware_skipped"),
        "gui_skipped": checklist.get("gui_skipped"),
        "real_camera_skipped": checklist.get("real_camera_skipped"),
        "openai_skipped": checklist.get("openai_skipped"),
    }


def real_projection_intake_section(intake: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    intake = intake if isinstance(intake, dict) else {}
    paths = intake.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    residual_artifacts = intake.get("residual_artifacts")
    residual_artifacts = residual_artifacts if isinstance(residual_artifacts, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(intake.get("ok", False)),
        "status": intake.get("status"),
        "paths": paths,
        "real_reference_media_count": intake.get("real_reference_media_count"),
        "comparable_count": intake.get("comparable_count"),
        "projection_comparable_count": intake.get("projection_comparable_count"),
        "depth_comparable_count": intake.get("depth_comparable_count"),
        "sidecar_valid_count": intake.get("sidecar_valid_count"),
        "sidecar_invalid_count": intake.get("sidecar_invalid_count"),
        "sidecar_missing_count": intake.get("sidecar_missing_count"),
        "missing_input_count": intake.get("missing_input_count"),
        "missing_inputs": intake.get("missing_inputs"),
        "next_capture_requirements": intake.get("next_capture_requirements"),
        "sim_metadata_native_depth_view_path": intake.get("sim_metadata_native_depth_view_path"),
        "sim_metadata_native_depth_view_png_path": intake.get("sim_metadata_native_depth_view_png_path"),
        "sim_metadata_native_depth_view_csv_path": intake.get("sim_metadata_native_depth_view_csv_path"),
        "sim_expected_projected_point_count": intake.get("sim_expected_projected_point_count"),
        "residual_artifacts": residual_artifacts,
        "records": intake.get("records"),
        "hardware_skipped": intake.get("hardware_skipped"),
        "gui_skipped": intake.get("gui_skipped"),
        "real_camera_capture_skipped": intake.get("real_camera_capture_skipped"),
        "openai_skipped": intake.get("openai_skipped"),
    }


def evidence_bundle_section(bundle: dict[str, Any] | None, bundle_dir: Path) -> dict[str, Any]:
    bundle = bundle if isinstance(bundle, dict) else {}
    output_md = bundle.get("output_md")
    output_json = bundle.get("output_json")
    return {
        "summary_path": str(bundle_dir / EVIDENCE_BUNDLE_JSON_NAME),
        "markdown_path": str(bundle_dir / EVIDENCE_BUNDLE_MD_NAME),
        "output_dir": str(bundle_dir),
        "ok": bool(bundle.get("ok", False)),
        "status": bundle.get("status"),
        "output_md": output_md if isinstance(output_md, str) else str(bundle_dir / EVIDENCE_BUNDLE_MD_NAME),
        "output_json": (
            output_json
            if isinstance(output_json, str)
            else str(bundle_dir / EVIDENCE_BUNDLE_JSON_NAME)
        ),
        "real_depth_reference_status": (
            bundle.get("summaries", {})
            .get("real_depth_reference", {})
            .get("status")
            if isinstance(bundle.get("summaries"), dict)
            else None
        ),
        "missing_required_artifact_count": len(bundle.get("missing_required_artifacts", []))
        if isinstance(bundle.get("missing_required_artifacts"), list)
        else None,
        "capture_plan": {
            "json_supplied": any(
                row.get("key") == "capture_plan_json" and row.get("status") == "available"
                for row in bundle.get("artifacts", [])
                if isinstance(row, dict)
            )
            if isinstance(bundle.get("artifacts"), list)
            else False,
            "markdown_supplied": any(
                row.get("key") == "capture_plan_md" and row.get("status") == "available"
                for row in bundle.get("artifacts", [])
                if isinstance(row, dict)
            )
            if isinstance(bundle.get("artifacts"), list)
            else False,
        },
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
    inventory_command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_inventory.py"),
        "--output-dir",
        str(inventory_dir),
    ]
    if args.reference_media_manifest is not None:
        inventory_command.extend(["--manifest", str(args.reference_media_manifest.expanduser())])
    inventory_record, inventory = run_child(
        name="inventory",
        command=inventory_command,
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

    pose_fixture_dir = output_dir / "sim_camera_pose_fixture"
    pose_fixture_summary_path = pose_fixture_dir / "sim_camera_pose_fixture_summary.json"
    pose_fixture_record, pose_fixture = run_child(
        name="sim_camera_pose_fixture",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_camera_pose_fixture.py"),
            "--output-dir",
            str(pose_fixture_dir),
            "--profile",
            str(args.base_profile),
            "--target-square",
            str(args.source_square),
            "--closed-gripper-square",
            str(args.target_square),
        ],
        output_dir=pose_fixture_dir,
        expected_json_path=pose_fixture_summary_path,
    )

    ik_reachability_dir = output_dir / "ik_reachability_drill"
    ik_reachability_summary_path = ik_reachability_dir / IK_REACHABILITY_SUMMARY_NAME
    ik_reachability_command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_ik_reachability_drill.py"),
        "--output-dir",
        str(ik_reachability_dir),
    ]
    if args.ik_model_path is not None:
        ik_reachability_command.extend(["--model-path", str(args.ik_model_path)])
    ik_reachability_record, ik_reachability = run_child(
        name="ik_reachability_drill",
        command=ik_reachability_command,
        output_dir=ik_reachability_dir,
        expected_json_path=ik_reachability_summary_path,
    )

    pov_dir = output_dir / "gripper_camera_pov_review"
    pov_summary_path = pov_dir / "gripper_camera_pov_review_summary.json"
    pov_record, pov = run_child(
        name="gripper_camera_pov_review",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_gripper_camera_pov_review.py"),
            "--output-dir",
            str(pov_dir),
            "--profile",
            str(args.base_profile),
            "--target-square",
            str(args.source_square),
        ],
        output_dir=pov_dir,
        expected_json_path=pov_summary_path,
    )

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

    app_entrypoint_dir = output_dir / "app_entrypoint"
    app_entrypoint_summary_path = app_entrypoint_dir / "smoke_sim_app_entrypoints_summary.json"
    app_entrypoint_frame_path = app_entrypoint_dir / "smoke_sim_app_frame.jpg"
    app_entrypoint_metadata_path = app_entrypoint_dir / "smoke_sim_app_metadata.json"
    app_entrypoint_record, app_entrypoint = run_child(
        name="app_entrypoint_metadata",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_app_entrypoints.py"),
            "--sim-camera-profile",
            str(args.base_profile),
            "--frame-out",
            str(app_entrypoint_frame_path),
            "--metadata-out",
            str(app_entrypoint_metadata_path),
            "--summary-out",
            str(app_entrypoint_summary_path),
        ],
        output_dir=app_entrypoint_dir,
        expected_json_path=app_entrypoint_summary_path,
    )

    visual_review_dir = output_dir / "visual_review"
    visual_review_summary_path = visual_review_dir / VISUAL_REVIEW_SUMMARY_NAME

    child_records = {
        "inventory": inventory_record,
        "comparison_set": comparison_record,
        "calibration_session_report": session_record,
        "perception_regression_fixture": fixture_record,
        "sim_camera_pose_fixture": pose_fixture_record,
        "ik_reachability_drill": ik_reachability_record,
        "gripper_camera_pov_review": pov_record,
        "pick_place_scenario_matrix": matrix_record,
    }
    if negative_record is not None:
        child_records["negative_empty_inventory_comparison_set"] = negative_record
    child_records["app_entrypoint_metadata"] = app_entrypoint_record

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
        "openai_skipped": True,
        "skipped_markers": {
            "hardware": "Suite and child smokes use simulator/reference media only; no robot hardware paths are invoked.",
            "gui": "Suite passes explicit non-interactive inputs and does not request OpenCV click/display flows.",
            "openai": "Suite and child smokes exercise local simulator/tool paths only; no OpenAI credentials or network calls are required.",
        },
        "candidate_inputs": candidate_paths,
        "child_commands": child_records,
        "reference_media_manifest": manifest_status_section(
            requested_manifest=args.reference_media_manifest,
            inventory=inventory,
            comparison=comparison,
        ),
        "inventory": {
            "summary_path": str(inventory_json_path),
            "summary": inventory.get("summary") if inventory else None,
            "manifest_summary": inventory.get("manifest_summary") if inventory else None,
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
        "sim_camera_pose_fixture": sim_camera_pose_fixture_section(
            pose_fixture,
            pose_fixture_summary_path,
        ),
        "ik_reachability_drill": ik_reachability_section(
            ik_reachability,
            ik_reachability_summary_path,
        ),
        "gripper_camera_pov_review": gripper_camera_pov_section(pov, pov_summary_path),
        "pick_place_scenario_matrix": matrix_summary_section(matrix, matrix_summary_path),
        "app_entrypoint_metadata": app_entrypoint_metadata_section(
            app_entrypoint,
            summary_path=app_entrypoint_summary_path,
            frame_path=app_entrypoint_frame_path,
            metadata_path=app_entrypoint_metadata_path,
        ),
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
        "reference_capture_checklist": {
            "summary_path": str(output_dir / "reference_capture_checklist" / REFERENCE_CAPTURE_CHECKLIST_NAME),
            "status": None,
            "represented_media_count": None,
            "missing_requirement_count": None,
        },
        "real_projection_intake": {
            "summary_path": str(output_dir / "real_projection_intake" / REAL_PROJECTION_INTAKE_NAME),
            "status": None,
            "real_reference_media_count": None,
            "comparable_count": None,
        },
        "evidence_bundle": {
            "summary_path": str(output_dir / EVIDENCE_BUNDLE_DIR_NAME / EVIDENCE_BUNDLE_JSON_NAME),
            "markdown_path": str(output_dir / EVIDENCE_BUNDLE_DIR_NAME / EVIDENCE_BUNDLE_MD_NAME),
            "status": None,
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
            "SimCamera intrinsics/extrinsics are simulator reference metadata for downstream tool compatibility, not physical calibration truth.",
        ],
    }
    write_json(summary_path, summary)

    visual_review_record, visual_review = run_child(
        name="visual_review",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "render_sim_calibration_visual_review.py"),
            str(summary_path),
            "--output-dir",
            str(visual_review_dir),
            "--try-video",
        ],
        output_dir=visual_review_dir,
        expected_json_path=visual_review_summary_path,
    )
    child_records["visual_review"] = visual_review_record
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
    summary["visual_review"] = visual_review_section(visual_review, visual_review_summary_path)
    write_json(summary_path, summary)

    checklist_dir = output_dir / "reference_capture_checklist"
    checklist_summary_path = checklist_dir / REFERENCE_CAPTURE_CHECKLIST_NAME
    checklist_record, checklist = run_child(
        name="reference_capture_checklist",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_reference_capture_checklist.py"),
            str(summary_path),
            "--output-dir",
            str(checklist_dir),
        ],
        output_dir=checklist_dir,
        expected_json_path=checklist_summary_path,
    )
    child_records["reference_capture_checklist"] = checklist_record
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
    summary["reference_capture_checklist"] = reference_capture_checklist_section(
        checklist,
        checklist_summary_path,
    )
    write_json(summary_path, summary)

    real_projection_intake_dir = output_dir / "real_projection_intake"
    real_projection_intake_summary_path = real_projection_intake_dir / REAL_PROJECTION_INTAKE_NAME
    real_projection_intake_record, real_projection_intake = run_child(
        name="real_projection_intake",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_real_projection_intake.py"),
            str(summary_path),
            "--output-dir",
            str(real_projection_intake_dir),
        ],
        output_dir=real_projection_intake_dir,
        expected_json_path=real_projection_intake_summary_path,
    )
    child_records["real_projection_intake"] = real_projection_intake_record
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
    summary["real_projection_intake"] = real_projection_intake_section(
        real_projection_intake,
        real_projection_intake_summary_path,
    )
    write_json(summary_path, summary)

    visual_review_refresh_record, visual_review_refresh = run_child(
        name="visual_review_real_depth_refresh",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "render_sim_calibration_visual_review.py"),
            str(summary_path),
            "--output-dir",
            str(visual_review_dir),
            "--try-video",
        ],
        output_dir=visual_review_dir,
        expected_json_path=visual_review_summary_path,
    )
    child_records["visual_review_real_depth_refresh"] = visual_review_refresh_record
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
    summary["visual_review"] = visual_review_section(
        visual_review_refresh,
        visual_review_summary_path,
    )
    write_json(summary_path, summary)

    evidence_bundle_dir = output_dir / EVIDENCE_BUNDLE_DIR_NAME
    evidence_bundle_json_path = evidence_bundle_dir / EVIDENCE_BUNDLE_JSON_NAME
    evidence_bundle_record, evidence_bundle = run_child(
        name="evidence_bundle",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "render_sim_evidence_bundle.py"),
            str(summary_path),
            "--output-dir",
            str(evidence_bundle_dir),
        ],
        output_dir=evidence_bundle_dir,
        expected_json_path=evidence_bundle_json_path,
    )
    child_records["evidence_bundle"] = evidence_bundle_record
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
    summary["evidence_bundle"] = evidence_bundle_section(evidence_bundle, evidence_bundle_dir)
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

    if not args.skip_artifact_index_report:
        report_path = output_dir / ARTIFACT_REPORT_NAME
        report_result = subprocess.run(
            [
                python,
                str(REPO_ROOT / "scripts" / "render_sim_calibration_artifact_index_report.py"),
                str(artifact_index_path),
                "--output-md",
                str(report_path),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if report_result.returncode != 0:
            if report_result.stdout:
                sys.stdout.write(report_result.stdout)
            if report_result.stderr:
                sys.stderr.write(report_result.stderr)
            required_ok = False
            summary["ok"] = False
            summary["status"] = "validation_failed"
            failed_children = list(summary["aggregate_status"].get("failed_children", []))
            failed_children.append("artifact_index_report")
            summary["aggregate_status"] = {
                "ok": False,
                "failed_children": failed_children,
            }
            write_json(summary_path, summary)
        else:
            try:
                write_artifact_entrypoint_readme(output_dir, summary)
            except OSError as exc:
                print(f"ERROR: Could not write artifact entrypoint README: {exc}", file=sys.stderr)
                required_ok = False
                summary["ok"] = False
                summary["status"] = "validation_failed"
                failed_children = list(summary["aggregate_status"].get("failed_children", []))
                failed_children.append("artifact_entrypoint_readme")
                summary["aggregate_status"] = {
                    "ok": False,
                    "failed_children": failed_children,
                }
                write_json(summary_path, summary)

    print(json.dumps(summary, indent=2))
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
