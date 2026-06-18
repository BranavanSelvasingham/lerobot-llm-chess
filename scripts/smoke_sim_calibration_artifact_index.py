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


def collect_reference_camera_tuning_diagnostics_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    diagnostics = suite.get("reference_camera_tuning_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    child_summary = load_optional_json(
        diagnostics.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    child_summary = child_summary if isinstance(child_summary, dict) else {}
    source = child_summary if child_summary else diagnostics
    artifact_paths = source.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        artifact_paths = source.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    scorecard = source.get("scorecard")
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    gaps = source.get("reference_gap_carry_through")
    gaps = gaps if isinstance(gaps, dict) else {}
    external = source.get("external_local_evidence_only")
    external = external if isinstance(external, dict) else {}
    suggestions = source.get("suggested_tuning_dimensions")
    suggestions = suggestions if isinstance(suggestions, list) else []
    suggestion_names = [
        suggestion.get("dimension")
        for suggestion in suggestions
        if isinstance(suggestion, dict) and suggestion.get("dimension")
    ]
    paths = {
        "summary_json": source.get("summary_path") or artifact_paths.get("summary_json"),
        "csv_rows": source.get("csv_path") or artifact_paths.get("csv_rows"),
        "readme_md": source.get("readme_path") or artifact_paths.get("readme_md"),
        "scorecard_png": (
            source.get("scorecard_path")
            or artifact_paths.get("scorecard_png")
            or scorecard.get("path")
            if scorecard.get("produced") is True
            else None
        ),
    }
    metrics = {
        "status": source.get("status"),
        "ok": source.get("ok"),
        "comparison_set_status": source.get("comparison_set_status"),
        "selected_comparison_count": source.get("selected_comparison_count"),
        "visual_comparison_count": source.get("visual_comparison_count"),
        "metadata_only_count": source.get("metadata_only_count"),
        "suggested_tuning_dimensions": suggestion_names,
        "scorecard_status": source.get("scorecard_status") or scorecard.get("status"),
        "scorecard_produced": source.get("scorecard_produced")
        if source.get("scorecard_produced") is not None
        else scorecard.get("produced"),
        "scorecard_path": source.get("scorecard_path") or paths.get("scorecard_png"),
        "media_assets_copied_into_repo": source.get("media_assets_copied_into_repo", False),
        "external_selected_count": source.get(
            "external_selected_count",
            external.get("external_selected_count"),
        ),
        "external_selected_paths": source.get(
            "external_selected_paths",
            external.get("external_selected_paths"),
        ),
        "absolute_sibling_paths_are_local_evidence_only": source.get(
            "absolute_sibling_paths_are_local_evidence_only",
            external.get("absolute_sibling_paths_are_local_evidence_only"),
        ),
        "missing_depth_reference": source.get(
            "missing_depth_reference",
            gaps.get("missing_depth_reference"),
        ),
        "missing_pick_place_video": source.get(
            "missing_pick_place_video",
            gaps.get("missing_pick_place_video"),
        ),
        "no_videos": source.get("no_videos", gaps.get("no_videos")),
        "videos_present": source.get("videos_present", gaps.get("videos_present")),
        "reference_gaps": source.get("reference_gaps", gaps.get("reference_gaps")),
        "render_dependencies": source.get("render_dependencies"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("csv_rows", "rows"),
        ("readme_md", "readme"),
        ("scorecard_png", "scorecard"),
    ):
        add_path(
            artifacts,
            category="reference_camera_tuning_diagnostics",
            label=f"reference_camera_tuning_diagnostics:{label_suffix}",
            value=paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"reference_camera_tuning_diagnostics.artifact_paths.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": paths.get("summary_json"),
        "csv_path": paths.get("csv_rows"),
        "readme_path": paths.get("readme_md"),
        "scorecard_path": metrics.get("scorecard_path"),
        "artifact_paths": paths,
        "external_local_evidence_only": external,
        "reference_gap_carry_through": gaps,
        "suggested_tuning_dimensions": suggestions,
        "suggested_tuning_dimension_names": suggestion_names,
        "input": source.get("input"),
        "limits": source.get("limits"),
    }


def collect_sim_camera_profile_sweep_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    sweep = suite.get("sim_camera_profile_sweep")
    sweep = sweep if isinstance(sweep, dict) else {}
    artifact_paths = sweep.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    current_vs_best = sweep.get("current_vs_best_metrics")
    current_vs_best = current_vs_best if isinstance(current_vs_best, dict) else {}
    metrics = {
        "status": sweep.get("status"),
        "ok": sweep.get("ok"),
        "profile_name": sweep.get("profile_name"),
        "current_gripper_finger_width_px": sweep.get("current_gripper_finger_width_px"),
        "marker_time_seconds": sweep.get("marker_time_seconds"),
        "candidate_count": sweep.get("candidate_count"),
        "current_mean_abs_delta": sweep.get(
            "current_mean_abs_delta",
            current_vs_best.get("current_mean_abs_delta"),
        ),
        "current_rmse": sweep.get("current_rmse", current_vs_best.get("current_rmse")),
        "best_candidate_id": sweep.get("best_candidate_id"),
        "best_candidate_name": sweep.get("best_candidate_name"),
        "best_mean_abs_delta": sweep.get(
            "best_mean_abs_delta",
            current_vs_best.get("best_mean_abs_delta"),
        ),
        "best_rmse": sweep.get("best_rmse", current_vs_best.get("best_rmse")),
        "mean_abs_delta_delta_vs_current": sweep.get(
            "mean_abs_delta_delta_vs_current",
            current_vs_best.get("mean_abs_delta_delta_vs_current"),
        ),
        "rmse_delta_vs_current": sweep.get(
            "rmse_delta_vs_current",
            current_vs_best.get("rmse_delta_vs_current"),
        ),
        "full_frame_image_delta_caveat": sweep.get("full_frame_image_delta_caveat"),
        "remaining_tuning_prompt_count": len(sweep.get("remaining_tuning_prompts") or []),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("candidate_montage_jpg", "candidate_montage"),
        ("candidate_dir", "candidate_dir"),
        ("current_overlay_jpg", "current_overlay"),
        ("current_absolute_difference_jpg", "current_absolute_difference"),
        ("current_side_by_side_jpg", "current_side_by_side"),
        ("best_overlay_jpg", "best_overlay"),
        ("best_absolute_difference_jpg", "best_absolute_difference"),
        ("best_side_by_side_jpg", "best_side_by_side"),
    ):
        add_path(
            artifacts,
            category="sim_camera_profile_sweep",
            label=f"sim_camera_profile_sweep:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"sim_camera_profile_sweep.artifact_paths.{key}",
            metrics=metrics,
        )

    ranking = sweep.get("candidate_ranking")
    ranking_rows = ranking if isinstance(ranking, list) else []
    for row in ranking_rows:
        if not isinstance(row, dict):
            continue
        candidate_id = row.get("candidate_id")
        candidate_id = candidate_id if isinstance(candidate_id, str) else None
        rank = row.get("rank") if isinstance(row.get("rank"), int) else None
        row_artifacts = row.get("artifact_paths")
        row_artifacts = row_artifacts if isinstance(row_artifacts, dict) else {}
        candidate_metrics = {
            **metrics,
            "candidate_id": candidate_id,
            "candidate_name": row.get("candidate_name"),
            "candidate_description": row.get("description"),
            "candidate_mean_abs_delta": row.get("mean_abs_delta"),
            "candidate_rmse": row.get("rmse"),
            "candidate_mean_abs_delta_delta_vs_current": row.get(
                "mean_abs_delta_delta_vs_current"
            ),
            "candidate_rmse_delta_vs_current": row.get("rmse_delta_vs_current"),
        }
        for key, label_suffix in (("frame_path", "frame"), ("annotated_path", "annotated")):
            add_path(
                artifacts,
                category="sim_camera_profile_sweep",
                label=f"sim_camera_profile_sweep:{candidate_id}:{label_suffix}",
                value=row_artifacts.get(key),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"sim_camera_profile_sweep.candidate_ranking.{key}",
                metrics=candidate_metrics,
                rank=rank,
                candidate_id=candidate_id,
            )

    return {
        **metrics,
        "summary_path": artifact_paths.get("summary_json") or sweep.get("summary_path"),
        "candidate_montage_path": artifact_paths.get("candidate_montage_jpg"),
        "candidate_dir": artifact_paths.get("candidate_dir"),
        "artifact_paths": artifact_paths,
        "candidate_ranking": ranking_rows,
        "remaining_tuning_prompts": sweep.get("remaining_tuning_prompts"),
        "current_vs_best_metrics": current_vs_best,
    }


def sim_camera_tuning_before_after_metric(
    source: dict[str, Any],
    direct_key: str,
    delta_key: str | None = None,
    metric_key: str | None = None,
) -> Any:
    if direct_key in source:
        return source.get(direct_key)
    if delta_key is None or metric_key is None:
        return None
    deltas = source.get("deltas")
    deltas = deltas if isinstance(deltas, dict) else {}
    row = deltas.get(delta_key)
    row = row if isinstance(row, dict) else {}
    return row.get(metric_key)


def sim_camera_tuning_sweep_artifacts(source: dict[str, Any], role: str) -> dict[str, Any]:
    paths = source.get("artifact_paths")
    paths = paths if isinstance(paths, dict) else {}
    sweeps = paths.get("sweeps")
    sweeps = sweeps if isinstance(sweeps, dict) else {}
    role_paths = sweeps.get(role)
    if isinstance(role_paths, dict) and role_paths:
        return role_paths

    raw_sweeps = source.get("sweeps")
    raw_sweeps = raw_sweeps if isinstance(raw_sweeps, dict) else {}
    sweep = raw_sweeps.get(role)
    sweep = sweep if isinstance(sweep, dict) else {}
    artifacts = sweep.get("artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def sim_camera_tuning_before_after_metrics(source: dict[str, Any]) -> dict[str, Any]:
    gaps = source.get("open_reference_gaps")
    gaps = gaps if isinstance(gaps, dict) else {}
    prompts = source.get("remaining_tuning_prompts")
    prompts = prompts if isinstance(prompts, list) else []
    return {
        "status": source.get("status"),
        "ok": source.get("ok"),
        "profile_name": source.get("profile_name") or source.get("profile"),
        "baseline_gripper_finger_width_px": source.get("baseline_gripper_finger_width_px"),
        "current_gripper_finger_width_px": source.get("current_gripper_finger_width_px"),
        "marker_time_seconds": source.get("marker_time_seconds"),
        "baseline_candidate_count": source.get("baseline_candidate_count"),
        "current_candidate_count": source.get("current_candidate_count"),
        "baseline_current_mean_abs_delta": source.get("baseline_current_mean_abs_delta"),
        "baseline_current_rmse": source.get("baseline_current_rmse"),
        "current_profile_mean_abs_delta": source.get("current_profile_mean_abs_delta"),
        "current_profile_rmse": source.get("current_profile_rmse"),
        "baseline_best_candidate": source.get("baseline_best_candidate"),
        "current_best_candidate": source.get("current_best_candidate"),
        "baseline_best_mean_abs_delta": source.get("baseline_best_mean_abs_delta"),
        "baseline_best_rmse": source.get("baseline_best_rmse"),
        "current_best_mean_abs_delta": source.get("current_best_mean_abs_delta"),
        "current_best_rmse": source.get("current_best_rmse"),
        "current_vs_baseline_mean_abs_delta": sim_camera_tuning_before_after_metric(
            source,
            "current_vs_baseline_mean_abs_delta",
            "current_profile_delta_vs_baseline_current_candidate",
            "mean_abs_delta",
        ),
        "current_vs_baseline_rmse": sim_camera_tuning_before_after_metric(
            source,
            "current_vs_baseline_rmse",
            "current_profile_delta_vs_baseline_current_candidate",
            "rmse",
        ),
        "best_vs_baseline_best_mean_abs_delta": sim_camera_tuning_before_after_metric(
            source,
            "best_vs_baseline_best_mean_abs_delta",
            "current_best_delta_vs_baseline_best_candidate",
            "mean_abs_delta",
        ),
        "best_vs_baseline_best_rmse": sim_camera_tuning_before_after_metric(
            source,
            "best_vs_baseline_best_rmse",
            "current_best_delta_vs_baseline_best_candidate",
            "rmse",
        ),
        "best_vs_baseline_current_mean_abs_delta": sim_camera_tuning_before_after_metric(
            source,
            "best_vs_baseline_current_mean_abs_delta",
            "current_best_delta_vs_baseline_current_candidate",
            "mean_abs_delta",
        ),
        "best_vs_baseline_current_rmse": sim_camera_tuning_before_after_metric(
            source,
            "best_vs_baseline_current_rmse",
            "current_best_delta_vs_baseline_current_candidate",
            "rmse",
        ),
        "remaining_tuning_prompt_count": source.get(
            "remaining_tuning_prompt_count",
            len(prompts),
        ),
        "remaining_tuning_prompt_ids": source.get("remaining_tuning_prompt_ids"),
        "media_assets_copied_into_repo": source.get("media_assets_copied_into_repo", False),
        "missing_real_depth_reference": source.get(
            "missing_real_depth_reference",
            gaps.get("missing_real_depth_reference"),
        ),
        "missing_pick_place_video": source.get(
            "missing_pick_place_video",
            gaps.get("missing_pick_place_video"),
        ),
        "full_frame_image_delta_caveat": source.get("full_frame_image_delta_caveat"),
    }


def collect_sim_camera_tuning_before_after_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    tuning = suite.get("simcamera_tuning_before_after")
    tuning = tuning if isinstance(tuning, dict) else {}
    child_summary = load_optional_json(
        tuning.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    child_summary = child_summary if isinstance(child_summary, dict) else {}
    source = tuning if tuning else child_summary
    artifact_paths = source.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    if not artifact_paths:
        child_artifacts = child_summary.get("artifacts")
        child_artifacts = child_artifacts if isinstance(child_artifacts, dict) else {}
        artifact_paths = {
            "summary_json": source.get("summary_path") or child_artifacts.get("summary_path"),
            "csv_rows": source.get("csv_path") or child_artifacts.get("csv_path"),
            "readme_md": source.get("readme_path") or child_artifacts.get("readme_path"),
            "baseline_profile_sweep_dir": child_artifacts.get("baseline_profile_sweep_dir"),
            "current_profile_sweep_dir": child_artifacts.get("current_profile_sweep_dir"),
        }
    metrics = sim_camera_tuning_before_after_metrics(source)

    for key, label_suffix in (
        ("summary_json", "summary"),
        ("csv_rows", "rows"),
        ("readme_md", "readme"),
        ("baseline_profile_sweep_dir", "baseline_profile_sweep_dir"),
        ("current_profile_sweep_dir", "current_profile_sweep_dir"),
    ):
        add_path(
            artifacts,
            category="sim_camera_tuning_before_after",
            label=f"sim_camera_tuning_before_after:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"simcamera_tuning_before_after.artifact_paths.{key}",
            metrics=metrics,
        )

    child_key_map = {
        "summary_path": "summary",
        "candidate_montage_path": "candidate_montage",
        "candidate_dir": "candidate_dir",
        "current_overlay_path": "current_overlay",
        "current_absolute_difference_path": "current_absolute_difference",
        "current_side_by_side_path": "current_side_by_side",
        "best_overlay_path": "best_overlay",
        "best_absolute_difference_path": "best_absolute_difference",
        "best_side_by_side_path": "best_side_by_side",
    }
    for role in ("baseline", "current"):
        role_artifacts = sim_camera_tuning_sweep_artifacts(source, role)
        for key, label_suffix in child_key_map.items():
            add_path(
                artifacts,
                category="sim_camera_tuning_before_after",
                label=f"sim_camera_tuning_before_after:{role}:{label_suffix}",
                value=role_artifacts.get(key),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"simcamera_tuning_before_after.sweeps.{role}.artifacts.{key}",
                metrics={**metrics, "sweep_role": role},
            )

    return {
        **metrics,
        "summary_path": artifact_paths.get("summary_json") or source.get("summary_path"),
        "csv_path": artifact_paths.get("csv_rows") or source.get("csv_path"),
        "readme_path": artifact_paths.get("readme_md") or source.get("readme_path"),
        "artifact_paths": artifact_paths,
        "sweep_artifact_paths": {
            role: sim_camera_tuning_sweep_artifacts(source, role)
            for role in ("baseline", "current")
        },
        "deltas": source.get("deltas"),
        "remaining_tuning_prompts": source.get("remaining_tuning_prompts"),
        "open_reference_gaps": source.get("open_reference_gaps"),
        "caveats": source.get("caveats"),
    }


def reference_capture_manifest_path_counts(source: dict[str, Any]) -> dict[str, int]:
    path_checks = source.get("path_checks")
    path_checks = [row for row in path_checks if isinstance(row, dict)] if isinstance(path_checks, list) else []
    missing_path_checks = source.get("missing_path_checks")
    missing_path_checks = (
        [row for row in missing_path_checks if isinstance(row, dict)]
        if isinstance(missing_path_checks, list)
        else []
    )
    media_count = sum(1 for row in path_checks if row.get("category") == "media")
    sidecar_count = sum(1 for row in path_checks if row.get("category") == "sidecar")
    return {
        "path_check_count": len(path_checks),
        "media_path_check_count": media_count,
        "sidecar_path_check_count": sidecar_count,
        "missing_path_count": len(missing_path_checks),
        "present_path_count": len(path_checks) - len(missing_path_checks),
    }


def collect_reference_capture_manifest_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    manifest = suite.get("reference_capture_manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    child_summary = load_optional_json(
        manifest.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    child_summary = child_summary if isinstance(child_summary, dict) else {}
    source = child_summary if child_summary else manifest
    artifact_paths = manifest.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    diagnostics = source.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    path_counts = reference_capture_manifest_path_counts(source)
    paths = {
        "summary_json": source.get("summary_path")
        or manifest.get("summary_path")
        or artifact_paths.get("summary_json"),
        "csv": source.get("csv_path") or manifest.get("csv_path") or artifact_paths.get("csv"),
        "readme_md": source.get("readme_path")
        or manifest.get("readme_path")
        or artifact_paths.get("readme_md"),
    }
    metrics = {
        "status": source.get("status"),
        "ok": source.get("ok"),
        "manifest_path": source.get("manifest_path"),
        "manifest_schema": source.get("manifest_schema"),
        "ready_for_calibration_grade_simcamera_tuning": source.get(
            "ready_for_calibration_grade_simcamera_tuning"
        ),
        "depth_reference_capture_count": source.get("depth_reference_capture_count", 0),
        "pick_place_video_capture_count": source.get("pick_place_video_capture_count", 0),
        "diagnostics": diagnostics,
        "gaps": diagnostics,
        "media_assets_copied_into_repo": source.get("media_assets_copied_into_repo", False),
        "provenance_present": source.get("provenance_present"),
        "review_present": source.get("review_present"),
        **path_counts,
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("csv", "checklist"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="reference_capture_manifest",
            label=f"reference_capture_manifest:{label_suffix}",
            value=paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"reference_capture_manifest.artifact_paths.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": paths.get("summary_json"),
        "csv_path": paths.get("csv"),
        "readme_path": paths.get("readme_md"),
        "artifact_paths": paths,
        "source_configuration": manifest.get("source_configuration"),
        "local_only_no_copy_policy": source.get("local_only_no_copy_policy"),
        "path_checks": source.get("path_checks") if isinstance(source.get("path_checks"), list) else [],
        "missing_path_checks": (
            source.get("missing_path_checks")
            if isinstance(source.get("missing_path_checks"), list)
            else []
        ),
        "notes": source.get("notes"),
    }


def int_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def unique_string_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def next_required_action_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[Any] = []
    for item in value:
        if isinstance(item, dict):
            labels.append(item.get("action_id"))
        else:
            labels.append(item)
    return unique_string_values(labels)


def real_depth_capture_plan_case_metrics(
    case: dict[str, Any],
    aggregate_metrics: dict[str, Any],
) -> dict[str, Any]:
    next_action_ids = (
        case.get("next_operator_action_ids")
        if isinstance(case.get("next_operator_action_ids"), list)
        else []
    )
    return {
        **aggregate_metrics,
        "case_id": case.get("case_id"),
        "scenario_label": case.get("scenario_label"),
        "evidence_source_kind": case.get("evidence_source_kind"),
        "evidence_status": case.get("evidence_status"),
        "ready_for_calibration_grade_simcamera_tuning": case.get(
            "ready_for_calibration_grade_simcamera_tuning"
        ),
        "case_depth_reference_capture_count": int_count(
            case.get("depth_reference_capture_count")
        ),
        "case_pick_place_video_capture_count": int_count(
            case.get("pick_place_video_capture_count")
        ),
        "case_missing_path_count": int_count(case.get("missing_path_count")),
        "no_copy_status": case.get("no_copy_status"),
        "case_next_operator_action_count": len(next_action_ids),
        "case_next_operator_action_ids": next_action_ids,
        "planner_json_path": case.get("planner_json_path"),
        "planner_markdown_path": case.get("planner_markdown_path"),
    }


def collect_real_depth_capture_plan_artifact_index_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    plan_index = suite.get("real_depth_capture_plan_artifact_index")
    plan_index = plan_index if isinstance(plan_index, dict) else {}
    child_summary = load_optional_json(
        plan_index.get("summary_path"),
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    child_summary = child_summary if isinstance(child_summary, dict) else {}
    source = child_summary if child_summary else plan_index
    artifact_paths = plan_index.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    cases = source.get("cases")
    cases = [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    evidence_statuses = unique_string_values([case.get("evidence_status") for case in cases])
    no_copy_statuses = unique_string_values([case.get("no_copy_status") for case in cases])
    next_operator_action_ids = unique_string_values(
        [
            action_id
            for case in cases
            for action_id in (
                case.get("next_operator_action_ids")
                if isinstance(case.get("next_operator_action_ids"), list)
                else []
            )
        ]
    )
    ready_case_ids = [
        str(case.get("case_id"))
        for case in cases
        if case.get("ready_for_calibration_grade_simcamera_tuning") is True and case.get("case_id")
    ]
    not_ready_case_ids = [
        str(case.get("case_id"))
        for case in cases
        if case.get("ready_for_calibration_grade_simcamera_tuning") is not True
        and case.get("case_id")
    ]
    paths = {
        "summary_json": source.get("artifact_index_path")
        or source.get("summary_path")
        or plan_index.get("summary_path")
        or artifact_paths.get("summary_json"),
        "csv": source.get("csv_path") or plan_index.get("csv_path") or artifact_paths.get("csv"),
        "readme_md": source.get("readme_path")
        or plan_index.get("readme_path")
        or artifact_paths.get("readme_md"),
        "bridge_smoke_summary_json": source.get("bridge_smoke_summary_json")
        or plan_index.get("bridge_smoke_summary_json"),
    }
    caveats = unique_string_values(
        [
            *(
                source.get("caveats")
                if isinstance(source.get("caveats"), list)
                else []
            ),
            *(
                plan_index.get("caveats")
                if isinstance(plan_index.get("caveats"), list)
                else []
            ),
        ]
    )
    bridge_smoke = source.get("bridge_smoke")
    bridge_smoke = bridge_smoke if isinstance(bridge_smoke, dict) else {}
    aggregate_metrics = {
        "status": source.get("status"),
        "ok": source.get("ok"),
        "source_mode": source.get("source_mode"),
        "case_count": int_count(source.get("case_count", len(cases))),
        "evidence_statuses": evidence_statuses,
        "ready_case_count": len(ready_case_ids),
        "not_ready_case_count": len(not_ready_case_ids),
        "ready_case_ids": ready_case_ids,
        "not_ready_case_ids": not_ready_case_ids,
        "depth_reference_capture_count": sum(
            int_count(case.get("depth_reference_capture_count")) for case in cases
        ),
        "pick_place_video_capture_count": sum(
            int_count(case.get("pick_place_video_capture_count")) for case in cases
        ),
        "missing_path_count": sum(int_count(case.get("missing_path_count")) for case in cases),
        "no_copy_statuses": no_copy_statuses,
        "next_operator_action_count": len(next_operator_action_ids),
        "next_operator_action_ids": next_operator_action_ids,
        "bridge_smoke_summary_json": paths.get("bridge_smoke_summary_json"),
        "bridge_smoke_status": bridge_smoke.get("status"),
        "media_assets_copied_into_repo": source.get("media_assets_copied_into_repo", False),
        "media_assets_opened_or_decoded": source.get("media_assets_opened_or_decoded", False),
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "caveats": caveats,
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("csv", "cases"),
        ("readme_md", "readme"),
        ("bridge_smoke_summary_json", "bridge_smoke_summary"),
    ):
        add_path(
            artifacts,
            category="real_depth_capture_plan_artifact_index",
            label=f"real_depth_capture_plan_artifact_index:{label_suffix}",
            value=paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"real_depth_capture_plan_artifact_index.artifact_paths.{key}",
            metrics=aggregate_metrics,
        )
    for case in cases:
        case_id = str(case.get("case_id") or "unknown_case")
        case_metrics = real_depth_capture_plan_case_metrics(case, aggregate_metrics)
        for key, label_suffix in (
            ("planner_json_path", "planner_json"),
            ("planner_markdown_path", "planner_markdown"),
        ):
            add_path(
                artifacts,
                category="real_depth_capture_plan_artifact_index",
                label=f"real_depth_capture_plan_artifact_index:{case_id}:{label_suffix}",
                value=case.get(key),
                suite_summary_path=suite_summary_path,
                output_dir=output_dir,
                repo_root=repo_root,
                source=f"real_depth_capture_plan_artifact_index.cases.{case_id}.{key}",
                metrics=case_metrics,
            )
    return {
        **aggregate_metrics,
        "summary_path": paths.get("summary_json"),
        "csv_path": paths.get("csv"),
        "readme_path": paths.get("readme_md"),
        "artifact_paths": paths,
        "bridge_smoke": bridge_smoke,
        "cases": cases,
        "case_summaries": plan_index.get("case_summaries"),
        "notes": source.get("notes") or plan_index.get("notes"),
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


def collect_so101_mujoco_smoke_artifacts(
    *,
    suite: dict[str, Any],
    suite_key: str,
    category: str,
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    smoke = suite.get(suite_key)
    smoke = smoke if isinstance(smoke, dict) else {}
    artifact_paths = smoke.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    dependencies = smoke.get("dependencies")
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    next_required = smoke.get("next_required_for_goal")
    next_required = next_required if isinstance(next_required, list) else []
    next_required_action_ids = next_required_action_labels(next_required)
    metrics = {
        "status": smoke.get("status"),
        "ok": smoke.get("ok"),
        "model_authority": smoke.get("model_authority"),
        "physical_so101_model_authority_ready": smoke.get("physical_so101_model_authority_ready"),
        "hardware_free_regression_fixture_ready": smoke.get("hardware_free_regression_fixture_ready"),
        "ready_for_model_backed_ik": smoke.get("ready_for_model_backed_ik"),
        "contact_model": smoke.get("contact_model"),
        "reviewed_model_motion_checked": smoke.get("reviewed_model_motion_checked"),
        "motion_authority_status": smoke.get("motion_authority_status"),
        "physical_reviewed_model_motion_checked": smoke.get("physical_reviewed_model_motion_checked"),
        "hardware_free_fixture_motion_checked": smoke.get("hardware_free_fixture_motion_checked"),
        "motion_evidence_not_physical_so101_authority": smoke.get("motion_evidence_not_physical_so101_authority"),
        "motion_authority": smoke.get("motion_authority"),
        "manifest_status": smoke.get("manifest_status"),
        "missing_inputs": smoke.get("missing_inputs"),
        "gymnasium_available": dependencies.get("gymnasium"),
        "mujoco_available": dependencies.get("mujoco"),
        "reset_count": smoke.get("reset_count"),
        "all_resets_ok": smoke.get("all_resets_ok"),
        "all_mujoco_fallback_free": smoke.get("all_mujoco_fallback_free"),
        "all_piece_resets_ok": smoke.get("all_piece_resets_ok"),
        "all_board_contacts_observed": smoke.get("all_board_contacts_observed"),
        "probe_count": smoke.get("probe_count"),
        "gripper_contact_observed": smoke.get("gripper_contact_observed"),
        "two_finger_contact_observed": smoke.get("two_finger_contact_observed"),
        "settled_gripper_contact_observed": smoke.get("settled_gripper_contact_observed"),
        "source_square": smoke.get("source_square"),
        "source_pick_started_at_source": smoke.get("source_pick_started_at_source"),
        "close_two_finger_contact_observed": smoke.get("close_two_finger_contact_observed"),
        "lift_verified": smoke.get("lift_verified"),
        "lift_without_manual_piece_pose_m": smoke.get("lift_without_manual_piece_pose_m"),
        "board_contact_cleared_during_lift": smoke.get("board_contact_cleared_during_lift"),
        "transfer_verified": smoke.get("transfer_verified"),
        "transfer_xy_m": smoke.get("transfer_xy_m"),
        "transfer_target_xy_error_m": smoke.get("transfer_target_xy_error_m"),
        "transfer_source_to_target_progress_m": smoke.get("transfer_source_to_target_progress_m"),
        "lift_place_physics_verified": smoke.get("lift_place_physics_verified"),
        "board_source_pick_place_verified": smoke.get("board_source_pick_place_verified"),
        "release_contact_cleared": smoke.get("release_contact_cleared"),
        "release_contact_cleared_after_retreat": smoke.get("release_contact_cleared_after_retreat"),
        "final_board_contact_observed": smoke.get("final_board_contact_observed"),
        "final_target_xy_error_m": smoke.get("final_target_xy_error_m"),
        "target_xy_tolerance_m": smoke.get("target_xy_tolerance_m"),
        "target_square": smoke.get("target_square"),
        "manual_piece_pose_used_after_fixture": smoke.get("manual_piece_pose_used_after_fixture"),
        "manual_piece_pose_used_after_reset": smoke.get("manual_piece_pose_used_after_reset"),
        "robot_pose_seeded_for_source_fixture": smoke.get("robot_pose_seeded_for_source_fixture"),
        "source_to_target_progress_m": smoke.get("source_to_target_progress_m"),
        "episode_count": smoke.get("episode_count"),
        "transition_count": smoke.get("transition_count"),
        "all_scripted_pick_place_complete": smoke.get("all_scripted_pick_place_complete"),
        "all_mujoco_piece_release_synced": smoke.get("all_mujoco_piece_release_synced"),
        "next_required_for_goal": next_required,
        "next_required_action_ids": next_required_action_ids,
    }
    for key, value in sorted(artifact_paths.items()):
        add_path(
            artifacts,
            category=category,
            label=f"{category}:{key}",
            value=value,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"{suite_key}.artifacts.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": artifact_paths.get("summary_json") or smoke.get("summary_path"),
        "artifact_paths": artifact_paths,
        "limitations": smoke.get("limitations"),
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
    joint_limits = bundle.get("joint_limits")
    joint_limits = joint_limits if isinstance(joint_limits, dict) else {}
    mesh_assets = bundle.get("mesh_assets")
    mesh_assets = mesh_assets if isinstance(mesh_assets, dict) else {}
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
    next_required = bundle.get("next_required_for_goal")
    next_required = [action for action in next_required if isinstance(action, dict)] if isinstance(next_required, list) else []
    next_required_action_ids = unique_string_values([action.get("action_id") for action in next_required])
    metrics = {
        "status": bundle.get("status"),
        "ok": bundle.get("ok"),
        "manifest_request_status": manifest_request.get("status"),
        "manifest_path": manifest_request.get("path"),
        "ready_for_model_backed_ik": bundle.get("ready_for_model_backed_ik"),
        "model_authority": bundle.get("model_authority"),
        "physical_authority_gate_status": bundle.get("physical_authority_gate_status"),
        "physical_so101_model_authority_ready": bundle.get("physical_so101_model_authority_ready"),
        "physical_authority_blockers": bundle.get("physical_authority_blockers"),
        "hardware_free_regression_fixture_ready": bundle.get("hardware_free_regression_fixture_ready"),
        "synthetic_fixture_authority_fields": bundle.get("synthetic_fixture_authority_fields"),
        "review_packet_status": bundle.get("review_packet_status"),
        "review_packet_model_authority": bundle.get("review_packet_model_authority"),
        "review_packet_item_count": bundle.get("review_packet_item_count"),
        "review_packet_item_ids": bundle.get("review_packet_item_ids"),
        "review_packet_needs_operator_review_item_ids": bundle.get(
            "review_packet_needs_operator_review_item_ids"
        ),
        "review_packet_action_ids": bundle.get("review_packet_action_ids"),
        "review_packet_observed_evidence_is_authority": bundle.get(
            "review_packet_observed_evidence_is_authority"
        ),
        "review_packet_development_fixture_evidence_not_physical_so101_truth": bundle.get(
            "review_packet_development_fixture_evidence_not_physical_so101_truth"
        ),
        "next_required_for_goal": next_required,
        "next_required_action_ids": next_required_action_ids,
        "next_required_action_count": len(next_required),
        "model_path_status": model_path.get("status"),
        "model_path": model_path.get("path"),
        "asset_root_status": asset_roots.get("status"),
        "asset_roots": asset_roots.get("asset_roots"),
        "joint_limits_status": joint_limits.get("status"),
        "joint_limits_missing_joints": joint_limits.get("missing_joints"),
        "joint_limits_invalid_joints": joint_limits.get("invalid_joints"),
        "mesh_assets_status": mesh_assets.get("status"),
        "mesh_assets_mesh_reference_count": mesh_assets.get("mesh_reference_count"),
        "mesh_assets_missing_asset_count": mesh_assets.get("missing_asset_count"),
        "mesh_assets_unresolved_reference_count": mesh_assets.get("unresolved_reference_count"),
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
        ("review_packet_json", "review_packet"),
        ("review_packet_csv", "review_packet_rows"),
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
        "review_packet_json_path": artifact_paths.get("review_packet_json"),
        "review_packet_csv_path": artifact_paths.get("review_packet_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "manifest_request": manifest_request,
        "ready_for_model_backed_ik": bundle.get("ready_for_model_backed_ik"),
        "model_path": model_path,
        "asset_roots": asset_roots,
        "joint_limits": joint_limits,
        "mesh_assets": mesh_assets,
        "target_frame": target_frame,
        "tcp_offset": tcp_offset,
        "base_to_board_alignment": alignment,
        "contract_checker": contract,
        "model_asset_preflight": asset_preflight,
        "missing_inputs": bundle.get("missing_inputs"),
        "next_required_for_goal": next_required,
        "next_required_action_ids": next_required_action_ids,
        "next_required_action_count": len(next_required),
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
        "source_authority_review_status": inventory.get("source_authority_review_status"),
        "source_authority_review_ready": inventory.get("source_authority_review_ready"),
        "source_authority_review": inventory.get("source_authority_review"),
        "source_authority_gate_status": inventory.get("source_authority_gate_status"),
        "source_authority_blockers": inventory.get("source_authority_blockers") or [],
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
        "next_required_for_goal": inventory.get("next_required_for_goal") or [],
        "next_required_action_ids": inventory.get("next_required_action_ids") or [],
        "next_required_action_count": len(inventory.get("next_required_for_goal") or []),
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
        "source_authority_review_status": inventory.get("source_authority_review_status"),
        "source_authority_review_ready": inventory.get("source_authority_review_ready"),
        "source_authority_review": inventory.get("source_authority_review"),
        "source_authority_gate_status": metrics["source_authority_gate_status"],
        "source_authority_blockers": metrics["source_authority_blockers"],
        "source_configuration": source_configuration,
        "recommended_contract_check_path": metrics["recommended_contract_check_path"],
        "recommended_contract_check": recommended_contract_check or None,
        "next_required_for_goal": inventory.get("next_required_for_goal") or [],
        "next_required_action_ids": inventory.get("next_required_action_ids") or [],
        "next_required_action_count": metrics["next_required_action_count"],
        "diagnostics": inventory.get("diagnostics"),
    }


def collect_so101_reviewed_model_authority_gate_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    gate = suite.get("so101_reviewed_model_authority_gate")
    gate = gate if isinstance(gate, dict) else {}
    artifact_paths = gate.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    metrics = {
        "status": gate.get("status"),
        "ok": gate.get("ok"),
        "ready": gate.get("ready"),
        "review_status": gate.get("review_status"),
        "source_authority_ready": gate.get("source_authority_ready"),
        "source_authority_gate_status": gate.get("source_authority_gate_status"),
        "physical_so101_model_authority_ready": gate.get(
            "physical_so101_model_authority_ready"
        ),
        "physical_authority_gate_status": gate.get("physical_authority_gate_status"),
        "physical_reviewed_model_motion_checked": gate.get(
            "physical_reviewed_model_motion_checked"
        ),
        "reviewed_mujoco_bundle_status": gate.get("reviewed_mujoco_bundle_status"),
        "development_fixture_evidence_not_physical_so101_truth": gate.get(
            "development_fixture_evidence_not_physical_so101_truth"
        ),
        "blockers": gate.get("blockers") or [],
        "blocker_count": gate.get("blocker_count"),
        "source_inventory_summary_path": gate.get("source_inventory_summary_path"),
        "bundle_manifest_summary_path": gate.get("bundle_manifest_summary_path"),
        "reviewed_mujoco_bundle_summary_path": gate.get(
            "reviewed_mujoco_bundle_summary_path"
        ),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("checklist_csv", "checklist"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="so101_reviewed_model_authority_gate",
            label=f"so101_reviewed_model_authority_gate:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_reviewed_model_authority_gate.artifacts.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": artifact_paths.get("summary_json") or gate.get("summary_path"),
        "checklist_csv_path": artifact_paths.get("checklist_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "artifact_paths": artifact_paths,
    }


def collect_so101_training_readiness_gate_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    gate = suite.get("so101_training_readiness_gate")
    gate = gate if isinstance(gate, dict) else {}
    artifact_paths = gate.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    metrics = {
        "status": gate.get("status"),
        "ok": gate.get("ok"),
        "ready": gate.get("ready"),
        "reviewed_model_authority_ready": gate.get("reviewed_model_authority_ready"),
        "reviewed_model_authority_status": gate.get("reviewed_model_authority_status"),
        "reviewed_model_backed_board_source_pick_place": gate.get(
            "reviewed_model_backed_board_source_pick_place"
        ),
        "board_pick_status": gate.get("board_pick_status"),
        "board_pick_model_authority": gate.get("board_pick_model_authority"),
        "board_pick_ready_for_model_backed_ik": gate.get(
            "board_pick_ready_for_model_backed_ik"
        ),
        "board_pick_robot_pose_seeded_for_source_fixture": gate.get(
            "board_pick_robot_pose_seeded_for_source_fixture"
        ),
        "board_pick_manual_piece_pose_used_after_reset": gate.get(
            "board_pick_manual_piece_pose_used_after_reset"
        ),
        "rollout_ready_for_policy_training": gate.get("rollout_ready_for_policy_training"),
        "rollout_training_authority_status": gate.get("rollout_training_authority_status"),
        "rollout_model_authority": gate.get("rollout_model_authority"),
        "rollout_use": gate.get("rollout_use"),
        "development_fixture_evidence_not_policy_training_truth": gate.get(
            "development_fixture_evidence_not_policy_training_truth"
        ),
        "blockers": gate.get("blockers") or [],
        "blocker_count": gate.get("blocker_count"),
        "reviewed_model_authority_gate_summary_path": gate.get(
            "reviewed_model_authority_gate_summary_path"
        ),
        "board_pick_summary_path": gate.get("board_pick_summary_path"),
        "training_rollouts_summary_path": gate.get("training_rollouts_summary_path"),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("checklist_csv", "checklist"),
        ("readme_md", "readme"),
    ):
        add_path(
            artifacts,
            category="so101_training_readiness_gate",
            label=f"so101_training_readiness_gate:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_training_readiness_gate.artifacts.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": artifact_paths.get("summary_json") or gate.get("summary_path"),
        "checklist_csv_path": artifact_paths.get("checklist_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "artifact_paths": artifact_paths,
    }


def collect_so101_model_bundle_probe_artifacts(
    *,
    suite: dict[str, Any],
    artifacts: list[dict[str, Any]],
    suite_summary_path: Path,
    output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    probe = suite.get("so101_model_bundle_probe")
    probe = probe if isinstance(probe, dict) else {}
    artifact_paths = probe.get("artifacts")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    metrics = {
        "status": probe.get("status"),
        "ok": probe.get("ok"),
        "model_authority": probe.get("model_authority"),
        "selected_model_path": probe.get("selected_model_path"),
        "model_request_status": probe.get("model_request_status"),
        "contract_status": probe.get("contract_status"),
        "asset_preflight_status": probe.get("asset_preflight_status"),
        "asset_preflight_mesh_reference_count": probe.get("asset_preflight_mesh_reference_count"),
        "asset_preflight_present_asset_count": probe.get("asset_preflight_present_asset_count"),
        "asset_preflight_missing_asset_count": probe.get("asset_preflight_missing_asset_count"),
        "asset_preflight_unresolved_reference_count": probe.get(
            "asset_preflight_unresolved_reference_count"
        ),
        "observed_source_hints_status": probe.get("observed_source_hints_status"),
        "observed_source_hints_export_tool_hints": probe.get(
            "observed_source_hints_export_tool_hints"
        ),
        "observed_source_hints_license_status": probe.get("observed_source_hints_license_status"),
        "observed_joint_limits_status": probe.get("observed_joint_limits_status"),
        "observed_joint_limits_complete": probe.get("observed_joint_limits_complete"),
        "observed_joint_limits_missing_joints": probe.get("observed_joint_limits_missing_joints"),
        "mesh_asset_review_status": probe.get("mesh_asset_review_status"),
        "mesh_asset_review_unique_missing_reference_count": probe.get(
            "mesh_asset_review_unique_missing_reference_count"
        ),
        "mesh_asset_review_unique_unresolved_reference_count": probe.get(
            "mesh_asset_review_unique_unresolved_reference_count"
        ),
        "manifest_status": probe.get("manifest_status"),
        "ready_for_model_backed_ik": probe.get("ready_for_model_backed_ik"),
        "missing_inputs": probe.get("missing_inputs"),
        "review_packet_status": probe.get("review_packet_status"),
        "review_packet_model_authority": probe.get("review_packet_model_authority"),
        "review_packet_item_count": probe.get("review_packet_item_count"),
        "review_packet_item_ids": probe.get("review_packet_item_ids"),
        "review_packet_observed_evidence_is_authority": probe.get(
            "review_packet_observed_evidence_is_authority"
        ),
        "review_packet_development_fixture_evidence_not_physical_so101_truth": probe.get(
            "review_packet_development_fixture_evidence_not_physical_so101_truth"
        ),
        "next_required_for_goal": probe.get("next_required_for_goal"),
        "next_required_action_ids": probe.get("next_required_action_ids"),
        "next_required_action_count": len(probe.get("next_required_for_goal") or []),
    }
    for key, label_suffix in (
        ("summary_json", "summary"),
        ("candidate_manifest_json", "candidate_manifest"),
        ("review_packet_json", "review_packet"),
        ("review_packet_csv", "review_packet_rows"),
        ("checklist_csv", "checklist"),
        ("readme_md", "readme"),
        ("contract_summary_json", "child_contract_summary"),
        ("contract_checklist_csv", "child_contract_checklist"),
        ("manifest_check_summary_json", "child_manifest_summary"),
        ("manifest_checklist_csv", "child_manifest_checklist"),
    ):
        add_path(
            artifacts,
            category="so101_model_bundle_probe",
            label=f"so101_model_bundle_probe:{label_suffix}",
            value=artifact_paths.get(key),
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source=f"so101_model_bundle_probe.artifacts.{key}",
            metrics=metrics,
        )
    return {
        **metrics,
        "summary_path": artifact_paths.get("summary_json") or probe.get("summary_path"),
        "candidate_manifest_path": artifact_paths.get("candidate_manifest_json"),
        "review_packet_json_path": artifact_paths.get("review_packet_json"),
        "review_packet_csv_path": artifact_paths.get("review_packet_csv"),
        "checklist_csv_path": artifact_paths.get("checklist_csv"),
        "readme_md_path": artifact_paths.get("readme_md"),
        "contract_summary_path": artifact_paths.get("contract_summary_json"),
        "manifest_check_summary_path": artifact_paths.get("manifest_check_summary_json"),
        "artifact_paths": artifact_paths,
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
    reference_camera_tuning_diagnostics = collect_reference_camera_tuning_diagnostics_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    sim_camera_profile_sweep = collect_sim_camera_profile_sweep_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    sim_camera_tuning_before_after = collect_sim_camera_tuning_before_after_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    reference_capture_manifest = collect_reference_capture_manifest_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    real_depth_capture_plan_artifact_index = (
        collect_real_depth_capture_plan_artifact_index_artifacts(
            suite=suite,
            artifacts=artifacts,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
        )
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
    so101_reviewed_model_authority_gate = (
        collect_so101_reviewed_model_authority_gate_artifacts(
            suite=suite,
            artifacts=artifacts,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
        )
    )
    so101_model_bundle_probe = collect_so101_model_bundle_probe_artifacts(
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
    so101_reviewed_mujoco_bundle = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_reviewed_mujoco_bundle",
        category="so101_reviewed_mujoco_bundle",
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
    so101_mujoco_scene = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_mujoco_scene",
        category="so101_mujoco_scene",
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_chess_env = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_chess_env",
        category="so101_chess_env",
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_env_resets = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_env_resets",
        category="so101_env_resets",
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_mujoco_contact_probe = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_mujoco_contact_probe",
        category="so101_mujoco_contact_probe",
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_mujoco_grasp_probe = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_mujoco_grasp_probe",
        category="so101_mujoco_grasp_probe",
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_mujoco_board_pick_probe = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_mujoco_board_pick_probe",
        category="so101_mujoco_board_pick_probe",
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_training_readiness_gate = collect_so101_training_readiness_gate_artifacts(
        suite=suite,
        artifacts=artifacts,
        suite_summary_path=suite_summary_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    so101_training_rollouts = collect_so101_mujoco_smoke_artifacts(
        suite=suite,
        suite_key="so101_training_rollouts",
        category="so101_training_rollouts",
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
        "reference_camera_tuning_diagnostics": reference_camera_tuning_diagnostics,
        "sim_camera_profile_sweep": sim_camera_profile_sweep,
        "sim_camera_tuning_before_after": sim_camera_tuning_before_after,
        "reference_capture_manifest": reference_capture_manifest,
        "real_depth_capture_plan_artifact_index": real_depth_capture_plan_artifact_index,
        "selected_real_reference_media": selected_media,
        "reference_capture_checklist": reference_capture_checklist,
        "real_projection_intake": real_projection_intake,
        "visual_review": visual_review,
        "sim_camera_pose_fixture_metadata_contract": sim_camera_pose_metadata_contract,
        "so101_model_source_inventory": so101_model_source_inventory,
        "so101_reviewed_model_authority_gate": so101_reviewed_model_authority_gate,
        "so101_model_bundle_probe": so101_model_bundle_probe,
        "so101_model_bundle_manifest": so101_model_bundle_manifest,
        "so101_reviewed_mujoco_bundle": so101_reviewed_mujoco_bundle,
        "so101_model_contract": so101_model_contract,
        "so101_model_asset_preflight": so101_model_asset_preflight,
        "ik_reachability": ik_reachability,
        "so101_mujoco_scene": so101_mujoco_scene,
        "so101_chess_env": so101_chess_env,
        "so101_env_resets": so101_env_resets,
        "so101_mujoco_contact_probe": so101_mujoco_contact_probe,
        "so101_mujoco_grasp_probe": so101_mujoco_grasp_probe,
        "so101_mujoco_board_pick_probe": so101_mujoco_board_pick_probe,
        "so101_training_readiness_gate": so101_training_readiness_gate,
        "so101_training_rollouts": so101_training_rollouts,
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
