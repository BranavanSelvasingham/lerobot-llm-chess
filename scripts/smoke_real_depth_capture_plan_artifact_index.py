#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_depth_capture_plan_artifact_index"
BRIDGE_SMOKE = REPO_ROOT / "scripts" / "smoke_real_depth_capture_plan_manifest_bridge.py"
BRIDGE_SUMMARY_NAME = "real_depth_capture_plan_manifest_bridge_smoke_summary.json"
SCHEMA = "lerobot.sim.real_depth_capture_plan_artifact_index.v1"
BRIDGE_SCHEMA = "lerobot.sim.real_depth_capture_plan_manifest_bridge_smoke.v1"
INDEX_JSON_NAME = "real_depth_capture_plan_artifact_index.json"
INDEX_CSV_NAME = "real_depth_capture_plan_artifact_index_cases.csv"
README_NAME = "README.md"
INPUT_READINESS_CAVEAT = (
    "Ready reference-capture-manifest evidence is input readiness only; physical calibration "
    "truth still requires subsequent sidecar validation, intake, and residual comparison artifacts."
)


class SummaryInputError(ValueError):
    """Raised when the bridge-smoke summary cannot be used as an index source."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a narrow hardware-free operator-side index for real depth capture "
            "planner bridge-smoke artifacts."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--bridge-smoke-summary-json",
        type=Path,
        default=None,
        help=(
            "Existing real_depth_capture_plan_manifest_bridge_smoke_summary.json to index. "
            "If omitted, the bridge smoke is run as a child under --output-dir."
        ),
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used when invoking the bridge smoke child.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SummaryInputError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SummaryInputError(f"Invalid JSON in {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SummaryInputError(f"{label} {path} must contain a JSON object.")
    return payload


def python_command(path: Path) -> str:
    text = str(path.expanduser())
    if path.is_absolute() or "/" in text:
        return text
    return shutil.which(text) or text


def resolve_cli_path(path: Path) -> Path:
    path = path.expanduser()
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def resolve_artifact_path(path_text: Any, *, base_dir: Path) -> Path | None:
    if not isinstance(path_text, str) or not path_text.strip():
        return None
    path = Path(path_text).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def run_child(command: list[str], *, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path.write_text(result.stdout)
        stderr_path.write_text(result.stderr)
        exit_code = result.returncode
    except FileNotFoundError as exc:
        stdout_path.write_text("")
        stderr_path.write_text(str(exc) + "\n")
        exit_code = 127
    return {
        "command": command,
        "exit_code": exit_code,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def run_bridge_smoke(*, output_dir: Path, python: str) -> tuple[Path, dict[str, Any]]:
    bridge_output_dir = output_dir / "bridge_smoke"
    log_dir = output_dir / "child_logs"
    run = run_child(
        [
            python,
            str(BRIDGE_SMOKE),
            "--output-dir",
            str(bridge_output_dir),
            "--python",
            python,
        ],
        stdout_path=log_dir / "bridge_smoke_stdout.json",
        stderr_path=log_dir / "bridge_smoke_stderr.txt",
    )
    return bridge_output_dir / BRIDGE_SUMMARY_NAME, run


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


def markdown_metadata(path: Path | None) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if path is None:
        return {"status": "not_supplied", "path": None}, [
            {"id": "planner_markdown_path_not_supplied", "severity": "warning", "path": ""}
        ]
    if not path.is_file():
        return {"status": "missing", "path": str(path)}, [
            {"id": "planner_markdown_missing", "severity": "warning", "path": str(path)}
        ]
    text = path.read_text()
    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), "")
    return {
        "status": "present",
        "path": str(path),
        "title": title,
        "line_count": len(text.splitlines()),
        "byte_count": len(text.encode()),
    }, []


def planner_json_metadata(path: Path | None) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    if path is None:
        return {"status": "not_supplied", "path": None}, {}, [
            {"id": "planner_json_path_not_supplied", "severity": "warning", "path": ""}
        ]
    if not path.is_file():
        return {"status": "missing", "path": str(path)}, {}, [
            {"id": "planner_json_missing", "severity": "warning", "path": str(path)}
        ]
    try:
        payload = read_json_object(path, label="planner JSON")
    except SummaryInputError as exc:
        return {"status": "invalid_json", "path": str(path), "error": str(exc)}, {}, [
            {"id": "planner_json_invalid", "severity": "warning", "path": str(path), "detail": str(exc)}
        ]
    return {
        "status": "present",
        "path": str(path),
        "schema": payload.get("schema"),
        "ok": payload.get("ok"),
        "status_field": payload.get("status"),
    }, payload, []


def action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [str(row["id"]) for row in actions if isinstance(row.get("id"), str)]


def action_summaries(actions: list[dict[str, Any]]) -> list[str]:
    summaries: list[str] = []
    for action in actions:
        action_id = action.get("id")
        operator_action = action.get("operator_action")
        if isinstance(action_id, str) and isinstance(operator_action, str):
            summaries.append(f"{action_id}: {operator_action}")
    return summaries


def child_run_paths(run: Any) -> tuple[list[str], list[str]]:
    run = run if isinstance(run, dict) else {}
    stdout = run.get("stdout_path")
    stderr = run.get("stderr_path")
    return (
        [stdout] if isinstance(stdout, str) and stdout else [],
        [stderr] if isinstance(stderr, str) and stderr else [],
    )


def checker_run_for_case(case: dict[str, Any], bridge_summary: dict[str, Any]) -> dict[str, Any]:
    child_runs = bridge_summary.get("child_runs")
    child_runs = child_runs if isinstance(child_runs, dict) else {}
    case_id = str(case.get("case_id") or "")
    if "missing" in case_id:
        return child_runs.get("missing_manifest_check") if isinstance(child_runs.get("missing_manifest_check"), dict) else {}
    if "ready" in case_id:
        return child_runs.get("ready_manifest_check") if isinstance(child_runs.get("ready_manifest_check"), dict) else {}
    return {}


def summarize_case(
    *,
    case: dict[str, Any],
    bridge_summary: dict[str, Any],
    bridge_summary_dir: Path,
    generated_bridge_run: dict[str, Any] | None,
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    planner_json_path = resolve_artifact_path(case.get("plan_json"), base_dir=bridge_summary_dir)
    planner_markdown_path = resolve_artifact_path(case.get("plan_markdown"), base_dir=bridge_summary_dir)
    planner_json, plan_summary, planner_json_diagnostics = planner_json_metadata(planner_json_path)
    planner_markdown, planner_markdown_diagnostics = markdown_metadata(planner_markdown_path)
    diagnostics.extend(planner_json_diagnostics)
    diagnostics.extend(planner_markdown_diagnostics)

    plan_evidence = plan_summary.get("reference_capture_manifest_evidence")
    plan_evidence = plan_evidence if isinstance(plan_evidence, dict) else {}
    next_actions = list_of_dicts(case.get("next_operator_actions")) or list_of_dicts(
        plan_evidence.get("next_operator_actions")
    )
    no_copy = plan_evidence.get("no_copy_status")
    no_copy = no_copy if isinstance(no_copy, dict) else {}

    planner_stdout, planner_stderr = child_run_paths(case.get("planner_run"))
    checker_stdout, checker_stderr = child_run_paths(checker_run_for_case(case, bridge_summary))
    bridge_stdout, bridge_stderr = child_run_paths(generated_bridge_run)
    caveats = [
        str(case.get("caveat") or plan_evidence.get("caveat") or INPUT_READINESS_CAVEAT),
        INPUT_READINESS_CAVEAT,
    ]
    compact_caveats = list(dict.fromkeys(caveat for caveat in caveats if caveat))

    evidence_media_copied = case.get("media_assets_copied_into_repo")
    if evidence_media_copied is None:
        evidence_media_copied = plan_evidence.get("media_assets_copied_into_repo")

    return {
        "case_id": case.get("case_id"),
        "scenario_label": case.get("scenario_label"),
        "evidence_arg": case.get("evidence_arg"),
        "evidence_path": case.get("evidence_path"),
        "evidence_source_kind": case.get("evidence_source_kind") or plan_evidence.get("source_kind"),
        "evidence_status": case.get("evidence_status") or plan_evidence.get("status"),
        "ready_for_calibration_grade_simcamera_tuning": bool(
            case.get("ready_for_calibration_grade_simcamera_tuning")
            or plan_evidence.get("ready_for_calibration_grade_simcamera_tuning")
        ),
        "depth_reference_capture_count": int_value(
            case.get("depth_reference_capture_count")
            if case.get("depth_reference_capture_count") is not None
            else plan_evidence.get("depth_reference_capture_count")
        ),
        "pick_place_video_capture_count": int_value(
            case.get("pick_place_video_capture_count")
            if case.get("pick_place_video_capture_count") is not None
            else plan_evidence.get("pick_place_video_capture_count")
        ),
        "path_check_count": int_value(
            case.get("path_check_count")
            if case.get("path_check_count") is not None
            else plan_evidence.get("path_check_count")
        ),
        "missing_path_count": int_value(
            case.get("missing_path_count")
            if case.get("missing_path_count") is not None
            else plan_evidence.get("missing_path_count")
        ),
        "no_copy_status": case.get("no_copy_status") or no_copy.get("status"),
        "evidence_media_assets_copied_into_repo": evidence_media_copied,
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "next_operator_action_ids": action_ids(next_actions),
        "next_operator_actions": next_actions,
        "next_operator_action_summaries": action_summaries(next_actions),
        "planner_json_path": planner_json.get("path"),
        "planner_json_status": planner_json.get("status"),
        "planner_json": planner_json,
        "planner_markdown_path": planner_markdown.get("path"),
        "planner_markdown_status": planner_markdown.get("status"),
        "planner_markdown": planner_markdown,
        "planner_stdout_path": planner_stdout[0] if planner_stdout else None,
        "planner_stderr_path": planner_stderr[0] if planner_stderr else None,
        "child_stdout_paths": planner_stdout + checker_stdout + bridge_stdout,
        "child_stderr_paths": planner_stderr + checker_stderr + bridge_stderr,
        "caveats": compact_caveats,
        "diagnostics": diagnostics,
    }


def validate_bridge_summary(summary: dict[str, Any], summary_path: Path) -> None:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        raise SummaryInputError(f"Bridge smoke summary {summary_path} does not contain a cases list.")
    schema = summary.get("schema")
    if schema != BRIDGE_SCHEMA:
        raise SummaryInputError(
            f"Bridge smoke summary {summary_path} has unexpected schema {schema!r}; expected {BRIDGE_SCHEMA!r}."
        )


def build_index(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    python = python_command(args.python)
    generated_bridge_run: dict[str, Any] | None = None

    if args.bridge_smoke_summary_json is None:
        bridge_summary_path, generated_bridge_run = run_bridge_smoke(output_dir=output_dir, python=python)
        source_mode = "generated_child_smoke"
    else:
        bridge_summary_path = resolve_cli_path(args.bridge_smoke_summary_json)
        source_mode = "supplied_summary"

    bridge_summary = read_json_object(bridge_summary_path, label="bridge smoke summary")
    validate_bridge_summary(bridge_summary, bridge_summary_path)
    bridge_summary_dir = bridge_summary_path.parent
    cases = [
        summarize_case(
            case=case,
            bridge_summary=bridge_summary,
            bridge_summary_dir=bridge_summary_dir,
            generated_bridge_run=generated_bridge_run,
        )
        for case in list_of_dicts(bridge_summary.get("cases"))
    ]
    diagnostics = [
        {
            "id": "case_artifact_diagnostic",
            "case_id": case.get("case_id"),
            **diagnostic,
        }
        for case in cases
        for diagnostic in list_of_dicts(case.get("diagnostics"))
    ]
    if generated_bridge_run is not None and generated_bridge_run.get("exit_code") != 0:
        diagnostics.append(
            {
                "id": "generated_bridge_smoke_failed",
                "severity": "error",
                "exit_code": generated_bridge_run.get("exit_code"),
                "stderr_path": generated_bridge_run.get("stderr_path"),
            }
        )

    index_path = output_dir / INDEX_JSON_NAME
    csv_path = output_dir / INDEX_CSV_NAME
    readme_path = output_dir / README_NAME
    generated_child_failed = generated_bridge_run is not None and generated_bridge_run.get("exit_code") != 0
    status = "failed_child_smoke" if generated_child_failed else ("ok_with_diagnostics" if diagnostics else "ok")
    index = {
        "schema": SCHEMA,
        "ok": not generated_child_failed,
        "status": status,
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "python": python,
        "source_mode": source_mode,
        "bridge_smoke_summary_json": str(bridge_summary_path),
        "bridge_smoke_child_run": generated_bridge_run,
        "bridge_smoke": {
            "schema": bridge_summary.get("schema"),
            "ok": bridge_summary.get("ok"),
            "status": bridge_summary.get("status"),
            "summary_path": bridge_summary.get("summary_path"),
            "csv_path": bridge_summary.get("csv_path"),
            "readme_path": bridge_summary.get("readme_path"),
            "output_dir": bridge_summary.get("output_dir"),
            "media_assets_copied_into_repo": bridge_summary.get("media_assets_copied_into_repo"),
            "media_assets_opened_or_decoded": bridge_summary.get("media_assets_opened_or_decoded"),
            "child_runs": bridge_summary.get("child_runs") if isinstance(bridge_summary.get("child_runs"), dict) else {},
        },
        "artifact_index_path": str(index_path),
        "csv_path": str(csv_path),
        "readme_path": str(readme_path),
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "case_count": len(cases),
        "diagnostic_count": len(diagnostics),
        "cases": cases,
        "diagnostics": diagnostics,
        "caveats": [
            INPUT_READINESS_CAVEAT,
            "This index reads planner JSON/Markdown artifacts and bridge-smoke metadata only.",
            "It does not copy, open, decode, modify, or commit photos or videos.",
        ],
    }
    write_json(index_path, index)
    write_cases_csv(csv_path, cases)
    write_readme(readme_path, index)
    return index, 1 if generated_child_failed else 0


def write_cases_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "evidence_source_kind",
        "evidence_status",
        "ready_for_calibration_grade_simcamera_tuning",
        "depth_reference_capture_count",
        "pick_place_video_capture_count",
        "missing_path_count",
        "no_copy_status",
        "evidence_media_assets_copied_into_repo",
        "media_assets_copied_into_repo",
        "media_assets_opened_or_decoded",
        "next_operator_action_ids",
        "planner_json_path",
        "planner_json_status",
        "planner_markdown_path",
        "planner_markdown_status",
        "planner_stdout_path",
        "planner_stderr_path",
        "child_stdout_paths",
        "child_stderr_paths",
        "caveats",
        "diagnostics",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            row = {field: case.get(field, "") for field in fieldnames}
            row["next_operator_action_ids"] = ",".join(string_list(case.get("next_operator_action_ids")))
            row["child_stdout_paths"] = ";".join(string_list(case.get("child_stdout_paths")))
            row["child_stderr_paths"] = ";".join(string_list(case.get("child_stderr_paths")))
            row["caveats"] = " | ".join(string_list(case.get("caveats")))
            row["diagnostics"] = ",".join(str(item.get("id")) for item in list_of_dicts(case.get("diagnostics")))
            writer.writerow(row)


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


def write_readme(path: Path, index: dict[str, Any]) -> None:
    cases = list_of_dicts(index.get("cases"))
    diagnostics = list_of_dicts(index.get("diagnostics"))
    lines = [
        "# Real Depth Capture Plan Artifact Index",
        "",
        "This hardware-free index gathers the bridge-smoke summary and planner JSON/Markdown outputs into one operator-side report.",
        "",
        "It does not open cameras, move robot hardware, call OpenAI, copy media, open media, or decode media. Ready evidence is input readiness only, not physical calibration truth.",
        "",
        "## Source",
        "",
        f"- Mode: `{index.get('source_mode')}`",
        f"- Bridge smoke summary: `{index.get('bridge_smoke_summary_json')}`",
        f"- Bridge smoke status: `{index.get('bridge_smoke', {}).get('status')}`",
        f"- Media copied into repo by this index: `{index.get('media_assets_copied_into_repo')}`",
        f"- Media opened or decoded by this index: `{index.get('media_assets_opened_or_decoded')}`",
        "",
        "## Cases",
    ]
    lines.extend(
        markdown_table(
            [
                "Case",
                "Evidence",
                "Status",
                "Ready",
                "Depth",
                "Pick/place",
                "Missing paths",
                "No-copy",
                "Planner JSON",
                "Planner Markdown",
            ],
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
                    case.get("planner_json_path"),
                    case.get("planner_markdown_path"),
                ]
                for case in cases
            ],
        )
    )
    lines.extend(["", "## Next Operator Actions"])
    for case in cases:
        lines.extend(["", f"### {case.get('case_id')}", ""])
        actions = list_of_dicts(case.get("next_operator_actions"))
        if not actions:
            lines.append("- No next actions recorded.")
        for action in actions:
            lines.append(f"- `{action.get('id')}`: {action.get('operator_action')}")
    lines.extend(["", "## Child Logs"])
    for case in cases:
        lines.extend(["", f"### {case.get('case_id')}", ""])
        stdout_paths = string_list(case.get("child_stdout_paths"))
        stderr_paths = string_list(case.get("child_stderr_paths"))
        if not stdout_paths and not stderr_paths:
            lines.append("- No child log paths recorded.")
        for stdout_path in stdout_paths:
            lines.append(f"- stdout: `{stdout_path}`")
        for stderr_path in stderr_paths:
            lines.append(f"- stderr: `{stderr_path}`")
    lines.extend(["", "## Diagnostics"])
    if not diagnostics:
        lines.append("- No missing planner artifacts or index diagnostics were recorded.")
    for diagnostic in diagnostics:
        detail = diagnostic.get("detail") or diagnostic.get("path") or diagnostic.get("stderr_path") or ""
        lines.append(f"- `{diagnostic.get('id')}` ({diagnostic.get('severity', 'info')}): {detail}")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Ready reference-capture-manifest evidence is input readiness only.",
            "- Physical calibration claims still require sidecar validation, real projection intake, and residual comparison evidence.",
            "- Photos and videos are not copied, opened, decoded, modified, or committed by this index.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def write_error_summary(output_dir: Path, error: str) -> None:
    payload = {
        "schema": SCHEMA,
        "ok": False,
        "status": "invalid_bridge_smoke_summary",
        "output_dir": str(output_dir),
        "error": error,
        "media_assets_copied_into_repo": False,
        "media_assets_opened_or_decoded": False,
        "caveats": [
            INPUT_READINESS_CAVEAT,
            "No media assets are copied, opened, decoded, modified, or committed by this error path.",
        ],
    }
    write_json(output_dir / INDEX_JSON_NAME, payload)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    try:
        index, exit_code = build_index(args)
    except SummaryInputError as exc:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_error_summary(output_dir, str(exc))
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(index, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
