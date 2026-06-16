#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SUITE_SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
ARTIFACT_INDEX_SCHEMA = "lerobot.sim.calibration_artifact_index.v1"
EVIDENCE_SCHEMA = "lerobot.sim.depth_calibration_evidence_bundle.v1"
DEFAULT_JSON_NAME = "sim_evidence_bundle.json"
DEFAULT_MD_NAME = "sim_evidence_bundle.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a focused hardware-free depth-calibration evidence bundle from an "
            "existing simulator calibration regression suite summary or artifact index."
        )
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="Path to calibration_regression_summary.json or artifact_index.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for sim_evidence_bundle.md/json. Defaults to "
            "<suite-output>/evidence_bundle."
        ),
    )
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--capture-plan-json",
        type=Path,
        default=None,
        help="Optional real-depth capture operator plan JSON to link into the bundle.",
    )
    parser.add_argument(
        "--capture-plan-md",
        type=Path,
        default=None,
        help="Optional real-depth capture operator plan Markdown to link into the bundle.",
    )
    return parser.parse_args()


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def resolve_path(value: str | Path, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def load_inputs(input_json: Path) -> tuple[dict[str, Any], dict[str, Any] | None, Path, Path]:
    input_json = input_json.expanduser().resolve()
    payload = read_json_object(input_json, label="input JSON")
    schema = payload.get("schema")

    if schema == SUITE_SCHEMA or "artifact_index" in payload:
        suite = payload
        output_dir = resolve_path(str(suite.get("output_dir") or input_json.parent), base_dir=input_json.parent)
        index = None
        artifact_index = suite.get("artifact_index")
        artifact_index = artifact_index if isinstance(artifact_index, dict) else {}
        artifact_index_path_value = artifact_index.get("path")
        if isinstance(artifact_index_path_value, str) and artifact_index_path_value:
            artifact_index_path = resolve_path(artifact_index_path_value, base_dir=input_json.parent)
            if artifact_index_path.is_file():
                index = read_json_object(artifact_index_path, label="artifact index")
        return suite, index, output_dir, input_json

    if schema == ARTIFACT_INDEX_SCHEMA or "artifacts" in payload:
        index = payload
        output_dir = resolve_path(str(index.get("output_dir") or input_json.parent), base_dir=input_json.parent)
        suite = None
        suite_summary_path_value = index.get("suite_summary_path")
        if isinstance(suite_summary_path_value, str) and suite_summary_path_value:
            suite_path = resolve_path(suite_summary_path_value, base_dir=input_json.parent)
            if suite_path.is_file():
                suite = read_json_object(suite_path, label="suite summary")
        return suite or {}, index, output_dir, input_json

    raise ValueError(
        f"{input_json} is neither a calibration regression suite summary nor an artifact index."
    )


def nested_get(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def artifact_rows(index: dict[str, Any] | None) -> list[dict[str, Any]]:
    artifacts = index.get("artifacts") if isinstance(index, dict) else None
    return [row for row in artifacts if isinstance(row, dict)] if isinstance(artifacts, list) else []


def find_artifact(index: dict[str, Any] | None, *, label: str) -> dict[str, Any] | None:
    for artifact in artifact_rows(index):
        if artifact.get("label") == label:
            return artifact
    return None


def path_exists(path: Path | None) -> bool:
    return bool(path is not None and path.exists())


def evidence_path(
    *,
    key: str,
    label: str,
    suite: dict[str, Any],
    index: dict[str, Any] | None,
    output_dir: Path,
    artifact_label: str | None = None,
    suite_path: tuple[str, ...] | None = None,
    required: bool = True,
    note: str = "",
) -> dict[str, Any]:
    source = "expected_path"
    path_value: Any = None
    artifact: dict[str, Any] | None = None
    if artifact_label:
        artifact = find_artifact(index, label=artifact_label)
        if artifact is not None:
            path_value = artifact.get("path") or artifact.get("relative_path")
            source = f"artifact_index:{artifact_label}"
    if path_value is None and suite_path:
        path_value = nested_get(suite, suite_path)
        source = "suite:" + ".".join(suite_path)
    if path_value is None:
        path_value = key
        source = "convention"

    path = resolve_path(path_value, base_dir=output_dir) if isinstance(path_value, str) and path_value else None
    exists = path_exists(path)
    status = "available" if exists else ("missing" if required else "not_present")
    if artifact is not None and artifact.get("exists") is False:
        status = "missing" if required else "not_present"
    return {
        "key": key,
        "label": label,
        "status": status,
        "required": required,
        "path": str(path) if path is not None else None,
        "exists": exists,
        "source": source,
        "note": note,
    }


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def real_depth_signal(suite: dict[str, Any], index: dict[str, Any] | None) -> dict[str, Any]:
    scorecard = as_dict(nested_get(suite, ("visual_review", "depth_distance_scorecard")))
    real_depth = as_dict(scorecard.get("real_depth_reference"))
    intake = as_dict(suite.get("real_projection_intake"))
    index_intake = as_dict(index.get("real_projection_intake")) if isinstance(index, dict) else {}
    status = (
        real_depth.get("status")
        or intake.get("status")
        or index_intake.get("status")
        or "missing_real_depth_reference"
    )
    return {
        "status": status,
        "real_depth_comparable": bool(real_depth.get("real_depth_comparable") or status == "real_depth_comparable"),
        "needs_real_depth_reference": bool(
            real_depth.get("needs_real_depth_reference", status != "real_depth_comparable")
        ),
        "missing_inputs": real_depth.get("missing_inputs") or intake.get("missing_inputs") or [],
        "intake_status": intake.get("status") or index_intake.get("status"),
        "residual_aggregate": real_depth.get("residual_aggregate") or intake.get("residual_aggregate") or {},
    }


def visual_review_signal(suite: dict[str, Any]) -> dict[str, Any]:
    visual_review = as_dict(suite.get("visual_review"))
    scorecard = as_dict(visual_review.get("depth_distance_scorecard"))
    metadata_native = as_dict(visual_review.get("metadata_native_depth_view"))
    return {
        "status": visual_review.get("status"),
        "scorecard_status": scorecard.get("review_status") or scorecard.get("status"),
        "scorecard_at_a_glance": scorecard.get("at_a_glance"),
        "metadata_native_status": metadata_native.get("status"),
        "recording_note": "MP4 recordings are best-effort; PNG/JSON evidence remains authoritative.",
    }


def recording_entries(suite: dict[str, Any], index: dict[str, Any] | None, output_dir: Path) -> list[dict[str, Any]]:
    visual_review = as_dict(suite.get("visual_review"))
    recordings = visual_review.get("recordings")
    if isinstance(recordings, dict) and recordings:
        recording_items = sorted((str(key), value) for key, value in recordings.items())
    else:
        recording = visual_review.get("recording")
        recording_items = [("gripper_camera_pov", recording)] if isinstance(recording, dict) else []

    entries: list[dict[str, Any]] = []
    for recording_id, recording in recording_items:
        recording = as_dict(recording)
        artifact = find_artifact(index, label=f"visual_review:{recording_id}_recording")
        path_value = recording.get("path") or (artifact or {}).get("path")
        path = resolve_path(path_value, base_dir=output_dir) if isinstance(path_value, str) and path_value else None
        produced = recording.get("produced") is True or path_exists(path)
        entries.append(
            {
                "key": f"{recording_id}_recording",
                "label": recording_label(recording_id),
                "status": "available" if produced and path_exists(path) else "not_present",
                "required": False,
                "path": str(path) if path is not None else None,
                "exists": path_exists(path),
                "produced": produced,
                "codec": recording.get("codec"),
                "fps": recording.get("fps"),
                "frame_count": recording.get("frame_count"),
                "duration_seconds": recording.get("duration_seconds"),
                "skipped_reason": recording.get("skipped_reason"),
                "note": "Included when OpenCV MP4 writing succeeds.",
            }
        )
    if not entries:
        entries.append(
            {
                "key": "mp4_recordings",
                "label": "Gripper/Pick-Place MP4 Recordings",
                "status": "not_present",
                "required": False,
                "path": None,
                "exists": False,
                "produced": False,
                "skipped_reason": "No recording metadata found in the suite summary.",
                "note": "This is non-fatal; inspect PNG contact sheets and frame sequences.",
            }
        )
    return entries


def recording_label(recording_id: str) -> str:
    labels = {
        "gripper_camera_pov": "Gripper-Camera POV MP4 Recording",
        "pick_place_sequence": "Pick-Place Sequence MP4 Recording",
    }
    return labels.get(recording_id, f"{recording_id.replace('_', ' ').title()} MP4 Recording")


def capture_plan_entry(path: Path | None, *, label: str, key: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve() if path is not None else None
    return {
        "key": key,
        "label": label,
        "status": "available" if path_exists(resolved) else "not_supplied",
        "required": False,
        "path": str(resolved) if resolved is not None else None,
        "exists": path_exists(resolved),
        "source": "cli",
        "note": "Optional operator plan artifact supplied to the evidence bundle renderer.",
    }


def build_bundle(
    *,
    input_json: Path,
    output_md: Path,
    output_json: Path,
    capture_plan_json: Path | None,
    capture_plan_md: Path | None,
) -> dict[str, Any]:
    suite, index, suite_output_dir, loaded_input = load_inputs(input_json)
    real_depth = real_depth_signal(suite, index)

    artifacts = [
        evidence_path(
            key="visual_review/pick_place_depth_distance_scorecard.png",
            label="Depth/Distance Scorecard PNG",
            suite=suite,
            index=index,
            output_dir=suite_output_dir,
            artifact_label="visual_review:pick_place_depth_distance_scorecard:png",
            suite_path=("visual_review", "depth_distance_scorecard", "paths", "png"),
            required=True,
            note="At-a-glance simulator-vs-baseline depth and residual scorecard.",
        ),
        evidence_path(
            key="visual_review/pick_place_depth_distance_scorecard.json",
            label="Depth/Distance Scorecard JSON",
            suite=suite,
            index=index,
            output_dir=suite_output_dir,
            artifact_label="visual_review:pick_place_depth_distance_scorecard:json",
            suite_path=("visual_review", "depth_distance_scorecard", "paths", "json"),
            required=True,
            note="Machine-readable scorecard including real-depth reference status.",
        ),
        evidence_path(
            key="visual_review/pick_place_metadata_native_depth_view.png",
            label="Metadata-Native Depth View PNG",
            suite=suite,
            index=index,
            output_dir=suite_output_dir,
            artifact_label="visual_review:pick_place_metadata_native_depth_view:png",
            suite_path=("visual_review", "metadata_native_depth_view", "paths", "png"),
            required=True,
            note="SimCamera metadata-native projection/depth visual evidence.",
        ),
        evidence_path(
            key="visual_review/pick_place_metadata_native_depth_view.json",
            label="Metadata-Native Depth View JSON",
            suite=suite,
            index=index,
            output_dir=suite_output_dir,
            artifact_label="visual_review:pick_place_metadata_native_depth_view:json",
            suite_path=("visual_review", "metadata_native_depth_view", "paths", "json"),
            required=True,
            note="Machine-readable metadata-native projection/depth rows.",
        ),
        evidence_path(
            key="real_projection_intake/real_projection_residual_overlay_contact_sheet.png",
            label="Real Projection Residual Overlay Contact Sheet",
            suite=suite,
            index=index,
            output_dir=suite_output_dir,
            artifact_label="real_projection_intake:residual_overlay_contact_sheet",
            suite_path=("real_projection_intake", "residual_paths", "overlay_contact_sheet_png"),
            required=real_depth["status"] == "real_depth_comparable",
            note="Present when real_capture sidecars make real-vs-sim residuals comparable.",
        ),
    ]
    artifacts.extend(recording_entries(suite, index, suite_output_dir))
    artifacts.extend(
        [
            capture_plan_entry(capture_plan_json, label="Real-Depth Capture Plan JSON", key="capture_plan_json"),
            capture_plan_entry(capture_plan_md, label="Real-Depth Capture Plan Markdown", key="capture_plan_md"),
        ]
    )

    missing_required = [row for row in artifacts if row.get("required") and not row.get("exists")]
    bundle = {
        "schema": EVIDENCE_SCHEMA,
        "ok": not missing_required,
        "status": "ok" if not missing_required else "missing_required_artifacts",
        "input_json": str(loaded_input),
        "suite_output_dir": str(suite_output_dir),
        "output_json": str(output_json),
        "output_md": str(output_md),
        "summaries": {
            "suite": {
                "status": suite.get("status"),
                "ok": suite.get("ok"),
                "hardware_skipped": suite.get("hardware_skipped"),
                "gui_skipped": suite.get("gui_skipped"),
                "openai_skipped": suite.get("openai_skipped"),
            },
            "visual_review": visual_review_signal(suite),
            "real_depth_reference": real_depth,
            "real_projection_intake": {
                "status": as_dict(suite.get("real_projection_intake")).get("status"),
                "comparable": as_dict(suite.get("real_projection_intake")).get("comparable"),
                "depth_comparable": as_dict(suite.get("real_projection_intake")).get("depth_comparable"),
            },
        },
        "artifacts": artifacts,
        "missing_required_artifacts": missing_required,
        "notes": [
            "Missing optional artifacts are non-fatal and stay visible in both JSON and Markdown.",
            "The bundle is hardware-free and only summarizes existing regression artifacts.",
        ],
    }
    return bundle


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_link(path: str | None, exists: bool) -> str:
    if not path:
        return ""
    escaped = path.replace(" ", "%20").replace(")", "%29")
    label = path
    return f"[{markdown_escape(label)}]({escaped})" if exists else f"`{markdown_escape(label)}`"


def render_markdown(bundle: dict[str, Any]) -> str:
    summaries = as_dict(bundle.get("summaries"))
    suite = as_dict(summaries.get("suite"))
    visual = as_dict(summaries.get("visual_review"))
    real_depth = as_dict(summaries.get("real_depth_reference"))
    lines = [
        "# Simulator Depth-Calibration Evidence Bundle",
        "",
        "Open this first for the key depth/distance screenshots, residual overlays, recordings, and real-depth capture-plan artifacts from the regression run.",
        "",
        "## Status",
        "",
        f"- Bundle status: `{bundle.get('status')}`",
        f"- Suite status: `{suite.get('status')}`",
        f"- Visual review status: `{visual.get('status')}`",
        f"- Scorecard status: `{visual.get('scorecard_status')}`",
        f"- Real-depth reference status: `{real_depth.get('status')}`",
        f"- Missing required artifacts: `{len(bundle.get('missing_required_artifacts') or [])}`",
        f"- Suite output: `{bundle.get('suite_output_dir')}`",
        "",
        "## Artifacts",
        "",
        "| Status | Artifact | Required | Path | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for artifact in bundle.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(artifact.get("status")),
                    markdown_escape(artifact.get("label")),
                    markdown_escape(artifact.get("required")),
                    markdown_link(artifact.get("path"), artifact.get("exists") is True),
                    markdown_escape(artifact.get("note")),
                ]
            )
            + " |"
        )

    missing_inputs = real_depth.get("missing_inputs")
    missing_inputs = missing_inputs if isinstance(missing_inputs, list) else []
    residual_aggregate = as_dict(real_depth.get("residual_aggregate"))
    lines.extend(
        [
            "",
            "## Real-Depth Summary",
            "",
            f"- Status: `{real_depth.get('status')}`",
            f"- Comparable: `{real_depth.get('real_depth_comparable')}`",
            f"- Needs real depth reference: `{real_depth.get('needs_real_depth_reference')}`",
            f"- Missing inputs: `{', '.join(str(item) for item in missing_inputs) if missing_inputs else ''}`",
            f"- Residual aggregate: `{json.dumps(residual_aggregate, sort_keys=True)}`",
            "",
            "## Notes",
            "",
        ]
    )
    for note in bundle.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    input_json = args.input_json.expanduser().resolve()
    default_output_dir = input_json.parent / "evidence_bundle"
    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else default_output_dir
    output_md = args.output_md.expanduser().resolve() if args.output_md else output_dir / DEFAULT_MD_NAME
    output_json = args.output_json.expanduser().resolve() if args.output_json else output_dir / DEFAULT_JSON_NAME

    try:
        bundle = build_bundle(
            input_json=input_json,
            output_md=output_md,
            output_json=output_json,
            capture_plan_json=args.capture_plan_json,
            capture_plan_md=args.capture_plan_md,
        )
        write_json(output_json, bundle)
        write_text(output_md, render_markdown(bundle))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {output_md}")
    print(f"Wrote {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
