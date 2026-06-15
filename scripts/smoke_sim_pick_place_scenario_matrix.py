#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "pick_place_scenario_matrix"
DEFAULT_PROFILE = "current_gripper_reference"
SCHEMA = "lerobot.sim.pick_place_scenario_matrix.v1"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    source_square: str
    target_square: str
    perspective: str
    note: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="center_to_center",
        source_square="e4",
        target_square="e5",
        perspective="center",
        note="Baseline center-board pickup and release path.",
    ),
    Scenario(
        scenario_id="left_edge_file",
        source_square="a4",
        target_square="a5",
        perspective="edge",
        note="Left file edge path for board-corner calibration sensitivity.",
    ),
    Scenario(
        scenario_id="back_rank",
        source_square="b8",
        target_square="c8",
        perspective="far_back_rank",
        note="Far rank path near the top of the gripper-camera board view.",
    ),
    Scenario(
        scenario_id="near_gripper_lower_board",
        source_square="e2",
        target_square="e3",
        perspective="near_gripper",
        note="Lower-board path near the visible gripper region.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free SO-101 simulator pick/place scenario matrix across "
            "center, edge, back-rank, and near-gripper board zones."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child pick/place smoke scripts.",
    )
    parser.add_argument(
        "--sim-camera-profile",
        default=DEFAULT_PROFILE,
        help="Named simulator camera calibration profile passed to each child smoke.",
    )
    parser.add_argument(
        "--sim-camera-profile-overrides",
        type=Path,
        default=None,
        help="Optional simulator-only profile_candidate.json passed to each child smoke.",
    )
    parser.add_argument("--grasp-percent", type=float, default=24.0)
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, f"Expected JSON object, got {type(payload).__name__}."
    return payload, None


def square_file_rank(square: str) -> tuple[int, int]:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(value[0]) - ord("a"), int(value[1]) - 1


def board_zone_labels(square: str) -> list[str]:
    file_idx, rank_idx = square_file_rank(square)
    labels: list[str] = []
    if file_idx in (0, 7):
        labels.append("file_edge")
    elif file_idx in (1, 6):
        labels.append("near_file_edge")
    else:
        labels.append("center_file")

    if rank_idx in (0, 7):
        labels.append("back_rank")
    elif rank_idx in (1, 2):
        labels.append("near_gripper_lower_board")
    elif rank_idx in (3, 4):
        labels.append("center_rank")
    else:
        labels.append("far_upper_board")

    if 2 <= file_idx <= 5 and 2 <= rank_idx <= 5:
        labels.append("center")
    if file_idx in (0, 7) or rank_idx in (0, 7):
        labels.append("edge")
    return labels


def pick_place_artifacts(summary: dict[str, Any] | None) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    if not summary:
        return artifacts
    summary_path = summary.get("summary_path")
    if isinstance(summary_path, str):
        artifacts["summary_path"] = summary_path
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


def missing_artifacts(artifacts: dict[str, str]) -> list[str]:
    return [path for path in artifacts.values() if not Path(path).is_file()]


def extract_gripper_visibility(summary: dict[str, Any] | None) -> dict[str, Any]:
    captures = summary.get("captures") if summary else None
    rows: list[dict[str, Any]] = []
    if isinstance(captures, list):
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            metadata = capture.get("metadata")
            if not isinstance(metadata, dict):
                continue
            rows.append(
                {
                    "label": capture.get("label"),
                    "path": capture.get("path"),
                    "gripper_visible": metadata.get("gripper_visible"),
                    "track_robot_gripper": metadata.get("track_robot_gripper"),
                    "tracked_gripper_percent": metadata.get("tracked_gripper_percent"),
                    "current_gripper_opening_px": metadata.get("current_gripper_opening_px"),
                }
            )
    visible_values = [row.get("gripper_visible") for row in rows if row.get("gripper_visible") is not None]
    return {
        "available": bool(rows),
        "all_captures_mark_gripper_visible": all(bool(value) for value in visible_values) if visible_values else None,
        "captures": rows,
    }


def extract_piece_visibility(summary: dict[str, Any] | None) -> dict[str, Any]:
    aggregate = summary.get("piece_visibility") if summary else None
    captures = summary.get("captures") if summary else None
    rows: list[dict[str, Any]] = []
    if isinstance(captures, list):
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            metric = capture.get("piece_visibility")
            if not isinstance(metric, dict):
                continue
            occlusion = metric.get("occlusion") if isinstance(metric.get("occlusion"), dict) else {}
            clearance = metric.get("gripper_clearance") if isinstance(metric.get("gripper_clearance"), dict) else {}
            piece = metric.get("piece") if isinstance(metric.get("piece"), dict) else {}
            rows.append(
                {
                    "label": capture.get("label"),
                    "path": capture.get("path"),
                    "available": metric.get("available"),
                    "status": metric.get("status"),
                    "piece_square": piece.get("square"),
                    "visible_fraction": occlusion.get("visible_fraction"),
                    "occlusion_fraction": occlusion.get("occlusion_fraction"),
                    "overlap_piece_pixels": occlusion.get("overlap_piece_pixels"),
                    "min_clearance_px": clearance.get("min_clearance_px"),
                    "clear_of_gripper": clearance.get("clear_of_gripper"),
                }
            )
    return {
        "available": bool(aggregate.get("available")) if isinstance(aggregate, dict) else bool(rows),
        "aggregate": aggregate if isinstance(aggregate, dict) else None,
        "captures": rows,
        "limitations": [
            "Synthetic geometry only; this does not model physical chess-piece contact or real camera segmentation.",
        ],
    }


def extract_selected_frames(artifacts: dict[str, str]) -> dict[str, str]:
    wanted = (
        "source_open_path",
        "source_hover_open_path",
        "source_pinched_path",
        "source_closed_path",
        "target_hover_closed_path",
        "target_release_open_path",
    )
    return {key: artifacts[key] for key in wanted if key in artifacts}


def run_scenario(
    *,
    scenario: Scenario,
    args: argparse.Namespace,
    output_dir: Path,
) -> dict[str, Any]:
    scenario_dir = output_dir / "scenarios" / scenario.scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    summary_path = scenario_dir / "summary.json"
    stdout_path = scenario_dir / "stdout.txt"
    stderr_path = scenario_dir / "stderr.txt"
    command = [
        str(args.python.expanduser()),
        str(REPO_ROOT / "scripts" / "smoke_sim_pick_place_calibration.py"),
        "--frame-dir",
        str(scenario_dir),
        "--source-square",
        scenario.source_square,
        "--target-square",
        scenario.target_square,
        "--grasp-percent",
        str(float(args.grasp_percent)),
    ]
    if args.sim_camera_profile:
        command.extend(["--sim-camera-profile", str(args.sim_camera_profile)])
    if args.sim_camera_profile_overrides:
        command.extend(
            [
                "--sim-camera-profile-overrides",
                str(args.sim_camera_profile_overrides.expanduser().resolve()),
            ]
        )

    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)

    child_summary, summary_error = read_json_object(summary_path) if summary_path.is_file() else (None, None)
    if child_summary is None and result.returncode == 0 and summary_error is None:
        summary_error = f"Expected summary JSON was not written: {summary_path}"
    artifacts = pick_place_artifacts(child_summary)
    missing = missing_artifacts(artifacts)
    child_ok = bool(child_summary.get("ok", False)) if child_summary else False
    squares_ok = (
        bool(child_summary)
        and child_summary.get("source_square") == scenario.source_square
        and child_summary.get("target_square") == scenario.target_square
    )
    ok = result.returncode == 0 and child_ok and squares_ok and summary_error is None and not missing

    return {
        "scenario_id": scenario.scenario_id,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "source_square": scenario.source_square,
        "target_square": scenario.target_square,
        "profile": str(args.sim_camera_profile) if args.sim_camera_profile else None,
        "perspective": scenario.perspective,
        "board_zones": {
            "source": board_zone_labels(scenario.source_square),
            "target": board_zone_labels(scenario.target_square),
        },
        "note": scenario.note,
        "command": command,
        "return_code": int(result.returncode),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(summary_path),
        "summary_loaded": child_summary is not None,
        "summary_error": summary_error,
        "summary_status": child_summary.get("scenario") if child_summary else None,
        "squares_ok": squares_ok,
        "artifacts": artifacts,
        "selected_frame_paths": extract_selected_frames(artifacts),
        "missing_artifact_paths": missing,
        "gripper_visibility": extract_gripper_visibility(child_summary),
        "piece_visibility": extract_piece_visibility(child_summary),
        "frame_deltas": child_summary.get("frame_deltas") if child_summary else None,
        "limitations": [
            "This matrix reuses the existing joint-state simulator smoke; it does not model physical chess-piece contact.",
            "piece_visibility is a synthetic-frame geometry signal and is evidence-only until values prove stable across local and CI runs.",
        ],
    }


def aggregate_piece_visibility(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    scenario_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        metric = scenario.get("piece_visibility")
        aggregate = metric.get("aggregate") if isinstance(metric, dict) else None
        if not isinstance(aggregate, dict):
            scenario_rows.append(
                {
                    "scenario_id": scenario.get("scenario_id"),
                    "available": False,
                    "status": "unavailable",
                }
            )
            continue
        scenario_rows.append(
            {
                "scenario_id": scenario.get("scenario_id"),
                "available": aggregate.get("available"),
                "all_captures_clear_of_gripper": aggregate.get("all_captures_clear_of_gripper"),
                "min_visible_fraction": aggregate.get("min_visible_fraction"),
                "max_occlusion_fraction": aggregate.get("max_occlusion_fraction"),
                "min_clearance_px": aggregate.get("min_clearance_px"),
                "worst_capture_label": aggregate.get("worst_capture_label"),
                "target_release_open": aggregate.get("target_release_open"),
            }
        )

    available = [row for row in scenario_rows if row.get("available")]
    return {
        "available": bool(available),
        "scenario_count": len(scenario_rows),
        "available_scenario_count": len(available),
        "all_scenarios_available": len(available) == len(scenario_rows),
        "scenarios": scenario_rows,
        "limitations": [
            "Synthetic geometry only; this does not model physical chess-piece contact or real camera segmentation.",
            "The matrix reports measured visibility/clearance evidence but does not fail scenarios on a visibility threshold yet.",
        ],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_records = [
        run_scenario(scenario=scenario, args=args, output_dir=output_dir) for scenario in SCENARIOS
    ]
    ok = all(bool(record["ok"]) for record in scenario_records)
    summary_path = output_dir / "scenario_matrix_summary.json"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "python": str(args.python.expanduser()),
        "sim_camera_profile": str(args.sim_camera_profile) if args.sim_camera_profile else None,
        "sim_camera_profile_overrides": (
            str(args.sim_camera_profile_overrides.expanduser().resolve())
            if args.sim_camera_profile_overrides
            else None
        ),
        "hardware_skipped": True,
        "gui_skipped": True,
        "skipped_markers": {
            "hardware": "Matrix and child smokes use simulator-only KinematicsTools and SimCamera paths.",
            "gui": "Matrix invokes non-interactive smoke scripts and does not open display calibration flows.",
        },
        "aggregate_status": {
            "ok": ok,
            "scenario_count": len(scenario_records),
            "failed_scenario_ids": [
                str(record["scenario_id"]) for record in scenario_records if not bool(record["ok"])
            ],
        },
        "piece_visibility": aggregate_piece_visibility(scenario_records),
        "scenarios": scenario_records,
        "notes": [
            "The canonical calibration regression suite invokes this matrix as a hardware-free child gate.",
            "The matrix broadens pick/place coverage only; it does not change simulator rendering, camera profiles, perception, robot execution, dependencies, UI behavior, or calibration constants.",
            "piece_visibility is derived from synthetic capture metadata and gripper geometry, not from real-image segmentation.",
        ],
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
