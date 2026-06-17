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
    parser.add_argument(
        "--capture-manifest-check-json",
        type=Path,
        default=None,
        help=(
            "Optional reference_capture_manifest_check.json, or a full calibration_regression_summary.json "
            "containing reference_capture_manifest, to fold into the operator plan."
        ),
    )
    parser.add_argument(
        "--calibration-suite-summary-json",
        type=Path,
        default=None,
        help=(
            "Optional full calibration_regression_summary.json containing reference_capture_manifest. "
            "Equivalent to --capture-manifest-check-json when a suite summary is supplied."
        ),
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


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def reference_capture_manifest_actions(*, ready: bool, manifest_path: str | None) -> list[dict[str, str]]:
    if ready:
        manifest_text = manifest_path or "/absolute/path/to/reference_capture_manifest.json"
        return [
            {
                "id": "validate_sidecars_and_intake",
                "label": "Validate sidecars and intake",
                "operator_action": (
                    "Review the referenced depth, camera, board-pose, and pick/place sidecars through the "
                    "existing real-calibration intake before treating them as comparable residual inputs."
                ),
            },
            {
                "id": "run_suite_with_reference_capture_manifest",
                "label": "Run suite with capture manifest",
                "operator_action": (
                    "Run the calibration regression suite with "
                    f"`--reference-capture-manifest {manifest_text}` so the suite-indexed readiness evidence "
                    "stays beside the real-depth planning artifacts."
                ),
            },
            {
                "id": "compare_residuals_before_calibration_claims",
                "label": "Compare residual evidence",
                "operator_action": (
                    "Use subsequent sidecar validation, real projection intake, and residual comparison artifacts "
                    "before making any physical calibration accuracy claim."
                ),
            },
        ]
    return [
        {
            "id": "collect_depth_reference",
            "label": "Depth reference",
            "operator_action": (
                "Capture or attach a local real SO-101 depth/distance reference with measured metric targets "
                "and camera/board pose context."
            ),
        },
        {
            "id": "collect_pick_place_video",
            "label": "Pick/place video",
            "operator_action": (
                "Capture or attach a local pick/place video that shows fingers, wrist/arm, pickup, release, "
                "and occlusion context."
            ),
        },
        {
            "id": "prepare_sidecars",
            "label": "Sidecars",
            "operator_action": (
                "Provide sidecars for depth measurements, capture metadata, camera intrinsics/extrinsics, "
                "board pose, and reviewed event markers as applicable."
            ),
        },
        {
            "id": "record_provenance_review",
            "label": "Provenance and review",
            "operator_action": (
                "Record operator, capture date/source, camera id, reviewer, review date, and review status "
                "in the manifest or capture entries."
            ),
        },
        {
            "id": "preserve_local_only_no_copy_policy",
            "label": "Local-only no-copy policy",
            "operator_action": (
                "Declare `media_assets_copied_into_repo: false` and a local-only no-copy policy; keep media "
                "outside commits and suite artifact directories."
            ),
        },
    ]


def no_copy_status(evidence: dict[str, Any]) -> dict[str, Any]:
    policy = evidence.get("local_only_no_copy_policy")
    policy = policy if isinstance(policy, dict) else None
    copied = evidence.get("media_assets_copied_into_repo")
    policy_ok = policy.get("ok") if policy is not None else None
    if copied is None and policy is None:
        status = "no_copy_evidence_not_available"
    elif copied is not False:
        status = "missing_media_assets_copied_into_repo_false"
    elif policy_ok is True:
        status = "local_only_no_copy_policy_confirmed"
    elif policy is None:
        status = "local_only_no_copy_policy_not_available"
    else:
        status = "local_only_no_copy_policy_needs_review"
    return {
        "status": status,
        "media_assets_copied_into_repo": copied,
        "local_only_no_copy_policy_ok": policy_ok,
        "local_only_no_copy_policy": policy,
    }


def compact_reference_capture_manifest_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    suite_section = payload.get("reference_capture_manifest")
    if isinstance(suite_section, dict):
        return suite_section, "calibration_regression_summary"
    if (
        payload.get("schema") == "lerobot.sim.reference_capture_manifest_check.v1"
        or "ready_for_calibration_grade_simcamera_tuning" in payload
        or str(payload.get("status") or "").startswith("reference_capture_manifest_")
    ):
        return payload, "reference_capture_manifest_check"
    raise ValueError(
        "capture manifest evidence JSON must be a reference_capture_manifest_check.json "
        "or a calibration_regression_summary.json containing reference_capture_manifest."
    )


def normalize_reference_capture_manifest_evidence(
    *,
    evidence_path: Path | None,
    repo_root: Path,
) -> dict[str, Any]:
    if evidence_path is None:
        evidence = {
            "status": "capture_manifest_evidence_not_supplied",
            "ready_for_calibration_grade_simcamera_tuning": False,
            "manifest_path": None,
            "depth_reference_capture_count": 0,
            "pick_place_video_capture_count": 0,
            "missing_path_count": 0,
            "diagnostics": ["reference_capture_manifest_not_supplied"],
            "gaps": ["reference_capture_manifest_not_supplied"],
            "media_assets_copied_into_repo": None,
            "local_only_no_copy_policy": None,
        }
        source_kind = "not_supplied"
        source_path = None
    else:
        source_path_obj = resolve_path(evidence_path, repo_root=repo_root)
        payload = read_json_object(source_path_obj, label="capture manifest evidence JSON")
        evidence, source_kind = compact_reference_capture_manifest_payload(payload)
        source_path = str(source_path_obj)

    diagnostics = string_list(evidence.get("diagnostics"))
    gaps = string_list(evidence.get("gaps")) or diagnostics
    missing_path_count = int_value(evidence.get("missing_path_count"))
    if not missing_path_count and isinstance(evidence.get("missing_path_checks"), list):
        missing_path_count = len([row for row in evidence["missing_path_checks"] if isinstance(row, dict)])
    ready = bool(evidence.get("ready_for_calibration_grade_simcamera_tuning", False))
    manifest_path = evidence.get("manifest_path") if isinstance(evidence.get("manifest_path"), str) else None
    normalized = {
        "source_path": source_path,
        "source_kind": source_kind,
        "supplied_to_planner": evidence_path is not None,
        "status": evidence.get("status"),
        "manifest_path": manifest_path,
        "summary_path": evidence.get("summary_path"),
        "csv_path": evidence.get("csv_path"),
        "readme_path": evidence.get("readme_path"),
        "ready_for_calibration_grade_simcamera_tuning": ready,
        "depth_reference_capture_count": int_value(evidence.get("depth_reference_capture_count")),
        "pick_place_video_capture_count": int_value(evidence.get("pick_place_video_capture_count")),
        "path_check_count": int_value(evidence.get("path_check_count")),
        "media_path_check_count": int_value(evidence.get("media_path_check_count")),
        "sidecar_path_check_count": int_value(evidence.get("sidecar_path_check_count")),
        "missing_path_count": missing_path_count,
        "diagnostics": diagnostics,
        "gaps": gaps,
        "media_assets_copied_into_repo": evidence.get("media_assets_copied_into_repo"),
        "local_only_no_copy_policy": evidence.get("local_only_no_copy_policy"),
        "provenance_present": evidence.get("provenance_present"),
        "review_present": evidence.get("review_present"),
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "caveat": (
            "Reference capture manifest readiness is an input-readiness gate only; physical calibration "
            "claims still require subsequent sidecar validation, intake, and residual comparison evidence."
        ),
    }
    normalized["no_copy_status"] = no_copy_status(normalized)
    normalized["next_operator_actions"] = reference_capture_manifest_actions(
        ready=ready,
        manifest_path=manifest_path,
    )
    return normalized


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
    reference_capture_manifest_evidence: dict[str, Any],
) -> dict[str, str]:
    manifest_text = repo_relative(manifest_path, repo_root) or str(manifest_path)
    positive_text = repo_relative(positive_manifest_path, repo_root) or str(positive_manifest_path)
    capture_manifest_text = (
        reference_capture_manifest_evidence.get("manifest_path")
        if isinstance(reference_capture_manifest_evidence.get("manifest_path"), str)
        else "/absolute/path/to/reference_capture_manifest.json"
    )
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
        "run_reference_capture_manifest_suite_after_manifest_review": command_block(
            f"{python_text} scripts/smoke_sim_calibration_regression_suite.py",
            f"--python {python_text}",
            f"--reference-capture-manifest {capture_manifest_text}",
            f"--output-dir {output_dir / 'reference_capture_manifest_suite'}",
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
    capture_manifest = summary["reference_capture_manifest_evidence"]
    no_copy = capture_manifest["no_copy_status"]
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
    lines.extend(
        [
            "## Reference Capture Manifest Evidence",
            "",
            f"- Source: `{capture_manifest['source_path'] or 'not supplied'}`",
            f"- Source kind: `{capture_manifest['source_kind']}`",
            f"- Status: `{capture_manifest['status']}`",
            "- Ready for calibration-grade SimCamera tuning inputs: "
            f"`{capture_manifest['ready_for_calibration_grade_simcamera_tuning']}`",
            f"- Depth reference captures: `{capture_manifest['depth_reference_capture_count']}`",
            f"- Pick/place video captures: `{capture_manifest['pick_place_video_capture_count']}`",
            f"- Missing referenced paths: `{capture_manifest['missing_path_count']}`",
            f"- Manifest path: `{capture_manifest['manifest_path'] or 'not available'}`",
            f"- Diagnostics: `{', '.join(capture_manifest['diagnostics']) or 'none'}`",
            f"- Gaps: `{', '.join(capture_manifest['gaps']) or 'none'}`",
            f"- No-copy status: `{no_copy['status']}`",
            f"- Media assets copied into repo: `{capture_manifest['media_assets_copied_into_repo']}`",
            f"- Caveat: {capture_manifest['caveat']}",
            "",
            "## Reference Capture Manifest Next Actions",
            "",
        ]
    )
    for action in capture_manifest["next_operator_actions"]:
        lines.extend(
            [
                f"### {action['label']}",
                "",
                f"- Action: {action['operator_action']}",
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
    if args.capture_manifest_check_json is not None and args.calibration_suite_summary_json is not None:
        raise ValueError(
            "Pass only one of --capture-manifest-check-json or --calibration-suite-summary-json."
        )
    repo_root = args.repo_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = resolve_path(args.manifest, repo_root=repo_root)
    positive_manifest_path = resolve_path(args.real_capture_fixture_manifest, repo_root=repo_root)
    scenario_label = slugify(args.scenario_label or manifest_path.stem)
    capture_manifest_evidence_path = args.capture_manifest_check_json or args.calibration_suite_summary_json

    manifest = analyze_manifest(manifest_path, repo_root=repo_root)
    positive_manifest = analyze_manifest(positive_manifest_path, repo_root=repo_root)
    reference_capture_manifest_evidence = normalize_reference_capture_manifest_evidence(
        evidence_path=capture_manifest_evidence_path,
        repo_root=repo_root,
    )
    commands = build_commands(
        manifest_path=manifest_path,
        manifest=manifest,
        positive_manifest_path=positive_manifest_path,
        output_dir=output_dir,
        repo_root=repo_root,
        python=args.python.expanduser().resolve(),
        reference_capture_manifest_evidence=reference_capture_manifest_evidence,
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
        "reference_capture_manifest_evidence": reference_capture_manifest_evidence,
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
