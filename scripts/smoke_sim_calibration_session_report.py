#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# The parent process validates SimCamera candidates before spawning smoke scripts.
# Keep OpenMP-backed imports fork-safe for subprocess-heavy runs in headless sandboxes.
os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from lerobot.sim import (  # noqa: E402
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    load_sim_camera_profile_overrides,
    make_sim_camera_config_from_profile,
)

CORNER_LABELS = ("a1", "h1", "h8", "a8")
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "calibration_session_report"
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
SCENARIO = "sim_calibration_session_report"


class CandidateInputError(ValueError):
    """Raised when a candidate cannot be used as a simulator profile override."""


@dataclass(frozen=True)
class CandidateSpec:
    index: int
    candidate_path: Path
    candidate_id: str
    base_profile: str
    profile_overrides: dict[str, Any]
    width: int
    height: int
    board_corners_xy: list[list[float]]
    reference_image_path: Path
    schema: str | None
    status: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one reviewable simulator calibration session report from one or more "
            "manual SimCamera profile candidates."
        )
    )
    parser.add_argument(
        "candidates",
        type=Path,
        nargs="+",
        help=(
            "profile_candidate.json files, or JSON files containing sim_camera_profile_overrides "
            "with board_corners_xy."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Session directory for per-candidate artifacts and session_summary.json.",
    )
    parser.add_argument(
        "--sim-camera-profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
        help="Base profile for override-only candidate files that do not declare base_profile.",
    )
    parser.add_argument(
        "--reference-image",
        type=Path,
        default=None,
        help="Override the real reference image used for comparison artifacts.",
    )
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--comparison-gripper-percent", type=float, default=80.0)
    parser.add_argument("--pick-place-grasp-percent", type=float, default=24.0)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child smoke scripts. Defaults to the current interpreter.",
    )
    return parser.parse_args()


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if hasattr(value, "value"):
        return jsonable(value.value)
    return value


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CandidateInputError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise CandidateInputError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CandidateInputError(f"{label} {path} must contain a JSON object, got {type(payload).__name__}.")
    return payload


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug or "candidate"


def resolve_repo_path(path_like: str | Path) -> Path:
    path = Path(path_like).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def resolve_reference_image(
    *,
    cli_reference_image: Path | None,
    payload: dict[str, Any],
    profile_overrides: dict[str, Any],
    base_profile: str,
) -> Path:
    if cli_reference_image is not None:
        reference_image = cli_reference_image
    elif "reference_image_path" in profile_overrides:
        reference_image = profile_overrides["reference_image_path"]
    elif "reference_image_path" in payload:
        reference_image = payload["reference_image_path"]
    else:
        reference_image = SIM_CAMERA_CALIBRATION_PROFILES[base_profile].get(
            "reference_image_path", DEFAULT_REFERENCE_IMAGE
        )

    reference_path = resolve_repo_path(reference_image)
    if not reference_path.is_file():
        raise CandidateInputError(f"Reference image does not exist for candidate: {reference_path}")
    return reference_path


def load_candidate_spec(index: int, candidate_path: Path, args: argparse.Namespace) -> CandidateSpec:
    resolved_candidate_path = candidate_path.expanduser().resolve()
    if not resolved_candidate_path.is_file():
        raise CandidateInputError(f"Candidate path does not exist or is not a file: {resolved_candidate_path}")

    payload = read_json_object(resolved_candidate_path, label="candidate")
    base_profile = str(payload.get("base_profile") or args.sim_camera_profile)
    if base_profile not in SIM_CAMERA_CALIBRATION_PROFILES:
        known_profiles = ", ".join(sorted(SIM_CAMERA_CALIBRATION_PROFILES))
        raise CandidateInputError(
            f"Unknown base profile {base_profile!r} in {resolved_candidate_path}. "
            f"Known profiles: {known_profiles}"
        )

    try:
        profile_overrides = load_sim_camera_profile_overrides(resolved_candidate_path)
    except ValueError as exc:
        raise CandidateInputError(str(exc)) from exc

    if "board_corners_xy" not in profile_overrides:
        raise CandidateInputError(
            f"Candidate {resolved_candidate_path} must include board_corners_xy in "
            "sim_camera_profile_overrides for session reporting."
        )

    try:
        camera_cfg = make_sim_camera_config_from_profile(base_profile, **profile_overrides)
    except ValueError as exc:
        raise CandidateInputError(str(exc)) from exc

    board_corners_xy = [
        [float(x), float(y)] for x, y in profile_overrides["board_corners_xy"]
    ]
    reference_image_path = resolve_reference_image(
        cli_reference_image=args.reference_image,
        payload=payload,
        profile_overrides=profile_overrides,
        base_profile=base_profile,
    )
    candidate_id = f"{index:02d}_{slugify(resolved_candidate_path.parent.name)}_{slugify(resolved_candidate_path.stem)}"
    return CandidateSpec(
        index=index,
        candidate_path=resolved_candidate_path,
        candidate_id=candidate_id,
        base_profile=base_profile,
        profile_overrides=profile_overrides,
        width=int(camera_cfg.width),
        height=int(camera_cfg.height),
        board_corners_xy=board_corners_xy,
        reference_image_path=reference_image_path,
        schema=payload.get("schema") if isinstance(payload.get("schema"), str) else None,
        status=payload.get("status") if isinstance(payload.get("status"), str) else None,
    )


def parse_json_from_text(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        loaded = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def run_child(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=child_env,
            check=False,
        )
        stdout_path.write_text(result.stdout)
        stderr_path.write_text(result.stderr)
        return {
            "returncode": int(result.returncode),
            "command": command,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    except OSError as exc:
        stdout_path.write_text("")
        stderr_path.write_text(f"ERROR: {exc}\n")
        return {
            "returncode": 127,
            "command": command,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "error": str(exc),
        }


def load_smoke_summary(
    *,
    summary_path: Path,
    stdout_path: Path,
    allow_stdout_json: bool = False,
) -> dict[str, Any] | None:
    if summary_path.is_file():
        try:
            loaded = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None
    if not allow_stdout_json:
        return None

    try:
        loaded = parse_json_from_text(stdout_path.read_text())
    except OSError:
        return None
    if loaded is None:
        return None
    summary_path.write_text(json.dumps(loaded, indent=2))
    return loaded


def append_if_path(paths: list[str], value: Any) -> None:
    if isinstance(value, str) and value:
        paths.append(value)


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def comparison_artifacts(summary: dict[str, Any] | None) -> dict[str, str]:
    if not summary:
        return {}
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    return {str(key): str(value) for key, value in artifacts.items() if isinstance(value, str)}


def board_pose_artifacts(summary: dict[str, Any] | None) -> dict[str, str]:
    if not summary:
        return {}
    keys = ("summary_path", "frame_path", "annotated_frame_path", "board_model_path")
    return {key: str(summary[key]) for key in keys if isinstance(summary.get(key), str)}


def pick_place_artifacts(summary: dict[str, Any] | None) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    if not summary:
        return artifacts
    if isinstance(summary.get("summary_path"), str):
        artifacts["summary_path"] = str(summary["summary_path"])
    captures = summary.get("captures")
    if isinstance(captures, list):
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            label = str(capture.get("label") or "capture")
            path = capture.get("path")
            if isinstance(path, str):
                artifacts[f"{label}_path"] = path
    return artifacts


def app_artifacts(summary: dict[str, Any] | None, summary_path: Path) -> dict[str, str]:
    artifacts = {"summary_path": str(summary_path)}
    if summary and isinstance(summary.get("frame"), str):
        artifacts["frame_path"] = str(summary["frame"])
    return artifacts


def smoke_manifest(
    *,
    name: str,
    run_info: dict[str, Any],
    summary: dict[str, Any] | None,
    summary_path: Path,
    artifacts: dict[str, str],
) -> dict[str, Any]:
    ok = int(run_info["returncode"]) == 0 and summary is not None
    return {
        "ok": ok,
        "name": name,
        "returncode": int(run_info["returncode"]),
        "command": run_info["command"],
        "summary_loaded": summary is not None,
        "summary_path": str(summary_path),
        "stdout_path": run_info["stdout_path"],
        "stderr_path": run_info["stderr_path"],
        "artifacts": artifacts,
    }


def select_gripper_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "gripper_visible",
        "track_robot_gripper",
        "tracked_gripper_percent",
        "current_gripper_opening_px",
        "gripper_center_x_px",
        "gripper_y_px",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def extract_piece_metadata(
    *,
    source_square: str,
    target_square: str,
    comparison_summary: dict[str, Any] | None,
    board_pose_summary: dict[str, Any] | None,
    pick_place_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    pick_transition = pick_place_summary.get("piece_square_transition") if pick_place_summary else None
    source_captures: list[dict[str, Any]] = []
    target_release: dict[str, Any] | None = None
    captures = pick_place_summary.get("captures") if pick_place_summary else None
    if isinstance(captures, list):
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            metadata = capture.get("metadata")
            if not isinstance(metadata, dict):
                continue
            item = {
                "label": capture.get("label"),
                "path": capture.get("path"),
                "piece_square": metadata.get("piece_square"),
                "piece_layout": metadata.get("piece_layout"),
            }
            if metadata.get("piece_square") == source_square:
                source_captures.append(item)
            if metadata.get("piece_square") == target_square:
                target_release = item

    return {
        source_square: {
            "comparison": comparison_summary.get("piece_square") if comparison_summary else None,
            "board_pose": board_pose_summary.get("piece_square") if board_pose_summary else None,
            "pick_place_source_captures": source_captures,
        },
        target_square: {
            "pick_place_release": target_release,
        },
        "pick_place_transition": pick_transition,
    }


def extract_gripper_metadata(
    *,
    comparison_summary: dict[str, Any] | None,
    app_summary: dict[str, Any] | None,
    pick_place_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    app_camera = app_summary.get("camera") if app_summary else None
    app_metadata = app_camera.get("metadata") if isinstance(app_camera, dict) else None
    pick_captures: list[dict[str, Any]] = []
    captures = pick_place_summary.get("captures") if pick_place_summary else None
    if isinstance(captures, list):
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            metadata = capture.get("metadata")
            if isinstance(metadata, dict):
                pick_captures.append(
                    {
                        "label": capture.get("label"),
                        "path": capture.get("path"),
                        **select_gripper_fields(metadata),
                    }
                )

    return {
        "comparison": comparison_summary.get("gripper") if comparison_summary else None,
        "app_frame": select_gripper_fields(app_metadata) if isinstance(app_metadata, dict) else None,
        "pick_place_captures": pick_captures,
        "pick_place_frame_deltas": pick_place_summary.get("frame_deltas") if pick_place_summary else None,
    }


def smoke_artifact_paths(smokes: dict[str, dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for smoke in smokes.values():
        append_if_path(paths, smoke.get("summary_path"))
        append_if_path(paths, smoke.get("stdout_path"))
        append_if_path(paths, smoke.get("stderr_path"))
        artifacts = smoke.get("artifacts")
        if isinstance(artifacts, dict):
            for path in artifacts.values():
                append_if_path(paths, path)
    return dedupe_paths(paths)


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def round_float(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None


def extract_candidate_validation(comparison_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    candidate = comparison_summary.get("candidate") if comparison_summary else None
    validation = candidate.get("validation") if isinstance(candidate, dict) else None
    return validation if isinstance(validation, dict) else None


def extract_candidate_geometry(comparison_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    candidate = comparison_summary.get("candidate") if comparison_summary else None
    geometry = candidate.get("geometry_vs_base_profile") if isinstance(candidate, dict) else None
    return geometry if isinstance(geometry, dict) else None


def image_score_metrics(comparison_summary: dict[str, Any] | None) -> dict[str, Any]:
    image = comparison_summary.get("image") if comparison_summary else None
    if not isinstance(image, dict):
        return {"mean_abs_delta": None, "rmse": None}
    return {
        "mean_abs_delta": round_float(as_float(image.get("mean_abs_delta"))),
        "rmse": round_float(as_float(image.get("rmse"))),
    }


def geometry_score_metrics(
    comparison_summary: dict[str, Any] | None,
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    validation = extract_candidate_validation(comparison_summary)
    geometry = extract_candidate_geometry(comparison_summary)
    area_delta_px2 = as_float(geometry.get("area_delta_px2")) if geometry else None
    image_area = float(width * height)
    return {
        "valid": bool(validation) and bool(validation.get("in_bounds")) and bool(validation.get("convex")),
        "area_ratio": round_float(as_float(validation.get("area_ratio")) if validation else None),
        "signed_area_px2": round_float(as_float(validation.get("signed_area_px2")) if validation else None),
        "mean_corner_l2_px": round_float(as_float(geometry.get("mean_corner_l2_px")) if geometry else None),
        "max_corner_l2_px": round_float(as_float(geometry.get("max_corner_l2_px")) if geometry else None),
        "area_delta_px2": round_float(area_delta_px2),
        "area_delta_ratio": round_float(area_delta_px2 / image_area if area_delta_px2 is not None else None),
    }


def piece_score_evidence(
    *,
    source_square: str,
    target_square: str,
    comparison_summary: dict[str, Any] | None,
    board_pose_summary: dict[str, Any] | None,
    pick_place_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison_piece = comparison_summary.get("piece_square") if comparison_summary else None
    board_pose_piece = board_pose_summary.get("piece_square") if board_pose_summary else None
    transition = pick_place_summary.get("piece_square_transition") if pick_place_summary else None

    comparison_square = comparison_piece.get("square") if isinstance(comparison_piece, dict) else None
    board_pose_square = board_pose_piece.get("square") if isinstance(board_pose_piece, dict) else None
    transition_source = transition.get("source_square") if isinstance(transition, dict) else None
    transition_release = transition.get("release_square") if isinstance(transition, dict) else None
    return {
        "expected_source_square": source_square,
        "expected_target_square": target_square,
        "comparison_square": comparison_square,
        "board_pose_square": board_pose_square,
        "pick_place_source_square": transition_source,
        "pick_place_release_square": transition_release,
        "comparison_source_ok": comparison_square == source_square,
        "board_pose_source_ok": board_pose_square == source_square,
        "pick_place_source_ok": transition_source == source_square,
        "pick_place_release_ok": transition_release == target_square,
    }


def gripper_score_evidence(
    *,
    comparison_summary: dict[str, Any] | None,
    pick_place_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison_gripper = comparison_summary.get("gripper") if comparison_summary else None
    captures = pick_place_summary.get("captures") if pick_place_summary else None
    frame_deltas = pick_place_summary.get("frame_deltas") if pick_place_summary else None
    capture_count = len(captures) if isinstance(captures, list) else 0
    frame_delta_count = len(frame_deltas) if isinstance(frame_deltas, dict) else 0
    return {
        "comparison_visible": (
            bool(comparison_gripper.get("visible")) if isinstance(comparison_gripper, dict) else False
        ),
        "comparison_track_robot_gripper": (
            bool(comparison_gripper.get("track_robot_gripper")) if isinstance(comparison_gripper, dict) else False
        ),
        "comparison_tracked_gripper_percent": (
            comparison_gripper.get("tracked_gripper_percent") if isinstance(comparison_gripper, dict) else None
        ),
        "comparison_current_gripper_opening_px": (
            comparison_gripper.get("current_gripper_opening_px") if isinstance(comparison_gripper, dict) else None
        ),
        "pick_place_capture_count": capture_count,
        "pick_place_frame_delta_count": frame_delta_count,
    }


def evidence_bonus(*, piece: dict[str, Any], gripper: dict[str, Any]) -> float:
    bonus = 0.0
    for key in (
        "comparison_source_ok",
        "board_pose_source_ok",
        "pick_place_source_ok",
        "pick_place_release_ok",
    ):
        if piece.get(key):
            bonus += 10.0
    if gripper.get("comparison_visible"):
        bonus += 10.0
    if gripper.get("comparison_track_robot_gripper"):
        bonus += 5.0
    bonus += min(float(gripper.get("pick_place_capture_count") or 0), 5.0)
    bonus += min(float(gripper.get("pick_place_frame_delta_count") or 0), 3.0)
    return bonus


def build_score_components(
    *,
    spec: CandidateSpec,
    smokes: dict[str, dict[str, Any]],
    source_square: str,
    target_square: str,
    comparison_summary: dict[str, Any] | None,
    board_pose_summary: dict[str, Any] | None,
    pick_place_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    smoke_ok = {name: bool(smoke.get("ok")) for name, smoke in smokes.items()}
    smoke_failures = sorted(name for name, ok in smoke_ok.items() if not ok)
    image = image_score_metrics(comparison_summary)
    geometry = geometry_score_metrics(comparison_summary, width=spec.width, height=spec.height)
    piece = piece_score_evidence(
        source_square=source_square,
        target_square=target_square,
        comparison_summary=comparison_summary,
        board_pose_summary=board_pose_summary,
        pick_place_summary=pick_place_summary,
    )
    gripper = gripper_score_evidence(
        comparison_summary=comparison_summary,
        pick_place_summary=pick_place_summary,
    )

    rmse = as_float(image.get("rmse"))
    mean_abs_delta = as_float(image.get("mean_abs_delta"))
    mean_corner_l2 = as_float(geometry.get("mean_corner_l2_px"))
    max_corner_l2 = as_float(geometry.get("max_corner_l2_px"))
    area_delta_ratio = as_float(geometry.get("area_delta_ratio"))
    bonus = evidence_bonus(piece=piece, gripper=gripper)
    penalties = {
        "smoke_failure_penalty": float(len(smoke_failures) * 100000.0),
        "missing_image_metric_penalty": 0.0 if rmse is not None and mean_abs_delta is not None else 1000.0,
        "missing_geometry_metric_penalty": 0.0 if mean_corner_l2 is not None and max_corner_l2 is not None else 1000.0,
        "image_rmse_penalty": rmse if rmse is not None else 0.0,
        "image_mean_abs_penalty": (mean_abs_delta * 0.25) if mean_abs_delta is not None else 0.0,
        "corner_mean_l2_penalty": mean_corner_l2 if mean_corner_l2 is not None else 0.0,
        "corner_max_l2_penalty": (max_corner_l2 * 0.25) if max_corner_l2 is not None else 0.0,
        "area_delta_ratio_penalty": (abs(area_delta_ratio) * 1000.0) if area_delta_ratio is not None else 0.0,
        "piece_and_gripper_evidence_bonus": -bonus,
    }
    total_penalty = sum(penalties.values())
    return {
        "smoke_ok": smoke_ok,
        "smoke_failures": smoke_failures,
        "image": image,
        "geometry": geometry,
        "piece_evidence": piece,
        "gripper_evidence": gripper,
        "penalties": {key: round_float(value) for key, value in penalties.items()},
        "total_penalty": round_float(total_penalty),
        "rank_score": round_float(10000.0 - total_penalty),
    }


def ranking_artifact_paths(candidate: dict[str, Any]) -> dict[str, str]:
    smokes = candidate.get("smokes")
    if not isinstance(smokes, dict):
        return {}

    def smoke_artifact(smoke_name: str, artifact_name: str) -> str | None:
        smoke = smokes.get(smoke_name)
        artifacts = smoke.get("artifacts") if isinstance(smoke, dict) else None
        value = artifacts.get(artifact_name) if isinstance(artifacts, dict) else None
        return value if isinstance(value, str) else None

    def smoke_summary(smoke_name: str) -> str | None:
        smoke = smokes.get(smoke_name)
        value = smoke.get("summary_path") if isinstance(smoke, dict) else None
        return value if isinstance(value, str) else None

    paths = {
        "candidate_path": candidate.get("candidate_path"),
        "candidate_artifact_dir": candidate.get("candidate_artifact_dir"),
        "comparison_summary_path": smoke_summary("comparison"),
        "comparison_side_by_side_path": smoke_artifact("comparison", "side_by_side_path"),
        "comparison_heatmap_path": smoke_artifact("comparison", "absolute_difference_heatmap_path"),
        "app_frame_summary_path": smoke_summary("app_frame"),
        "app_frame_path": smoke_artifact("app_frame", "frame_path"),
        "board_pose_summary_path": smoke_summary("board_pose"),
        "board_pose_annotated_frame_path": smoke_artifact("board_pose", "annotated_frame_path"),
        "pick_place_summary_path": smoke_summary("pick_place"),
        "pick_place_release_path": smoke_artifact("pick_place", "target_release_open_path"),
    }
    return {key: value for key, value in paths.items() if isinstance(value, str)}


def build_ranking(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for candidate in candidates:
        score_components = candidate.get("score_components")
        if not isinstance(score_components, dict):
            continue
        smoke_failures = score_components.get("smoke_failures")
        if not isinstance(smoke_failures, list):
            smoke_failures = []
        total_penalty = as_float(score_components.get("total_penalty"))
        rank_score = as_float(score_components.get("rank_score"))
        ranked.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_path": candidate["candidate_path"],
                "candidate_artifact_dir": candidate["candidate_artifact_dir"],
                "rank_score": round_float(rank_score),
                "total_penalty": round_float(total_penalty),
                "all_smokes_ok": bool(candidate.get("ok")),
                "smoke_failures": smoke_failures,
                "image": score_components.get("image"),
                "geometry": score_components.get("geometry"),
                "piece_evidence": score_components.get("piece_evidence"),
                "gripper_evidence": score_components.get("gripper_evidence"),
                "artifact_paths": ranking_artifact_paths(candidate),
            }
        )

    ranked.sort(
        key=lambda item: (
            not bool(item["all_smokes_ok"]),
            len(item["smoke_failures"]),
            item["total_penalty"] if item["total_penalty"] is not None else float("inf"),
            str(item["candidate_id"]),
        )
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


def write_candidate_inputs(spec: CandidateSpec, candidate_dir: Path) -> dict[str, str]:
    candidate_input_dir = candidate_dir / "candidate"
    candidate_input_dir.mkdir(parents=True, exist_ok=True)

    candidate_copy_path = candidate_input_dir / "input_profile_candidate.json"
    if spec.candidate_path.resolve() != candidate_copy_path.resolve():
        shutil.copyfile(spec.candidate_path, candidate_copy_path)

    normalized_corners_path = candidate_input_dir / "normalized_corners.json"
    normalized_corners = {
        "corner_labels": list(CORNER_LABELS),
        "board_corners_xy": spec.board_corners_xy,
        "source_candidate_path": str(spec.candidate_path),
    }
    normalized_corners_path.write_text(json.dumps(normalized_corners, indent=2))
    return {
        "input_candidate_copy_path": str(candidate_copy_path),
        "normalized_corners_path": str(normalized_corners_path),
    }


def run_candidate_session(spec: CandidateSpec, *, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    candidate_dir = output_dir / "candidates" / spec.candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_input_artifacts = write_candidate_inputs(spec, candidate_dir)
    python = str(args.python.expanduser())

    comparison_dir = candidate_dir / "comparison"
    comparison_summary_path = comparison_dir / "summary.json"
    comparison_run = run_child(
        [
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_manual_corner_profile_candidate.py"),
            "--corners-json",
            candidate_input_artifacts["normalized_corners_path"],
            "--output-dir",
            str(comparison_dir),
            "--reference-image",
            str(spec.reference_image_path),
            "--profile",
            spec.base_profile,
            "--piece-square",
            str(args.source_square),
            "--gripper-percent",
            str(float(args.comparison_gripper_percent)),
        ],
        cwd=REPO_ROOT,
        stdout_path=comparison_dir / "stdout.log",
        stderr_path=comparison_dir / "stderr.log",
    )
    comparison_summary = load_smoke_summary(
        summary_path=comparison_summary_path,
        stdout_path=comparison_dir / "stdout.log",
    )

    app_dir = candidate_dir / "app"
    app_summary_path = app_dir / "summary.json"
    app_run = run_child(
        [
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_app_entrypoints.py"),
            "--frame-out",
            str(app_dir / "frame.jpg"),
            "--sim-camera-profile",
            spec.base_profile,
            "--sim-camera-profile-overrides",
            str(spec.candidate_path),
        ],
        cwd=REPO_ROOT,
        stdout_path=app_dir / "stdout.log",
        stderr_path=app_dir / "stderr.log",
    )
    app_summary = load_smoke_summary(
        summary_path=app_summary_path,
        stdout_path=app_dir / "stdout.log",
        allow_stdout_json=True,
    )

    board_pose_dir = candidate_dir / "board_pose"
    board_pose_summary_path = board_pose_dir / "summary.json"
    board_pose_run = run_child(
        [
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_board_pose_calibration.py"),
            "--frame-dir",
            str(board_pose_dir),
            "--piece-square",
            str(args.source_square),
            "--sim-camera-profile",
            spec.base_profile,
            "--sim-camera-profile-overrides",
            str(spec.candidate_path),
        ],
        cwd=REPO_ROOT,
        stdout_path=board_pose_dir / "stdout.log",
        stderr_path=board_pose_dir / "stderr.log",
    )
    board_pose_summary = load_smoke_summary(
        summary_path=board_pose_summary_path,
        stdout_path=board_pose_dir / "stdout.log",
    )

    pick_place_dir = candidate_dir / "pick_place"
    pick_place_summary_path = pick_place_dir / "summary.json"
    pick_place_run = run_child(
        [
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_pick_place_calibration.py"),
            "--frame-dir",
            str(pick_place_dir),
            "--source-square",
            str(args.source_square),
            "--target-square",
            str(args.target_square),
            "--grasp-percent",
            str(float(args.pick_place_grasp_percent)),
            "--sim-camera-profile",
            spec.base_profile,
            "--sim-camera-profile-overrides",
            str(spec.candidate_path),
        ],
        cwd=REPO_ROOT,
        stdout_path=pick_place_dir / "stdout.log",
        stderr_path=pick_place_dir / "stderr.log",
    )
    pick_place_summary = load_smoke_summary(
        summary_path=pick_place_summary_path,
        stdout_path=pick_place_dir / "stdout.log",
    )

    smokes = {
        "comparison": smoke_manifest(
            name="comparison",
            run_info=comparison_run,
            summary=comparison_summary,
            summary_path=comparison_summary_path,
            artifacts=comparison_artifacts(comparison_summary),
        ),
        "app_frame": smoke_manifest(
            name="app_frame",
            run_info=app_run,
            summary=app_summary,
            summary_path=app_summary_path,
            artifacts=app_artifacts(app_summary, app_summary_path),
        ),
        "board_pose": smoke_manifest(
            name="board_pose",
            run_info=board_pose_run,
            summary=board_pose_summary,
            summary_path=board_pose_summary_path,
            artifacts=board_pose_artifacts(board_pose_summary),
        ),
        "pick_place": smoke_manifest(
            name="pick_place",
            run_info=pick_place_run,
            summary=pick_place_summary,
            summary_path=pick_place_summary_path,
            artifacts=pick_place_artifacts(pick_place_summary),
        ),
    }
    artifact_paths = dedupe_paths(
        [
            str(spec.candidate_path),
            *candidate_input_artifacts.values(),
            *smoke_artifact_paths(smokes),
        ]
    )
    ok = all(smoke["ok"] for smoke in smokes.values())
    score_components = build_score_components(
        spec=spec,
        smokes=smokes,
        source_square=str(args.source_square),
        target_square=str(args.target_square),
        comparison_summary=comparison_summary,
        board_pose_summary=board_pose_summary,
        pick_place_summary=pick_place_summary,
    )
    return {
        "ok": ok,
        "candidate_id": spec.candidate_id,
        "candidate_path": str(spec.candidate_path),
        "candidate_artifact_dir": str(candidate_dir),
        "base_profile": spec.base_profile,
        "profile_name": spec.base_profile,
        "schema": spec.schema,
        "status": spec.status,
        "width": spec.width,
        "height": spec.height,
        "board_corners_xy": spec.board_corners_xy,
        "reference_image_path": str(spec.reference_image_path),
        "profile_overrides": jsonable(spec.profile_overrides),
        "profile_values": jsonable(SIM_CAMERA_CALIBRATION_PROFILES[spec.base_profile]),
        "candidate_input_artifacts": candidate_input_artifacts,
        "smokes": smokes,
        "score_components": score_components,
        "piece_metadata": extract_piece_metadata(
            source_square=str(args.source_square),
            target_square=str(args.target_square),
            comparison_summary=comparison_summary,
            board_pose_summary=board_pose_summary,
            pick_place_summary=pick_place_summary,
        ),
        "gripper_metadata": extract_gripper_metadata(
            comparison_summary=comparison_summary,
            app_summary=app_summary,
            pick_place_summary=pick_place_summary,
        ),
        "artifact_paths": artifact_paths,
    }


def main() -> int:
    args = parse_args()
    try:
        specs = [
            load_candidate_spec(index=index, candidate_path=candidate_path, args=args)
            for index, candidate_path in enumerate(args.candidates, start=1)
        ]
    except CandidateInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = [run_candidate_session(spec, output_dir=output_dir, args=args) for spec in specs]
    summary_path = output_dir / "session_summary.json"
    ranking = build_ranking(candidates)
    selected_candidate = ranking[0] if ranking else None
    ok = bool(selected_candidate and selected_candidate.get("all_smokes_ok") is True)
    summary = {
        "ok": ok,
        "scenario": SCENARIO,
        "output_dir": str(output_dir),
        "summary_path": str(summary_path),
        "candidate_count": len(candidates),
        "source_square": str(args.source_square),
        "target_square": str(args.target_square),
        "python": str(args.python.expanduser()),
        "hardware_skipped": True,
        "gui_skipped": True,
        "smoke_names": ["comparison", "app_frame", "board_pose", "pick_place"],
        "session_pass_criteria": (
            "At least one rankable candidate must have every child smoke passing. "
            "Lower-ranked candidate failures remain in the report as comparative calibration evidence."
        ),
        "failed_candidate_count": sum(1 for candidate in candidates if not bool(candidate.get("ok"))),
        "ranking_criteria": {
            "order": [
                "all child smokes passing",
                "fewest child smoke failures",
                "lowest total_penalty",
                "candidate_id lexical tiebreaker",
            ],
            "total_penalty_components": {
                "smoke_failure_penalty": "100000 per failed child smoke",
                "missing_image_metric_penalty": "1000 if comparison image RMSE or mean absolute delta is unavailable",
                "missing_geometry_metric_penalty": "1000 if corner delta metrics are unavailable",
                "image_rmse_penalty": "comparison image RMSE",
                "image_mean_abs_penalty": "0.25 * comparison image mean_abs_delta",
                "corner_mean_l2_penalty": "mean candidate-vs-base corner L2 delta in pixels",
                "corner_max_l2_penalty": "0.25 * max candidate-vs-base corner L2 delta in pixels",
                "area_delta_ratio_penalty": "1000 * absolute signed-area delta ratio vs base profile",
                "piece_and_gripper_evidence_bonus": (
                    "negative penalty for expected source/target piece transition and gripper metadata evidence"
                ),
            },
            "rank_score": "10000 - total_penalty; higher is better after smoke-pass ordering",
            "limits": (
                "This is a deterministic simulator smoke heuristic for comparing review artifacts. "
                "It is not a full photoreal calibration score and does not validate real hardware."
            ),
        },
        "ranking": ranking,
        "candidates": candidates,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
