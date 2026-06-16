#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "lerobot.sim.calibration_artifact_index.v1"
CATEGORY_ORDER = {
    "evidence_bundle": 0,
    "reference_media_inventory": 0,
    "real_reference_media": 1,
    "reference_media_comparison": 2,
    "reference_capture_checklist": 2,
    "visual_review": 3,
    "real_reference_comparison": 4,
    "real_projection_intake": 5,
    "ranked_candidate": 6,
    "perception_fixture": 7,
    "sim_camera_pose_fixture": 8,
    "so101_model_source_inventory": 9,
    "so101_model_bundle_manifest": 10,
    "so101_model_contract": 11,
    "so101_model_asset_preflight": 12,
    "ik_reachability": 13,
    "gripper_camera_pov": 14,
    "app_entrypoint": 15,
    "pick_place_scenario": 16,
    "negative_check": 17,
    "logs": 18,
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a compact artifact index from a generated simulator calibration "
            "regression suite summary without rerunning child smokes."
        )
    )
    parser.add_argument("suite_summary", type=Path)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Artifact index path. Defaults to artifact_index.json beside the suite summary.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


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


def path_kind(path: Path) -> str:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return "image"
    if path.suffix.lower() in VIDEO_SUFFIXES:
        return "video"
    if path.suffix.lower() == ".json":
        return "json"
    if path.suffix.lower() == ".csv":
        return "csv"
    if path.suffix.lower() in {".txt", ".log"}:
        return "log"
    if path.is_dir():
        return "directory"
    return "file"


def output_relative(path: Path, output_dir: Path) -> str | None:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return None


def repo_relative(path: Path, repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return None


def resolve_path(value: str, *, suite_summary_path: Path, output_dir: Path, repo_root: Path | None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    output_candidate = (output_dir / path).resolve()
    if output_candidate.exists():
        return output_candidate

    if repo_root is not None:
        repo_candidate = (repo_root / path).resolve()
        if repo_candidate.exists():
            return repo_candidate

    return (suite_summary_path.parent / path).resolve()


def artifact_entry(
    *,
    category: str,
    label: str,
    path_value: str,
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
    source: str,
    metrics: dict[str, Any] | None = None,
    scenario_id: str | None = None,
    rank: int | None = None,
    candidate_id: str | None = None,
    reference_media: str | None = None,
) -> dict[str, Any]:
    path = resolve_path(path_value, suite_summary_path=suite_summary_path, output_dir=output_dir, repo_root=repo_root)
    row: dict[str, Any] = {
        "category": category,
        "label": label,
        "kind": path_kind(path),
        "path": str(path),
        "relative_path": output_relative(path, output_dir),
        "repo_relative_path": repo_relative(path, repo_root),
        "exists": path.exists(),
        "source": source,
    }
    if metrics:
        row["metrics"] = metrics
    if scenario_id is not None:
        row["scenario_id"] = scenario_id
    if rank is not None:
        row["rank"] = rank
    if candidate_id is not None:
        row["candidate_id"] = candidate_id
    if reference_media is not None:
        row["reference_media"] = reference_media
    return row


def add_path(
    artifacts: list[dict[str, Any]],
    *,
    category: str,
    label: str,
    value: Any,
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
    source: str,
    metrics: dict[str, Any] | None = None,
    scenario_id: str | None = None,
    rank: int | None = None,
    candidate_id: str | None = None,
    reference_media: str | None = None,
) -> None:
    if isinstance(value, str) and value:
        artifacts.append(
            artifact_entry(
                category=category,
                label=label,
                path_value=value,
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=source,
                metrics=metrics,
                scenario_id=scenario_id,
                rank=rank,
                candidate_id=candidate_id,
                reference_media=reference_media,
            )
        )


def load_optional_json(path_value: Any, *, suite_summary_path: Path, output_dir: Path, repo_root: Path | None) -> dict[str, Any] | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = resolve_path(path_value, suite_summary_path=suite_summary_path, output_dir=output_dir, repo_root=repo_root)
    if not path.is_file():
        return None
    try:
        return read_json_object(path, label="referenced summary")
    except ValueError:
        return None


def collect_real_reference_media(
    *,
    suite: dict[str, Any],
    comparison_set: dict[str, Any] | None,
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> list[dict[str, Any]]:
    selected = comparison_set.get("selected_media") if comparison_set else None
    selected_rows = selected if isinstance(selected, list) else []
    if not selected_rows:
        inventory = suite.get("inventory") if isinstance(suite.get("inventory"), dict) else {}
        recommended = inventory.get("next_recommended_reference_fixture_inputs")
        selected_rows = [{"relative_path": value} for value in recommended if isinstance(value, str)] if isinstance(recommended, list) else []

    rows: list[dict[str, Any]] = []
    for record in selected_rows:
        if not isinstance(record, dict):
            continue
        relative_path = record.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        declared_metadata = record.get("declared_metadata")
        declared_metadata = declared_metadata if isinstance(declared_metadata, dict) else {}
        manifest_validation = record.get("manifest_validation")
        manifest_validation = manifest_validation if isinstance(manifest_validation, dict) else {}
        manifest_metrics = {
            "manifest_declared": manifest_validation.get("declared"),
            "manifest_validation_status": manifest_validation.get("status"),
            "capture_id": declared_metadata.get("capture_id"),
            "declared_target_categories": declared_metadata.get("declared_target_categories"),
            "failure_mode": declared_metadata.get("failure_mode"),
            "sim_profiles": declared_metadata.get("sim_profiles"),
        }
        add_path(
            artifacts,
            category="real_reference_media",
            label=f"real_reference:{relative_path}",
            value=relative_path,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="comparison_set.selected_media",
            metrics=manifest_metrics,
            reference_media=relative_path,
        )
        rows.append(
            {
                "relative_path": relative_path,
                "media_type": record.get("media_type"),
                "dimensions": record.get("dimensions"),
                "selection_reasons": record.get("selection_reasons"),
                "currently_wired_into_simulator_tooling": record.get("currently_wired_into_simulator_tooling"),
                "manifest_validation": manifest_validation,
                "declared_metadata": declared_metadata or None,
                "capture_id": declared_metadata.get("capture_id"),
                "declared_target_categories": declared_metadata.get("declared_target_categories"),
                "failure_mode": declared_metadata.get("failure_mode"),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("relative_path") or ""))


def comparison_set_metrics(comparison_set: dict[str, Any] | None) -> dict[str, Any]:
    comparison_set = comparison_set if isinstance(comparison_set, dict) else {}
    diagnostics = comparison_set.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    contact_sheet = comparison_set.get("contact_sheet")
    contact_sheet = contact_sheet if isinstance(contact_sheet, dict) else {}
    return {
        "status": comparison_set.get("status"),
        "ok": comparison_set.get("ok"),
        "selected_candidate_count": comparison_set.get("selected_candidate_count"),
        "selected_media_count": comparison_set.get("selected_media_count"),
        "visual_comparison_count": comparison_set.get("visual_comparison_count"),
        "failed_comparison_count": comparison_set.get("failed_comparison_count"),
        "skipped_media_count": comparison_set.get("skipped_media_count"),
        "contact_sheet_status": comparison_set.get("contact_sheet_status")
        or contact_sheet.get("status"),
        "contact_sheet_produced": comparison_set.get("contact_sheet_produced")
        if comparison_set.get("contact_sheet_produced") is not None
        else contact_sheet.get("produced"),
        "contact_sheet_path": comparison_set.get("contact_sheet_path") or contact_sheet.get("path"),
        "media_assets_copied_into_repo": comparison_set.get(
            "media_assets_copied_into_repo",
            diagnostics.get("media_assets_copied_into_repo"),
        ),
        "external_selected_count": comparison_set.get(
            "external_selected_count",
            diagnostics.get("external_selected_count"),
        ),
        "missing_depth_reference": comparison_set.get(
            "missing_depth_reference",
            diagnostics.get("missing_depth_reference"),
        ),
        "missing_pick_place_video": comparison_set.get(
            "missing_pick_place_video",
            diagnostics.get("missing_pick_place_video"),
        ),
        "no_videos": comparison_set.get("no_videos", diagnostics.get("no_videos")),
        "videos_present": comparison_set.get("videos_present", diagnostics.get("videos_present")),
        "reference_gaps": comparison_set.get("reference_gaps", diagnostics.get("reference_gaps")),
        "render_dependencies": comparison_set.get(
            "render_dependencies",
            diagnostics.get("render_dependencies"),
        ),
    }


def collect_reference_media_comparison_artifacts(
    *,
    suite: dict[str, Any],
    comparison_set_summary: dict[str, Any] | None,
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    suite_comparison = (
        suite.get("comparison_set") if isinstance(suite.get("comparison_set"), dict) else {}
    )
    comparison_set = (
        comparison_set_summary
        if isinstance(comparison_set_summary, dict) and comparison_set_summary
        else suite_comparison
    )
    artifact_paths = comparison_set.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    if not artifact_paths and isinstance(comparison_set.get("artifacts"), dict):
        artifact_paths = comparison_set["artifacts"]
    metrics = comparison_set_metrics(comparison_set)
    paths = {
        "summary_json": comparison_set.get("summary_path")
        or comparison_set.get("comparison_set_summary_path")
        or artifact_paths.get("summary_json"),
        "csv_rows": comparison_set.get("csv_path") or artifact_paths.get("csv_rows"),
        "readme_md": comparison_set.get("readme_path") or artifact_paths.get("readme_md"),
        "contact_sheet_png": (
            artifact_paths.get("contact_sheet_png")
            if metrics.get("contact_sheet_produced") is True
            else None
        ),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("csv_rows", "rows"),
        ("readme_md", "readme"),
        ("contact_sheet_png", "contact_sheet"),
    ):
        add_path(
            artifacts,
            category="reference_media_comparison",
            label=f"reference_media_comparison:{label_suffix}",
            value=paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"comparison_set.artifact_paths.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": paths.get("summary_json"),
        "csv_path": paths.get("csv_rows"),
        "readme_path": paths.get("readme_md"),
        "contact_sheet_path": metrics.get("contact_sheet_path") or paths.get("contact_sheet_png"),
        "artifact_paths": paths,
        "diagnostics": comparison_set.get("diagnostics"),
    }


def reference_media_inventory_from_suite(suite: dict[str, Any]) -> dict[str, Any]:
    inventory = suite.get("reference_media_inventory")
    if isinstance(inventory, dict) and inventory:
        return inventory
    inventory = suite.get("inventory")
    return inventory if isinstance(inventory, dict) else {}


def reference_media_inventory_metrics(inventory: dict[str, Any]) -> dict[str, Any]:
    summary = inventory.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    current = inventory.get("current_gripper_reference")
    current = current if isinstance(current, dict) else {}
    return {
        "status": inventory.get("status") or summary.get("status"),
        "ok": inventory.get("ok"),
        "candidate_count": inventory.get("candidate_count", summary.get("candidate_count")),
        "image_count": inventory.get("image_count", summary.get("image_count")),
        "video_count": inventory.get("video_count", summary.get("video_count")),
        "calibration_data_count": inventory.get(
            "calibration_data_count",
            summary.get("calibration_data_count"),
        ),
        "currently_wired_media_count": inventory.get(
            "currently_wired_media_count",
            summary.get("currently_wired_media_count"),
        ),
        "current_gripper_reference_detected": current.get(
            "detected",
            summary.get("active_current_gripper_reference_detected"),
        ),
        "current_gripper_reference_path": current.get(
            "path",
            summary.get("active_current_gripper_reference_path"),
        ),
        "reference_gaps": inventory.get("reference_gaps") or summary.get("reference_gaps"),
        "scan_mode": (
            inventory.get("source_configuration", {}).get("scan_mode")
            if isinstance(inventory.get("source_configuration"), dict)
            else None
        ),
    }


def collect_reference_media_inventory_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    inventory = reference_media_inventory_from_suite(suite)
    artifact_paths = inventory.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    metrics = reference_media_inventory_metrics(inventory)
    paths = {
        "summary_json": inventory.get("summary_path") or artifact_paths.get("summary_json"),
        "csv": inventory.get("csv_path") or artifact_paths.get("csv"),
        "readme_md": inventory.get("readme_path") or artifact_paths.get("readme_md"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("csv", "csv"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="reference_media_inventory",
            label=f"reference_media_inventory:{label_suffix}",
            value=paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"reference_media_inventory.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": paths.get("summary_json"),
        "csv_path": paths.get("csv"),
        "readme_path": paths.get("readme_md"),
        "artifact_paths": paths,
        "visibility_gaps": inventory.get("visibility_gaps"),
        "scan": inventory.get("scan"),
        "source_configuration": inventory.get("source_configuration"),
    }


def collect_comparison_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> None:
    comparison_set = suite.get("comparison_set") if isinstance(suite.get("comparison_set"), dict) else {}
    for index, comparison in enumerate(comparison_set.get("artifacts") or [], start=1):
        if not isinstance(comparison, dict):
            continue
        reference_media = comparison.get("relative_path") if isinstance(comparison.get("relative_path"), str) else None
        add_path(
            artifacts,
            category="real_reference_comparison",
            label=f"comparison:{index:03d}:summary",
            value=comparison.get("summary_path"),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="comparison_set.artifacts.summary_path",
            reference_media=reference_media,
        )
        visuals = comparison.get("visual_artifact_paths")
        if isinstance(visuals, dict):
            for key, value in sorted(visuals.items()):
                add_path(
                    artifacts,
                    category="real_reference_comparison",
                    label=f"comparison:{index:03d}:{key}",
                    value=value,
                    suite_summary_path=suite_summary_path,
                    output_dir=output_dir,
                    repo_root=repo_root,
                    source="comparison_set.artifacts.visual_artifact_paths",
                    reference_media=reference_media,
                )


def collect_real_projection_intake_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    intake = suite.get("real_projection_intake")
    intake = intake if isinstance(intake, dict) else {}
    paths = intake.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    residual_artifacts = intake.get("residual_artifacts")
    residual_artifacts = residual_artifacts if isinstance(residual_artifacts, dict) else {}
    residual_aggregate = residual_artifacts.get("aggregate")
    residual_aggregate = residual_aggregate if isinstance(residual_aggregate, dict) else {}
    records = intake.get("records")
    records = records if isinstance(records, list) else []
    first_record = next((record for record in records if isinstance(record, dict)), {})
    metrics = {
        "status": intake.get("status"),
        "ok": intake.get("ok"),
        "real_reference_media_count": intake.get("real_reference_media_count"),
        "comparable_count": intake.get("comparable_count"),
        "projection_comparable_count": intake.get("projection_comparable_count"),
        "depth_comparable_count": intake.get("depth_comparable_count"),
        "sidecar_valid_count": intake.get("sidecar_valid_count"),
        "sidecar_invalid_count": intake.get("sidecar_invalid_count"),
        "sidecar_missing_count": intake.get("sidecar_missing_count"),
        "missing_input_count": intake.get("missing_input_count"),
        "missing_inputs": intake.get("missing_inputs"),
        "sim_expected_projected_point_count": intake.get("sim_expected_projected_point_count"),
        "sim_metadata_native_depth_view_path": intake.get("sim_metadata_native_depth_view_path"),
        "example_real_reference_media_path": first_record.get("real_reference_media_path"),
        "example_real_intrinsics_status": first_record.get("real_intrinsics_status"),
        "example_real_board_pose_status": first_record.get("real_board_pose_status"),
        "example_comparable": first_record.get("comparable"),
        "residual_status": residual_artifacts.get("status"),
        "residual_available": residual_artifacts.get("available"),
        "residual_projection_row_count": residual_aggregate.get("projection_row_count"),
        "residual_board_corner_row_count": residual_aggregate.get("board_corner_row_count"),
        "residual_depth_row_count": residual_aggregate.get("depth_row_count"),
        "mean_real_vs_sim_projection_residual_px": residual_aggregate.get(
            "mean_real_vs_sim_projection_residual_px"
        ),
        "mean_detected_corner_vs_sim_residual_px": residual_aggregate.get(
            "mean_detected_corner_vs_sim_residual_px"
        ),
        "mean_abs_real_vs_sim_depth_residual_mm": residual_aggregate.get(
            "mean_abs_real_vs_sim_depth_residual_mm"
        ),
        "real_camera_capture_skipped": intake.get("real_camera_capture_skipped"),
    }
    add_path(
        artifacts,
        category="real_projection_intake",
        label="real_projection_intake:summary",
        value=intake.get("summary_path") or paths.get("json"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="real_projection_intake.summary_path",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="real_projection_intake",
        label="real_projection_intake:csv",
        value=paths.get("csv"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="real_projection_intake.paths.csv",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="real_projection_intake",
        label="real_projection_intake:contact_sheet",
        value=paths.get("png"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="real_projection_intake.paths.png",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="real_projection_intake",
        label="real_projection_intake:residual_json",
        value=paths.get("residual_json"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="real_projection_intake.paths.residual_json",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="real_projection_intake",
        label="real_projection_intake:residual_csv",
        value=paths.get("residual_csv"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="real_projection_intake.paths.residual_csv",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="real_projection_intake",
        label="real_projection_intake:residual_overlay",
        value=paths.get("residual_png"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="real_projection_intake.paths.residual_png",
        metrics=metrics,
    )
    return {
        "status": intake.get("status"),
        "ok": intake.get("ok"),
        "summary_path": intake.get("summary_path") or paths.get("json"),
        "csv_path": paths.get("csv"),
        "contact_sheet_path": paths.get("png"),
        "residual_json_path": paths.get("residual_json"),
        "residual_csv_path": paths.get("residual_csv"),
        "residual_overlay_path": paths.get("residual_png"),
        "real_reference_media_count": intake.get("real_reference_media_count"),
        "comparable_count": intake.get("comparable_count"),
        "projection_comparable_count": intake.get("projection_comparable_count"),
        "depth_comparable_count": intake.get("depth_comparable_count"),
        "sidecar_valid_count": intake.get("sidecar_valid_count"),
        "sidecar_invalid_count": intake.get("sidecar_invalid_count"),
        "sidecar_missing_count": intake.get("sidecar_missing_count"),
        "missing_inputs": intake.get("missing_inputs"),
        "next_capture_requirements": intake.get("next_capture_requirements"),
        "sim_metadata_native_depth_view_path": intake.get("sim_metadata_native_depth_view_path"),
        "sim_expected_projected_point_count": intake.get("sim_expected_projected_point_count"),
        "residual_artifacts": residual_artifacts,
        "records": records,
        "real_camera_capture_skipped": intake.get("real_camera_capture_skipped"),
    }


def collect_reference_capture_checklist_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    checklist = suite.get("reference_capture_checklist")
    checklist = checklist if isinstance(checklist, dict) else {}
    checklist_summary = load_optional_json(
        checklist.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    checklist_summary = checklist_summary if isinstance(checklist_summary, dict) else {}
    counts = checklist_summary.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    media_summary = checklist_summary.get("media_summary")
    media_summary = media_summary if isinstance(media_summary, dict) else {}
    current_view = checklist_summary.get("current_view_representation")
    current_view = current_view if isinstance(current_view, dict) else {}
    metrics = {
        "status": checklist_summary.get("status", checklist.get("status")),
        "ok": checklist_summary.get("ok", checklist.get("ok")),
        "represented_media_count": media_summary.get(
            "represented_media_count",
            checklist.get("represented_media_count"),
        ),
        "video_count": media_summary.get("video_count", checklist.get("video_count")),
        "requirement_count": counts.get("requirement_count", checklist.get("requirement_count")),
        "missing_requirement_count": counts.get(
            "missing_requirement_count",
            checklist.get("missing_requirement_count"),
        ),
        "partial_requirement_count": counts.get(
            "partial_requirement_count",
            checklist.get("partial_requirement_count"),
        ),
        "action_item_count": counts.get("action_item_count", checklist.get("action_item_count")),
        "current_reference_detected": current_view.get("detected"),
        "current_reference_roles": current_view.get("represented_roles"),
        "hardware_skipped": checklist_summary.get("hardware_skipped", checklist.get("hardware_skipped")),
        "gui_skipped": checklist_summary.get("gui_skipped", checklist.get("gui_skipped")),
        "real_camera_skipped": checklist_summary.get(
            "real_camera_skipped",
            checklist.get("real_camera_skipped"),
        ),
        "openai_skipped": checklist_summary.get("openai_skipped", checklist.get("openai_skipped")),
    }
    add_path(
        artifacts,
        category="reference_capture_checklist",
        label="reference_capture_checklist:json",
        value=checklist.get("summary_path") or checklist_summary.get("checklist_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="reference_capture_checklist.summary_path",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="reference_capture_checklist",
        label="reference_capture_checklist:markdown",
        value=checklist.get("markdown_path") or checklist_summary.get("markdown_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="reference_capture_checklist.markdown_path",
        metrics=metrics,
    )
    return {
        "status": checklist_summary.get("status", checklist.get("status")),
        "ok": checklist_summary.get("ok", checklist.get("ok")),
        "summary_path": checklist.get("summary_path") or checklist_summary.get("checklist_path"),
        "markdown_path": checklist.get("markdown_path") or checklist_summary.get("markdown_path"),
        "represented_media_count": metrics.get("represented_media_count"),
        "represented_media": media_summary.get("represented_media", checklist.get("represented_media")),
        "missing_requirement_count": metrics.get("missing_requirement_count"),
        "partial_requirement_count": metrics.get("partial_requirement_count"),
        "action_item_count": metrics.get("action_item_count"),
        "hardware_skipped": metrics.get("hardware_skipped"),
        "gui_skipped": metrics.get("gui_skipped"),
        "real_camera_skipped": metrics.get("real_camera_skipped"),
        "openai_skipped": metrics.get("openai_skipped"),
        "current_view_representation": current_view or None,
        "capture_requirements": checklist_summary.get("capture_requirements"),
        "action_items": checklist_summary.get("action_items"),
        "synthetic_visual_review_outputs": checklist_summary.get("synthetic_visual_review_outputs"),
    }


def collect_visual_review_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    visual_review = suite.get("visual_review")
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    add_path(
        artifacts,
        category="visual_review",
        label="visual_review:summary",
        value=visual_review.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="visual_review.summary_path",
        metrics={
            "status": visual_review.get("status"),
            "ok": visual_review.get("ok"),
            "contact_sheet_count": visual_review.get("contact_sheet_count"),
        },
    )

    distance_metrics = visual_review.get("distance_metrics")
    distance_metrics = distance_metrics if isinstance(distance_metrics, dict) else {}
    metric_paths = distance_metrics.get("paths")
    metric_paths = metric_paths if isinstance(metric_paths, dict) else {}
    metric_rows = distance_metrics.get("rows")
    metric_rows = metric_rows if isinstance(metric_rows, list) else []
    first_metric = next((row for row in metric_rows if isinstance(row, dict)), {})
    first_fields = first_metric.get("distance_depth_fields") if isinstance(first_metric, dict) else {}
    first_fields = first_fields if isinstance(first_fields, dict) else {}
    metric_artifact_summary = {
        "status": distance_metrics.get("status"),
        "ok": distance_metrics.get("ok"),
        "frame_count": distance_metrics.get("frame_count"),
        "units": distance_metrics.get("units"),
        "metric_sources": distance_metrics.get("metric_sources"),
        "ground_truth_scope": distance_metrics.get("ground_truth_scope"),
        "perceived_depth_status": distance_metrics.get("perceived_depth_status"),
        "true_depth_estimation": distance_metrics.get("true_depth_estimation"),
        "example_camera_to_piece_distance_mm": first_fields.get("camera_to_piece_distance_mm"),
        "example_camera_to_board_plane_distance_mm": first_fields.get(
            "camera_to_board_plane_distance_mm"
        ),
        "example_gripper_to_piece_distance_mm": first_fields.get("gripper_to_piece_distance_mm"),
        "gripper_to_piece_distance_source": first_fields.get("gripper_to_piece_distance_source"),
    }
    for key, label_suffix in (("json", "json"), ("csv", "csv")):
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:pick_place_depth_distance_metrics:{label_suffix}",
            value=metric_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"visual_review.distance_metrics.paths.{key}",
            metrics=metric_artifact_summary,
            scenario_id=(
                distance_metrics.get("scenario_id")
                if isinstance(distance_metrics.get("scenario_id"), str)
                else None
            ),
        )

    perceived_comparison = visual_review.get("perceived_depth_comparison")
    perceived_comparison = perceived_comparison if isinstance(perceived_comparison, dict) else {}
    comparison_paths = perceived_comparison.get("paths")
    comparison_paths = comparison_paths if isinstance(comparison_paths, dict) else {}
    comparison_rows = perceived_comparison.get("rows")
    comparison_rows = comparison_rows if isinstance(comparison_rows, list) else []
    first_comparison = next((row for row in comparison_rows if isinstance(row, dict)), {})
    comparison_aggregate = perceived_comparison.get("aggregate")
    comparison_aggregate = comparison_aggregate if isinstance(comparison_aggregate, dict) else {}
    comparison_estimator = perceived_comparison.get("estimator")
    comparison_estimator = comparison_estimator if isinstance(comparison_estimator, dict) else {}
    comparison_artifact_summary = {
        "status": perceived_comparison.get("status"),
        "ok": perceived_comparison.get("ok"),
        "frame_count": perceived_comparison.get("frame_count"),
        "estimator": comparison_estimator.get("name"),
        "estimator_status": comparison_estimator.get("status"),
        "estimator_source": comparison_estimator.get("source"),
        "uses_sim_metadata": comparison_estimator.get("uses_sim_metadata"),
        "uses_real_camera_pixels": comparison_estimator.get("uses_real_camera_pixels"),
        "uses_depth_sensor": comparison_estimator.get("uses_depth_sensor"),
        "mean_abs_camera_to_piece_error_mm": comparison_aggregate.get(
            "mean_abs_camera_to_piece_error_mm"
        ),
        "max_abs_camera_to_piece_error_mm": comparison_aggregate.get(
            "max_abs_camera_to_piece_error_mm"
        ),
        "mean_abs_camera_to_board_error_mm": comparison_aggregate.get(
            "mean_abs_camera_to_board_error_mm"
        ),
        "max_abs_camera_to_board_error_mm": comparison_aggregate.get(
            "max_abs_camera_to_board_error_mm"
        ),
        "example_estimated_camera_to_piece_distance_mm": first_comparison.get(
            "estimated_camera_to_piece_distance_mm"
        ),
        "example_ground_truth_camera_to_piece_distance_mm": first_comparison.get(
            "ground_truth_camera_to_piece_distance_mm"
        ),
        "example_camera_to_piece_error_mm": first_comparison.get("camera_to_piece_error_mm"),
        "example_estimated_camera_to_board_plane_distance_mm": first_comparison.get(
            "estimated_camera_to_board_plane_distance_mm"
        ),
        "example_ground_truth_camera_to_board_plane_distance_mm": first_comparison.get(
            "ground_truth_camera_to_board_plane_distance_mm"
        ),
        "example_camera_to_board_error_mm": first_comparison.get("camera_to_board_error_mm"),
    }
    for key, label_suffix in (("json", "json"), ("csv", "csv")):
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:pick_place_perceived_depth_comparison:{label_suffix}",
            value=comparison_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"visual_review.perceived_depth_comparison.paths.{key}",
            metrics=comparison_artifact_summary,
            scenario_id=(
                perceived_comparison.get("scenario_id")
                if isinstance(perceived_comparison.get("scenario_id"), str)
                else None
            ),
        )

    pnp_diagnostics = visual_review.get("pnp_residual_diagnostics")
    pnp_diagnostics = pnp_diagnostics if isinstance(pnp_diagnostics, dict) else {}
    pnp_paths = pnp_diagnostics.get("paths")
    pnp_paths = pnp_paths if isinstance(pnp_paths, dict) else {}
    pnp_rows = pnp_diagnostics.get("rows")
    pnp_rows = pnp_rows if isinstance(pnp_rows, list) else []
    first_pnp = next((row for row in pnp_rows if isinstance(row, dict)), {})
    pnp_aggregate = pnp_diagnostics.get("aggregate")
    pnp_aggregate = pnp_aggregate if isinstance(pnp_aggregate, dict) else {}
    pnp_assumptions = pnp_diagnostics.get("assumptions")
    pnp_assumptions = pnp_assumptions if isinstance(pnp_assumptions, dict) else {}
    pnp_artifact_summary = {
        "status": pnp_diagnostics.get("status"),
        "ok": pnp_diagnostics.get("ok"),
        "frame_count": pnp_diagnostics.get("frame_count"),
        "board_size_m": pnp_assumptions.get("board_size_m"),
        "default_corner_order": pnp_assumptions.get("default_corner_order"),
        "metadata_projection_comparability_threshold_px": pnp_assumptions.get(
            "metadata_projection_comparability_threshold_px"
        ),
        "mean_metadata_projected_corner_residual_px": pnp_aggregate.get(
            "mean_metadata_projected_corner_residual_px"
        ),
        "mean_rendered_corner_pnp_reprojection_residual_px": pnp_aggregate.get(
            "mean_rendered_corner_pnp_reprojection_residual_px"
        ),
        "mean_abs_rendered_corner_pnp_camera_to_piece_error_mm": pnp_aggregate.get(
            "mean_abs_rendered_corner_pnp_camera_to_piece_error_mm"
        ),
        "mean_abs_rendered_corner_pnp_camera_to_board_error_mm": pnp_aggregate.get(
            "mean_abs_rendered_corner_pnp_camera_to_board_error_mm"
        ),
        "mean_rendered_corner_pnp_camera_center_delta_norm_mm": pnp_aggregate.get(
            "mean_rendered_corner_pnp_camera_center_delta_norm_mm"
        ),
        "not_geometrically_comparable_row_count": pnp_aggregate.get(
            "not_geometrically_comparable_row_count"
        ),
        "reason_label_counts": pnp_aggregate.get("reason_label_counts"),
        "example_reason_labels": first_pnp.get("reason_labels"),
        "example_metadata_projected_corner_mean_residual_px": first_pnp.get(
            "metadata_projected_corner_mean_residual_px"
        ),
        "example_rendered_corner_pnp_reprojection_mean_residual_px": first_pnp.get(
            "rendered_corner_pnp_reprojection_mean_residual_px"
        ),
        "example_rendered_corner_pnp_camera_center_delta_norm_mm": first_pnp.get(
            "rendered_corner_pnp_camera_center_delta_norm_mm"
        ),
        "example_rendered_corner_pnp_camera_to_piece_error_mm": first_pnp.get(
            "rendered_corner_pnp_camera_to_piece_error_mm"
        ),
        "example_rendered_corner_pnp_camera_to_board_error_mm": first_pnp.get(
            "rendered_corner_pnp_camera_to_board_error_mm"
        ),
    }
    for key, label_suffix in (("json", "json"), ("csv", "csv")):
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:pick_place_pnp_residual_diagnostics:{label_suffix}",
            value=pnp_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"visual_review.pnp_residual_diagnostics.paths.{key}",
            metrics=pnp_artifact_summary,
            scenario_id=(
                pnp_diagnostics.get("scenario_id")
                if isinstance(pnp_diagnostics.get("scenario_id"), str)
                else None
            ),
        )

    metadata_native = visual_review.get("metadata_native_depth_view")
    metadata_native = metadata_native if isinstance(metadata_native, dict) else {}
    metadata_native_paths = metadata_native.get("paths")
    metadata_native_paths = metadata_native_paths if isinstance(metadata_native_paths, dict) else {}
    metadata_native_example = metadata_native.get("example_row")
    metadata_native_example = metadata_native_example if isinstance(metadata_native_example, dict) else {}
    metadata_native_visual = metadata_native.get("visual")
    metadata_native_visual = metadata_native_visual if isinstance(metadata_native_visual, dict) else {}
    metadata_native_artifact_summary = {
        "status": metadata_native.get("status"),
        "ok": metadata_native.get("ok"),
        "frame_count": metadata_native.get("frame_count"),
        "row_count": metadata_native.get("row_count"),
        "point_roles": metadata_native.get("point_roles"),
        "source_model": metadata_native.get("source_model"),
        "source_projection_model": metadata_native.get("source_projection_model"),
        "uses_rendered_overlay_corners": metadata_native.get("uses_rendered_overlay_corners"),
        "ground_truth_scope": metadata_native.get("ground_truth_scope"),
        "source_artifacts": metadata_native.get("source_artifacts"),
        "example_stage": metadata_native_example.get("stage"),
        "example_point_role": metadata_native_example.get("point_role"),
        "example_square": metadata_native_example.get("square"),
        "example_metadata_projected_pixel_xy": metadata_native_example.get("metadata_projected_pixel_xy"),
        "example_camera_frame_xyz_mm": metadata_native_example.get("camera_frame_xyz_mm"),
        "example_camera_z_depth_mm": metadata_native_example.get("camera_z_depth_mm"),
        "example_camera_range_mm": metadata_native_example.get("camera_range_mm"),
        "example_board_plane_distance_mm": metadata_native_example.get("board_plane_distance_mm"),
        "output_dimensions": metadata_native_visual.get("output_dimensions"),
    }
    for key, label_suffix in (("png", "png"), ("json", "json"), ("csv", "csv")):
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:pick_place_metadata_native_depth_view:{label_suffix}",
            value=metadata_native_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"visual_review.metadata_native_depth_view.paths.{key}",
            metrics=metadata_native_artifact_summary,
            scenario_id=(
                metadata_native.get("scenario_id")
                if isinstance(metadata_native.get("scenario_id"), str)
                else None
            ),
        )

    scorecard = visual_review.get("depth_distance_scorecard")
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    scorecard_paths = scorecard.get("paths")
    scorecard_paths = scorecard_paths if isinstance(scorecard_paths, dict) else {}
    scorecard_baseline = scorecard.get("metadata_derived_baseline")
    scorecard_baseline = scorecard_baseline if isinstance(scorecard_baseline, dict) else {}
    scorecard_pnp = scorecard.get("pnp_residuals")
    scorecard_pnp = scorecard_pnp if isinstance(scorecard_pnp, dict) else {}
    scorecard_gap = scorecard.get("real_camera_depth_gap")
    scorecard_gap = scorecard_gap if isinstance(scorecard_gap, dict) else {}
    scorecard_real_depth = scorecard.get("real_depth_reference")
    scorecard_real_depth = scorecard_real_depth if isinstance(scorecard_real_depth, dict) else scorecard_gap
    scorecard_real_depth_residuals = scorecard_real_depth.get("residual_aggregate")
    scorecard_real_depth_residuals = (
        scorecard_real_depth_residuals if isinstance(scorecard_real_depth_residuals, dict) else {}
    )
    scorecard_visual = scorecard.get("visual")
    scorecard_visual = scorecard_visual if isinstance(scorecard_visual, dict) else {}
    scorecard_artifact_summary = {
        "status": scorecard.get("status"),
        "ok": scorecard.get("ok"),
        "review_status": scorecard.get("review_status"),
        "at_a_glance": scorecard.get("at_a_glance"),
        "frame_count": scorecard.get("frame_count"),
        "status_labels": scorecard.get("status_labels"),
        "baseline_quality": scorecard_baseline.get("quality"),
        "baseline_quality_status": scorecard_baseline.get("quality_status"),
        "worst_mean_abs_depth_error_mm": scorecard_baseline.get(
            "worst_mean_abs_depth_error_mm"
        ),
        "mean_abs_camera_to_piece_error_mm": scorecard_baseline.get(
            "mean_abs_camera_to_piece_error_mm"
        ),
        "mean_abs_camera_to_board_error_mm": scorecard_baseline.get(
            "mean_abs_camera_to_board_error_mm"
        ),
        "mean_abs_camera_to_target_square_error_mm": scorecard_baseline.get(
            "mean_abs_camera_to_target_square_error_mm"
        ),
        "mean_board_corner_reprojection_residual_px": scorecard_baseline.get(
            "mean_board_corner_reprojection_residual_px"
        ),
        "metadata_corner_quality": scorecard_pnp.get("quality"),
        "mean_metadata_projected_corner_residual_px": scorecard_pnp.get(
            "mean_metadata_projected_corner_residual_px"
        ),
        "not_geometrically_comparable_row_count": scorecard_pnp.get(
            "not_geometrically_comparable_row_count"
        ),
        "real_camera_depth_status": scorecard_real_depth.get("status"),
        "real_depth_comparable": scorecard_real_depth.get("real_depth_comparable"),
        "needs_real_depth_reference": scorecard_real_depth.get("needs_real_depth_reference"),
        "real_depth_reference_missing_inputs": scorecard_real_depth.get("missing_inputs"),
        "real_depth_projection_row_count": scorecard_real_depth_residuals.get("projection_row_count"),
        "real_depth_depth_row_count": scorecard_real_depth_residuals.get("depth_row_count"),
        "mean_real_vs_sim_projection_residual_px": scorecard_real_depth_residuals.get(
            "mean_real_vs_sim_projection_residual_px"
        ),
        "mean_abs_real_vs_sim_depth_residual_mm": scorecard_real_depth_residuals.get(
            "mean_abs_real_vs_sim_depth_residual_mm"
        ),
        "real_projection_intake_summary_path": scorecard_real_depth.get("intake_summary_path"),
        "real_projection_residual_paths": scorecard_real_depth.get("residual_paths"),
        "source_artifacts": scorecard.get("source_artifacts"),
        "output_dimensions": scorecard_visual.get("output_dimensions"),
    }
    for key, label_suffix in (("png", "png"), ("json", "json")):
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:pick_place_depth_distance_scorecard:{label_suffix}",
            value=scorecard_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"visual_review.depth_distance_scorecard.paths.{key}",
            metrics=scorecard_artifact_summary,
            scenario_id=(
                scorecard.get("scenario_id")
                if isinstance(scorecard.get("scenario_id"), str)
                else None
            ),
        )

    contact_sheets = visual_review.get("contact_sheets")
    contact_sheet_rows = contact_sheets if isinstance(contact_sheets, list) else []
    for sheet in contact_sheet_rows:
        if not isinstance(sheet, dict):
            continue
        sheet_id = sheet.get("id")
        if not isinstance(sheet_id, str) or not sheet_id:
            sheet_id = "contact_sheet"
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:{sheet_id}",
            value=sheet.get("path"),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="visual_review.contact_sheets",
            metrics={
                "label": sheet.get("label"),
                "source": sheet.get("source"),
                "source_collection": sheet.get("source_collection"),
                "source_frame_count": sheet.get("source_frame_count"),
                "source_frame_labels": sheet.get("source_frame_labels"),
                "output_dimensions": sheet.get("output_dimensions"),
            },
        )

    frame_sequences = visual_review.get("frame_sequences")
    sequence_rows = frame_sequences if isinstance(frame_sequences, list) else []
    for sequence in sequence_rows:
        if not isinstance(sequence, dict):
            continue
        sequence_id = str(sequence.get("id") or "frame_sequence")
        frames = sequence.get("frames")
        frame_rows = frames if isinstance(frames, list) else []
        for frame in frame_rows:
            if not isinstance(frame, dict):
                continue
            frame_id = str(frame.get("id") or "frame")
            add_path(
                artifacts,
                category="visual_review",
                label=f"visual_review:{sequence_id}:{frame_id}",
                value=frame.get("path"),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source="visual_review.frame_sequences.frames",
                metrics={
                    "label": sequence.get("label"),
                    "sequence_id": sequence_id,
                    "scenario_id": sequence.get("scenario_id"),
                    "capture_label": frame.get("capture_label"),
                    "stage": frame.get("stage"),
                    "description": frame.get("description"),
                    "source_path": frame.get("source_path"),
                    "source_relative_path": frame.get("source_relative_path"),
                    "output_dimensions": frame.get("output_dimensions"),
                    "gripper": frame.get("gripper"),
                    "piece_visibility": frame.get("piece_visibility"),
                    "distance_depth_fields": frame.get("distance_depth_fields"),
                },
                scenario_id=sequence.get("scenario_id") if isinstance(sequence.get("scenario_id"), str) else None,
            )

    app_frame = visual_review.get("app_entrypoint_frame")
    app_frame = app_frame if isinstance(app_frame, dict) else {}
    add_path(
        artifacts,
        category="visual_review",
        label="visual_review:app_entrypoint_frame",
        value=app_frame.get("review_copy_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="visual_review.app_entrypoint_frame.review_copy_path",
        metrics={
            "status": app_frame.get("status"),
            "source_path": app_frame.get("source_path"),
            "output_dimensions": app_frame.get("output_dimensions"),
        },
    )

    recordings = visual_review.get("recordings")
    if isinstance(recordings, dict) and recordings:
        recording_items = sorted(recordings.items())
    else:
        recording = visual_review.get("recording")
        recording_items = [("gripper_camera_pov", recording)] if isinstance(recording, dict) else []
    for recording_id, recording in recording_items:
        if not isinstance(recording, dict) or recording.get("produced") is not True:
            continue
        add_path(
            artifacts,
            category="visual_review",
            label=f"visual_review:{recording_id}_recording",
            value=recording.get("path"),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"visual_review.recordings.{recording_id}.path",
            metrics={
                "codec": recording.get("codec"),
                "fps": recording.get("fps"),
                "frame_count": recording.get("frame_count"),
                "duration_seconds": recording.get("duration_seconds"),
                "dimensions": recording.get("dimensions"),
            },
        )
    return visual_review


def collect_ranked_candidate_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> None:
    selected = suite.get("selected_candidate") if isinstance(suite.get("selected_candidate"), dict) else {}
    rank = selected.get("rank") if isinstance(selected.get("rank"), int) else None
    candidate_id = selected.get("candidate_id") if isinstance(selected.get("candidate_id"), str) else None
    paths = selected.get("artifact_paths")
    if not isinstance(paths, dict):
        return
    metrics = {
        key: selected.get(key)
        for key in ("rank_score",)
        if selected.get(key) is not None
    }
    for key, value in sorted(paths.items()):
        add_path(
            artifacts,
            category="ranked_candidate",
            label=f"ranked_candidate:{key}",
            value=value,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="selected_candidate.artifact_paths",
            metrics=metrics,
            rank=rank,
            candidate_id=candidate_id,
        )


def collect_perception_fixture_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> None:
    fixture = suite.get("perception_fixture") if isinstance(suite.get("perception_fixture"), dict) else {}
    add_path(
        artifacts,
        category="perception_fixture",
        label="perception_fixture:summary",
        value=fixture.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="perception_fixture.summary_path",
    )
    paths = fixture.get("artifact_paths")
    if not isinstance(paths, dict):
        return
    selected = fixture.get("selected_candidate") if isinstance(fixture.get("selected_candidate"), dict) else {}
    rank = selected.get("rank") if isinstance(selected.get("rank"), int) else None
    candidate_id = selected.get("candidate_id") if isinstance(selected.get("candidate_id"), str) else None
    for key, value in sorted(paths.items()):
        add_path(
            artifacts,
            category="perception_fixture",
            label=f"perception_fixture:{key}",
            value=value,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="perception_fixture.artifact_paths",
            rank=rank,
            candidate_id=candidate_id,
        )


def collect_sim_camera_pose_fixture_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    fixture = suite.get("sim_camera_pose_fixture")
    fixture = fixture if isinstance(fixture, dict) else {}
    metadata_contract = fixture.get("metadata_contract")
    metadata_contract = metadata_contract if isinstance(metadata_contract, dict) else {}
    required_keys = metadata_contract.get("required_keys")
    required_keys = required_keys if isinstance(required_keys, list) else []
    add_path(
        artifacts,
        category="sim_camera_pose_fixture",
        label="sim_camera_pose_fixture:summary",
        value=fixture.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="sim_camera_pose_fixture.summary_path",
        metrics={"status": fixture.get("status"), "case_count": fixture.get("case_count")},
    )
    cases = fixture.get("cases")
    case_rows = cases if isinstance(cases, list) else []
    case_metrics: dict[str, dict[str, Any]] = {}
    for case in case_rows:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            continue
        checks = case.get("metadata_contract_checks")
        checks = checks if isinstance(checks, dict) else {}
        case_metrics[str(case.get("case_id"))] = {
            "view": case.get("view"),
            "profile": case.get("profile"),
            "target_square": case.get("target_square"),
            "piece_square": case.get("piece_square"),
            "unique_colors": case.get("unique_colors"),
            "metadata_contract_ok": (
                all(bool(checks.get(str(key))) for key in required_keys)
                if required_keys
                else None
            ),
            "metadata_image_size": bool(checks.get("image_size_px")),
            "metadata_intrinsics": bool(checks.get("camera_matrix_px") and checks.get("intrinsics")),
            "metadata_distortion": bool(checks.get("distortion_coefficients")),
            "metadata_extrinsics_board_to_camera": bool(checks.get("extrinsics.board_to_camera")),
            "metadata_coordinate_frames": bool(checks.get("coordinate_frame_convention")),
            "metadata_scope": checks.get("coordinate_frame_scope"),
        }
    for collection_key, label_suffix in (
        ("frame_paths", "frame"),
        ("annotated_frame_paths", "annotated_frame"),
        ("metadata_paths", "metadata"),
    ):
        paths = fixture.get(collection_key)
        if not isinstance(paths, dict):
            continue
        for case_id, value in sorted(paths.items()):
            case_id_str = str(case_id)
            add_path(
                artifacts,
                category="sim_camera_pose_fixture",
                label=f"sim_camera_pose_fixture:{case_id_str}:{label_suffix}",
                value=value,
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"sim_camera_pose_fixture.{collection_key}",
                metrics=case_metrics.get(case_id_str),
                scenario_id=case_id_str,
            )
    return metadata_contract


def collect_ik_reachability_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    ik = suite.get("ik_reachability_drill")
    ik = ik if isinstance(ik, dict) else {}
    artifact_paths = ik.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    model_diagnostic = ik.get("model_diagnostic")
    model_diagnostic = model_diagnostic if isinstance(model_diagnostic, dict) else {}
    model_solver = ik.get("model_solver")
    model_solver = model_solver if isinstance(model_solver, dict) else {}
    metrics = {
        "status": ik.get("status"),
        "ok": ik.get("ok"),
        "row_count": ik.get("row_count"),
        "counts_by_feasibility": ik.get("counts_by_feasibility"),
        "model_diagnostic_status": model_diagnostic.get("status"),
        "model_diagnostic_reason": model_diagnostic.get("reason"),
        "repo_local_model_count": model_diagnostic.get("repo_local_model_count"),
        "selected_model_path": model_diagnostic.get("selected_model_path"),
        "selected_model_source": model_diagnostic.get("selected_model_source"),
        "model_solver_available": model_solver.get("available"),
        "model_solver_status": model_solver.get("status"),
        "model_solver_backend": model_solver.get("solver_backend"),
        "model_solver_reason": model_solver.get("reason"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("rows_csv", "rows"),
        ("heatmap_png", "heatmap"),
    ):
        add_path(
            artifacts,
            category="ik_reachability",
            label=f"ik_reachability:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"ik_reachability_drill.artifacts.{key}",
            metrics=metrics,
        )
    return {
        "status": ik.get("status"),
        "ok": ik.get("ok"),
        "summary_path": artifact_paths.get("summary_json") or ik.get("summary_path"),
        "rows_csv_path": artifact_paths.get("rows_csv"),
        "heatmap_png_path": artifact_paths.get("heatmap_png"),
        "row_count": ik.get("row_count"),
        "counts_by_feasibility": ik.get("counts_by_feasibility"),
        "model_diagnostic": model_diagnostic,
        "model_solver": model_solver,
    }


def collect_so101_model_contract_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    contract = suite.get("so101_model_contract")
    contract = contract if isinstance(contract, dict) else {}
    artifact_paths = contract.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    model_request = contract.get("model_request")
    model_request = model_request if isinstance(model_request, dict) else {}
    robot_kinematics_path = contract.get("robot_kinematics_path")
    robot_kinematics_path = robot_kinematics_path if isinstance(robot_kinematics_path, dict) else {}
    metrics = {
        "status": contract.get("status"),
        "ok": contract.get("ok"),
        "model_request_status": contract.get("model_request_status") or model_request.get("status"),
        "model_request_path": model_request.get("path"),
        "model_request_exists": model_request.get("exists"),
        "robot_kinematics_status": contract.get("robot_kinematics_status")
        or robot_kinematics_path.get("status"),
        "robot_kinematics_directly_usable": robot_kinematics_path.get("directly_usable"),
        "placo_available": robot_kinematics_path.get("placo_available"),
        "target_frame": contract.get("target_frame"),
        "missing_alignment_input_count": contract.get("missing_alignment_input_count"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("checklist_csv", "checklist"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="so101_model_contract",
            label=f"so101_model_contract:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_model_contract.artifacts.{key}",
            metrics=metrics,
        )
    return {
        "status": contract.get("status"),
        "ok": contract.get("ok"),
        "summary_path": artifact_paths.get("summary_json") or contract.get("summary_path"),
        "checklist_csv_path": artifact_paths.get("checklist_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "model_request_status": metrics["model_request_status"],
        "model_request": model_request,
        "robot_kinematics_status": metrics["robot_kinematics_status"],
        "robot_kinematics_path": robot_kinematics_path,
        "target_frame": contract.get("target_frame"),
        "missing_alignment_input_count": contract.get("missing_alignment_input_count"),
    }


def collect_so101_model_bundle_manifest_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    bundle = suite.get("so101_model_bundle_manifest")
    bundle = bundle if isinstance(bundle, dict) else {}
    artifact_paths = bundle.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    manifest_request = bundle.get("manifest_request")
    manifest_request = manifest_request if isinstance(manifest_request, dict) else {}
    model_path = bundle.get("model_path")
    model_path = model_path if isinstance(model_path, dict) else {}
    asset_roots = bundle.get("asset_roots")
    asset_roots = asset_roots if isinstance(asset_roots, dict) else {}
    target_frame = bundle.get("target_frame")
    target_frame = target_frame if isinstance(target_frame, dict) else {}
    tcp_offset = bundle.get("tcp_offset")
    tcp_offset = tcp_offset if isinstance(tcp_offset, dict) else {}
    alignment = bundle.get("base_to_board_alignment")
    alignment = alignment if isinstance(alignment, dict) else {}
    forwarding = bundle.get("forwarding")
    forwarding = forwarding if isinstance(forwarding, dict) else {}
    contract = bundle.get("contract_checker")
    contract = contract if isinstance(contract, dict) else {}
    contract_artifacts = contract.get("artifacts")
    contract_artifacts = contract_artifacts if isinstance(contract_artifacts, dict) else {}
    asset_preflight = bundle.get("model_asset_preflight")
    asset_preflight = asset_preflight if isinstance(asset_preflight, dict) else {}
    asset_preflight_artifacts = asset_preflight.get("artifacts")
    asset_preflight_artifacts = asset_preflight_artifacts if isinstance(asset_preflight_artifacts, dict) else {}
    metrics = {
        "status": bundle.get("status"),
        "ok": bundle.get("ok"),
        "manifest_request_status": manifest_request.get("status"),
        "manifest_path": manifest_request.get("path"),
        "ready_for_model_backed_ik": bundle.get("ready_for_model_backed_ik"),
        "model_path_status": model_path.get("status"),
        "model_path": model_path.get("path"),
        "asset_root_status": asset_roots.get("status"),
        "asset_roots": asset_roots.get("asset_roots"),
        "target_frame": target_frame.get("value"),
        "target_frame_status": target_frame.get("status"),
        "tcp_offset_status": tcp_offset.get("status"),
        "tcp_offset_field": tcp_offset.get("field"),
        "base_to_board_alignment_status": alignment.get("status"),
        "base_to_board_alignment_field": alignment.get("field"),
        "contract_status": contract.get("status"),
        "contract_model_request_status": contract.get("model_request_status"),
        "contract_robot_kinematics_status": contract.get("robot_kinematics_status"),
        "asset_preflight_status": asset_preflight.get("status"),
        "asset_preflight_mesh_reference_count": asset_preflight.get("mesh_reference_count"),
        "asset_preflight_present_asset_count": asset_preflight.get("present_asset_count"),
        "asset_preflight_missing_asset_count": asset_preflight.get("missing_asset_count"),
        "asset_preflight_unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
        "missing_inputs": bundle.get("missing_inputs"),
        "diagnostic_only": forwarding.get("diagnostic_only"),
        "diagnostic_only_reason": forwarding.get("diagnostic_only_reason"),
        "ik_model_path_source": forwarding.get("ik_model_path_source"),
        "ik_model_asset_root_source": forwarding.get("ik_model_asset_root_source"),
        "used_for_downstream_contract": forwarding.get("used_for_downstream_contract"),
        "used_for_downstream_ik": forwarding.get("used_for_downstream_ik"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("checklist_csv", "checklist"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="so101_model_bundle_manifest",
            label=f"so101_model_bundle_manifest:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_model_bundle_manifest.artifacts.{key}",
            metrics=metrics,
        )

    if contract.get("returncode") is not None:
        for key, label_suffix in (
            ("summary_json", "child_contract_summary"),
            ("checklist_csv", "child_contract_checklist"),
            ("readme_md", "child_contract_readme"),
        ):
            add_path(
                artifacts,
                category="so101_model_bundle_manifest",
                label=f"so101_model_bundle_manifest:{label_suffix}",
                value=contract_artifacts.get(key),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"so101_model_bundle_manifest.contract_checker.artifacts.{key}",
                metrics=metrics,
            )
        for key, label_suffix in (
            ("summary_json", "child_asset_preflight_summary"),
            ("assets_csv", "child_asset_preflight_assets"),
            ("readme_md", "child_asset_preflight_readme"),
        ):
            add_path(
                artifacts,
                category="so101_model_bundle_manifest",
                label=f"so101_model_bundle_manifest:{label_suffix}",
                value=asset_preflight_artifacts.get(key),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"so101_model_bundle_manifest.model_asset_preflight.artifacts.{key}",
                metrics=metrics,
            )

    return {
        "status": bundle.get("status"),
        "ok": bundle.get("ok"),
        "summary_path": artifact_paths.get("summary_json") or bundle.get("summary_path"),
        "checklist_csv_path": artifact_paths.get("checklist_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "manifest_request": manifest_request,
        "ready_for_model_backed_ik": bundle.get("ready_for_model_backed_ik"),
        "model_path": model_path,
        "asset_roots": asset_roots,
        "target_frame": target_frame,
        "tcp_offset": tcp_offset,
        "base_to_board_alignment": alignment,
        "contract_checker": contract,
        "model_asset_preflight": asset_preflight,
        "missing_inputs": bundle.get("missing_inputs"),
        "forwarding": forwarding,
    }


def collect_so101_model_asset_preflight_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    contract = suite.get("so101_model_contract")
    contract = contract if isinstance(contract, dict) else {}
    asset_preflight = contract.get("model_asset_preflight")
    asset_preflight = asset_preflight if isinstance(asset_preflight, dict) else {}
    artifact_paths = asset_preflight.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    metrics = {
        "status": asset_preflight.get("status"),
        "ok": asset_preflight.get("ok"),
        "model_request_status": asset_preflight.get("model_request_status"),
        "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
        "present_asset_count": asset_preflight.get("present_asset_count"),
        "missing_asset_count": asset_preflight.get("missing_asset_count"),
        "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
        "missing_assets": asset_preflight.get("missing_assets"),
        "unresolved_references": asset_preflight.get("unresolved_references"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("assets_csv", "assets"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="so101_model_asset_preflight",
            label=f"so101_model_asset_preflight:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_model_contract.model_asset_preflight.artifacts.{key}",
            metrics=metrics,
        )
    return {
        "status": asset_preflight.get("status"),
        "ok": asset_preflight.get("ok"),
        "summary_path": artifact_paths.get("summary_json"),
        "assets_csv_path": artifact_paths.get("assets_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "model_request_status": asset_preflight.get("model_request_status"),
        "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
        "present_asset_count": asset_preflight.get("present_asset_count"),
        "missing_asset_count": asset_preflight.get("missing_asset_count"),
        "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
    }


def collect_so101_model_source_inventory_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    inventory = suite.get("so101_model_source_inventory")
    inventory = inventory if isinstance(inventory, dict) else {}
    artifact_paths = inventory.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    recommended_contract_check = inventory.get("recommended_contract_check")
    recommended_contract_check = (
        recommended_contract_check
        if isinstance(recommended_contract_check, dict)
        else {}
    )
    source_configuration = inventory.get("source_configuration")
    source_configuration = source_configuration if isinstance(source_configuration, dict) else {}
    metrics = {
        "status": inventory.get("status"),
        "ok": inventory.get("ok"),
        "candidate_count": inventory.get("candidate_count"),
        "likely_candidate_count": inventory.get("likely_candidate_count"),
        "direct_contract_candidate_count": inventory.get("direct_contract_candidate_count"),
        "authoritative_candidate_count": inventory.get("authoritative_candidate_count"),
        "root_count": inventory.get("root_count"),
        "source_scan_mode": source_configuration.get("scan_mode"),
        "configured_model_source_roots": source_configuration.get("model_source_roots"),
        "configured_model_source_extra_roots": source_configuration.get("model_source_extra_roots"),
        "configured_authoritative_model_paths": source_configuration.get("authoritative_model_paths"),
        "configured_authoritative_model_roots": source_configuration.get("authoritative_model_roots"),
        "ik_model_path_is_authority": source_configuration.get("ik_model_path_is_authority"),
        "recommended_contract_check_path": inventory.get("recommended_contract_check_path")
        or recommended_contract_check.get("candidate_path"),
        "recommended_contract_check_candidate_id": recommended_contract_check.get("candidate_id"),
        "recommended_contract_check_authoritative": recommended_contract_check.get("authoritative"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("candidates_csv", "candidates"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="so101_model_source_inventory",
            label=f"so101_model_source_inventory:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_model_source_inventory.artifacts.{key}",
            metrics=metrics,
        )
    return {
        "status": inventory.get("status"),
        "ok": inventory.get("ok"),
        "summary_path": artifact_paths.get("summary_json") or inventory.get("summary_path"),
        "candidates_csv_path": artifact_paths.get("candidates_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "candidate_count": inventory.get("candidate_count"),
        "likely_candidate_count": inventory.get("likely_candidate_count"),
        "direct_contract_candidate_count": inventory.get("direct_contract_candidate_count"),
        "authoritative_candidate_count": inventory.get("authoritative_candidate_count"),
        "source_configuration": source_configuration,
        "recommended_contract_check_path": metrics["recommended_contract_check_path"],
        "recommended_contract_check": recommended_contract_check or None,
        "diagnostics": inventory.get("diagnostics"),
    }


def collect_app_entrypoint_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    app_entrypoint = suite.get("app_entrypoint_metadata")
    app_entrypoint = app_entrypoint if isinstance(app_entrypoint, dict) else {}
    metadata_contract = app_entrypoint.get("metadata_contract")
    metadata_contract = metadata_contract if isinstance(metadata_contract, dict) else {}
    contract_checks = app_entrypoint.get("metadata_contract_checks")
    contract_checks = contract_checks if isinstance(contract_checks, dict) else {}
    app_camera_status = app_entrypoint.get("app_camera_status")
    app_camera_status = app_camera_status if isinstance(app_camera_status, dict) else {}
    app_camera_metadata_contract = app_camera_status.get("metadata_contract")
    app_camera_metadata_contract = (
        app_camera_metadata_contract
        if isinstance(app_camera_metadata_contract, dict)
        else {}
    )
    metrics = {
        "status": app_entrypoint.get("status"),
        "ok": app_entrypoint.get("ok"),
        "sim_camera_profile": app_entrypoint.get("sim_camera_profile"),
        "app_camera_status_ok": app_camera_status.get("ok"),
        "app_camera_status_readout": app_camera_status.get("readout"),
        "app_camera_status_contract": app_camera_metadata_contract.get("status"),
        "metadata_contract_ok": metadata_contract.get("ok"),
        "metadata_contract_check_count": metadata_contract.get("check_count"),
        "metadata_contract_failed_check_count": metadata_contract.get("failed_check_count"),
        "metadata_contract_checks": contract_checks,
        "hardware_skipped": app_entrypoint.get("hardware_skipped"),
        "gui_skipped": app_entrypoint.get("gui_skipped"),
        "openai_skipped": app_entrypoint.get("openai_skipped"),
    }
    add_path(
        artifacts,
        category="app_entrypoint",
        label="app_entrypoint:summary",
        value=app_entrypoint.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="app_entrypoint_metadata.summary_path",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="app_entrypoint",
        label="app_entrypoint:frame",
        value=app_entrypoint.get("frame_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="app_entrypoint_metadata.frame_path",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="app_entrypoint",
        label="app_entrypoint:metadata_sidecar",
        value=app_entrypoint.get("metadata_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="app_entrypoint_metadata.metadata_path",
        metrics=metrics,
    )
    return metadata_contract


def collect_gripper_camera_pov_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    pov = suite.get("gripper_camera_pov_review")
    pov = pov if isinstance(pov, dict) else {}
    metadata_contract = pov.get("metadata_contract")
    metadata_contract = metadata_contract if isinstance(metadata_contract, dict) else {}
    contract_by_state = metadata_contract.get("by_state")
    contract_by_state = contract_by_state if isinstance(contract_by_state, dict) else {}
    visibility_by_state = pov.get("visibility_by_state")
    visibility_by_state = visibility_by_state if isinstance(visibility_by_state, dict) else {}
    projection_by_state = pov.get("projection_by_state")
    projection_by_state = projection_by_state if isinstance(projection_by_state, dict) else {}
    gripper_by_state = pov.get("gripper_by_state")
    gripper_by_state = gripper_by_state if isinstance(gripper_by_state, dict) else {}
    required_keys = metadata_contract.get("required_keys")
    required_keys = required_keys if isinstance(required_keys, list) else []

    add_path(
        artifacts,
        category="gripper_camera_pov",
        label="gripper_camera_pov:summary",
        value=pov.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="gripper_camera_pov_review.summary_path",
        metrics={
            "status": pov.get("status"),
            "ok": pov.get("ok"),
            "target_square": pov.get("target_square"),
            "state_count": pov.get("state_count"),
            "metadata_contract_ok": metadata_contract.get("all_states_include_required_metadata"),
            "min_visible_fraction": (
                pov.get("piece_visibility", {}).get("min_visible_fraction")
                if isinstance(pov.get("piece_visibility"), dict)
                else None
            ),
            "max_occlusion_fraction": (
                pov.get("piece_visibility", {}).get("max_occlusion_fraction")
                if isinstance(pov.get("piece_visibility"), dict)
                else None
            ),
        },
    )

    state_metrics: dict[str, dict[str, Any]] = {}
    state_ids = pov.get("state_ids")
    iterable_state_ids = (
        state_ids
        if isinstance(state_ids, list)
        else sorted(set(visibility_by_state) | set(projection_by_state) | set(gripper_by_state))
    )
    for state_id_value in iterable_state_ids:
        state_id = str(state_id_value)
        visibility = visibility_by_state.get(state_id)
        visibility = visibility if isinstance(visibility, dict) else {}
        projection = projection_by_state.get(state_id)
        projection = projection if isinstance(projection, dict) else {}
        target_projection = projection.get("target_square")
        target_projection = target_projection if isinstance(target_projection, dict) else {}
        piece_projection = projection.get("piece_square")
        piece_projection = piece_projection if isinstance(piece_projection, dict) else {}
        gripper = gripper_by_state.get(state_id)
        gripper = gripper if isinstance(gripper, dict) else {}
        contract_checks = contract_by_state.get(state_id)
        contract_checks = contract_checks if isinstance(contract_checks, dict) else {}
        metrics = {
            "target_square": target_projection.get("square"),
            "target_center_xy": target_projection.get("center_image_xy"),
            "piece_square": piece_projection.get("square"),
            "piece_center_xy": piece_projection.get("center_image_xy") or visibility.get("piece_center_xy"),
            "visibility_status": visibility.get("status"),
            "visible_fraction": visibility.get("visible_fraction"),
            "occlusion_fraction": visibility.get("occlusion_fraction"),
            "min_clearance_px": visibility.get("min_clearance_px"),
            "clear_of_gripper": visibility.get("clear_of_gripper"),
            "tracked_gripper_percent": gripper.get("tracked_gripper_percent"),
            "current_gripper_opening_px": gripper.get("current_gripper_opening_px"),
            "metadata_contract_ok": (
                all(bool(contract_checks.get(str(key))) for key in required_keys)
                if required_keys
                else None
            ),
            "metadata_intrinsics": bool(contract_checks.get("camera_matrix_px") and contract_checks.get("intrinsics")),
            "metadata_distortion": bool(contract_checks.get("distortion_coefficients")),
            "metadata_extrinsics_board_to_camera": bool(contract_checks.get("extrinsics.board_to_camera")),
            "metadata_coordinate_frames": bool(contract_checks.get("coordinate_frame_convention")),
            "piece_visibility": bool(contract_checks.get("piece_visibility")),
        }
        state_metrics[state_id] = metrics

    for collection_key, label_suffix in (
        ("frame_paths", "frame"),
        ("annotated_frame_paths", "annotated_frame"),
        ("metadata_paths", "metadata"),
    ):
        paths = pov.get(collection_key)
        if not isinstance(paths, dict):
            continue
        for state_id, value in sorted(paths.items()):
            state_id_str = str(state_id)
            add_path(
                artifacts,
                category="gripper_camera_pov",
                label=f"gripper_camera_pov:{state_id_str}:{label_suffix}",
                value=value,
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"gripper_camera_pov_review.{collection_key}",
                metrics=state_metrics.get(state_id_str),
                scenario_id=state_id_str,
            )
    return {
        "metadata_contract": metadata_contract,
        "piece_visibility": pov.get("piece_visibility"),
    }


def collect_pick_place_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, dict[str, Any]]:
    matrix = suite.get("pick_place_scenario_matrix") if isinstance(suite.get("pick_place_scenario_matrix"), dict) else {}
    add_path(
        artifacts,
        category="pick_place_scenario",
        label="pick_place_scenario:summary",
        value=matrix.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="pick_place_scenario_matrix.summary_path",
    )
    release_paths = matrix.get("release_frame_paths")
    visibility = matrix.get("piece_visibility_by_scenario")
    release_paths = release_paths if isinstance(release_paths, dict) else {}
    visibility = visibility if isinstance(visibility, dict) else {}

    release_metrics: dict[str, dict[str, Any]] = {}
    for scenario_id, value in sorted(release_paths.items()):
        scenario_metrics = visibility.get(scenario_id)
        scenario_metrics = scenario_metrics if isinstance(scenario_metrics, dict) else {}
        target_release = scenario_metrics.get("target_release_open")
        target_release = target_release if isinstance(target_release, dict) else {}
        metrics = {
            "target_release_open": target_release,
            "aggregate": {
                key: scenario_metrics.get(key)
                for key in (
                    "available",
                    "all_captures_clear_of_gripper",
                    "min_visible_fraction",
                    "max_occlusion_fraction",
                    "min_clearance_px",
                    "worst_capture_label",
                )
                if key in scenario_metrics
            },
        }
        release_metrics[str(scenario_id)] = metrics
        add_path(
            artifacts,
            category="pick_place_scenario",
            label=f"pick_place_scenario:{scenario_id}:target_release_open",
            value=value,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="pick_place_scenario_matrix.release_frame_paths",
            metrics=metrics,
            scenario_id=str(scenario_id),
        )
    return release_metrics


def collect_negative_check_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> None:
    negative = suite.get("negative_check") if isinstance(suite.get("negative_check"), dict) else {}
    add_path(
        artifacts,
        category="negative_check",
        label="negative_check:summary",
        value=negative.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="negative_check.summary_path",
        metrics={"status": negative.get("status"), "included": negative.get("included")},
    )


def collect_log_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> None:
    child_commands = suite.get("child_commands")
    if not isinstance(child_commands, dict):
        return
    for child_name, record in sorted(child_commands.items()):
        if not isinstance(record, dict):
            continue
        metrics = {
            "ok": record.get("ok"),
            "return_code": record.get("return_code"),
            "status": record.get("summary_status"),
            "expected_failure": record.get("expected_failure"),
        }
        for key in ("stdout_path", "stderr_path", "expected_output_json_path"):
            add_path(
                artifacts,
                category="logs",
                label=f"logs:{child_name}:{key}",
                value=record.get(key),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"child_commands.{child_name}.{key}",
                metrics=metrics,
            )


def collect_evidence_bundle_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    evidence_bundle = suite.get("evidence_bundle")
    evidence_bundle = evidence_bundle if isinstance(evidence_bundle, dict) else {}
    metrics = {
        "status": evidence_bundle.get("status"),
        "ok": evidence_bundle.get("ok"),
        "real_depth_reference_status": evidence_bundle.get("real_depth_reference_status"),
        "missing_required_artifact_count": evidence_bundle.get("missing_required_artifact_count"),
        "capture_plan": evidence_bundle.get("capture_plan"),
    }
    add_path(
        artifacts,
        category="evidence_bundle",
        label="evidence_bundle:markdown",
        value=evidence_bundle.get("markdown_path") or evidence_bundle.get("output_md"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="evidence_bundle.markdown_path",
        metrics=metrics,
    )
    add_path(
        artifacts,
        category="evidence_bundle",
        label="evidence_bundle:json",
        value=evidence_bundle.get("summary_path") or evidence_bundle.get("output_json"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="evidence_bundle.summary_path",
        metrics=metrics,
    )
    return evidence_bundle


def sort_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for artifact in artifacts:
        key = (str(artifact["category"]), str(artifact["label"]), str(artifact["path"]))
        unique[key] = artifact
    return sorted(
        unique.values(),
        key=lambda row: (
            CATEGORY_ORDER.get(str(row["category"]), 99),
            str(row["label"]),
            str(row["relative_path"] or row["repo_relative_path"] or row["path"]),
        ),
    )


def build_index(suite_summary_path: Path, output_json: Path) -> dict[str, Any]:
    suite_summary_path = suite_summary_path.expanduser().resolve()
    suite = read_json_object(suite_summary_path, label="suite summary")
    output_dir = Path(str(suite.get("output_dir") or suite_summary_path.parent)).expanduser().resolve()
    repo_root_value = suite.get("repo_root")
    repo_root = Path(repo_root_value).expanduser().resolve() if isinstance(repo_root_value, str) else None
    artifacts: list[dict[str, Any]] = []

    add_path(
        artifacts,
        category="logs",
        label="suite:summary",
        value=str(suite_summary_path),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
        source="suite_summary",
        metrics={"status": suite.get("status"), "ok": suite.get("ok")},
    )
    evidence_bundle = collect_evidence_bundle_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )

    comparison_set_summary = None
    comparison_set = suite.get("comparison_set") if isinstance(suite.get("comparison_set"), dict) else {}
    comparison_set_summary = load_optional_json(
        comparison_set.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    reference_media_comparison = collect_reference_media_comparison_artifacts(
        suite=suite,
        comparison_set_summary=comparison_set_summary,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )

    reference_media_inventory = collect_reference_media_inventory_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    selected_media = collect_real_reference_media(
        suite=suite,
        comparison_set=comparison_set_summary,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    reference_capture_checklist = collect_reference_capture_checklist_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    visual_review = collect_visual_review_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    collect_comparison_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    real_projection_intake = collect_real_projection_intake_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    collect_ranked_candidate_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    collect_perception_fixture_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    sim_camera_pose_metadata_contract = collect_sim_camera_pose_fixture_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_model_source_inventory = collect_so101_model_source_inventory_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_model_bundle_manifest = collect_so101_model_bundle_manifest_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_model_contract = collect_so101_model_contract_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_model_asset_preflight = collect_so101_model_asset_preflight_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    ik_reachability = collect_ik_reachability_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    gripper_camera_pov = collect_gripper_camera_pov_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    app_entrypoint_metadata_contract = collect_app_entrypoint_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    release_metrics = collect_pick_place_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    collect_negative_check_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    collect_log_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )

    sorted_rows = sort_artifacts(artifacts)
    missing = [
        {
            "category": row["category"],
            "label": row["label"],
            "path": row["path"],
            "source": row["source"],
        }
        for row in sorted_rows
        if not row["exists"]
    ]
    categories = [
        {
            "category": category,
            "artifact_count": sum(1 for row in sorted_rows if row["category"] == category),
            "missing_count": sum(1 for row in sorted_rows if row["category"] == category and not row["exists"]),
        }
        for category in CATEGORY_ORDER
        if any(row["category"] == category for row in sorted_rows)
    ]

    return {
        "schema": SCHEMA,
        "ok": not missing,
        "status": "ok" if not missing else "validation_failed",
        "artifact_index_path": str(output_json),
        "suite_summary_path": str(suite_summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(repo_root) if repo_root else None,
        "hardware_skipped": suite.get("hardware_skipped"),
        "gui_skipped": suite.get("gui_skipped"),
        "openai_skipped": suite.get("openai_skipped"),
        "skipped_markers": suite.get("skipped_markers"),
        "suite_status": {
            "ok": suite.get("ok"),
            "status": suite.get("status"),
            "aggregate_status": suite.get("aggregate_status"),
        },
        "reference_media_manifest": suite.get("reference_media_manifest"),
        "evidence_bundle": evidence_bundle,
        "reference_media_inventory": reference_media_inventory,
        "reference_media_comparison": reference_media_comparison,
        "selected_real_reference_media": selected_media,
        "reference_capture_checklist": reference_capture_checklist,
        "real_projection_intake": real_projection_intake,
        "visual_review": visual_review,
        "sim_camera_pose_fixture_metadata_contract": sim_camera_pose_metadata_contract,
        "so101_model_source_inventory": so101_model_source_inventory,
        "so101_model_bundle_manifest": so101_model_bundle_manifest,
        "so101_model_contract": so101_model_contract,
        "so101_model_asset_preflight": so101_model_asset_preflight,
        "ik_reachability": ik_reachability,
        "gripper_camera_pov": gripper_camera_pov,
        "app_entrypoint_metadata_contract": app_entrypoint_metadata_contract,
        "pick_place_release_frame_count": sum(
            1 for row in sorted_rows if row["category"] == "pick_place_scenario" and row.get("scenario_id")
        ),
        "pick_place_target_release_open_metrics": release_metrics,
        "categories": categories,
        "artifacts": sorted_rows,
        "missing_artifacts": missing,
        "notes": [
            "This index validates existing suite artifacts only; it does not rerun smokes or touch hardware.",
            "relative_path is populated for artifacts under output_dir; repo_relative_path is populated for repository inputs.",
        ],
    }


def failure_index(output_json: Path, suite_summary_path: Path, error: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "validation_failed",
        "artifact_index_path": str(output_json),
        "suite_summary_path": str(suite_summary_path.expanduser().resolve()),
        "output_dir": None,
        "hardware_skipped": None,
        "gui_skipped": None,
        "openai_skipped": None,
        "error": error,
        "categories": [],
        "artifacts": [],
        "missing_artifacts": [
            {
                "category": "logs",
                "label": "suite:summary",
                "path": str(suite_summary_path.expanduser().resolve()),
                "source": "suite_summary",
                "reason": error,
            }
        ],
    }


def main() -> int:
    args = parse_args()
    suite_summary_path = args.suite_summary.expanduser().resolve()
    output_json = (
        args.output_json.expanduser().resolve()
        if args.output_json
        else suite_summary_path.parent / "artifact_index.json"
    )
    try:
        index = build_index(suite_summary_path, output_json)
    except ValueError as exc:
        index = failure_index(output_json, suite_summary_path, str(exc))
    write_json(output_json, index)
    print(json.dumps(index, indent=2))
    if not index["ok"]:
        print(f"ERROR: artifact index status={index['status']}; wrote {output_json}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
