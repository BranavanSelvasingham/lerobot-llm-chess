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
    "real_reference_media": 0,
    "reference_capture_checklist": 1,
    "visual_review": 2,
    "real_reference_comparison": 3,
    "real_projection_intake": 4,
    "ranked_candidate": 5,
    "perception_fixture": 6,
    "sim_camera_pose_fixture": 7,
    "so101_model_source_inventory": 8,
    "so101_model_contract": 9,
    "ik_reachability": 10,
    "gripper_camera_pov": 11,
    "app_entrypoint": 12,
    "pick_place_scenario": 13,
    "negative_check": 14,
    "logs": 15,
}
CATEGORY_LABELS = {
    "real_reference_media": "Real Reference Media",
    "reference_capture_checklist": "Reference Capture Checklist",
    "visual_review": "Visual Review Artifacts",
    "real_reference_comparison": "Real Reference Comparisons",
    "real_projection_intake": "Real Projection Intake",
    "ranked_candidate": "Ranked Candidate Captures",
    "perception_fixture": "Perception Fixture Evidence",
    "sim_camera_pose_fixture": "SimCamera Pose Fixture",
    "so101_model_source_inventory": "SO-101 Model Source Inventory",
    "so101_model_contract": "SO-101 Model Contract",
    "ik_reachability": "IK Reachability Drill",
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
    inventory = suite.get("inventory")
    inventory = inventory if isinstance(inventory, dict) else {}
    gaps = inventory.get("visibility_gaps")
    return [gap for gap in gaps if isinstance(gap, dict)] if isinstance(gaps, list) else []


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
        metrics.get("source_scan_mode", ""),
        source_root_summary(metrics),
        source_authority_summary(metrics),
        metrics.get("recommended_contract_check_path", ""),
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

    lines.extend(["", "## Real Reference Media Gap"])
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
        lines.append("")
        lines.extend(table(["Gap", "Status", "Note"], gap_rows(gaps)))
    else:
        lines.append("")
        lines.append("_No inventory visibility gaps were available from the suite summary._")

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
                "Source Mode",
                "Configured Roots",
                "Authority Inputs",
                "Recommended Contract Path",
                "Artifact Status",
            ],
            [so101_model_source_inventory_row(row) for row in so101_model_source_inventory],
        )
        if so101_model_source_inventory
        else ["_No SO-101 model source inventory artifacts indexed._"]
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
            "- Visual review contact sheets are generated PNGs from existing suite frames and are the stable first-pass visual evidence.",
            "- The pick/place visual sequence is simulator-only evidence for approach, grasp/contact, lift/transfer, place/release, and retreat review.",
            "- The SO-101 model-source inventory is a hardware-free provenance preflight; `missing_authoritative_model` is a successful explicit diagnostic, and `--ik-model-path` is not automatically treated as authoritative.",
            "- The SO-101 model contract checker is a hardware-free preflight for model availability, direct RobotKinematics usability, and joint/frame/TCP alignment inputs.",
            "- The IK reachability drill is a hardware-free feasibility gate; `model_unavailable_fallback_complete` remains a deliberate non-failing status until a repo-local SO-101 model is wired in.",
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
