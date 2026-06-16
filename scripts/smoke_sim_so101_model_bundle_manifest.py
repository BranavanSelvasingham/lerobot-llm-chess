#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "lerobot.sim.so101_model_bundle_manifest.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_bundle_manifest"
REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_contract.py"
EXPECTED_TARGET_FRAME = "gripper_frame_link"
TCP_OFFSET_FIELDS = (
    "tcp_offset_m",
    "gripper_tip_offset_m",
    "target_frame_to_tcp_m",
    "tool_center_point_offset_m",
)
ALIGNMENT_FIELDS = (
    "base_to_board_transform",
    "base_to_board_alignment",
)
ALIGNMENT_PLACEHOLDER_FIELDS = (
    "base_to_board_alignment_placeholder",
    "alignment_placeholders",
)
REQUIRED_INPUTS = (
    {
        "input": "manifest_path",
        "requirement": "JSON manifest path supplied through --manifest-path.",
    },
    {
        "input": "model_path",
        "requirement": "SO-101 kinematic model path, absolute or relative to the manifest directory.",
    },
    {
        "input": "asset_roots",
        "requirement": "Explicit mesh/asset root list, even when empty because the model directory is sufficient.",
    },
    {
        "input": "authority",
        "requirement": "Reviewed source-authority fields for the model bundle.",
    },
    {
        "input": "provenance",
        "requirement": "Model provenance fields such as source URL/commit/export tool/license basis.",
    },
    {
        "input": "target_frame",
        "requirement": f"Target frame name; defaults to {EXPECTED_TARGET_FRAME!r} when omitted.",
    },
    {
        "input": "tcp_offset_m",
        "requirement": "Calibrated target-frame to TCP/gripper-tip offset as x/y/z meters.",
    },
    {
        "input": "base_to_board_transform",
        "requirement": "Calibrated base-to-board transform, not only a placeholder.",
    },
    {
        "input": "contract_checker_result",
        "requirement": "Non-blocking SO-101 model contract checker and nested mesh asset preflight diagnostics.",
    },
)
CSV_FIELDNAMES = (
    "requirement_id",
    "category",
    "status",
    "severity",
    "source",
    "observed_value",
    "expected_value",
    "missing_inputs",
    "diagnostics",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a hardware-free SO-101 model bundle manifest before model-backed IK "
            "calibration treats Cartesian/delta/radial reachability residuals as trustworthy."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="JSON manifest describing the SO-101 model bundle. Missing manifests are diagnostic-only.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child model contract/preflight tooling.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def resolve_manifest_relative(value: str, manifest_dir: Path | None) -> Path:
    raw_path = Path(value).expanduser()
    if raw_path.is_absolute() or manifest_dir is None:
        return normalize_path(raw_path)
    return normalize_path(manifest_dir / raw_path)


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


def row(
    requirement_id: str,
    category: str,
    status: str,
    severity: str,
    source: str,
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
        "source": source,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "missing_inputs": missing_inputs,
        "diagnostics": diagnostics,
        "notes": notes,
    }


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def load_manifest(manifest_path: Path | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if manifest_path is None:
        return None, {
            "status": "model_bundle_manifest_not_supplied",
            "path": None,
            "exists": False,
            "diagnostics": [
                {
                    "diagnostic": "manifest_not_supplied",
                    "severity": "action_required",
                    "reason": "No --manifest-path was supplied.",
                }
            ],
        }

    resolved = normalize_path(manifest_path)
    if not resolved.exists():
        return None, {
            "status": "model_bundle_manifest_unavailable",
            "path": str(resolved),
            "exists": False,
            "diagnostics": [
                {
                    "diagnostic": "manifest_unavailable",
                    "severity": "action_required",
                    "reason": f"Manifest path does not exist: {resolved}",
                }
            ],
        }

    try:
        payload = json.loads(resolved.read_text())
    except Exception as exc:
        return None, {
            "status": "model_bundle_manifest_parse_error",
            "path": str(resolved),
            "exists": True,
            "diagnostics": [
                {
                    "diagnostic": "manifest_parse_error",
                    "severity": "action_required",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            ],
        }

    if not isinstance(payload, dict):
        return None, {
            "status": "model_bundle_manifest_schema_error",
            "path": str(resolved),
            "exists": True,
            "diagnostics": [
                {
                    "diagnostic": "manifest_not_json_object",
                    "severity": "action_required",
                    "reason": "The manifest root must be a JSON object.",
                }
            ],
        }

    return payload, {
        "status": "model_bundle_manifest_loaded",
        "path": str(resolved),
        "exists": True,
        "diagnostics": [],
    }


def vector3_status(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        missing = [axis for axis in ("x", "y", "z") if axis not in value]
        if missing:
            return {
                "present": True,
                "valid": False,
                "value": value,
                "diagnostics": [f"missing_axis:{axis}" for axis in missing],
            }
        try:
            vector = {axis: float(value[axis]) for axis in ("x", "y", "z")}
        except (TypeError, ValueError) as exc:
            return {
                "present": True,
                "valid": False,
                "value": value,
                "diagnostics": [f"non_numeric_axis:{type(exc).__name__}"],
            }
        return {"present": True, "valid": True, "value": vector, "diagnostics": []}

    if isinstance(value, list) and len(value) == 3:
        try:
            vector = [float(item) for item in value]
        except (TypeError, ValueError) as exc:
            return {
                "present": True,
                "valid": False,
                "value": value,
                "diagnostics": [f"non_numeric_vector:{type(exc).__name__}"],
            }
        return {"present": True, "valid": True, "value": vector, "diagnostics": []}

    return {
        "present": value is not None,
        "valid": False,
        "value": value,
        "diagnostics": ["expected_x_y_z_object_or_len3_list"],
    }


def find_first_field(manifest: dict[str, Any], field_names: tuple[str, ...]) -> tuple[str | None, Any]:
    for field_name in field_names:
        if field_name in manifest:
            return field_name, manifest[field_name]
    return None, None


def inspect_model_path(manifest: dict[str, Any] | None, manifest_dir: Path | None) -> dict[str, Any]:
    if not manifest or not non_empty(manifest.get("model_path")):
        return {
            "status": "missing",
            "raw": None,
            "path": None,
            "exists": False,
            "diagnostics": ["model_path_missing"],
        }

    raw = str(manifest["model_path"])
    resolved = resolve_manifest_relative(raw, manifest_dir)
    return {
        "status": "present" if resolved.exists() else "unavailable",
        "raw": raw,
        "path": str(resolved),
        "exists": resolved.exists(),
        "suffix": resolved.suffix.lower(),
        "diagnostics": [] if resolved.exists() else ["model_path_unavailable"],
    }


def inspect_asset_roots(manifest: dict[str, Any] | None, manifest_dir: Path | None) -> dict[str, Any]:
    if not manifest or "asset_roots" not in manifest:
        return {
            "status": "missing",
            "present": False,
            "asset_roots": [],
            "asset_root_checks": [],
            "diagnostics": ["asset_roots_missing"],
        }

    raw_roots = manifest.get("asset_roots")
    if not isinstance(raw_roots, list):
        return {
            "status": "invalid",
            "present": True,
            "asset_roots": [],
            "asset_root_checks": [],
            "diagnostics": ["asset_roots_not_list"],
        }

    seen: set[str] = set()
    roots: list[Path] = []
    diagnostics: list[str] = []
    for index, raw_root in enumerate(raw_roots):
        if not isinstance(raw_root, str) or not raw_root.strip():
            diagnostics.append(f"asset_root_{index}_not_string")
            continue
        resolved = resolve_manifest_relative(raw_root, manifest_dir)
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)

    checks = [
        {
            "path": str(root),
            "exists": root.exists(),
            "is_dir": root.is_dir(),
        }
        for root in roots
    ]
    for check in checks:
        if not check["exists"]:
            diagnostics.append(f"asset_root_unavailable:{check['path']}")
        elif not check["is_dir"]:
            diagnostics.append(f"asset_root_not_directory:{check['path']}")

    if diagnostics:
        status = "needs_follow_up"
    else:
        status = "present"
    return {
        "status": status,
        "present": True,
        "asset_roots": [str(root) for root in roots],
        "asset_root_checks": checks,
        "diagnostics": diagnostics,
        "notes": (
            "An explicit empty asset_roots list is valid when the model directory alone resolves meshes; "
            "non-empty roots are forwarded to the contract checker as --model-asset-root."
        ),
    }


def inspect_authority(manifest: dict[str, Any] | None) -> dict[str, Any]:
    value = manifest.get("authority") if manifest else None
    if isinstance(value, dict) and value:
        return {"status": "present", "value": value, "diagnostics": []}
    return {
        "status": "missing",
        "value": value,
        "diagnostics": ["authority_missing_or_empty"],
    }


def inspect_provenance(manifest: dict[str, Any] | None) -> dict[str, Any]:
    value = manifest.get("provenance") if manifest else None
    if isinstance(value, dict) and value:
        return {"status": "present", "value": value, "diagnostics": []}
    return {
        "status": "missing",
        "value": value,
        "diagnostics": ["provenance_missing_or_empty"],
    }


def inspect_target_frame(manifest: dict[str, Any] | None) -> dict[str, Any]:
    raw = manifest.get("target_frame") if manifest else None
    if raw is None:
        return {
            "status": "defaulted",
            "value": EXPECTED_TARGET_FRAME,
            "diagnostics": [],
            "notes": f"target_frame omitted; defaulted to {EXPECTED_TARGET_FRAME}.",
        }
    if isinstance(raw, str) and raw.strip():
        diagnostics = [] if raw == EXPECTED_TARGET_FRAME else ["target_frame_differs_from_default"]
        return {"status": "present", "value": raw, "diagnostics": diagnostics}
    return {
        "status": "invalid",
        "value": raw,
        "diagnostics": ["target_frame_not_nonempty_string"],
    }


def inspect_tcp_offset(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "diagnostics": ["tcp_offset_missing"],
        }
    field_name, value = find_first_field(manifest, TCP_OFFSET_FIELDS)
    if field_name is None:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "diagnostics": ["tcp_offset_missing"],
        }
    vector = vector3_status(value)
    return {
        "status": "present" if vector["valid"] else "invalid",
        "field": field_name,
        "value": vector["value"],
        "diagnostics": vector["diagnostics"],
    }


def inspect_alignment(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "placeholder_field": None,
            "placeholder_value": None,
            "diagnostics": ["base_to_board_transform_missing"],
        }

    field_name, value = find_first_field(manifest, ALIGNMENT_FIELDS)
    if field_name is not None and non_empty(value):
        return {
            "status": "present",
            "field": field_name,
            "value": value,
            "placeholder_field": None,
            "placeholder_value": None,
            "diagnostics": [],
        }

    placeholder_field, placeholder_value = find_first_field(manifest, ALIGNMENT_PLACEHOLDER_FIELDS)
    if placeholder_field is not None and non_empty(placeholder_value):
        return {
            "status": "placeholder_only",
            "field": None,
            "value": None,
            "placeholder_field": placeholder_field,
            "placeholder_value": placeholder_value,
            "diagnostics": ["alignment_placeholder_declared_without_transform"],
        }

    return {
        "status": "missing",
        "field": None,
        "value": value,
        "placeholder_field": placeholder_field,
        "placeholder_value": placeholder_value,
        "diagnostics": ["base_to_board_transform_missing"],
    }


def run_contract_checker(
    python_path: Path,
    output_dir: Path,
    model_path: dict[str, Any],
    asset_roots: dict[str, Any],
    target_frame: dict[str, Any],
) -> dict[str, Any]:
    contract_dir = output_dir / "so101_model_contract"
    summary_path = contract_dir / "so101_model_contract_summary.json"
    csv_path = contract_dir / "so101_model_contract_checklist.csv"
    readme_path = contract_dir / "README.md"

    if model_path["path"] is None:
        return {
            "status": "not_attempted",
            "ok": False,
            "reason": "No model_path was available in the manifest.",
            "artifacts": {
                "summary_json": str(summary_path),
                "checklist_csv": str(csv_path),
                "readme_md": str(readme_path),
            },
        }

    command = [
        str(normalize_path(python_path)),
        str(CONTRACT_CHECKER_PATH),
        "--output-dir",
        str(contract_dir),
        "--model-path",
        str(model_path["path"]),
        "--target-frame",
        str(target_frame["value"]),
    ]
    for asset_root in asset_roots["asset_roots"]:
        command.extend(["--model-asset-root", asset_root])

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    base = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "artifacts": {
            "summary_json": str(summary_path),
            "checklist_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
    }

    if result.returncode != 0:
        return {
            **base,
            "status": "contract_checker_failed",
            "ok": False,
            "reason": "Child SO-101 model contract checker returned nonzero.",
            "diagnostics": [
                {
                    "diagnostic": "contract_checker_nonzero",
                    "severity": "action_required",
                    "returncode": result.returncode,
                }
            ],
        }

    try:
        child_summary = json.loads(summary_path.read_text())
    except Exception as exc:
        return {
            **base,
            "status": "contract_checker_summary_unavailable",
            "ok": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "diagnostics": [
                {
                    "diagnostic": "contract_checker_summary_unavailable",
                    "severity": "action_required",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            ],
        }

    asset_preflight = child_summary.get("model_asset_preflight") or {}
    return {
        **base,
        "status": child_summary.get("status"),
        "ok": bool(child_summary.get("ok")),
        "model_request_status": child_summary.get("model_request", {}).get("status"),
        "robot_kinematics_status": child_summary.get("robot_kinematics_path", {}).get("status"),
        "robot_kinematics_initialization_status": child_summary.get("robot_kinematics_initialization", {}).get("status"),
        "model_asset_preflight": {
            "status": asset_preflight.get("status"),
            "asset_roots": asset_preflight.get("asset_roots"),
            "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
            "present_asset_count": asset_preflight.get("present_asset_count"),
            "missing_asset_count": asset_preflight.get("missing_asset_count"),
            "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
            "artifacts": asset_preflight.get("artifacts"),
            "diagnostics": asset_preflight.get("diagnostics", []),
            "limitations": asset_preflight.get("limitations", []),
        },
        "child_diagnostics": {
            "model_structure_inspection": child_summary.get("model_structure_inspection"),
            "model_to_sim_alignment_inputs_missing": child_summary.get("model_to_sim_alignment_inputs_missing"),
            "tcp_or_gripper_tip_sources": child_summary.get("tcp_or_gripper_tip_sources"),
        },
    }


def contract_non_blocking(contract: dict[str, Any]) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []
    if contract.get("status") != "model_contract_checked":
        diagnostics.append(f"contract_status:{contract.get('status')}")
    if contract.get("model_request_status") != "model_supplied":
        diagnostics.append(f"model_request_status:{contract.get('model_request_status')}")

    asset_preflight = contract.get("model_asset_preflight") or {}
    if asset_preflight.get("status") not in {"asset_preflight_checked", "asset_preflight_limited_diagnostics"}:
        diagnostics.append(f"asset_preflight_status:{asset_preflight.get('status')}")
    if asset_preflight.get("missing_asset_count") not in {0, None}:
        diagnostics.append(f"missing_asset_count:{asset_preflight.get('missing_asset_count')}")
    if asset_preflight.get("unresolved_reference_count") not in {0, None}:
        diagnostics.append(f"unresolved_reference_count:{asset_preflight.get('unresolved_reference_count')}")

    return not diagnostics, diagnostics


def build_field_checks(
    manifest_request: dict[str, Any],
    model_path: dict[str, Any],
    asset_roots: dict[str, Any],
    authority: dict[str, Any],
    provenance: dict[str, Any],
    target_frame: dict[str, Any],
    tcp_offset: dict[str, Any],
    alignment: dict[str, Any],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    contract_ok, contract_diagnostics = contract_non_blocking(contract)
    return [
        {
            "requirement_id": "manifest_path",
            "ok": manifest_request["status"] == "model_bundle_manifest_loaded",
            "missing_inputs": None
            if manifest_request["status"] == "model_bundle_manifest_loaded"
            else ["--manifest-path"],
            "diagnostics": manifest_request.get("diagnostics", []),
        },
        {
            "requirement_id": "model_path",
            "ok": model_path["status"] == "present",
            "missing_inputs": None if model_path["status"] == "present" else ["model_path"],
            "diagnostics": model_path.get("diagnostics", []),
        },
        {
            "requirement_id": "asset_roots",
            "ok": asset_roots["status"] == "present",
            "missing_inputs": None if asset_roots["status"] == "present" else ["asset_roots"],
            "diagnostics": asset_roots.get("diagnostics", []),
        },
        {
            "requirement_id": "authority",
            "ok": authority["status"] == "present",
            "missing_inputs": None if authority["status"] == "present" else ["authority"],
            "diagnostics": authority.get("diagnostics", []),
        },
        {
            "requirement_id": "provenance",
            "ok": provenance["status"] == "present",
            "missing_inputs": None if provenance["status"] == "present" else ["provenance"],
            "diagnostics": provenance.get("diagnostics", []),
        },
        {
            "requirement_id": "target_frame",
            "ok": target_frame["status"] in {"present", "defaulted"},
            "missing_inputs": None if target_frame["status"] in {"present", "defaulted"} else ["target_frame"],
            "diagnostics": target_frame.get("diagnostics", []),
        },
        {
            "requirement_id": "tcp_offset_m",
            "ok": tcp_offset["status"] == "present",
            "missing_inputs": None if tcp_offset["status"] == "present" else ["tcp_offset_m"],
            "diagnostics": tcp_offset.get("diagnostics", []),
        },
        {
            "requirement_id": "base_to_board_transform",
            "ok": alignment["status"] == "present",
            "missing_inputs": None
            if alignment["status"] == "present"
            else ["base_to_board_transform"],
            "diagnostics": alignment.get("diagnostics", []),
        },
        {
            "requirement_id": "contract_checker_result",
            "ok": contract_ok,
            "missing_inputs": None if contract_ok else ["non_blocking_contract_checker_result"],
            "diagnostics": contract_diagnostics,
        },
    ]


def build_checklist_rows(
    manifest_request: dict[str, Any],
    model_path: dict[str, Any],
    asset_roots: dict[str, Any],
    authority: dict[str, Any],
    provenance: dict[str, Any],
    target_frame: dict[str, Any],
    tcp_offset: dict[str, Any],
    alignment: dict[str, Any],
    contract: dict[str, Any],
    ready: bool,
    missing_inputs: list[str],
) -> list[dict[str, Any]]:
    contract_ok, contract_diagnostics = contract_non_blocking(contract)
    return [
        row(
            "manifest_path",
            "manifest",
            "ok" if manifest_request["status"] == "model_bundle_manifest_loaded" else "action_required",
            "info",
            "cli",
            manifest_request,
            {"format": "json_object"},
            None if manifest_request["status"] == "model_bundle_manifest_loaded" else ["--manifest-path"],
            manifest_request.get("diagnostics", []),
            "Manifest absence/unavailability is diagnostic-only and exits 0.",
        ),
        row(
            "model_path",
            "kinematic_model",
            "ok" if model_path["status"] == "present" else "action_required",
            "warning",
            "manifest.model_path",
            model_path,
            {"exists": True},
            None if model_path["status"] == "present" else ["model_path"],
            model_path.get("diagnostics", []),
            "Relative model paths resolve from the manifest directory.",
        ),
        row(
            "asset_roots",
            "mesh_assets",
            "ok" if asset_roots["status"] == "present" else "action_required",
            "warning",
            "manifest.asset_roots",
            asset_roots,
            {"type": "list", "all_supplied_roots_exist": True},
            None if asset_roots["status"] == "present" else ["asset_roots"],
            asset_roots.get("diagnostics", []),
            "Forwarded to the model contract checker as repeatable --model-asset-root values.",
        ),
        row(
            "authority",
            "authority",
            "ok" if authority["status"] == "present" else "action_required",
            "warning",
            "manifest.authority",
            authority["value"],
            {"non_empty_json_object": True},
            None if authority["status"] == "present" else ["authority"],
            authority.get("diagnostics", []),
            "Authority is declared by the manifest; this checker does not infer it from --ik-model-path.",
        ),
        row(
            "provenance",
            "provenance",
            "ok" if provenance["status"] == "present" else "action_required",
            "warning",
            "manifest.provenance",
            provenance["value"],
            {"non_empty_json_object": True},
            None if provenance["status"] == "present" else ["provenance"],
            provenance.get("diagnostics", []),
            "Record source URL/commit/export/license context before trusting the bundle.",
        ),
        row(
            "target_frame",
            "tcp_frame",
            "ok" if target_frame["status"] in {"present", "defaulted"} else "action_required",
            "info",
            "manifest.target_frame",
            target_frame,
            EXPECTED_TARGET_FRAME,
            None if target_frame["status"] in {"present", "defaulted"} else ["target_frame"],
            target_frame.get("diagnostics", []),
            "Omitted target_frame defaults to gripper_frame_link.",
        ),
        row(
            "tcp_offset_m",
            "tcp_frame",
            "ok" if tcp_offset["status"] == "present" else "action_required",
            "warning",
            f"manifest.{'|'.join(TCP_OFFSET_FIELDS)}",
            tcp_offset,
            {"x": "meters", "y": "meters", "z": "meters"},
            None if tcp_offset["status"] == "present" else ["tcp_offset_m"],
            tcp_offset.get("diagnostics", []),
            "Accepted aliases are tcp_offset_m, gripper_tip_offset_m, target_frame_to_tcp_m, and tool_center_point_offset_m.",
        ),
        row(
            "base_to_board_transform",
            "alignment",
            "ok" if alignment["status"] == "present" else "action_required",
            "warning",
            f"manifest.{'|'.join(ALIGNMENT_FIELDS + ALIGNMENT_PLACEHOLDER_FIELDS)}",
            alignment,
            {"calibrated_transform": True},
            None if alignment["status"] == "present" else ["base_to_board_transform"],
            alignment.get("diagnostics", []),
            "Explicit placeholders are recorded but do not make the bundle ready for model-backed IK.",
        ),
        row(
            "contract_checker_result",
            "child_diagnostics",
            "ok" if contract_ok else "action_required",
            "warning",
            str(CONTRACT_CHECKER_PATH),
            contract,
            {"status": "model_contract_checked", "missing_asset_count": 0, "unresolved_reference_count": 0},
            None if contract_ok else ["non_blocking_contract_checker_result"],
            contract_diagnostics,
            "The child contract checker also runs the mesh asset preflight.",
        ),
        row(
            "model_backed_ik_readiness",
            "readiness",
            "ok" if ready else "action_required",
            "warning",
            "bundle_manifest_checker",
            {"ready_for_model_backed_ik": ready},
            {"ready_for_model_backed_ik": True},
            None if ready else missing_inputs,
            [] if ready else ["bundle_not_ready_for_model_backed_ik"],
            "Do not trust Cartesian/delta/radial residuals unless this row is ok.",
        ),
    ]


def status_for(
    manifest_request: dict[str, Any],
    ready: bool,
) -> str:
    if manifest_request["status"] != "model_bundle_manifest_loaded":
        return manifest_request["status"]
    if ready:
        return "model_bundle_manifest_ready_for_model_backed_ik"
    return "model_bundle_manifest_needs_follow_up"


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    contract = summary["contract_checker"]
    asset_preflight = contract.get("model_asset_preflight") or {}
    lines = [
        "# SO-101 Model Bundle Manifest Check",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `ready_for_model_backed_ik`: `{str(summary['ready_for_model_backed_ik']).lower()}`",
        f"- `manifest_path`: `{summary['manifest_request']['path']}`",
        f"- `model_path`: `{summary['model_path']['path']}`",
        f"- `asset_roots`: `{'; '.join(summary['asset_roots']['asset_roots']) if summary['asset_roots']['asset_roots'] else 'none'}`",
        f"- `target_frame`: `{summary['target_frame']['value']}`",
        f"- `tcp_offset_field`: `{summary['tcp_offset']['field']}`",
        f"- `alignment_status`: `{summary['base_to_board_alignment']['status']}`",
        f"- `contract_status`: `{contract.get('status')}`",
        f"- `asset_preflight_status`: `{asset_preflight.get('status')}`",
        f"- `asset_preflight_missing_asset_count`: `{asset_preflight.get('missing_asset_count')}`",
        f"- `asset_preflight_unresolved_reference_count`: `{asset_preflight.get('unresolved_reference_count')}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `checklist_csv`: `{summary['artifacts']['checklist_csv']}`",
        f"- `contract_summary_json`: `{contract.get('artifacts', {}).get('summary_json')}`",
        "",
        "## Missing Inputs",
        "",
    ]
    if summary["missing_inputs"]:
        for missing_input in summary["missing_inputs"]:
            lines.append(f"- `{missing_input}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Checklist",
            "",
            "| Requirement | Status | Notes |",
            "| --- | --- | --- |",
        ]
    )
    for checklist_row in rows:
        notes = checklist_row["notes"] or checklist_row["diagnostics"] or checklist_row["observed_value"] or ""
        lines.append(
            "| `{requirement}` | `{status}` | {notes} |".format(
                requirement=checklist_row["requirement_id"],
                status=checklist_row["status"],
                notes=str(notes).replace("|", "/"),
            )
        )
    path.write_text("\n".join(lines) + "\n")


def build_summary(
    manifest: dict[str, Any] | None,
    manifest_request: dict[str, Any],
    python_path: Path,
    output_dir: Path,
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_dir = Path(manifest_request["path"]).parent if manifest_request.get("path") else None
    model_path = inspect_model_path(manifest, manifest_dir)
    asset_roots = inspect_asset_roots(manifest, manifest_dir)
    authority = inspect_authority(manifest)
    provenance = inspect_provenance(manifest)
    target_frame = inspect_target_frame(manifest)
    tcp_offset = inspect_tcp_offset(manifest)
    alignment = inspect_alignment(manifest)
    contract = run_contract_checker(python_path, output_dir, model_path, asset_roots, target_frame)
    field_checks = build_field_checks(
        manifest_request,
        model_path,
        asset_roots,
        authority,
        provenance,
        target_frame,
        tcp_offset,
        alignment,
        contract,
    )
    missing_inputs = [
        missing_input
        for check in field_checks
        if not check["ok"]
        for missing_input in (check["missing_inputs"] or [])
    ]
    ready = not missing_inputs
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status_for(manifest_request, ready),
        "ready_for_model_backed_ik": ready,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "required_inputs": list(REQUIRED_INPUTS),
        "manifest_request": manifest_request,
        "manifest": manifest,
        "model_path": model_path,
        "asset_roots": asset_roots,
        "authority": authority,
        "provenance": provenance,
        "target_frame": target_frame,
        "tcp_offset": tcp_offset,
        "base_to_board_alignment": alignment,
        "contract_checker": contract,
        "field_checks": field_checks,
        "missing_inputs": sorted(set(missing_inputs)),
        "artifacts": artifacts,
        "limitations": [
            "This checker is hardware-free and never opens robot motors, serial ports, cameras, GUI flows, OpenAI calls, or network resources.",
            "The manifest declares authority and provenance; those declarations still require human review before being treated as source truth.",
            "Explicit alignment placeholders are useful diagnostics but do not make model-backed IK residuals trustworthy.",
            "The child model contract checker owns static model/mesh diagnostics; this wrapper only gates whether one reviewed bundle supplies all inputs together.",
        ],
    }
    rows = build_checklist_rows(
        manifest_request,
        model_path,
        asset_roots,
        authority,
        provenance,
        target_frame,
        tcp_offset,
        alignment,
        contract,
        ready,
        summary["missing_inputs"],
    )
    return summary, rows


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "so101_model_bundle_manifest_summary.json"
    csv_path = output_dir / "so101_model_bundle_manifest_checklist.csv"
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(csv_path),
        "readme_md": str(readme_path),
    }

    manifest, manifest_request = load_manifest(args.manifest_path)
    summary, rows = build_summary(manifest, manifest_request, args.python, output_dir, artifacts)

    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    write_markdown(readme_path, summary, rows)

    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
                "missing_inputs": summary["missing_inputs"],
                "manifest_path": summary["manifest_request"]["path"],
                "model_path": summary["model_path"]["path"],
                "asset_roots": summary["asset_roots"]["asset_roots"],
                "contract_status": summary["contract_checker"].get("status"),
                "asset_preflight_status": summary["contract_checker"].get("model_asset_preflight", {}).get("status"),
                "summary_json": str(summary_path),
                "checklist_csv": str(csv_path),
                "readme_md": str(readme_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
