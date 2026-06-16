#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Keep OpenMP-backed imports and subprocess children stable in headless sandboxes.
os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from lerobot.sim.config import CURRENT_GRIPPER_REFERENCE_PROFILE, SIM_CAMERA_CALIBRATION_PROFILES

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "simcamera_tuning_before_after"
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
PROFILE_SWEEP_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_profile_calibration_sweep.py"
SUMMARY_NAME = "simcamera_tuning_before_after_summary.json"
CSV_NAME = "simcamera_tuning_before_after_rows.csv"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.simcamera_tuning_before_after.v1"
CAVEAT = (
    "Full-frame image delta is hardware-free coarse review evidence only; it is not physical "
    "calibration truth and does not replace real depth or pick/place video references."
)
OPEN_REFERENCE_GAPS = {
    "missing_real_depth_reference": True,
    "missing_pick_place_video": True,
    "notes": [
        "This focused smoke does not ingest or validate real depth sidecars.",
        "This focused smoke does not ingest or validate pick/place video captures.",
        "Those gaps remain open unless separate reviewed real sidecars/captures are supplied.",
    ],
}


@dataclass(frozen=True)
class ChildRun:
    role: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    summary_path: Path


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic before/after SimCamera profile sweeps for a documented "
            "baseline gripper-finger-width override versus the current canonical profile."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reference-image", type=Path, default=DEFAULT_REFERENCE_IMAGE)
    parser.add_argument(
        "--profile",
        choices=sorted(SIM_CAMERA_CALIBRATION_PROFILES),
        default=CURRENT_GRIPPER_REFERENCE_PROFILE,
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child profile sweep invocations.",
    )
    parser.add_argument(
        "--baseline-gripper-finger-width-px",
        type=positive_int,
        default=72,
        help="Baseline gripper finger width override for the before sweep.",
    )
    parser.add_argument(
        "--marker-time-seconds",
        type=float,
        default=0.0,
        help="Fixed SimCamera marker timestamp forwarded to both profile sweeps.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def fmt_float(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.6f}"


def path_exists(path_value: Any) -> bool:
    return isinstance(path_value, str) and Path(path_value).exists()


def missing_dependency_names(output: str) -> list[str]:
    names: set[str] = set()
    for match in re.finditer(r"No module named ['\"]([^'\"]+)['\"]", output):
        top_level = match.group(1).split(".", maxsplit=1)[0]
        if top_level in {"cv2", "numpy", "PIL"}:
            names.add(top_level)
    if "OpenCV" in output or "cv2" in output and "ImportError" in output:
        names.add("cv2")
    if "numpy" in output and "ImportError" in output:
        names.add("numpy")
    return sorted(names)


def run_profile_sweep(
    *,
    role: str,
    python: Path,
    output_dir: Path,
    reference_image: Path,
    profile: str,
    marker_time_seconds: float,
    gripper_finger_width_px: int | None,
) -> ChildRun:
    command = [
        str(python),
        str(PROFILE_SWEEP_SCRIPT),
        "--output-dir",
        str(output_dir),
        "--reference-image",
        str(reference_image),
        "--profile",
        profile,
        "--marker-time-seconds",
        str(float(marker_time_seconds)),
    ]
    if gripper_finger_width_px is not None:
        command.extend(["--gripper-finger-width-px", str(int(gripper_finger_width_px))])
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
        check=False,
    )
    return ChildRun(
        role=role,
        command=command,
        returncode=int(result.returncode),
        stdout=result.stdout,
        stderr=result.stderr,
        summary_path=output_dir / "summary.json",
    )


def candidate_by_name(summary: dict[str, Any], name: str) -> dict[str, Any]:
    for candidate in summary.get("candidates", []):
        if candidate.get("name") == name:
            return candidate
    raise AssertionError(f"Missing candidate {name!r} in {summary.get('output_dir')}")


def candidate_metrics(candidate: dict[str, Any]) -> dict[str, float]:
    metrics = candidate.get("metrics", {})
    return {
        "mean_abs_delta": float(metrics["mean_abs_delta"]),
        "rmse": float(metrics["rmse"]),
    }


def metric_delta(lhs: dict[str, Any], rhs: dict[str, Any]) -> dict[str, float]:
    lhs_metrics = candidate_metrics(lhs)
    rhs_metrics = candidate_metrics(rhs)
    return {
        "mean_abs_delta": lhs_metrics["mean_abs_delta"] - rhs_metrics["mean_abs_delta"],
        "rmse": lhs_metrics["rmse"] - rhs_metrics["rmse"],
    }


def artifact_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "summary_path",
        "candidate_montage_path",
        "candidate_dir",
        "current_overlay_path",
        "current_absolute_difference_path",
        "current_side_by_side_path",
        "best_overlay_path",
        "best_absolute_difference_path",
        "best_side_by_side_path",
    ]
    selected = {key: artifacts.get(key) for key in keys}
    selected["exists"] = {key: path_exists(value) for key, value in selected.items()}
    return selected


def ranked_candidates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = list(summary.get("candidates", []))
    return sorted(
        candidates,
        key=lambda candidate: (
            float(candidate.get("metrics", {}).get("mean_abs_delta", float("inf"))),
            float(candidate.get("metrics", {}).get("rmse", float("inf"))),
            str(candidate.get("name", "")),
        ),
    )


def tuning_prompts(summary: dict[str, Any], *, role: str, limit: int = 5) -> list[dict[str, Any]]:
    current = candidate_by_name(summary, "current")
    prompts: list[dict[str, Any]] = []
    for candidate in ranked_candidates(summary):
        if candidate.get("name") == "current":
            continue
        prompts.append(
            {
                "sweep": role,
                "candidate": candidate.get("name"),
                "description": candidate.get("description"),
                "overrides": candidate.get("overrides", {}),
                "mean_abs_delta": candidate_metrics(candidate)["mean_abs_delta"],
                "rmse": candidate_metrics(candidate)["rmse"],
                "delta_vs_current": metric_delta(candidate, current),
                "prompt_scope": "review_prompt_only_not_canonical_profile_update",
            }
        )
        if len(prompts) >= limit:
            break
    return prompts


def validate_artifacts(sweep: dict[str, Any], *, role: str) -> None:
    artifacts = artifact_summary(sweep.get("artifacts", {}))
    missing = [key for key, exists in artifacts["exists"].items() if not exists]
    if missing:
        raise AssertionError(f"{role} sweep is missing expected artifacts: {', '.join(missing)}")


def summarize_sweep(
    summary: dict[str, Any],
    *,
    role: str,
    expected_gripper_finger_width_px: int,
) -> dict[str, Any]:
    validate_artifacts(summary, role=role)
    current = candidate_by_name(summary, "current")
    best_name = str(summary.get("selection", {}).get("best_candidate"))
    best = candidate_by_name(summary, best_name)
    current_metrics = candidate_metrics(current)
    best_metrics = candidate_metrics(best)
    current_gripper = current.get("gripper", {})
    best_gripper = best.get("gripper", {})
    return {
        "role": role,
        "profile": summary.get("profile"),
        "profile_values": summary.get("profile_values", {}),
        "effective_profile_values": summary.get("effective_profile_values", {}),
        "expected_gripper_finger_width_px": int(expected_gripper_finger_width_px),
        "current_candidate_gripper_finger_width_px": int(current_gripper["finger_width_px"]),
        "marker_time_seconds": float(summary.get("marker_time_seconds", 0.0)),
        "candidate_count": int(summary.get("image", {}).get("candidate_count", 0)),
        "current_candidate": {
            "name": current.get("name"),
            "description": current.get("description"),
            "metrics": current_metrics,
            "gripper_overlay_inputs": current_gripper,
        },
        "best_candidate": {
            "name": best.get("name"),
            "description": best.get("description"),
            "overrides": best.get("overrides", {}),
            "metrics": best_metrics,
            "gripper_overlay_inputs": best_gripper,
        },
        "best_minus_current": metric_delta(best, current),
        "remaining_tuning_prompts": tuning_prompts(summary, role=role),
        "artifacts": artifact_summary(summary.get("artifacts", {})),
        "ranked_candidates": [
            {
                "rank": index + 1,
                "name": candidate.get("name"),
                "description": candidate.get("description"),
                "overrides": candidate.get("overrides", {}),
                "metrics": candidate_metrics(candidate),
            }
            for index, candidate in enumerate(ranked_candidates(summary))
        ],
    }


def make_csv_rows(
    *,
    baseline: dict[str, Any],
    current: dict[str, Any],
    deltas: dict[str, Any],
    prompt_text: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sweep in (baseline, current):
        is_current = sweep["role"] == "current"
        artifacts = sweep["artifacts"]
        rows.append(
            {
                "row_type": "sweep_summary",
                "sweep": sweep["role"],
                "profile": sweep["profile"],
                "gripper_finger_width_px": sweep["current_candidate_gripper_finger_width_px"],
                "marker_time_seconds": sweep["marker_time_seconds"],
                "candidate_count": sweep["candidate_count"],
                "current_candidate": sweep["current_candidate"]["name"],
                "best_candidate": sweep["best_candidate"]["name"],
                "current_mean_abs_delta": fmt_float(
                    sweep["current_candidate"]["metrics"]["mean_abs_delta"]
                ),
                "current_rmse": fmt_float(sweep["current_candidate"]["metrics"]["rmse"]),
                "best_mean_abs_delta": fmt_float(sweep["best_candidate"]["metrics"]["mean_abs_delta"]),
                "best_rmse": fmt_float(sweep["best_candidate"]["metrics"]["rmse"]),
                "best_minus_current_mean_abs_delta": fmt_float(
                    sweep["best_minus_current"]["mean_abs_delta"]
                ),
                "best_minus_current_rmse": fmt_float(sweep["best_minus_current"]["rmse"]),
                "current_vs_baseline_current_mean_abs_delta": fmt_float(
                    deltas["current_profile_delta_vs_baseline_current_candidate"]["mean_abs_delta"]
                    if is_current
                    else None
                ),
                "current_vs_baseline_current_rmse": fmt_float(
                    deltas["current_profile_delta_vs_baseline_current_candidate"]["rmse"]
                    if is_current
                    else None
                ),
                "best_vs_baseline_best_mean_abs_delta": fmt_float(
                    deltas["current_best_delta_vs_baseline_best_candidate"]["mean_abs_delta"]
                    if is_current
                    else None
                ),
                "best_vs_baseline_best_rmse": fmt_float(
                    deltas["current_best_delta_vs_baseline_best_candidate"]["rmse"]
                    if is_current
                    else None
                ),
                "artifact_summary_path": artifacts.get("summary_path", ""),
                "artifact_montage_path": artifacts.get("candidate_montage_path", ""),
                "artifact_current_overlay_path": artifacts.get("current_overlay_path", ""),
                "artifact_current_absolute_difference_path": artifacts.get(
                    "current_absolute_difference_path", ""
                ),
                "artifact_current_side_by_side_path": artifacts.get("current_side_by_side_path", ""),
                "artifact_best_overlay_path": artifacts.get("best_overlay_path", ""),
                "artifact_best_absolute_difference_path": artifacts.get(
                    "best_absolute_difference_path", ""
                ),
                "artifact_best_side_by_side_path": artifacts.get("best_side_by_side_path", ""),
                "remaining_tuning_prompts": prompt_text,
                "missing_real_depth_reference": "true",
                "missing_pick_place_video": "true",
                "media_assets_copied_into_repo": "false",
                "caveat": CAVEAT,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_type",
        "sweep",
        "profile",
        "gripper_finger_width_px",
        "marker_time_seconds",
        "candidate_count",
        "current_candidate",
        "best_candidate",
        "current_mean_abs_delta",
        "current_rmse",
        "best_mean_abs_delta",
        "best_rmse",
        "best_minus_current_mean_abs_delta",
        "best_minus_current_rmse",
        "current_vs_baseline_current_mean_abs_delta",
        "current_vs_baseline_current_rmse",
        "best_vs_baseline_best_mean_abs_delta",
        "best_vs_baseline_best_rmse",
        "artifact_summary_path",
        "artifact_montage_path",
        "artifact_current_overlay_path",
        "artifact_current_absolute_difference_path",
        "artifact_current_side_by_side_path",
        "artifact_best_overlay_path",
        "artifact_best_absolute_difference_path",
        "artifact_best_side_by_side_path",
        "remaining_tuning_prompts",
        "missing_real_depth_reference",
        "missing_pick_place_video",
        "media_assets_copied_into_repo",
        "caveat",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(path: Path, payload: dict[str, Any]) -> None:
    baseline = payload["sweeps"]["baseline"]
    current = payload["sweeps"]["current"]
    deltas = payload["deltas"]
    lines = [
        "# SimCamera Tuning Before/After Smoke",
        "",
        "This hardware-free smoke compares a documented baseline SimCamera gripper-reference",
        "profile override against the current canonical profile by reusing the deterministic",
        "`smoke_sim_profile_calibration_sweep.py` renderer.",
        "",
        "## Sweep Summary",
        "",
        "| sweep | profile | finger width px | candidates | current MAD / RMSE | best candidate | best MAD / RMSE | best-current MAD / RMSE |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for sweep in (baseline, current):
        current_metrics = sweep["current_candidate"]["metrics"]
        best_metrics = sweep["best_candidate"]["metrics"]
        best_minus_current = sweep["best_minus_current"]
        lines.append(
            "| {role} | {profile} | {width} | {count} | {current_mad} / {current_rmse} | "
            "{best_name} | {best_mad} / {best_rmse} | {delta_mad} / {delta_rmse} |".format(
                role=sweep["role"],
                profile=sweep["profile"],
                width=sweep["current_candidate_gripper_finger_width_px"],
                count=sweep["candidate_count"],
                current_mad=fmt_float(current_metrics["mean_abs_delta"]),
                current_rmse=fmt_float(current_metrics["rmse"]),
                best_name=sweep["best_candidate"]["name"],
                best_mad=fmt_float(best_metrics["mean_abs_delta"]),
                best_rmse=fmt_float(best_metrics["rmse"]),
                delta_mad=fmt_float(best_minus_current["mean_abs_delta"]),
                delta_rmse=fmt_float(best_minus_current["rmse"]),
            )
        )
    lines.extend(
        [
            "",
            "## Before/After Deltas",
            "",
            "| comparison | MAD delta | RMSE delta |",
            "| --- | ---: | ---: |",
            "| current profile current-candidate minus baseline current-candidate | "
            f"{fmt_float(deltas['current_profile_delta_vs_baseline_current_candidate']['mean_abs_delta'])} | "
            f"{fmt_float(deltas['current_profile_delta_vs_baseline_current_candidate']['rmse'])} |",
            "| current best-candidate minus baseline best-candidate | "
            f"{fmt_float(deltas['current_best_delta_vs_baseline_best_candidate']['mean_abs_delta'])} | "
            f"{fmt_float(deltas['current_best_delta_vs_baseline_best_candidate']['rmse'])} |",
            "| current best-candidate minus baseline current-candidate | "
            f"{fmt_float(deltas['current_best_delta_vs_baseline_current_candidate']['mean_abs_delta'])} | "
            f"{fmt_float(deltas['current_best_delta_vs_baseline_current_candidate']['rmse'])} |",
            "",
            "Negative deltas mean the current side has lower full-frame error for that comparison.",
            "",
            "## Artifacts",
            "",
        ]
    )
    for sweep in (baseline, current):
        lines.extend(
            [
                f"### {sweep['role'].title()}",
                "",
                f"- Summary: `{sweep['artifacts']['summary_path']}`",
                f"- Montage: `{sweep['artifacts']['candidate_montage_path']}`",
                f"- Current overlay: `{sweep['artifacts']['current_overlay_path']}`",
                f"- Current difference: `{sweep['artifacts']['current_absolute_difference_path']}`",
                f"- Current side-by-side: `{sweep['artifacts']['current_side_by_side_path']}`",
                f"- Best overlay: `{sweep['artifacts']['best_overlay_path']}`",
                f"- Best difference: `{sweep['artifacts']['best_absolute_difference_path']}`",
                f"- Best side-by-side: `{sweep['artifacts']['best_side_by_side_path']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Remaining Review Prompts",
            "",
        ]
    )
    for prompt in payload["remaining_tuning_prompts"]:
        lines.append(
            f"- {prompt['sweep']}: `{prompt['candidate']}` - {prompt['description']} "
            f"(MAD delta vs current {fmt_float(prompt['delta_vs_current']['mean_abs_delta'])}, "
            f"RMSE delta vs current {fmt_float(prompt['delta_vs_current']['rmse'])})"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            f"- {CAVEAT}",
            "- `media_assets_copied_into_repo: false`; the smoke reads the configured reference image and writes generated artifacts only under the output directory.",
            "- Missing real depth reference remains open unless separate reviewed real sidecars exist.",
            "- Missing pick/place video remains open unless separate reviewed real captures exist.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def command_payload(run: ChildRun) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": run.role,
        "command": run.command,
        "returncode": run.returncode,
        "summary_path": str(run.summary_path),
    }
    if run.returncode != 0 or run.stderr:
        payload["stdout_tail"] = run.stdout[-2000:]
        payload["stderr_tail"] = run.stderr[-2000:]
    return payload


def write_failure_artifacts(
    *,
    output_dir: Path,
    status: str,
    child_runs: list[ChildRun],
    message: str,
    missing_dependencies: list[str] | None = None,
) -> dict[str, Any]:
    summary_path = output_dir / SUMMARY_NAME
    csv_path = output_dir / CSV_NAME
    readme_path = output_dir / README_NAME
    payload = {
        "ok": False,
        "status": status,
        "schema": SCHEMA,
        "scenario": "simcamera_tuning_before_after",
        "message": message,
        "missing_dependencies": missing_dependencies or [],
        "media_assets_copied_into_repo": False,
        "open_reference_gaps": OPEN_REFERENCE_GAPS,
        "child_commands": [command_payload(run) for run in child_runs],
        "artifacts": {
            "summary_path": str(summary_path),
            "csv_path": str(csv_path),
            "readme_path": str(readme_path),
        },
    }
    write_json(summary_path, payload)
    write_csv(
        csv_path,
        [
            {
                "row_type": status,
                "sweep": run.role,
                "profile": "",
                "gripper_finger_width_px": "",
                "marker_time_seconds": "",
                "candidate_count": "",
                "current_candidate": "",
                "best_candidate": "",
                "current_mean_abs_delta": "",
                "current_rmse": "",
                "best_mean_abs_delta": "",
                "best_rmse": "",
                "best_minus_current_mean_abs_delta": "",
                "best_minus_current_rmse": "",
                "current_vs_baseline_current_mean_abs_delta": "",
                "current_vs_baseline_current_rmse": "",
                "best_vs_baseline_best_mean_abs_delta": "",
                "best_vs_baseline_best_rmse": "",
                "artifact_summary_path": str(run.summary_path),
                "artifact_montage_path": "",
                "artifact_current_overlay_path": "",
                "artifact_current_absolute_difference_path": "",
                "artifact_current_side_by_side_path": "",
                "artifact_best_overlay_path": "",
                "artifact_best_absolute_difference_path": "",
                "artifact_best_side_by_side_path": "",
                "remaining_tuning_prompts": "",
                "missing_real_depth_reference": "true",
                "missing_pick_place_video": "true",
                "media_assets_copied_into_repo": "false",
                "caveat": CAVEAT,
            }
            for run in child_runs
        ],
    )
    lines = [
        "# SimCamera Tuning Before/After Smoke",
        "",
        f"Status: `{status}`",
        "",
        message,
        "",
        f"Missing dependencies: `{', '.join(missing_dependencies or []) or 'none'}`",
        "",
        "No media assets were copied into the repository.",
    ]
    readme_path.write_text("\n".join(lines) + "\n")
    return payload


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    reference_image = args.reference_image.expanduser().resolve()
    python = args.python.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    profile_values = SIM_CAMERA_CALIBRATION_PROFILES[str(args.profile)]
    current_gripper_finger_width_px = int(profile_values.get("gripper_finger_width_px") or 72)
    marker_time_seconds = float(args.marker_time_seconds)

    child_runs = [
        run_profile_sweep(
            role="baseline",
            python=python,
            output_dir=output_dir / "baseline_profile_sweep",
            reference_image=reference_image,
            profile=str(args.profile),
            marker_time_seconds=marker_time_seconds,
            gripper_finger_width_px=int(args.baseline_gripper_finger_width_px),
        )
    ]
    if child_runs[-1].returncode == 0:
        child_runs.append(
            run_profile_sweep(
                role="current",
                python=python,
                output_dir=output_dir / "current_profile_sweep",
                reference_image=reference_image,
                profile=str(args.profile),
                marker_time_seconds=marker_time_seconds,
                gripper_finger_width_px=None,
            )
        )

    for run in child_runs:
        if run.returncode != 0:
            missing_dependencies = missing_dependency_names(run.stdout + "\n" + run.stderr)
            if missing_dependencies:
                payload = write_failure_artifacts(
                    output_dir=output_dir,
                    status="dependency_unavailable",
                    child_runs=child_runs,
                    message=(
                        "A child profile sweep could not run because rendering dependencies are "
                        "unavailable. This is recorded as non-destructive diagnostics."
                    ),
                    missing_dependencies=missing_dependencies,
                )
                print(json.dumps(payload, indent=2))
                return 0
            payload = write_failure_artifacts(
                output_dir=output_dir,
                status="child_profile_sweep_failed",
                child_runs=child_runs,
                message="A child profile sweep failed in the normal repo environment.",
            )
            print(json.dumps(payload, indent=2))
            return run.returncode or 1

    try:
        baseline_raw = load_json(child_runs[0].summary_path)
        current_raw = load_json(child_runs[1].summary_path)
        baseline = summarize_sweep(
            baseline_raw,
            role="baseline",
            expected_gripper_finger_width_px=int(args.baseline_gripper_finger_width_px),
        )
        current = summarize_sweep(
            current_raw,
            role="current",
            expected_gripper_finger_width_px=current_gripper_finger_width_px,
        )
    except Exception as exc:
        payload = write_failure_artifacts(
            output_dir=output_dir,
            status="summary_extraction_failed",
            child_runs=child_runs,
            message=f"Failed to load or validate child sweep summaries: {exc}",
        )
        print(json.dumps(payload, indent=2))
        return 1

    baseline_current = candidate_by_name(baseline_raw, "current")
    current_current = candidate_by_name(current_raw, "current")
    baseline_best = candidate_by_name(baseline_raw, baseline["best_candidate"]["name"])
    current_best = candidate_by_name(current_raw, current["best_candidate"]["name"])
    deltas = {
        "current_profile_delta_vs_baseline_current_candidate": metric_delta(
            current_current, baseline_current
        ),
        "current_best_delta_vs_baseline_best_candidate": metric_delta(current_best, baseline_best),
        "current_best_delta_vs_baseline_current_candidate": metric_delta(
            current_best, baseline_current
        ),
    }
    prompts = baseline["remaining_tuning_prompts"] + current["remaining_tuning_prompts"]
    prompt_text = " | ".join(f"{item['sweep']}:{item['candidate']}" for item in prompts)
    summary_path = output_dir / SUMMARY_NAME
    csv_path = output_dir / CSV_NAME
    readme_path = output_dir / README_NAME
    payload = {
        "ok": True,
        "status": "ok",
        "schema": SCHEMA,
        "scenario": "simcamera_tuning_before_after",
        "profile": str(args.profile),
        "reference_image_path": str(reference_image),
        "output_dir": str(output_dir),
        "baseline_gripper_finger_width_px": int(args.baseline_gripper_finger_width_px),
        "current_gripper_finger_width_px": current_gripper_finger_width_px,
        "marker_time_seconds": marker_time_seconds,
        "media_assets_copied_into_repo": False,
        "sweeps": {
            "baseline": baseline,
            "current": current,
        },
        "deltas": deltas,
        "remaining_tuning_prompts": prompts,
        "open_reference_gaps": OPEN_REFERENCE_GAPS,
        "caveats": [
            CAVEAT,
            "The baseline override is review evidence only and does not mutate canonical SimCamera constants.",
            "The current sweep records the canonical profile as checked out in this repository.",
        ],
        "child_commands": [command_payload(run) for run in child_runs],
        "artifacts": {
            "summary_path": str(summary_path),
            "csv_path": str(csv_path),
            "readme_path": str(readme_path),
            "baseline_profile_sweep_dir": str(output_dir / "baseline_profile_sweep"),
            "current_profile_sweep_dir": str(output_dir / "current_profile_sweep"),
        },
    }
    rows = make_csv_rows(
        baseline=baseline,
        current=current,
        deltas=deltas,
        prompt_text=prompt_text,
    )
    write_json(summary_path, payload)
    write_csv(csv_path, rows)
    write_readme(readme_path, payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
