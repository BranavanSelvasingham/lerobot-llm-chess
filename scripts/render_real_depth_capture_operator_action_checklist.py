#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_depth_capture_operator_action_checklist"
DEFAULT_SUITE_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "calibration_regression_suite"
DEFAULT_PLAN_INDEX_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_depth_capture_plan_artifact_index"
DOCUMENTED_PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3")
DEFAULT_PYTHON = DOCUMENTED_PYTHON if DOCUMENTED_PYTHON.exists() else Path(sys.executable)

SCHEMA = "lerobot.sim.real_depth_capture_operator_action_checklist.v1"
OUTPUT_JSON_NAME = "real_depth_capture_operator_action_checklist.json"
OUTPUT_CSV_NAME = "real_depth_capture_operator_action_checklist_actions.csv"
README_NAME = "README.md"

INPUT_READINESS_CAVEAT = (
    "Ready reference-capture-manifest evidence is input readiness only; physical calibration "
    "truth still requires subsequent sidecar validation, intake, and residual comparison artifacts."
)
NO_MEDIA_CAVEAT = (
    "This renderer reads JSON summary/index files only; it does not copy, open, decode, modify, "
    "or commit photos or videos."
)


class ChecklistInputError(ValueError):
    """Raised when an explicitly supplied JSON input cannot be used."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a narrow hardware-free operator action checklist from the suite-indexed "
            "real depth capture plan artifact index."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument(
        "--plan-artifact-index-json",
        type=Path,
        default=None,
        help="Existing real_depth_capture_plan_artifact_index.json to render directly.",
    )
    inputs.add_argument(
        "--calibration-suite-summary-json",
        type=Path,
        default=None,
        help=(
            "Existing calibration_regression_summary.json. The renderer will prefer the "
            "referenced real_depth_capture_plan_artifact_index JSON and fall back to embedded cases."
        ),
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ChecklistInputError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ChecklistInputError(f"Invalid JSON in {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ChecklistInputError(f"{label} {path} must contain a JSON object.")
    return payload


def resolve_cli_path(path: Path) -> Path:
    path = path.expanduser()
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def resolve_artifact_path(path_text: Any, *, base_dir: Path) -> Path | None:
    if not isinstance(path_text, str) or not path_text.strip():
        return None
    path = Path(path_text).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def action_text(action: dict[str, Any]) -> str:
    for key in ("operator_action", "text", "label", "command"):
        value = action.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_action(action: dict[str, Any], *, case_id: str | None, group: str, scope: str) -> dict[str, Any]:
    action_id = action.get("id")
    return {
        "case_id": case_id,
        "group": group,
        "scope": scope,
        "id": str(action_id) if isinstance(action_id, str) and action_id else "unnamed_operator_action",
        "text": action_text(action),
        "raw": action,
    }


def action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [action["id"] for action in actions if isinstance(action.get("id"), str)]


def command_entry(action_id: str, description: str, command: list[str]) -> dict[str, Any]:
    return {"id": action_id, "description": description, "command": command}


def default_recommended_commands(output_dir: Path) -> list[dict[str, Any]]:
    suite_summary = DEFAULT_SUITE_OUTPUT_DIR / "calibration_regression_summary.json"
    plan_index = DEFAULT_PLAN_INDEX_OUTPUT_DIR / "real_depth_capture_plan_artifact_index.json"
    return [
        command_entry(
            "run_calibration_suite_for_suite_indexed_plan_artifact",
            "Run the full hardware-free calibration suite so it writes the suite-indexed plan artifact index.",
            [
                str(DEFAULT_PYTHON),
                "scripts/smoke_sim_calibration_regression_suite.py",
                "--python",
                str(DEFAULT_PYTHON),
                "--output-dir",
                str(DEFAULT_SUITE_OUTPUT_DIR),
            ],
        ),
        command_entry(
            "run_focused_plan_artifact_index",
            "Run the focused hardware-free plan artifact index without the full suite.",
            [
                str(DEFAULT_PYTHON),
                "scripts/smoke_real_depth_capture_plan_artifact_index.py",
                "--output-dir",
                str(DEFAULT_PLAN_INDEX_OUTPUT_DIR),
            ],
        ),
        command_entry(
            "render_checklist_from_suite_summary",
            "Render this operator checklist from the suite summary.",
            [
                str(DEFAULT_PYTHON),
                "scripts/render_real_depth_capture_operator_action_checklist.py",
                "--calibration-suite-summary-json",
                str(suite_summary),
                "--output-dir",
                str(output_dir),
            ],
        ),
        command_entry(
            "render_checklist_from_direct_plan_index",
            "Render this operator checklist from a direct plan artifact index.",
            [
                str(DEFAULT_PYTHON),
                "scripts/render_real_depth_capture_operator_action_checklist.py",
                "--plan-artifact-index-json",
                str(plan_index),
                "--output-dir",
                str(output_dir),
            ],
        ),
    ]


def missing_evidence_actions(output_dir: Path) -> list[dict[str, Any]]:
    return [
        {
            "id": "run_calibration_suite_for_plan_artifact_index",
            "operator_action": (
                "Run the calibration regression suite and then render this checklist with "
                "--calibration-suite-summary-json."
            ),
            "command": default_recommended_commands(output_dir)[0]["command"],
        },
        {
            "id": "run_focused_plan_artifact_index",
            "operator_action": (
                "Run the focused real depth capture plan artifact index and then render this checklist with "
                "--plan-artifact-index-json."
            ),
            "command": default_recommended_commands(output_dir)[1]["command"],
        },
    ]


def case_next_actions(case: dict[str, Any]) -> list[dict[str, Any]]:
    actions = list_of_dicts(case.get("next_operator_actions"))
    if actions:
        return actions
    ids = string_list(case.get("next_operator_action_ids"))
    return [{"id": action_id, "operator_action": ""} for action_id in ids]


def normalize_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id_value = case.get("case_id")
    case_id = str(case_id_value) if case_id_value is not None else "unknown_case"
    ready = case.get("ready_for_calibration_grade_simcamera_tuning") is True
    next_actions = [
        normalize_action(action, case_id=case_id, group="ready_input_cases" if ready else "missing_input_cases", scope="case")
        for action in case_next_actions(case)
    ]
    return {
        "case_id": case_id,
        "scenario_label": case.get("scenario_label"),
        "evidence_source_kind": case.get("evidence_source_kind"),
        "evidence_status": case.get("evidence_status"),
        "ready_for_calibration_grade_simcamera_tuning": ready,
        "depth_reference_capture_count": int_value(case.get("depth_reference_capture_count")),
        "pick_place_video_capture_count": int_value(case.get("pick_place_video_capture_count")),
        "missing_path_count": int_value(case.get("missing_path_count")),
        "no_copy_status": case.get("no_copy_status"),
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "next_operator_action_ids": action_ids(next_actions),
        "next_operator_actions": next_actions,
        "planner_json_path": case.get("planner_json_path"),
        "planner_markdown_path": case.get("planner_markdown_path"),
        "caveats": unique_strings(
            [
                *string_list(case.get("caveats")),
                INPUT_READINESS_CAVEAT,
                NO_MEDIA_CAVEAT,
            ]
        ),
    }


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_cases = [normalize_case(case) for case in cases]
    ready_cases = [case for case in normalized_cases if case["ready_for_calibration_grade_simcamera_tuning"]]
    missing_cases = [case for case in normalized_cases if not case["ready_for_calibration_grade_simcamera_tuning"]]
    grouped_actions: dict[str, list[dict[str, Any]]] = {
        "missing_input_cases": [
            action
            for case in missing_cases
            for action in list_of_dicts(case.get("next_operator_actions"))
        ],
        "ready_input_cases": [
            action
            for case in ready_cases
            for action in list_of_dicts(case.get("next_operator_actions"))
        ],
    }
    return {
        "cases": normalized_cases,
        "case_count": len(normalized_cases),
        "ready_case_count": len(ready_cases),
        "not_ready_case_count": len(missing_cases),
        "ready_case_ids": [case["case_id"] for case in ready_cases],
        "not_ready_case_ids": [case["case_id"] for case in missing_cases],
        "evidence_statuses": unique_strings([case.get("evidence_status") for case in normalized_cases]),
        "depth_reference_capture_count": sum(case["depth_reference_capture_count"] for case in normalized_cases),
        "pick_place_video_capture_count": sum(case["pick_place_video_capture_count"] for case in normalized_cases),
        "missing_path_count": sum(case["missing_path_count"] for case in normalized_cases),
        "no_copy_statuses": unique_strings([case.get("no_copy_status") for case in normalized_cases]),
        "action_groups": {
            group: {
                "case_count": len(missing_cases if group == "missing_input_cases" else ready_cases),
                "case_ids": [
                    case["case_id"]
                    for case in (missing_cases if group == "missing_input_cases" else ready_cases)
                ],
                "action_count": len(actions),
                "action_ids": unique_strings(action_ids(actions)),
                "actions": actions,
            }
            for group, actions in grouped_actions.items()
        },
    }


def load_plan_index_payload(path: Path, *, label: str) -> dict[str, Any]:
    payload = read_json_object(path, label=label)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ChecklistInputError(f"{label} {path} does not contain a cases list.")
    return payload


def suite_plan_index_candidates(section: dict[str, Any]) -> list[str]:
    artifact_paths = section.get("artifact_paths")
    artifact_paths = artifact_paths if isinstance(artifact_paths, dict) else {}
    return [
        str(path)
        for path in (
            section.get("summary_path"),
            section.get("artifact_index_path"),
            artifact_paths.get("summary_json"),
        )
        if isinstance(path, str) and path
    ]


def extract_from_suite_summary(
    *,
    suite_summary: dict[str, Any],
    suite_summary_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    section = suite_summary.get("real_depth_capture_plan_artifact_index")
    if not isinstance(section, dict):
        diagnostics.append(
            {
                "id": "suite_summary_missing_real_depth_capture_plan_artifact_index",
                "severity": "warning",
                "detail": "calibration_regression_summary.json has no real_depth_capture_plan_artifact_index object.",
            }
        )
        return {
            "mode": "calibration_suite_summary_json",
            "status": "real_depth_capture_plan_artifact_index_missing",
            "calibration_suite_summary_json": str(suite_summary_path),
            "plan_artifact_index_json": None,
            "plan_artifact_index_status": None,
            "plan_artifact_index_ok": None,
            "source_mode": None,
            "bridge_smoke_summary_json": None,
        }, [], diagnostics

    child_payload: dict[str, Any] = {}
    child_path: Path | None = None
    for path_text in suite_plan_index_candidates(section):
        candidate = resolve_artifact_path(path_text, base_dir=suite_summary_path.parent)
        if candidate is None:
            continue
        if not candidate.is_file():
            diagnostics.append(
                {
                    "id": "referenced_plan_artifact_index_json_missing",
                    "severity": "warning",
                    "path": str(candidate),
                }
            )
            continue
        try:
            child_payload = load_plan_index_payload(candidate, label="referenced plan artifact index JSON")
            child_path = candidate
            break
        except ChecklistInputError as exc:
            diagnostics.append(
                {
                    "id": "referenced_plan_artifact_index_json_unusable",
                    "severity": "warning",
                    "path": str(candidate),
                    "detail": str(exc),
                }
            )

    source = child_payload if child_payload else section
    cases = list_of_dicts(source.get("cases"))
    if not cases and isinstance(source.get("case_summaries"), list):
        cases = list_of_dicts(source.get("case_summaries"))
        diagnostics.append(
            {
                "id": "using_suite_embedded_case_summaries_without_action_text",
                "severity": "warning",
                "detail": "Only case summaries were available, so action IDs may not include full operator text.",
            }
        )
    if not cases:
        diagnostics.append(
            {
                "id": "real_depth_capture_plan_artifact_index_cases_unavailable",
                "severity": "warning",
                "detail": "No plan artifact index cases were available from the referenced child JSON or embedded suite section.",
            }
        )

    source_metadata = {
        "mode": "calibration_suite_summary_json",
        "status": "referenced_plan_artifact_index_loaded" if child_payload else "using_embedded_suite_section",
        "calibration_suite_summary_json": str(suite_summary_path),
        "plan_artifact_index_json": str(child_path) if child_path else None,
        "plan_artifact_index_status": source.get("status"),
        "plan_artifact_index_ok": source.get("ok"),
        "source_mode": source.get("source_mode"),
        "bridge_smoke_summary_json": source.get("bridge_smoke_summary_json"),
    }
    return source_metadata, cases, diagnostics


def build_no_input_checklist(output_dir: Path) -> dict[str, Any]:
    missing_actions = [
        normalize_action(action, case_id=None, group="missing_input_cases", scope="missing_evidence")
        for action in missing_evidence_actions(output_dir)
    ]
    summary = summarize_cases([])
    summary["action_groups"]["missing_input_cases"]["action_count"] = len(missing_actions)
    summary["action_groups"]["missing_input_cases"]["action_ids"] = unique_strings(action_ids(missing_actions))
    summary["action_groups"]["missing_input_cases"]["actions"] = missing_actions
    return {
        "schema": SCHEMA,
        "ok": True,
        "status": "missing_plan_artifact_index_input",
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "input": {
            "mode": "no_input",
            "status": "no_plan_artifact_index_or_suite_summary_supplied",
            "plan_artifact_index_json": None,
            "calibration_suite_summary_json": None,
        },
        **summary,
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "recommended_next_commands": default_recommended_commands(output_dir),
        "diagnostics": [
            {
                "id": "no_input_supplied",
                "severity": "warning",
                "detail": (
                    "Supply --calibration-suite-summary-json or --plan-artifact-index-json to render "
                    "case-specific operator actions."
                ),
            }
        ],
        "caveats": [INPUT_READINESS_CAVEAT, NO_MEDIA_CAVEAT],
    }


def build_checklist(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    output_dir = args.output_dir.expanduser().resolve()
    if args.plan_artifact_index_json is None and args.calibration_suite_summary_json is None:
        return build_no_input_checklist(output_dir), 0

    input_diagnostics: list[dict[str, Any]] = []
    if args.plan_artifact_index_json is not None:
        plan_index_path = resolve_cli_path(args.plan_artifact_index_json)
        plan_index = load_plan_index_payload(plan_index_path, label="plan artifact index JSON")
        source_metadata = {
            "mode": "plan_artifact_index_json",
            "status": "plan_artifact_index_loaded",
            "plan_artifact_index_json": str(plan_index_path),
            "calibration_suite_summary_json": None,
            "plan_artifact_index_status": plan_index.get("status"),
            "plan_artifact_index_ok": plan_index.get("ok"),
            "source_mode": plan_index.get("source_mode"),
            "bridge_smoke_summary_json": plan_index.get("bridge_smoke_summary_json"),
        }
        cases = list_of_dicts(plan_index.get("cases"))
    else:
        suite_summary_path = resolve_cli_path(args.calibration_suite_summary_json)
        suite_summary = read_json_object(suite_summary_path, label="calibration suite summary JSON")
        source_metadata, cases, input_diagnostics = extract_from_suite_summary(
            suite_summary=suite_summary,
            suite_summary_path=suite_summary_path,
        )

    summary = summarize_cases(cases)
    checklist = {
        "schema": SCHEMA,
        "ok": True,
        "status": "ok_with_diagnostics" if input_diagnostics else "ok",
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "input": source_metadata,
        **summary,
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "recommended_next_commands": default_recommended_commands(output_dir),
        "diagnostics": input_diagnostics,
        "caveats": unique_strings(
            [
                INPUT_READINESS_CAVEAT,
                NO_MEDIA_CAVEAT,
                *[
                    caveat
                    for case in summary["cases"]
                    for caveat in string_list(case.get("caveats"))
                ],
            ]
        ),
    }
    return checklist, 0


def write_actions_csv(path: Path, checklist: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "group",
        "scope",
        "case_id",
        "action_id",
        "action_text",
        "case_ready_for_calibration_grade_simcamera_tuning",
        "case_evidence_status",
        "case_depth_reference_capture_count",
        "case_pick_place_video_capture_count",
        "case_missing_path_count",
        "case_no_copy_status",
    ]
    cases = {case.get("case_id"): case for case in list_of_dicts(checklist.get("cases"))}
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        groups = checklist.get("action_groups")
        groups = groups if isinstance(groups, dict) else {}
        for group_name in ("missing_input_cases", "ready_input_cases"):
            group = groups.get(group_name)
            group = group if isinstance(group, dict) else {}
            for action in list_of_dicts(group.get("actions")):
                case = cases.get(action.get("case_id"), {})
                writer.writerow(
                    {
                        "group": group_name,
                        "scope": action.get("scope"),
                        "case_id": action.get("case_id") or "",
                        "action_id": action.get("id"),
                        "action_text": action.get("text"),
                        "case_ready_for_calibration_grade_simcamera_tuning": case.get(
                            "ready_for_calibration_grade_simcamera_tuning", ""
                        ),
                        "case_evidence_status": case.get("evidence_status", ""),
                        "case_depth_reference_capture_count": case.get(
                            "depth_reference_capture_count", ""
                        ),
                        "case_pick_place_video_capture_count": case.get(
                            "pick_place_video_capture_count", ""
                        ),
                        "case_missing_path_count": case.get("missing_path_count", ""),
                        "case_no_copy_status": case.get("no_copy_status", ""),
                    }
                )


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_escape(value) for value in row) + " |" for row in rows)
    return lines


def command_line(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command or "")


def write_readme(path: Path, checklist: dict[str, Any]) -> None:
    groups = checklist.get("action_groups")
    groups = groups if isinstance(groups, dict) else {}
    cases = list_of_dicts(checklist.get("cases"))
    diagnostics = list_of_dicts(checklist.get("diagnostics"))
    lines = [
        "# Real Depth Capture Operator Action Checklist",
        "",
        "This hardware-free renderer turns the suite-indexed real depth capture plan artifact index into a concise operator review artifact.",
        "",
        "It reads JSON summary/index files only. It does not copy, open, decode, modify, or commit photos or videos. Ready input evidence is not physical calibration truth.",
        "",
        "## Source",
        "",
        f"- Mode: `{checklist.get('input', {}).get('mode')}`",
        f"- Status: `{checklist.get('input', {}).get('status')}`",
        f"- Plan artifact index JSON: `{checklist.get('input', {}).get('plan_artifact_index_json')}`",
        f"- Calibration suite summary JSON: `{checklist.get('input', {}).get('calibration_suite_summary_json')}`",
        f"- Bridge smoke summary JSON: `{checklist.get('input', {}).get('bridge_smoke_summary_json')}`",
        f"- Media copied into repo: `{checklist.get('media_assets_copied_into_repo')}`",
        f"- Media opened or decoded: `{checklist.get('media_assets_opened_or_decoded')}`",
        "",
        "## Case Summary",
    ]
    lines.extend(
        markdown_table(
            [
                "Cases",
                "Ready",
                "Not ready",
                "Depth captures",
                "Pick/place captures",
                "Missing paths",
                "No-copy statuses",
            ],
            [
                [
                    checklist.get("case_count"),
                    checklist.get("ready_case_count"),
                    checklist.get("not_ready_case_count"),
                    checklist.get("depth_reference_capture_count"),
                    checklist.get("pick_place_video_capture_count"),
                    checklist.get("missing_path_count"),
                    ", ".join(string_list(checklist.get("no_copy_statuses"))),
                ]
            ],
        )
    )
    if cases:
        lines.extend(["", "## Cases"])
        lines.extend(
            markdown_table(
                ["Case", "Evidence", "Status", "Ready", "Depth", "Pick/place", "Missing paths", "No-copy"],
                [
                    [
                        case.get("case_id"),
                        case.get("evidence_source_kind"),
                        case.get("evidence_status"),
                        case.get("ready_for_calibration_grade_simcamera_tuning"),
                        case.get("depth_reference_capture_count"),
                        case.get("pick_place_video_capture_count"),
                        case.get("missing_path_count"),
                        case.get("no_copy_status"),
                    ]
                    for case in cases
                ],
            )
        )
    lines.extend(["", "## Next Operator Actions"])
    for group_name, heading in (
        ("missing_input_cases", "Missing Input Cases"),
        ("ready_input_cases", "Ready Input Cases"),
    ):
        group = groups.get(group_name)
        group = group if isinstance(group, dict) else {}
        lines.extend(["", f"### {heading}", ""])
        actions = list_of_dicts(group.get("actions"))
        if not actions:
            lines.append("- No actions recorded.")
        for action in actions:
            case_suffix = f" ({action.get('case_id')})" if action.get("case_id") else ""
            text = action.get("text") or "See the recommended commands below."
            lines.append(f"- `{action.get('id')}`{case_suffix}: {text}")
    lines.extend(["", "## Recommended Commands", ""])
    for command in list_of_dicts(checklist.get("recommended_next_commands")):
        lines.append(f"- `{command.get('id')}`: {command.get('description')}")
        lines.append("")
        lines.append("  ```bash")
        lines.append("  " + command_line(command.get("command")))
        lines.append("  ```")
        lines.append("")
    lines.extend(["## Diagnostics"])
    if not diagnostics:
        lines.append("- No checklist diagnostics were recorded.")
    for diagnostic in diagnostics:
        detail = diagnostic.get("detail") or diagnostic.get("path") or ""
        lines.append(f"- `{diagnostic.get('id')}` ({diagnostic.get('severity', 'info')}): {detail}")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Ready reference-capture-manifest evidence is input readiness only.",
            "- Physical calibration claims still require sidecar validation, real projection intake, and residual comparison evidence.",
            "- Photos and videos are not copied, opened, decoded, modified, or committed by this renderer.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def write_outputs(checklist: dict[str, Any]) -> None:
    output_dir = Path(str(checklist["output_dir"]))
    json_path = output_dir / OUTPUT_JSON_NAME
    csv_path = output_dir / OUTPUT_CSV_NAME
    readme_path = output_dir / README_NAME
    checklist["artifact_paths"] = {
        "summary_json": str(json_path),
        "actions_csv": str(csv_path),
        "readme_md": str(readme_path),
    }
    write_json(json_path, checklist)
    write_actions_csv(csv_path, checklist)
    write_readme(readme_path, checklist)


def write_error_summary(output_dir: Path, error: str) -> None:
    payload = {
        "schema": SCHEMA,
        "ok": False,
        "status": "invalid_explicit_input_json",
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "error": error,
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "caveats": [INPUT_READINESS_CAVEAT, NO_MEDIA_CAVEAT],
    }
    write_json(output_dir / OUTPUT_JSON_NAME, payload)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    try:
        checklist, exit_code = build_checklist(args)
    except ChecklistInputError as exc:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_error_summary(output_dir, str(exc))
        print(str(exc), file=sys.stderr)
        return 2
    write_outputs(checklist)
    print(json.dumps(checklist, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
