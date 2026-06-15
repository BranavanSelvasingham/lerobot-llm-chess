#!/usr/bin/env python3

from __future__ import annotations

import argparse
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


def selection_reasons(record: dict[str, Any], recommended_inputs: set[str]) -> list[str]:
    reasons: list[str] = []
    if record.get("currently_wired_into_simulator_tooling") is True:
        reasons.append("currently_wired_into_simulator_tooling")
    relative_path = record.get("relative_path")
    if isinstance(relative_path, str) and relative_path in recommended_inputs:
        reasons.append("next_recommended_reference_fixture_inputs")
    return reasons


def select_reference_records(inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    media = inventory.get("media")
    if not isinstance(media, list):
        return [], [{"reason": "inventory_media_missing", "note": "Inventory does not contain a media list."}]

    recommended_raw = inventory.get("next_recommended_reference_fixture_inputs")
    recommended_inputs = {
        str(value) for value in recommended_raw if isinstance(value, str)
    } if isinstance(recommended_raw, list) else set()

    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in media:
        if not isinstance(item, dict):
            skipped.append({"reason": "invalid_media_record", "media": item})
            continue
        relative_path = item.get("relative_path")
        path_label = relative_path if isinstance(relative_path, str) else "<missing>"
        reasons = selection_reasons(item, recommended_inputs)
        if item.get("media_type") != "image":
            skipped.append({"relative_path": path_label, "reason": "not_image", "media_type": item.get("media_type")})
            continue
        if not reasons:
            skipped.append({"relative_path": path_label, "reason": "not_selected_by_inventory"})
            continue
        selected.append({**item, "selection_reasons": reasons})

    selected.sort(key=lambda record: str(record.get("relative_path") or ""))
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


def build_comparison_record(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    repo_root: Path,
    index: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    relative_path = str(record["relative_path"])
    reference_path = (repo_root / relative_path).resolve()
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
        "relative_path": relative_path,
        "reference_image_path": str(reference_path),
        "selection_reasons": record.get("selection_reasons", []),
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
    selected, skipped = select_reference_records(inventory)
    visibility_gaps = inventory.get("visibility_gaps")
    visibility_gaps = visibility_gaps if isinstance(visibility_gaps, list) else []

    summary_path = output_dir / "comparison_set_summary.json"
    comparisons = [
        build_comparison_record(
            args=args,
            output_dir=output_dir,
            repo_root=repo_root,
            index=index,
            record=record,
        )
        for index, record in enumerate(selected, start=1)
    ]
    selected_count = len(selected)
    failed = [record for record in comparisons if not record["ok"]]
    status = "ok" if selected_count and not failed else "validation_failed"
    if selected_count == 0:
        status = "no_reference_media_selected"

    summary = {
        "schema": SCHEMA,
        "ok": status == "ok",
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
        "selected_media_count": selected_count,
        "skipped_media_count": len(skipped),
        "failed_comparison_count": len(failed),
        "selected_media": [
            {
                "relative_path": record.get("relative_path"),
                "media_type": record.get("media_type"),
                "dimensions": record.get("dimensions"),
                "selection_reasons": record.get("selection_reasons"),
                "currently_wired_into_simulator_tooling": record.get("currently_wired_into_simulator_tooling"),
                "simulator_references": record.get("simulator_references"),
            }
            for record in selected
        ],
        "skipped_media": skipped,
        "visibility_gaps": visibility_gaps,
        "comparisons": comparisons,
        "notes": [
            "Selected image records are those currently wired into simulator tooling or named by next_recommended_reference_fixture_inputs.",
            "Videos and non-selected inventory records are reported as skipped rather than compared.",
        ],
    }
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
