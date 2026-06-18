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

DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_scene_matrix"
SCHEMA = "lerobot.sim.so101_mujoco_scene_matrix.v1"
SCENE_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_scene.py"
SCENE_SUMMARY_NAME = "so101_mujoco_scene_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a focused hardware-free matrix over the development SO-101 MuJoCo "
            "chess scene. Cases exercise different board source/target placements "
            "while keeping the generated MJCF explicitly non-authoritative."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child scene checks.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing output directory before running.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def executable_arg(path: Path) -> str:
    raw = str(path)
    expanded = path.expanduser()
    if expanded.is_absolute():
        return str(expanded)
    if "/" in raw:
        return str((REPO_ROOT / expanded).absolute())
    return raw


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "case_id",
        "ok",
        "return_code",
        "expected_return_code",
        "status",
        "expected_status",
        "model_authority",
        "source_square",
        "target_square",
        "square_geom_count",
        "target_frame_site_present",
        "target_marker_present",
        "model_load_ok",
        "sim_robot_sync_ok",
        "env_scripted_pick_place_complete",
        "ready_for_model_backed_ik",
        "ready_for_policy_training",
        "physical_authority",
        "mujoco_scene_validity_status",
        "configuration_error",
        "model_xml_exists",
        "manifest_json_exists",
        "summary_path",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:
        return {
            "ok": False,
            "status": f"{label}_unavailable",
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": f"{label}_not_json_object",
            "diagnostics": ["expected_json_object"],
        }
    return payload


def case_specs() -> list[dict[str, Any]]:
    return [
        {"case_id": "center_file_scene_e4_e5", "source_square": "e4", "target_square": "e5", "expect_ok": True},
        {"case_id": "corner_diagonal_scene_a1_h8", "source_square": "a1", "target_square": "h8", "expect_ok": True},
        {"case_id": "back_rank_to_edge_scene_b8_a4", "source_square": "b8", "target_square": "a4", "expect_ok": True},
        {"case_id": "edge_to_center_scene_h2_d5", "source_square": "h2", "target_square": "d5", "expect_ok": True},
        {
            "case_id": "invalid_source_square_rejected",
            "source_square": "z9",
            "target_square": "e4",
            "expect_ok": False,
            "expected_error_contains": "Invalid chess square",
        },
        {
            "case_id": "same_source_target_rejected",
            "source_square": "e4",
            "target_square": "e4",
            "expect_ok": False,
            "expected_error_contains": "piece_square and target_square must differ",
        },
    ]


def run_child(
    *,
    case_dir: Path,
    command: list[str],
    expected_summary_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / "stdout.txt"
    stderr_path = case_dir / "stderr.txt"
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    summary = read_json_object(expected_summary_path, label="summary")
    return {
        "command": command,
        "return_code": result.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(expected_summary_path),
    }, summary


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def summarize_case(
    *,
    spec: dict[str, str],
    record: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    case_id = spec["case_id"]
    errors: list[str] = []
    model_load = (
        summary.get("mujoco_model_load")
        if isinstance(summary.get("mujoco_model_load"), dict)
        else {}
    )
    sim_sync = (
        summary.get("sim_robot_mujoco_sync")
        if isinstance(summary.get("sim_robot_mujoco_sync"), dict)
        else {}
    )
    env_result = (
        summary.get("env_scripted_pick_place")
        if isinstance(summary.get("env_scripted_pick_place"), dict)
        else {}
    )
    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    model_xml_path = artifacts.get("model_xml")
    manifest_path = artifacts.get("manifest_json")
    expect_ok = bool(spec.get("expect_ok", True))
    expected_return_code = 0 if expect_ok else 1
    expected_status = "ok" if expect_ok else "invalid_task_configuration"
    expected_scene_validity_status = (
        "development_scene_validated_not_physical_authority"
        if expect_ok
        else "invalid_task_configuration"
    )
    configuration_error = summary.get("configuration_error")
    configuration_error = configuration_error if isinstance(configuration_error, dict) else {}
    observations = {
        "return_code": record.get("return_code"),
        "expected_return_code": expected_return_code,
        "ok": summary.get("ok"),
        "status": summary.get("status"),
        "expected_status": expected_status,
        "model_authority": summary.get("model_authority"),
        "source_square": summary.get("source_square"),
        "target_square": summary.get("target_square"),
        "square_geom_count": summary.get("square_geom_count"),
        "target_frame_site_present": summary.get("target_frame_site_present"),
        "target_marker_present": summary.get("target_marker_present"),
        "model_load_ok": model_load.get("ok"),
        "sim_robot_sync_ok": sim_sync.get("ok"),
        "env_scripted_pick_place_complete": env_result.get("scripted_pick_place_complete"),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": summary.get("ready_for_policy_training"),
        "physical_authority": summary.get("observed_evidence_is_physical_so101_authority"),
        "mujoco_scene_validity_status": summary.get("mujoco_scene_validity_status"),
        "configuration_error": configuration_error,
        "model_xml_exists": isinstance(model_xml_path, str) and Path(model_xml_path).is_file(),
        "manifest_json_exists": isinstance(manifest_path, str) and Path(manifest_path).is_file(),
        "missing_required_geoms": model_load.get("missing_required_geoms"),
        "missing_required_sites": model_load.get("missing_required_sites"),
        "artifacts": artifacts,
    }
    add_error(errors, f"{case_id}.return_code", record.get("return_code"), expected_return_code)
    add_error(errors, f"{case_id}.ok", observations["ok"], expect_ok)
    add_error(errors, f"{case_id}.status", observations["status"], expected_status)
    add_error(
        errors,
        f"{case_id}.model_authority",
        observations["model_authority"],
        "development_scaffold_not_reviewed",
    )
    add_error(errors, f"{case_id}.source_square", observations["source_square"], spec["source_square"])
    add_error(errors, f"{case_id}.target_square", observations["target_square"], spec["target_square"])
    if expect_ok:
        add_error(errors, f"{case_id}.square_geom_count", observations["square_geom_count"], 64)
        add_error(errors, f"{case_id}.target_frame_site_present", observations["target_frame_site_present"], True)
        add_error(errors, f"{case_id}.target_marker_present", observations["target_marker_present"], True)
        add_error(errors, f"{case_id}.model_load_ok", observations["model_load_ok"], True)
        add_error(errors, f"{case_id}.sim_robot_sync_ok", observations["sim_robot_sync_ok"], True)
        add_error(
            errors,
            f"{case_id}.env_scripted_pick_place_complete",
            observations["env_scripted_pick_place_complete"],
            True,
        )
        add_error(
            errors,
            f"{case_id}.mujoco_scene_validity_status",
            observations["mujoco_scene_validity_status"],
            expected_scene_validity_status,
        )
        add_error(errors, f"{case_id}.missing_required_geoms", observations["missing_required_geoms"], [])
        add_error(errors, f"{case_id}.missing_required_sites", observations["missing_required_sites"], [])
        add_error(errors, f"{case_id}.model_xml_exists", observations["model_xml_exists"], True)
        add_error(errors, f"{case_id}.manifest_json_exists", observations["manifest_json_exists"], True)
    else:
        add_error(errors, f"{case_id}.square_geom_count", observations["square_geom_count"], None)
        add_error(errors, f"{case_id}.target_frame_site_present", observations["target_frame_site_present"], None)
        add_error(errors, f"{case_id}.target_marker_present", observations["target_marker_present"], None)
        add_error(errors, f"{case_id}.model_load_ok", observations["model_load_ok"], False)
        add_error(errors, f"{case_id}.sim_robot_sync_ok", observations["sim_robot_sync_ok"], False)
        add_error(
            errors,
            f"{case_id}.env_scripted_pick_place_complete",
            observations["env_scripted_pick_place_complete"],
            False,
        )
        add_error(
            errors,
            f"{case_id}.mujoco_scene_validity_status",
            observations["mujoco_scene_validity_status"],
            expected_scene_validity_status,
        )
        add_error(errors, f"{case_id}.model_xml_exists", observations["model_xml_exists"], False)
        add_error(errors, f"{case_id}.manifest_json_exists", observations["manifest_json_exists"], False)
        expected_error = spec.get("expected_error_contains")
        error_message = configuration_error.get("message")
        if isinstance(expected_error, str) and expected_error not in str(error_message):
            errors.append(f"{case_id}.configuration_error: expected {expected_error!r} in {error_message!r}")
    add_error(errors, f"{case_id}.ready_for_model_backed_ik", observations["ready_for_model_backed_ik"], False)
    add_error(errors, f"{case_id}.ready_for_policy_training", observations["ready_for_policy_training"], False)
    add_error(errors, f"{case_id}.physical_authority", observations["physical_authority"], False)
    artifacts = observations["artifacts"]
    if not isinstance(artifacts, dict):
        errors.append(f"{case_id}.artifacts: expected dict")
    else:
        required_keys = ("summary_json", "model_xml", "manifest_json", "steps_csv", "readme")
        for key in required_keys:
            artifact_path = artifacts.get(key)
            if not isinstance(artifact_path, str):
                errors.append(f"{case_id}.artifacts.{key}: expected existing path")
                continue
            if key in {"model_xml", "manifest_json"} and not expect_ok:
                if Path(artifact_path).exists():
                    errors.append(f"{case_id}.artifacts.{key}: expected absent path for invalid task")
            elif not Path(artifact_path).is_file():
                errors.append(f"{case_id}.artifacts.{key}: expected existing file")

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "record": record,
        "summary_path": record["summary_path"],
        "expected": {
            "source_square": spec["source_square"],
            "target_square": spec["target_square"],
            "ok": expect_ok,
            "return_code": expected_return_code,
            "status": expected_status,
        },
        "observations": observations,
    }


def run_case(
    *,
    output_dir: Path,
    python_path: Path,
    spec: dict[str, str],
) -> dict[str, Any]:
    case_id = spec["case_id"]
    case_dir = output_dir / "cases" / case_id
    command = [
        executable_arg(python_path),
        str(SCENE_SCRIPT),
        "--output-dir",
        str(case_dir),
        "--source-square",
        spec["source_square"],
        "--target-square",
        spec["target_square"],
    ]
    record, summary = run_child(
        case_dir=case_dir,
        command=command,
        expected_summary_path=case_dir / SCENE_SUMMARY_NAME,
    )
    record["case_id"] = case_id
    return summarize_case(spec=spec, record=record, summary=summary)


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    observations = case["observations"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "return_code": observations.get("return_code"),
        "expected_return_code": observations.get("expected_return_code"),
        "status": observations.get("status"),
        "expected_status": observations.get("expected_status"),
        "model_authority": observations.get("model_authority"),
        "source_square": observations.get("source_square"),
        "target_square": observations.get("target_square"),
        "square_geom_count": observations.get("square_geom_count"),
        "target_frame_site_present": observations.get("target_frame_site_present"),
        "target_marker_present": observations.get("target_marker_present"),
        "model_load_ok": observations.get("model_load_ok"),
        "sim_robot_sync_ok": observations.get("sim_robot_sync_ok"),
        "env_scripted_pick_place_complete": observations.get("env_scripted_pick_place_complete"),
        "ready_for_model_backed_ik": observations.get("ready_for_model_backed_ik"),
        "ready_for_policy_training": observations.get("ready_for_policy_training"),
        "physical_authority": observations.get("physical_authority"),
        "mujoco_scene_validity_status": observations.get("mujoco_scene_validity_status"),
        "configuration_error": observations.get("configuration_error"),
        "model_xml_exists": observations.get("model_xml_exists"),
        "manifest_json_exists": observations.get("manifest_json_exists"),
        "summary_path": case["summary_path"],
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 MuJoCo Scene Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "This matrix validates generated development MJCF scene plumbing across several board placements. It is not reviewed physical SO-101 model authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Source | Target | Squares | Target Frame | Target Marker | Env Complete | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{source}` | `{target}` | `{squares}` | `{frame}` | `{marker}` | `{env}` | `{summary}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                source=obs.get("source_square"),
                target=obs.get("target_square"),
                squares=obs.get("square_geom_count"),
                frame=obs.get("target_frame_site_present"),
                marker=obs.get("target_marker_present"),
                env=obs.get("env_scripted_pick_place_complete"),
                summary=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- All cases use generated `development_scaffold_not_reviewed` MJCF.",
            "- Passing cases prove MuJoCo loading, joint sync, target marker/site presence, and Gymnasium loop plumbing only.",
            "- `ready_for_model_backed_ik` and `ready_for_policy_training` must remain false.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        run_case(output_dir=output_dir, python_path=args.python, spec=spec)
        for spec in case_specs()
    ]
    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_mujoco_scene_matrix_summary.json"
    csv_path = output_dir / "so101_mujoco_scene_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "so101_mujoco_scene_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "Generated development scenes are approximate and non-authoritative.",
            "This matrix does not provide reviewed mesh roots, calibrated TCP offset, or base-to-board alignment.",
            "Scene validity here is MuJoCo/Gymnasium plumbing evidence only.",
        ],
    }
    write_json(summary_path, summary)
    write_csv(csv_path, [flatten_case(case) for case in cases])
    write_readme(readme_path, summary)
    print(
        json.dumps(
            {
                "ok": ok,
                "status": summary["status"],
                "summary_json": str(summary_path),
                "cases_csv": str(csv_path),
                "readme_md": str(readme_path),
                "case_ids": summary["case_ids"],
                "failed_cases": summary["failed_case_ids"],
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
