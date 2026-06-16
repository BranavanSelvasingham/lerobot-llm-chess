#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_depth_capture_plan"
DEFAULT_MISSING_MANIFEST = REPO_ROOT / "test_data" / "real_calibration_sidecars" / "missing_real_depth_manifest.json"
DEFAULT_REAL_CAPTURE_FIXTURE_MANIFEST = (
    REPO_ROOT / "test_data" / "real_calibration_sidecars" / "reference_media_manifest.synthetic_real_capture_test.json"
)
DOCUMENTED_PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3")
DEFAULT_PYTHON = DOCUMENTED_PYTHON if DOCUMENTED_PYTHON.exists() else Path(sys.executable)
SCHEMA = "lerobot.sim.real_depth_capture_session_plan.v1"
SIDECAR_KINDS = ("intrinsics", "extrinsics", "board_pose", "depth")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a hardware-free SO-101 real depth capture operator plan. The plan names the "
            "physical measurements, sidecars, and regression commands needed to unlock "
            "real-vs-sim depth residual evidence."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MISSING_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--python",
        type=Path,
        default=DEFAULT_PYTHON,
        help="Python executable to show in generated commands.",
    )
    parser.add_argument(
        "--scenario-label",
        default=None,
        help="Optional label used in generated filenames and report titles.",
    )
    parser.add_argument(
        "--real-capture-fixture-manifest",
        type=Path,
        default=DEFAULT_REAL_CAPTURE_FIXTURE_MANIFEST,
        help="Synthetic positive fixture manifest used only as a regression command example.",
    )
    return parser.parse_args()


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def resolve_path(path: Path, *, repo_root: Path) -> Path:
    path = path.expanduser()
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def repo_relative(path: Path, repo_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def path_exists(path_text: Any, *, repo_root: Path) -> bool:
    if not isinstance(path_text, str) or not path_text:
        return False
    path = Path(path_text).expanduser()
    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    return resolved.is_file()


def slugify(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "_" for char in value.strip()]
    slug = "_".join("".join(chars).split("_"))
    return slug or "real_depth_capture"


def sidecar_fields(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "intrinsics": entry.get("real_intrinsics_path")
        or entry.get("camera_intrinsics_path")
        or entry.get("intrinsics_path"),
        "extrinsics": entry.get("real_extrinsics_path")
        or entry.get("camera_extrinsics_path")
        or entry.get("extrinsics_path"),
        "board_pose": entry.get("real_board_pose_path")
        or entry.get("board_pose_path")
        or entry.get("board_corner_detections_path")
        or entry.get("board_corners_path"),
        "depth": entry.get("real_depth_path")
        or entry.get("depth_map_path")
        or entry.get("depth_reference_path")
        or entry.get("metric_depth_reference_path"),
    }


def media_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    media = manifest.get("media")
    return [entry for entry in media if isinstance(entry, dict)] if isinstance(media, list) else []


def analyze_manifest(manifest_path: Path, *, repo_root: Path) -> dict[str, Any]:
    exists = manifest_path.is_file()
    if not exists:
        return {
            "path": str(manifest_path),
            "repo_relative_path": repo_relative(manifest_path, repo_root),
            "exists": False,
            "status": "manifest_missing",
            "media": [],
            "sidecar_summary": {"declared": [], "missing": list(SIDECAR_KINDS), "existing": []},
        }

    manifest = read_json_object(manifest_path, label="reference media manifest")
    rows: list[dict[str, Any]] = []
    declared: set[str] = set()
    existing: set[str] = set()
    for index, entry in enumerate(media_entries(manifest), start=1):
        fields = sidecar_fields(entry)
        sidecars: dict[str, Any] = {}
        for kind, value in fields.items():
            if isinstance(value, str) and value:
                declared.add(kind)
                if path_exists(value, repo_root=repo_root):
                    existing.add(kind)
            sidecars[kind] = {
                "path": value,
                "declared": isinstance(value, str) and bool(value),
                "exists": path_exists(value, repo_root=repo_root),
            }
        rows.append(
            {
                "index": index,
                "relative_path": entry.get("relative_path"),
                "capture_id": entry.get("capture_id"),
                "media_exists": path_exists(entry.get("relative_path"), repo_root=repo_root),
                "sidecars": sidecars,
                "declared_tags": entry.get("declared_tags", []),
            }
        )

    missing = [kind for kind in SIDECAR_KINDS if kind not in existing]
    status = "ready_for_real_depth_intake" if not missing and rows else "missing_real_depth_reference_inputs"
    return {
        "path": str(manifest_path),
        "repo_relative_path": repo_relative(manifest_path, repo_root),
        "exists": True,
        "status": status,
        "media": rows,
        "sidecar_summary": {
            "declared": sorted(declared),
            "existing": sorted(existing),
            "missing": missing,
        },
    }


def measurement_tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": "reference_media",
            "label": "Reference image",
            "operator_action": (
                "Capture or select a sharp repo-local SO-101 gripper-camera chessboard frame with all "
                "four board corners visible."
            ),
            "record": ["repo-relative image path", "capture_id", "camera_id", "image_size_px"],
            "sidecar": "reference media manifest entry",
        },
        {
            "id": "intrinsics",
            "label": "Camera intrinsics",
            "operator_action": "Calibrate the physical camera with a real target for the same resolution used by the frame.",
            "record": ["camera_matrix_px", "distortion_coefficients", "distortion_model", "calibration_source"],
            "sidecar": "real_intrinsics_path",
        },
        {
            "id": "extrinsics",
            "label": "Camera-to-board transform",
            "operator_action": (
                "Solve or measure the physical camera pose relative to the chessboard using the documented "
                "OpenCV camera frame convention."
            ),
            "record": ["transform_convention", "transform.matrix_4x4 or translation_m plus rotation_matrix"],
            "sidecar": "real_extrinsics_path",
        },
        {
            "id": "board_pose",
            "label": "Board corner detections",
            "operator_action": "Mark the board corners in strict a1,h1,h8,a8 order in the captured image.",
            "record": ["corner_order", "corners[].label", "corners[].pixel_xy", "board_size_m if known"],
            "sidecar": "board_corner_detections_path",
        },
        {
            "id": "depth",
            "label": "Depth references",
            "operator_action": (
                "Measure camera range or z-depth to board_center, piece_center, piece_top, or target_square "
                "with units and scale, or attach depth-map metadata."
            ),
            "record": ["depth_units", "depth_scale_to_m", "reference_frame", "metric_references[].distance_m"],
            "sidecar": "depth_reference_path",
        },
    ]


def command_block(*parts: str) -> str:
    return " \\\n  ".join(parts)


def build_commands(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    positive_manifest_path: Path,
    output_dir: Path,
    repo_root: Path,
    python: Path,
) -> dict[str, str]:
    manifest_text = repo_relative(manifest_path, repo_root) or str(manifest_path)
    positive_text = repo_relative(positive_manifest_path, repo_root) or str(positive_manifest_path)
    python_text = str(python)
    real_capture_sidecars_dir = output_dir / "real_capture_sidecars"
    commands = {
        "generate_capture_sidecars_after_measurement": command_block(
            f"{python_text} scripts/prepare_real_calibration_capture_sidecars.py",
            "--image-path path/to/real_so101_depth_capture.jpg",
            "--capture-id so101_depth_capture_001",
            "--camera-id so101_gripper_camera",
            "--image-size 640x480",
            "--camera-matrix-json '[[fx,0,cx],[0,fy,cy],[0,0,1]]'",
            "--distortion-json '[k1,k2,p1,p2,k3]'",
            "--corner a1:x,y --corner h1:x,y --corner h8:x,y --corner a8:x,y",
            "--distance board_center:0.500:x,y",
            "--real-capture",
            "--require intrinsics --require extrinsics --require board_pose --require depth",
            f"--output-dir {real_capture_sidecars_dir}",
        ),
        "validate_generated_capture_manifest_after_measurement": command_block(
            f"{python_text} scripts/smoke_sim_real_calibration_sidecars.py",
            f"--manifest {real_capture_sidecars_dir / 'reference_media_manifest.generated_sidecars.json'}",
            "--require-valid-count 4",
            f"--output-dir {output_dir / 'generated_sidecar_validation'}",
        ),
        "run_default_missing_reference_suite": command_block(
            f"{python_text} scripts/smoke_sim_calibration_regression_suite.py",
            f"--python {python_text}",
            f"--output-dir {output_dir / 'default_missing_reference_suite'}",
        ),
        "run_real_capture_fixture_suite": command_block(
            f"{python_text} scripts/smoke_sim_calibration_regression_suite.py",
            f"--python {python_text}",
            f"--reference-media-manifest {positive_text}",
            f"--output-dir {output_dir / 'synthetic_real_capture_fixture_suite'}",
        ),
    }
    if manifest.get("exists") is True:
        return {
            "validate_selected_manifest": command_block(
                f"{python_text} scripts/smoke_sim_real_calibration_sidecars.py",
                f"--manifest {manifest_text}",
                f"--output-dir {output_dir / 'selected_manifest_sidecar_validation'}",
            ),
            **commands,
        }
    return commands


def build_markdown(summary: dict[str, Any]) -> str:
    manifest = summary["manifest"]
    positive_manifest = summary["synthetic_positive_fixture_manifest"]
    lines = [
        "# Real Depth Capture Operator Plan",
        "",
        "This is a hardware-free planning artifact. It did not open a camera, move SO-101 motors, start GUI paths, or call OpenAI.",
        "",
        "## Current Manifest",
        "",
        f"- Manifest: `{manifest['repo_relative_path'] or manifest['path']}`",
        f"- Status: `{manifest['status']}`",
        f"- Existing sidecars: `{', '.join(manifest['sidecar_summary']['existing']) or 'none'}`",
        f"- Missing sidecars: `{', '.join(manifest['sidecar_summary']['missing']) or 'none'}`",
        f"- Synthetic positive fixture for regression only: `{positive_manifest['repo_relative_path'] or positive_manifest['path']}`",
        "",
    ]
    if manifest.get("exists") is not True:
        lines.extend(
            [
                "There is no current manifest to validate yet. Generate real-capture sidecars first, then validate the generated manifest from `real_capture_sidecars/reference_media_manifest.generated_sidecars.json`.",
                "",
            ]
        )
    lines.extend(["## Measurements To Collect", ""])
    for task in summary["measurement_tasks"]:
        lines.extend(
            [
                f"### {task['label']}",
                "",
                f"- Action: {task['operator_action']}",
                f"- Record: `{', '.join(task['record'])}`",
                f"- Produces: `{task['sidecar']}`",
                "",
            ]
        )

    lines.extend(["## Commands After Capture", ""])
    for label, command in summary["commands"].items():
        lines.extend([f"### {label}", "", "```bash", command, "```", ""])

    lines.extend(
        [
            "## Expected Scorecard Signals",
            "",
            "- Before real sidecars: `visual_review/pick_place_depth_distance_scorecard.json` should report `real_depth_reference.status: missing_real_depth_reference`.",
            "- With real_capture sidecars: the suite should emit `real_projection_intake/real_projection_residuals.json`, `.csv`, and `real_projection_residual_overlay_contact_sheet.png`, and the scorecard should report `real_depth_comparable`.",
            "- Synthetic fixtures prove only report plumbing; they are not physical SO-101 calibration truth.",
            "",
        ]
    )
    return "\n".join(lines)


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = resolve_path(args.manifest, repo_root=repo_root)
    positive_manifest_path = resolve_path(args.real_capture_fixture_manifest, repo_root=repo_root)
    scenario_label = slugify(args.scenario_label or manifest_path.stem)

    manifest = analyze_manifest(manifest_path, repo_root=repo_root)
    positive_manifest = analyze_manifest(positive_manifest_path, repo_root=repo_root)
    commands = build_commands(
        manifest_path=manifest_path,
        manifest=manifest,
        positive_manifest_path=positive_manifest_path,
        output_dir=output_dir,
        repo_root=repo_root,
        python=args.python.expanduser().resolve(),
    )
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": "ok",
        "scenario_label": scenario_label,
        "output_dir": str(output_dir),
        "repo_root": str(repo_root),
        "python": str(args.python.expanduser().resolve()),
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "robot_motion_skipped": True,
        "openai_skipped": True,
        "manifest": manifest,
        "synthetic_positive_fixture_manifest": positive_manifest,
        "current_manifest_validation": {
            "available": manifest.get("exists") is True,
            "status": "available" if manifest.get("exists") is True else "not_available_until_manifest_exists",
            "note": (
                "Validate the selected manifest before capture-sidecar generation."
                if manifest.get("exists") is True
                else "No selected manifest exists yet; validate the generated capture manifest after running prepare_real_calibration_capture_sidecars.py."
            ),
        },
        "measurement_tasks": measurement_tasks(),
        "commands": commands,
        "artifacts": {
            "json": str(output_dir / f"{scenario_label}_real_depth_capture_plan.json"),
            "markdown": str(output_dir / f"{scenario_label}_real_depth_capture_plan.md"),
        },
        "notes": [
            "The planner is an operator package, not a calibration solver.",
            "Only user-supplied physical measurements should be marked real_capture=true.",
            "Synthetic real_capture fixtures exist only to prove residual and scorecard plumbing.",
        ],
    }
    write_json(Path(summary["artifacts"]["json"]), summary)
    write_text(Path(summary["artifacts"]["markdown"]), build_markdown(summary))
    return summary


def main() -> int:
    args = parse_args()
    try:
        summary = build_summary(args)
    except ValueError as exc:
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "status": "invalid_plan_inputs",
            "output_dir": str(output_dir),
            "error": str(exc),
            "hardware_skipped": True,
            "gui_skipped": True,
            "real_camera_capture_skipped": True,
            "robot_motion_skipped": True,
            "openai_skipped": True,
        }
        write_json(output_dir / "real_depth_capture_plan_error.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
