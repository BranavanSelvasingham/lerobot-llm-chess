#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "lerobot.sim.calibration_artifact_index.v1"
CATEGORY_ORDER = {
    "real_reference_media": 0,
    "real_reference_comparison": 1,
    "ranked_candidate": 2,
    "perception_fixture": 3,
    "sim_camera_pose_fixture": 4,
    "pick_place_scenario": 5,
    "negative_check": 6,
    "logs": 7,
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


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
    if path.suffix.lower() == ".json":
        return "json"
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
        add_path(
            artifacts,
            category="real_reference_media",
            label=f"real_reference:{relative_path}",
            value=relative_path,
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            repo_root=repo_root,
            source="comparison_set.selected_media",
            reference_media=relative_path,
        )
        rows.append(
            {
                "relative_path": relative_path,
                "media_type": record.get("media_type"),
                "dimensions": record.get("dimensions"),
                "selection_reasons": record.get("selection_reasons"),
                "currently_wired_into_simulator_tooling": record.get("currently_wired_into_simulator_tooling"),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("relative_path") or ""))


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

    comparison_set_summary = None
    comparison_set = suite.get("comparison_set") if isinstance(suite.get("comparison_set"), dict) else {}
    comparison_set_summary = load_optional_json(
        comparison_set.get("summary_path"),
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
    collect_comparison_artifacts(
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
        "skipped_markers": suite.get("skipped_markers"),
        "suite_status": {
            "ok": suite.get("ok"),
            "status": suite.get("status"),
            "aggregate_status": suite.get("aggregate_status"),
        },
        "selected_real_reference_media": selected_media,
        "sim_camera_pose_fixture_metadata_contract": sim_camera_pose_metadata_contract,
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
