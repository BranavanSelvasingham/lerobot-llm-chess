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
EXPECTED_SO101_JOINTS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
TARGET_FRAME_REVIEW_FIELDS = (
    "target_frame_authority",
    "target_frame_review",
    "tcp_frame_authority",
    "target_frame_metadata",
)
TARGET_FRAME_STATUS_FIELDS = (
    "target_frame_authority_status",
    "target_frame_review_status",
    "review_status",
    "status",
)
REVIEWED_TARGET_FRAME_STATUSES = {
    "reviewed",
    "operator_reviewed",
    "target_frame_reviewed",
    "tcp_frame_reviewed",
    "model_bundle_reviewed",
}
SYNTHETIC_FIXTURE_TARGET_FRAME_STATUS = "synthetic_fixture_reviewed_for_automation_only"
TCP_OFFSET_FIELDS = (
    "tcp_offset_m",
    "gripper_tip_offset_m",
    "target_frame_to_tcp_m",
    "tool_center_point_offset_m",
)
TCP_OFFSET_REVIEW_FIELDS = (
    "tcp_offset_authority",
    "tcp_offset_review",
    "gripper_tip_offset_review",
    "tcp_calibration",
)
TCP_OFFSET_STATUS_FIELDS = (
    "tcp_offset_authority_status",
    "tcp_calibration_status",
    "review_status",
    "status",
)
REVIEWED_TCP_OFFSET_STATUSES = {
    "reviewed",
    "operator_reviewed",
    "tcp_offset_reviewed",
    "tcp_calibration_reviewed",
    "model_bundle_reviewed",
}
SYNTHETIC_FIXTURE_TCP_OFFSET_STATUS = "synthetic_fixture_reviewed_for_automation_only"
JOINT_LIMIT_FIELDS = (
    "joint_limits_deg",
    "joint_limits",
    "joint_limit_authority",
)
JOINT_LIMIT_NESTED_VALUE_FIELDS = (
    "joint_limits_deg",
    "joint_limits",
    "limits_deg",
    "limits",
)
JOINT_LIMIT_REVIEW_FIELDS = (
    "joint_limit_authority",
    "joint_limits_review",
    "joint_limit_review",
    "joint_limits_metadata",
)
JOINT_LIMIT_STATUS_FIELDS = (
    "joint_limit_authority_status",
    "review_status",
    "status",
)
REVIEWED_JOINT_LIMIT_STATUSES = {
    "reviewed",
    "operator_reviewed",
    "joint_limits_reviewed",
    "source_reviewed",
    "model_bundle_reviewed",
}
AUTHORITY_STATUS_FIELDS = (
    "source_authority_status",
    "review_status",
    "status",
)
AUTHORITY_REVIEW_FIELDS = (
    "reviewed_by",
    "reviewed_at",
    "review_id",
    "review_url",
)
REVIEWED_AUTHORITY_STATUSES = {
    "reviewed",
    "operator_reviewed",
    "source_reviewed",
    "model_bundle_reviewed",
    "reviewed_so101_model_bundle",
}
SYNTHETIC_FIXTURE_AUTHORITY_STATUS = "synthetic_fixture_reviewed_for_automation_only"
SYNTHETIC_FIXTURE_JOINT_LIMIT_STATUS = "synthetic_fixture_reviewed_for_automation_only"
PROVENANCE_SOURCE_FIELDS = (
    "source_url",
    "source_uri",
    "cad_url",
    "repository_url",
    "source_path",
    "source_reference",
)
PROVENANCE_EXPORT_FIELDS = (
    "export_tool",
    "exporter",
    "generated_by",
)
PROVENANCE_LICENSE_FIELDS = (
    "license",
    "license_url",
    "license_file",
    "license_review",
    "license_basis",
)
MESH_ASSET_REVIEW_FIELDS = (
    "mesh_asset_authority",
    "mesh_assets_review",
    "mesh_asset_review",
    "mesh_assets_metadata",
)
MESH_ASSET_STATUS_FIELDS = (
    "mesh_asset_authority_status",
    "review_status",
    "status",
)
REVIEWED_MESH_ASSET_STATUSES = {
    "reviewed",
    "operator_reviewed",
    "mesh_assets_reviewed",
    "source_reviewed",
    "model_bundle_reviewed",
}
SYNTHETIC_FIXTURE_MESH_ASSET_STATUS = "synthetic_fixture_reviewed_for_automation_only"
ALIGNMENT_FIELDS = (
    "base_to_board_transform",
    "base_to_board_alignment",
)
ALIGNMENT_REVIEW_FIELDS = (
    "base_to_board_alignment_authority",
    "base_to_board_authority",
    "base_to_board_alignment_review",
    "base_to_board_review",
    "alignment_calibration",
)
ALIGNMENT_STATUS_FIELDS = (
    "base_to_board_alignment_authority_status",
    "base_to_board_authority_status",
    "alignment_calibration_status",
    "review_status",
    "status",
)
REVIEWED_ALIGNMENT_STATUSES = {
    "reviewed",
    "operator_reviewed",
    "base_to_board_reviewed",
    "alignment_reviewed",
    "calibration_reviewed",
    "model_bundle_reviewed",
}
SYNTHETIC_FIXTURE_ALIGNMENT_STATUS = "synthetic_fixture_reviewed_for_automation_only"
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
        "input": "joint_limits_deg",
        "requirement": "Reviewed joint-limit authority covering every SO-101 joint.",
    },
    {
        "input": "mesh_assets",
        "requirement": "At least one model mesh reference visible to asset preflight and resolved with no missing assets.",
    },
    {
        "input": "target_frame",
        "requirement": f"Reviewed target frame name; diagnostics may default to {EXPECTED_TARGET_FRAME!r} when omitted.",
    },
    {
        "input": "tcp_offset_m",
        "requirement": "Calibrated target-frame to TCP/gripper-tip offset as x/y/z meters with review authority.",
    },
    {
        "input": "base_to_board_transform",
        "requirement": "Calibrated base-to-board transform with review authority, not only a placeholder.",
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


def executable_arg(path: Path) -> str:
    raw = str(path)
    if path.is_absolute() or "/" in raw:
        return str(normalize_path(path))
    return raw


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


def has_any_non_empty_field(value: dict[str, Any], field_names: tuple[str, ...]) -> bool:
    return any(non_empty(value.get(field_name)) for field_name in field_names)


def first_non_empty_field(value: dict[str, Any], field_names: tuple[str, ...]) -> tuple[str | None, Any]:
    for field_name in field_names:
        field_value = value.get(field_name)
        if non_empty(field_value):
            return field_name, field_value
    return None, None


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


def vector_status(value: Any, axes: tuple[str, str, str]) -> dict[str, Any]:
    if isinstance(value, dict):
        missing = [axis for axis in axes if axis not in value]
        if missing:
            return {
                "present": True,
                "valid": False,
                "value": value,
                "diagnostics": [f"missing_axis:{axis}" for axis in missing],
            }
        try:
            vector = {axis: float(value[axis]) for axis in axes}
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
        "diagnostics": [f"expected_{'_'.join(axes)}_object_or_len3_list"],
    }


def vector3_status(value: Any) -> dict[str, Any]:
    return vector_status(value, ("x", "y", "z"))


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
    if not isinstance(value, dict) or not value:
        return {
            "status": "missing",
            "value": value,
            "diagnostics": ["authority_missing_or_empty"],
            "accepted_review_statuses": sorted(REVIEWED_AUTHORITY_STATUSES),
        }

    status_field, raw_status = first_non_empty_field(value, AUTHORITY_STATUS_FIELDS)
    status_value = str(raw_status).strip().lower() if raw_status is not None else ""
    review_field_present = has_any_non_empty_field(value, AUTHORITY_REVIEW_FIELDS)
    diagnostics: list[str] = []
    if not status_value:
        diagnostics.append("authority_review_status_missing")
    elif status_value not in REVIEWED_AUTHORITY_STATUSES and status_value != SYNTHETIC_FIXTURE_AUTHORITY_STATUS:
        diagnostics.append(f"authority_review_status_not_accepted:{status_value}")
    if not review_field_present:
        diagnostics.append("authority_review_evidence_missing")

    is_synthetic_fixture = status_value == SYNTHETIC_FIXTURE_AUTHORITY_STATUS
    if is_synthetic_fixture and "hardware-free" not in str(value.get("scope", "")).lower():
        diagnostics.append("synthetic_fixture_scope_missing_hardware_free")

    review_status_ok = status_value in REVIEWED_AUTHORITY_STATUSES or (
        is_synthetic_fixture and "synthetic_fixture_scope_missing_hardware_free" not in diagnostics
    )
    status = "present" if review_status_ok and review_field_present else "needs_review"
    return {
        "status": status,
        "value": value,
        "review_status_field": status_field,
        "review_status": status_value or None,
        "review_evidence_present": review_field_present,
        "synthetic_fixture_only": is_synthetic_fixture,
        "diagnostics": diagnostics,
        "accepted_review_statuses": sorted(REVIEWED_AUTHORITY_STATUSES),
        "notes": (
            "Synthetic fixture authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 source authority."
            if is_synthetic_fixture
            else "Authority requires an accepted reviewed status plus reviewer/date/id/url evidence."
        ),
    }


def inspect_provenance(manifest: dict[str, Any] | None) -> dict[str, Any]:
    value = manifest.get("provenance") if manifest else None
    if not isinstance(value, dict) or not value:
        return {
            "status": "missing",
            "value": value,
            "diagnostics": ["provenance_missing_or_empty"],
            "required_field_groups": {
                "source": list(PROVENANCE_SOURCE_FIELDS),
                "export": list(PROVENANCE_EXPORT_FIELDS),
                "license": list(PROVENANCE_LICENSE_FIELDS),
            },
        }

    source_field, source_value = first_non_empty_field(value, PROVENANCE_SOURCE_FIELDS)
    export_field, export_value = first_non_empty_field(value, PROVENANCE_EXPORT_FIELDS)
    license_field, license_value = first_non_empty_field(value, PROVENANCE_LICENSE_FIELDS)
    diagnostics: list[str] = []
    if source_field is None:
        diagnostics.append("provenance_source_reference_missing")
    if export_field is None:
        diagnostics.append("provenance_export_tool_missing")
    if license_field is None:
        diagnostics.append("provenance_license_basis_missing")

    return {
        "status": "present" if not diagnostics else "needs_review",
        "value": value,
        "source_field": source_field,
        "source_value": source_value,
        "export_field": export_field,
        "export_value": export_value,
        "license_field": license_field,
        "license_value": license_value,
        "diagnostics": diagnostics,
        "required_field_groups": {
            "source": list(PROVENANCE_SOURCE_FIELDS),
            "export": list(PROVENANCE_EXPORT_FIELDS),
            "license": list(PROVENANCE_LICENSE_FIELDS),
        },
        "notes": "Provenance requires source reference, export tool, and license basis fields.",
    }


def parse_joint_limit_pair(value: Any) -> tuple[bool, Any, list[str]]:
    if isinstance(value, dict):
        lower_key = "lower" if "lower" in value else "min" if "min" in value else None
        upper_key = "upper" if "upper" in value else "max" if "max" in value else None
        if lower_key is None or upper_key is None:
            return False, value, ["joint_limit_missing_lower_or_upper"]
        try:
            lower = float(value[lower_key])
            upper = float(value[upper_key])
        except (TypeError, ValueError) as exc:
            return False, value, [f"joint_limit_non_numeric:{type(exc).__name__}"]
        if lower >= upper:
            return False, {"lower": lower, "upper": upper}, ["joint_limit_lower_not_below_upper"]
        return True, {"lower": lower, "upper": upper}, []

    if isinstance(value, list) and len(value) == 2:
        try:
            lower = float(value[0])
            upper = float(value[1])
        except (TypeError, ValueError) as exc:
            return False, value, [f"joint_limit_non_numeric:{type(exc).__name__}"]
        if lower >= upper:
            return False, [lower, upper], ["joint_limit_lower_not_below_upper"]
        return True, [lower, upper], []

    return False, value, ["joint_limit_expected_lower_upper_or_len2_list"]


def joint_limit_values_from_field(field_name: str, value: Any) -> tuple[str, Any]:
    if field_name == "joint_limit_authority" and isinstance(value, dict):
        nested_field, nested_value = find_first_field(value, JOINT_LIMIT_NESTED_VALUE_FIELDS)
        if nested_field is not None:
            return f"{field_name}.{nested_field}", nested_value
    return field_name, value


def inspect_joint_limit_review(
    manifest: dict[str, Any],
    field_name: str,
    raw_value: Any,
) -> dict[str, Any]:
    candidates: list[tuple[str, Any]] = []
    if field_name == "joint_limit_authority":
        candidates.append((field_name, raw_value))
    if isinstance(raw_value, dict):
        candidates.append((field_name, raw_value))
    for review_field in JOINT_LIMIT_REVIEW_FIELDS:
        if review_field in manifest:
            candidates.append((review_field, manifest.get(review_field)))

    review_source = None
    review_source_field = None
    for candidate_field, candidate_value in candidates:
        if not isinstance(candidate_value, dict):
            continue
        has_status = has_any_non_empty_field(candidate_value, JOINT_LIMIT_STATUS_FIELDS)
        has_review = has_any_non_empty_field(candidate_value, AUTHORITY_REVIEW_FIELDS)
        if has_status or has_review:
            review_source = candidate_value
            review_source_field = candidate_field
            break

    if not isinstance(review_source, dict):
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "review_status": None,
            "review_evidence_present": False,
            "synthetic_fixture_only": False,
            "accepted_review_statuses": sorted(REVIEWED_JOINT_LIMIT_STATUSES),
            "diagnostics": ["joint_limit_authority_review_missing"],
        }

    status_field, raw_status = first_non_empty_field(review_source, JOINT_LIMIT_STATUS_FIELDS)
    status_value = str(raw_status).strip().lower() if raw_status is not None else ""
    review_field_present = has_any_non_empty_field(review_source, AUTHORITY_REVIEW_FIELDS)
    diagnostics: list[str] = []
    if not status_value:
        diagnostics.append("joint_limit_authority_review_status_missing")
    elif (
        status_value not in REVIEWED_JOINT_LIMIT_STATUSES
        and status_value != SYNTHETIC_FIXTURE_JOINT_LIMIT_STATUS
    ):
        diagnostics.append(f"joint_limit_authority_review_status_not_accepted:{status_value}")
    if not review_field_present:
        diagnostics.append("joint_limit_authority_review_evidence_missing")

    is_synthetic_fixture = status_value == SYNTHETIC_FIXTURE_JOINT_LIMIT_STATUS
    if is_synthetic_fixture and "hardware-free" not in str(review_source.get("scope", "")).lower():
        diagnostics.append("synthetic_joint_limit_scope_missing_hardware_free")

    review_status_ok = status_value in REVIEWED_JOINT_LIMIT_STATUSES or (
        is_synthetic_fixture and "synthetic_joint_limit_scope_missing_hardware_free" not in diagnostics
    )
    return {
        "status": "present" if review_status_ok and review_field_present else "needs_review",
        "field": review_source_field,
        "value": review_source,
        "review_status_field": status_field,
        "review_status": status_value or None,
        "review_evidence_present": review_field_present,
        "synthetic_fixture_only": is_synthetic_fixture,
        "accepted_review_statuses": sorted(REVIEWED_JOINT_LIMIT_STATUSES),
        "diagnostics": diagnostics,
        "notes": (
            "Synthetic fixture joint-limit authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 joint-limit truth."
            if is_synthetic_fixture
            else "Joint-limit readiness requires accepted review status plus reviewer/date/id/url evidence."
        ),
    }


def inspect_joint_limits(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "expected_joints": list(EXPECTED_SO101_JOINTS),
            "missing_joints": list(EXPECTED_SO101_JOINTS),
            "invalid_joints": [],
            "diagnostics": ["joint_limits_missing"],
        }

    field_name, value = find_first_field(manifest, JOINT_LIMIT_FIELDS)
    if field_name is None:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "expected_joints": list(EXPECTED_SO101_JOINTS),
            "missing_joints": list(EXPECTED_SO101_JOINTS),
            "invalid_joints": [],
            "diagnostics": ["joint_limits_missing"],
        }
    value_field_name, value_payload = joint_limit_values_from_field(field_name, value)
    if not isinstance(value_payload, dict):
        return {
            "status": "invalid",
            "field": field_name,
            "value_field": value_field_name,
            "value": value_payload,
            "expected_joints": list(EXPECTED_SO101_JOINTS),
            "missing_joints": list(EXPECTED_SO101_JOINTS),
            "invalid_joints": [],
            "diagnostics": ["joint_limits_not_object"],
        }

    normalized: dict[str, Any] = {}
    invalid_joints: list[dict[str, Any]] = []
    for joint in EXPECTED_SO101_JOINTS:
        if joint not in value_payload:
            continue
        valid, normalized_value, diagnostics = parse_joint_limit_pair(value_payload[joint])
        if valid:
            normalized[joint] = normalized_value
        else:
            invalid_joints.append(
                {"joint": joint, "value": normalized_value, "diagnostics": diagnostics}
            )
    missing_joints = [joint for joint in EXPECTED_SO101_JOINTS if joint not in normalized]
    diagnostics = []
    if missing_joints:
        diagnostics.extend(f"joint_limit_missing:{joint}" for joint in missing_joints)
    for invalid in invalid_joints:
        diagnostics.extend(
            f"joint_limit_invalid:{invalid['joint']}:{diagnostic}"
            for diagnostic in invalid["diagnostics"]
        )
    review = inspect_joint_limit_review(manifest, field_name, value)
    if not diagnostics and review["status"] != "present":
        diagnostics.extend(review.get("diagnostics", []))
    return {
        "status": "present" if not diagnostics else "needs_review" if not missing_joints and not invalid_joints else "invalid",
        "field": field_name,
        "value_field": value_field_name,
        "value": normalized,
        "review": review,
        "review_status": review.get("status"),
        "review_diagnostics": review.get("diagnostics", []),
        "expected_joints": list(EXPECTED_SO101_JOINTS),
        "missing_joints": missing_joints,
        "invalid_joints": invalid_joints,
        "diagnostics": diagnostics,
    }


def inspect_target_frame(manifest: dict[str, Any] | None) -> dict[str, Any]:
    raw = manifest.get("target_frame") if manifest else None
    if raw is None:
        return {
            "status": "missing",
            "value": EXPECTED_TARGET_FRAME,
            "defaulted_value": EXPECTED_TARGET_FRAME,
            "diagnostics": ["target_frame_missing"],
            "notes": f"target_frame omitted; diagnostics use {EXPECTED_TARGET_FRAME} but readiness requires an explicit reviewed target frame.",
        }
    if isinstance(raw, str) and raw.strip():
        diagnostics = [] if raw == EXPECTED_TARGET_FRAME else ["target_frame_differs_from_default"]
        review = inspect_target_frame_review(manifest, raw)
        if review["status"] != "present":
            diagnostics.extend(review.get("diagnostics", []))
        return {
            "status": "present" if review["status"] == "present" else "needs_review",
            "value": raw,
            "review": review,
            "review_status": review.get("status"),
            "review_diagnostics": review.get("diagnostics", []),
            "diagnostics": diagnostics,
        }
    return {
        "status": "invalid",
        "value": raw,
        "diagnostics": ["target_frame_not_nonempty_string"],
    }


def inspect_review_metadata(
    candidates: list[tuple[str, Any]],
    *,
    status_fields: tuple[str, ...],
    accepted_statuses: set[str],
    synthetic_status: str,
    diagnostic_prefix: str,
    synthetic_scope_diagnostic: str,
    synthetic_note: str,
    review_note: str,
) -> dict[str, Any]:
    review_source = None
    review_source_field = None
    for candidate_field, candidate_value in candidates:
        if not isinstance(candidate_value, dict):
            continue
        has_status = has_any_non_empty_field(candidate_value, status_fields)
        has_review = has_any_non_empty_field(candidate_value, AUTHORITY_REVIEW_FIELDS)
        if has_status or has_review:
            review_source = candidate_value
            review_source_field = candidate_field
            break

    if not isinstance(review_source, dict):
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "review_status": None,
            "review_evidence_present": False,
            "synthetic_fixture_only": False,
            "accepted_review_statuses": sorted(accepted_statuses),
            "diagnostics": [f"{diagnostic_prefix}_review_missing"],
        }

    status_field, raw_status = first_non_empty_field(review_source, status_fields)
    status_value = str(raw_status).strip().lower() if raw_status is not None else ""
    review_field_present = has_any_non_empty_field(review_source, AUTHORITY_REVIEW_FIELDS)
    diagnostics: list[str] = []
    if not status_value:
        diagnostics.append(f"{diagnostic_prefix}_review_status_missing")
    elif status_value not in accepted_statuses and status_value != synthetic_status:
        diagnostics.append(f"{diagnostic_prefix}_review_status_not_accepted:{status_value}")
    if not review_field_present:
        diagnostics.append(f"{diagnostic_prefix}_review_evidence_missing")

    is_synthetic_fixture = status_value == synthetic_status
    if is_synthetic_fixture and "hardware-free" not in str(review_source.get("scope", "")).lower():
        diagnostics.append(synthetic_scope_diagnostic)

    review_status_ok = status_value in accepted_statuses or (
        is_synthetic_fixture and synthetic_scope_diagnostic not in diagnostics
    )
    return {
        "status": "present" if review_status_ok and review_field_present else "needs_review",
        "field": review_source_field,
        "value": review_source,
        "review_status_field": status_field,
        "review_status": status_value or None,
        "review_evidence_present": review_field_present,
        "synthetic_fixture_only": is_synthetic_fixture,
        "accepted_review_statuses": sorted(accepted_statuses),
        "diagnostics": diagnostics,
        "notes": synthetic_note if is_synthetic_fixture else review_note,
    }


def inspect_tcp_offset_review(
    manifest: dict[str, Any],
    field_name: str,
    raw_value: Any,
) -> dict[str, Any]:
    candidates: list[tuple[str, Any]] = []
    if isinstance(raw_value, dict):
        candidates.append((field_name, raw_value))
    for review_field in TCP_OFFSET_REVIEW_FIELDS:
        if review_field in manifest:
            candidates.append((review_field, manifest.get(review_field)))
    return inspect_review_metadata(
        candidates,
        status_fields=TCP_OFFSET_STATUS_FIELDS,
        accepted_statuses=REVIEWED_TCP_OFFSET_STATUSES,
        synthetic_status=SYNTHETIC_FIXTURE_TCP_OFFSET_STATUS,
        diagnostic_prefix="tcp_offset_authority",
        synthetic_scope_diagnostic="synthetic_tcp_offset_scope_missing_hardware_free",
        synthetic_note=(
            "Synthetic fixture TCP offset authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 TCP truth."
        ),
        review_note="TCP offset readiness requires accepted review status plus reviewer/date/id/url evidence.",
    )


def inspect_target_frame_review(
    manifest: dict[str, Any],
    raw_value: str,
) -> dict[str, Any]:
    candidates: list[tuple[str, Any]] = []
    for review_field in TARGET_FRAME_REVIEW_FIELDS:
        if review_field in manifest:
            candidates.append((review_field, manifest.get(review_field)))
    review = inspect_review_metadata(
        candidates,
        status_fields=TARGET_FRAME_STATUS_FIELDS,
        accepted_statuses=REVIEWED_TARGET_FRAME_STATUSES,
        synthetic_status=SYNTHETIC_FIXTURE_TARGET_FRAME_STATUS,
        diagnostic_prefix="target_frame_authority",
        synthetic_scope_diagnostic="synthetic_target_frame_scope_missing_hardware_free",
        synthetic_note=(
            "Synthetic fixture target-frame authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 TCP-frame truth."
        ),
        review_note="Target-frame readiness requires accepted review status plus reviewer/date/id/url evidence.",
    )
    return {
        **review,
        "target_frame": raw_value,
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
    review = inspect_tcp_offset_review(manifest, field_name, value)
    diagnostics = list(vector["diagnostics"])
    if vector["valid"] and review["status"] != "present":
        diagnostics.extend(review.get("diagnostics", []))
    return {
        "status": "present" if not diagnostics else "needs_review" if vector["valid"] else "invalid",
        "field": field_name,
        "value": vector["value"],
        "review": review,
        "review_status": review.get("status"),
        "review_diagnostics": review.get("diagnostics", []),
        "diagnostics": diagnostics,
    }


def alignment_transform_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "valid": False,
            "value": value,
            "diagnostics": ["base_to_board_transform_not_object"],
        }

    translation_field, translation_value = find_first_field(
        value,
        ("translation_m", "translation", "position_m"),
    )
    rotation_field, rotation_value = find_first_field(
        value,
        ("rotation_rpy_rad", "rotation_rpy", "rpy_rad"),
    )
    diagnostics: list[str] = []
    normalized: dict[str, Any] = {}
    if translation_field is None:
        diagnostics.append("base_to_board_translation_missing")
    else:
        translation = vector3_status(translation_value)
        normalized["translation"] = {
            "field": translation_field,
            "value": translation["value"],
        }
        diagnostics.extend(f"translation:{diagnostic}" for diagnostic in translation["diagnostics"])
    if rotation_field is None:
        diagnostics.append("base_to_board_rotation_rpy_missing")
    else:
        rotation = vector_status(rotation_value, ("roll", "pitch", "yaw"))
        normalized["rotation_rpy"] = {
            "field": rotation_field,
            "value": rotation["value"],
        }
        diagnostics.extend(f"rotation_rpy:{diagnostic}" for diagnostic in rotation["diagnostics"])
    return {
        "valid": not diagnostics,
        "value": normalized if normalized else value,
        "diagnostics": diagnostics,
    }


def inspect_alignment_review(
    manifest: dict[str, Any],
    field_name: str,
    raw_value: Any,
) -> dict[str, Any]:
    candidates: list[tuple[str, Any]] = []
    if isinstance(raw_value, dict):
        candidates.append((field_name, raw_value))
    for review_field in ALIGNMENT_REVIEW_FIELDS:
        if review_field in manifest:
            candidates.append((review_field, manifest.get(review_field)))
    return inspect_review_metadata(
        candidates,
        status_fields=ALIGNMENT_STATUS_FIELDS,
        accepted_statuses=REVIEWED_ALIGNMENT_STATUSES,
        synthetic_status=SYNTHETIC_FIXTURE_ALIGNMENT_STATUS,
        diagnostic_prefix="base_to_board_alignment_authority",
        synthetic_scope_diagnostic="synthetic_base_to_board_alignment_scope_missing_hardware_free",
        synthetic_note=(
            "Synthetic fixture base-to-board alignment authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 board-alignment truth."
        ),
        review_note="Base-to-board alignment readiness requires accepted review status plus reviewer/date/id/url evidence.",
    )


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
        transform = alignment_transform_status(value)
        review = inspect_alignment_review(manifest, field_name, value)
        diagnostics = list(transform["diagnostics"])
        if transform["valid"] and review["status"] != "present":
            diagnostics.extend(review.get("diagnostics", []))
        return {
            "status": "present" if not diagnostics else "needs_review" if transform["valid"] else "invalid",
            "field": field_name,
            "value": value,
            "transform": transform,
            "review": review,
            "review_status": review.get("status"),
            "review_diagnostics": review.get("diagnostics", []),
            "placeholder_field": None,
            "placeholder_value": None,
            "diagnostics": diagnostics,
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
        executable_arg(python_path),
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
    if contract.get("model_request_status") != "model_supplied":
        diagnostics.append(f"model_request_status:{contract.get('model_request_status')}")

    contract_status = contract.get("status")
    if contract_status == "model_contract_checked":
        pass
    elif contract_status == "model_suffix_supported_not_directly_usable":
        structure = (contract.get("child_diagnostics") or {}).get("model_structure_inspection") or {}
        missing_joints = structure.get("expected_joint_names_missing")
        target_frame_present = structure.get("target_frame_present")
        if missing_joints:
            diagnostics.append(f"model_structure_missing_joints:{missing_joints}")
        if target_frame_present is not True:
            diagnostics.append(f"model_structure_target_frame_present:{target_frame_present}")
    elif (
        contract_status == "model_contract_needs_follow_up"
        and contract.get("robot_kinematics_status") == "urdf_requires_placo"
        and contract.get("robot_kinematics_initialization_status") == "not_attempted"
    ):
        structure = (contract.get("child_diagnostics") or {}).get("model_structure_inspection") or {}
        missing_joints = structure.get("expected_joint_names_missing")
        target_frame_present = structure.get("target_frame_present")
        if missing_joints:
            diagnostics.append(f"model_structure_missing_joints:{missing_joints}")
        if target_frame_present is not True:
            diagnostics.append(f"model_structure_target_frame_present:{target_frame_present}")
    else:
        diagnostics.append(f"contract_status:{contract_status}")

    asset_preflight = contract.get("model_asset_preflight") or {}
    if asset_preflight.get("status") not in {"asset_preflight_checked", "asset_preflight_limited_diagnostics"}:
        diagnostics.append(f"asset_preflight_status:{asset_preflight.get('status')}")
    mesh_reference_count = asset_preflight.get("mesh_reference_count")
    if not isinstance(mesh_reference_count, int) or mesh_reference_count <= 0:
        diagnostics.append(f"mesh_reference_count:{mesh_reference_count}")
    if asset_preflight.get("missing_asset_count") not in {0, None}:
        diagnostics.append(f"missing_asset_count:{asset_preflight.get('missing_asset_count')}")
    if asset_preflight.get("unresolved_reference_count") not in {0, None}:
        diagnostics.append(f"unresolved_reference_count:{asset_preflight.get('unresolved_reference_count')}")

    return not diagnostics, diagnostics


def inspect_mesh_asset_review(manifest: dict[str, Any] | None) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {}
    review_source = None
    review_source_field = None
    for review_field in MESH_ASSET_REVIEW_FIELDS:
        candidate = manifest.get(review_field)
        if not isinstance(candidate, dict):
            continue
        has_status = has_any_non_empty_field(candidate, MESH_ASSET_STATUS_FIELDS)
        has_review = has_any_non_empty_field(candidate, AUTHORITY_REVIEW_FIELDS)
        if has_status or has_review:
            review_source = candidate
            review_source_field = review_field
            break

    if not isinstance(review_source, dict):
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "review_status": None,
            "review_evidence_present": False,
            "synthetic_fixture_only": False,
            "accepted_review_statuses": sorted(REVIEWED_MESH_ASSET_STATUSES),
            "diagnostics": ["mesh_asset_authority_review_missing"],
        }

    status_field, raw_status = first_non_empty_field(review_source, MESH_ASSET_STATUS_FIELDS)
    status_value = str(raw_status).strip().lower() if raw_status is not None else ""
    review_field_present = has_any_non_empty_field(review_source, AUTHORITY_REVIEW_FIELDS)
    diagnostics: list[str] = []
    if not status_value:
        diagnostics.append("mesh_asset_authority_review_status_missing")
    elif (
        status_value not in REVIEWED_MESH_ASSET_STATUSES
        and status_value != SYNTHETIC_FIXTURE_MESH_ASSET_STATUS
    ):
        diagnostics.append(f"mesh_asset_authority_review_status_not_accepted:{status_value}")
    if not review_field_present:
        diagnostics.append("mesh_asset_authority_review_evidence_missing")

    is_synthetic_fixture = status_value == SYNTHETIC_FIXTURE_MESH_ASSET_STATUS
    if is_synthetic_fixture and "hardware-free" not in str(review_source.get("scope", "")).lower():
        diagnostics.append("synthetic_mesh_asset_scope_missing_hardware_free")

    review_status_ok = status_value in REVIEWED_MESH_ASSET_STATUSES or (
        is_synthetic_fixture and "synthetic_mesh_asset_scope_missing_hardware_free" not in diagnostics
    )
    return {
        "status": "present" if review_status_ok and review_field_present else "needs_review",
        "field": review_source_field,
        "value": review_source,
        "review_status_field": status_field,
        "review_status": status_value or None,
        "review_evidence_present": review_field_present,
        "synthetic_fixture_only": is_synthetic_fixture,
        "accepted_review_statuses": sorted(REVIEWED_MESH_ASSET_STATUSES),
        "diagnostics": diagnostics,
        "notes": (
            "Synthetic fixture mesh-asset authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 mesh truth."
            if is_synthetic_fixture
            else "Mesh readiness requires accepted review status plus reviewer/date/id/url evidence."
        ),
    }


def inspect_mesh_assets(contract: dict[str, Any], manifest: dict[str, Any] | None) -> dict[str, Any]:
    asset_preflight = contract.get("model_asset_preflight") or {}
    mesh_reference_count = asset_preflight.get("mesh_reference_count")
    present_asset_count = asset_preflight.get("present_asset_count")
    missing_asset_count = asset_preflight.get("missing_asset_count")
    unresolved_reference_count = asset_preflight.get("unresolved_reference_count")
    review = inspect_mesh_asset_review(manifest)
    diagnostics: list[str] = []
    if not isinstance(mesh_reference_count, int) or mesh_reference_count <= 0:
        diagnostics.append("mesh_reference_count_missing_or_zero")
    if missing_asset_count not in {0, None}:
        diagnostics.append(f"missing_asset_count:{missing_asset_count}")
    if unresolved_reference_count not in {0, None}:
        diagnostics.append(f"unresolved_reference_count:{unresolved_reference_count}")
    if diagnostics:
        status = "missing" if not isinstance(mesh_reference_count, int) or mesh_reference_count <= 0 else "needs_follow_up"
    elif review["status"] == "present":
        status = "present"
    else:
        status = "needs_review"
        diagnostics.extend(review.get("diagnostics", []))
    return {
        "status": status,
        "mesh_reference_count": mesh_reference_count,
        "present_asset_count": present_asset_count,
        "missing_asset_count": missing_asset_count,
        "unresolved_reference_count": unresolved_reference_count,
        "asset_preflight_status": asset_preflight.get("status"),
        "artifacts": asset_preflight.get("artifacts"),
        "review": review,
        "review_status": review.get("status"),
        "review_diagnostics": review.get("diagnostics", []),
        "diagnostics": diagnostics,
    }


def mesh_asset_missing_inputs(mesh_assets: dict[str, Any]) -> list[str] | None:
    status = mesh_assets.get("status")
    if status == "present":
        return None
    if status == "needs_review":
        return ["mesh_asset_authority"]
    return ["mesh_assets"]


def joint_limit_missing_inputs(joint_limits: dict[str, Any]) -> list[str] | None:
    status = joint_limits.get("status")
    if status == "present":
        return None
    if status == "needs_review":
        return ["joint_limit_authority"]
    return ["joint_limits_deg"]


def tcp_offset_missing_inputs(tcp_offset: dict[str, Any]) -> list[str] | None:
    status = tcp_offset.get("status")
    if status == "present":
        return None
    if status == "needs_review":
        return ["tcp_offset_authority"]
    return ["tcp_offset_m"]


def alignment_missing_inputs(alignment: dict[str, Any]) -> list[str] | None:
    status = alignment.get("status")
    if status == "present":
        return None
    if status == "needs_review":
        return ["base_to_board_alignment_authority"]
    return ["base_to_board_transform"]


def target_frame_missing_inputs(target_frame: dict[str, Any]) -> list[str] | None:
    status = target_frame.get("status")
    if status == "present":
        return None
    if status == "needs_review":
        return ["target_frame_authority"]
    return ["target_frame"]


def build_field_checks(
    manifest_request: dict[str, Any],
    model_path: dict[str, Any],
    asset_roots: dict[str, Any],
    authority: dict[str, Any],
    provenance: dict[str, Any],
    joint_limits: dict[str, Any],
    mesh_assets: dict[str, Any],
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
            "requirement_id": "joint_limits_deg",
            "ok": joint_limits["status"] == "present",
            "missing_inputs": joint_limit_missing_inputs(joint_limits),
            "diagnostics": joint_limits.get("diagnostics", []),
        },
        {
            "requirement_id": "mesh_assets",
            "ok": mesh_assets["status"] == "present",
            "missing_inputs": mesh_asset_missing_inputs(mesh_assets),
            "diagnostics": mesh_assets.get("diagnostics", []),
        },
        {
            "requirement_id": "target_frame",
            "ok": target_frame["status"] == "present",
            "missing_inputs": target_frame_missing_inputs(target_frame),
            "diagnostics": target_frame.get("diagnostics", []),
        },
        {
            "requirement_id": "tcp_offset_m",
            "ok": tcp_offset["status"] == "present",
            "missing_inputs": tcp_offset_missing_inputs(tcp_offset),
            "diagnostics": tcp_offset.get("diagnostics", []),
        },
        {
            "requirement_id": "base_to_board_transform",
            "ok": alignment["status"] == "present",
            "missing_inputs": alignment_missing_inputs(alignment),
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
    joint_limits: dict[str, Any],
    mesh_assets: dict[str, Any],
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
            "joint_limits_deg",
            "joint_contract",
            "ok" if joint_limits["status"] == "present" else "action_required",
            "warning",
            f"manifest.{'|'.join(JOINT_LIMIT_FIELDS)}",
            joint_limits,
            {
                "required_joints": list(EXPECTED_SO101_JOINTS),
                "unit": "degrees",
                "review_authority": True,
            },
            joint_limit_missing_inputs(joint_limits),
            joint_limits.get("diagnostics", []),
            "The reviewed bundle must declare limit authority for every SO-101 joint before model-backed IK is trusted.",
        ),
        row(
            "mesh_assets",
            "mesh_assets",
            "ok" if mesh_assets["status"] == "present" else "action_required",
            "warning",
            "contract_checker.model_asset_preflight",
            mesh_assets,
            {
                "mesh_reference_count": "> 0",
                "missing_asset_count": 0,
                "unresolved_reference_count": 0,
                "review_authority": True,
            },
            mesh_asset_missing_inputs(mesh_assets),
            mesh_assets.get("diagnostics", []),
            "Readiness requires resolved model mesh references plus reviewed mesh/asset-root authority.",
        ),
        row(
            "target_frame",
            "tcp_frame",
            "ok" if target_frame["status"] == "present" else "action_required",
            "info",
            f"manifest.target_frame|{'|'.join(TARGET_FRAME_REVIEW_FIELDS)}",
            target_frame,
            {"target_frame": EXPECTED_TARGET_FRAME, "review_authority": True},
            target_frame_missing_inputs(target_frame),
            target_frame.get("diagnostics", []),
            "Readiness requires an explicit target_frame plus reviewed target-frame authority.",
        ),
        row(
            "tcp_offset_m",
            "tcp_frame",
            "ok" if tcp_offset["status"] == "present" else "action_required",
            "warning",
            f"manifest.{'|'.join(TCP_OFFSET_FIELDS)}",
            tcp_offset,
            {"x": "meters", "y": "meters", "z": "meters", "review_authority": True},
            tcp_offset_missing_inputs(tcp_offset),
            tcp_offset.get("diagnostics", []),
            "Accepted aliases are tcp_offset_m, gripper_tip_offset_m, target_frame_to_tcp_m, and tool_center_point_offset_m; readiness also requires reviewed TCP authority.",
        ),
        row(
            "base_to_board_transform",
            "alignment",
            "ok" if alignment["status"] == "present" else "action_required",
            "warning",
            f"manifest.{'|'.join(ALIGNMENT_FIELDS + ALIGNMENT_PLACEHOLDER_FIELDS)}",
            alignment,
            {
                "calibrated_transform": True,
                "translation_m": "x/y/z meters",
                "rotation_rpy_rad": "roll/pitch/yaw radians",
                "review_authority": True,
            },
            alignment_missing_inputs(alignment),
            alignment.get("diagnostics", []),
            "Explicit placeholders are recorded but do not make the bundle ready; readiness requires reviewed base-to-board alignment authority.",
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
        f"- `joint_limits_status`: `{summary['joint_limits']['status']}`",
        f"- `mesh_assets_status`: `{summary['mesh_assets']['status']}`",
        f"- `mesh_reference_count`: `{summary['mesh_assets']['mesh_reference_count']}`",
        f"- `target_frame`: `{summary['target_frame']['value']}`",
        f"- `tcp_offset_status`: `{summary['tcp_offset']['status']}`",
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
    joint_limits = inspect_joint_limits(manifest)
    mesh_assets = inspect_mesh_assets(contract, manifest)
    field_checks = build_field_checks(
        manifest_request,
        model_path,
        asset_roots,
        authority,
        provenance,
        joint_limits,
        mesh_assets,
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
        "joint_limits": joint_limits,
        "mesh_assets": mesh_assets,
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
        joint_limits,
        mesh_assets,
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
                "joint_limits_status": summary["joint_limits"]["status"],
                "mesh_assets_status": summary["mesh_assets"]["status"],
                "mesh_reference_count": summary["mesh_assets"]["mesh_reference_count"],
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
