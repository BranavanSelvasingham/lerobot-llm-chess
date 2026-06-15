#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ARTIFACT_INDEX_SCHEMA = "lerobot.sim.calibration_artifact_index.v1"
SUITE_SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
DEFAULT_REPORT_NAME = "artifact_index_report.md"
CATEGORY_ORDER = {
    "real_reference_media": 0,
    "real_reference_comparison": 1,
    "ranked_candidate": 2,
    "perception_fixture": 3,
    "sim_camera_pose_fixture": 4,
    "gripper_camera_pov": 5,
    "app_entrypoint": 6,
    "pick_place_scenario": 7,
    "negative_check": 8,
    "logs": 9,
}
CATEGORY_LABELS = {
    "real_reference_media": "Real Reference Media",
    "real_reference_comparison": "Real Reference Comparisons",
    "ranked_candidate": "Ranked Candidate Captures",
    "perception_fixture": "Perception Fixture Evidence",
    "sim_camera_pose_fixture": "SimCamera Pose Fixture",
    "gripper_camera_pov": "Gripper-Camera POV Review",
    "app_entrypoint": "App Entrypoint Metadata",
    "pick_place_scenario": "Pick/Place Release Frames",
    "negative_check": "Negative Check",
    "logs": "Child Logs",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a small Markdown report for an existing simulator calibration "
            "artifact_index.json, or for a suite summary that points at one."
        )
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="Path to artifact_index.json or calibration_regression_summary.json.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Report path. Defaults to artifact_index_report.md in the suite output directory.",
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


def resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def load_inputs(input_json: Path) -> tuple[dict[str, Any], dict[str, Any] | None, Path]:
    input_json = input_json.expanduser().resolve()
    payload = read_json_object(input_json, label="input JSON")
    schema = payload.get("schema")
    if schema == ARTIFACT_INDEX_SCHEMA or "artifacts" in payload:
        index = payload
        suite = None
        suite_path_value = index.get("suite_summary_path")
        if isinstance(suite_path_value, str) and suite_path_value:
            suite_path = resolve_path(suite_path_value, base_dir=input_json.parent)
            if suite_path.is_file():
                suite = read_json_object(suite_path, label="suite summary")
        return index, suite, input_json

    if schema == SUITE_SCHEMA or "artifact_index" in payload:
        suite = payload
        artifact_index = suite.get("artifact_index")
        artifact_index = artifact_index if isinstance(artifact_index, dict) else {}
        artifact_index_path_value = artifact_index.get("path")
        if not isinstance(artifact_index_path_value, str) or not artifact_index_path_value:
            raise ValueError(f"Suite summary {input_json} does not contain artifact_index.path.")
        artifact_index_path = resolve_path(artifact_index_path_value, base_dir=input_json.parent)
        index = read_json_object(artifact_index_path, label="artifact index")
        return index, suite, artifact_index_path

    raise ValueError(
        f"{input_json} is neither an artifact index nor a calibration regression suite summary."
    )


def validate_index(index: dict[str, Any], artifact_index_path: Path) -> None:
    if index.get("schema") != ARTIFACT_INDEX_SCHEMA:
        raise ValueError(
            f"Artifact index {artifact_index_path} has unexpected schema {index.get('schema')!r}."
        )
    if not isinstance(index.get("artifacts"), list):
        raise ValueError(f"Artifact index {artifact_index_path} must contain an artifacts list.")
    if not isinstance(index.get("categories"), list):
        raise ValueError(f"Artifact index {artifact_index_path} must contain a categories list.")


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_code(value: Any) -> str:
    text = "" if value is None else str(value)
    escaped = text.replace("`", "\\`")
    return f"`{escaped}`"


def display_path(artifact: dict[str, Any]) -> str:
    for key in ("relative_path", "repo_relative_path", "path"):
        value = artifact.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def link_path(artifact: dict[str, Any]) -> str:
    value = artifact.get("relative_path")
    if isinstance(value, str) and value:
        return value
    value = artifact.get("path")
    if isinstance(value, str) and value:
        return value
    return display_path(artifact)


def markdown_link(label: str, target: str) -> str:
    if not target:
        return markdown_escape(label)
    escaped_label = markdown_escape(label)
    escaped_target = target.replace(" ", "%20").replace(")", "%29")
    return f"[{escaped_label}]({escaped_target})"


def artifact_sort_key(artifact: dict[str, Any]) -> tuple[int, str, str]:
    category = str(artifact.get("category") or "")
    return (
        CATEGORY_ORDER.get(category, 99),
        str(artifact.get("label") or ""),
        display_path(artifact),
    )


def artifacts_by_category(index: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_ORDER}
    for artifact in index.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        grouped.setdefault(category, []).append(artifact)
    for category, rows in grouped.items():
        grouped[category] = sorted(rows, key=artifact_sort_key)
    return grouped


def category_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    by_category = {
        row.get("category"): row
        for row in index.get("categories", [])
        if isinstance(row, dict) and isinstance(row.get("category"), str)
    }
    rows: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        source = by_category.get(category, {})
        rows.append(
            {
                "category": category,
                "artifact_count": int(source.get("artifact_count") or 0),
                "missing_count": int(source.get("missing_count") or 0),
            }
        )
    for category in sorted(str(key) for key in by_category if key not in CATEGORY_ORDER):
        source = by_category[category]
        rows.append(
            {
                "category": category,
                "artifact_count": int(source.get("artifact_count") or 0),
                "missing_count": int(source.get("missing_count") or 0),
            }
        )
    return rows


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_escape(value) for value in row) + " |" for row in rows)
    return lines


def value_from_suite_or_index(index: dict[str, Any], suite: dict[str, Any] | None, key: str) -> Any:
    if suite is not None and key in suite:
        return suite.get(key)
    return index.get(key)


def skipped_marker_rows(index: dict[str, Any], suite: dict[str, Any] | None) -> list[list[Any]]:
    markers = value_from_suite_or_index(index, suite, "skipped_markers")
    markers = markers if isinstance(markers, dict) else {}
    return [
        [
            "hardware",
            value_from_suite_or_index(index, suite, "hardware_skipped"),
            markers.get("hardware", ""),
        ],
        [
            "gui",
            value_from_suite_or_index(index, suite, "gui_skipped"),
            markers.get("gui", ""),
        ],
        [
            "openai",
            value_from_suite_or_index(index, suite, "openai_skipped"),
            markers.get("openai", ""),
        ],
    ]


def suite_inventory_gaps(suite: dict[str, Any] | None) -> list[dict[str, Any]]:
    if suite is None:
        return []
    inventory = suite.get("inventory")
    inventory = inventory if isinstance(inventory, dict) else {}
    gaps = inventory.get("visibility_gaps")
    return [gap for gap in gaps if isinstance(gap, dict)] if isinstance(gaps, list) else []


def selected_media_rows(index: dict[str, Any]) -> list[list[Any]]:
    selected = index.get("selected_real_reference_media")
    selected = selected if isinstance(selected, list) else []
    rows: list[list[Any]] = []
    for media in selected:
        if not isinstance(media, dict):
            continue
        rows.append(
            [
                media.get("relative_path", ""),
                media.get("media_type", ""),
                media.get("dimensions", ""),
                media.get("currently_wired_into_simulator_tooling", ""),
            ]
        )
    return rows


def gap_rows(gaps: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for gap in gaps:
        rows.append(
            [
                gap.get("category", ""),
                gap.get("status", ""),
                gap.get("note", ""),
            ]
        )
    return rows


def evidence_row(artifact: dict[str, Any]) -> list[Any]:
    exists = "ok" if artifact.get("exists") is True else "missing"
    target = link_path(artifact)
    label = str(artifact.get("label") or "")
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        label,
        markdown_link(path, target) if path else "",
        exists,
    ]


def linked_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for value in row:
            text = "" if value is None else str(value)
            cells.append(text.replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def metric_value(metrics: dict[str, Any], key: str) -> Any:
    aggregate = metrics.get("aggregate")
    if isinstance(aggregate, dict) and key in aggregate:
        return aggregate.get(key)
    return ""


def release_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    target_release = metrics.get("target_release_open")
    target_release = target_release if isinstance(target_release, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("scenario_id", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        target_release.get("visible_fraction", ""),
        target_release.get("occlusion_fraction", ""),
        target_release.get("min_clearance_px", metric_value(metrics, "min_clearance_px")),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def pose_fixture_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("scenario_id", ""),
        artifact.get("kind", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("view", ""),
        metrics.get("target_square", ""),
        metrics.get("piece_square", ""),
        "ok" if metrics.get("metadata_intrinsics") is True else "",
        "ok" if metrics.get("metadata_distortion") is True else "",
        "ok" if metrics.get("metadata_extrinsics_board_to_camera") is True else "",
        "ok" if metrics.get("metadata_coordinate_frames") is True else "",
        "ok" if artifact.get("exists") is True else "missing",
    ]


def gripper_camera_pov_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("scenario_id", ""),
        artifact.get("kind", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("target_square", ""),
        metrics.get("target_center_xy", ""),
        metrics.get("visible_fraction", ""),
        metrics.get("occlusion_fraction", ""),
        metrics.get("min_clearance_px", ""),
        metrics.get("tracked_gripper_percent", ""),
        metrics.get("current_gripper_opening_px", ""),
        "ok" if metrics.get("metadata_contract_ok") is True else "",
        "ok" if artifact.get("exists") is True else "missing",
    ]


def app_entrypoint_row(artifact: dict[str, Any]) -> list[Any]:
    metrics = artifact.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    path = display_path(artifact)
    return [
        artifact.get("kind", ""),
        artifact.get("label", ""),
        markdown_link(path, link_path(artifact)) if path else "",
        metrics.get("sim_camera_profile", ""),
        "ok" if metrics.get("metadata_contract_ok") is True else "",
        metrics.get("metadata_contract_check_count", ""),
        metrics.get("metadata_contract_failed_check_count", ""),
        metrics.get("hardware_skipped", ""),
        metrics.get("gui_skipped", ""),
        metrics.get("openai_skipped", ""),
        "ok" if artifact.get("exists") is True else "missing",
    ]


def negative_status(index: dict[str, Any], suite: dict[str, Any] | None) -> Any:
    if suite is not None:
        negative = suite.get("negative_check")
        if isinstance(negative, dict) and negative.get("status") is not None:
            return negative.get("status")
    for artifact in index.get("artifacts", []):
        if not isinstance(artifact, dict) or artifact.get("category") != "negative_check":
            continue
        metrics = artifact.get("metrics")
        if isinstance(metrics, dict) and metrics.get("status") is not None:
            return metrics.get("status")
    return ""


def child_log_rows(logs: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for artifact in logs:
        label = str(artifact.get("label") or "")
        if "stdout_path" not in label and "stderr_path" not in label:
            continue
        metrics = artifact.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        path = display_path(artifact)
        rows.append(
            [
                label,
                markdown_link(path, link_path(artifact)) if path else "",
                metrics.get("ok", ""),
                metrics.get("return_code", ""),
                "ok" if artifact.get("exists") is True else "missing",
            ]
        )
    return rows


def append_artifact_group(lines: list[str], category: str, artifacts: list[dict[str, Any]]) -> None:
    lines.append(f"### {CATEGORY_LABELS.get(category, category)}")
    if not artifacts:
        lines.append("")
        lines.append("_No artifacts indexed._")
        lines.append("")
        return
    rows: list[list[Any]] = []
    for artifact in artifacts:
        detail_parts = []
        if artifact.get("scenario_id") is not None:
            detail_parts.append(f"scenario={artifact.get('scenario_id')}")
        if artifact.get("candidate_id") is not None:
            detail_parts.append(f"candidate={artifact.get('candidate_id')}")
        if artifact.get("rank") is not None:
            detail_parts.append(f"rank={artifact.get('rank')}")
        rows.append(evidence_row(artifact) + [", ".join(detail_parts)])
    lines.extend(linked_table(["Kind", "Label", "Path", "Status", "Details"], rows))
    lines.append("")


def render_report(index: dict[str, Any], suite: dict[str, Any] | None, artifact_index_path: Path) -> str:
    grouped = artifacts_by_category(index)
    lines: list[str] = [
        "# Simulator Calibration Artifact Index Report",
        "",
        "## Run Metadata",
    ]
    suite_status = index.get("suite_status")
    suite_status = suite_status if isinstance(suite_status, dict) else {}
    lines.extend(
        table(
            ["Field", "Value"],
            [
                ["artifact_index_status", index.get("status", "")],
                ["artifact_count", len(index.get("artifacts", []))],
                ["missing_artifact_count", len(index.get("missing_artifacts", []))],
                ["suite_status", suite_status.get("status", "")],
                ["suite_ok", suite_status.get("ok", "")],
                ["output_dir", index.get("output_dir", "")],
                ["suite_summary_path", index.get("suite_summary_path", "")],
                ["artifact_index_path", str(artifact_index_path)],
            ],
        )
    )

    lines.extend(["", "## Category Summary"])
    lines.extend(
        table(
            ["Category", "Artifacts", "Missing"],
            [
                [CATEGORY_LABELS.get(row["category"], row["category"]), row["artifact_count"], row["missing_count"]]
                for row in category_rows(index)
            ],
        )
    )

    lines.extend(["", "## Skipped Hardware, GUI, And OpenAI"])
    lines.extend(table(["Path", "Skipped", "Marker"], skipped_marker_rows(index, suite)))

    lines.extend(["", "## Real Reference Media Gap"])
    media_rows = selected_media_rows(index)
    if media_rows:
        lines.extend(table(["Media", "Type", "Dimensions", "Wired"], media_rows))
    else:
        lines.append("_No real reference media selected in the artifact index._")
    gaps = suite_inventory_gaps(suite)
    if gaps:
        lines.append("")
        lines.extend(table(["Gap", "Status", "Note"], gap_rows(gaps)))
    else:
        lines.append("")
        lines.append("_No inventory visibility gaps were available from the suite summary._")

    lines.extend(["", "## Important Evidence"])
    comparison_images = [
        row for row in grouped.get("real_reference_comparison", []) if row.get("kind") == "image"
    ]
    lines.extend(["", "### Real-Reference Comparison Images"])
    lines.extend(
        linked_table(["Kind", "Label", "Path", "Status"], [evidence_row(row) for row in comparison_images])
        if comparison_images
        else ["_No image artifacts indexed._"]
    )

    ranked_candidate = grouped.get("ranked_candidate", [])
    lines.extend(["", "### Ranked Candidate Captures"])
    lines.extend(
        linked_table(
            ["Kind", "Label", "Path", "Status", "Candidate", "Rank"],
            [
                evidence_row(row) + [row.get("candidate_id", ""), row.get("rank", "")]
                for row in ranked_candidate
            ],
        )
        if ranked_candidate
        else ["_No ranked candidate artifacts indexed._"]
    )

    fixture = grouped.get("perception_fixture", [])
    lines.extend(["", "### Perception Fixture Artifacts"])
    lines.extend(
        linked_table(["Kind", "Label", "Path", "Status"], [evidence_row(row) for row in fixture])
        if fixture
        else ["_No perception fixture artifacts indexed._"]
    )

    pose_fixture = [
        row
        for row in grouped.get("sim_camera_pose_fixture", [])
        if row.get("label") != "sim_camera_pose_fixture:summary"
    ]
    lines.extend(["", "### SimCamera Pose Fixture"])
    lines.extend(
        linked_table(
            [
                "Case",
                "Kind",
                "Path",
                "View",
                "Target Square",
                "Piece Square",
                "Intrinsics",
                "Distortion",
                "Board->Camera",
                "Frame Notes",
                "Status",
            ],
            [pose_fixture_row(row) for row in pose_fixture],
        )
        if pose_fixture
        else ["_No SimCamera pose fixture artifacts indexed._"]
    )

    pov = [
        row
        for row in grouped.get("gripper_camera_pov", [])
        if row.get("label") != "gripper_camera_pov:summary"
    ]
    lines.extend(["", "### Gripper-Camera POV Review"])
    lines.extend(
        linked_table(
            [
                "State",
                "Kind",
                "Path",
                "Target Square",
                "Target Center",
                "Visible Fraction",
                "Occlusion Fraction",
                "Min Clearance Px",
                "Gripper %",
                "Opening Px",
                "Metadata Contract",
                "Status",
            ],
            [gripper_camera_pov_row(row) for row in pov],
        )
        if pov
        else ["_No gripper-camera POV artifacts indexed._"]
    )

    app_entrypoint = grouped.get("app_entrypoint", [])
    lines.extend(["", "### App Entrypoint Metadata"])
    lines.extend(
        linked_table(
            [
                "Kind",
                "Label",
                "Path",
                "Profile",
                "Metadata Contract",
                "Checks",
                "Failed Checks",
                "Hardware Skipped",
                "GUI Skipped",
                "OpenAI Skipped",
                "Status",
            ],
            [app_entrypoint_row(row) for row in app_entrypoint],
        )
        if app_entrypoint
        else ["_No app-entrypoint artifacts indexed._"]
    )

    releases = [
        row
        for row in grouped.get("pick_place_scenario", [])
        if isinstance(row.get("scenario_id"), str) and row.get("kind") == "image"
    ]
    lines.extend(["", "### Pick/Place Release Frames"])
    lines.extend(
        linked_table(
            [
                "Scenario",
                "Release Frame",
                "Visible Fraction",
                "Occlusion Fraction",
                "Min Clearance Px",
                "Status",
            ],
            [release_row(row) for row in releases],
        )
        if releases
        else ["_No pick/place release frame artifacts indexed._"]
    )

    negative = grouped.get("negative_check", [])
    lines.extend(["", "### Negative Check"])
    lines.append(f"Status: {markdown_code(negative_status(index, suite))}")
    if negative:
        lines.extend(linked_table(["Kind", "Label", "Path", "Status"], [evidence_row(row) for row in negative]))

    logs = grouped.get("logs", [])
    lines.extend(["", "### Child Logs"])
    child_rows = child_log_rows(logs)
    lines.extend(
        linked_table(["Label", "Path", "Child OK", "Return Code", "Status"], child_rows)
        if child_rows
        else ["_No child stdout/stderr logs indexed._"]
    )

    lines.extend(["", "## Compact Artifact List"])
    for category in sorted(grouped, key=lambda key: (CATEGORY_ORDER.get(key, 99), key)):
        append_artifact_group(lines, category, grouped[category])

    lines.extend(
        [
            "## Notes",
            "",
            "- This report is a deterministic Markdown view of existing JSON artifacts only.",
            "- SimCamera pose fixture intrinsics/extrinsics are simulator reference metadata, not physical calibration truth.",
            "- Gripper-camera POV visibility and clearance values are synthetic metadata evidence, not real-camera segmentation or physical contact proof.",
            "- It does not rerun child smokes, open GUI calibration flows, call OpenAI, or touch SO-101 hardware.",
            "",
        ]
    )
    return "\n".join(lines)


def default_output_path(index: dict[str, Any], artifact_index_path: Path) -> Path:
    output_dir = index.get("output_dir")
    if isinstance(output_dir, str) and output_dir:
        return Path(output_dir).expanduser().resolve() / DEFAULT_REPORT_NAME
    return artifact_index_path.parent / DEFAULT_REPORT_NAME


def main() -> int:
    args = parse_args()
    try:
        index, suite, artifact_index_path = load_inputs(args.input_json)
        artifact_index_path = artifact_index_path.expanduser().resolve()
        validate_index(index, artifact_index_path)
        output_md = (
            args.output_md.expanduser().resolve()
            if args.output_md
            else default_output_path(index, artifact_index_path)
        )
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_report(index, suite, artifact_index_path))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(str(output_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
