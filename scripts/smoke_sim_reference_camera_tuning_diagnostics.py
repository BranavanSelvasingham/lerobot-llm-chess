#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "reference_camera_tuning_diagnostics"
SUITE_SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
COMPARISON_SCHEMA = "lerobot.sim.reference_media_comparison_set.v1"
SCHEMA = "lerobot.sim.reference_camera_tuning_diagnostics.v1"
SUMMARY_NAME = "reference_camera_tuning_diagnostics.json"
CSV_NAME = "reference_camera_tuning_diagnostics.csv"
README_NAME = "README.md"
SCORECARD_NAME = "reference_camera_tuning_scorecard.png"
VISUAL_ARTIFACT_KEYS = (
    "side_by_side_path",
    "overlay_path",
    "absolute_difference_path",
    "absolute_difference_heatmap_path",
    "reference_annotated_path",
    "synthetic_annotated_path",
    "synthetic_path",
)


class DiagnosticsInputError(ValueError):
    """Raised when the diagnostics input cannot be interpreted."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize real/reference-vs-synthetic comparison artifacts into hardware-free "
            "camera tuning diagnostics without changing simulator constants."
        )
    )
    parser.add_argument(
        "--comparison-summary-json",
        type=Path,
        required=True,
        help="Path to comparison_set_summary.json or calibration_regression_summary.json.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--max-scorecard-rows",
        type=int,
        default=4,
        help="Maximum selected rows to include in the optional PNG scorecard.",
    )
    return parser.parse_args()


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise DiagnosticsInputError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise DiagnosticsInputError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DiagnosticsInputError(f"{label} {path} must contain a JSON object.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def resolve_path(value: Any, *, base_dir: Path) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def path_exists(value: Any, *, base_dir: Path) -> bool:
    path = resolve_path(value, base_dir=base_dir)
    return bool(path and path.is_file())


def artifact_path_map(comparison: dict[str, Any], *, base_dir: Path) -> dict[str, dict[str, Any]]:
    details = comparison.get("comparison") if isinstance(comparison.get("comparison"), dict) else {}
    child = details.get("child_artifact_paths") if isinstance(details.get("child_artifact_paths"), dict) else {}
    visual = details.get("visual_artifact_paths") if isinstance(details.get("visual_artifact_paths"), dict) else {}
    artifacts: dict[str, dict[str, Any]] = {}
    for key in sorted(set(child) | set(visual)):
        value = visual.get(key, child.get(key))
        if not isinstance(value, str) or not value:
            continue
        path = resolve_path(value, base_dir=base_dir)
        artifacts[key] = {
            "path": str(path) if path else value,
            "exists": bool(path and path.is_file()),
        }
    return artifacts


def load_comparison_payload(input_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = read_json_object(input_path, label="comparison summary")
    input_path = input_path.resolve()
    schema = payload.get("schema")
    if schema == COMPARISON_SCHEMA or "selected_candidates" in payload or "comparisons" in payload:
        return payload, {
            "input_path": str(input_path),
            "input_schema": schema,
            "source_kind": "comparison_set_summary",
            "comparison_set_summary_path": str(input_path),
            "loaded_child_summary": False,
        }
    if schema == SUITE_SCHEMA or "comparison_set" in payload:
        comparison_section = payload.get("comparison_set")
        if not isinstance(comparison_section, dict):
            comparison_section = {}
        summary_path = (
            comparison_section.get("summary_path")
            or comparison_section.get("comparison_set_summary_path")
            or (comparison_section.get("artifact_paths") or {}).get("summary_json")
        )
        child_path = resolve_path(summary_path, base_dir=input_path.parent)
        if child_path and child_path.is_file():
            child = read_json_object(child_path, label="comparison set summary")
            return child, {
                "input_path": str(input_path),
                "input_schema": schema,
                "source_kind": "calibration_regression_summary",
                "comparison_set_summary_path": str(child_path),
                "loaded_child_summary": True,
                "suite_comparison_status": comparison_section.get("status"),
            }
        if comparison_section:
            return comparison_section, {
                "input_path": str(input_path),
                "input_schema": schema,
                "source_kind": "calibration_regression_summary_embedded_comparison_set",
                "comparison_set_summary_path": str(child_path) if child_path else None,
                "loaded_child_summary": False,
                "suite_comparison_status": comparison_section.get("status"),
            }
        return {}, {
            "input_path": str(input_path),
            "input_schema": schema,
            "source_kind": "calibration_regression_summary_no_comparison_set",
            "comparison_set_summary_path": str(child_path) if child_path else None,
            "loaded_child_summary": False,
        }
    raise DiagnosticsInputError(
        f"{input_path} is neither a comparison_set_summary.json nor a calibration_regression_summary.json."
    )


def board_alignment_signals(comparison: dict[str, Any]) -> dict[str, Any]:
    corners = comparison.get("board_corners") if isinstance(comparison.get("board_corners"), dict) else {}
    points = corners.get("corners_xy")
    dimensions = comparison.get("dimensions") if isinstance(comparison.get("dimensions"), dict) else {}
    synthetic = dimensions.get("synthetic") if isinstance(dimensions.get("synthetic"), dict) else {}
    reference = dimensions.get("reference") if isinstance(dimensions.get("reference"), dict) else {}
    width = as_int(synthetic.get("width")) or as_int(reference.get("width"))
    height = as_int(synthetic.get("height")) or as_int(reference.get("height"))
    signal: dict[str, Any] = {
        "corner_labels": corners.get("corner_labels"),
        "corner_checks": corners.get("corner_checks"),
        "corners_present": isinstance(points, list) and len(points) == 4,
    }
    if not signal["corners_present"]:
        signal["diagnostic_status"] = "missing_board_corner_signals"
        return signal

    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        if (
            isinstance(point, list)
            and len(point) >= 2
            and as_float(point[0]) is not None
            and as_float(point[1]) is not None
        ):
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if len(xs) != 4 or len(ys) != 4:
        signal["diagnostic_status"] = "invalid_board_corner_signals"
        return signal

    bbox = {
        "x_min": min(xs),
        "y_min": min(ys),
        "x_max": max(xs),
        "y_max": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }
    signal["bounding_box_px"] = bbox
    if width and height:
        signal["image_width"] = width
        signal["image_height"] = height
        signal["coverage_x"] = bbox["width"] / float(width)
        signal["coverage_y"] = bbox["height"] / float(height)
        signal["margin_left_px"] = bbox["x_min"]
        signal["margin_right_px"] = float(width) - bbox["x_max"]
        signal["margin_top_px"] = bbox["y_min"]
        signal["margin_bottom_px"] = float(height) - bbox["y_max"]
    signal["diagnostic_status"] = "ok"
    return signal


def gripper_signals(comparison: dict[str, Any]) -> dict[str, Any]:
    gripper = comparison.get("gripper") if isinstance(comparison.get("gripper"), dict) else {}
    metadata = comparison.get("camera_metadata") if isinstance(comparison.get("camera_metadata"), dict) else {}
    signal = {
        "visible": gripper.get("visible"),
        "requested_percent": gripper.get("requested_percent"),
        "track_robot_gripper": gripper.get("track_robot_gripper"),
        "tracked_gripper_percent": gripper.get("tracked_gripper_percent"),
        "current_gripper_opening_px": gripper.get("current_gripper_opening_px"),
        "metadata_gripper_visible": metadata.get("gripper_visible"),
        "metadata_current_gripper_opening_px": metadata.get("current_gripper_opening_px"),
    }
    signal["diagnostic_status"] = "ok" if any(value is not None for value in signal.values()) else "missing_gripper_signals"
    return signal


def visual_availability(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    present = {
        key: artifacts.get(key, {"path": None, "exists": False})
        for key in VISUAL_ARTIFACT_KEYS
        if key in artifacts
    }
    return {
        "available_keys": [key for key, value in present.items() if value.get("exists")],
        "missing_keys": [key for key in VISUAL_ARTIFACT_KEYS if key not in present or not present[key].get("exists")],
        "artifacts": present,
        "has_side_by_side": bool(present.get("side_by_side_path", {}).get("exists")),
        "has_overlay": bool(present.get("overlay_path", {}).get("exists")),
        "has_absolute_difference_heatmap": bool(
            present.get("absolute_difference_path", {}).get("exists")
            or present.get("absolute_difference_heatmap_path", {}).get("exists")
        ),
        "has_annotated_reference": bool(present.get("reference_annotated_path", {}).get("exists")),
        "has_annotated_synthetic": bool(present.get("synthetic_annotated_path", {}).get("exists")),
    }


def image_metric_status(image_metrics: dict[str, Any]) -> str:
    if as_float(image_metrics.get("mean_abs_delta")) is not None or as_float(image_metrics.get("rmse")) is not None:
        return "ok"
    return "metadata_only_metrics_absent"


def tuning_suggestions(row: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = row["image_metrics"]
    board = row["board_alignment_signals"]
    gripper = row["gripper_signals"]
    gaps = row["reference_gap_carry_through"]
    suggestions: list[dict[str, Any]] = []
    mean_abs_delta = as_float(metrics.get("mean_abs_delta"))
    rmse = as_float(metrics.get("rmse"))
    coverage_x = as_float(board.get("coverage_x"))
    coverage_y = as_float(board.get("coverage_y"))
    gripper_visible = gripper.get("visible") if gripper.get("visible") is not None else gripper.get("metadata_gripper_visible")
    opening = as_float(gripper.get("current_gripper_opening_px")) or as_float(
        gripper.get("metadata_current_gripper_opening_px")
    )

    if coverage_x is not None or coverage_y is not None:
        suggestions.append(
            {
                "dimension": "camera_framing_board_scale_board_crop",
                "reason": "Projected board-corner bounding box is available for review against the real/reference framing.",
                "signals": {
                    "coverage_x": coverage_x,
                    "coverage_y": coverage_y,
                    "bbox_px": board.get("bounding_box_px"),
                    "margins_px": {
                        "left": board.get("margin_left_px"),
                        "right": board.get("margin_right_px"),
                        "top": board.get("margin_top_px"),
                        "bottom": board.get("margin_bottom_px"),
                    },
                },
                "automatic_change": False,
            }
        )
    else:
        suggestions.append(
            {
                "dimension": "camera_framing_board_scale_board_crop",
                "reason": "Board-corner metrics are absent; review visual artifacts or add corner detection sidecars before tuning pose/framing.",
                "signals": {"status": board.get("diagnostic_status")},
                "automatic_change": False,
            }
        )

    suggestions.append(
        {
            "dimension": "board_color_texture_lighting",
            "reason": (
                "Pixel deltas are available for appearance review."
                if mean_abs_delta is not None or rmse is not None
                else "Pixel deltas are absent; this row is metadata-only for appearance."
            ),
            "signals": {
                "mean_abs_delta": mean_abs_delta,
                "rmse": rmse,
                "mean_abs_delta_bgr": metrics.get("mean_abs_delta_bgr"),
                "rmse_bgr": metrics.get("rmse_bgr"),
            },
            "automatic_change": False,
        }
    )

    suggestions.append(
        {
            "dimension": "gripper_overlay_geometry_occlusion",
            "reason": (
                "Synthetic gripper visibility/opening metadata is present for occlusion review."
                if gripper.get("diagnostic_status") == "ok"
                else "Gripper metadata is absent; visual occlusion review is metadata-only."
            ),
            "signals": {
                "visible": gripper_visible,
                "opening_px": opening,
                "track_robot_gripper": gripper.get("track_robot_gripper"),
                "tracked_percent": gripper.get("tracked_gripper_percent"),
            },
            "automatic_change": False,
        }
    )

    suggestions.append(
        {
            "dimension": "piece_size_contrast",
            "reason": (
                "Piece-square center metadata is available for size/contrast review."
                if isinstance(row.get("piece_square"), dict)
                else "Piece-square center metadata is absent; this row is metadata-only for piece size/contrast."
            ),
            "signals": row.get("piece_square"),
            "automatic_change": False,
        }
    )

    if gaps.get("missing_depth_reference") or gaps.get("missing_pick_place_video") or gaps.get("no_videos"):
        suggestions.append(
            {
                "dimension": "missing_depth_video_capture_needs",
                "reason": "Reference gaps are preserved; synthetic comparison evidence does not close real depth or pick/place-video gaps.",
                "signals": gaps,
                "automatic_change": False,
            }
        )
    return suggestions


def selected_by_relative_path(comparison_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    selected = comparison_set.get("selected_candidates")
    selected = selected if isinstance(selected, list) else []
    records: dict[str, dict[str, Any]] = {}
    for item in selected:
        if not isinstance(item, dict):
            continue
        key = str(item.get("relative_path") or item.get("path") or item.get("selection_rank") or "")
        if key:
            records[key] = item
    return records


def build_rows(comparison_set: dict[str, Any], *, base_dir: Path) -> list[dict[str, Any]]:
    diagnostics = comparison_set.get("diagnostics") if isinstance(comparison_set.get("diagnostics"), dict) else {}
    reference_gaps = normalize_string_list(diagnostics.get("reference_gaps"))
    comparisons = comparison_set.get("comparisons")
    comparisons = comparisons if isinstance(comparisons, list) else []
    selected_lookup = selected_by_relative_path(comparison_set)
    rows: list[dict[str, Any]] = []

    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        key = str(comparison.get("relative_path") or comparison.get("reference_image_path") or comparison.get("selection_rank") or "")
        selected = selected_lookup.get(str(comparison.get("relative_path") or ""), {})
        artifacts = artifact_path_map(comparison, base_dir=base_dir)
        image_metrics = comparison.get("image_metrics") if isinstance(comparison.get("image_metrics"), dict) else {}
        dimensions = comparison.get("dimensions") if isinstance(comparison.get("dimensions"), dict) else {}
        row = {
            "selection_rank": comparison.get("selection_rank"),
            "relative_path": comparison.get("relative_path"),
            "reference_image_path": comparison.get("reference_image_path") or selected.get("path"),
            "path_scope": comparison.get("path_scope") or selected.get("path_scope"),
            "media_type": selected.get("media_type", "image"),
            "reference_classes": normalize_string_list(comparison.get("reference_classes") or selected.get("reference_classes")),
            "reference_tags": normalize_string_list(comparison.get("reference_tags") or selected.get("reference_tags")),
            "selection_reasons": normalize_string_list(comparison.get("selection_reasons") or selected.get("selection_reasons")),
            "comparison_ok": comparison.get("ok"),
            "comparison_summary_path": (
                (comparison.get("comparison") or {}).get("summary_path")
                if isinstance(comparison.get("comparison"), dict)
                else None
            ),
            "visual_comparison_availability": visual_availability(artifacts),
            "dimensions": dimensions,
            "image_metrics": image_metrics,
            "image_metric_status": image_metric_status(image_metrics),
            "board_alignment_signals": board_alignment_signals(comparison),
            "gripper_signals": gripper_signals(comparison),
            "piece_square": comparison.get("piece_square"),
            "camera_metadata_scope": (
                comparison.get("camera_metadata", {}).get("calibration_metadata_scope")
                if isinstance(comparison.get("camera_metadata"), dict)
                else None
            ),
            "reference_gap_carry_through": {
                "reference_gaps": reference_gaps,
                "missing_depth_reference": diagnostics.get("missing_depth_reference"),
                "missing_pick_place_video": diagnostics.get("missing_pick_place_video"),
                "no_videos": diagnostics.get("no_videos"),
            },
            "external_local_evidence_only": comparison.get("path_scope") == "external",
            "media_assets_copied_into_repo": False,
        }
        row["suggested_tuning_dimensions"] = tuning_suggestions(row)
        rows.append(row)
        selected_lookup.pop(str(comparison.get("relative_path") or ""), None)

    for selected in sorted(
        selected_lookup.values(),
        key=lambda item: (
            as_int(item.get("selection_rank")) if as_int(item.get("selection_rank")) is not None else 9999,
            str(item.get("relative_path") or item.get("path") or ""),
        ),
    ):
        row = {
            "selection_rank": selected.get("selection_rank"),
            "relative_path": selected.get("relative_path"),
            "reference_image_path": selected.get("path"),
            "path_scope": selected.get("path_scope"),
            "media_type": selected.get("media_type"),
            "reference_classes": normalize_string_list(selected.get("reference_classes")),
            "reference_tags": normalize_string_list(selected.get("reference_tags")),
            "selection_reasons": normalize_string_list(selected.get("selection_reasons")),
            "comparison_ok": None,
            "comparison_summary_path": None,
            "visual_comparison_availability": visual_availability({}),
            "dimensions": {"reference": selected.get("dimensions") if isinstance(selected.get("dimensions"), dict) else {}},
            "image_metrics": {},
            "image_metric_status": "metadata_only_no_visual_comparison",
            "board_alignment_signals": {"diagnostic_status": "missing_board_corner_signals", "corners_present": False},
            "gripper_signals": {"diagnostic_status": "missing_gripper_signals"},
            "piece_square": None,
            "camera_metadata_scope": None,
            "reference_gap_carry_through": {
                "reference_gaps": reference_gaps,
                "missing_depth_reference": diagnostics.get("missing_depth_reference"),
                "missing_pick_place_video": diagnostics.get("missing_pick_place_video"),
                "no_videos": diagnostics.get("no_videos"),
            },
            "external_local_evidence_only": selected.get("path_scope") == "external",
            "media_assets_copied_into_repo": False,
        }
        row["suggested_tuning_dimensions"] = tuning_suggestions(row)
        rows.append(row)

    rows.sort(
        key=lambda item: (
            as_int(item.get("selection_rank")) if as_int(item.get("selection_rank")) is not None else 9999,
            str(item.get("relative_path") or item.get("reference_image_path") or ""),
        )
    )
    return rows


def overall_status(rows: list[dict[str, Any]], comparison_set: dict[str, Any]) -> str:
    if not rows:
        return "no_reference_media_selected"
    if any(row.get("image_metric_status") == "ok" for row in rows):
        return "ok"
    if comparison_set.get("status") == "no_reference_media_selected":
        return "no_reference_media_selected"
    return "metadata_only"


def aggregate_suggestions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_dimension: dict[str, dict[str, Any]] = {}
    for row in rows:
        for suggestion in row.get("suggested_tuning_dimensions", []):
            if not isinstance(suggestion, dict):
                continue
            dimension = str(suggestion.get("dimension") or "")
            if not dimension:
                continue
            record = by_dimension.setdefault(
                dimension,
                {
                    "dimension": dimension,
                    "row_count": 0,
                    "example_reasons": [],
                    "automatic_change": False,
                },
            )
            record["row_count"] += 1
            reason = str(suggestion.get("reason") or "")
            if reason and reason not in record["example_reasons"]:
                record["example_reasons"].append(reason)
    return [by_dimension[key] for key in sorted(by_dimension)]


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "selection_rank",
        "relative_path",
        "reference_image_path",
        "path_scope",
        "media_type",
        "comparison_ok",
        "image_metric_status",
        "mean_abs_delta",
        "rmse",
        "reference_width",
        "reference_height",
        "synthetic_width",
        "synthetic_height",
        "board_coverage_x",
        "board_coverage_y",
        "gripper_visible",
        "gripper_opening_px",
        "side_by_side_path",
        "overlay_path",
        "absolute_difference_path",
        "missing_depth_reference",
        "missing_pick_place_video",
        "no_videos",
        "external_local_evidence_only",
        "media_assets_copied_into_repo",
        "suggested_tuning_dimensions",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            dimensions = row.get("dimensions") if isinstance(row.get("dimensions"), dict) else {}
            reference = dimensions.get("reference") if isinstance(dimensions.get("reference"), dict) else {}
            synthetic = dimensions.get("synthetic") if isinstance(dimensions.get("synthetic"), dict) else {}
            metrics = row.get("image_metrics") if isinstance(row.get("image_metrics"), dict) else {}
            board = row.get("board_alignment_signals") if isinstance(row.get("board_alignment_signals"), dict) else {}
            gripper = row.get("gripper_signals") if isinstance(row.get("gripper_signals"), dict) else {}
            gaps = row.get("reference_gap_carry_through") if isinstance(row.get("reference_gap_carry_through"), dict) else {}
            visual = row.get("visual_comparison_availability") if isinstance(row.get("visual_comparison_availability"), dict) else {}
            artifacts = visual.get("artifacts") if isinstance(visual.get("artifacts"), dict) else {}
            writer.writerow(
                {
                    "selection_rank": row.get("selection_rank"),
                    "relative_path": row.get("relative_path"),
                    "reference_image_path": row.get("reference_image_path"),
                    "path_scope": row.get("path_scope"),
                    "media_type": row.get("media_type"),
                    "comparison_ok": row.get("comparison_ok"),
                    "image_metric_status": row.get("image_metric_status"),
                    "mean_abs_delta": metrics.get("mean_abs_delta"),
                    "rmse": metrics.get("rmse"),
                    "reference_width": reference.get("width"),
                    "reference_height": reference.get("height"),
                    "synthetic_width": synthetic.get("width"),
                    "synthetic_height": synthetic.get("height"),
                    "board_coverage_x": board.get("coverage_x"),
                    "board_coverage_y": board.get("coverage_y"),
                    "gripper_visible": gripper.get("visible") if gripper.get("visible") is not None else gripper.get("metadata_gripper_visible"),
                    "gripper_opening_px": gripper.get("current_gripper_opening_px") or gripper.get("metadata_current_gripper_opening_px"),
                    "side_by_side_path": artifacts.get("side_by_side_path", {}).get("path") if isinstance(artifacts.get("side_by_side_path"), dict) else None,
                    "overlay_path": artifacts.get("overlay_path", {}).get("path") if isinstance(artifacts.get("overlay_path"), dict) else None,
                    "absolute_difference_path": artifacts.get("absolute_difference_path", {}).get("path") if isinstance(artifacts.get("absolute_difference_path"), dict) else None,
                    "missing_depth_reference": gaps.get("missing_depth_reference"),
                    "missing_pick_place_video": gaps.get("missing_pick_place_video"),
                    "no_videos": gaps.get("no_videos"),
                    "external_local_evidence_only": row.get("external_local_evidence_only"),
                    "media_assets_copied_into_repo": row.get("media_assets_copied_into_repo"),
                    "suggested_tuning_dimensions": ";".join(
                        str(item.get("dimension"))
                        for item in row.get("suggested_tuning_dimensions", [])
                        if isinstance(item, dict) and item.get("dimension")
                    ),
                }
            )


def render_dependency_status() -> dict[str, Any]:
    missing: list[str] = []
    for module_name in ("cv2", "numpy"):
        try:
            __import__(module_name)
        except Exception as exc:
            missing.append(f"{module_name}: {exc}")
    return {"available": not missing, "status": "available" if not missing else "missing_render_dependency", "missing": missing}


def first_visual_path(row: dict[str, Any]) -> Path | None:
    visual = row.get("visual_comparison_availability") if isinstance(row.get("visual_comparison_availability"), dict) else {}
    artifacts = visual.get("artifacts") if isinstance(visual.get("artifacts"), dict) else {}
    for key in ("side_by_side_path", "overlay_path", "absolute_difference_path"):
        artifact = artifacts.get(key)
        if isinstance(artifact, dict) and artifact.get("exists") and isinstance(artifact.get("path"), str):
            return Path(str(artifact["path"]))
    return None


def write_scorecard(path: Path, rows: list[dict[str, Any]], *, max_rows: int) -> dict[str, Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        return {"produced": False, "status": "missing_render_dependency", "path": str(path), "error": str(exc)}

    selected_rows = rows[: max(0, int(max_rows))]
    if not selected_rows:
        return {"produced": False, "status": "no_selected_rows", "path": str(path)}

    width = 1200
    row_height = 260
    header_height = 86
    sheet = np.full((header_height + row_height * len(selected_rows), width, 3), 255, dtype=np.uint8)
    cv2.putText(sheet, "Reference Camera Tuning Diagnostics", (24, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(
        sheet,
        "Hardware-free evidence only: suggested tuning dimensions, not physical calibration truth",
        (24, 66),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (70, 70, 70),
        1,
        cv2.LINE_AA,
    )
    skipped: list[dict[str, str]] = []
    y = header_height
    for row in selected_rows:
        cv2.rectangle(sheet, (0, y), (width, y + row_height - 1), (245, 245, 245), -1)
        thumb_path = first_visual_path(row)
        if thumb_path is not None:
            image = cv2.imread(str(thumb_path), cv2.IMREAD_COLOR)
            if image is not None:
                max_thumb_w = 500
                max_thumb_h = row_height - 34
                scale = min(max_thumb_w / image.shape[1], max_thumb_h / image.shape[0], 1.0)
                thumb = cv2.resize(
                    image,
                    (max(1, int(round(image.shape[1] * scale))), max(1, int(round(image.shape[0] * scale)))),
                    interpolation=cv2.INTER_AREA,
                )
                sheet[y + 18 : y + 18 + thumb.shape[0], 24 : 24 + thumb.shape[1]] = thumb
            else:
                skipped.append({"relative_path": str(row.get("relative_path")), "reason": "visual_unreadable"})
        else:
            skipped.append({"relative_path": str(row.get("relative_path")), "reason": "visual_missing"})

        metrics = row.get("image_metrics") if isinstance(row.get("image_metrics"), dict) else {}
        board = row.get("board_alignment_signals") if isinstance(row.get("board_alignment_signals"), dict) else {}
        gripper = row.get("gripper_signals") if isinstance(row.get("gripper_signals"), dict) else {}
        gaps = row.get("reference_gap_carry_through") if isinstance(row.get("reference_gap_carry_through"), dict) else {}
        text_x = 550
        label = f"rank {row.get('selection_rank')}: {row.get('relative_path') or row.get('reference_image_path')}"
        if len(label) > 92:
            label = label[:89] + "..."
        lines = [
            label,
            f"status={row.get('image_metric_status')} mean_abs_delta={metrics.get('mean_abs_delta')} rmse={metrics.get('rmse')}",
            f"board_coverage=({board.get('coverage_x')}, {board.get('coverage_y')}) gripper_visible={gripper.get('visible')}",
            f"gaps depth={gaps.get('missing_depth_reference')} pick_place_video={gaps.get('missing_pick_place_video')} no_videos={gaps.get('no_videos')}",
            "suggest: camera framing, board appearance, gripper occlusion, piece contrast, capture gaps",
        ]
        for offset, line in enumerate(lines):
            cv2.putText(
                sheet,
                str(line),
                (text_x, y + 34 + offset * 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (20, 20, 20) if offset == 0 else (65, 65, 65),
                1,
                cv2.LINE_AA,
            )
        y += row_height

    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), sheet)
    return {
        "produced": bool(ok),
        "status": "ok" if ok else "write_failed",
        "path": str(path),
        "row_count": len(selected_rows),
        "skipped": skipped,
    }


def markdown_link(path: Any) -> str:
    if not isinstance(path, str) or not path:
        return "none"
    return f"`{path}`"


def write_readme(path: Path, *, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    diagnostics = summary.get("reference_gap_carry_through") if isinstance(summary.get("reference_gap_carry_through"), dict) else {}
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    lines = [
        "# Reference Camera Tuning Diagnostics",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Source kind: `{summary.get('input', {}).get('source_kind')}`",
        f"- Selected comparison rows: `{summary.get('selected_comparison_count')}`",
        f"- Metadata-only rows: `{summary.get('metadata_only_count')}`",
        f"- Media assets copied into repo: `{summary.get('media_assets_copied_into_repo')}`",
        f"- Missing depth reference: `{diagnostics.get('missing_depth_reference')}`",
        f"- Missing pick/place video: `{diagnostics.get('missing_pick_place_video')}`",
        f"- No videos: `{diagnostics.get('no_videos')}`",
        "",
        "## Artifacts",
        "",
        f"- JSON summary: {markdown_link(artifacts.get('summary_json'))}",
        f"- CSV rows: {markdown_link(artifacts.get('csv_rows'))}",
        f"- PNG scorecard: {markdown_link(artifacts.get('scorecard_png'))}",
        "",
        "## Suggested Tuning Dimensions",
        "",
    ]
    for suggestion in summary.get("suggested_tuning_dimensions", []):
        if not isinstance(suggestion, dict):
            continue
        lines.append(f"- `{suggestion.get('dimension')}`: rows `{suggestion.get('row_count')}`; automatic change `false`.")
    if not summary.get("suggested_tuning_dimensions"):
        lines.append("- None; no selected comparison rows were available.")

    lines.extend(
        [
            "",
            "## Selected Evidence Rows",
            "",
        ]
    )
    if not rows:
        lines.append("_No selected comparison rows were available. This is a non-failing no-selected diagnostic._")
    for row in rows:
        visual = row.get("visual_comparison_availability") if isinstance(row.get("visual_comparison_availability"), dict) else {}
        artifacts_map = visual.get("artifacts") if isinstance(visual.get("artifacts"), dict) else {}
        side_by_side = artifacts_map.get("side_by_side_path", {}).get("path") if isinstance(artifacts_map.get("side_by_side_path"), dict) else None
        overlay = artifacts_map.get("overlay_path", {}).get("path") if isinstance(artifacts_map.get("overlay_path"), dict) else None
        diff = artifacts_map.get("absolute_difference_path", {}).get("path") if isinstance(artifacts_map.get("absolute_difference_path"), dict) else None
        lines.extend(
            [
                f"### Rank {row.get('selection_rank')}: `{row.get('relative_path') or row.get('reference_image_path')}`",
                "",
                f"- Scope/classes: `{row.get('path_scope')}` / `{';'.join(row.get('reference_classes', []))}`",
                f"- Image metric status: `{row.get('image_metric_status')}`",
                f"- Side by side: {markdown_link(side_by_side)}",
                f"- Overlay: {markdown_link(overlay)}",
                f"- Absolute difference heatmap: {markdown_link(diff)}",
                "",
            ]
        )

    lines.extend(
        [
            "## Limits",
            "",
            "This report is hardware-free review evidence. It proposes tuning dimensions for future simulator camera pose, board appearance, and gripper occlusion work; it does not update constants, copy media assets, close missing depth/pick-place-video gaps, or claim physical calibration readiness.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def failure_summary(output_dir: Path, input_path: Path, error: str) -> dict[str, Any]:
    summary_path = output_dir / SUMMARY_NAME
    csv_path = output_dir / CSV_NAME
    readme_path = output_dir / README_NAME
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "validation_failed",
        "error": error,
        "input": {"input_path": str(input_path)},
        "selected_comparison_count": 0,
        "metadata_only_count": 0,
        "media_assets_copied_into_repo": False,
        "artifacts": {
            "summary_json": str(summary_path),
            "csv_rows": str(csv_path),
            "readme_md": str(readme_path),
            "scorecard_png": None,
        },
    }


def build_summary(args: argparse.Namespace, output_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    input_path = args.comparison_summary_json.expanduser().resolve()
    comparison_set, input_record = load_comparison_payload(input_path)
    comparison_base = Path(str(input_record.get("comparison_set_summary_path") or input_path)).parent
    rows = build_rows(comparison_set, base_dir=comparison_base)
    status = overall_status(rows, comparison_set)
    diagnostics = comparison_set.get("diagnostics") if isinstance(comparison_set.get("diagnostics"), dict) else {}
    summary_path = output_dir / SUMMARY_NAME
    csv_path = output_dir / CSV_NAME
    readme_path = output_dir / README_NAME
    scorecard_path = output_dir / SCORECARD_NAME
    scorecard = write_scorecard(scorecard_path, rows, max_rows=args.max_scorecard_rows)
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "input": input_record,
        "comparison_set_status": comparison_set.get("status"),
        "comparison_set_ok": comparison_set.get("ok"),
        "selected_comparison_count": len(rows),
        "visual_comparison_count": sum(
            1
            for row in rows
            if row.get("visual_comparison_availability", {}).get("has_side_by_side")
            or row.get("visual_comparison_availability", {}).get("has_overlay")
        ),
        "metadata_only_count": sum(1 for row in rows if row.get("image_metric_status") != "ok"),
        "media_assets_copied_into_repo": False,
        "reference_gap_carry_through": {
            "reference_gaps": normalize_string_list(diagnostics.get("reference_gaps")),
            "missing_depth_reference": diagnostics.get("missing_depth_reference"),
            "missing_pick_place_video": diagnostics.get("missing_pick_place_video"),
            "no_videos": diagnostics.get("no_videos"),
            "videos_present": diagnostics.get("videos_present"),
        },
        "external_local_evidence_only": {
            "absolute_sibling_paths_are_local_evidence_only": diagnostics.get(
                "absolute_sibling_paths_are_local_evidence_only", True
            ),
            "external_selected_count": diagnostics.get("external_selected_count"),
            "external_selected_paths": diagnostics.get("external_selected_paths"),
        },
        "render_dependencies": render_dependency_status(),
        "scorecard": scorecard,
        "selected_rows": rows,
        "suggested_tuning_dimensions": aggregate_suggestions(rows),
        "limits": [
            "Hardware-free diagnostics only; no robot, GUI calibration, camera runtime, OpenAI/LLM path, IK solver, renderer, or simulator constants are changed.",
            "Synthetic comparison evidence does not close missing real depth-reference or pick/place-video gaps.",
            "This is not physical calibration truth and does not claim readiness for hardware execution.",
        ],
        "artifacts": {
            "summary_json": str(summary_path),
            "csv_rows": str(csv_path),
            "readme_md": str(readme_path),
            "scorecard_png": str(scorecard_path) if scorecard.get("produced") else None,
        },
    }
    return summary, rows


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_NAME
    csv_path = output_dir / CSV_NAME
    readme_path = output_dir / README_NAME
    try:
        summary, rows = build_summary(args, output_dir)
    except DiagnosticsInputError as exc:
        summary = failure_summary(output_dir, args.comparison_summary_json.expanduser().resolve(), str(exc))
        rows = []
        write_json(summary_path, summary)
        write_rows_csv(csv_path, rows)
        write_readme(readme_path, summary=summary, rows=rows)
        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"ERROR: reference camera tuning diagnostics status={summary['status']}; wrote {summary_path}", file=sys.stderr)
        return 2

    write_json(summary_path, summary)
    write_rows_csv(csv_path, rows)
    write_readme(readme_path, summary=summary, rows=rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
