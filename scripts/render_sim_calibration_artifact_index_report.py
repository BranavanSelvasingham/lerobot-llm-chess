#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ARTIFACT_INDEX_SCHEMA = "lerobot.sim.calibration_artifact_index.v1"
SUITE_SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
DEFAULT_REPORT_NAME = "artifact_index_report.md"
CATEGORY_ORDER = {
    "reference_media_inventory": 0,
    "real_reference_media": 1,
    "reference_media_comparison": 2,
    "reference_camera_tuning_diagnostics": 3,
    "sim_camera_profile_sweep": 4,
    "sim_camera_tuning_before_after": 5,
    "reference_capture_manifest": 6,
    "real_depth_capture_plan_artifact_index": 7,
    "reference_capture_checklist": 8,
    "visual_review": 9,
    "real_reference_comparison": 10,
    "real_projection_intake": 11,
    "ranked_candidate": 12,
    "perception_fixture": 13,
    "sim_camera_pose_fixture": 14,
    "so101_model_source_inventory": 15,
    "so101_reviewed_model_authority_gate": 16,
    "so101_model_bundle_probe": 17,
    "so101_model_bundle_manifest": 18,
    "so101_reviewed_mujoco_bundle": 19,
    "so101_model_contract": 20,
    "so101_model_asset_preflight": 21,
    "ik_reachability": 22,
    "so101_mujoco_scene": 23,
    "so101_chess_env": 24,
    "so101_env_resets": 25,
    "so101_mujoco_contact_probe": 26,
    "so101_mujoco_grasp_probe": 27,
    "so101_mujoco_board_pick_probe": 28,
    "so101_training_readiness_gate": 29,
    "so101_training_rollouts": 30,
    "gripper_camera_pov": 31,
    "app_entrypoint": 32,
    "pick_place_scenario": 33,
    "negative_check": 34,
    "logs": 35,
}
CATEGORY_LABELS = {
    "reference_media_inventory": "Reference Media Inventory",
    "real_reference_media": "Real Reference Media",
    "reference_media_comparison": "Reference Media Comparison",
    "reference_camera_tuning_diagnostics": "Reference Camera Tuning Diagnostics",
    "sim_camera_profile_sweep": "SimCamera Profile Sweep",
    "sim_camera_tuning_before_after": "SimCamera Tuning Before/After",
    "reference_capture_manifest": "Reference Capture Manifest",
    "real_depth_capture_plan_artifact_index": "Real Depth Capture Plan Artifact Index",
    "reference_capture_checklist": "Reference Capture Checklist",
    "visual_review": "Visual Review Artifacts",
    "real_reference_comparison": "Real Reference Comparisons",
    "real_projection_intake": "Real Projection Intake",
    "ranked_candidate": "Ranked Candidate Captures",
    "perception_fixture": "Perception Fixture Evidence",
    "sim_camera_pose_fixture": "SimCamera Pose Fixture",
    "so101_model_source_inventory": "SO-101 Model Source Inventory",
    "so101_reviewed_model_authority_gate": "SO-101 Reviewed Model Authority Gate",
    "so101_model_bundle_probe": "SO-101 Model Bundle Probe",
    "so101_model_bundle_manifest": "SO-101 Model Bundle Manifest",
    "so101_reviewed_mujoco_bundle": "SO-101 Reviewed MuJoCo Bundle",
    "so101_model_contract": "SO-101 Model Contract",
    "so101_model_asset_preflight": "SO-101 Model Asset Preflight",
    "ik_reachability": "IK Reachability Drill",
    "so101_mujoco_scene": "SO-101 MuJoCo Scene",
    "so101_chess_env": "SO-101 Chess Gymnasium Env",
    "so101_env_resets": "SO-101 Env Resets",
    "so101_mujoco_contact_probe": "SO-101 MuJoCo Contact Probe",
    "so101_mujoco_grasp_probe": "SO-101 MuJoCo Grasp Probe",
    "so101_mujoco_board_pick_probe": "SO-101 MuJoCo Board Pick Probe",
    "so101_training_readiness_gate": "SO-101 Training Readiness Gate",
    "so101_training_rollouts": "SO-101 Training Rollouts",
    "gripper_camera_pov": "Gripper-Camera POV Review",
    "app_entrypoint": "App Entrypoint Metadata",
    "pick_place_scenario": "Pick/Place Release Frames",
    "negative_check": "Negative Check",
    "logs": "Child Logs",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a small Markdown report for an existing simulator calibration "
            "artifact_index.json, or for a suite summary that points at one."
        )
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="Path to artifact_index.json or calibration_regression_summary.json.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Report path. Defaults to artifact_index_report.md in the suite output directory.",
    )
    return parser.parse_args()


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object.")
    return payload


def resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def load_inputs(input_json: Path) -> tuple[dict[str, Any], dict[str, Any] | None, Path]:
    input_json = input_json.expanduser().resolve()
    payload = read_json_object(input_json, label="input JSON")
    schema = payload.get("schema")
    if schema == ARTIFACT_INDEX_SCHEMA or "artifacts" in payload:
        index = payload
        suite = None
        suite_path_value = index.get("suite_summary_path")
        if isinstance(suite_path_value, str) and suite_path_value:
            suite_path = resolve_path(suite_path_value, base_dir=input_json.parent)
            if suite_path.is_file():
                suite = read_json_object(suite_path, label="suite summary")
        return index, suite, input_json

    if schema == SUITE_SCHEMA or "artifact_index" in payload:
        suite = payload
        artifact_index = suite.get("artifact_index")
        artifact_index = artifact_index if isinstance(artifact_index, dict) else {}
        artifact_index_path_value = artifact_index.get("path")
        if not isinstance(artifact_index_path_value, str) or not artifact_index_path_value:
            raise ValueError(f"Suite summary {input_json} does not contain artifact_index.path.")
        artifact_index_path = resolve_path(artifact_index_path_value, base_dir=input_json.parent)
        index = read_json_object(artifact_index_path, label="artifact index")
        return index, suite, artifact_index_path

    raise ValueError(
        f"{input_json} is neither an artifact index nor a calibration regression suite summary."
    )


def validate_index(index: dict[str, Any], artifact_index_path: Path) -> None:
    if index.get("schema") != ARTIFACT_INDEX_SCHEMA:
        raise ValueError(
            f"Artifact index {artifact_index_path} has unexpected schema {index.get('schema')!r}."
        )
    if not isinstance(index.get("artifacts"), list):
        raise ValueError(f"Artifact index {artifact_index_path} must contain an artifacts list.")
    if not isinstance(index.get("categories"), list):
        raise ValueError(f"Artifact index {artifact_index_path} must contain a categories list.")


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_code(value: Any) -> str:
    text = "" if value is None else str(value)
    escaped = text.replace("`", "\\`")
    return f"`{escaped}`"


def compact_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    return "<br>".join(markdown_code(item) for item in value)


def source_root_summary(metrics: dict[str, Any]) -> str:
    parts = []
    roots = compact_list(metrics.get("configured_model_source_roots"))
    extra_roots = compact_list(metrics.get("configured_model_source_extra_roots"))
    if roots:
        parts.append(f"roots:<br>{roots}")
    if extra_roots:
        parts.append(f"extra:<br>{extra_roots}")
    return "<br>".join(parts)


def source_authority_summary(metrics: dict[str, Any]) -> str:
    parts = []
    paths = compact_list(metrics.get("configured_authoritative_model_paths"))
    roots = compact_list(metrics.get("configured_authoritative_model_roots"))
    if paths:
        parts.append(f"paths:<br>{paths}")
    if roots:
        parts.append(f"roots:<br>{roots}")
    return "<br>".join(parts)


def display_path(artifact: dict[str, Any]) -> str:
    for key in ("relative_path", "repo_relative_path", "path"):
        value = artifact.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def link_path(artifact: dict[str, Any]) -> str:
    value = artifact.get("relative_path")
    if isinstance(value, str) and value:
        return value
    value = artifact.get("path")
    if isinstance(value, str) and value:
        return value
    return display_path(artifact)


def markdown_link(label: str, target: str) -> str:
    if not target:
        return markdown_escape(label)
    escaped_label = markdown_escape(label)
    escaped_target = target.replace(" ", "%20").replace(")", "%29")
    return f"[{escaped_label}]({escaped_target})"


def artifact_sort_key(artifact: dict[str, Any]) -> tuple[int, str, str]:
    category = str(artifact.get("category") or "")
    return (
        CATEGORY_ORDER.get(category, 99),
        str(artifact.get("label") or ""),
        display_path(artifact),
    )


def artifacts_by_category(index: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_ORDER}
    for artifact in index.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        grouped.setdefault(category, []).append(artifact)
    for category, rows in grouped.items():
        grouped[category] = sorted(rows, key=artifact_sort_key)
    return grouped


def category_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    by_category = {
        row.get("category"): row
        for row in index.get("categories", [])
        if isinstance(row, dict) and isinstance(row.get("category"), str)
    }
    rows: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        source = by_category.get(category, {})
        rows.append(
            {
                "category": category,
                "artifact_count": int(source.get("artifact_count") or 0),
                "missing_count": int(source.get("missing_count") or 0),
            }
        )
    for category in sorted(str(key) for key in by_category if key not in CATEGORY_ORDER):
        source = by_category[category]
        rows.append(
            {
                "category": category,
                "artifact_count": int(source.get("artifact_count") or 0),
                "missing_count": int(source.get("missing_count") or 0),
            }
        )
    return rows


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_escape(value) for value in row) + " |" for row in rows)
    return lines


def value_from_suite_or_index(index: dict[str, Any], suite: dict[str, Any] | None, key: str) -> Any:
    if suite is not None and key in suite:
        return suite.get(key)
    return index.get(key)


def skipped_marker_rows(index: dict[str, Any], suite: dict[str, Any] | None) -> list[list[Any]]:
    markers = value_from_suite_or_index(index, suite, "skipped_markers")
    markers = markers if isinstance(markers, dict) else {}
    return [
        [
            "hardware",
            value_from_suite_or_index(index, suite, "hardware_skipped"),
            markers.get("hardware", ""),
        ],
        [
            "gui",
            value_from_suite_or_index(index, suite, "gui_skipped"),
            markers.get("gui", ""),
        ],
        [
            "openai",
            value_from_suite_or_index(index, suite, "openai_skipped"),
            markers.get("openai", ""),
        ],
    ]


def suite_inventory_gaps(suite: dict[str, Any] | None) -> list[dict[str, Any]]:
    if suite is None:
        return []
    inventory = suite.get("reference_media_inventory")
    if not isinstance(inventory, dict) or not inventory:
        inventory = suite.get("inventory")
    inventory = inventory if isinstance(inventory, dict) else {}
    gaps = inventory.get("visibility_gaps")
    return [gap for gap in gaps if isinstance(gap, dict)] if isinstance(gaps, list) else []


def reference_media_inventory_signal(index: dict[str, Any], suite: dict[str, Any] | None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    inventory = index.get("reference_media_inventory")
    if isinstance(inventory, dict):
        candidates.append(inventory)
    if suite is not None:
        for key in ("reference_media_inventory", "inventory"):
            suite_inventory = suite.get(key)
            if isinstance(suite_inventory, dict):
                candidates.append(suite_inventory)
    for candidate in candidates:
        if candidate:
            return candidate
    return {}


def inventory_summary_value(inventory: dict[str, Any], key: str) -> Any:
    if key in inventory:
        return inventory.get(key)
    summary = inventory.get("summary")
    if isinstance(summary, dict):
        return summary.get(key)
    return None


def inventory_current_gripper_reference(inventory: dict[str, Any]) -> dict[str, Any]:
    current = inventory.get("current_gripper_reference")
    if isinstance(current, dict):
        return current
    summary = inventory.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    return {
        "detected": summary.get("active_current_gripper_reference_detected"),
        "path": summary.get("active_current_gripper_reference_path"),
    }


def inventory_reference_gaps(inventory: dict[str, Any]) -> list[Any]:
    gaps = inventory.get("reference_gaps")
    if isinstance(gaps, list):
        return gaps
    summary = inventory.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("reference_gaps"), list):
        return summary["reference_gaps"]
    return []


def selected_media_rows(index: dict[str, Any]) -> list[list[Any]]:
    selected = index.get("selected_real_reference_media")
    selected = selected if isinstance(selected, list) else []
    rows: list[list[Any]] = []
    for media in selected:
        if not isinstance(media, dict):
            continue
        validation = media.get("manifest_validation")
        validation = validation if isinstance(validation, dict) else {}
        rows.append(
            [
                media.get("relative_path", ""),
                media.get("media_type", ""),
                media.get("dimensions", ""),
                media.get("currently_wired_into_simulator_tooling", ""),
                validation.get("status", ""),
                media.get("capture_id", ""),
                media.get("declared_target_categories", ""),
                media.get("failure_mode", ""),
            ]
        )
    return rows


def reference_media_comparison_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison = index.get("reference_media_comparison")
    if isinstance(comparison, dict) and comparison:
        return comparison
    if suite is not None and isinstance(suite.get("comparison_set"), dict):
        return suite["comparison_set"]
    return {}


def reference_media_comparison_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("selected_candidate_count", ""),
        metrics.get("selected_media_count", ""),
        metrics.get("visual_comparison_count", ""),
        metrics.get("contact_sheet_status", ""),
        metrics.get("media_assets_copied_into_repo", ""),
        metrics.get("external_selected_count", ""),
        metrics.get("missing_depth_reference", ""),
        metrics.get("missing_pick_place_video", ""),
        metrics.get("no_videos", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def reference_camera_tuning_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    diagnostics = index.get("reference_camera_tuning_diagnostics")
    if isinstance(diagnostics, dict) and diagnostics:
        return diagnostics
    if suite is not None and isinstance(suite.get("reference_camera_tuning_diagnostics"), dict):
        return suite["reference_camera_tuning_diagnostics"]
    return {}


def reference_camera_tuning_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("selected_comparison_count", ""),
        metrics.get("visual_comparison_count", ""),
        metrics.get("metadata_only_count", ""),
        compact_list(metrics.get("suggested_tuning_dimensions")),
        metrics.get("scorecard_status", ""),
        metrics.get("scorecard_produced", ""),
        metrics.get("media_assets_copied_into_repo", ""),
        metrics.get("external_selected_count", ""),
        metrics.get("absolute_sibling_paths_are_local_evidence_only", ""),
        metrics.get("missing_depth_reference", ""),
        metrics.get("missing_pick_place_video", ""),
        metrics.get("no_videos", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def sim_camera_profile_sweep_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    sweep = index.get("sim_camera_profile_sweep")
    if isinstance(sweep, dict) and sweep:
        return sweep
    if suite is not None and isinstance(suite.get("sim_camera_profile_sweep"), dict):
        return suite["sim_camera_profile_sweep"]
    return {}


def sim_camera_profile_sweep_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("profile_name", ""),
        metrics.get("current_gripper_finger_width_px", ""),
        metrics.get("marker_time_seconds", ""),
        metrics.get("candidate_count", ""),
        metrics.get("best_candidate_id", ""),
        metrics.get("current_mean_abs_delta", ""),
        metrics.get("current_rmse", ""),
        metrics.get("best_mean_abs_delta", ""),
        metrics.get("best_rmse", ""),
        metrics.get("mean_abs_delta_delta_vs_current", ""),
        metrics.get("rmse_delta_vs_current", ""),
        metrics.get("candidate_id", ""),
        metrics.get("candidate_mean_abs_delta", ""),
        metrics.get("candidate_rmse", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def sim_camera_profile_sweep_ranking_rows(sweep: dict[str, Any]) -> list[list[Any]]:
    ranking = sweep.get("candidate_ranking")
    ranking_rows = ranking if isinstance(ranking, list) else []
    rows: list[list[Any]] = []
    for row in ranking_rows:
        if not isinstance(row, dict):
            continue
        artifacts = row.get("artifact_paths")
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        annotated_path = artifacts.get("annotated_path")
        rows.append(
            [
                row.get("rank", ""),
                row.get("candidate_id", ""),
                row.get("description", ""),
                row.get("mean_abs_delta", ""),
                row.get("rmse", ""),
                row.get("mean_abs_delta_delta_vs_current", ""),
                row.get("rmse_delta_vs_current", ""),
                markdown_link(str(annotated_path), str(annotated_path)) if annotated_path else "",
            ]
        )
    return rows


def sim_camera_profile_sweep_prompt_rows(sweep: dict[str, Any]) -> list[list[Any]]:
    prompts = sweep.get("remaining_tuning_prompts")
    prompt_rows = prompts if isinstance(prompts, list) else []
    rows: list[list[Any]] = []
    for prompt in prompt_rows:
        if not isinstance(prompt, dict):
            continue
        rows.append(
            [
                prompt.get("candidate_id", ""),
                prompt.get("description", ""),
                prompt.get("mean_abs_delta_delta_vs_current", ""),
                prompt.get("rmse_delta_vs_current", ""),
            ]
        )
    return rows


def sim_camera_tuning_before_after_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    tuning = index.get("sim_camera_tuning_before_after")
    if isinstance(tuning, dict) and tuning:
        return tuning
    if suite is not None and isinstance(suite.get("simcamera_tuning_before_after"), dict):
        return suite["simcamera_tuning_before_after"]
    return {}


def sim_camera_tuning_before_after_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("sweep_role", ""),
        metrics.get("profile_name", ""),
        metrics.get("baseline_gripper_finger_width_px", ""),
        metrics.get("current_gripper_finger_width_px", ""),
        metrics.get("marker_time_seconds", ""),
        metrics.get("baseline_candidate_count", ""),
        metrics.get("current_candidate_count", ""),
        metrics.get("current_vs_baseline_mean_abs_delta", ""),
        metrics.get("current_vs_baseline_rmse", ""),
        metrics.get("best_vs_baseline_best_mean_abs_delta", ""),
        metrics.get("best_vs_baseline_best_rmse", ""),
        metrics.get("remaining_tuning_prompt_count", ""),
        metrics.get("media_assets_copied_into_repo", ""),
        metrics.get("missing_real_depth_reference", ""),
        metrics.get("missing_pick_place_video", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def sim_camera_tuning_before_after_prompt_rows(tuning: dict[str, Any]) -> list[list[Any]]:
    prompts = tuning.get("remaining_tuning_prompts")
    prompt_rows = prompts if isinstance(prompts, list) else []
    rows: list[list[Any]] = []
    for prompt in prompt_rows:
        if not isinstance(prompt, dict):
            continue
        delta = prompt.get("delta_vs_current")
        delta = delta if isinstance(delta, dict) else {}
        rows.append(
            [
                prompt.get("sweep", ""),
                prompt.get("candidate", ""),
                prompt.get("description", ""),
                prompt.get("mean_abs_delta", ""),
                prompt.get("rmse", ""),
                delta.get("mean_abs_delta", ""),
                delta.get("rmse", ""),
            ]
        )
    return rows


def reference_capture_manifest_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    manifest = index.get("reference_capture_manifest")
    if isinstance(manifest, dict) and manifest:
        return manifest
    if suite is not None and isinstance(suite.get("reference_capture_manifest"), dict):
        return suite["reference_capture_manifest"]
    return {}


def reference_capture_manifest_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("ready_for_calibration_grade_simcamera_tuning", ""),
        metrics.get("depth_reference_capture_count", ""),
        metrics.get("pick_place_video_capture_count", ""),
        metrics.get("path_check_count", ""),
        metrics.get("missing_path_count", ""),
        metrics.get("media_assets_copied_into_repo", ""),
        compact_list(metrics.get("diagnostics")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def real_depth_capture_plan_artifact_index_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    plan_index = index.get("real_depth_capture_plan_artifact_index")
    if isinstance(plan_index, dict) and plan_index:
        return plan_index
    if suite is not None and isinstance(suite.get("real_depth_capture_plan_artifact_index"), dict):
        return suite["real_depth_capture_plan_artifact_index"]
    return {}


def real_depth_capture_plan_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("source_mode", ""),
        metrics.get("case_id", ""),
        metrics.get("evidence_status", compact_list(metrics.get("evidence_statuses"))),
        metrics.get("ready_for_calibration_grade_simcamera_tuning", ""),
        metrics.get("ready_case_count", ""),
        metrics.get("not_ready_case_count", ""),
        metrics.get("case_depth_reference_capture_count", metrics.get("depth_reference_capture_count", "")),
        metrics.get(
            "case_pick_place_video_capture_count",
            metrics.get("pick_place_video_capture_count", ""),
        ),
        metrics.get("case_missing_path_count", metrics.get("missing_path_count", "")),
        metrics.get("no_copy_status", compact_list(metrics.get("no_copy_statuses"))),
        metrics.get("case_next_operator_action_count", metrics.get("next_operator_action_count", "")),
        compact_list(
            metrics.get("case_next_operator_action_ids")
            or metrics.get("next_operator_action_ids")
        ),
        metrics.get("media_assets_copied_into_repo", ""),
        metrics.get("media_assets_opened_or_decoded", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def real_depth_capture_plan_case_rows(plan_index: dict[str, Any]) -> list[list[Any]]:
    cases = plan_index.get("cases")
    cases = cases if isinstance(cases, list) else plan_index.get("case_summaries")
    cases = cases if isinstance(cases, list) else []
    rows: list[list[Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        rows.append(
            [
                case.get("case_id", ""),
                case.get("evidence_source_kind", ""),
                case.get("evidence_status", ""),
                case.get("ready_for_calibration_grade_simcamera_tuning", ""),
                case.get("depth_reference_capture_count", ""),
                case.get("pick_place_video_capture_count", ""),
                case.get("missing_path_count", ""),
                case.get("no_copy_status", ""),
                compact_list(case.get("next_operator_action_ids")),
                markdown_link(str(case.get("planner_json_path")), str(case.get("planner_json_path")))
                if case.get("planner_json_path")
                else "",
                markdown_link(
                    str(case.get("planner_markdown_path")),
                    str(case.get("planner_markdown_path")),
                )
                if case.get("planner_markdown_path")
                else "",
            ]
        )
    return rows


def manifest_signal(index: dict[str, Any], suite: dict[str, Any] | None) -> dict[str, Any]:
    if suite is not None and isinstance(suite.get("reference_media_manifest"), dict):
        return suite["reference_media_manifest"]
    manifest = index.get("reference_media_manifest")
    return manifest if isinstance(manifest, dict) else {}


def gap_rows(gaps: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for gap in gaps:
        rows.append(
            [
                gap.get("category", ""),
                gap.get("status", ""),
                gap.get("note", ""),
            ]
        )
    return rows


def reference_capture_checklist_signal(index: dict[str, Any], suite: dict[str, Any] | None) -> dict[str, Any]:
    checklist = index.get("reference_capture_checklist")
    if isinstance(checklist, dict) and checklist:
        return checklist
    if suite is not None and isinstance(suite.get("reference_capture_checklist"), dict):
        return suite["reference_capture_checklist"]
    return {}


def checklist_artifact_rows(artifacts: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for artifact in artifacts:
        metrics = artifact.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        path = display_path(artifact)
        rows.append(
            [
                artifact.get("kind", ""),
                artifact.get("label", ""),
                markdown_link(path, link_path(artifact)) if path else "",
                metrics.get("status", ""),
                metrics.get("represented_media_count", ""),
                metrics.get("missing_requirement_count", ""),
                metrics.get("action_item_count", ""),
                metrics.get("real_camera_skipped", ""),
                "ok" if artifact.get("exists") is True else "missing",
            ]
        )
    return rows


def checklist_requirement_rows(checklist: dict[str, Any]) -> list[list[Any]]:
    requirements = checklist.get("capture_requirements")
    requirements = requirements if isinstance(requirements, list) else []
    rows: list[list[Any]] = []
    for item in requirements:
        if not isinstance(item, dict):
            continue
        template = item.get("manifest_template")
        template = template if isinstance(template, dict) else {}
        rows.append(
            [
                item.get("id", ""),
                item.get("status", ""),
                item.get("media_type", ""),
                item.get("represented_by") or item.get("partial_represented_by") or "",
                item.get("missing_evidence", ""),
                item.get("suggested_filenames", ""),
                template.get("calibration_targets", ""),
                template.get("failure_mode", ""),
                template.get("sim_profiles", ""),
            ]
        )
    return rows


def evidence_row(artifact: dict[str, Any]) -> list[Any]:
    exists = "ok" if artifact.get("exists") is True else "missing"
    target = link_path(artifact)
    label = str(artifact.get("label") or "")
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        label,
        markdown_link(path, target) if path else "",
        exists,
    ]


def linked_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for value in row:
            text = "" if value is None else str(value)
            cells.append(text.replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def metric_value(metrics: dict[str, Any], key: str) -> Any:
    aggregate = metrics.get("aggregate")
    if isinstance(aggregate, dict) and key in aggregate:
        return aggregate.get(key)
    return ""


def release_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    target_release = metrics.get("target_release_open")
    target_release = target_release if isinstance(target_release, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("scenario_id", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        target_release.get("visible_fraction", ""),
        target_release.get("occlusion_fraction", ""),
        target_release.get("min_clearance_px", metric_value(metrics, "min_clearance_px")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def pose_fixture_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("scenario_id", ""),
        artifact.get("kind", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("view", ""),
        metrics.get("target_square", ""),
        metrics.get("piece_square", ""),
        "ok" if metrics.get("metadata_intrinsics") is True else "",
        "ok" if metrics.get("metadata_distortion") is True else "",
        "ok" if metrics.get("metadata_extrinsics_board_to_camera") is True else "",
        "ok" if metrics.get("metadata_coordinate_frames") is True else "",
        "ok" if artifact.get("exists") is True else "missing",
    ]


def gripper_camera_pov_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("scenario_id", ""),
        artifact.get("kind", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("target_square", ""),
        metrics.get("target_center_xy", ""),
        metrics.get("visible_fraction", ""),
        metrics.get("occlusion_fraction", ""),
        metrics.get("min_clearance_px", ""),
        metrics.get("tracked_gripper_percent", ""),
        metrics.get("current_gripper_opening_px", ""),
        "ok" if metrics.get("metadata_contract_ok") is True else "",
        "ok" if artifact.get("exists") is True else "missing",
    ]


def visual_review_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    dimensions = metrics.get("output_dimensions")
    if not isinstance(dimensions, dict):
        dimensions = metrics.get("dimensions")
    dimensions = dimensions if isinstance(dimensions, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("source_frame_count", ""),
        metrics.get("source_frame_labels", ""),
        (
            f"{dimensions.get('width_px')}x{dimensions.get('height_px')}"
            if dimensions.get("width_px") and dimensions.get("height_px")
            else ""
        ),
        metrics.get("codec", ""),
        metrics.get("duration_seconds", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def depth_distance_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    true_depth = metrics.get("true_depth_estimation")
    true_depth = true_depth if isinstance(true_depth, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("frame_count", ""),
        metrics.get("example_camera_to_piece_distance_mm", ""),
        metrics.get("example_camera_to_board_plane_distance_mm", ""),
        metrics.get("example_gripper_to_piece_distance_mm", ""),
        metrics.get("gripper_to_piece_distance_source", ""),
        metrics.get("perceived_depth_status", true_depth.get("status", "")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def depth_distance_scorecard_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("frame_count", ""),
        metrics.get("review_status", ""),
        metrics.get("at_a_glance", ""),
        metrics.get("baseline_quality", ""),
        metrics.get("worst_mean_abs_depth_error_mm", ""),
        metrics.get("mean_board_corner_reprojection_residual_px", ""),
        metrics.get("mean_metadata_projected_corner_residual_px", ""),
        metrics.get("not_geometrically_comparable_row_count", ""),
        metrics.get("real_camera_depth_status", ""),
        metrics.get("real_depth_depth_row_count", ""),
        metrics.get("mean_real_vs_sim_projection_residual_px", ""),
        metrics.get("mean_abs_real_vs_sim_depth_residual_mm", ""),
        metrics.get("real_depth_reference_missing_inputs", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def depth_distance_scorecard_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    visual_review = index.get("visual_review")
    if isinstance(visual_review, dict):
        candidates.append(visual_review)
    if suite is not None and isinstance(suite.get("visual_review"), dict):
        candidates.append(suite["visual_review"])
    for candidate in candidates:
        scorecard = candidate.get("depth_distance_scorecard")
        if isinstance(scorecard, dict) and scorecard:
            return scorecard
    return {}


def depth_distance_scorecard_stage_rows(scorecard: dict[str, Any]) -> list[list[Any]]:
    rows = scorecard.get("stage_rows")
    rows = rows if isinstance(rows, list) else []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sim_ground_truth = row.get("sim_ground_truth")
        sim_ground_truth = sim_ground_truth if isinstance(sim_ground_truth, dict) else {}
        baseline = row.get("metadata_derived_baseline")
        baseline = baseline if isinstance(baseline, dict) else {}
        out.append(
            [
                row.get("stage", ""),
                sim_ground_truth.get("camera_to_piece_distance_mm", ""),
                baseline.get("estimated_camera_to_piece_distance_mm", ""),
                baseline.get("camera_to_piece_abs_error_mm", ""),
                sim_ground_truth.get("camera_to_board_plane_distance_mm", ""),
                baseline.get("estimated_camera_to_board_plane_distance_mm", ""),
                baseline.get("camera_to_board_abs_error_mm", ""),
                baseline.get("board_corner_reprojection_mean_residual_px", ""),
                baseline.get("pnp_vs_sim_ground_truth_status", ""),
                row.get("status", ""),
            ]
        )
    return out


def perceived_depth_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("frame_count", ""),
        metrics.get("estimator", ""),
        metrics.get("estimator_status", ""),
        metrics.get("example_estimated_camera_to_piece_distance_mm", ""),
        metrics.get("example_ground_truth_camera_to_piece_distance_mm", ""),
        metrics.get("example_camera_to_piece_error_mm", ""),
        metrics.get("mean_abs_camera_to_piece_error_mm", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def perceived_depth_comparison_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    visual_review = index.get("visual_review")
    if isinstance(visual_review, dict):
        candidates.append(visual_review)
    if suite is not None and isinstance(suite.get("visual_review"), dict):
        candidates.append(suite["visual_review"])
    for candidate in candidates:
        comparison = candidate.get("perceived_depth_comparison")
        if isinstance(comparison, dict) and comparison:
            return comparison
    return {}


def perceived_depth_stage_rows(comparison: dict[str, Any]) -> list[list[Any]]:
    rows = comparison.get("rows")
    rows = rows if isinstance(rows, list) else []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            [
                row.get("stage", ""),
                row.get("estimator", ""),
                row.get("perceived_depth_status", ""),
                row.get("estimated_camera_to_piece_distance_mm", ""),
                row.get("ground_truth_camera_to_piece_distance_mm", ""),
                row.get("camera_to_piece_error_mm", ""),
                row.get("estimated_camera_to_board_plane_distance_mm", ""),
                row.get("ground_truth_camera_to_board_plane_distance_mm", ""),
                row.get("camera_to_board_error_mm", ""),
                row.get("board_corner_reprojection_mean_residual_px", ""),
                row.get("status", ""),
            ]
        )
    return out


def pnp_residual_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("frame_count", ""),
        metrics.get("mean_metadata_projected_corner_residual_px", ""),
        metrics.get("mean_rendered_corner_pnp_reprojection_residual_px", ""),
        metrics.get("mean_abs_rendered_corner_pnp_camera_to_piece_error_mm", ""),
        metrics.get("mean_abs_rendered_corner_pnp_camera_to_board_error_mm", ""),
        metrics.get("not_geometrically_comparable_row_count", ""),
        metrics.get("example_reason_labels", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def pnp_residual_diagnostic_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    visual_review = index.get("visual_review")
    if isinstance(visual_review, dict):
        candidates.append(visual_review)
    if suite is not None and isinstance(suite.get("visual_review"), dict):
        candidates.append(suite["visual_review"])
    for candidate in candidates:
        diagnostic = candidate.get("pnp_residual_diagnostics")
        if isinstance(diagnostic, dict) and diagnostic:
            return diagnostic
    return {}


def pnp_residual_stage_rows(diagnostic: dict[str, Any]) -> list[list[Any]]:
    rows = diagnostic.get("rows")
    rows = rows if isinstance(rows, list) else []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        comparability = row.get("source_comparability")
        comparability = comparability if isinstance(comparability, dict) else {}
        pnp_vs_gt = comparability.get("rendered_board_corner_pnp_vs_sim_ground_truth")
        pnp_vs_gt = pnp_vs_gt if isinstance(pnp_vs_gt, dict) else {}
        out.append(
            [
                row.get("stage", ""),
                row.get("metadata_projected_corner_mean_residual_px", ""),
                row.get("rendered_corner_pnp_reprojection_mean_residual_px", ""),
                row.get("rendered_corner_pnp_camera_center_delta_norm_mm", ""),
                row.get("rendered_corner_pnp_camera_to_piece_error_mm", ""),
                row.get("rendered_corner_pnp_camera_to_board_error_mm", ""),
                pnp_vs_gt.get("status", ""),
                row.get("reason_labels", ""),
                row.get("status", ""),
            ]
        )
    return out


def metadata_native_depth_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("frame_count", ""),
        metrics.get("row_count", ""),
        metrics.get("source_model", ""),
        metrics.get("example_metadata_projected_pixel_xy", ""),
        metrics.get("example_camera_z_depth_mm", ""),
        metrics.get("example_camera_range_mm", ""),
        metrics.get("example_board_plane_distance_mm", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def metadata_native_depth_view_signal(
    index: dict[str, Any],
    suite: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    visual_review = index.get("visual_review")
    if isinstance(visual_review, dict):
        candidates.append(visual_review)
    if suite is not None and isinstance(suite.get("visual_review"), dict):
        candidates.append(suite["visual_review"])
    for candidate in candidates:
        view = candidate.get("metadata_native_depth_view")
        if isinstance(view, dict) and view:
            return view
    return {}


def metadata_native_depth_stage_rows(view: dict[str, Any]) -> list[list[Any]]:
    rows = view.get("rows")
    rows = rows if isinstance(rows, list) else []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            [
                row.get("stage", ""),
                row.get("point_role", ""),
                row.get("square", ""),
                row.get("metadata_projected_pixel_xy", ""),
                row.get("camera_frame_xyz_mm", ""),
                row.get("camera_z_depth_mm", ""),
                row.get("camera_range_mm", ""),
                row.get("board_plane_distance_mm", ""),
                row.get("source_model", ""),
                row.get("status", ""),
            ]
        )
    return out


def so101_model_contract_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("model_request_status", ""),
        metrics.get("model_request_path", ""),
        metrics.get("robot_kinematics_status", ""),
        metrics.get("robot_kinematics_directly_usable", ""),
        metrics.get("target_frame", ""),
        metrics.get("missing_alignment_input_count", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_model_asset_preflight_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("model_request_status", ""),
        metrics.get("mesh_reference_count", ""),
        metrics.get("present_asset_count", ""),
        metrics.get("missing_asset_count", ""),
        metrics.get("unresolved_reference_count", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_model_source_inventory_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("candidate_count", ""),
        metrics.get("likely_candidate_count", ""),
        metrics.get("direct_contract_candidate_count", ""),
        metrics.get("authoritative_candidate_count", ""),
        metrics.get("authoritative_source_selection_status", ""),
        metrics.get("selected_authoritative_candidate_path", ""),
        metrics.get("selected_authoritative_candidate_sha256", ""),
        metrics.get("source_scan_mode", ""),
        source_root_summary(metrics),
        source_authority_summary(metrics),
        metrics.get("source_authority_review_status", ""),
        metrics.get("source_authority_review_ready", ""),
        metrics.get("source_authority_review_scope_ready", ""),
        compact_list(metrics.get("source_authority_missing_review_scope_ids")),
        metrics.get("source_authority_gate_status", ""),
        compact_list(metrics.get("source_authority_blockers")),
        metrics.get("recommended_contract_check_path", ""),
        metrics.get("next_required_action_count", ""),
        compact_list(metrics.get("next_required_action_ids")),
        metrics.get("review_packet_status", ""),
        metrics.get("review_packet_model_authority", ""),
        metrics.get("review_packet_item_count", ""),
        compact_list(metrics.get("review_packet_action_ids")),
        metrics.get("review_packet_observed_evidence_is_authority", ""),
        metrics.get("review_packet_development_fixture_evidence_not_physical_so101_truth", ""),
        metrics.get("review_packet_physical_so101_model_authority_ready", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_reviewed_model_authority_gate_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("review_status", ""),
        metrics.get("ready", ""),
        metrics.get("source_authority_ready", ""),
        metrics.get("source_authority_gate_status", ""),
        metrics.get("physical_so101_model_authority_ready", ""),
        metrics.get("physical_authority_gate_status", ""),
        metrics.get("source_bundle_consistency_ready", ""),
        metrics.get("source_bundle_consistency_status", ""),
        metrics.get("reviewed_mujoco_motion_bundle_consistency_ready", ""),
        metrics.get("reviewed_mujoco_motion_bundle_consistency_status", ""),
        metrics.get("physical_reviewed_model_motion_checked", ""),
        metrics.get("physical_reviewed_model_motion_reported", ""),
        metrics.get("physical_reviewed_model_motion_status_ready", ""),
        metrics.get("physical_reviewed_model_motion_child_ready", ""),
        metrics.get("reviewed_mujoco_bundle_status", ""),
        metrics.get("reviewed_mujoco_motion_authority_status", ""),
        metrics.get("development_fixture_evidence_not_physical_so101_truth", ""),
        metrics.get("blocker_count", ""),
        compact_list(metrics.get("blockers")),
        metrics.get("blocker_packet_status", ""),
        metrics.get("blocker_packet_model_authority", ""),
        metrics.get("blocker_packet_item_count", ""),
        metrics.get("blocker_packet_action_required_count", ""),
        compact_list(metrics.get("blocker_packet_blocked_by_prior_requirements_item_ids")),
        compact_list(metrics.get("blocker_packet_next_action_ids")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_model_bundle_manifest_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("manifest_request_status", ""),
        metrics.get("ready_for_model_backed_ik", ""),
        metrics.get("model_authority", ""),
        metrics.get("physical_authority_gate_status", ""),
        metrics.get("physical_so101_model_authority_ready", ""),
        compact_list(metrics.get("physical_authority_blockers")),
        metrics.get("hardware_free_regression_fixture_ready", ""),
        compact_list(metrics.get("synthetic_fixture_authority_fields")),
        metrics.get("review_packet_status", ""),
        metrics.get("review_packet_model_authority", ""),
        metrics.get("review_packet_item_count", ""),
        compact_list(metrics.get("review_packet_action_ids")),
        metrics.get("next_required_action_count", ""),
        compact_list(metrics.get("next_required_action_ids")),
        metrics.get("model_path", ""),
        compact_list(metrics.get("asset_roots")),
        metrics.get("joint_limits_status", ""),
        metrics.get("mesh_assets_status", ""),
        metrics.get("mesh_assets_mesh_reference_count", ""),
        metrics.get("target_frame", ""),
        metrics.get("tcp_offset_field", ""),
        metrics.get("base_to_board_alignment_status", ""),
        metrics.get("contract_status", ""),
        metrics.get("asset_preflight_status", ""),
        metrics.get("diagnostic_only", ""),
        metrics.get("diagnostic_only_reason", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_model_bundle_probe_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("model_authority", ""),
        metrics.get("selected_model_path", ""),
        metrics.get("model_request_status", ""),
        metrics.get("contract_status", ""),
        metrics.get("asset_preflight_status", ""),
        metrics.get("asset_preflight_mesh_reference_count", ""),
        metrics.get("asset_preflight_missing_asset_count", ""),
        metrics.get("asset_preflight_unresolved_reference_count", ""),
        metrics.get("observed_source_hints_status", ""),
        metrics.get("observed_joint_limits_status", ""),
        metrics.get("observed_joint_limits_complete", ""),
        metrics.get("mesh_asset_review_status", ""),
        metrics.get("manifest_status", ""),
        metrics.get("ready_for_model_backed_ik", ""),
        metrics.get("review_packet_status", ""),
        metrics.get("review_packet_model_authority", ""),
        metrics.get("review_packet_item_count", ""),
        compact_list(metrics.get("review_packet_item_ids")),
        metrics.get("next_required_action_count", ""),
        compact_list(metrics.get("next_required_action_ids")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_mujoco_smoke_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("model_authority", ""),
        metrics.get("physical_so101_model_authority_ready", ""),
        metrics.get("hardware_free_regression_fixture_ready", ""),
        metrics.get("ready_for_model_backed_ik", ""),
        metrics.get("reviewed_model_motion_checked", ""),
        metrics.get("motion_authority_status", ""),
        metrics.get("physical_reviewed_model_motion_checked", ""),
        metrics.get("hardware_free_fixture_motion_checked", ""),
        metrics.get("gymnasium_available", ""),
        metrics.get("mujoco_available", ""),
        metrics.get("all_resets_ok", ""),
        metrics.get("all_board_contacts_observed", ""),
        metrics.get("gripper_contact_observed", ""),
        metrics.get("lift_place_physics_verified", ""),
        metrics.get("source_pick_started_at_source", ""),
        metrics.get("board_source_pick_place_verified", ""),
        metrics.get("robot_pose_seeded_for_source_fixture", ""),
        metrics.get("final_board_contact_observed", ""),
        metrics.get("final_target_xy_error_m", ""),
        metrics.get("episode_count", ""),
        metrics.get("transition_count", ""),
        compact_list(metrics.get("next_required_action_ids") or metrics.get("next_required_for_goal")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def so101_training_readiness_gate_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("ready", ""),
        metrics.get("reviewed_model_authority_ready", ""),
        metrics.get("reviewed_model_authority_status", ""),
        metrics.get("reviewed_model_physical_motion_checked", ""),
        metrics.get("reviewed_model_backed_board_source_pick_place", ""),
        metrics.get("board_pick_status", ""),
        metrics.get("board_pick_model_authority", ""),
        metrics.get("board_pick_reviewed_model_authority_ready", ""),
        metrics.get("board_pick_detailed_evidence_ready", ""),
        metrics.get("board_pick_ready_for_model_backed_ik", ""),
        metrics.get("board_pick_robot_pose_seeded_for_source_fixture", ""),
        metrics.get("rollout_ready_for_policy_training", ""),
        metrics.get("rollout_policy_training_authority_ready", ""),
        metrics.get("rollout_training_authority_status", ""),
        metrics.get("rollout_model_authority", ""),
        metrics.get("rollout_use", ""),
        metrics.get("development_fixture_evidence_not_policy_training_truth", ""),
        compact_list(metrics.get("priority_gate_order")),
        metrics.get("next_priority_gate_id", ""),
        compact_list(metrics.get("next_priority_action_ids")),
        compact_list(metrics.get("development_evidence_only_gate_ids")),
        compact_list(metrics.get("blocked_by_prior_gate_ids")),
        metrics.get("blocker_count", ""),
        compact_list(metrics.get("blockers")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def real_projection_intake_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("real_reference_media_count", ""),
        metrics.get("comparable_count", ""),
        metrics.get("depth_comparable_count", ""),
        metrics.get("sidecar_valid_count", ""),
        metrics.get("sidecar_invalid_count", ""),
        metrics.get("sidecar_missing_count", ""),
        metrics.get("missing_inputs", ""),
        metrics.get("sim_expected_projected_point_count", ""),
        metrics.get("residual_available", ""),
        metrics.get("residual_projection_row_count", ""),
        metrics.get("mean_real_vs_sim_projection_residual_px", ""),
        metrics.get("mean_abs_real_vs_sim_depth_residual_mm", ""),
        metrics.get("real_camera_capture_skipped", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def reference_media_inventory_artifact_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("status", ""),
        metrics.get("candidate_count", ""),
        metrics.get("image_count", ""),
        metrics.get("video_count", ""),
        metrics.get("calibration_data_count", ""),
        metrics.get("currently_wired_media_count", ""),
        metrics.get("current_gripper_reference_detected", ""),
        compact_list(metrics.get("reference_gaps")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def real_projection_intake_signal(index: dict[str, Any], suite: dict[str, Any] | None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    intake = index.get("real_projection_intake")
    if isinstance(intake, dict):
        candidates.append(intake)
    if suite is not None and isinstance(suite.get("real_projection_intake"), dict):
        candidates.append(suite["real_projection_intake"])
    for candidate in candidates:
        if candidate:
            return candidate
    return {}


def real_projection_intake_record_rows(intake: dict[str, Any]) -> list[list[Any]]:
    records = intake.get("records")
    records = records if isinstance(records, list) else []
    rows: list[list[Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        next_requirements = record.get("next_capture_requirements")
        requirement_ids = [
            item.get("id")
            for item in next_requirements
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ] if isinstance(next_requirements, list) else []
        residuals = record.get("residuals")
        residuals = residuals if isinstance(residuals, dict) else {}
        residual_aggregate = residuals.get("aggregate")
        residual_aggregate = residual_aggregate if isinstance(residual_aggregate, dict) else {}
        rows.append(
            [
                record.get("real_reference_media_relative_path") or record.get("real_reference_media_path", ""),
                record.get("status", ""),
                record.get("real_intrinsics_status", ""),
                record.get("real_extrinsics_status", ""),
                record.get("real_board_pose_status", ""),
                record.get("real_depth_status", ""),
                record.get("sidecar_validation", {}).get("valid_count", "")
                if isinstance(record.get("sidecar_validation"), dict)
                else "",
                record.get("sidecar_validation", {}).get("invalid_count", "")
                if isinstance(record.get("sidecar_validation"), dict)
                else "",
                record.get("sim_expected_projected_point_count", ""),
                record.get("comparable", ""),
                residuals.get("available", ""),
                residual_aggregate.get("projected_point_count", ""),
                residual_aggregate.get("board_corner_observation_count", ""),
                residual_aggregate.get("depth_reference_count", ""),
                record.get("missing_inputs", ""),
                requirement_ids,
            ]
        )
    return rows


def app_entrypoint_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("sim_camera_profile", ""),
        "ok" if metrics.get("metadata_contract_ok") is True else "",
        metrics.get("metadata_contract_check_count", ""),
        metrics.get("metadata_contract_failed_check_count", ""),
        metrics.get("hardware_skipped", ""),
        metrics.get("gui_skipped", ""),
        metrics.get("openai_skipped", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def negative_status(index: dict[str, Any], suite: dict[str, Any] | None) -> Any:
    if suite is not None:
        negative = suite.get("negative_check")
        if isinstance(negative, dict) and negative.get("status") is not None:
            return negative.get("status")
    for artifact in index.get("artifacts", []):
        if not isinstance(artifact, dict) or artifact.get("category") != "negative_check":
            continue
        metrics = artifact.get("metrics")
        if isinstance(metrics, dict) and metrics.get("status") is not None:
            return metrics.get("status")
    return ""


def child_log_rows(logs: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for artifact in logs:
        label = str(artifact.get("label") or "")
        if "stdout_path" not in label and "stderr_path" not in label:
            continue
        metrics = artifact.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        path = display_path(artifact)
        rows.append(
            [
                label,
                markdown_link(path, link_path(artifact)) if path else "",
                metrics.get("ok", ""),
                metrics.get("return_code", ""),
                "ok" if artifact.get("exists") is True else "missing",
            ]
        )
    return rows


def append_artifact_group(lines: list[str], category: str, artifacts: list[dict[str, Any]]) -> None:
    lines.append(f"### {CATEGORY_LABELS.get(category, category)}")
    if not artifacts:
        lines.append("")
        lines.append("_No artifacts indexed._")
        lines.append("")
        return
    rows: list[list[Any]] = []
    for artifact in artifacts:
        detail_parts = []
        if artifact.get("scenario_id") is not None:
            detail_parts.append(f"scenario={artifact.get('scenario_id')}")
        if artifact.get("candidate_id") is not None:
            detail_parts.append(f"candidate={artifact.get('candidate_id')}")
        if artifact.get("rank") is not None:
            detail_parts.append(f"rank={artifact.get('rank')}")
        rows.append(evidence_row(artifact) + [", ".join(detail_parts)])
    lines.extend(linked_table(["Kind", "Label", "Path", "Status", "Details"], rows))
    lines.append("")


def render_report(index: dict[str, Any], suite: dict[str, Any] | None, artifact_index_path: Path) -> str:
    grouped = artifacts_by_category(index)
    lines: list[str] = [
        "# Simulator Calibration Artifact Index Report",
        "",
        "## Run Metadata",
    ]
    suite_status = index.get("suite_status")
    suite_status = suite_status if isinstance(suite_status, dict) else {}
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["artifact_index_status", index.get("status", "")],
                ["artifact_count", len(index.get("artifacts", []))],
                ["missing_artifact_count", len(index.get("missing_artifacts", []))],
                ["suite_status", suite_status.get("status", "")],
                ["suite_ok", suite_status.get("ok", "")],
                ["output_dir", index.get("output_dir", "")],
                ["suite_summary_path", index.get("suite_summary_path", "")],
                ["artifact_index_path", str(artifact_index_path)],
            ],
        )
    )

    lines.extend(["", "## Category Summary"])
    lines.extend(
        table(
            ["Category", "Artifacts", "Missing"],
            [
                [CATEGORY_LABELS.get(row["category"], row["category"]), row["artifact_count"], row["missing_count"]]
                for row in category_rows(index)
            ],
        )
    )

    lines.extend(["", "## Skipped Hardware, GUI, And OpenAI"])
    lines.extend(table(["Path", "Skipped", "Marker"], skipped_marker_rows(index, suite)))

    lines.extend(["", "## Reference Media Inventory"])
    reference_inventory = reference_media_inventory_signal(index, suite)
    current_reference = inventory_current_gripper_reference(reference_inventory)
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", inventory_summary_value(reference_inventory, "status")],
                ["candidate_count", inventory_summary_value(reference_inventory, "candidate_count")],
                ["image_count", inventory_summary_value(reference_inventory, "image_count")],
                ["video_count", inventory_summary_value(reference_inventory, "video_count")],
                [
                    "calibration_data_count",
                    inventory_summary_value(reference_inventory, "calibration_data_count"),
                ],
                [
                    "currently_wired_media_count",
                    inventory_summary_value(reference_inventory, "currently_wired_media_count"),
                ],
                ["current_gripper_reference_detected", current_reference.get("detected", "")],
                ["current_gripper_reference_path", current_reference.get("path", "")],
                ["reference_gaps", inventory_reference_gaps(reference_inventory)],
            ],
        )
    )
    inventory_artifacts = grouped.get("reference_media_inventory", [])
    lines.append("")
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Inventory Status",
                "Candidates",
                "Images",
                "Videos",
                "Calibration Data",
                "Wired",
                "Current Gripper Ref",
                "Gaps",
                "Artifact Status",
            ],
            [reference_media_inventory_artifact_row(row) for row in inventory_artifacts],
        )
        if inventory_artifacts
        else ["_No reference media inventory artifacts indexed._"]
    )
    lines.extend(["", "### Manifest And Selected Media"])
    manifest = manifest_signal(index, suite)
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["manifest_supplied", manifest.get("supplied", "")],
                ["manifest_status", manifest.get("status", "")],
                ["manifest_path", manifest.get("path", "")],
                ["declared_media_count", manifest.get("declared_media_count", "")],
                ["matched_media_count", manifest.get("matched_media_count", "")],
                ["selected_declared_media_count", manifest.get("selected_declared_media_count", "")],
            ],
        )
    )
    lines.append("")
    media_rows = selected_media_rows(index)
    if media_rows:
        lines.extend(
            table(
                [
                    "Media",
                    "Type",
                    "Dimensions",
                    "Wired",
                    "Manifest",
                    "Capture",
                    "Declared Targets",
                    "Failure Mode",
                ],
                media_rows,
            )
        )
    else:
        lines.append("_No real reference media selected in the artifact index._")
    gaps = suite_inventory_gaps(suite)
    if gaps:
        lines.extend(["", "### Visibility Gaps"])
        lines.append("")
        lines.extend(table(["Gap", "Status", "Note"], gap_rows(gaps)))
    else:
        lines.append("")
        lines.append("_No inventory visibility gaps were available from the suite summary._")

    lines.extend(["", "## Reference Media Comparison"])
    reference_comparison = reference_media_comparison_signal(index, suite)
    reference_comparison_artifacts = grouped.get("reference_media_comparison", [])
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", reference_comparison.get("status", "")],
                ["selected_candidate_count", reference_comparison.get("selected_candidate_count", "")],
                ["selected_media_count", reference_comparison.get("selected_media_count", "")],
                ["visual_comparison_count", reference_comparison.get("visual_comparison_count", "")],
                ["failed_comparison_count", reference_comparison.get("failed_comparison_count", "")],
                ["contact_sheet_status", reference_comparison.get("contact_sheet_status", "")],
                ["contact_sheet_path", reference_comparison.get("contact_sheet_path", "")],
                [
                    "media_assets_copied_into_repo",
                    reference_comparison.get("media_assets_copied_into_repo", ""),
                ],
                ["external_selected_count", reference_comparison.get("external_selected_count", "")],
                ["missing_depth_reference", reference_comparison.get("missing_depth_reference", "")],
                ["missing_pick_place_video", reference_comparison.get("missing_pick_place_video", "")],
                ["no_videos", reference_comparison.get("no_videos", "")],
                ["summary_path", reference_comparison.get("summary_path", "")],
                ["csv_path", reference_comparison.get("csv_path", "")],
                ["readme_path", reference_comparison.get("readme_path", "")],
            ],
        )
    )
    lines.append("")
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Comparison Status",
                "Selected Candidates",
                "Selected Media",
                "Visual Comparisons",
                "Contact Sheet",
                "Copied Into Repo",
                "External Selected",
                "Missing Depth",
                "Missing Pick/Place Video",
                "No Videos",
                "Artifact Status",
            ],
            [reference_media_comparison_artifact_row(row) for row in reference_comparison_artifacts],
        )
        if reference_comparison_artifacts
        else ["_No reference media comparison artifacts indexed._"]
    )

    lines.extend(["", "## Reference Camera Tuning Diagnostics"])
    tuning = reference_camera_tuning_signal(index, suite)
    tuning_artifacts = grouped.get("reference_camera_tuning_diagnostics", [])
    external = tuning.get("external_local_evidence_only")
    external = external if isinstance(external, dict) else {}
    gaps = tuning.get("reference_gap_carry_through")
    gaps = gaps if isinstance(gaps, dict) else {}
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", tuning.get("status", "")],
                ["selected_comparison_count", tuning.get("selected_comparison_count", "")],
                ["visual_comparison_count", tuning.get("visual_comparison_count", "")],
                ["metadata_only_count", tuning.get("metadata_only_count", "")],
                [
                    "suggested_tuning_dimensions",
                    compact_list(tuning.get("suggested_tuning_dimension_names") or tuning.get("suggested_tuning_dimensions")),
                ],
                ["scorecard_status", tuning.get("scorecard_status", "")],
                ["scorecard_path", tuning.get("scorecard_path", "")],
                [
                    "media_assets_copied_into_repo",
                    tuning.get("media_assets_copied_into_repo", ""),
                ],
                [
                    "external_selected_count",
                    tuning.get("external_selected_count", external.get("external_selected_count", "")),
                ],
                [
                    "absolute_sibling_paths_are_local_evidence_only",
                    tuning.get(
                        "absolute_sibling_paths_are_local_evidence_only",
                        external.get("absolute_sibling_paths_are_local_evidence_only", ""),
                    ),
                ],
                [
                    "missing_depth_reference",
                    tuning.get("missing_depth_reference", gaps.get("missing_depth_reference", "")),
                ],
                [
                    "missing_pick_place_video",
                    tuning.get("missing_pick_place_video", gaps.get("missing_pick_place_video", "")),
                ],
                ["no_videos", tuning.get("no_videos", gaps.get("no_videos", ""))],
                ["summary_path", tuning.get("summary_path", "")],
                ["csv_path", tuning.get("csv_path", "")],
                ["readme_path", tuning.get("readme_path", "")],
            ],
        )
    )
    lines.append("")
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Diagnostics Status",
                "Selected",
                "Visual",
                "Metadata Only",
                "Suggested Dimensions",
                "Scorecard Status",
                "Scorecard Produced",
                "Copied Into Repo",
                "External Selected",
                "External Local Only",
                "Missing Depth",
                "Missing Pick/Place Video",
                "No Videos",
                "Artifact Status",
            ],
            [reference_camera_tuning_artifact_row(row) for row in tuning_artifacts],
        )
        if tuning_artifacts
        else ["_No reference camera tuning diagnostics artifacts indexed._"]
    )

    lines.extend(["", "## SimCamera Profile Sweep"])
    profile_sweep = sim_camera_profile_sweep_signal(index, suite)
    profile_sweep_artifacts = grouped.get("sim_camera_profile_sweep", [])
    current_vs_best = profile_sweep.get("current_vs_best_metrics")
    current_vs_best = current_vs_best if isinstance(current_vs_best, dict) else {}
    lines.append(
        "This deterministic hardware-free child renders the current SimCamera profile and "
        "explicit perturbation candidates against the saved gripper reference. Full-frame "
        "image deltas are coarse review evidence, not physical calibration truth."
    )
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", profile_sweep.get("status", "")],
                ["profile_name", profile_sweep.get("profile_name", "")],
                [
                    "current_gripper_finger_width_px",
                    profile_sweep.get("current_gripper_finger_width_px", ""),
                ],
                ["marker_time_seconds", profile_sweep.get("marker_time_seconds", "")],
                ["candidate_count", profile_sweep.get("candidate_count", "")],
                ["current_mean_abs_delta", current_vs_best.get("current_mean_abs_delta", "")],
                ["current_rmse", current_vs_best.get("current_rmse", "")],
                ["best_candidate_id", profile_sweep.get("best_candidate_id", "")],
                ["best_candidate_name", profile_sweep.get("best_candidate_name", "")],
                ["best_mean_abs_delta", current_vs_best.get("best_mean_abs_delta", "")],
                ["best_rmse", current_vs_best.get("best_rmse", "")],
                [
                    "mean_abs_delta_delta_vs_current",
                    current_vs_best.get("mean_abs_delta_delta_vs_current", ""),
                ],
                ["rmse_delta_vs_current", current_vs_best.get("rmse_delta_vs_current", "")],
                [
                    "full_frame_image_delta_caveat",
                    profile_sweep.get("full_frame_image_delta_caveat", ""),
                ],
                ["summary_path", profile_sweep.get("summary_path", "")],
                ["candidate_montage_path", profile_sweep.get("candidate_montage_path", "")],
                ["candidate_dir", profile_sweep.get("candidate_dir", "")],
            ],
        )
    )
    lines.extend(["", "### Candidate Ranking"])
    ranking_rows = sim_camera_profile_sweep_ranking_rows(profile_sweep)
    lines.extend(
        linked_table(
            [
                "Rank",
                "Candidate",
                "Description",
                "MAD",
                "RMSE",
                "MAD Delta",
                "RMSE Delta",
                "Annotated Frame",
            ],
            ranking_rows,
        )
        if ranking_rows
        else ["_No SimCamera profile sweep ranking was available._"]
    )
    lines.extend(["", "### Remaining Tuning Prompts"])
    prompt_rows = sim_camera_profile_sweep_prompt_rows(profile_sweep)
    lines.extend(
        table(["Candidate", "Description", "MAD Delta", "RMSE Delta"], prompt_rows)
        if prompt_rows
        else ["_No lower-MAD perturbation prompts remained in this sweep._"]
    )
    lines.extend(["", "### Sweep Artifacts"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Profile",
                "Finger Width",
                "Marker Time",
                "Candidates",
                "Best",
                "Current MAD",
                "Current RMSE",
                "Best MAD",
                "Best RMSE",
                "MAD Delta",
                "RMSE Delta",
                "Candidate",
                "Candidate MAD",
                "Candidate RMSE",
                "Artifact Status",
            ],
            [sim_camera_profile_sweep_artifact_row(row) for row in profile_sweep_artifacts],
        )
        if profile_sweep_artifacts
        else ["_No SimCamera profile sweep artifacts indexed._"]
    )

    lines.extend(["", "## SimCamera Tuning Before/After"])
    tuning_before_after = sim_camera_tuning_before_after_signal(index, suite)
    tuning_before_after_artifacts = grouped.get("sim_camera_tuning_before_after", [])
    lines.append(
        "This deterministic hardware-free child compares the documented 72px baseline "
        "gripper-reference width against the current canonical SimCamera profile. "
        "Full-frame image deltas are coarse review evidence, not physical calibration truth."
    )
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", tuning_before_after.get("status", "")],
                ["profile_name", tuning_before_after.get("profile_name", "")],
                [
                    "baseline_gripper_finger_width_px",
                    tuning_before_after.get("baseline_gripper_finger_width_px", ""),
                ],
                [
                    "current_gripper_finger_width_px",
                    tuning_before_after.get("current_gripper_finger_width_px", ""),
                ],
                ["marker_time_seconds", tuning_before_after.get("marker_time_seconds", "")],
                [
                    "baseline_candidate_count",
                    tuning_before_after.get("baseline_candidate_count", ""),
                ],
                [
                    "current_candidate_count",
                    tuning_before_after.get("current_candidate_count", ""),
                ],
                [
                    "baseline_current_mean_abs_delta",
                    tuning_before_after.get("baseline_current_mean_abs_delta", ""),
                ],
                ["baseline_current_rmse", tuning_before_after.get("baseline_current_rmse", "")],
                [
                    "current_profile_mean_abs_delta",
                    tuning_before_after.get("current_profile_mean_abs_delta", ""),
                ],
                ["current_profile_rmse", tuning_before_after.get("current_profile_rmse", "")],
                [
                    "current_vs_baseline_mean_abs_delta",
                    tuning_before_after.get("current_vs_baseline_mean_abs_delta", ""),
                ],
                [
                    "current_vs_baseline_rmse",
                    tuning_before_after.get("current_vs_baseline_rmse", ""),
                ],
                [
                    "baseline_best_candidate",
                    tuning_before_after.get("baseline_best_candidate", ""),
                ],
                ["current_best_candidate", tuning_before_after.get("current_best_candidate", "")],
                [
                    "best_vs_baseline_best_mean_abs_delta",
                    tuning_before_after.get("best_vs_baseline_best_mean_abs_delta", ""),
                ],
                [
                    "best_vs_baseline_best_rmse",
                    tuning_before_after.get("best_vs_baseline_best_rmse", ""),
                ],
                [
                    "remaining_tuning_prompt_count",
                    tuning_before_after.get("remaining_tuning_prompt_count", ""),
                ],
                [
                    "media_assets_copied_into_repo",
                    tuning_before_after.get("media_assets_copied_into_repo", ""),
                ],
                [
                    "missing_real_depth_reference",
                    tuning_before_after.get("missing_real_depth_reference", ""),
                ],
                [
                    "missing_pick_place_video",
                    tuning_before_after.get("missing_pick_place_video", ""),
                ],
                [
                    "full_frame_image_delta_caveat",
                    tuning_before_after.get("full_frame_image_delta_caveat", ""),
                ],
                ["summary_path", tuning_before_after.get("summary_path", "")],
                ["csv_path", tuning_before_after.get("csv_path", "")],
                ["readme_path", tuning_before_after.get("readme_path", "")],
            ],
        )
    )
    lines.extend(["", "### Before/After Remaining Prompts"])
    before_after_prompt_rows = sim_camera_tuning_before_after_prompt_rows(tuning_before_after)
    lines.extend(
        table(
            ["Sweep", "Candidate", "Description", "MAD", "RMSE", "MAD Delta", "RMSE Delta"],
            before_after_prompt_rows,
        )
        if before_after_prompt_rows
        else ["_No before/after remaining tuning prompts were available._"]
    )
    lines.extend(["", "### Before/After Artifacts"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Sweep",
                "Profile",
                "Baseline Width",
                "Current Width",
                "Marker Time",
                "Baseline Candidates",
                "Current Candidates",
                "Current-vs-Baseline MAD",
                "Current-vs-Baseline RMSE",
                "Best-vs-Baseline MAD",
                "Best-vs-Baseline RMSE",
                "Prompts",
                "Copied Into Repo",
                "Missing Real Depth",
                "Missing Pick/Place Video",
                "Artifact Status",
            ],
            [
                sim_camera_tuning_before_after_artifact_row(row)
                for row in tuning_before_after_artifacts
            ],
        )
        if tuning_before_after_artifacts
        else ["_No SimCamera tuning before/after artifacts indexed._"]
    )

    lines.extend(["", "## Reference Capture Manifest"])
    reference_capture_manifest = reference_capture_manifest_signal(index, suite)
    reference_capture_manifest_artifacts = grouped.get("reference_capture_manifest", [])
    lines.append(
        "This hardware-free child checks a local-only operator manifest for real "
        "depth-reference captures, pick/place videos, provenance/review fields, and "
        "referenced sidecar path availability. It is an input-readiness gate only, not "
        "physical calibration truth."
    )
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", reference_capture_manifest.get("status", "")],
                [
                    "ready_for_calibration_grade_simcamera_tuning",
                    reference_capture_manifest.get("ready_for_calibration_grade_simcamera_tuning", ""),
                ],
                [
                    "depth_reference_capture_count",
                    reference_capture_manifest.get("depth_reference_capture_count", ""),
                ],
                [
                    "pick_place_video_capture_count",
                    reference_capture_manifest.get("pick_place_video_capture_count", ""),
                ],
                ["path_check_count", reference_capture_manifest.get("path_check_count", "")],
                ["media_path_check_count", reference_capture_manifest.get("media_path_check_count", "")],
                [
                    "sidecar_path_check_count",
                    reference_capture_manifest.get("sidecar_path_check_count", ""),
                ],
                ["missing_path_count", reference_capture_manifest.get("missing_path_count", "")],
                [
                    "media_assets_copied_into_repo",
                    reference_capture_manifest.get("media_assets_copied_into_repo", ""),
                ],
                ["diagnostics", compact_list(reference_capture_manifest.get("diagnostics"))],
                ["manifest_path", reference_capture_manifest.get("manifest_path", "")],
                ["summary_path", reference_capture_manifest.get("summary_path", "")],
                ["csv_path", reference_capture_manifest.get("csv_path", "")],
                ["readme_path", reference_capture_manifest.get("readme_path", "")],
            ],
        )
    )
    lines.append("")
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Ready",
                "Depth Captures",
                "Pick/Place Videos",
                "Path Checks",
                "Missing Paths",
                "Copied Into Repo",
                "Diagnostics",
                "Artifact Status",
            ],
            [
                reference_capture_manifest_artifact_row(row)
                for row in reference_capture_manifest_artifacts
            ],
        )
        if reference_capture_manifest_artifacts
        else ["_No reference capture manifest artifacts indexed._"]
    )

    lines.extend(["", "## Real Depth Capture Plan Artifact Index"])
    real_depth_plan_index = real_depth_capture_plan_artifact_index_signal(index, suite)
    real_depth_plan_artifacts = grouped.get("real_depth_capture_plan_artifact_index", [])
    lines.append(
        "This hardware-free child indexes the real-depth operator plan bridge smoke, "
        "planner JSON/Markdown outputs, and next operator actions. Ready evidence is "
        "input readiness only, not physical calibration truth."
    )
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["status", real_depth_plan_index.get("status", "")],
                ["source_mode", real_depth_plan_index.get("source_mode", "")],
                ["case_count", real_depth_plan_index.get("case_count", "")],
                ["ready_case_count", real_depth_plan_index.get("ready_case_count", "")],
                ["not_ready_case_count", real_depth_plan_index.get("not_ready_case_count", "")],
                ["evidence_statuses", compact_list(real_depth_plan_index.get("evidence_statuses"))],
                [
                    "depth_reference_capture_count",
                    real_depth_plan_index.get("depth_reference_capture_count", ""),
                ],
                [
                    "pick_place_video_capture_count",
                    real_depth_plan_index.get("pick_place_video_capture_count", ""),
                ],
                ["missing_path_count", real_depth_plan_index.get("missing_path_count", "")],
                ["no_copy_statuses", compact_list(real_depth_plan_index.get("no_copy_statuses"))],
                [
                    "next_operator_action_count",
                    real_depth_plan_index.get("next_operator_action_count", ""),
                ],
                [
                    "next_operator_action_ids",
                    compact_list(real_depth_plan_index.get("next_operator_action_ids")),
                ],
                ["bridge_smoke_status", real_depth_plan_index.get("bridge_smoke_status", "")],
                [
                    "bridge_smoke_summary_json",
                    real_depth_plan_index.get("bridge_smoke_summary_json", ""),
                ],
                [
                    "media_assets_copied_into_repo",
                    real_depth_plan_index.get("media_assets_copied_into_repo", ""),
                ],
                [
                    "media_assets_opened_or_decoded",
                    real_depth_plan_index.get("media_assets_opened_or_decoded", ""),
                ],
                [
                    "input_readiness_caveat",
                    compact_list(real_depth_plan_index.get("caveats")),
                ],
                ["summary_path", real_depth_plan_index.get("summary_path", "")],
                ["csv_path", real_depth_plan_index.get("csv_path", "")],
                ["readme_path", real_depth_plan_index.get("readme_path", "")],
            ],
        )
    )
    lines.extend(["", "### Operator Plan Cases"])
    plan_case_rows = real_depth_capture_plan_case_rows(real_depth_plan_index)
    lines.extend(
        linked_table(
            [
                "Case",
                "Evidence",
                "Status",
                "Ready",
                "Depth Captures",
                "Pick/Place Videos",
                "Missing Paths",
                "No-Copy",
                "Next Actions",
                "Planner JSON",
                "Planner Markdown",
            ],
            plan_case_rows,
        )
        if plan_case_rows
        else ["_No real-depth operator plan cases were available._"]
    )
    lines.extend(["", "### Operator Plan Artifacts"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Source Mode",
                "Case",
                "Evidence Status",
                "Ready",
                "Ready Cases",
                "Not-Ready Cases",
                "Depth Captures",
                "Pick/Place Videos",
                "Missing Paths",
                "No-Copy",
                "Next Actions",
                "Next Action IDs",
                "Copied Into Repo",
                "Opened Or Decoded",
                "Artifact Status",
            ],
            [real_depth_capture_plan_artifact_row(row) for row in real_depth_plan_artifacts],
        )
        if real_depth_plan_artifacts
        else ["_No real-depth operator plan artifacts indexed._"]
    )

    lines.extend(["", "## Reference Capture Checklist"])
    checklist = reference_capture_checklist_signal(index, suite)
    checklist_artifacts = grouped.get("reference_capture_checklist", [])
    if checklist:
        lines.extend(
            table(
                ["Field", "Value"],
                [
                    ["status", checklist.get("status", "")],
                    ["represented_media_count", checklist.get("represented_media_count", "")],
                    ["missing_requirement_count", checklist.get("missing_requirement_count", "")],
                    ["partial_requirement_count", checklist.get("partial_requirement_count", "")],
                    ["action_item_count", checklist.get("action_item_count", "")],
                    ["hardware_skipped", checklist.get("hardware_skipped", "")],
                    ["gui_skipped", checklist.get("gui_skipped", "")],
                    ["real_camera_skipped", checklist.get("real_camera_skipped", "")],
                    ["openai_skipped", checklist.get("openai_skipped", "")],
                ],
            )
        )
    else:
        lines.append("_No reference capture checklist metadata was available._")
    lines.append("")
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Checklist Status",
                "Represented Media",
                "Missing Requirements",
                "Action Items",
                "Real Camera Skipped",
                "Artifact Status",
            ],
            checklist_artifact_rows(checklist_artifacts),
        )
        if checklist_artifacts
        else ["_No checklist artifacts indexed._"]
    )
    requirement_rows = checklist_requirement_rows(checklist)
    if requirement_rows:
        lines.extend(["", "### Capture Requirement Status"])
        lines.extend(
            table(
                [
                    "Requirement",
                    "Status",
                    "Media Type",
                    "Represented/Partial By",
                    "Missing Evidence",
                    "Suggested Filename",
                    "Manifest Targets",
                    "Failure Mode",
                    "Sim Profiles",
                ],
                requirement_rows,
            )
        )

    lines.extend(["", "## Important Evidence"])
    visual_review = [
        row
        for row in grouped.get("visual_review", [])
        if row.get("label") != "visual_review:summary"
    ]
    lines.extend(["", "### Visual Review Artifacts"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Source Frames",
                "Frame Labels",
                "Dimensions",
                "Codec",
                "Duration Seconds",
                "Status",
            ],
            [visual_review_row(row) for row in visual_review],
        )
        if visual_review
        else ["_No visual-review artifacts indexed._"]
    )

    depth_scorecard_artifacts = [
        row
        for row in grouped.get("visual_review", [])
        if str(row.get("label") or "").startswith("visual_review:pick_place_depth_distance_scorecard")
    ]
    depth_scorecard = depth_distance_scorecard_signal(index, suite)
    lines.extend(["", "### Pick/Place Depth-Distance Scorecard"])
    lines.append(
        "This is the first-pass scorecard for depth/distance judgment. It combines SimCamera "
        "ground truth, the metadata-derived rendered-corner PnP baseline, residual severity, "
        "and either a `real_depth_comparable` sidecar residual summary or a "
        "`missing_real_depth_reference` checklist before the detailed tables below."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Frames",
                "Review Status",
                "At A Glance",
                "Baseline Quality",
                "Worst Mean Abs Depth Error mm",
                "Mean PnP Reproj px",
                "Mean Metadata-Corner px",
                "Not Comparable Rows",
                "Real Depth",
                "Real Depth Rows",
                "Mean Real-vs-Sim Proj px",
                "Mean Abs Real-vs-Sim Depth mm",
                "Missing Real Inputs",
                "Status",
            ],
            [depth_distance_scorecard_artifact_row(row) for row in depth_scorecard_artifacts],
        )
        if depth_scorecard_artifacts
        else ["_No pick/place depth-distance scorecard artifacts indexed._"]
    )
    scorecard_stage_rows = depth_distance_scorecard_stage_rows(depth_scorecard)
    lines.extend(
        table(
            [
                "Stage",
                "GT Cam-Piece mm",
                "Est Cam-Piece mm",
                "Abs Piece Error mm",
                "GT Cam-Board mm",
                "Est Cam-Board mm",
                "Abs Board Error mm",
                "PnP Reproj px",
                "PnP vs GT",
                "Status",
            ],
            scorecard_stage_rows,
        )
        if scorecard_stage_rows
        else ["_No per-stage depth-distance scorecard rows were available._"]
    )

    pick_place_depth_metrics = [
        row
        for row in grouped.get("visual_review", [])
        if str(row.get("label") or "").startswith("visual_review:pick_place_depth_distance_metrics")
    ]
    lines.extend(["", "### Pick/Place Depth/Distance Metrics"])
    lines.append(
        "These rows are simulator ground truth unless the source column says otherwise; "
        "the current gripper-to-piece value is a board-plane proxy and perceived depth is "
        "explicitly marked when not implemented."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Frames",
                "Example Cam-Piece mm",
                "Example Cam-Board mm",
                "Example Grip-Piece mm",
                "Grip Source",
                "Perceived Depth",
                "Status",
            ],
            [depth_distance_row(row) for row in pick_place_depth_metrics],
        )
        if pick_place_depth_metrics
        else ["_No pick/place depth-distance metric artifacts indexed._"]
    )

    perceived_depth_artifacts = [
        row
        for row in grouped.get("visual_review", [])
        if str(row.get("label") or "").startswith("visual_review:pick_place_perceived_depth_comparison")
    ]
    perceived_comparison = perceived_depth_comparison_signal(index, suite)
    lines.extend(["", "### Pick/Place Perceived Depth Comparison"])
    lines.append(
        "This compact table compares a metadata-derived rendered-board-corner PnP baseline "
        "against simulator ground truth. It is not an independent real-camera depth estimate."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Frames",
                "Estimator",
                "Estimator Status",
                "Example Est Cam-Piece mm",
                "Example GT Cam-Piece mm",
                "Example Cam-Piece Error mm",
                "Mean Abs Cam-Piece Error mm",
                "Status",
            ],
            [perceived_depth_artifact_row(row) for row in perceived_depth_artifacts],
        )
        if perceived_depth_artifacts
        else ["_No perceived-depth comparison artifacts indexed._"]
    )
    stage_rows = perceived_depth_stage_rows(perceived_comparison)
    lines.extend(
        table(
            [
                "Stage",
                "Estimator",
                "Source Status",
                "Est Cam-Piece mm",
                "GT Cam-Piece mm",
                "Cam-Piece Error mm",
                "Est Cam-Board mm",
                "GT Cam-Board mm",
                "Cam-Board Error mm",
                "Reproj Mean px",
                "Status",
            ],
            stage_rows,
        )
        if stage_rows
        else ["_No per-stage perceived-depth comparison rows were available._"]
    )

    metadata_native_artifacts = [
        row
        for row in grouped.get("visual_review", [])
        if str(row.get("label") or "").startswith("visual_review:pick_place_metadata_native_depth_view")
    ]
    metadata_native_view = metadata_native_depth_view_signal(index, suite)
    lines.extend(["", "### Metadata-Native Projection/Depth View"])
    lines.append(
        "Use this artifact as the simulator ground-truth, camera-model-aligned projection/depth "
        "view. It projects known board, piece, and target points through SimCamera metadata "
        "(`camera_matrix_px` plus `extrinsics.board_to_camera`) and does not use rendered "
        "overlay board corners as depth authority. Use the rendered-overlay PnP diagnostic "
        "below only to explain source mismatch and residuals."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Frames",
                "Rows",
                "Source Model",
                "Example Pixel XY",
                "Example Z mm",
                "Example Range mm",
                "Board Plane mm",
                "Status",
            ],
            [metadata_native_depth_artifact_row(row) for row in metadata_native_artifacts],
        )
        if metadata_native_artifacts
        else ["_No metadata-native projection/depth artifacts indexed._"]
    )
    metadata_stage_rows = metadata_native_depth_stage_rows(metadata_native_view)
    lines.extend(
        table(
            [
                "Stage",
                "Point",
                "Square",
                "Metadata Pixel XY",
                "Camera XYZ mm",
                "Z Depth mm",
                "Range mm",
                "Board Plane mm",
                "Source Model",
                "Status",
            ],
            metadata_stage_rows,
        )
        if metadata_stage_rows
        else ["_No metadata-native per-point rows were available._"]
    )

    real_projection_artifacts = grouped.get("real_projection_intake", [])
    real_projection_intake = real_projection_intake_signal(index, suite)
    lines.extend(["", "### Real Projection Intake"])
    lines.append(
        "This artifact links selected real reference media to the metadata-native SimCamera "
        "projection/depth view. It reports `real_depth_comparable` only when selected "
        "media has real_capture=true intrinsics, board pose/extrinsics or corner detections, "
        "and depth references; otherwise it reports `missing_real_depth_reference` with "
        "the exact missing inputs."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Real Refs",
                "Comparable",
                "Depth Comparable",
                "Sidecars Valid",
                "Sidecars Invalid",
                "Sidecars Missing",
                "Missing Inputs",
                "Sim Points",
                "Residuals",
                "Residual Rows",
                "Mean Proj px",
                "Mean Abs Depth mm",
                "Real Camera Skipped",
                "Artifact Status",
            ],
            [real_projection_intake_artifact_row(row) for row in real_projection_artifacts],
        )
        if real_projection_artifacts
        else ["_No real projection intake artifacts indexed._"]
    )
    intake_record_rows = real_projection_intake_record_rows(real_projection_intake)
    lines.extend(
        table(
            [
                "Media",
                "Status",
                "Intrinsics",
                "Extrinsics",
                "Board Pose",
                "Real Depth",
                "Sidecars Valid",
                "Sidecars Invalid",
                "Sim Points",
                "Comparable",
                "Residuals",
                "Proj Rows",
                "Corner Rows",
                "Depth Rows",
                "Missing Inputs",
                "Next Requirements",
            ],
            intake_record_rows,
        )
        if intake_record_rows
        else ["_No real projection intake rows were available._"]
    )

    pnp_residual_artifacts = [
        row
        for row in grouped.get("visual_review", [])
        if str(row.get("label") or "").startswith("visual_review:pick_place_pnp_residual_diagnostics")
    ]
    pnp_diagnostic = pnp_residual_diagnostic_signal(index, suite)
    lines.extend(["", "### Pick/Place PnP Residual Diagnostics"])
    lines.append(
        "This table diagnoses whether the rendered-board-corner PnP baseline is geometrically "
        "comparable to simulator metadata extrinsics. Metadata-projected corner residuals "
        "come from projecting 3D board corners through SimCamera intrinsics/extrinsics and "
        "comparing those pixels with the rendered board-corner overlay."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Frames",
                "Mean Metadata-Corner Residual px",
                "Mean PnP Reproj px",
                "Mean Abs Cam-Piece Error mm",
                "Mean Abs Cam-Board Error mm",
                "Not Comparable Rows",
                "Example Reason Labels",
                "Status",
            ],
            [pnp_residual_artifact_row(row) for row in pnp_residual_artifacts],
        )
        if pnp_residual_artifacts
        else ["_No PnP residual diagnostic artifacts indexed._"]
    )
    diagnostic_stage_rows = pnp_residual_stage_rows(pnp_diagnostic)
    lines.extend(
        table(
            [
                "Stage",
                "Metadata-Corner Residual px",
                "PnP Reproj px",
                "Camera Center Delta mm",
                "Cam-Piece Error mm",
                "Cam-Board Error mm",
                "PnP vs GT Comparability",
                "Reason Labels",
                "Status",
            ],
            diagnostic_stage_rows,
        )
        if diagnostic_stage_rows
        else ["_No per-stage PnP residual diagnostic rows were available._"]
    )

    pick_place_sequence = [
        row
        for row in grouped.get("visual_review", [])
        if str(row.get("label") or "").startswith("visual_review:pick_place_sequence")
    ]
    lines.extend(["", "### Pick/Place Visual Sequence"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Source Frames",
                "Frame Labels",
                "Dimensions",
                "Codec",
                "Duration Seconds",
                "Status",
            ],
            [visual_review_row(row) for row in pick_place_sequence],
        )
        if pick_place_sequence
        else ["_No pick/place visual sequence artifacts indexed._"]
    )

    comparison_images = [
        row for row in grouped.get("real_reference_comparison", []) if row.get("kind") == "image"
    ]
    lines.extend(["", "### Real-Reference Comparison Images"])
    lines.extend(
        linked_table(["Kind", "Label", "Path", "Status"], [evidence_row(row) for row in comparison_images])
        if comparison_images
        else ["_No image artifacts indexed._"]
    )

    ranked_candidate = grouped.get("ranked_candidate", [])
    lines.extend(["", "### Ranked Candidate Captures"])
    lines.extend(
        linked_table(
            ["Kind", "Label", "Path", "Status", "Candidate", "Rank"],
            [
                evidence_row(row) + [row.get("candidate_id", ""), row.get("rank", "")]
                for row in ranked_candidate
            ],
        )
        if ranked_candidate
        else ["_No ranked candidate artifacts indexed._"]
    )

    fixture = grouped.get("perception_fixture", [])
    lines.extend(["", "### Perception Fixture Artifacts"])
    lines.extend(
        linked_table(["Kind", "Label", "Path", "Status"], [evidence_row(row) for row in fixture])
        if fixture
        else ["_No perception fixture artifacts indexed._"]
    )

    pose_fixture = [
        row
        for row in grouped.get("sim_camera_pose_fixture", [])
        if row.get("label") != "sim_camera_pose_fixture:summary"
    ]
    lines.extend(["", "### SimCamera Pose Fixture"])
    lines.extend(
        linked_table(
            [
                "Case",
                "Kind",
                "Path",
                "View",
                "Target Square",
                "Piece Square",
                "Intrinsics",
                "Distortion",
                "Board->Camera",
                "Frame Notes",
                "Status",
            ],
            [pose_fixture_row(row) for row in pose_fixture],
        )
        if pose_fixture
        else ["_No SimCamera pose fixture artifacts indexed._"]
    )

    so101_model_source_inventory = grouped.get("so101_model_source_inventory", [])
    lines.extend(["", "### SO-101 Model Source Inventory"])
    lines.append(
        "This hardware-free child scans repo-local model-source roots before the model "
        "contract checker, records candidate/provenance/authority counts, and keeps "
        "`missing_authoritative_model` as a successful diagnostic when no reviewed "
        "authoritative source exists."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Candidates",
                "Likely",
                "Direct Contract",
                "Authoritative",
                "Authority Selection",
                "Selected Authority Path",
                "Selected Authority SHA-256",
                "Source Mode",
                "Configured Roots",
                "Authority Inputs",
                "Authority Review",
                "Review Ready",
                "Scope Ready",
                "Missing Scopes",
                "Authority Gate",
                "Authority Blockers",
                "Recommended Contract Path",
                "Action Count",
                "Next Actions",
                "Review Packet",
                "Packet Authority",
                "Packet Items",
                "Packet Actions",
                "Observed Evidence Is Authority",
                "Fixture Evidence Not Physical Truth",
                "Physical Authority Ready",
                "Artifact Status",
            ],
            [so101_model_source_inventory_row(row) for row in so101_model_source_inventory],
        )
        if so101_model_source_inventory
        else ["_No SO-101 model source inventory artifacts indexed._"]
    )

    so101_reviewed_model_authority_gate = grouped.get(
        "so101_reviewed_model_authority_gate",
        [],
    )
    lines.extend(["", "### SO-101 Reviewed Model Authority Gate"])
    lines.append(
        "This aggregate gate summarizes the highest-priority SO-101 blocker before "
        "serious model-backed IK or training: source authority, physical bundle "
        "authority, and physical-reviewed MuJoCo motion must all be true. Development "
        "fixture evidence remains useful automation coverage only."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Review Status",
                "Ready",
                "Source Authority",
                "Source Gate",
                "Physical Authority",
                "Physical Gate",
                "Source/Bundle Match",
                "Match Status",
                "Motion/Bundle Match",
                "Motion Match Status",
                "Reviewed Motion",
                "Motion Reported",
                "Motion Status Ready",
                "Motion Child Ready",
                "MuJoCo Bundle",
                "Motion Authority",
                "Fixture Caveat",
                "Blocker Count",
                "Blockers",
                "Blocker Packet",
                "Packet Authority",
                "Packet Items",
                "Action Required",
                "Blocked Prior",
                "Packet Next Actions",
                "Artifact Status",
            ],
            [
                so101_reviewed_model_authority_gate_row(row)
                for row in so101_reviewed_model_authority_gate
            ],
        )
        if so101_reviewed_model_authority_gate
        else ["_No SO-101 reviewed model authority gate artifacts indexed._"]
    )

    so101_model_bundle_probe = grouped.get("so101_model_bundle_probe", [])
    lines.extend(["", "### SO-101 Model Bundle Probe"])
    lines.append(
        "This hardware-free child turns a selected candidate model path, when one exists, "
        "into a candidate bundle manifest draft and nested contract/manifest diagnostics. "
        "With no selected model it still emits a template artifact. Probe output is "
        "review scaffolding only and does not create source authority, physical model "
        "authority, or physical reviewed MuJoCo motion evidence."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Authority",
                "Selected Model",
                "Model Request",
                "Contract",
                "Asset Preflight",
                "Mesh Refs",
                "Missing Mesh",
                "Unresolved Mesh",
                "Source Hints",
                "Joint Limits",
                "Limits Complete",
                "Mesh Review",
                "Manifest Status",
                "Ready",
                "Review Packet",
                "Review Packet Authority",
                "Review Items",
                "Review Item IDs",
                "Action Count",
                "Next Actions",
                "Artifact Status",
            ],
            [so101_model_bundle_probe_row(row) for row in so101_model_bundle_probe],
        )
        if so101_model_bundle_probe
        else ["_No SO-101 model bundle probe artifacts indexed._"]
    )

    so101_model_bundle_manifest = grouped.get("so101_model_bundle_manifest", [])
    lines.extend(["", "### SO-101 Model Bundle Manifest"])
    lines.append(
        "This hardware-free child records one reviewed SO-101 model bundle manifest, "
        "including model path, asset roots, joint-limit authority, mesh evidence, target frame, "
        "TCP/gripper-tip offset, base-to-board alignment, child contract diagnostics, and nested asset-preflight "
        "diagnostics. Manifest fields remain diagnostic-only unless "
        "`ready_for_model_backed_ik` is true; fixture-only readiness stays labeled separately "
        "from physical SO-101 model authority and explicit suite CLI model inputs take precedence."
        " The manifest review packet is indexed as operator intake only and remains "
        "`review_packet_not_authority`."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Request",
                "Ready",
                "Authority",
                "Authority Gate",
                "Physical Authority",
                "Authority Blockers",
                "Fixture Ready",
                "Synthetic Fields",
                "Review Packet",
                "Review Packet Authority",
                "Review Items",
                "Review Actions",
                "Action Count",
                "Next Actions",
                "Model Path",
                "Asset Roots",
                "Joint Limits",
                "Mesh Assets",
                "Mesh Refs",
                "Target Frame",
                "TCP Field",
                "Alignment",
                "Contract",
                "Asset Preflight",
                "Diagnostic Only",
                "Reason",
                "Artifact Status",
            ],
            [so101_model_bundle_manifest_row(row) for row in so101_model_bundle_manifest],
        )
        if so101_model_bundle_manifest
        else ["_No SO-101 model bundle manifest artifacts indexed._"]
    )

    so101_model_contract = grouped.get("so101_model_contract", [])
    lines.extend(["", "### SO-101 Model Contract"])
    lines.append(
        "This hardware-free child records whether the optional model requested through "
        "`--ik-model-path` is available, whether the current RobotKinematics path can use "
        "it directly, and which joint/frame/TCP alignment inputs still gate trustworthy "
        "model-backed IK residuals."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Model Request",
                "Model Path",
                "RobotKinematics",
                "Directly Usable",
                "Target Frame",
                "Missing Alignment Inputs",
                "Artifact Status",
            ],
            [so101_model_contract_row(row) for row in so101_model_contract],
        )
        if so101_model_contract
        else ["_No SO-101 model contract artifacts indexed._"]
    )

    so101_model_asset_preflight = grouped.get("so101_model_asset_preflight", [])
    lines.extend(["", "### SO-101 Model Asset Preflight"])
    lines.append(
        "This table surfaces the model contract checker's nested asset preflight before "
        "IK reachability evidence. Missing or unresolved mesh references remain "
        "non-failing diagnostics, but they are visible as follow-up counts and linked artifacts."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Model Request",
                "Mesh Refs",
                "Present",
                "Missing",
                "Unresolved",
                "Artifact Status",
            ],
            [so101_model_asset_preflight_row(row) for row in so101_model_asset_preflight],
        )
        if so101_model_asset_preflight
        else ["_No SO-101 model asset-preflight artifacts indexed._"]
    )

    ik_reachability = grouped.get("ik_reachability", [])
    lines.extend(["", "### IK Reachability Drill"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Row Count",
                "Model Diagnostic",
                "Solver",
                "Status",
            ],
            [
                [
                    row.get("kind", ""),
                    row.get("label", ""),
                    markdown_link(display_path(row), link_path(row)),
                    (row.get("metrics") or {}).get("row_count", ""),
                    (row.get("metrics") or {}).get("model_diagnostic_status", ""),
                    (row.get("metrics") or {}).get("model_solver_status", ""),
                    "ok" if row.get("exists") else "missing",
                ]
                for row in ik_reachability
            ],
        )
        if ik_reachability
        else ["_No IK reachability artifacts indexed._"]
    )

    so101_training_readiness_gate = grouped.get("so101_training_readiness_gate", [])
    lines.extend(["", "### SO-101 Training Readiness Gate"])
    lines.append(
        "This gate is the hard boundary before serious policy training. It stays blocked "
        "until reviewed model authority is ready, board-source pick/place has been repeated "
        "with reviewed model-backed IK, and rollout evidence is no longer development-scaffold-only."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Ready",
                "Authority Ready",
                "Authority Status",
                "Reviewed Motion",
                "Reviewed Board Pick",
                "Board Pick Status",
                "Board Pick Authority",
                "Board Authority Ready",
                "Board Detail Ready",
                "Board Pick IK Ready",
                "Seeded Pose",
                "Rollout Ready",
                "Rollout Authority Ready",
                "Rollout Authority Status",
                "Rollout Authority",
                "Rollout Use",
                "Fixture Caveat",
                "Priority Order",
                "Next Gate",
                "Next Actions",
                "Development Only Gates",
                "Blocked Prior Gates",
                "Blocker Count",
                "Blockers",
                "Artifact Status",
            ],
            [
                so101_training_readiness_gate_row(row)
                for row in so101_training_readiness_gate
            ],
        )
        if so101_training_readiness_gate
        else ["_No SO-101 training readiness gate artifacts indexed._"]
    )

    so101_mujoco_rows = []
    for category in (
        "so101_reviewed_mujoco_bundle",
        "so101_mujoco_scene",
        "so101_chess_env",
        "so101_env_resets",
        "so101_mujoco_contact_probe",
        "so101_mujoco_grasp_probe",
        "so101_mujoco_board_pick_probe",
        "so101_training_rollouts",
    ):
        so101_mujoco_rows.extend(grouped.get(category, []))
    lines.extend(["", "### SO-101 MuJoCo Development Gates"])
    lines.append(
        "These hardware-free children prioritize the MuJoCo/Gymnasium training path: "
        "reviewed bundle handoff into MuJoCo, development scene load, env reset/step, "
        "freejoint/contact checks, gripper-contact lift/place verification, board-source pick/place probing, and scripted rollout collection. The development scene "
        "still uses a generated scaffold; serious training remains blocked until the "
        "reviewed bundle gate reports MuJoCo motion checked and seeded board-source pickup is replaced with reviewed model-backed IK."
    )
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Status",
                "Authority",
                "Physical Authority",
                "Fixture Ready",
                "Ready",
                "Reviewed Motion",
                "Motion Authority",
                "Physical Motion",
                "Fixture Motion",
                "Gymnasium",
                "MuJoCo",
                "Resets",
                "Board Contact",
                "Gripper Contact",
                "Lift/Place Physics",
                "Source Pick",
                "Board Pick/Place",
                "Seeded Pose",
                "Final Board",
                "Target XY Error",
                "Episodes",
                "Transitions",
                "Next Required",
                "Artifact Status",
            ],
            [so101_mujoco_smoke_row(row) for row in so101_mujoco_rows],
        )
        if so101_mujoco_rows
        else ["_No SO-101 MuJoCo development gate artifacts indexed._"]
    )

    pov = [
        row
        for row in grouped.get("gripper_camera_pov", [])
        if row.get("label") != "gripper_camera_pov:summary"
    ]
    lines.extend(["", "### Gripper-Camera POV Review"])
    lines.extend(
        linked_table(
            [
                "State",
                "Kind",
                "Path",
                "Target Square",
                "Target Center",
                "Visible Fraction",
                "Occlusion Fraction",
                "Min Clearance Px",
                "Gripper %",
                "Opening Px",
                "Metadata Contract",
                "Status",
            ],
            [gripper_camera_pov_row(row) for row in pov],
        )
        if pov
        else ["_No gripper-camera POV artifacts indexed._"]
    )

    app_entrypoint = grouped.get("app_entrypoint", [])
    lines.extend(["", "### App Entrypoint Metadata"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Profile",
                "Metadata Contract",
                "Checks",
                "Failed Checks",
                "Hardware Skipped",
                "GUI Skipped",
                "OpenAI Skipped",
                "Status",
            ],
            [app_entrypoint_row(row) for row in app_entrypoint],
        )
        if app_entrypoint
        else ["_No app-entrypoint artifacts indexed._"]
    )

    releases = [
        row
        for row in grouped.get("pick_place_scenario", [])
        if isinstance(row.get("scenario_id"), str) and row.get("kind") == "image"
    ]
    lines.extend(["", "### Pick/Place Release Frames"])
    lines.extend(
        linked_table(
            [
                "Scenario",
                "Release Frame",
                "Visible Fraction",
                "Occlusion Fraction",
                "Min Clearance Px",
                "Status",
            ],
            [release_row(row) for row in releases],
        )
        if releases
        else ["_No pick/place release frame artifacts indexed._"]
    )

    negative = grouped.get("negative_check", [])
    lines.extend(["", "### Negative Check"])
    lines.append(f"Status: {markdown_code(negative_status(index, suite))}")
    if negative:
        lines.extend(linked_table(["Kind", "Label", "Path", "Status"], [evidence_row(row) for row in negative]))

    logs = grouped.get("logs", [])
    lines.extend(["", "### Child Logs"])
    child_rows = child_log_rows(logs)
    lines.extend(
        linked_table(["Label", "Path", "Child OK", "Return Code", "Status"], child_rows)
        if child_rows
        else ["_No child stdout/stderr logs indexed._"]
    )

    lines.extend(["", "## Compact Artifact List"])
    for category in sorted(grouped, key=lambda key: (CATEGORY_ORDER.get(key, 99), key)):
        append_artifact_group(lines, category, grouped[category])

    lines.extend(
        [
            "## Notes",
            "",
            "- This report is a deterministic Markdown view of existing JSON artifacts only.",
            "- The reference media inventory records repo-local or explicit-root candidates and visibility gaps without copying media assets into the artifact bundle.",
            "- Visual review contact sheets are generated PNGs from existing suite frames and are the stable first-pass visual evidence.",
            "- The pick/place visual sequence is simulator-only evidence for approach, grasp/contact, lift/transfer, place/release, and retreat review.",
            "- The SO-101 model-source inventory is a hardware-free provenance preflight; `missing_authoritative_model` is a successful explicit diagnostic, and `--ik-model-path` is not automatically treated as authoritative.",
            "- The SO-101 model bundle manifest checker is hardware-free evidence for one reviewed bundle; it forwards model path and asset roots only when `ready_for_model_backed_ik` is true and explicit IK CLI inputs do not take precedence.",
            "- The SO-101 model contract checker is a hardware-free preflight for model availability, direct RobotKinematics usability, and joint/frame/TCP alignment inputs.",
            "- The IK reachability drill is a hardware-free feasibility gate; `model_unavailable_fallback_complete` remains a deliberate non-failing status until a repo-local SO-101 model is wired in.",
            "- The SO-101 MuJoCo development gates exercise the Gymnasium/MuJoCo path with a generated scaffold; gripper-contact fixture lift/place and seeded board-source pick/place evidence are separate from reviewed physical model truth, and reviewed model authority, TCP/gripper offset, base-to-board alignment, and reviewed model-backed IK remain required before serious policy training.",
            "- The SimCamera profile sweep is deterministic synthetic review evidence; its full-frame image deltas are coarse prompts, not physical calibration truth.",
            "- The SimCamera tuning before/after section compares the documented 72px baseline against the current canonical profile and keeps missing real depth and pick/place video gaps open.",
            "- The reference capture manifest section records local input readiness for real depth-reference and pick/place-video captures; readiness is not physical calibration truth.",
            "- The real depth capture plan artifact index is hardware-free operator-planning evidence; ready cases are input readiness only and do not claim physical calibration truth.",
            "- The metadata-native projection/depth view is the simulator camera-model-aligned ground-truth artifact; rendered-overlay PnP diagnostics are source-mismatch evidence, not depth authority.",
            "- SimCamera pose fixture intrinsics/extrinsics are simulator reference metadata, not physical calibration truth.",
            "- Gripper-camera POV visibility and clearance values are synthetic metadata evidence, not real-camera segmentation or physical contact proof.",
            "- It does not rerun child smokes, open GUI calibration flows, call OpenAI, or touch SO-101 hardware.",
            "",
        ]
    )
    return "\n".join(lines)


def default_output_path(index: dict[str, Any], artifact_index_path: Path) -> Path:
    output_dir = index.get("output_dir")
    if isinstance(output_dir, str) and output_dir:
        return Path(output_dir).expanduser().resolve() / DEFAULT_REPORT_NAME
    return artifact_index_path.parent / DEFAULT_REPORT_NAME


def main() -> int:
    args = parse_args()
    try:
        index, suite, artifact_index_path = load_inputs(args.input_json)
        artifact_index_path = artifact_index_path.expanduser().resolve()
        validate_index(index, artifact_index_path)
        output_md = (
            args.output_md.expanduser().resolve()
            if args.output_md
            else default_output_path(index, artifact_index_path)
        )
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_report(index, suite, artifact_index_path))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(str(output_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
