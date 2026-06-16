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
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_bundle_ready_forwarding"
SCHEMA = "lerobot.sim.so101_bundle_ready_forwarding.v1"
SUITE_PATH = REPO_ROOT / "scripts" / "smoke_sim_calibration_regression_suite.py"
EXPECTED_TARGET_FRAME = "gripper_frame_link"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free regression proving the simulator calibration suite forwards a "
            "ready SO-101 model bundle manifest only when it is ready, while preserving explicit "
            "--ik-model-path precedence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for the suite subprocesses.",
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
    if path.is_absolute() or "/" in raw:
        return str(normalize_path(path))
    return raw


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "case_id",
        "ok",
        "suite_status",
        "bundle_ready",
        "forwarding_diagnostic_only",
        "diagnostic_only_reason",
        "ik_model_path_source",
        "ik_model_asset_root_source",
        "effective_ik_model_path",
        "effective_ik_model_asset_roots",
        "artifact_index_missing_count",
        "summary_path",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row[key], sort_keys=True)
                    if isinstance(row.get(key), (dict, list, tuple))
                    else row.get(key)
                    for key in fieldnames
                }
            )


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Bundle Ready Forwarding Smoke",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `ready_manifest`: `{summary['fixtures']['ready_manifest_path']}`",
        f"- `placeholder_manifest`: `{summary['fixtures']['placeholder_manifest_path']}`",
        f"- `explicit_model_path`: `{summary['fixtures']['explicit_model_path']}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "## Cases",
        "",
        "| Case | Status | Forwarding | Artifact index missing | Summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        forwarding = case["observations"]["bundle_forwarding"]
        lines.append(
            "| `{case_id}` | `{status}` | source `{source}`, diagnostic `{diagnostic}` | `{missing}` | `{summary_path}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                source=forwarding.get("ik_model_path_source"),
                diagnostic=forwarding.get("diagnostic_only"),
                missing=case["observations"].get("artifact_index_missing_count"),
                summary_path=case["summary_path"],
            )
        )
    path.write_text("\n".join(lines) + "\n")


def stl_text() -> str:
    return """solid synthetic_so101
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 0.01 0 0
      vertex 0 0.01 0
    endloop
  endfacet
endsolid synthetic_so101
"""


def synthetic_urdf(*, include_mesh: bool) -> str:
    visual = ""
    if include_mesh:
        visual = """
    <visual>
      <geometry>
        <mesh filename="meshes/synthetic_gripper_shell.stl"/>
      </geometry>
    </visual>"""
    return f"""<?xml version="1.0"?>
<robot name="synthetic_so101_forwarding">
  <link name="base_link">{visual}
  </link>
  <link name="shoulder_pan_link"/>
  <link name="shoulder_lift_link"/>
  <link name="elbow_flex_link"/>
  <link name="wrist_flex_link"/>
  <link name="{EXPECTED_TARGET_FRAME}"/>

  <joint name="shoulder_pan" type="revolute">
    <parent link="base_link"/>
    <child link="shoulder_pan_link"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1.919862" upper="1.919862" effort="1" velocity="1"/>
  </joint>
  <joint name="shoulder_lift" type="revolute">
    <parent link="shoulder_pan_link"/>
    <child link="shoulder_lift_link"/>
    <axis xyz="0 1 0"/>
    <limit lower="-1.919862" upper="1.919862" effort="1" velocity="1"/>
  </joint>
  <joint name="elbow_flex" type="revolute">
    <parent link="shoulder_lift_link"/>
    <child link="elbow_flex_link"/>
    <axis xyz="0 1 0"/>
    <limit lower="-2.094395" upper="2.094395" effort="1" velocity="1"/>
  </joint>
  <joint name="wrist_flex" type="revolute">
    <parent link="elbow_flex_link"/>
    <child link="wrist_flex_link"/>
    <axis xyz="0 1 0"/>
    <limit lower="-2.094395" upper="2.094395" effort="1" velocity="1"/>
  </joint>
  <joint name="wrist_roll" type="revolute">
    <parent link="wrist_flex_link"/>
    <child link="{EXPECTED_TARGET_FRAME}"/>
    <axis xyz="1 0 0"/>
    <limit lower="-3.141593" upper="3.141593" effort="1" velocity="1"/>
  </joint>
</robot>
"""


def manifest_payload(*, ready: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_path": "model/synthetic_so101.urdf",
        "asset_roots": ["assets"],
        "authority": {
            "source_authority_status": "synthetic_smoke_reviewed",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-16",
            "scope": "hardware-free forwarding regression only",
        },
        "provenance": {
            "source_url": "local synthetic fixture",
            "source_commit": "not_applicable",
            "export_tool": "smoke_sim_so101_bundle_ready_forwarding.py",
            "license": "test-only",
        },
        "target_frame": EXPECTED_TARGET_FRAME,
        "tcp_offset_m": {"x": 0.0, "y": 0.0, "z": 0.075},
    }
    if ready:
        payload["base_to_board_transform"] = {
            "translation_m": {"x": 0.10, "y": -0.175, "z": 0.09},
            "rotation_rpy_rad": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            "source": "synthetic deterministic smoke fixture",
        }
    else:
        payload["base_to_board_alignment_placeholder"] = {
            "reason": "negative fixture must not become ready without real base_to_board_transform",
        }
    return payload


def create_fixtures(output_dir: Path) -> dict[str, Path]:
    fixture_dir = output_dir / "fixtures"
    bundle_dir = fixture_dir / "ready_bundle"
    placeholder_dir = fixture_dir / "placeholder_bundle"
    explicit_dir = fixture_dir / "explicit_cli"

    for root in (bundle_dir, placeholder_dir):
        (root / "model").mkdir(parents=True, exist_ok=True)
        (root / "model" / "meshes").mkdir(parents=True, exist_ok=True)
        (root / "assets" / "meshes").mkdir(parents=True, exist_ok=True)
        (root / "model" / "synthetic_so101.urdf").write_text(synthetic_urdf(include_mesh=True))
        (root / "model" / "meshes" / "synthetic_gripper_shell.stl").write_text(stl_text())
        (root / "assets" / "meshes" / "synthetic_gripper_shell.stl").write_text(stl_text())

    explicit_dir.mkdir(parents=True, exist_ok=True)
    explicit_model_path = explicit_dir / "explicit_cli_so101.urdf"
    explicit_model_path.write_text(synthetic_urdf(include_mesh=False))

    ready_manifest_path = bundle_dir / "so101_model_bundle.ready.json"
    placeholder_manifest_path = placeholder_dir / "so101_model_bundle.placeholder.json"
    write_json(ready_manifest_path, manifest_payload(ready=True))
    write_json(placeholder_manifest_path, manifest_payload(ready=False))

    return {
        "ready_manifest_path": ready_manifest_path,
        "placeholder_manifest_path": placeholder_manifest_path,
        "ready_model_path": bundle_dir / "model" / "synthetic_so101.urdf",
        "ready_asset_root": bundle_dir / "assets",
        "explicit_model_path": explicit_model_path,
    }


def run_suite_case(
    *,
    case_id: str,
    python_path: Path,
    output_dir: Path,
    manifest_path: Path,
    explicit_model_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_dir = output_dir / case_id
    summary_path = case_dir / "calibration_regression_summary.json"
    python_executable = executable_arg(python_path)
    command = [
        python_executable,
        str(SUITE_PATH),
        "--output-dir",
        str(case_dir),
        "--python",
        python_executable,
        "--include-negative-check",
        "--so101-model-bundle-manifest",
        str(manifest_path),
    ]
    if explicit_model_path is not None:
        command.extend(["--ik-model-path", str(explicit_model_path)])

    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / f"{case_id}_stdout.txt"
    stderr_path = case_dir / f"{case_id}_stderr.txt"
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)

    try:
        suite_summary = json.loads(summary_path.read_text())
    except Exception as exc:
        suite_summary = {
            "ok": False,
            "status": "summary_unavailable",
            "summary_error": f"{type(exc).__name__}: {exc}",
        }

    record = {
        "case_id": case_id,
        "command": command,
        "return_code": result.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(summary_path),
    }
    return record, suite_summary


def get_nested(payload: dict[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def command_contains(command: Any, value: Path) -> bool:
    if not isinstance(command, list):
        return False
    target = str(value)
    return any(str(item) == target for item in command)


def assert_equal(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(errors: list[str], label: str, value: Any) -> None:
    if value is not True:
        errors.append(f"{label}: expected true, got {value!r}")


def assert_false(errors: list[str], label: str, value: Any) -> None:
    if value is not False:
        errors.append(f"{label}: expected false, got {value!r}")


def summarize_case(
    *,
    record: dict[str, Any],
    suite_summary: dict[str, Any],
    fixtures: dict[str, Path],
    expectation: str,
) -> dict[str, Any]:
    errors: list[str] = []
    case_id = str(record["case_id"])
    forwarding = get_nested(suite_summary, ("so101_model_bundle_manifest", "forwarding"), {})
    bundle = get_nested(suite_summary, ("so101_model_bundle_manifest",), {})
    contract = get_nested(suite_summary, ("so101_model_contract",), {})
    contract_preflight = get_nested(suite_summary, ("so101_model_contract", "model_asset_preflight"), {})
    bundle_preflight = get_nested(suite_summary, ("so101_model_bundle_manifest", "model_asset_preflight"), {})
    artifact_index_missing_count = get_nested(suite_summary, ("artifact_index", "missing_artifact_count"))
    contract_command = get_nested(suite_summary, ("child_commands", "so101_model_contract", "command"), [])
    ik_command = get_nested(suite_summary, ("child_commands", "ik_reachability_drill", "command"), [])

    assert_equal(errors, f"{case_id}.suite_return_code", record["return_code"], 0)
    assert_true(errors, f"{case_id}.suite_ok", suite_summary.get("ok"))
    assert_equal(errors, f"{case_id}.suite_status", suite_summary.get("status"), "ok")
    assert_equal(errors, f"{case_id}.artifact_index_missing_count", artifact_index_missing_count, 0)

    ready_model_path = normalize_path(fixtures["ready_model_path"])
    ready_asset_root = normalize_path(fixtures["ready_asset_root"])
    explicit_model_path = normalize_path(fixtures["explicit_model_path"])

    if expectation == "ready_manifest_forwarded":
        assert_true(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_false(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_true(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "so101_model_bundle_manifest")
        assert_equal(errors, f"{case_id}.ik_model_asset_root_source", forwarding.get("ik_model_asset_root_source"), "so101_model_bundle_manifest")
        assert_equal(errors, f"{case_id}.effective_ik_model_path", forwarding.get("effective_ik_model_path"), str(ready_model_path))
        assert_equal(
            errors,
            f"{case_id}.effective_asset_roots",
            forwarding.get("effective_ik_model_asset_roots"),
            [str(ready_asset_root)],
        )
        assert_true(errors, f"{case_id}.contract_command_has_manifest_model", command_contains(contract_command, ready_model_path))
        assert_true(errors, f"{case_id}.contract_command_has_manifest_asset_root", command_contains(contract_command, ready_asset_root))
        assert_true(errors, f"{case_id}.ik_command_has_manifest_model", command_contains(ik_command, ready_model_path))
        assert_equal(errors, f"{case_id}.contract_model_path", get_nested(contract, ("model_request", "path")), str(ready_model_path))
        assert_equal(errors, f"{case_id}.contract_preflight_missing", contract_preflight.get("missing_asset_count"), 0)
        assert_equal(errors, f"{case_id}.contract_preflight_unresolved", contract_preflight.get("unresolved_reference_count"), 0)
        assert_equal(errors, f"{case_id}.bundle_preflight_missing", bundle_preflight.get("missing_asset_count"), 0)
    elif expectation == "explicit_cli_precedence":
        assert_true(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(errors, f"{case_id}.diagnostic_reason", forwarding.get("diagnostic_only_reason"), "explicit_ik_model_path_supplied")
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "explicit_cli")
        assert_equal(errors, f"{case_id}.effective_ik_model_path", forwarding.get("effective_ik_model_path"), str(explicit_model_path))
        assert_true(errors, f"{case_id}.contract_command_has_explicit_model", command_contains(contract_command, explicit_model_path))
        assert_false(errors, f"{case_id}.contract_command_has_manifest_model", command_contains(contract_command, ready_model_path))
        assert_false(errors, f"{case_id}.contract_command_has_manifest_asset_root", command_contains(contract_command, ready_asset_root))
        assert_true(errors, f"{case_id}.ik_command_has_explicit_model", command_contains(ik_command, explicit_model_path))
        assert_false(errors, f"{case_id}.ik_command_has_manifest_model", command_contains(ik_command, ready_model_path))
        assert_equal(errors, f"{case_id}.contract_model_path", get_nested(contract, ("model_request", "path")), str(explicit_model_path))
        assert_equal(errors, f"{case_id}.contract_preflight_missing", contract_preflight.get("missing_asset_count"), 0)
        assert_equal(errors, f"{case_id}.contract_preflight_unresolved", contract_preflight.get("unresolved_reference_count"), 0)
    elif expectation == "placeholder_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "not_supplied")
        assert_equal(errors, f"{case_id}.effective_ik_model_path", forwarding.get("effective_ik_model_path"), None)
        assert_false(errors, f"{case_id}.contract_command_has_manifest_model", command_contains(contract_command, ready_model_path))
        assert_false(errors, f"{case_id}.ik_command_has_manifest_model", command_contains(ik_command, ready_model_path))
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "placeholder_only",
        )
    else:
        errors.append(f"{case_id}.unknown_expectation:{expectation}")

    status = "ok" if not errors else "failed"
    return {
        "case_id": case_id,
        "ok": not errors,
        "status": status,
        "errors": errors,
        "record": record,
        "summary_path": record["summary_path"],
        "observations": {
            "suite_status": suite_summary.get("status"),
            "bundle_status": bundle.get("status"),
            "bundle_ready": bundle.get("ready_for_model_backed_ik"),
            "bundle_forwarding": forwarding,
            "contract_model_request": contract.get("model_request"),
            "contract_asset_preflight": contract_preflight,
            "bundle_asset_preflight": bundle_preflight,
            "artifact_index_missing_count": artifact_index_missing_count,
        },
    }


def flatten_case_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        forwarding = case["observations"]["bundle_forwarding"]
        rows.append(
            {
                "case_id": case["case_id"],
                "ok": case["ok"],
                "suite_status": case["observations"]["suite_status"],
                "bundle_ready": case["observations"]["bundle_ready"],
                "forwarding_diagnostic_only": forwarding.get("diagnostic_only"),
                "diagnostic_only_reason": forwarding.get("diagnostic_only_reason"),
                "ik_model_path_source": forwarding.get("ik_model_path_source"),
                "ik_model_asset_root_source": forwarding.get("ik_model_asset_root_source"),
                "effective_ik_model_path": forwarding.get("effective_ik_model_path"),
                "effective_ik_model_asset_roots": forwarding.get("effective_ik_model_asset_roots"),
                "artifact_index_missing_count": case["observations"]["artifact_index_missing_count"],
                "summary_path": case["summary_path"],
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures = create_fixtures(output_dir)
    case_specs = [
        {
            "case_id": "ready_manifest_forwarded",
            "manifest_path": fixtures["ready_manifest_path"],
            "explicit_model_path": None,
            "expectation": "ready_manifest_forwarded",
        },
        {
            "case_id": "explicit_cli_precedence",
            "manifest_path": fixtures["ready_manifest_path"],
            "explicit_model_path": fixtures["explicit_model_path"],
            "expectation": "explicit_cli_precedence",
        },
        {
            "case_id": "placeholder_manifest_not_forwarded",
            "manifest_path": fixtures["placeholder_manifest_path"],
            "explicit_model_path": None,
            "expectation": "placeholder_not_forwarded",
        },
    ]

    cases: list[dict[str, Any]] = []
    for spec in case_specs:
        record, suite_summary = run_suite_case(
            case_id=spec["case_id"],
            python_path=args.python,
            output_dir=output_dir,
            manifest_path=spec["manifest_path"],
            explicit_model_path=spec["explicit_model_path"],
        )
        cases.append(
            summarize_case(
                record=record,
                suite_summary=suite_summary,
                fixtures=fixtures,
                expectation=spec["expectation"],
            )
        )

    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_bundle_ready_forwarding_summary.json"
    csv_path = output_dir / "so101_bundle_ready_forwarding_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "fixtures": {key: str(normalize_path(value)) for key, value in fixtures.items()},
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "Synthetic URDF and mesh fixtures live under the smoke output directory and are not physical SO-101 calibration truth.",
            "This smoke invokes the integrated simulator calibration regression suite as the system under test.",
            "It does not open robot hardware, cameras, GUI flows, network resources, or LLM/OpenAI paths.",
        ],
    }
    write_json(summary_path, summary)
    write_csv(csv_path, flatten_case_rows(cases))
    write_readme(readme_path, summary)

    print(
        json.dumps(
            {
                "ok": ok,
                "status": summary["status"],
                "summary_json": str(summary_path),
                "cases_csv": str(csv_path),
                "readme_md": str(readme_path),
                "failed_cases": [case["case_id"] for case in cases if not case["ok"]],
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
