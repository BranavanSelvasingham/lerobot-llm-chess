#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "lerobot.sim.so101_model_bundle_probe.v1"
CANDIDATE_SCHEMA = "lerobot.sim.so101_model_bundle_candidate.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_bundle_probe"
REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_contract.py"
MANIFEST_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_manifest.py"
EXPECTED_TARGET_FRAME = "gripper_frame_link"

CSV_FIELDNAMES = (
    "requirement_id",
    "category",
    "status",
    "severity",
    "observed_value",
    "expected_value",
    "missing_inputs",
    "diagnostics",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a hardware-free SO-101 model bundle manifest draft from a candidate "
            "URDF/MJCF path plus optional mesh asset roots, then run the existing contract "
            "and bundle-manifest diagnostics against that draft."
        )
    )
    parser.add_argument("--model-path", type=Path, default=None)
    parser.add_argument(
        "--asset-root",
        type=Path,
        action="append",
        default=[],
        help="Additional mesh/asset root for the candidate bundle. Repeatable.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-frame", default=EXPECTED_TARGET_FRAME)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child contract/manifest tooling.",
    )
    parser.add_argument(
        "--authority-reviewed-by",
        default=None,
        help="Optional reviewed-by identifier. Authority is populated only with --authority-reviewed-at too.",
    )
    parser.add_argument(
        "--authority-reviewed-at",
        default=None,
        help="Optional deterministic review date/string. Authority is populated only with --authority-reviewed-by too.",
    )
    parser.add_argument("--provenance-source-url", default=None)
    parser.add_argument("--provenance-source-commit", default=None)
    parser.add_argument("--provenance-export-tool", default=None)
    parser.add_argument("--provenance-license", default=None)
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        normalized = normalize_path(path)
        key = str(normalized)
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def executable_arg(path: Path) -> str:
    raw = str(path)
    if path.is_absolute() or "/" in raw:
        return str(normalize_path(path))
    return raw


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in CSV_FIELDNAMES})


def run_child(command: list[str], summary_path: Path) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    base: dict[str, Any] = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "summary_json": str(summary_path),
    }
    if result.returncode != 0:
        return {
            **base,
            "ok": False,
            "status": "child_failed",
            "diagnostics": [
                {
                    "diagnostic": "child_nonzero",
                    "severity": "action_required",
                    "returncode": result.returncode,
                }
            ],
        }
    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        return {
            **base,
            "ok": False,
            "status": "child_summary_unavailable",
            "diagnostics": [
                {
                    "diagnostic": "child_summary_unavailable",
                    "severity": "action_required",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            ],
        }
    if not isinstance(summary, dict):
        return {
            **base,
            "ok": False,
            "status": "child_summary_not_object",
            "diagnostics": [
                {
                    "diagnostic": "child_summary_not_object",
                    "severity": "action_required",
                }
            ],
        }
    return {**base, "ok": bool(summary.get("ok")), "status": summary.get("status"), "summary": summary}


def run_contract_checker(
    python_path: Path,
    output_dir: Path,
    model_path: Path | None,
    asset_roots: list[Path],
    target_frame: str,
) -> dict[str, Any]:
    contract_dir = output_dir / "so101_model_contract"
    summary_path = contract_dir / "so101_model_contract_summary.json"
    command = [
        executable_arg(python_path),
        str(CONTRACT_CHECKER_PATH),
        "--output-dir",
        str(contract_dir),
        "--target-frame",
        target_frame,
    ]
    if model_path is not None:
        command.extend(["--model-path", str(model_path)])
    for asset_root in asset_roots:
        command.extend(["--model-asset-root", str(asset_root)])
    result = run_child(command, summary_path)
    result["artifacts"] = {
        "summary_json": str(summary_path),
        "checklist_csv": str(contract_dir / "so101_model_contract_checklist.csv"),
        "readme_md": str(contract_dir / "README.md"),
    }
    summary = result.get("summary") or {}
    asset_preflight = summary.get("model_asset_preflight") or {}
    result["diagnostic_excerpt"] = {
        "status": summary.get("status", result.get("status")),
        "model_request_status": (summary.get("model_request") or {}).get("status"),
        "robot_kinematics_status": (summary.get("robot_kinematics_path") or {}).get("status"),
        "robot_kinematics_initialization_status": (summary.get("robot_kinematics_initialization") or {}).get("status"),
        "model_asset_preflight": {
            "status": asset_preflight.get("status"),
            "asset_roots": asset_preflight.get("asset_roots"),
            "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
            "present_asset_count": asset_preflight.get("present_asset_count"),
            "missing_asset_count": asset_preflight.get("missing_asset_count"),
            "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
            "diagnostics": asset_preflight.get("diagnostics", []),
            "limitations": asset_preflight.get("limitations", []),
            "artifacts": asset_preflight.get("artifacts"),
        },
        "artifacts": result["artifacts"],
    }
    return result


def run_manifest_checker(
    python_path: Path,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest_dir = output_dir / "so101_model_bundle_manifest_check"
    summary_path = manifest_dir / "so101_model_bundle_manifest_summary.json"
    command = [
        executable_arg(python_path),
        str(MANIFEST_CHECKER_PATH),
        "--output-dir",
        str(manifest_dir),
        "--manifest-path",
        str(manifest_path),
    ]
    result = run_child(command, summary_path)
    result["artifacts"] = {
        "summary_json": str(summary_path),
        "checklist_csv": str(manifest_dir / "so101_model_bundle_manifest_checklist.csv"),
        "readme_md": str(manifest_dir / "README.md"),
    }
    summary = result.get("summary") or {}
    contract = summary.get("contract_checker") or {}
    asset_preflight = contract.get("model_asset_preflight") or {}
    result["diagnostic_excerpt"] = {
        "status": summary.get("status", result.get("status")),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "missing_inputs": summary.get("missing_inputs", []),
        "model_path": summary.get("model_path"),
        "asset_roots": summary.get("asset_roots"),
        "target_frame": summary.get("target_frame"),
        "tcp_offset": summary.get("tcp_offset"),
        "base_to_board_alignment": summary.get("base_to_board_alignment"),
        "contract_status": contract.get("status"),
        "asset_preflight_status": asset_preflight.get("status"),
        "asset_preflight_missing_asset_count": asset_preflight.get("missing_asset_count"),
        "asset_preflight_unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
        "artifacts": result["artifacts"],
    }
    return result


def build_model_request(model_path: Path | None) -> dict[str, Any]:
    if model_path is None:
        return {
            "status": "model_not_supplied",
            "path": None,
            "exists": False,
            "diagnostics": [
                {
                    "diagnostic": "candidate_model_path_missing",
                    "severity": "action_required",
                    "reason": "Supply --model-path to probe a concrete URDF/MJCF/Xacro/XML candidate.",
                }
            ],
        }
    exists = model_path.exists()
    return {
        "status": "model_supplied" if exists else "model_unavailable",
        "path": str(model_path),
        "exists": exists,
        "suffix": model_path.suffix.lower(),
        "diagnostics": []
        if exists
        else [
            {
                "diagnostic": "candidate_model_path_unavailable",
                "severity": "action_required",
                "reason": f"Model path does not exist: {model_path}",
            }
        ],
    }


def inspect_asset_roots(asset_roots: list[Path]) -> dict[str, Any]:
    checks = [
        {
            "path": str(root),
            "exists": root.exists(),
            "is_dir": root.is_dir(),
        }
        for root in asset_roots
    ]
    diagnostics: list[dict[str, Any]] = []
    for check in checks:
        if not check["exists"]:
            diagnostics.append(
                {
                    "diagnostic": "candidate_asset_root_unavailable",
                    "severity": "action_required",
                    "path": check["path"],
                }
            )
        elif not check["is_dir"]:
            diagnostics.append(
                {
                    "diagnostic": "candidate_asset_root_not_directory",
                    "severity": "action_required",
                    "path": check["path"],
                }
            )
    return {
        "asset_roots": [str(root) for root in asset_roots],
        "asset_root_count": len(asset_roots),
        "asset_root_checks": checks,
        "diagnostics": diagnostics,
        "notes": (
            "An explicit empty asset_roots list is allowed when the model directory alone resolves meshes. "
            "Non-empty roots are forwarded to the contract checker asset preflight."
        ),
    }


def build_authority(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    required = {
        "reviewed_by": args.authority_reviewed_by,
        "reviewed_at": args.authority_reviewed_at,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        return {}, {
            "status": "TODO_authority_review_required",
            "required_fields": sorted(required),
            "missing_fields": missing,
            "supplied_fields": {key: value for key, value in required.items() if value},
            "reason": "The probe never infers reviewed model authority from a path or asset root.",
        }
    return {
        "source_authority_status": "operator_supplied_reviewed",
        "reviewed_by": args.authority_reviewed_by,
        "reviewed_at": args.authority_reviewed_at,
    }, {
        "status": "operator_supplied",
        "required_fields": sorted(required),
        "missing_fields": [],
    }


def build_provenance(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    required = {
        "source_url": args.provenance_source_url,
        "export_tool": args.provenance_export_tool,
        "license": args.provenance_license,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        supplied = {key: value for key, value in required.items() if value}
        if args.provenance_source_commit:
            supplied["source_commit"] = args.provenance_source_commit
        return {}, {
            "status": "TODO_provenance_review_required",
            "required_fields": sorted(required),
            "optional_fields": ["source_commit"],
            "missing_fields": missing,
            "supplied_fields": supplied,
            "reason": "The probe records source provenance only when deterministic provenance inputs are supplied.",
        }
    provenance = {
        "source_url": args.provenance_source_url,
        "export_tool": args.provenance_export_tool,
        "license": args.provenance_license,
    }
    if args.provenance_source_commit:
        provenance["source_commit"] = args.provenance_source_commit
    return provenance, {
        "status": "operator_supplied",
        "required_fields": sorted(required),
        "optional_fields": ["source_commit"],
        "missing_fields": [],
    }


def build_candidate_manifest(
    *,
    model_request: dict[str, Any],
    asset_root_config: dict[str, Any],
    target_frame: str,
    authority: dict[str, Any],
    authority_placeholder: dict[str, Any],
    provenance: dict[str, Any],
    provenance_placeholder: dict[str, Any],
    contract_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": CANDIDATE_SCHEMA,
        "generated_by": "scripts/smoke_sim_so101_model_bundle_probe.py",
        "review_state": "draft_candidate_not_ready_for_model_backed_ik",
        "model_path": model_request["path"] or "",
        "model_path_placeholder": {
            "status": "TODO_model_path_required" if model_request["path"] is None else model_request["status"],
            "reason": "Set model_path to the reviewed SO-101 URDF/MJCF/Xacro/XML candidate.",
        },
        "asset_roots": asset_root_config["asset_roots"],
        "authority": authority,
        "authority_placeholder": authority_placeholder,
        "provenance": provenance,
        "provenance_placeholder": provenance_placeholder,
        "target_frame": target_frame,
        "joint_limits_placeholder": {
            "status": "TODO_reviewed_joint_limits_required",
            "accepted_manifest_fields": ["joint_limits_deg", "joint_limits", "joint_limit_authority"],
            "required_joints": [
                "shoulder_pan",
                "shoulder_lift",
                "elbow_flex",
                "wrist_flex",
                "wrist_roll",
                "gripper",
            ],
            "reason": "The probe cannot infer reviewed joint-limit authority from model existence alone.",
        },
        "tcp_offset_placeholder": {
            "status": "TODO_calibrated_target_frame_to_tcp_offset_required",
            "accepted_manifest_fields": [
                "tcp_offset_m",
                "gripper_tip_offset_m",
                "target_frame_to_tcp_m",
                "tool_center_point_offset_m",
            ],
            "required_shape": {"x": "meters", "y": "meters", "z": "meters"},
            "reason": "The probe cannot infer gripper contact TCP from the model alone.",
        },
        "base_to_board_alignment_placeholder": {
            "status": "TODO_calibrated_base_to_board_transform_required",
            "accepted_manifest_fields": ["base_to_board_transform", "base_to_board_alignment"],
            "reason": "Future model-backed IK residuals need the simulator base frame aligned to the chess board frame.",
        },
        "probe_child_diagnostics": {
            "model_request": model_request,
            "asset_roots": asset_root_config,
            "contract_checker": contract_result["diagnostic_excerpt"],
        },
        "notes": [
            "This candidate manifest is a review draft. It should stay diagnostic-only until authority, provenance, joint limits, TCP, and base-to-board fields are replaced with reviewed values.",
            "The probe does not copy, ingest, or modify model/mesh assets.",
            "Extra probe_child_diagnostics fields are for operator review; the bundle manifest checker derives readiness from the declared manifest fields.",
            "Populate joint_limits_deg or an equivalent joint-limit authority field before expecting ready_for_model_backed_ik.",
        ],
    }


def row(
    requirement_id: str,
    category: str,
    status: str,
    severity: str,
    observed_value: Any,
    expected_value: Any,
    missing_inputs: Any = None,
    diagnostics: Any = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "category": category,
        "status": status,
        "severity": severity,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "missing_inputs": missing_inputs,
        "diagnostics": diagnostics,
        "notes": notes,
    }


def build_rows(
    *,
    model_request: dict[str, Any],
    asset_root_config: dict[str, Any],
    authority: dict[str, Any],
    authority_placeholder: dict[str, Any],
    provenance: dict[str, Any],
    provenance_placeholder: dict[str, Any],
    contract_result: dict[str, Any],
    manifest_result: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    missing_inputs = manifest_excerpt.get("missing_inputs") or []
    contract_excerpt = contract_result["diagnostic_excerpt"]
    asset_preflight = contract_excerpt.get("model_asset_preflight") or {}
    return [
        row(
            "candidate_model_path",
            "model_path",
            "ok" if model_request["status"] == "model_supplied" else "action_required",
            "warning",
            model_request,
            {"exists": True},
            None if model_request["status"] == "model_supplied" else ["--model-path"],
            model_request.get("diagnostics", []),
            "Missing or unavailable model paths are diagnostic-only and still produce a manifest draft.",
        ),
        row(
            "candidate_asset_roots",
            "mesh_assets",
            "ok" if not asset_root_config["diagnostics"] else "action_required",
            "warning",
            asset_root_config,
            {"all_supplied_roots_exist": True, "all_supplied_roots_are_directories": True},
            None if not asset_root_config["diagnostics"] else ["--asset-root"],
            asset_root_config["diagnostics"],
            "Repeat --asset-root for separate mesh directories; an empty list is explicit and valid.",
        ),
        row(
            "authority",
            "authority",
            "ok" if authority else "action_required",
            "warning",
            authority or authority_placeholder,
            {"authority": "non-empty reviewed authority object"},
            None if authority else ["authority"],
            [] if authority else [authority_placeholder],
            "Defaults to an empty authority object so placeholders are not treated as reviewed authority.",
        ),
        row(
            "provenance",
            "provenance",
            "ok" if provenance else "action_required",
            "warning",
            provenance or provenance_placeholder,
            {"provenance": "non-empty reviewed provenance object"},
            None if provenance else ["provenance"],
            [] if provenance else [provenance_placeholder],
            "Defaults to an empty provenance object so placeholders are not treated as reviewed provenance.",
        ),
        row(
            "tcp_offset_m",
            "tcp_frame",
            "action_required",
            "warning",
            {"tcp_offset_placeholder": True},
            {"x": "meters", "y": "meters", "z": "meters"},
            ["tcp_offset_m"],
            ["tcp_offset_placeholder_declared_without_calibrated_vector"],
            "The probe intentionally does not invent TCP/gripper-tip offsets.",
        ),
        row(
            "joint_limits_deg",
            "joint_contract",
            "action_required",
            "warning",
            {"joint_limits_placeholder": True},
            {"required_joints": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]},
            ["joint_limits_deg"],
            ["joint_limits_placeholder_declared_without_reviewed_limits"],
            "The probe intentionally does not invent reviewed joint-limit authority.",
        ),
        row(
            "base_to_board_transform",
            "alignment",
            "action_required",
            "warning",
            {"base_to_board_alignment_placeholder": True},
            {"calibrated_base_to_board_transform": True},
            ["base_to_board_transform"],
            ["alignment_placeholder_declared_without_transform"],
            "The generated placeholder keeps model-backed IK disabled until calibration is reviewed.",
        ),
        row(
            "child_contract_checker",
            "child_diagnostics",
            "ok"
            if contract_excerpt.get("status")
            in {"model_contract_checked", "model_contract_needs_follow_up"}
            and asset_preflight.get("missing_asset_count") in {0, None}
            and asset_preflight.get("unresolved_reference_count") in {0, None}
            else "action_required",
            "warning",
            contract_excerpt,
            {"missing_asset_count": 0, "unresolved_reference_count": 0},
            None
            if contract_excerpt.get("status") in {"model_contract_checked", "model_contract_needs_follow_up"}
            else ["non_blocking_contract_checker_result"],
            contract_result.get("diagnostics", []),
            "This reuses the existing SO-101 model contract checker and nested asset preflight.",
        ),
        row(
            "bundle_manifest_checker",
            "readiness",
            "ok" if manifest_excerpt.get("ready_for_model_backed_ik") else "action_required",
            "warning",
            manifest_excerpt,
            {"ready_for_model_backed_ik": True},
            None if manifest_excerpt.get("ready_for_model_backed_ik") else missing_inputs,
            [] if manifest_excerpt.get("ready_for_model_backed_ik") else ["candidate_manifest_not_ready"],
            "This is the same readiness gate used by the integrated simulator regression suite.",
        ),
    ]


def status_for(model_request: dict[str, Any], manifest_result: dict[str, Any]) -> str:
    if model_request["status"] == "model_not_supplied":
        return "candidate_model_missing"
    if model_request["status"] == "model_unavailable":
        return "candidate_model_unavailable"
    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    if manifest_excerpt.get("ready_for_model_backed_ik"):
        return "candidate_manifest_ready_for_model_backed_ik"
    return "candidate_manifest_needs_review"


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    contract = summary["contract_checker"]["diagnostic_excerpt"]
    manifest = summary["manifest_checker"]["diagnostic_excerpt"]
    asset_preflight = contract.get("model_asset_preflight") or {}
    lines = [
        "# SO-101 Model Bundle Probe",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `candidate_manifest`: `{summary['artifacts']['candidate_manifest_json']}`",
        f"- `model_path`: `{summary['model_request']['path']}`",
        f"- `asset_roots`: `{'; '.join(summary['asset_roots']['asset_roots']) if summary['asset_roots']['asset_roots'] else 'none'}`",
        f"- `target_frame`: `{summary['target_frame']}`",
        f"- `contract_status`: `{contract.get('status')}`",
        f"- `asset_preflight_status`: `{asset_preflight.get('status')}`",
        f"- `asset_preflight_missing_asset_count`: `{asset_preflight.get('missing_asset_count')}`",
        f"- `asset_preflight_unresolved_reference_count`: `{asset_preflight.get('unresolved_reference_count')}`",
        f"- `manifest_status`: `{manifest.get('status')}`",
        f"- `ready_for_model_backed_ik`: `{str(manifest.get('ready_for_model_backed_ik')).lower()}`",
        f"- `manifest_missing_inputs`: `{', '.join(manifest.get('missing_inputs') or []) if manifest.get('missing_inputs') else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `checklist_csv`: `{summary['artifacts']['checklist_csv']}`",
        "",
        "## Checklist",
        "",
        "| Requirement | Status | Notes |",
        "| --- | --- | --- |",
    ]
    for checklist_row in rows:
        notes = checklist_row["notes"] or checklist_row["diagnostics"] or checklist_row["observed_value"] or ""
        lines.append(
            "| `{requirement}` | `{status}` | {notes} |".format(
                requirement=checklist_row["requirement_id"],
                status=checklist_row["status"],
                notes=str(notes).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Next Inputs",
            "",
            "- Replace empty `authority` and `provenance` placeholders with reviewed source fields.",
            "- Replace `tcp_offset_placeholder` with one accepted calibrated TCP/gripper-tip offset field.",
            "- Replace `base_to_board_alignment_placeholder` with a real base-to-board transform/alignment.",
            "- Re-run `scripts/smoke_sim_so101_model_bundle_manifest.py` on the candidate manifest before enabling model-backed IK.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = normalize_path(args.model_path) if args.model_path is not None else None
    asset_roots = unique_paths(list(args.asset_root))
    model_request = build_model_request(model_path)
    asset_root_config = inspect_asset_roots(asset_roots)
    authority, authority_placeholder = build_authority(args)
    provenance, provenance_placeholder = build_provenance(args)

    contract_result = run_contract_checker(
        args.python,
        output_dir,
        model_path,
        asset_roots,
        str(args.target_frame),
    )

    candidate_manifest_path = output_dir / "so101_model_bundle.candidate.json"
    candidate_manifest = build_candidate_manifest(
        model_request=model_request,
        asset_root_config=asset_root_config,
        target_frame=str(args.target_frame),
        authority=authority,
        authority_placeholder=authority_placeholder,
        provenance=provenance,
        provenance_placeholder=provenance_placeholder,
        contract_result=contract_result,
    )
    write_json(candidate_manifest_path, candidate_manifest)

    manifest_result = run_manifest_checker(args.python, output_dir, candidate_manifest_path)
    rows = build_rows(
        model_request=model_request,
        asset_root_config=asset_root_config,
        authority=authority,
        authority_placeholder=authority_placeholder,
        provenance=provenance,
        provenance_placeholder=provenance_placeholder,
        contract_result=contract_result,
        manifest_result=manifest_result,
    )

    summary_path = output_dir / "so101_model_bundle_probe_summary.json"
    csv_path = output_dir / "so101_model_bundle_probe_checklist.csv"
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(csv_path),
        "readme_md": str(readme_path),
        "candidate_manifest_json": str(candidate_manifest_path),
        "contract_summary_json": contract_result["artifacts"]["summary_json"],
        "contract_checklist_csv": contract_result["artifacts"]["checklist_csv"],
        "manifest_check_summary_json": manifest_result["artifacts"]["summary_json"],
        "manifest_checklist_csv": manifest_result["artifacts"]["checklist_csv"],
    }
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status_for(model_request, manifest_result),
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "target_frame": str(args.target_frame),
        "model_request": model_request,
        "asset_roots": asset_root_config,
        "authority": {
            "value": authority,
            "placeholder": authority_placeholder,
        },
        "provenance": {
            "value": provenance,
            "placeholder": provenance_placeholder,
        },
        "candidate_manifest": candidate_manifest,
        "contract_checker": {
            "status": contract_result.get("status"),
            "ok": contract_result.get("ok"),
            "returncode": contract_result.get("returncode"),
            "diagnostic_excerpt": contract_result["diagnostic_excerpt"],
            "artifacts": contract_result["artifacts"],
            "command": contract_result.get("command"),
        },
        "manifest_checker": {
            "status": manifest_result.get("status"),
            "ok": manifest_result.get("ok"),
            "returncode": manifest_result.get("returncode"),
            "diagnostic_excerpt": manifest_result["diagnostic_excerpt"],
            "artifacts": manifest_result["artifacts"],
            "command": manifest_result.get("command"),
        },
        "checklist": rows,
        "artifacts": artifacts,
        "limitations": [
            "This probe is hardware-free and never opens robot motors, serial ports, cameras, GUI flows, OpenAI calls, or network resources.",
            "The generated candidate manifest is a draft and does not copy, ingest, or modify model/mesh assets.",
            "Authority, provenance, TCP, and base-to-board placeholders are not treated as readiness fields by default.",
            "Future model-backed IK residuals remain diagnostic-only until the bundle manifest checker reports ready_for_model_backed_ik true.",
        ],
    }

    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    write_markdown(readme_path, summary, rows)

    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "candidate_manifest_json": str(candidate_manifest_path),
                "summary_json": str(summary_path),
                "checklist_csv": str(csv_path),
                "readme_md": str(readme_path),
                "model_request_status": model_request["status"],
                "contract_status": contract_result["diagnostic_excerpt"].get("status"),
                "asset_preflight_status": (
                    contract_result["diagnostic_excerpt"].get("model_asset_preflight") or {}
                ).get("status"),
                "manifest_status": manifest_excerpt.get("status"),
                "ready_for_model_backed_ik": manifest_excerpt.get("ready_for_model_backed_ik"),
                "missing_inputs": manifest_excerpt.get("missing_inputs", []),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
