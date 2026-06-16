#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "reference_media_comparison_set"
DEFAULT_PROFILE = "current_gripper_reference"
SCHEMA = "lerobot.sim.reference_media_comparison_set.v1"
COMPARISON_ROWS_NAME = "reference_media_comparison_rows.csv"
CONTACT_SHEET_NAME = "reference_media_comparison_contact_sheet.png"
README_NAME = "README.md"
TARGET_REFERENCE_CLASSES = ("camera_pov", "chessboard_board", "gripper_arm")
ACTIVE_REFERENCE_TAG = "active_current_gripper_reference"
MEDIA_TYPE_RANK = {
    "image": 0,
    "video": 1,
    "calibration_data": 2,
}


class FixtureInputError(ValueError):
    """Raised when inventory input cannot produce a comparison fixture."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the simulator real-reference comparison smoke over useful image references "
            "selected from the reference-media inventory."
        )
    )
    parser.add_argument("--inventory-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--max-selected-candidates",
        type=int,
        default=3,
        help="Maximum ranked inventory candidates to keep as comparison evidence rows.",
    )
    parser.add_argument(
        "--max-visual-comparisons",
        type=int,
        default=1,
        help="Maximum selected image candidates to render through the synthetic side-by-side comparison.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Override the simulator camera profile for every selected image. When omitted, "
            "the first profile wired to each inventory entry is used, falling back to "
            f"{DEFAULT_PROFILE}."
        ),
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child inventory/comparison smoke scripts.",
    )
    parser.add_argument(
        "--inventory-script",
        type=Path,
        default=REPO_ROOT / "scripts" / "smoke_sim_reference_media_inventory.py",
    )
    parser.add_argument(
        "--comparison-script",
        type=Path,
        default=REPO_ROOT / "scripts" / "smoke_sim_real_reference_comparison.py",
    )
    return parser.parse_args()


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise FixtureInputError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise FixtureInputError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FixtureInputError(f"{label} {path} must contain a JSON object.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return slug or "reference"


def run_child(command: list[str], *, stdout_path: Path, stderr_path: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    return result


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def inventory_reference_gaps(inventory: dict[str, Any]) -> list[str]:
    gaps = inventory.get("reference_gaps")
    if isinstance(gaps, list):
        return [str(gap) for gap in gaps if isinstance(gap, str) and gap]
    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    summary_gaps = summary.get("reference_gaps")
    if not isinstance(summary_gaps, list):
        return []
    return [str(gap) for gap in summary_gaps if isinstance(gap, str) and gap]


def inventory_active_reference_path(inventory: dict[str, Any]) -> str:
    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    value = summary.get("active_current_gripper_reference_path")
    return str(value) if isinstance(value, str) and value else "archive/chess_test_images/current_view.jpg"


def is_synthetic_or_example_record(record: dict[str, Any]) -> bool:
    text = " ".join(
        str(value).lower()
        for value in (
            record.get("relative_path"),
            record.get("root_relative_path"),
            record.get("path"),
        )
    )
    return any(token in text for token in ("synthetic", ".example", "example_", "/test_data/", "test_data/"))


def reference_path_for_record(record: dict[str, Any], repo_root: Path) -> Path:
    path_value = record.get("path")
    if isinstance(path_value, str) and path_value:
        return Path(path_value).expanduser().resolve()
    relative_path = str(record["relative_path"])
    return (repo_root / relative_path).resolve()


def selection_score_components(
    record: dict[str, Any],
    *,
    inventory: dict[str, Any],
    recommended_inputs: set[str],
) -> dict[str, Any]:
    relative_path = str(record.get("relative_path") or "")
    classes = set(normalize_string_list(record.get("reference_classes")))
    tags = set(normalize_string_list(record.get("reference_tags"))) | set(normalize_string_list(record.get("inferred_tags")))
    manifest_validation = record.get("manifest_validation")
    manifest_validation = manifest_validation if isinstance(manifest_validation, dict) else {}
    target_class_hits = [class_name for class_name in TARGET_REFERENCE_CLASSES if class_name in classes]
    active_reference_path = inventory_active_reference_path(inventory)
    media_type = str(record.get("media_type") or "")
    path_scope = str(record.get("path_scope") or "")
    return {
        "active_current_gripper_reference": (
            relative_path == active_reference_path
            or ACTIVE_REFERENCE_TAG in tags
        ),
        "has_camera_board_gripper_class_set": set(TARGET_REFERENCE_CLASSES) <= classes,
        "target_reference_class_count": len(target_class_hits),
        "target_reference_class_hits": target_class_hits,
        "repo_local": path_scope == "repo_local",
        "external_local_evidence_only": path_scope == "external",
        "image_candidate": media_type == "image",
        "calibration_data_only": media_type == "calibration_data",
        "media_type_rank": MEDIA_TYPE_RANK.get(media_type, 99),
        "currently_wired_into_simulator_tooling": record.get("currently_wired_into_simulator_tooling") is True,
        "next_recommended_reference_fixture_input": relative_path in recommended_inputs,
        "manifest_declared": manifest_validation.get("declared") is True,
        "synthetic_or_example": is_synthetic_or_example_record(record),
    }


def selection_reasons_from_score(score: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in (
        "active_current_gripper_reference",
        "has_camera_board_gripper_class_set",
        "repo_local",
        "image_candidate",
        "currently_wired_into_simulator_tooling",
        "next_recommended_reference_fixture_input",
        "manifest_declared",
    ):
        if score.get(key) is True:
            reasons.append(key)
    hits = score.get("target_reference_class_hits")
    if isinstance(hits, list) and hits:
        reasons.append("target_reference_classes:" + ",".join(str(hit) for hit in hits))
    if score.get("external_local_evidence_only") is True:
        reasons.append("external_local_evidence_only")
    if score.get("calibration_data_only") is True:
        reasons.append("calibration_data_only")
    if score.get("synthetic_or_example") is True:
        reasons.append("synthetic_or_example_diagnostic_only")
    return reasons


def candidate_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    score = record["selection_score"]
    return (
        not bool(score["active_current_gripper_reference"]),
        not bool(score["has_camera_board_gripper_class_set"]),
        -int(score["target_reference_class_count"]),
        bool(score["synthetic_or_example"]),
        not bool(score["repo_local"]),
        int(score["media_type_rank"]),
        not bool(score["currently_wired_into_simulator_tooling"]),
        not bool(score["next_recommended_reference_fixture_input"]),
        not bool(score["manifest_declared"]),
        str(record.get("relative_path") or ""),
        str(record.get("path") or ""),
    )


def candidate_is_relevant(score: dict[str, Any]) -> bool:
    return any(
        [
            score["active_current_gripper_reference"],
            score["has_camera_board_gripper_class_set"],
            score["target_reference_class_count"],
            score["currently_wired_into_simulator_tooling"],
            score["next_recommended_reference_fixture_input"],
            score["manifest_declared"],
        ]
    )


def command_record(command: list[str], result: subprocess.CompletedProcess[str], stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    return {
        "command": command,
        "return_code": int(result.returncode),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def generate_inventory(args: argparse.Namespace, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    inventory_dir = output_dir / "inventory"
    inventory_path = inventory_dir / "reference_media_inventory.json"
    stdout_path = inventory_dir / "inventory_stdout.txt"
    stderr_path = inventory_dir / "inventory_stderr.txt"
    command = [
        str(args.python.expanduser()),
        str(args.inventory_script.expanduser().resolve()),
        "--output-dir",
        str(inventory_dir),
    ]
    result = run_child(command, stdout_path=stdout_path, stderr_path=stderr_path)
    record = command_record(command, result, stdout_path, stderr_path)
    record["inventory_json_path"] = str(inventory_path)
    if result.returncode != 0:
        raise FixtureInputError(f"Inventory script failed with exit code {result.returncode}; see {stderr_path}.")
    if not inventory_path.is_file():
        raise FixtureInputError(f"Inventory script did not write expected JSON: {inventory_path}")
    return inventory_path, record


def simulator_profiles(record: dict[str, Any]) -> list[str]:
    refs = record.get("simulator_references")
    if not isinstance(refs, list):
        return []
    profiles = [
        str(ref.get("profile"))
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("profile"), str) and ref.get("profile")
    ]
    return sorted(set(profiles))


def select_reference_records(
    inventory: dict[str, Any],
    *,
    max_selected: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    media = inventory.get("media")
    if not isinstance(media, list):
        return [], [{"reason": "inventory_media_missing", "note": "Inventory does not contain a media list."}]

    recommended_raw = inventory.get("next_recommended_reference_fixture_inputs")
    recommended_inputs = {
        str(value) for value in recommended_raw if isinstance(value, str)
    } if isinstance(recommended_raw, list) else set()

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in media:
        if not isinstance(item, dict):
            skipped.append({"reason": "invalid_media_record", "media": item})
            continue
        relative_path = item.get("relative_path")
        path_label = relative_path if isinstance(relative_path, str) else "<missing>"
        score = selection_score_components(item, inventory=inventory, recommended_inputs=recommended_inputs)
        reasons = selection_reasons_from_score(score)
        if not reasons:
            skipped.append({"relative_path": path_label, "reason": "not_selected_by_inventory"})
            continue
        if not candidate_is_relevant(score):
            skipped.append({"relative_path": path_label, "reason": "not_camera_board_gripper_candidate"})
            continue
        candidates.append({**item, "selection_reasons": reasons, "selection_score": score})

    selected = sorted(candidates, key=candidate_sort_key)[: max(0, int(max_selected))]
    for rank, record in enumerate(selected, start=1):
        record["selection_rank"] = rank
    skipped.sort(key=lambda record: str(record.get("relative_path") or record.get("reason") or ""))
    return selected, skipped


def comparison_profile(record: dict[str, Any], override_profile: str | None) -> str:
    if override_profile:
        return override_profile
    profiles = simulator_profiles(record)
    if profiles:
        return profiles[0]
    return DEFAULT_PROFILE


def expected_child_artifacts(summary: dict[str, Any]) -> dict[str, str]:
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    return {str(key): str(value) for key, value in sorted(artifacts.items()) if isinstance(value, str)}


def visual_artifacts(artifacts: dict[str, str]) -> dict[str, str]:
    wanted = ("side_by_side", "overlay", "heatmap", "absolute_difference")
    return {key: value for key, value in artifacts.items() if any(token in key for token in wanted)}


def visual_record_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection_rank": record.get("selection_rank"),
        "relative_path": record.get("relative_path"),
        "path": record.get("path"),
        "root": record.get("root"),
        "root_relative_path": record.get("root_relative_path"),
        "path_scope": record.get("path_scope"),
        "media_type": record.get("media_type"),
        "dimensions": record.get("dimensions"),
        "reference_classes": record.get("reference_classes"),
        "reference_tags": record.get("reference_tags"),
        "selection_reasons": record.get("selection_reasons"),
        "selection_score": record.get("selection_score"),
        "declared_metadata": record.get("declared_metadata"),
        "manifest_validation": record.get("manifest_validation"),
        "currently_wired_into_simulator_tooling": record.get("currently_wired_into_simulator_tooling"),
        "simulator_references": record.get("simulator_references"),
    }


def build_comparison_record(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    repo_root: Path,
    index: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    relative_path = str(record["relative_path"])
    reference_path = reference_path_for_record(record, repo_root)
    reference_dir = output_dir / "references" / f"{index:03d}_{safe_slug(relative_path)}"
    child_stdout_path = reference_dir / "comparison_stdout.txt"
    child_stderr_path = reference_dir / "comparison_stderr.txt"
    summary_path = reference_dir / "summary.json"
    profile = comparison_profile(record, args.profile)
    command = [
        str(args.python.expanduser()),
        str(args.comparison_script.expanduser().resolve()),
        "--output-dir",
        str(reference_dir),
        "--reference-image",
        str(reference_path),
        "--profile",
        profile,
    ]
    result = run_child(command, stdout_path=child_stdout_path, stderr_path=child_stderr_path)

    child_summary: dict[str, Any] = {}
    child_error: str | None = None
    if summary_path.is_file():
        try:
            child_summary = read_json_object(summary_path, label="comparison summary")
        except FixtureInputError as exc:
            child_error = str(exc)
    elif result.returncode == 0:
        child_error = f"Comparison script exited 0 but did not write {summary_path}."

    artifacts = expected_child_artifacts(child_summary)
    image = child_summary.get("image") if isinstance(child_summary.get("image"), dict) else {}
    board = child_summary.get("board") if isinstance(child_summary.get("board"), dict) else {}

    return {
        "ok": result.returncode == 0 and bool(child_summary.get("ok", False)) and child_error is None,
        "selection_rank": record.get("selection_rank"),
        "relative_path": relative_path,
        "reference_image_path": str(reference_path),
        "selection_reasons": record.get("selection_reasons", []),
        "selection_score": record.get("selection_score"),
        "path_scope": record.get("path_scope"),
        "reference_classes": record.get("reference_classes"),
        "reference_tags": record.get("reference_tags"),
        "inventory_dimensions": record.get("dimensions"),
        "active_profile": profile,
        "simulator_profiles": simulator_profiles(record),
        "comparison": {
            **command_record(command, result, child_stdout_path, child_stderr_path),
            "summary_path": str(summary_path),
            "summary_loaded": bool(child_summary),
            "summary_error": child_error,
            "child_artifact_paths": artifacts,
            "visual_artifact_paths": visual_artifacts(artifacts),
        },
        "dimensions": {
            "reference": image.get("reference", {}),
            "synthetic": image.get("synthetic", {}),
            "absolute_difference": image.get("absolute_difference", {}),
        },
        "image_metrics": {
            "mean_abs_delta": image.get("mean_abs_delta"),
            "mean_abs_delta_bgr": image.get("mean_abs_delta_bgr"),
            "rmse": image.get("rmse"),
            "rmse_bgr": image.get("rmse_bgr"),
        },
        "board_corners": {
            "corner_labels": board.get("corner_labels"),
            "corners_xy": board.get("corners_xy"),
            "corner_checks": board.get("corner_checks"),
        },
        "piece_square": child_summary.get("piece_square"),
        "gripper": child_summary.get("gripper"),
        "camera_metadata": child_summary.get("camera_metadata"),
    }


def render_dependency_status() -> dict[str, Any]:
    missing: list[str] = []
    for module_name in ("cv2", "numpy"):
        try:
            __import__(module_name)
        except Exception as exc:
            missing.append(f"{module_name}: {exc}")
    return {
        "available": not missing,
        "missing": missing,
        "status": "available" if not missing else "missing_render_dependency",
    }


def read_image_for_contact_sheet(path: Path) -> Any | None:
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return image


def comparison_side_by_side_path(comparison: dict[str, Any]) -> Path | None:
    details = comparison.get("comparison")
    details = details if isinstance(details, dict) else {}
    visual = details.get("visual_artifact_paths")
    visual = visual if isinstance(visual, dict) else {}
    for key in ("side_by_side_path", "comparison_side_by_side_path"):
        value = visual.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    children = details.get("child_artifact_paths")
    children = children if isinstance(children, dict) else {}
    value = children.get("side_by_side_path")
    return Path(value) if isinstance(value, str) and value else None


def write_contact_sheet(path: Path, comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        return {
            "produced": False,
            "status": "missing_render_dependency",
            "path": str(path),
            "error": str(exc),
        }

    tiles = []
    skipped: list[dict[str, str]] = []
    for comparison in comparisons:
        if comparison.get("ok") is not True:
            skipped.append(
                {
                    "relative_path": str(comparison.get("relative_path")),
                    "reason": "comparison_not_ok",
                }
            )
            continue
        side_by_side_path = comparison_side_by_side_path(comparison)
        if side_by_side_path is None:
            skipped.append(
                {
                    "relative_path": str(comparison.get("relative_path")),
                    "reason": "side_by_side_path_missing",
                }
            )
            continue
        image = read_image_for_contact_sheet(side_by_side_path)
        if image is None:
            skipped.append(
                {
                    "relative_path": str(comparison.get("relative_path")),
                    "reason": "side_by_side_image_unreadable",
                }
            )
            continue
        max_width = 1280
        if image.shape[1] > max_width:
            scale = max_width / float(image.shape[1])
            image = cv2.resize(image, (max_width, int(round(image.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        header_height = 52
        tile = np.full((image.shape[0] + header_height, image.shape[1], 3), 245, dtype=np.uint8)
        tile[header_height:, :, :] = image
        label = f"rank {comparison.get('selection_rank')}: {comparison.get('relative_path')}"
        if len(label) > 150:
            label = label[:147] + "..."
        cv2.putText(tile, label, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
        cv2.putText(
            tile,
            "real/reference media metadata path vs synthetic SimCamera evidence",
            (12, 44),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (70, 70, 70),
            1,
            cv2.LINE_AA,
        )
        tiles.append(tile)

    if not tiles:
        return {
            "produced": False,
            "status": "no_contact_sheet_tiles",
            "path": str(path),
            "skipped": skipped,
        }

    gap = 18
    width = max(tile.shape[1] for tile in tiles)
    height = sum(tile.shape[0] for tile in tiles) + gap * (len(tiles) - 1)
    sheet = np.full((height, width, 3), 255, dtype=np.uint8)
    y = 0
    for tile in tiles:
        sheet[y : y + tile.shape[0], : tile.shape[1], :] = tile
        y += tile.shape[0] + gap

    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), sheet)
    return {
        "produced": bool(ok),
        "status": "ok" if ok else "write_failed",
        "path": str(path),
        "tile_count": len(tiles),
        "skipped": skipped,
    }


def diagnostics_section(
    *,
    inventory: dict[str, Any],
    selected_candidates: list[dict[str, Any]],
    visual_records: list[dict[str, Any]],
    render_dependencies: dict[str, Any],
) -> dict[str, Any]:
    gaps = inventory_reference_gaps(inventory)
    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    video_count = int(summary.get("video_count") or 0)
    external = [record for record in selected_candidates if record.get("path_scope") == "external"]
    synthetic_or_example = [
        record for record in selected_candidates if record.get("selection_score", {}).get("synthetic_or_example") is True
    ]
    return {
        "reference_gaps": gaps,
        "missing_depth_reference": "missing_depth_reference" in gaps,
        "missing_pick_place_video": "missing_pick_place_video" in gaps,
        "videos_present": bool(summary.get("videos_present", video_count > 0)),
        "no_videos": video_count == 0,
        "video_count": video_count,
        "synthetic_example_rows_do_not_close_real_gaps": True,
        "synthetic_or_example_selected_count": len(synthetic_or_example),
        "synthetic_or_example_selected_paths": [str(record.get("relative_path")) for record in synthetic_or_example],
        "absolute_sibling_paths_are_local_evidence_only": True,
        "external_selected_count": len(external),
        "external_selected_paths": [str(record.get("path") or record.get("relative_path")) for record in external],
        "media_assets_copied_into_repo": False,
        "visual_comparison_candidate_count": len(visual_records),
        "render_dependencies": render_dependencies,
        "notes": [
            "The inventory gap taxonomy remains authoritative for missing real depth and pick/place video evidence.",
            "Synthetic/example inventory rows may exercise tooling but are diagnostic-only for real-reference gap closure.",
            "External absolute paths from sibling roots are local review evidence only and are not copied into this repository.",
        ],
    }


def write_rows_csv(path: Path, selected_candidates: list[dict[str, Any]], comparisons: list[dict[str, Any]]) -> None:
    by_relative_path = {
        str(comparison.get("relative_path")): comparison
        for comparison in comparisons
        if isinstance(comparison.get("relative_path"), str)
    }
    fieldnames = [
        "selection_rank",
        "relative_path",
        "path",
        "path_scope",
        "media_type",
        "selected_for_visual_comparison",
        "comparison_ok",
        "comparison_summary_path",
        "side_by_side_path",
        "synthetic_path",
        "reference_classes",
        "selection_reasons",
        "target_reference_class_count",
        "active_current_gripper_reference",
        "repo_local",
        "external_local_evidence_only",
        "synthetic_or_example",
        "width",
        "height",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in selected_candidates:
            comparison = by_relative_path.get(str(record.get("relative_path")))
            details = comparison.get("comparison") if isinstance(comparison, dict) else {}
            details = details if isinstance(details, dict) else {}
            artifacts = details.get("child_artifact_paths")
            artifacts = artifacts if isinstance(artifacts, dict) else {}
            dimensions = record.get("dimensions") if isinstance(record.get("dimensions"), dict) else {}
            score = record.get("selection_score") if isinstance(record.get("selection_score"), dict) else {}
            writer.writerow(
                {
                    "selection_rank": record.get("selection_rank"),
                    "relative_path": record.get("relative_path"),
                    "path": record.get("path"),
                    "path_scope": record.get("path_scope"),
                    "media_type": record.get("media_type"),
                    "selected_for_visual_comparison": comparison is not None,
                    "comparison_ok": comparison.get("ok") if isinstance(comparison, dict) else None,
                    "comparison_summary_path": details.get("summary_path"),
                    "side_by_side_path": artifacts.get("side_by_side_path"),
                    "synthetic_path": artifacts.get("synthetic_path"),
                    "reference_classes": ";".join(normalize_string_list(record.get("reference_classes"))),
                    "selection_reasons": ";".join(normalize_string_list(record.get("selection_reasons"))),
                    "target_reference_class_count": score.get("target_reference_class_count"),
                    "active_current_gripper_reference": score.get("active_current_gripper_reference"),
                    "repo_local": score.get("repo_local"),
                    "external_local_evidence_only": score.get("external_local_evidence_only"),
                    "synthetic_or_example": score.get("synthetic_or_example"),
                    "width": dimensions.get("width"),
                    "height": dimensions.get("height"),
                }
            )


def markdown_list(values: list[str]) -> list[str]:
    if not values:
        return ["- None."]
    return [f"- `{value}`" for value in values]


def write_readme(
    path: Path,
    *,
    summary: dict[str, Any],
    rows_path: Path,
    contact_sheet: dict[str, Any],
) -> None:
    diagnostics = summary.get("diagnostics") if isinstance(summary.get("diagnostics"), dict) else {}
    rules = summary.get("selection_rules") if isinstance(summary.get("selection_rules"), list) else []
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    lines = [
        "# Reference-Driven SimCamera Comparison",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Inventory JSON: `{summary.get('inventory_json_path')}`",
        f"- Selected candidate count: `{summary.get('selected_candidate_count')}`",
        f"- Visual comparison count: `{summary.get('visual_comparison_count')}`",
        f"- JSON summary: `{Path(str(summary.get('comparison_set_summary_path'))).name}`",
        f"- CSV rows: `{rows_path.name}`",
        f"- Contact sheet: `{Path(str(contact_sheet.get('path'))).name if contact_sheet.get('produced') else 'not produced'}`",
        "",
        "## Selection Rules",
        "",
        *markdown_list([str(rule) for rule in rules]),
        "",
        "## Preserved Diagnostics",
        "",
        f"- Missing depth reference: `{diagnostics.get('missing_depth_reference')}`",
        f"- Missing pick/place video: `{diagnostics.get('missing_pick_place_video')}`",
        f"- No videos: `{diagnostics.get('no_videos')}`",
        f"- Synthetic/example rows close real gaps: `false`",
        f"- External absolute paths are local evidence only: `{diagnostics.get('absolute_sibling_paths_are_local_evidence_only')}`",
        f"- Media assets copied into repo: `{diagnostics.get('media_assets_copied_into_repo')}`",
        "",
        "## Artifacts",
        "",
        *markdown_list([f"{key}: {value}" for key, value in sorted(artifacts.items()) if value]),
        "",
        "This smoke is hardware-free. It points at inventory media paths, renders derived review artifacts under this output directory, and preserves inventory gaps instead of claiming physical camera, depth, or pick/place calibration coverage.",
        "",
    ]
    path.write_text("\n".join(lines))


def validation_failure_summary(
    *,
    output_dir: Path,
    status: str,
    error: str,
    inventory_json_path: Path | None,
    inventory_command: dict[str, Any] | None,
) -> dict[str, Any]:
    summary_path = output_dir / "comparison_set_summary.json"
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": status,
        "comparison_set_summary_path": str(summary_path),
        "hardware_skipped": True,
        "gui_skipped": True,
        "inventory_json_path": str(inventory_json_path) if inventory_json_path else None,
        "inventory_command": inventory_command,
        "selected_media_count": 0,
        "selected_candidate_count": 0,
        "visual_comparison_count": 0,
        "skipped_media": [],
        "visibility_gaps": [],
        "error": error,
    }


def build_fixture(args: argparse.Namespace, output_dir: Path) -> tuple[dict[str, Any], int]:
    inventory_command: dict[str, Any] | None = None
    if args.inventory_json is None:
        inventory_json_path, inventory_command = generate_inventory(args, output_dir)
    else:
        inventory_json_path = args.inventory_json.expanduser().resolve()
        if not inventory_json_path.is_file():
            raise FixtureInputError(f"Inventory JSON does not exist: {inventory_json_path}")

    inventory = read_json_object(inventory_json_path, label="reference media inventory")
    repo_root = Path(str(inventory.get("repo_root") or REPO_ROOT)).expanduser().resolve()
    selected, skipped = select_reference_records(
        inventory,
        max_selected=max(0, int(args.max_selected_candidates)),
    )
    visibility_gaps = inventory.get("visibility_gaps")
    visibility_gaps = visibility_gaps if isinstance(visibility_gaps, list) else []

    summary_path = output_dir / "comparison_set_summary.json"
    rows_path = output_dir / COMPARISON_ROWS_NAME
    readme_path = output_dir / README_NAME
    contact_sheet_path = output_dir / CONTACT_SHEET_NAME
    visual_records = [
        record for record in selected if record.get("media_type") == "image"
    ][: max(0, int(args.max_visual_comparisons))]
    render_dependencies = render_dependency_status()
    comparisons: list[dict[str, Any]] = []
    if render_dependencies["available"]:
        comparisons = [
            build_comparison_record(
                args=args,
                output_dir=output_dir,
                repo_root=repo_root,
                index=index,
                record=record,
            )
            for index, record in enumerate(visual_records, start=1)
        ]
    selected_count = len(visual_records)
    failed = [record for record in comparisons if not record["ok"]]
    status = "ok" if selected_count and not failed and render_dependencies["available"] else "validation_failed"
    if selected_count and not render_dependencies["available"]:
        status = "metadata_only_render_dependency_missing"
    elif selected and selected_count == 0:
        status = "metadata_only_no_visual_images"
    elif not selected:
        status = "no_reference_media_selected"
    ok = status in {"ok", "metadata_only_render_dependency_missing", "metadata_only_no_visual_images"}
    contact_sheet = (
        write_contact_sheet(contact_sheet_path, comparisons)
        if comparisons
        else {
            "produced": False,
            "status": "no_visual_comparisons",
            "path": str(contact_sheet_path),
        }
    )
    diagnostics = diagnostics_section(
        inventory=inventory,
        selected_candidates=selected,
        visual_records=visual_records,
        render_dependencies=render_dependencies,
    )

    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": status,
        "comparison_set_summary_path": str(summary_path),
        "hardware_skipped": True,
        "gui_skipped": True,
        "limits": (
            "Simulator-only fixture; it reuses the existing real-reference comparison smoke "
            "and does not touch hardware, GUI display paths, camera profiles, or calibration constants."
        ),
        "inventory_json_path": str(inventory_json_path),
        "inventory_command": inventory_command,
        "inventory_summary": inventory.get("summary"),
        "selection_rules": [
            "Rank active/current gripper reference evidence first.",
            "Prefer records classified with camera_pov + chessboard_board + gripper_arm, then records with partial hits for those classes.",
            "Prefer repo-local paths before external absolute sibling-root paths.",
            "Prefer image rows for visual side-by-side output before videos and calibration-data-only rows.",
            "Keep synthetic/example rows diagnostic-only; they do not close real-reference gaps.",
        ],
        "selected_candidate_count": len(selected),
        "selected_media_count": selected_count,
        "visual_comparison_count": len(comparisons),
        "skipped_media_count": len(skipped),
        "failed_comparison_count": len(failed),
        "selected_candidates": [visual_record_payload(record) for record in selected],
        "selected_media": [visual_record_payload(record) for record in visual_records],
        "skipped_media": skipped,
        "visibility_gaps": visibility_gaps,
        "diagnostics": diagnostics,
        "comparisons": comparisons,
        "contact_sheet": contact_sheet,
        "artifacts": {
            "summary_json": str(summary_path),
            "csv_rows": str(rows_path),
            "readme_md": str(readme_path),
            "contact_sheet_png": str(contact_sheet_path) if contact_sheet.get("produced") else None,
        },
        "notes": [
            "Selected candidates are ranked from the inventory; only selected image rows are passed to the visual comparison child.",
            "Videos and calibration-data-only rows remain metadata evidence unless a later workflow adds media-specific rendering.",
            "External absolute sibling paths are local evidence only and are not copied into the repository.",
        ],
    }
    write_rows_csv(rows_path, selected, comparisons)
    write_readme(readme_path, summary=summary, rows_path=rows_path, contact_sheet=contact_sheet)
    return summary, 0 if summary["ok"] else 2


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "comparison_set_summary.json"

    inventory_path_for_error = args.inventory_json.expanduser().resolve() if args.inventory_json else None
    try:
        summary, exit_code = build_fixture(args, output_dir)
    except FixtureInputError as exc:
        summary = validation_failure_summary(
            output_dir=output_dir,
            status="validation_failed",
            error=str(exc),
            inventory_json_path=inventory_path_for_error,
            inventory_command=None,
        )
        exit_code = 2

    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    if exit_code != 0:
        print(f"ERROR: reference media comparison set status={summary['status']}; wrote {summary_path}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
