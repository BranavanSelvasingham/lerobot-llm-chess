#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.sim import load_ranked_sim_calibration_session  # noqa: E402

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "perception_regression_fixture"
SCHEMA = "lerobot.sim.perception_regression_fixture.v1"
REQUIRED_RANKING_ARTIFACTS = (
    "candidate_path",
    "comparison_summary_path",
    "comparison_side_by_side_path",
    "comparison_heatmap_path",
    "app_frame_summary_path",
    "app_frame_path",
    "board_pose_summary_path",
    "board_pose_annotated_frame_path",
    "pick_place_summary_path",
    "pick_place_release_path",
)


class FixtureInputError(ValueError):
    """Raised when an existing session cannot produce a fixture manifest."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Package one ranked simulator calibration candidate into a machine-readable "
            "perception regression fixture manifest."
        )
    )
    parser.add_argument("summary_path", type=Path, help="Ranked session_summary.json.")
    parser.add_argument("--select-rank", type=int, default=1)
    parser.add_argument("--select-candidate-id", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
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


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value


def artifact_path_strings(artifact_paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(path) for key, path in sorted(artifact_paths.items())}


def missing_named_artifacts(
    artifact_paths: dict[str, Path],
    required_keys: tuple[str, ...],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for key in required_keys:
        path = artifact_paths.get(key)
        if path is None:
            missing.append({"key": key, "path": "", "reason": "not_listed"})
        elif not path.exists():
            missing.append({"key": key, "path": str(path), "reason": "missing"})
    return missing


def collect_missing_paths(named_paths: dict[str, str | None]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for key, value in sorted(named_paths.items()):
        if value is None:
            missing.append({"key": key, "path": "", "reason": "not_listed"})
            continue
        path = Path(value)
        if not path.exists():
            missing.append({"key": key, "path": value, "reason": "missing"})
    return missing


def image_metrics(comparison_summary: dict[str, Any]) -> dict[str, Any]:
    image = comparison_summary.get("image")
    if not isinstance(image, dict):
        return {}
    return {
        "mean_abs_delta": image.get("mean_abs_delta"),
        "mean_abs_delta_bgr": image.get("mean_abs_delta_bgr"),
        "rmse": image.get("rmse"),
        "rmse_bgr": image.get("rmse_bgr"),
        "reference": image.get("reference"),
        "synthetic": image.get("synthetic"),
        "absolute_difference": image.get("absolute_difference"),
    }


def comparison_metrics(comparison_summary: dict[str, Any]) -> dict[str, Any]:
    candidate = comparison_summary.get("candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    return {
        "image": image_metrics(comparison_summary),
        "candidate_validation": candidate.get("validation"),
        "geometry_vs_base_profile": candidate.get("geometry_vs_base_profile"),
        "piece_square": comparison_summary.get("piece_square"),
        "gripper": comparison_summary.get("gripper"),
    }


def capture_record(capture: dict[str, Any]) -> dict[str, Any]:
    metadata = capture.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "label": capture.get("label"),
        "path": capture.get("path"),
        "piece_square": metadata.get("piece_square"),
        "piece_layout": metadata.get("piece_layout"),
        "gripper_visible": metadata.get("gripper_visible"),
        "track_robot_gripper": metadata.get("track_robot_gripper"),
        "tracked_gripper_percent": metadata.get("tracked_gripper_percent"),
        "current_gripper_opening_px": metadata.get("current_gripper_opening_px"),
        "gripper_center_x_px": metadata.get("gripper_center_x_px"),
        "gripper_y_px": metadata.get("gripper_y_px"),
        "mean_bgr": capture.get("mean_bgr"),
        "unique_colors": capture.get("unique_colors"),
    }


def pick_place_evidence(
    pick_place_summary: dict[str, Any], *, source_square: str, target_square: str
) -> dict[str, Any]:
    captures = pick_place_summary.get("captures")
    capture_rows = (
        [capture_record(capture) for capture in captures if isinstance(capture, dict)]
        if isinstance(captures, list)
        else []
    )
    source_captures = [
        capture
        for capture in capture_rows
        if str(capture.get("label") or "").startswith("source_")
    ]
    target_captures = [
        capture
        for capture in capture_rows
        if str(capture.get("label") or "").startswith("target_")
    ]
    release_capture = next(
        (
            capture
            for capture in target_captures
            if capture.get("piece_square") == target_square
            and "release" in str(capture.get("label") or "")
        ),
        target_captures[-1] if target_captures else None,
    )
    return {
        "source_square": source_square,
        "target_square": target_square,
        "piece_square_transition": pick_place_summary.get("piece_square_transition"),
        "source_captures": source_captures,
        "target_captures": target_captures,
        "release_capture": release_capture,
        "frame_deltas": pick_place_summary.get("frame_deltas"),
        "tool_results": pick_place_summary.get("tool_results"),
    }


def gripper_metadata(
    *,
    comparison_summary: dict[str, Any],
    app_summary: dict[str, Any],
    pick_place_summary: dict[str, Any],
) -> dict[str, Any]:
    app_camera = app_summary.get("camera")
    app_metadata = app_camera.get("metadata") if isinstance(app_camera, dict) else None
    captures = pick_place_summary.get("captures")
    return {
        "comparison": comparison_summary.get("gripper"),
        "app_frame": app_metadata if isinstance(app_metadata, dict) else None,
        "pick_place_captures": [
            capture_record(capture)
            for capture in captures
            if isinstance(capture, dict)
        ]
        if isinstance(captures, list)
        else [],
    }


def board_pose_summary(board_pose: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary_path": board_pose.get("summary_path"),
        "frame_path": board_pose.get("frame_path"),
        "annotated_frame_path": board_pose.get("annotated_frame_path"),
        "board_model_path": board_pose.get("board_model_path"),
        "image": board_pose.get("image"),
        "corner_checks": board_pose.get("corner_checks"),
        "board_geometry": board_pose.get("board_geometry"),
        "pose_estimator": board_pose.get("pose_estimator"),
        "piece_square": board_pose.get("piece_square"),
        "notes": board_pose.get("notes"),
    }


def app_frame_summary(app_summary: dict[str, Any], *, summary_path: Path) -> dict[str, Any]:
    return {
        "summary_path": app_summary.get("summary_path") or str(summary_path),
        "frame_path": app_summary.get("frame"),
        "shape": app_summary.get("shape"),
        "camera": app_summary.get("camera"),
        "selected_calibration": app_summary.get("selected_calibration"),
    }


def summary_artifact(summary: dict[str, Any], key: str) -> str | None:
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    value = artifacts.get(key)
    return value if isinstance(value, str) else None


def build_fixture(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        session = load_ranked_sim_calibration_session(args.summary_path)
        selected = session.select(
            rank=int(args.select_rank),
            candidate_id=str(args.select_candidate_id) if args.select_candidate_id else None,
        )
    except ValueError as exc:
        raise FixtureInputError(str(exc)) from exc

    artifact_paths = artifact_path_strings(selected.artifact_paths)
    missing_artifacts = missing_named_artifacts(selected.artifact_paths, REQUIRED_RANKING_ARTIFACTS)
    if missing_artifacts:
        return (
            {
                "schema": SCHEMA,
                "ok": False,
                "status": "validation_failed",
                "summary_path": str(Path(args.summary_path).expanduser().resolve()),
                "selected": selected.to_jsonable(),
                "artifact_paths": artifact_paths,
                "missing_artifacts": missing_artifacts,
            },
            missing_artifacts,
        )

    comparison_summary = read_json_object(
        selected.artifact_paths["comparison_summary_path"],
        label="comparison summary",
    )
    app_summary = read_json_object(
        selected.artifact_paths["app_frame_summary_path"],
        label="app frame summary",
    )
    pose_summary = read_json_object(
        selected.artifact_paths["board_pose_summary_path"],
        label="board pose summary",
    )
    pick_summary = read_json_object(
        selected.artifact_paths["pick_place_summary_path"],
        label="pick/place summary",
    )

    fixture_artifacts: dict[str, str | None] = {
        "session_summary_path": str(selected.summary_path),
        "candidate_path": str(selected.candidate_path),
        "candidate_artifact_dir": str(selected.candidate_artifact_dir) if selected.candidate_artifact_dir else None,
        "reference_image_path": str(selected.reference_image_path) if selected.reference_image_path else None,
        **artifact_paths,
        "comparison_reference_candidate_overlay_path": summary_artifact(
            comparison_summary,
            "reference_candidate_overlay_path",
        ),
        "comparison_synthetic_candidate_path": summary_artifact(
            comparison_summary,
            "synthetic_candidate_path",
        ),
        "board_pose_frame_path": pose_summary.get("frame_path") if isinstance(pose_summary.get("frame_path"), str) else None,
        "board_pose_board_model_path": pose_summary.get("board_model_path") if isinstance(pose_summary.get("board_model_path"), str) else None,
    }

    pick_evidence = pick_place_evidence(
        pick_summary,
        source_square=str(args.source_square),
        target_square=str(args.target_square),
    )
    for index, capture in enumerate(pick_evidence["source_captures"], start=1):
        fixture_artifacts[f"pick_place_source_capture_{index}_path"] = (
            capture.get("path") if isinstance(capture.get("path"), str) else None
        )
    release_capture = pick_evidence.get("release_capture")
    if isinstance(release_capture, dict):
        fixture_artifacts["pick_place_release_capture_path"] = (
            release_capture.get("path") if isinstance(release_capture.get("path"), str) else None
        )

    missing_artifacts.extend(collect_missing_paths(fixture_artifacts))

    fixture = {
        "schema": SCHEMA,
        "ok": not missing_artifacts,
        "status": "ok" if not missing_artifacts else "validation_failed",
        "fixture_summary_path": str(args.output_dir.expanduser().resolve() / "fixture_summary.json"),
        "hardware_skipped": True,
        "gui_skipped": True,
        "limits": (
            "Simulator-only regression fixture assembled from existing calibration smoke artifacts; "
            "it does not validate real hardware behavior."
        ),
        "selected_candidate": {
            "rank": int(selected.rank),
            "candidate_id": selected.candidate_id,
            "rank_score": selected.rank_score,
            "total_penalty": selected.total_penalty,
            "all_smokes_ok": selected.all_smokes_ok,
            "smoke_failures": list(selected.smoke_failures),
            "profile_name": selected.base_profile,
            "base_profile": selected.base_profile,
            "candidate_path": str(selected.candidate_path),
            "candidate_artifact_dir": str(selected.candidate_artifact_dir) if selected.candidate_artifact_dir else None,
            "board_corners_xy": [[float(x), float(y)] for x, y in selected.board_corners_xy],
            "reference_image_path": str(selected.reference_image_path) if selected.reference_image_path else None,
            "profile_overrides": jsonable(selected.profile_overrides),
        },
        "comparison": {
            "summary_path": str(selected.artifact_paths["comparison_summary_path"]),
            "metrics": comparison_metrics(comparison_summary),
            "artifacts": comparison_summary.get("artifacts"),
        },
        "app_frame": app_frame_summary(
            app_summary,
            summary_path=selected.artifact_paths["app_frame_summary_path"],
        ),
        "board_pose": board_pose_summary(pose_summary),
        "pick_place": pick_evidence,
        "gripper_metadata": gripper_metadata(
            comparison_summary=comparison_summary,
            app_summary=app_summary,
            pick_place_summary=pick_summary,
        ),
        "artifact_paths": {key: value for key, value in fixture_artifacts.items() if value is not None},
        "missing_artifacts": missing_artifacts,
        "source_session": {
            "summary_path": str(session.summary_path),
            "candidate_count": len(session.candidates),
        },
    }
    return fixture, missing_artifacts


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    try:
        fixture, missing_artifacts = build_fixture(args)
    except FixtureInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    fixture["fixture_summary_path"] = str(output_dir / "fixture_summary.json")
    (output_dir / "fixture_summary.json").write_text(json.dumps(fixture, indent=2))
    print(json.dumps(fixture, indent=2))
    if missing_artifacts:
        print(
            f"ERROR: fixture validation failed with {len(missing_artifacts)} missing artifact(s); "
            f"wrote {output_dir / 'fixture_summary.json'}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
