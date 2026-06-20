#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = "lerobot.sim.so101_model_bundle_manifest.v1"
REVIEW_PACKET_SCHEMA = "lerobot.sim.so101_model_bundle_manifest_review_packet.v1"
BUNDLE_INTAKE_SCHEMA = "lerobot.sim.so101_model_bundle_manifest_intake_checklist.v1"
REVIEW_REQUIREMENTS_SCHEMA = (
    "lerobot.sim.so101_model_bundle_manifest_review_requirements.v1"
)
REVIEWED_MANIFEST_TEMPLATE_SCHEMA = (
    "lerobot.sim.so101_model_bundle_manifest_template.v1"
)
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
JOINT_LIMIT_REQUIRED_REVIEW_SCOPE_IDS = ("joint_limits",)
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
AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS = (
    "model_identity",
    "provenance",
    "license",
)
REVIEW_SCOPE_FIELDS = (
    "review_scope",
    "review_scopes",
    "review_scope_id",
    "review_scope_ids",
)
REVIEW_SCOPE_DESCRIPTIONS = {
    "model_identity": "The selected model path, digest, and SO-101 identity were reviewed.",
    "provenance": "The source/export path and provenance context were reviewed.",
    "license": "The license or redistribution basis was reviewed.",
    "joint_limits": "The SO-101 joint-limit values were reviewed.",
    "mesh_assets": "The mesh references and asset roots were reviewed.",
    "target_frame": "The MuJoCo/SO-101 target frame was reviewed.",
    "tcp_offset": "The TCP or gripper-tip offset was reviewed.",
    "base_to_board_alignment": "The base-to-board transform was reviewed.",
}
REVIEW_EVIDENCE_REQUIRED_GROUPS = (
    ("review_actor", ("reviewed_by",)),
    ("review_trace", ("reviewed_at", "review_id", "review_url")),
    ("review_artifact", ("review_id", "review_url")),
)
REVIEW_OPEN_WORK_FIELDS = (
    "missing_inputs",
    "missing_review_inputs",
    "next_required_for_goal",
    "next_required_action_ids",
    "pending_action_ids",
    "blockers",
    "review_blockers",
    "unresolved_findings",
    "open_findings",
)
PLACEHOLDER_REVIEW_EVIDENCE_VALUES = {
    "na",
    "n/a",
    "none",
    "not applicable",
    "not supplied",
    "null",
    "required",
    "review required",
    "tbd",
    "todo",
    "unknown",
}
PLACEHOLDER_REVIEW_EVIDENCE_PREFIXES = (
    "fixme",
    "placeholder",
    "tbd",
    "todo",
    "unknown",
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
MODEL_SHA256_FIELDS = (
    "model_sha256",
    "model_file_sha256",
    "model_digest",
    "model_file_digest",
)
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
PROVENANCE_URL_FIELDS = {
    "source_url",
    "cad_url",
    "repository_url",
    "license_url",
}
PROVENANCE_FIXTURE_ONLY_MARKERS = (
    "synthetic",
    "hardware free",
    "hardware-free",
    "smoke",
    "test only",
    "test-only",
    "regression fixture",
    "automation only",
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
MESH_ASSET_REQUIRED_REVIEW_SCOPE_IDS = ("mesh_assets",)
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
TARGET_FRAME_REQUIRED_REVIEW_SCOPE_IDS = ("target_frame",)
TCP_OFFSET_REQUIRED_REVIEW_SCOPE_IDS = ("tcp_offset",)
ALIGNMENT_REQUIRED_REVIEW_SCOPE_IDS = ("base_to_board_alignment",)
SYNTHETIC_FIXTURE_ALIGNMENT_STATUS = "synthetic_fixture_reviewed_for_automation_only"
ALIGNMENT_PLACEHOLDER_FIELDS = (
    "base_to_board_alignment_placeholder",
    "alignment_placeholders",
)
MAX_TCP_OFFSET_NORM_M = 0.50
MAX_BASE_TO_BOARD_TRANSLATION_NORM_M = 2.00
MAX_BASE_TO_BOARD_ROTATION_ABS_RAD = math.tau
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
        "input": "model_sha256",
        "requirement": "Reviewed SHA-256 digest for the exact SO-101 model file referenced by model_path.",
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
NEXT_ACTION_ORDER = (
    "--manifest-path",
    "model_path",
    "model_sha256",
    "authority",
    "provenance",
    "asset_roots",
    "mesh_assets",
    "mesh_asset_authority",
    "joint_limits_deg",
    "joint_limit_authority",
    "target_frame",
    "target_frame_authority",
    "tcp_offset_m",
    "tcp_offset_authority",
    "base_to_board_transform",
    "base_to_board_alignment_authority",
    "non_blocking_contract_checker_result",
)
NEXT_ACTIONS = {
    "--manifest-path": {
        "action_id": "supply_reviewed_so101_model_bundle_manifest",
        "gate": "reviewed_model_authority",
        "title": "Supply a reviewed SO-101 model bundle manifest",
        "detail": "Create or provide the JSON manifest that declares the selected SO-101 model bundle.",
    },
    "model_path": {
        "action_id": "select_reviewed_so101_model_path",
        "gate": "reviewed_model_authority",
        "title": "Select the reviewed SO-101 URDF/MJCF model path",
        "detail": "Set manifest.model_path to the reviewed model file, resolved relative to the manifest directory or as an absolute path.",
    },
    "model_sha256": {
        "action_id": "record_reviewed_so101_model_file_sha256",
        "gate": "reviewed_model_authority",
        "title": "Record the reviewed SO-101 model file digest",
        "detail": "Set manifest.model_sha256 to the SHA-256 digest of the exact reviewed model file so path contents cannot drift silently.",
    },
    "authority": {
        "action_id": "record_reviewed_model_source_authority",
        "gate": "reviewed_model_authority",
        "title": "Record reviewed model source authority",
        "detail": "Fill authority with an accepted review status, reviewer identity, and a stable review artifact handle: review_id or review_url.",
    },
    "provenance": {
        "action_id": "record_model_provenance",
        "gate": "reviewed_model_authority",
        "title": "Record model provenance and license basis",
        "detail": "Fill provenance with source reference, export tool, and license basis before trusting the bundle.",
    },
    "asset_roots": {
        "action_id": "declare_model_asset_roots",
        "gate": "reviewed_model_authority",
        "title": "Declare repeatable model asset roots",
        "detail": "Set manifest.asset_roots, using an explicit empty list only when the model directory alone resolves meshes.",
    },
    "mesh_assets": {
        "action_id": "resolve_so101_mesh_assets",
        "gate": "reviewed_model_authority",
        "title": "Resolve SO-101 mesh assets",
        "detail": "Provide reviewed mesh roots/assets until the nested asset preflight has no missing or unresolved references.",
    },
    "mesh_asset_authority": {
        "action_id": "record_mesh_asset_authority",
        "gate": "reviewed_model_authority",
        "title": "Record reviewed mesh/asset-root authority",
        "detail": "Add mesh_asset_authority or an accepted mesh review field with review evidence.",
    },
    "joint_limits_deg": {
        "action_id": "declare_reviewed_joint_limits",
        "gate": "reviewed_model_authority",
        "title": "Declare reviewed SO-101 joint limits",
        "detail": "Provide numeric lower/upper limits for shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, and gripper.",
    },
    "joint_limit_authority": {
        "action_id": "record_joint_limit_authority",
        "gate": "reviewed_model_authority",
        "title": "Record reviewed joint-limit authority",
        "detail": "Add joint_limit_authority or an accepted joint-limit review field with review evidence.",
    },
    "target_frame": {
        "action_id": "declare_target_frame",
        "gate": "reviewed_model_authority",
        "title": "Declare the SO-101 target frame",
        "detail": "Set target_frame explicitly, normally gripper_frame_link for the current simulator contract.",
    },
    "target_frame_authority": {
        "action_id": "record_target_frame_authority",
        "gate": "reviewed_model_authority",
        "title": "Record reviewed target-frame authority",
        "detail": "Add target_frame_authority or an accepted TCP-frame review field proving the target frame is the intended gripper/TCP reference.",
    },
    "tcp_offset_m": {
        "action_id": "calibrate_tcp_offset",
        "gate": "reviewed_model_authority",
        "title": "Calibrate target-frame to TCP/gripper offset",
        "detail": "Provide tcp_offset_m or an accepted alias as x/y/z meters.",
    },
    "tcp_offset_authority": {
        "action_id": "record_tcp_offset_authority",
        "gate": "reviewed_model_authority",
        "title": "Record reviewed TCP/gripper offset authority",
        "detail": "Add tcp_offset_authority or an accepted TCP calibration review field with review evidence.",
    },
    "base_to_board_transform": {
        "action_id": "calibrate_base_to_board_transform",
        "gate": "reviewed_model_authority",
        "title": "Calibrate base-to-board transform",
        "detail": "Provide base_to_board_transform or base_to_board_alignment with translation and rotation fields.",
    },
    "base_to_board_alignment_authority": {
        "action_id": "record_base_to_board_alignment_authority",
        "gate": "reviewed_model_authority",
        "title": "Record reviewed base-to-board alignment authority",
        "detail": "Add base_to_board_alignment_authority or an accepted alignment review field with review evidence.",
    },
    "non_blocking_contract_checker_result": {
        "action_id": "clear_model_contract_and_asset_preflight",
        "gate": "mujoco_scene_validity",
        "title": "Clear model contract and asset preflight diagnostics",
        "detail": "Rerun the child SO-101 model contract checker until the static joint/frame contract and mesh asset preflight are non-blocking.",
    },
}
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
REVIEW_PACKET_FIELDNAMES = (
    "priority",
    "review_item_id",
    "gate",
    "status",
    "manifest_fields",
    "missing_inputs",
    "review_action_ids",
    "observed_evidence",
    "caveat",
)
BUNDLE_INTAKE_FIELDNAMES = (
    "priority",
    "action_id",
    "status",
    "gate",
    "title",
    "detail",
    "missing_input",
    "manifest_fields",
    "command",
    "required_inputs",
    "related_requirement_ids",
    "field_check_diagnostics",
    "field_check_context",
)
REVIEW_REQUIREMENTS_FIELDNAMES = (
    "priority",
    "requirement_id",
    "gate",
    "manifest_fields",
    "accepted_review_statuses",
    "required_review_scope_ids",
    "required_evidence_groups",
    "required_inputs",
    "placeholder_rule",
    "synthetic_fixture_status",
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


def unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in CSV_FIELDNAMES})


def write_review_packet_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_PACKET_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: csv_value(row.get(field)) for field in REVIEW_PACKET_FIELDNAMES}
            )


def write_bundle_intake_csv(path: Path, bundle_intake: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BUNDLE_INTAKE_FIELDNAMES)
        writer.writeheader()
        for action in bundle_intake.get("actions") or []:
            writer.writerow(
                {field: csv_value(action.get(field)) for field in BUNDLE_INTAKE_FIELDNAMES}
            )


def write_review_requirements_csv(path: Path, review_requirements: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_REQUIREMENTS_FIELDNAMES)
        writer.writeheader()
        for item in review_requirements.get("requirements") or []:
            writer.writerow(
                {
                    field: csv_value(item.get(field))
                    for field in REVIEW_REQUIREMENTS_FIELDNAMES
                }
            )


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


def normalized_review_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def placeholder_review_evidence(value: Any) -> bool:
    if not non_empty(value):
        return False
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    normalized = normalized_review_text(value)
    return normalized in PLACEHOLDER_REVIEW_EVIDENCE_VALUES or any(
        normalized.startswith(prefix) for prefix in PLACEHOLDER_REVIEW_EVIDENCE_PREFIXES
    )


def invalid_review_url(value: Any) -> bool:
    if not non_empty(value):
        return False
    if not isinstance(value, str):
        return True
    parsed = urlparse(value.strip())
    return parsed.scheme not in {"http", "https"} or not parsed.netloc


def invalid_reviewed_at(value: Any) -> bool:
    if not non_empty(value):
        return False
    if not isinstance(value, str):
        return True
    raw = value.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}($|[T ])", raw):
        return True
    try:
        parsed_date = date.fromisoformat(raw)
        return parsed_date > date.today()
    except ValueError:
        pass
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed_datetime = datetime.fromisoformat(normalized)
    except ValueError:
        return True
    now = (
        datetime.now(parsed_datetime.tzinfo)
        if parsed_datetime.tzinfo is not None
        else datetime.now()
    )
    return parsed_datetime > now


def invalid_review_evidence(field_name: str, value: Any) -> bool:
    if field_name == "reviewed_at":
        return invalid_reviewed_at(value)
    if field_name != "review_url":
        return False
    return invalid_review_url(value)


def invalid_provenance_url(field_name: str, value: Any) -> bool:
    if field_name not in PROVENANCE_URL_FIELDS:
        return False
    return invalid_review_url(value)


def normalized_review_scope_ids(value: Any) -> list[str]:
    if value is None:
        raw_values: list[Any] = []
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]

    seen: set[str] = set()
    normalized: list[str] = []
    for raw_value in raw_values:
        for raw_scope in str(raw_value).split(","):
            scope = raw_scope.strip().lower().replace("-", "_")
            if not scope or scope in seen:
                continue
            seen.add(scope)
            normalized.append(scope)
    return normalized


def mapping_review_scope_ids(mapping: dict[str, Any]) -> list[str]:
    for field_name in REVIEW_SCOPE_FIELDS:
        scopes = normalized_review_scope_ids(mapping.get(field_name))
        if scopes:
            return scopes
    return []


def fixture_only_provenance_evidence(value: Any) -> bool:
    if not non_empty(value):
        return False
    if not isinstance(value, str):
        return False
    normalized = normalized_review_text(value)
    return any(marker in normalized for marker in PROVENANCE_FIXTURE_ONLY_MARKERS)


def review_evidence_summary(
    value: dict[str, Any],
    field_names: tuple[str, ...] = AUTHORITY_REVIEW_FIELDS,
    required_review_scope_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    supplied_fields: list[str] = []
    valid_fields: list[str] = []
    placeholder_fields: list[str] = []
    invalid_fields: list[str] = []
    for field_name in field_names:
        field_value = value.get(field_name)
        if not non_empty(field_value):
            continue
        supplied_fields.append(field_name)
        if placeholder_review_evidence(field_value):
            placeholder_fields.append(field_name)
        elif invalid_review_evidence(field_name, field_value):
            invalid_fields.append(field_name)
        else:
            valid_fields.append(field_name)
    valid_field_set = set(valid_fields)
    required_groups = [
        {
            "group": group_name,
            "fields": [field for field in group_fields if field in field_names],
        }
        for group_name, group_fields in REVIEW_EVIDENCE_REQUIRED_GROUPS
    ]
    required_groups = [group for group in required_groups if group["fields"]]
    missing_required_groups = [
        group["group"]
        for group in required_groups
        if not any(field in valid_field_set for field in group["fields"])
    ]
    satisfied_required_groups = [
        group["group"]
        for group in required_groups
        if any(field in valid_field_set for field in group["fields"])
    ]
    supplied_review_scope_ids = mapping_review_scope_ids(value)
    missing_review_scope_ids = [
        scope_id
        for scope_id in required_review_scope_ids
        if scope_id not in supplied_review_scope_ids
    ]
    open_work_fields = [
        field_name
        for field_name in REVIEW_OPEN_WORK_FIELDS
        if non_empty(value.get(field_name))
    ]
    return {
        "supplied_fields": supplied_fields,
        "valid_fields": valid_fields,
        "placeholder_fields": placeholder_fields,
        "invalid_fields": invalid_fields,
        "open_work_fields": open_work_fields,
        "ready_has_open_work": bool(open_work_fields),
        "present": bool(valid_fields),
        "required_groups": required_groups,
        "satisfied_required_groups": satisfied_required_groups,
        "missing_required_groups": missing_required_groups,
        "required_review_scope_ids": list(required_review_scope_ids),
        "supplied_review_scope_ids": supplied_review_scope_ids,
        "missing_review_scope_ids": missing_review_scope_ids,
        "review_scope_descriptions": {
            scope_id: REVIEW_SCOPE_DESCRIPTIONS.get(scope_id, "")
            for scope_id in required_review_scope_ids
        },
        "review_scope_ready": not missing_review_scope_ids,
        "ok": (
            bool(valid_fields)
            and not placeholder_fields
            and not invalid_fields
            and not missing_required_groups
            and not missing_review_scope_ids
            and not open_work_fields
        ),
    }


def review_evidence_report_fields(review_evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_evidence_present": review_evidence["present"],
        "review_evidence_valid_fields": review_evidence["valid_fields"],
        "review_evidence_placeholder_fields": review_evidence["placeholder_fields"],
        "review_evidence_invalid_fields": review_evidence["invalid_fields"],
        "review_evidence_open_work_fields": review_evidence["open_work_fields"],
        "review_evidence_ready_has_open_work": review_evidence[
            "ready_has_open_work"
        ],
        "review_evidence_required_groups": review_evidence["required_groups"],
        "review_evidence_satisfied_required_groups": review_evidence[
            "satisfied_required_groups"
        ],
        "review_evidence_missing_required_groups": review_evidence[
            "missing_required_groups"
        ],
        "required_review_scope_ids": review_evidence["required_review_scope_ids"],
        "supplied_review_scope_ids": review_evidence["supplied_review_scope_ids"],
        "missing_review_scope_ids": review_evidence["missing_review_scope_ids"],
        "review_scope_descriptions": review_evidence["review_scope_descriptions"],
        "review_scope_ready": review_evidence["review_scope_ready"],
    }


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

    def reject_json_constant(value: str) -> None:
        raise ValueError(f"non_standard_json_constant:{value}")

    try:
        payload = json.loads(resolved.read_text(), parse_constant=reject_json_constant)
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
        non_finite_axes = [axis for axis, item in vector.items() if not math.isfinite(item)]
        if non_finite_axes:
            return {
                "present": True,
                "valid": False,
                "value": value,
                "diagnostics": [f"non_finite_axis:{axis}" for axis in non_finite_axes],
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
        non_finite_indexes = [
            index for index, item in enumerate(vector) if not math.isfinite(item)
        ]
        if non_finite_indexes:
            return {
                "present": True,
                "valid": False,
                "value": value,
                "diagnostics": [
                    f"non_finite_vector_index:{index}" for index in non_finite_indexes
                ],
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


def vector_components(value: Any, axes: tuple[str, str, str]) -> list[float] | None:
    if isinstance(value, dict):
        try:
            return [float(value[axis]) for axis in axes]
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, list) and len(value) == 3:
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return None
    return None


def vector3_components(value: Any) -> list[float] | None:
    return vector_components(value, ("x", "y", "z"))


def vectors_equivalent(
    left: list[float],
    right: list[float],
    *,
    abs_tol: float = 1e-9,
) -> bool:
    if len(left) != len(right):
        return False
    return all(
        math.isclose(left_item, right_item, rel_tol=0.0, abs_tol=abs_tol)
        for left_item, right_item in zip(left, right)
    )


def vector_norm(value: Any) -> float | None:
    if isinstance(value, dict):
        items = list(value.values())
    elif isinstance(value, list):
        items = value
    else:
        return None
    try:
        return math.sqrt(sum(float(item) ** 2 for item in items))
    except (TypeError, ValueError):
        return None


def find_first_field(manifest: dict[str, Any], field_names: tuple[str, ...]) -> tuple[str | None, Any]:
    for field_name in field_names:
        if field_name in manifest:
            return field_name, manifest[field_name]
    return None, None


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def inspect_model_path(manifest: dict[str, Any] | None, manifest_dir: Path | None) -> dict[str, Any]:
    if not manifest or not non_empty(manifest.get("model_path")):
        return {
            "status": "missing",
            "raw": None,
            "path": None,
            "exists": False,
            "is_file": False,
            "sha256": None,
            "diagnostics": ["model_path_missing"],
        }

    raw = str(manifest["model_path"])
    resolved = resolve_manifest_relative(raw, manifest_dir)
    exists = resolved.exists()
    is_file = resolved.is_file()
    diagnostics: list[str] = []
    if not exists:
        diagnostics.append("model_path_unavailable")
    elif not is_file:
        diagnostics.append("model_path_not_file")
    return {
        "status": "present" if is_file else "unavailable",
        "raw": raw,
        "path": str(resolved),
        "exists": exists,
        "is_file": is_file,
        "suffix": resolved.suffix.lower(),
        "sha256": sha256_file(resolved),
        "diagnostics": diagnostics,
    }


def normalize_sha256(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:").strip()
    if len(text) != 64:
        return None
    if any(char not in "0123456789abcdef" for char in text):
        return None
    return text


def inspect_model_identity(
    manifest: dict[str, Any] | None,
    model_path: dict[str, Any],
) -> dict[str, Any]:
    observed_sha256 = model_path.get("sha256")
    if not manifest:
        return {
            "status": "missing",
            "field": None,
            "declared_sha256": None,
            "observed_sha256": observed_sha256,
            "matches": False,
            "diagnostics": ["model_sha256_missing"],
        }

    digest_aliases = [
        (field_name, manifest.get(field_name))
        for field_name in MODEL_SHA256_FIELDS
        if non_empty(manifest.get(field_name))
    ]
    if not digest_aliases:
        return {
            "status": "missing",
            "field": None,
            "digest_aliases": [],
            "declared_sha256": None,
            "observed_sha256": observed_sha256,
            "matches": False,
            "diagnostics": ["model_sha256_missing"],
        }

    field, raw_value = digest_aliases[0]
    normalized_aliases = [
        {
            "field": alias_field,
            "raw_value": alias_raw_value,
            "normalized_sha256": normalize_sha256(alias_raw_value),
        }
        for alias_field, alias_raw_value in digest_aliases
    ]
    declared_sha256 = normalized_aliases[0]["normalized_sha256"]
    invalid_alias_fields = [
        alias["field"] for alias in normalized_aliases if alias["normalized_sha256"] is None
    ]
    normalized_values = sorted(
        {
            alias["normalized_sha256"]
            for alias in normalized_aliases
            if isinstance(alias["normalized_sha256"], str)
        }
    )
    diagnostics: list[str] = []
    if invalid_alias_fields:
        diagnostics.append("model_sha256_invalid")
        diagnostics.extend(
            f"model_sha256_alias_invalid:{alias_field}"
            for alias_field in invalid_alias_fields
        )
    if len(normalized_values) > 1:
        diagnostics.append("model_sha256_alias_conflict")
    if not observed_sha256:
        diagnostics.append("model_sha256_observed_unavailable")
    if declared_sha256 is not None and observed_sha256 and declared_sha256 != observed_sha256:
        diagnostics.append("model_sha256_mismatch")

    matches = (
        declared_sha256 is not None
        and bool(observed_sha256)
        and declared_sha256 == observed_sha256
        and not invalid_alias_fields
        and len(normalized_values) <= 1
    )
    return {
        "status": "present" if matches else "invalid",
        "field": field,
        "digest_aliases": normalized_aliases,
        "digest_alias_conflict": len(normalized_values) > 1,
        "declared_sha256": declared_sha256,
        "observed_sha256": observed_sha256,
        "matches": matches,
        "diagnostics": diagnostics,
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
    review_evidence = review_evidence_summary(
        value,
        required_review_scope_ids=AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS,
    )
    diagnostics: list[str] = []
    if not status_value:
        diagnostics.append("authority_review_status_missing")
    elif status_value not in REVIEWED_AUTHORITY_STATUSES and status_value != SYNTHETIC_FIXTURE_AUTHORITY_STATUS:
        diagnostics.append(f"authority_review_status_not_accepted:{status_value}")
    if not review_evidence["present"]:
        diagnostics.append("authority_review_evidence_missing")
    for group_name in review_evidence["missing_required_groups"]:
        diagnostics.append(f"authority_review_evidence_missing_required_group:{group_name}")
    for field_name in review_evidence["placeholder_fields"]:
        diagnostics.append(f"authority_review_evidence_placeholder:{field_name}")
    for field_name in review_evidence["invalid_fields"]:
        diagnostics.append(f"authority_review_evidence_invalid:{field_name}")
    for field_name in review_evidence["open_work_fields"]:
        diagnostics.append(f"authority_review_evidence_open_work:{field_name}")
    for scope_id in review_evidence["missing_review_scope_ids"]:
        diagnostics.append(f"authority_review_scope_missing:{scope_id}")

    is_synthetic_fixture = status_value == SYNTHETIC_FIXTURE_AUTHORITY_STATUS
    if is_synthetic_fixture and "hardware-free" not in str(value.get("scope", "")).lower():
        diagnostics.append("synthetic_fixture_scope_missing_hardware_free")

    review_status_ok = status_value in REVIEWED_AUTHORITY_STATUSES or (
        is_synthetic_fixture and "synthetic_fixture_scope_missing_hardware_free" not in diagnostics
    )
    status = "present" if review_status_ok and review_evidence["ok"] else "needs_review"
    return {
        "status": status,
        "value": value,
        "review_status_field": status_field,
        "review_status": status_value or None,
        **review_evidence_report_fields(review_evidence),
        "synthetic_fixture_only": is_synthetic_fixture,
        "diagnostics": diagnostics,
        "accepted_review_statuses": sorted(REVIEWED_AUTHORITY_STATUSES),
        "notes": (
            "Synthetic fixture authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 source authority."
            if is_synthetic_fixture
            else "Authority requires an accepted reviewed status, reviewer identity, a stable review artifact handle, and model_identity/provenance/license review scopes."
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

    def first_valid_provenance_field(
        field_names: tuple[str, ...],
    ) -> tuple[str | None, Any, list[str], list[str]]:
        placeholder_fields: list[str] = []
        invalid_fields: list[str] = []
        selected_field = None
        selected_value = None
        for field_name in field_names:
            field_value = value.get(field_name)
            if not non_empty(field_value):
                continue
            if placeholder_review_evidence(field_value):
                placeholder_fields.append(field_name)
                continue
            if invalid_provenance_url(field_name, field_value):
                invalid_fields.append(field_name)
                continue
            if selected_field is None:
                selected_field = field_name
                selected_value = field_value
        return selected_field, selected_value, placeholder_fields, invalid_fields

    (
        source_field,
        source_value,
        source_placeholder_fields,
        source_invalid_fields,
    ) = first_valid_provenance_field(PROVENANCE_SOURCE_FIELDS)
    (
        export_field,
        export_value,
        export_placeholder_fields,
        export_invalid_fields,
    ) = first_valid_provenance_field(PROVENANCE_EXPORT_FIELDS)
    (
        license_field,
        license_value,
        license_placeholder_fields,
        license_invalid_fields,
    ) = first_valid_provenance_field(PROVENANCE_LICENSE_FIELDS)
    blocking_diagnostics: list[str] = []
    diagnostics: list[str] = []
    fixture_only_fields: list[str] = []
    if source_field is None:
        blocking_diagnostics.append("provenance_source_reference_missing")
    if export_field is None:
        blocking_diagnostics.append("provenance_export_tool_missing")
    if license_field is None:
        blocking_diagnostics.append("provenance_license_basis_missing")
    for field_name, field_value in (
        (source_field, source_value),
        (export_field, export_value),
        (license_field, license_value),
    ):
        if field_name is not None and fixture_only_provenance_evidence(field_value):
            fixture_only_fields.append(field_name)
            diagnostics.append(f"provenance_fixture_only:{field_name}")
    for field_name in source_placeholder_fields:
        blocking_diagnostics.append(f"provenance_source_reference_placeholder:{field_name}")
    for field_name in export_placeholder_fields:
        blocking_diagnostics.append(f"provenance_export_tool_placeholder:{field_name}")
    for field_name in license_placeholder_fields:
        blocking_diagnostics.append(f"provenance_license_basis_placeholder:{field_name}")
    for field_name in source_invalid_fields:
        blocking_diagnostics.append(f"provenance_source_reference_invalid:{field_name}")
    for field_name in export_invalid_fields:
        blocking_diagnostics.append(f"provenance_export_tool_invalid:{field_name}")
    for field_name in license_invalid_fields:
        blocking_diagnostics.append(f"provenance_license_basis_invalid:{field_name}")
    diagnostics = [*blocking_diagnostics, *diagnostics]

    return {
        "status": "present" if not blocking_diagnostics else "needs_review",
        "value": value,
        "source_field": source_field,
        "source_value": source_value,
        "source_placeholder_fields": source_placeholder_fields,
        "source_invalid_fields": source_invalid_fields,
        "export_field": export_field,
        "export_value": export_value,
        "export_placeholder_fields": export_placeholder_fields,
        "export_invalid_fields": export_invalid_fields,
        "license_field": license_field,
        "license_value": license_value,
        "license_placeholder_fields": license_placeholder_fields,
        "license_invalid_fields": license_invalid_fields,
        "synthetic_fixture_only": bool(fixture_only_fields),
        "fixture_only_fields": fixture_only_fields,
        "blocking_diagnostics": blocking_diagnostics,
        "diagnostics": diagnostics,
        "required_field_groups": {
            "source": list(PROVENANCE_SOURCE_FIELDS),
            "export": list(PROVENANCE_EXPORT_FIELDS),
            "license": list(PROVENANCE_LICENSE_FIELDS),
        },
        "notes": (
            "Provenance requires source reference, export tool, and license basis fields. "
            "Placeholder values such as TODO/TBD/unknown or unedited <...> template tokens do not satisfy provenance readiness. "
            "Synthetic, test-only, smoke, or hardware-free provenance remains automation evidence only."
        ),
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
        if not math.isfinite(lower) or not math.isfinite(upper):
            return False, value, ["joint_limit_non_finite"]
        if lower >= upper:
            return False, {"lower": lower, "upper": upper}, ["joint_limit_lower_not_below_upper"]
        return True, {"lower": lower, "upper": upper}, []

    if isinstance(value, list) and len(value) == 2:
        try:
            lower = float(value[0])
            upper = float(value[1])
        except (TypeError, ValueError) as exc:
            return False, value, [f"joint_limit_non_numeric:{type(exc).__name__}"]
        if not math.isfinite(lower) or not math.isfinite(upper):
            return False, value, ["joint_limit_non_finite"]
        if lower >= upper:
            return False, [lower, upper], ["joint_limit_lower_not_below_upper"]
        return True, [lower, upper], []

    return False, value, ["joint_limit_expected_lower_upper_or_len2_list"]


def inspect_joint_limit_payload(value_payload: Any) -> dict[str, Any]:
    if not isinstance(value_payload, dict):
        return {
            "valid": False,
            "value": value_payload,
            "expected_joints": list(EXPECTED_SO101_JOINTS),
            "missing_joints": list(EXPECTED_SO101_JOINTS),
            "unexpected_joints": [],
            "invalid_joints": [],
            "diagnostics": ["joint_limits_not_object"],
        }

    normalized: dict[str, Any] = {}
    invalid_joints: list[dict[str, Any]] = []
    unexpected_joints = [
        str(joint)
        for joint in value_payload
        if str(joint) not in EXPECTED_SO101_JOINTS
    ]
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
    if unexpected_joints:
        diagnostics.extend(
            f"joint_limit_unexpected:{joint}" for joint in unexpected_joints
        )
    for invalid in invalid_joints:
        diagnostics.extend(
            f"joint_limit_invalid:{invalid['joint']}:{diagnostic}"
            for diagnostic in invalid["diagnostics"]
        )
    return {
        "valid": not missing_joints and not unexpected_joints and not invalid_joints,
        "value": normalized,
        "expected_joints": list(EXPECTED_SO101_JOINTS),
        "missing_joints": missing_joints,
        "unexpected_joints": unexpected_joints,
        "invalid_joints": invalid_joints,
        "diagnostics": diagnostics,
    }


def joint_limit_pair_components(value: Any) -> list[float] | None:
    if isinstance(value, dict):
        try:
            return [float(value["lower"]), float(value["upper"])]
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, list) and len(value) == 2:
        try:
            return [float(value[0]), float(value[1])]
        except (TypeError, ValueError):
            return None
    return None


def joint_limit_components(value: dict[str, Any]) -> list[float] | None:
    components: list[float] = []
    for joint in EXPECTED_SO101_JOINTS:
        pair = joint_limit_pair_components(value.get(joint))
        if pair is None:
            return None
        components.extend(pair)
    return components


def joint_limit_value_aliases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = []
    for field_name in JOINT_LIMIT_FIELDS:
        raw_value = manifest.get(field_name)
        if not non_empty(raw_value):
            continue
        if field_name == "joint_limit_authority":
            if not isinstance(raw_value, dict):
                continue
            nested_aliases = []
            for nested_field in JOINT_LIMIT_NESTED_VALUE_FIELDS:
                nested_value = raw_value.get(nested_field)
                if not non_empty(nested_value):
                    continue
                nested = inspect_joint_limit_payload(nested_value)
                nested_aliases.append(
                    {
                        "field": f"{field_name}.{nested_field}",
                        "value": nested["value"],
                        "valid": nested["valid"],
                        "missing_joints": nested["missing_joints"],
                        "unexpected_joints": nested["unexpected_joints"],
                        "invalid_joints": nested["invalid_joints"],
                        "diagnostics": nested["diagnostics"],
                    }
                )
            if not nested_aliases:
                continue
            invalid_nested_alias_fields = [
                alias["field"] for alias in nested_aliases if not alias["valid"]
            ]
            normalized_nested_aliases = []
            for alias in nested_aliases:
                components = joint_limit_components(alias["value"])
                if alias["valid"] and components is not None:
                    normalized_nested_aliases.append(components)
            unique_nested_aliases: list[list[float]] = []
            for components in normalized_nested_aliases:
                if not any(
                    vectors_equivalent(components, existing)
                    for existing in unique_nested_aliases
                ):
                    unique_nested_aliases.append(components)
            nested_alias_conflict = len(unique_nested_aliases) > 1
            selected = nested_aliases[0]
            diagnostics = list(selected["diagnostics"])
            if invalid_nested_alias_fields:
                diagnostics.extend(
                    f"joint_limit_nested_alias_invalid:{alias_field}"
                    for alias_field in invalid_nested_alias_fields
                )
            if nested_alias_conflict:
                diagnostics.append("joint_limit_nested_alias_conflict")
            aliases.append(
                {
                    "field": field_name,
                    "value_field": selected["field"],
                    "value": selected["value"],
                    "valid": bool(
                        selected["valid"]
                        and not invalid_nested_alias_fields
                        and not nested_alias_conflict
                    ),
                    "missing_joints": selected["missing_joints"],
                    "unexpected_joints": selected["unexpected_joints"],
                    "invalid_joints": selected["invalid_joints"],
                    "nested_aliases": nested_aliases,
                    "nested_alias_conflict": nested_alias_conflict,
                    "diagnostics": diagnostics,
                }
            )
            continue

        inspected = inspect_joint_limit_payload(raw_value)
        aliases.append(
            {
                "field": field_name,
                "value_field": field_name,
                "value": inspected["value"],
                "valid": inspected["valid"],
                "missing_joints": inspected["missing_joints"],
                "unexpected_joints": inspected["unexpected_joints"],
                "invalid_joints": inspected["invalid_joints"],
                "nested_aliases": [],
                "nested_alias_conflict": False,
                "diagnostics": inspected["diagnostics"],
            }
        )
    return aliases


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
        has_review = bool(review_evidence_summary(candidate_value)["supplied_fields"])
        if has_status or has_review:
            review_source = candidate_value
            review_source_field = candidate_field
            break

    if not isinstance(review_source, dict):
        review_evidence = review_evidence_summary(
            {},
            required_review_scope_ids=JOINT_LIMIT_REQUIRED_REVIEW_SCOPE_IDS,
        )
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "review_status": None,
            **review_evidence_report_fields(review_evidence),
            "synthetic_fixture_only": False,
            "accepted_review_statuses": sorted(REVIEWED_JOINT_LIMIT_STATUSES),
            "diagnostics": ["joint_limit_authority_review_missing"],
        }

    status_field, raw_status = first_non_empty_field(review_source, JOINT_LIMIT_STATUS_FIELDS)
    status_value = str(raw_status).strip().lower() if raw_status is not None else ""
    review_evidence = review_evidence_summary(
        review_source,
        required_review_scope_ids=JOINT_LIMIT_REQUIRED_REVIEW_SCOPE_IDS,
    )
    diagnostics: list[str] = []
    if not status_value:
        diagnostics.append("joint_limit_authority_review_status_missing")
    elif (
        status_value not in REVIEWED_JOINT_LIMIT_STATUSES
        and status_value != SYNTHETIC_FIXTURE_JOINT_LIMIT_STATUS
    ):
        diagnostics.append(f"joint_limit_authority_review_status_not_accepted:{status_value}")
    if not review_evidence["present"]:
        diagnostics.append("joint_limit_authority_review_evidence_missing")
    for group_name in review_evidence["missing_required_groups"]:
        diagnostics.append(
            f"joint_limit_authority_review_evidence_missing_required_group:{group_name}"
        )
    for field_name in review_evidence["placeholder_fields"]:
        diagnostics.append(f"joint_limit_authority_review_evidence_placeholder:{field_name}")
    for field_name in review_evidence["invalid_fields"]:
        diagnostics.append(f"joint_limit_authority_review_evidence_invalid:{field_name}")
    for field_name in review_evidence["open_work_fields"]:
        diagnostics.append(
            f"joint_limit_authority_review_evidence_open_work:{field_name}"
        )
    for scope_id in review_evidence["missing_review_scope_ids"]:
        diagnostics.append(f"joint_limit_authority_review_scope_missing:{scope_id}")

    is_synthetic_fixture = status_value == SYNTHETIC_FIXTURE_JOINT_LIMIT_STATUS
    if is_synthetic_fixture and "hardware-free" not in str(review_source.get("scope", "")).lower():
        diagnostics.append("synthetic_joint_limit_scope_missing_hardware_free")

    review_status_ok = status_value in REVIEWED_JOINT_LIMIT_STATUSES or (
        is_synthetic_fixture and "synthetic_joint_limit_scope_missing_hardware_free" not in diagnostics
    )
    return {
        "status": "present" if review_status_ok and review_evidence["ok"] else "needs_review",
        "field": review_source_field,
        "value": review_source,
        "review_status_field": status_field,
        "review_status": status_value or None,
        **review_evidence_report_fields(review_evidence),
        "synthetic_fixture_only": is_synthetic_fixture,
        "accepted_review_statuses": sorted(REVIEWED_JOINT_LIMIT_STATUSES),
        "diagnostics": diagnostics,
        "notes": (
            "Synthetic fixture joint-limit authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 joint-limit truth."
            if is_synthetic_fixture
            else "Joint-limit readiness requires accepted review status, reviewer identity, a stable review artifact handle, and the joint_limits review scope."
        ),
    }


def inspect_joint_limits(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "joint_limit_aliases": [],
            "joint_limit_alias_conflict": False,
            "expected_joints": list(EXPECTED_SO101_JOINTS),
            "missing_joints": list(EXPECTED_SO101_JOINTS),
            "unexpected_joints": [],
            "invalid_joints": [],
            "diagnostics": ["joint_limits_missing"],
        }

    aliases = joint_limit_value_aliases(manifest)
    if not aliases:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "joint_limit_aliases": [],
            "joint_limit_alias_conflict": False,
            "expected_joints": list(EXPECTED_SO101_JOINTS),
            "missing_joints": list(EXPECTED_SO101_JOINTS),
            "unexpected_joints": [],
            "invalid_joints": [],
            "diagnostics": ["joint_limits_missing"],
        }

    selected = aliases[0]
    field_name = selected["field"]
    value = manifest.get(field_name)
    value_field_name = selected["value_field"]
    normalized = selected["value"]
    missing_joints = list(selected["missing_joints"])
    unexpected_joints = list(selected["unexpected_joints"])
    invalid_joints = list(selected["invalid_joints"])
    diagnostics = list(selected["diagnostics"])
    invalid_alias_fields = [alias["field"] for alias in aliases if not alias["valid"]]
    if invalid_alias_fields:
        diagnostics.extend(
            f"joint_limits_alias_invalid:{alias_field}"
            for alias_field in invalid_alias_fields
        )
    normalized_aliases = []
    for alias in aliases:
        components = joint_limit_components(alias["value"])
        if alias["valid"] and components is not None:
            normalized_aliases.append(components)
    unique_aliases: list[list[float]] = []
    for components in normalized_aliases:
        if not any(
            vectors_equivalent(components, existing)
            for existing in unique_aliases
        ):
            unique_aliases.append(components)
    top_level_alias_conflict = len(unique_aliases) > 1
    nested_alias_conflict = any(
        bool(alias.get("nested_alias_conflict")) for alias in aliases
    )
    alias_conflict = top_level_alias_conflict or nested_alias_conflict
    if top_level_alias_conflict:
        diagnostics.append("joint_limits_alias_conflict")
    if nested_alias_conflict:
        diagnostics.append("joint_limit_nested_alias_conflict")
    review = inspect_joint_limit_review(manifest, field_name, value)
    value_valid = bool(
        selected["valid"]
        and not invalid_alias_fields
        and not alias_conflict
    )
    if value_valid and review["status"] != "present":
        diagnostics.extend(review.get("diagnostics", []))
    return {
        "status": "present" if not diagnostics else "needs_review" if value_valid else "invalid",
        "field": field_name,
        "value_field": value_field_name,
        "value": normalized,
        "joint_limit_aliases": aliases,
        "joint_limit_alias_conflict": alias_conflict,
        "top_level_joint_limit_alias_conflict": top_level_alias_conflict,
        "nested_joint_limit_alias_conflict": nested_alias_conflict,
        "review": review,
        "review_status": review.get("status"),
        "review_diagnostics": review.get("diagnostics", []),
        "expected_joints": list(EXPECTED_SO101_JOINTS),
        "missing_joints": missing_joints,
        "unexpected_joints": unexpected_joints,
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
        if raw != EXPECTED_TARGET_FRAME:
            status = "invalid"
        elif review["status"] == "present":
            status = "present"
        else:
            status = "needs_review"
        return {
            "status": status,
            "value": raw,
            "expected_value": EXPECTED_TARGET_FRAME,
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
    required_review_scope_ids: tuple[str, ...],
) -> dict[str, Any]:
    review_candidates: list[tuple[str, dict[str, Any]]] = []
    for candidate_field, candidate_value in candidates:
        if not isinstance(candidate_value, dict):
            continue
        has_status = has_any_non_empty_field(candidate_value, status_fields)
        has_review = bool(review_evidence_summary(candidate_value)["supplied_fields"])
        if has_status or has_review:
            review_candidates.append((candidate_field, candidate_value))

    if not review_candidates:
        review_evidence = review_evidence_summary(
            {},
            required_review_scope_ids=required_review_scope_ids,
        )
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "review_status": None,
            **review_evidence_report_fields(review_evidence),
            "synthetic_fixture_only": False,
            "accepted_review_statuses": sorted(accepted_statuses),
            "review_aliases": [],
            "review_alias_conflict": False,
            "review_alias_not_ready_fields": [],
            "diagnostics": [f"{diagnostic_prefix}_review_missing"],
        }

    reviews = []
    for candidate_field, candidate_value in review_candidates:
        status_field, raw_status = first_non_empty_field(candidate_value, status_fields)
        status_value = str(raw_status).strip().lower() if raw_status is not None else ""
        review_evidence = review_evidence_summary(
            candidate_value,
            required_review_scope_ids=required_review_scope_ids,
        )
        diagnostics: list[str] = []
        if not status_value:
            diagnostics.append(f"{diagnostic_prefix}_review_status_missing")
        elif status_value not in accepted_statuses and status_value != synthetic_status:
            diagnostics.append(
                f"{diagnostic_prefix}_review_status_not_accepted:{status_value}"
            )
        if not review_evidence["present"]:
            diagnostics.append(f"{diagnostic_prefix}_review_evidence_missing")
        for group_name in review_evidence["missing_required_groups"]:
            diagnostics.append(
                f"{diagnostic_prefix}_review_evidence_missing_required_group:{group_name}"
            )
        for field_name in review_evidence["placeholder_fields"]:
            diagnostics.append(
                f"{diagnostic_prefix}_review_evidence_placeholder:{field_name}"
            )
        for field_name in review_evidence["invalid_fields"]:
            diagnostics.append(
                f"{diagnostic_prefix}_review_evidence_invalid:{field_name}"
            )
        for field_name in review_evidence["open_work_fields"]:
            diagnostics.append(
                f"{diagnostic_prefix}_review_evidence_open_work:{field_name}"
            )
        for scope_id in review_evidence["missing_review_scope_ids"]:
            diagnostics.append(f"{diagnostic_prefix}_review_scope_missing:{scope_id}")

        is_synthetic_fixture = status_value == synthetic_status
        if (
            is_synthetic_fixture
            and "hardware-free" not in str(candidate_value.get("scope", "")).lower()
        ):
            diagnostics.append(synthetic_scope_diagnostic)

        review_status_ok = status_value in accepted_statuses or (
            is_synthetic_fixture and synthetic_scope_diagnostic not in diagnostics
        )
        reviews.append(
            {
                "status": (
                    "present"
                    if review_status_ok and review_evidence["ok"]
                    else "needs_review"
                ),
                "field": candidate_field,
                "value": candidate_value,
                "review_status_field": status_field,
                "review_status": status_value or None,
                **review_evidence_report_fields(review_evidence),
                "synthetic_fixture_only": is_synthetic_fixture,
                "accepted_review_statuses": sorted(accepted_statuses),
                "diagnostics": diagnostics,
                "notes": synthetic_note if is_synthetic_fixture else review_note,
            }
        )

    selected = reviews[0]
    diagnostics = list(selected["diagnostics"])
    alias_not_ready_fields = [
        review["field"] for review in reviews if review["status"] != "present"
    ]
    diagnostics.extend(
        f"{diagnostic_prefix}_review_alias_not_ready:{field_name}"
        for field_name in alias_not_ready_fields
    )
    ready_alias_kinds = {
        "synthetic" if review["synthetic_fixture_only"] else "reviewed"
        for review in reviews
        if review["status"] == "present"
    }
    alias_conflict = len(ready_alias_kinds) > 1
    if alias_conflict:
        diagnostics.append(f"{diagnostic_prefix}_review_alias_conflict")
    is_synthetic_fixture = any(review["synthetic_fixture_only"] for review in reviews)
    status = (
        "present"
        if selected["status"] == "present"
        and not alias_not_ready_fields
        and not alias_conflict
        else "needs_review"
    )
    return {
        **selected,
        "status": status,
        "synthetic_fixture_only": is_synthetic_fixture,
        "review_aliases": [
            {
                "field": review["field"],
                "status": review["status"],
                "review_status": review["review_status"],
                "synthetic_fixture_only": review["synthetic_fixture_only"],
                "diagnostics": review["diagnostics"],
            }
            for review in reviews
        ],
        "review_alias_conflict": alias_conflict,
        "review_alias_not_ready_fields": alias_not_ready_fields,
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
        review_note="TCP offset readiness requires accepted review status, reviewer identity, a stable review artifact handle, and the tcp_offset review scope.",
        required_review_scope_ids=TCP_OFFSET_REQUIRED_REVIEW_SCOPE_IDS,
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
        review_note="Target-frame readiness requires accepted review status, reviewer identity, a stable review artifact handle, and the target_frame review scope.",
        required_review_scope_ids=TARGET_FRAME_REQUIRED_REVIEW_SCOPE_IDS,
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
            "tcp_offset_aliases": [],
            "tcp_offset_alias_conflict": False,
            "diagnostics": ["tcp_offset_missing"],
        }
    field_name, value = find_first_field(manifest, TCP_OFFSET_FIELDS)
    if field_name is None:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "tcp_offset_aliases": [],
            "tcp_offset_alias_conflict": False,
            "diagnostics": ["tcp_offset_missing"],
        }
    alias_checks = []
    for alias_field in TCP_OFFSET_FIELDS:
        alias_value = manifest.get(alias_field)
        if not non_empty(alias_value):
            continue
        alias_vector = vector3_status(alias_value)
        alias_checks.append(
            {
                "field": alias_field,
                "value": alias_vector["value"],
                "valid": alias_vector["valid"],
                "diagnostics": alias_vector["diagnostics"],
            }
        )
    vector = vector3_status(value)
    review = inspect_tcp_offset_review(manifest, field_name, value)
    diagnostics = list(vector["diagnostics"])
    invalid_alias_fields = [
        alias["field"] for alias in alias_checks if not alias["valid"]
    ]
    if invalid_alias_fields:
        diagnostics.extend(
            f"tcp_offset_alias_invalid:{alias_field}"
            for alias_field in invalid_alias_fields
        )
    normalized_alias_vectors = []
    for alias in alias_checks:
        if not alias["valid"]:
            continue
        components = vector3_components(alias["value"])
        if components is not None:
            normalized_alias_vectors.append(components)
    unique_alias_vectors: list[list[float]] = []
    for components in normalized_alias_vectors:
        if not any(
            vectors_equivalent(components, existing)
            for existing in unique_alias_vectors
        ):
            unique_alias_vectors.append(components)
    alias_conflict = len(unique_alias_vectors) > 1
    if alias_conflict:
        diagnostics.append("tcp_offset_alias_conflict")
    norm_m = vector_norm(vector["value"]) if vector["valid"] else None
    if norm_m is not None and norm_m > MAX_TCP_OFFSET_NORM_M:
        diagnostics.append(
            f"tcp_offset_norm_exceeds_limit:{norm_m:.6g}>{MAX_TCP_OFFSET_NORM_M:.6g}"
        )
    value_valid = bool(vector["valid"] and not any(
        diagnostic.startswith("tcp_offset_norm_exceeds_limit")
        for diagnostic in diagnostics
    ) and not invalid_alias_fields and not alias_conflict)
    if value_valid and review["status"] != "present":
        diagnostics.extend(review.get("diagnostics", []))
    return {
        "status": "present" if not diagnostics else "needs_review" if value_valid else "invalid",
        "field": field_name,
        "value": vector["value"],
        "tcp_offset_aliases": alias_checks,
        "tcp_offset_alias_conflict": alias_conflict,
        "norm_m": norm_m,
        "max_norm_m": MAX_TCP_OFFSET_NORM_M,
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
            "translation_alias_conflict": False,
            "rotation_alias_conflict": False,
            "alias_conflict": False,
            "diagnostics": ["base_to_board_transform_not_object"],
        }

    translation_fields = ("translation_m", "translation", "position_m")
    rotation_fields = ("rotation_rpy_rad", "rotation_rpy", "rpy_rad")
    translation_field, translation_value = find_first_field(
        value,
        translation_fields,
    )
    rotation_field, rotation_value = find_first_field(
        value,
        rotation_fields,
    )
    diagnostics: list[str] = []
    normalized: dict[str, Any] = {}
    if translation_field is None:
        diagnostics.append("base_to_board_translation_missing")
    else:
        translation_aliases = []
        for alias_field in translation_fields:
            alias_value = value.get(alias_field)
            if not non_empty(alias_value):
                continue
            alias_vector = vector3_status(alias_value)
            translation_aliases.append(
                {
                    "field": alias_field,
                    "value": alias_vector["value"],
                    "valid": alias_vector["valid"],
                    "diagnostics": alias_vector["diagnostics"],
                }
            )
        translation = vector3_status(translation_value)
        translation_norm_m = vector_norm(translation["value"]) if translation["valid"] else None
        invalid_translation_alias_fields = [
            alias["field"] for alias in translation_aliases if not alias["valid"]
        ]
        if invalid_translation_alias_fields:
            diagnostics.extend(
                f"translation:base_to_board_translation_alias_invalid:{alias_field}"
                for alias_field in invalid_translation_alias_fields
            )
        normalized_translation_vectors = []
        for alias in translation_aliases:
            if not alias["valid"]:
                continue
            components = vector3_components(alias["value"])
            if components is not None:
                normalized_translation_vectors.append(components)
        unique_translation_vectors: list[list[float]] = []
        for components in normalized_translation_vectors:
            if not any(
                vectors_equivalent(components, existing)
                for existing in unique_translation_vectors
            ):
                unique_translation_vectors.append(components)
        translation_alias_conflict = len(unique_translation_vectors) > 1
        if translation_alias_conflict:
            diagnostics.append("translation:base_to_board_translation_alias_conflict")
        normalized["translation"] = {
            "field": translation_field,
            "value": translation["value"],
            "aliases": translation_aliases,
            "alias_conflict": translation_alias_conflict,
            "norm_m": translation_norm_m,
            "max_norm_m": MAX_BASE_TO_BOARD_TRANSLATION_NORM_M,
        }
        diagnostics.extend(f"translation:{diagnostic}" for diagnostic in translation["diagnostics"])
        if (
            translation_norm_m is not None
            and translation_norm_m > MAX_BASE_TO_BOARD_TRANSLATION_NORM_M
        ):
            diagnostics.append(
                "translation:base_to_board_translation_norm_exceeds_limit:"
                f"{translation_norm_m:.6g}>{MAX_BASE_TO_BOARD_TRANSLATION_NORM_M:.6g}"
            )
    translation_alias_conflict = bool(
        (normalized.get("translation") or {}).get("alias_conflict")
    )
    if rotation_field is None:
        diagnostics.append("base_to_board_rotation_rpy_missing")
    else:
        rotation_aliases = []
        for alias_field in rotation_fields:
            alias_value = value.get(alias_field)
            if not non_empty(alias_value):
                continue
            alias_vector = vector_status(alias_value, ("roll", "pitch", "yaw"))
            rotation_aliases.append(
                {
                    "field": alias_field,
                    "value": alias_vector["value"],
                    "valid": alias_vector["valid"],
                    "diagnostics": alias_vector["diagnostics"],
                }
            )
        rotation = vector_status(rotation_value, ("roll", "pitch", "yaw"))
        rotation_components = (
            vector_components(rotation["value"], ("roll", "pitch", "yaw"))
            if rotation["valid"]
            else None
        )
        rotation_max_abs_rad = (
            max(abs(component) for component in rotation_components)
            if rotation_components is not None
            else None
        )
        invalid_rotation_alias_fields = [
            alias["field"] for alias in rotation_aliases if not alias["valid"]
        ]
        if invalid_rotation_alias_fields:
            diagnostics.extend(
                f"rotation_rpy:base_to_board_rotation_alias_invalid:{alias_field}"
                for alias_field in invalid_rotation_alias_fields
            )
        normalized_rotation_vectors = []
        for alias in rotation_aliases:
            if not alias["valid"]:
                continue
            components = vector_components(alias["value"], ("roll", "pitch", "yaw"))
            if components is not None:
                normalized_rotation_vectors.append(components)
        unique_rotation_vectors: list[list[float]] = []
        for components in normalized_rotation_vectors:
            if not any(
                vectors_equivalent(components, existing)
                for existing in unique_rotation_vectors
            ):
                unique_rotation_vectors.append(components)
        rotation_alias_conflict = len(unique_rotation_vectors) > 1
        if rotation_alias_conflict:
            diagnostics.append("rotation_rpy:base_to_board_rotation_alias_conflict")
        normalized["rotation_rpy"] = {
            "field": rotation_field,
            "value": rotation["value"],
            "aliases": rotation_aliases,
            "alias_conflict": rotation_alias_conflict,
            "max_abs_rad": rotation_max_abs_rad,
            "max_allowed_abs_rad": MAX_BASE_TO_BOARD_ROTATION_ABS_RAD,
        }
        diagnostics.extend(f"rotation_rpy:{diagnostic}" for diagnostic in rotation["diagnostics"])
        if (
            rotation_max_abs_rad is not None
            and rotation_max_abs_rad > MAX_BASE_TO_BOARD_ROTATION_ABS_RAD
        ):
            diagnostics.append(
                "rotation_rpy:base_to_board_rotation_abs_exceeds_limit:"
                f"{rotation_max_abs_rad:.6g}>{MAX_BASE_TO_BOARD_ROTATION_ABS_RAD:.6g}"
            )
    rotation_alias_conflict = bool(
        (normalized.get("rotation_rpy") or {}).get("alias_conflict")
    )
    return {
        "valid": not diagnostics,
        "value": normalized if normalized else value,
        "translation_alias_conflict": translation_alias_conflict,
        "rotation_alias_conflict": rotation_alias_conflict,
        "alias_conflict": translation_alias_conflict or rotation_alias_conflict,
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
        review_note="Base-to-board alignment readiness requires accepted review status, reviewer identity, a stable review artifact handle, and the base_to_board_alignment review scope.",
        required_review_scope_ids=ALIGNMENT_REQUIRED_REVIEW_SCOPE_IDS,
    )


def alignment_transform_components(transform: dict[str, Any]) -> list[float] | None:
    if not transform.get("valid"):
        return None
    value = transform.get("value")
    if not isinstance(value, dict):
        return None
    translation_value = (value.get("translation") or {}).get("value")
    rotation_value = (value.get("rotation_rpy") or {}).get("value")
    translation = vector3_components(translation_value)
    rotation = vector_components(rotation_value, ("roll", "pitch", "yaw"))
    if translation is None or rotation is None:
        return None
    return translation + rotation


def inspect_alignment(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "alignment_aliases": [],
            "alignment_alias_conflict": False,
            "placeholder_field": None,
            "placeholder_value": None,
            "diagnostics": ["base_to_board_transform_missing"],
        }

    alignment_aliases = []
    for alias_field in ALIGNMENT_FIELDS:
        alias_value = manifest.get(alias_field)
        if not non_empty(alias_value):
            continue
        alias_transform = alignment_transform_status(alias_value)
        alignment_aliases.append(
            {
                "field": alias_field,
                "valid": alias_transform["valid"],
                "value": alias_transform["value"],
                "alias_conflict": alias_transform.get("alias_conflict", False),
                "diagnostics": alias_transform["diagnostics"],
            }
        )
    if alignment_aliases:
        field_name = alignment_aliases[0]["field"]
        value = manifest.get(field_name)
        transform = alignment_transform_status(value)
        review = inspect_alignment_review(manifest, field_name, value)
        diagnostics = list(transform["diagnostics"])
        invalid_alias_fields = [
            alias["field"] for alias in alignment_aliases if not alias["valid"]
        ]
        if invalid_alias_fields:
            diagnostics.extend(
                f"base_to_board_alignment_alias_invalid:{alias_field}"
                for alias_field in invalid_alias_fields
            )
        normalized_alias_transforms = []
        for alias in alignment_aliases:
            components = alignment_transform_components(alias)
            if components is not None:
                normalized_alias_transforms.append(components)
        unique_alias_transforms: list[list[float]] = []
        for components in normalized_alias_transforms:
            if not any(
                vectors_equivalent(components, existing)
                for existing in unique_alias_transforms
            ):
                unique_alias_transforms.append(components)
        top_level_alias_conflict = len(unique_alias_transforms) > 1
        nested_alias_conflict = any(
            bool(alias.get("alias_conflict")) for alias in alignment_aliases
        )
        alias_conflict = top_level_alias_conflict or nested_alias_conflict
        if top_level_alias_conflict:
            diagnostics.append("base_to_board_alignment_alias_conflict")
        value_valid = bool(transform["valid"] and not invalid_alias_fields and not alias_conflict)
        if value_valid and review["status"] != "present":
            diagnostics.extend(review.get("diagnostics", []))
        return {
            "status": "present" if not diagnostics else "needs_review" if value_valid else "invalid",
            "field": field_name,
            "value": value,
            "transform": transform,
            "alignment_aliases": alignment_aliases,
            "alignment_alias_conflict": alias_conflict,
            "top_level_alignment_alias_conflict": top_level_alias_conflict,
            "nested_alignment_alias_conflict": nested_alias_conflict,
            "review": review,
            "review_status": review.get("status"),
            "review_diagnostics": review.get("diagnostics", []),
            "placeholder_field": None,
            "placeholder_value": None,
            "diagnostics": diagnostics,
        }

    field_name, value = find_first_field(manifest, ALIGNMENT_FIELDS)
    placeholder_field, placeholder_value = find_first_field(manifest, ALIGNMENT_PLACEHOLDER_FIELDS)
    if placeholder_field is not None and non_empty(placeholder_value):
        return {
            "status": "placeholder_only",
            "field": None,
            "value": None,
            "alignment_aliases": [],
            "alignment_alias_conflict": False,
            "placeholder_field": placeholder_field,
            "placeholder_value": placeholder_value,
            "diagnostics": ["alignment_placeholder_declared_without_transform"],
        }

    return {
        "status": "missing",
        "field": None,
        "value": value,
        "alignment_aliases": [],
        "alignment_alias_conflict": False,
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


def inspect_single_mesh_asset_review(
    field_name: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    return inspect_review_metadata(
        [(field_name, value)],
        status_fields=MESH_ASSET_STATUS_FIELDS,
        accepted_statuses=REVIEWED_MESH_ASSET_STATUSES,
        synthetic_status=SYNTHETIC_FIXTURE_MESH_ASSET_STATUS,
        diagnostic_prefix="mesh_asset_authority",
        synthetic_scope_diagnostic="synthetic_mesh_asset_scope_missing_hardware_free",
        synthetic_note=(
            "Synthetic fixture mesh-asset authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 mesh truth."
        ),
        review_note="Mesh readiness requires accepted review status, reviewer identity, a stable review artifact handle, and the mesh_assets review scope.",
        required_review_scope_ids=MESH_ASSET_REQUIRED_REVIEW_SCOPE_IDS,
    )


def mesh_asset_review_aliases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = []
    for review_field in MESH_ASSET_REVIEW_FIELDS:
        candidate = manifest.get(review_field)
        if not isinstance(candidate, dict):
            continue
        has_status = has_any_non_empty_field(candidate, MESH_ASSET_STATUS_FIELDS)
        has_review = bool(review_evidence_summary(candidate)["supplied_fields"])
        if not has_status and not has_review:
            continue
        review = inspect_single_mesh_asset_review(review_field, candidate)
        aliases.append(
            {
                "field": review_field,
                "status": review["status"],
                "review_status": review["review_status"],
                "synthetic_fixture_only": review["synthetic_fixture_only"],
                "diagnostics": review["diagnostics"],
            }
        )
    return aliases


def inspect_mesh_asset_review(manifest: dict[str, Any] | None) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {}
    aliases = mesh_asset_review_aliases(manifest)
    if not aliases:
        review_evidence = review_evidence_summary(
            {},
            required_review_scope_ids=MESH_ASSET_REQUIRED_REVIEW_SCOPE_IDS,
        )
        return {
            "status": "missing",
            "field": None,
            "value": None,
            "review_status": None,
            **review_evidence_report_fields(review_evidence),
            "synthetic_fixture_only": False,
            "accepted_review_statuses": sorted(REVIEWED_MESH_ASSET_STATUSES),
            "mesh_asset_review_aliases": [],
            "mesh_asset_review_alias_conflict": False,
            "mesh_asset_review_alias_not_ready_fields": [],
            "diagnostics": ["mesh_asset_authority_review_missing"],
        }

    review_source_field = aliases[0]["field"]
    review_source = manifest[review_source_field]
    selected = inspect_single_mesh_asset_review(review_source_field, review_source)
    diagnostics = list(selected["diagnostics"])
    alias_not_ready_fields = [
        alias["field"] for alias in aliases if alias["status"] != "present"
    ]
    diagnostics.extend(
        f"mesh_asset_authority_review_alias_not_ready:{field_name}"
        for field_name in alias_not_ready_fields
    )
    ready_alias_kinds = {
        "synthetic" if alias["synthetic_fixture_only"] else "reviewed"
        for alias in aliases
        if alias["status"] == "present"
    }
    alias_conflict = len(ready_alias_kinds) > 1
    if alias_conflict:
        diagnostics.append("mesh_asset_authority_review_alias_conflict")
    is_synthetic_fixture = any(alias["synthetic_fixture_only"] for alias in aliases)
    status = (
        "present"
        if selected["status"] == "present"
        and not alias_not_ready_fields
        and not alias_conflict
        else "needs_review"
    )
    return {
        **selected,
        "status": status,
        "field": review_source_field,
        "value": review_source,
        "synthetic_fixture_only": is_synthetic_fixture,
        "mesh_asset_review_aliases": aliases,
        "mesh_asset_review_alias_conflict": alias_conflict,
        "mesh_asset_review_alias_not_ready_fields": alias_not_ready_fields,
        "diagnostics": diagnostics,
        "notes": (
            "Synthetic fixture mesh-asset authority is accepted only for hardware-free forwarding regression fixtures; "
            "it is not physical SO-101 mesh truth."
            if is_synthetic_fixture
            else "Mesh readiness requires accepted review status, reviewer identity, a stable review artifact handle, and the mesh_assets review scope."
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
    model_identity: dict[str, Any],
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
            "requirement_id": "model_sha256",
            "ok": model_identity["status"] == "present",
            "missing_inputs": None if model_identity["status"] == "present" else ["model_sha256"],
            "diagnostics": model_identity.get("diagnostics", []),
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


def synthetic_fixture_authority_flags(
    authority: dict[str, Any],
    provenance: dict[str, Any],
    joint_limits: dict[str, Any],
    mesh_assets: dict[str, Any],
    target_frame: dict[str, Any],
    tcp_offset: dict[str, Any],
    alignment: dict[str, Any],
) -> dict[str, bool]:
    return {
        "authority": bool(authority.get("synthetic_fixture_only")),
        "provenance": bool(provenance.get("synthetic_fixture_only")),
        "joint_limits": bool((joint_limits.get("review") or {}).get("synthetic_fixture_only")),
        "mesh_assets": bool((mesh_assets.get("review") or {}).get("synthetic_fixture_only")),
        "target_frame": bool((target_frame.get("review") or {}).get("synthetic_fixture_only")),
        "tcp_offset": bool((tcp_offset.get("review") or {}).get("synthetic_fixture_only")),
        "base_to_board_alignment": bool((alignment.get("review") or {}).get("synthetic_fixture_only")),
    }


def model_authority_class(ready: bool, synthetic_flags: dict[str, bool]) -> str:
    if any(synthetic_flags.values()):
        if ready:
            return "hardware_free_regression_fixture_not_physical_so101_authority"
        return "incomplete_hardware_free_regression_fixture_not_physical_so101_authority"
    if ready:
        return "reviewed_so101_model_bundle_manifest"
    return "reviewed_bundle_required"


def physical_authority_gate_status(ready: bool, physical_authority_ready: bool, synthetic_fields: list[str]) -> str:
    if physical_authority_ready:
        return "physical_reviewed_authority_ready"
    if ready and synthetic_fields:
        return "hardware_free_fixture_ready_not_physical_authority"
    return "physical_reviewed_authority_blocked"


def build_next_required_for_goal(missing_inputs: list[str]) -> list[dict[str, Any]]:
    missing_set = set(missing_inputs)
    ordered_inputs = [item for item in NEXT_ACTION_ORDER if item in missing_set]
    ordered_inputs.extend(sorted(missing_set.difference(ordered_inputs)))

    actions: list[dict[str, Any]] = []
    for index, missing_input in enumerate(ordered_inputs, start=1):
        safe_input = missing_input.strip("-").replace("-", "_")
        template = NEXT_ACTIONS.get(
            missing_input,
            {
                "action_id": f"resolve_{safe_input}",
                "gate": "reviewed_model_authority",
                "title": f"Resolve missing input: {missing_input}",
                "detail": "Fill or review this manifest input, then rerun the checker.",
            },
        )
        actions.append(
            {
                "priority": index,
                "missing_input": missing_input,
                **template,
            }
        )
    return actions


def build_physical_authority_blockers(
    next_required_for_goal: list[dict[str, Any]],
    synthetic_fields: list[str],
) -> list[str]:
    blockers: list[str] = []
    for action in next_required_for_goal:
        action_id = action.get("action_id")
        if isinstance(action_id, str) and action_id:
            blockers.append(action_id)
    blockers.extend(
        f"synthetic_fixture_authority_not_physical_so101:{field}"
        for field in synthetic_fields
    )
    return blockers


def review_packet_status(summary: dict[str, Any]) -> str:
    if summary["manifest_request"]["status"] != "model_bundle_manifest_loaded":
        return "review_packet_waiting_for_manifest"
    if summary["physical_so101_model_authority_ready"] is True:
        return "review_packet_physical_authority_ready"
    if summary["hardware_free_regression_fixture_ready"] is True:
        return "review_packet_hardware_free_fixture_ready_not_physical_authority"
    return "review_packet_manifest_needs_operator_review"


def review_packet_manifest_fields(row_value: dict[str, Any]) -> list[str]:
    requirement_id = row_value["requirement_id"]
    if requirement_id == "manifest_path":
        return ["--manifest-path"]
    if requirement_id == "model_path":
        return ["model_path"]
    if requirement_id == "model_sha256":
        return list(MODEL_SHA256_FIELDS)
    if requirement_id == "asset_roots":
        return ["asset_roots"]
    if requirement_id == "authority":
        return ["authority"]
    if requirement_id == "provenance":
        return ["provenance"]
    if requirement_id == "joint_limits_deg":
        return list(JOINT_LIMIT_FIELDS + JOINT_LIMIT_REVIEW_FIELDS)
    if requirement_id == "mesh_assets":
        return ["asset_roots", *MESH_ASSET_REVIEW_FIELDS]
    if requirement_id == "target_frame":
        return ["target_frame", *TARGET_FRAME_REVIEW_FIELDS]
    if requirement_id == "tcp_offset_m":
        return list(TCP_OFFSET_FIELDS + TCP_OFFSET_REVIEW_FIELDS)
    if requirement_id == "base_to_board_transform":
        return list(ALIGNMENT_FIELDS + ALIGNMENT_REVIEW_FIELDS)
    if requirement_id == "contract_checker_result":
        return ["model_path", "asset_roots", "target_frame"]
    if requirement_id == "model_backed_ik_readiness":
        return ["ready_for_model_backed_ik"]
    return [requirement_id]


def review_packet_action_map(next_required_for_goal: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    action_map: dict[str, list[dict[str, Any]]] = {}
    for action in next_required_for_goal:
        missing_input = action.get("missing_input")
        if not isinstance(missing_input, str) or not missing_input:
            continue
        action_map.setdefault(missing_input, []).append(action)
    return action_map


def review_packet_row(
    priority: int,
    row_value: dict[str, Any],
    action_map: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    missing_inputs = row_value.get("missing_inputs")
    missing_inputs = missing_inputs if isinstance(missing_inputs, list) else []
    actions = [
        action
        for missing_input in missing_inputs
        for action in action_map.get(str(missing_input), [])
    ]
    first_missing_input = str(missing_inputs[0]) if missing_inputs else ""
    return {
        "priority": priority,
        "review_item_id": row_value["requirement_id"],
        "gate": NEXT_ACTIONS.get(first_missing_input, {}).get(
            "gate",
            "reviewed_model_authority"
            if row_value["requirement_id"] != "contract_checker_result"
            else "mujoco_scene_validity",
        ),
        "status": "reviewed_or_machine_ready"
        if row_value["status"] == "ok"
        else "needs_operator_review",
        "manifest_fields": review_packet_manifest_fields(row_value),
        "missing_inputs": missing_inputs,
        "review_action_ids": [
            action["action_id"]
            for action in actions
            if isinstance(action.get("action_id"), str) and action["action_id"]
        ],
        "observed_evidence": {
            "category": row_value.get("category"),
            "check_status": row_value.get("status"),
            "observed_value": row_value.get("observed_value"),
            "expected_value": row_value.get("expected_value"),
            "diagnostics": row_value.get("diagnostics"),
            "source": row_value.get("source"),
        },
        "caveat": (
            "This item is machine-checked review evidence only. It does not create physical "
            "SO-101 authority unless the manifest checker reports physical_so101_model_authority_ready true."
        ),
    }


def build_review_packet(
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    action_map = review_packet_action_map(summary["next_required_for_goal"])
    packet_rows = [
        review_packet_row(index, row_value, action_map)
        for index, row_value in enumerate(rows, start=1)
    ]
    row_action_ids = {
        action_id
        for row_value in packet_rows
        for action_id in row_value["review_action_ids"]
    }
    review_action_ids = [
        action["action_id"]
        for action in summary["next_required_for_goal"]
        if action.get("action_id") in row_action_ids
    ]
    packet = {
        "schema": REVIEW_PACKET_SCHEMA,
        "ok": True,
        "status": review_packet_status(summary),
        "model_authority": "review_packet_not_authority",
        "manifest_path": summary["manifest_request"]["path"],
        "manifest_status": summary["status"],
        "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
        "physical_so101_model_authority_ready": summary["physical_so101_model_authority_ready"],
        "hardware_free_regression_fixture_ready": summary["hardware_free_regression_fixture_ready"],
        "physical_authority_blockers": summary["physical_authority_blockers"],
        "synthetic_fixture_authority_fields": summary["synthetic_fixture_authority_fields"],
        "review_item_count": len(packet_rows),
        "review_item_ids": [row_value["review_item_id"] for row_value in packet_rows],
        "needs_operator_review_item_ids": [
            row_value["review_item_id"]
            for row_value in packet_rows
            if row_value["status"] == "needs_operator_review"
        ],
        "review_action_ids": review_action_ids,
        "review_items": packet_rows,
        "observed_evidence_is_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "notes": [
            "The packet is derived from the manifest checker's current field checks.",
            "It is an operator review aid and not a reviewed model bundle.",
            "Synthetic fixture readiness remains explicitly non-physical SO-101 authority.",
        ],
    }
    return packet, packet_rows


def bundle_intake_status(summary: dict[str, Any]) -> str:
    if summary.get("physical_so101_model_authority_ready") is True:
        return "physical_bundle_authority_ready"
    if summary.get("hardware_free_regression_fixture_ready") is True:
        return "fixture_bundle_ready_not_physical_authority"
    manifest_request = summary.get("manifest_request")
    manifest_request = manifest_request if isinstance(manifest_request, dict) else {}
    if manifest_request.get("status") != "model_bundle_manifest_loaded":
        return "manifest_required"
    return "bundle_review_required"


def bundle_intake_manifest_fields(missing_input: str) -> list[str]:
    if missing_input == "--manifest-path":
        return ["--manifest-path"]
    if missing_input == "non_blocking_contract_checker_result":
        return ["model_path", "asset_roots", "target_frame"]
    return review_packet_manifest_fields({"requirement_id": missing_input})


def bundle_intake_required_inputs(missing_input: str) -> list[str]:
    fields = bundle_intake_manifest_fields(missing_input)
    if missing_input == "authority":
        fields.extend(["authority.reviewed_by", "authority.review_id|authority.review_url"])
    elif missing_input == "provenance":
        fields.extend(["provenance.source_reference", "provenance.license_basis"])
    elif missing_input in {
        "joint_limit_authority",
        "mesh_asset_authority",
        "target_frame_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    }:
        fields.extend(["reviewed_by", "review_id|review_url", "review_scope"])
    elif missing_input == "non_blocking_contract_checker_result":
        fields.extend(
            [
                "contract checker non-blocking",
                "SO-101 joints visible",
                "target frame visible",
                "mesh asset preflight non-blocking",
            ]
        )
    return unique_strings(fields)


def bundle_intake_field_check_context(
    summary: dict[str, Any],
    missing_input: str,
) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for check in summary.get("field_checks") or []:
        if not isinstance(check, dict):
            continue
        missing_inputs = check.get("missing_inputs")
        missing_inputs = missing_inputs if isinstance(missing_inputs, list) else []
        if missing_input not in missing_inputs:
            continue
        context.append(
            {
                "requirement_id": check.get("requirement_id"),
                "ok": check.get("ok"),
                "missing_inputs": missing_inputs,
                "diagnostics": check.get("diagnostics") or [],
            }
        )
    return context


def bundle_intake_related_requirement_ids(
    field_check_context: list[dict[str, Any]],
) -> list[str]:
    return unique_strings(
        [
            str(check["requirement_id"])
            for check in field_check_context
            if isinstance(check.get("requirement_id"), str)
            and check["requirement_id"]
        ]
    )


def bundle_intake_field_check_diagnostics(
    field_check_context: list[dict[str, Any]],
) -> list[Any]:
    diagnostics: list[Any] = []
    seen: set[str] = set()
    for check in field_check_context:
        for diagnostic in check.get("diagnostics") or []:
            key = json.dumps(diagnostic, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            diagnostics.append(diagnostic)
    return diagnostics


def bundle_intake_command_template(action_id: str) -> list[str]:
    output_dir = DEFAULT_OUTPUT_DIR.parent / "so101_model_bundle_manifest_reviewed"
    return [
        sys.executable,
        "scripts/smoke_sim_so101_model_bundle_manifest.py",
        "--manifest-path",
        "<reviewed-so101-model-bundle.json>",
        "--output-dir",
        str(output_dir),
    ]


def review_requirement_item(
    *,
    priority: int,
    requirement_id: str,
    gate: str,
    manifest_fields: list[str],
    accepted_review_statuses: list[str] | None = None,
    required_review_scope_ids: list[str] | None = None,
    required_inputs: list[str] | None = None,
    synthetic_fixture_status: str | None = None,
    url_field_policy: dict[str, Any] | None = None,
    notes: str,
) -> dict[str, Any]:
    required_groups = [
        {
            "group": group_name,
            "fields": list(group_fields),
        }
        for group_name, group_fields in REVIEW_EVIDENCE_REQUIRED_GROUPS
    ]
    return {
        "priority": priority,
        "requirement_id": requirement_id,
        "gate": gate,
        "manifest_fields": manifest_fields,
        "accepted_review_statuses": accepted_review_statuses or [],
        "required_review_scope_ids": required_review_scope_ids or [],
        "required_review_scope_descriptions": {
            scope_id: REVIEW_SCOPE_DESCRIPTIONS.get(scope_id, "")
            for scope_id in (required_review_scope_ids or [])
        },
        "required_evidence_groups": required_groups
        if accepted_review_statuses
        else [],
        "required_inputs": required_inputs or [],
        "placeholder_rule": (
            "TODO/TBD/unknown, placeholder/review-required values, and unedited "
            "<...> template tokens are rejected. Review authority objects with "
            "non-empty missing_inputs, next_required_for_goal, next_required_action_ids, "
            "pending_action_ids, blockers, or open findings are also rejected."
        ),
        "url_field_policy": url_field_policy or {},
        "synthetic_fixture_status": synthetic_fixture_status,
        "notes": notes,
    }


def provenance_url_field_policy() -> dict[str, Any]:
    return {
        "http_url_fields": sorted(PROVENANCE_URL_FIELDS),
        "required_schemes": ["http", "https"],
        "non_url_source_handle_fields": ["source_path", "source_reference"],
        "invalid_url_diagnostics": [
            "provenance_source_reference_invalid:<field>",
            "provenance_export_tool_invalid:<field>",
            "provenance_license_basis_invalid:<field>",
        ],
        "notes": [
            "Fields whose names explicitly end in _url must contain HTTP(S) URLs.",
            "Use source_path or source_reference for local paths, tickets, commit IDs, or other non-URL handles.",
        ],
    }


def build_review_requirements(summary: dict[str, Any]) -> dict[str, Any]:
    url_field_policy = provenance_url_field_policy()
    requirements = [
        review_requirement_item(
            priority=1,
            requirement_id="model_identity",
            gate="reviewed_model_authority",
            manifest_fields=["model_path", *MODEL_SHA256_FIELDS],
            required_inputs=[
                "model_path resolves to a file",
                "declared SHA-256 matches the resolved model file",
            ],
            notes=(
                "The selected SO-101 model path and digest must be stable before "
                "authority review can protect against model drift."
            ),
        ),
        review_requirement_item(
            priority=2,
            requirement_id="source_authority",
            gate="reviewed_model_authority",
            manifest_fields=["authority"],
            accepted_review_statuses=sorted(REVIEWED_AUTHORITY_STATUSES),
            required_review_scope_ids=list(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
            required_inputs=[
                "authority.reviewed_by",
                "authority.review_id or authority.review_url",
            ],
            synthetic_fixture_status=SYNTHETIC_FIXTURE_AUTHORITY_STATUS,
            notes=(
                "Source authority must identify who reviewed model identity, "
                "provenance, and license basis, plus a stable review artifact."
            ),
        ),
        review_requirement_item(
            priority=3,
            requirement_id="provenance",
            gate="reviewed_model_authority",
            manifest_fields=["provenance"],
            required_inputs=[
                "source reference",
                "export tool",
                "license basis",
            ],
            notes=(
                "Provenance is not a reviewed-status block, but source, export, "
                "and license fields must be real non-placeholder records."
            ),
            url_field_policy=url_field_policy,
        ),
        review_requirement_item(
            priority=4,
            requirement_id="mesh_assets",
            gate="reviewed_model_authority",
            manifest_fields=["asset_roots", *MESH_ASSET_REVIEW_FIELDS],
            accepted_review_statuses=sorted(REVIEWED_MESH_ASSET_STATUSES),
            required_review_scope_ids=list(MESH_ASSET_REQUIRED_REVIEW_SCOPE_IDS),
            required_inputs=[
                "mesh references visible to asset preflight",
                "missing_asset_count == 0",
                "unresolved_reference_count == 0",
                "mesh_asset_authority.reviewed_by",
                "mesh_asset_authority.review_id or mesh_asset_authority.review_url",
            ],
            synthetic_fixture_status=SYNTHETIC_FIXTURE_MESH_ASSET_STATUS,
            notes="Mesh roots/assets must be reviewed and repeatably resolvable.",
        ),
        review_requirement_item(
            priority=5,
            requirement_id="joint_limits",
            gate="reviewed_model_authority",
            manifest_fields=list(JOINT_LIMIT_FIELDS + JOINT_LIMIT_REVIEW_FIELDS),
            accepted_review_statuses=sorted(REVIEWED_JOINT_LIMIT_STATUSES),
            required_review_scope_ids=list(JOINT_LIMIT_REQUIRED_REVIEW_SCOPE_IDS),
            required_inputs=[
                f"limits for {joint}"
                for joint in EXPECTED_SO101_JOINTS
            ]
            + [
                "joint_limit_authority.reviewed_by",
                "joint_limit_authority.review_id or joint_limit_authority.review_url",
            ],
            synthetic_fixture_status=SYNTHETIC_FIXTURE_JOINT_LIMIT_STATUS,
            notes=(
                "Every expected SO-101 joint must have numeric lower/upper limits "
                "and separate joint-limit review authority."
            ),
        ),
        review_requirement_item(
            priority=6,
            requirement_id="target_frame",
            gate="reviewed_model_authority",
            manifest_fields=["target_frame", *TARGET_FRAME_REVIEW_FIELDS],
            accepted_review_statuses=sorted(REVIEWED_TARGET_FRAME_STATUSES),
            required_review_scope_ids=list(TARGET_FRAME_REQUIRED_REVIEW_SCOPE_IDS),
            required_inputs=[
                f"target_frame == {EXPECTED_TARGET_FRAME}",
                "target frame visible in model structure",
                "target_frame_authority.reviewed_by",
                "target_frame_authority.review_id or target_frame_authority.review_url",
            ],
            synthetic_fixture_status=SYNTHETIC_FIXTURE_TARGET_FRAME_STATUS,
            notes="The simulator contract currently requires the reviewed target frame to be gripper_frame_link.",
        ),
        review_requirement_item(
            priority=7,
            requirement_id="tcp_offset",
            gate="reviewed_model_authority",
            manifest_fields=list(TCP_OFFSET_FIELDS + TCP_OFFSET_REVIEW_FIELDS),
            accepted_review_statuses=sorted(REVIEWED_TCP_OFFSET_STATUSES),
            required_review_scope_ids=list(TCP_OFFSET_REQUIRED_REVIEW_SCOPE_IDS),
            required_inputs=[
                "numeric x/y/z meters",
                f"norm <= {MAX_TCP_OFFSET_NORM_M} m",
                "tcp_offset_authority.reviewed_by",
                "tcp_offset_authority.review_id or tcp_offset_authority.review_url",
            ],
            synthetic_fixture_status=SYNTHETIC_FIXTURE_TCP_OFFSET_STATUS,
            notes="TCP/gripper-tip offset must be calibrated and reviewed separately from target-frame selection.",
        ),
        review_requirement_item(
            priority=8,
            requirement_id="base_to_board_alignment",
            gate="reviewed_model_authority",
            manifest_fields=list(ALIGNMENT_FIELDS + ALIGNMENT_REVIEW_FIELDS),
            accepted_review_statuses=sorted(REVIEWED_ALIGNMENT_STATUSES),
            required_review_scope_ids=list(ALIGNMENT_REQUIRED_REVIEW_SCOPE_IDS),
            required_inputs=[
                "translation x/y/z meters",
                "rotation roll/pitch/yaw radians",
                f"translation norm <= {MAX_BASE_TO_BOARD_TRANSLATION_NORM_M} m",
                "base_to_board_alignment_authority.reviewed_by",
                "base_to_board_alignment_authority.review_id or base_to_board_alignment_authority.review_url",
            ],
            synthetic_fixture_status=SYNTHETIC_FIXTURE_ALIGNMENT_STATUS,
            notes="Board registration must be a reviewed transform, not a placeholder.",
        ),
        review_requirement_item(
            priority=9,
            requirement_id="model_contract_and_asset_preflight",
            gate="mujoco_scene_validity",
            manifest_fields=["model_path", "asset_roots", "target_frame"],
            required_inputs=[
                "contract checker non-blocking",
                "SO-101 joints visible",
                "target frame visible",
                "mesh asset preflight non-blocking",
            ],
            notes=(
                "The child model contract checker is the handoff from reviewed "
                "bundle intake to MuJoCo scene validity."
            ),
        ),
    ]
    return {
        "schema": REVIEW_REQUIREMENTS_SCHEMA,
        "ok": True,
        "status": "review_requirements_for_so101_model_bundle",
        "model_authority": "review_requirements_not_authority",
        "manifest_status": summary.get("status"),
        "manifest_request_status": (
            summary.get("manifest_request", {}).get("status")
            if isinstance(summary.get("manifest_request"), dict)
            else None
        ),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "physical_so101_model_authority_ready": summary.get(
            "physical_so101_model_authority_ready"
        ),
        "observed_evidence_is_authority": False,
        "physical_so101_truth_claimed": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "requirement_count": len(requirements),
        "requirement_ids": [item["requirement_id"] for item in requirements],
        "missing_inputs": summary.get("missing_inputs") or [],
        "next_required_action_ids": summary.get("next_required_action_ids") or [],
        "placeholder_policy": {
            "angle_bracket_template_tokens_rejected": True,
            "placeholder_values": sorted(PLACEHOLDER_REVIEW_EVIDENCE_VALUES),
            "placeholder_prefixes": list(PLACEHOLDER_REVIEW_EVIDENCE_PREFIXES),
        },
        "url_field_policy": url_field_policy,
        "requirements": requirements,
        "rerun_command": bundle_intake_command_template("review_requirements"),
        "caveats": [
            "This requirements artifact is an operator review aid only.",
            "It is not reviewed physical SO-101 authority and does not make a manifest ready.",
            "The manifest checker summary is the readiness authority for model-backed IK forwarding.",
        ],
    }


def reviewed_manifest_template_status(summary: dict[str, Any]) -> str:
    if summary.get("physical_so101_model_authority_ready") is True:
        return "physical_authority_manifest_supplied"
    manifest_request = summary.get("manifest_request")
    manifest_request = manifest_request if isinstance(manifest_request, dict) else {}
    if manifest_request.get("status") == "model_bundle_manifest_loaded":
        return "template_for_manifest_follow_up"
    return "template_waiting_for_reviewed_manifest"


def reviewed_manifest_template_payload() -> dict[str, Any]:
    return {
        "model_path": "<reviewed-so101-model.urdf-or-mjcf>",
        "model_sha256": "<sha256-of-reviewed-model-file>",
        "asset_roots": ["<reviewed-mesh-or-asset-root>"],
        "authority": {
            "source_authority_status": "reviewed",
            "reviewed_by": "<reviewer-or-team>",
            "reviewed_at": "<review-date-YYYY-MM-DD>",
            "review_id": "<stable-review-ticket-commit-or-artifact-id>",
            "review_scopes": ["model_identity", "provenance", "license"],
        },
        "provenance": {
            "source_reference": "<reviewed-source-url-path-or-record>",
            "export_tool": "<reviewed-export-tool-and-version>",
            "license_basis": "<reviewed-license-file-url-or-record>",
        },
        "target_frame": EXPECTED_TARGET_FRAME,
        "target_frame_authority": {
            "target_frame_authority_status": "reviewed",
            "reviewed_by": "<reviewer-or-team>",
            "reviewed_at": "<review-date-YYYY-MM-DD>",
            "review_id": "<stable-target-frame-review-artifact-id>",
            "review_scope": "target_frame",
            "source": "<reviewed-target-frame-or-tcp-reference-record>",
        },
        "joint_limits_deg": {
            joint: ["<lower-deg-or-mm>", "<upper-deg-or-mm>"]
            for joint in EXPECTED_SO101_JOINTS
        },
        "joint_limit_authority": {
            "joint_limit_authority_status": "reviewed",
            "reviewed_by": "<reviewer-or-team>",
            "reviewed_at": "<review-date-YYYY-MM-DD>",
            "review_id": "<stable-joint-limit-review-artifact-id>",
            "review_scope": "joint_limits",
            "source": "<reviewed-joint-limit-record>",
        },
        "mesh_asset_authority": {
            "mesh_asset_authority_status": "reviewed",
            "reviewed_by": "<reviewer-or-team>",
            "reviewed_at": "<review-date-YYYY-MM-DD>",
            "review_id": "<stable-mesh-asset-review-artifact-id>",
            "review_scope": "mesh_assets",
            "source": "<reviewed-model-export-or-mesh-root-record>",
        },
        "tcp_offset_m": {"x": "<meters>", "y": "<meters>", "z": "<meters>"},
        "tcp_offset_authority": {
            "tcp_offset_authority_status": "reviewed",
            "reviewed_by": "<reviewer-or-team>",
            "reviewed_at": "<review-date-YYYY-MM-DD>",
            "review_id": "<stable-tcp-offset-review-artifact-id>",
            "review_scope": "tcp_offset",
            "source": "<reviewed-tcp-or-gripper-tip-calibration-record>",
        },
        "base_to_board_transform": {
            "translation_m": {"x": "<meters>", "y": "<meters>", "z": "<meters>"},
            "rotation_rpy_rad": {
                "roll": "<radians>",
                "pitch": "<radians>",
                "yaw": "<radians>",
            },
        },
        "base_to_board_alignment_authority": {
            "base_to_board_alignment_authority_status": "reviewed",
            "reviewed_by": "<reviewer-or-team>",
            "reviewed_at": "<review-date-YYYY-MM-DD>",
            "review_id": "<stable-base-board-review-artifact-id>",
            "review_scope": "base_to_board_alignment",
            "source": "<reviewed-board-registration-or-calibration-record>",
        },
    }


def build_reviewed_manifest_template(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": REVIEWED_MANIFEST_TEMPLATE_SCHEMA,
        "ok": True,
        "status": reviewed_manifest_template_status(summary),
        "model_authority": "reviewed_manifest_template_not_authority",
        "manifest_status": summary.get("status"),
        "manifest_request_status": (
            summary.get("manifest_request", {}).get("status")
            if isinstance(summary.get("manifest_request"), dict)
            else None
        ),
        "ready_for_model_backed_ik": False,
        "physical_so101_model_authority_ready": False,
        "observed_evidence_is_authority": False,
        "physical_so101_truth_claimed": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "missing_inputs": summary.get("missing_inputs") or [],
        "next_required_for_goal": summary.get("next_required_for_goal") or [],
        "next_required_action_ids": summary.get("next_required_action_ids") or [],
        "required_review_scopes_by_field": {
            "authority": ["model_identity", "provenance", "license"],
            "target_frame_authority": ["target_frame"],
            "joint_limit_authority": ["joint_limits"],
            "mesh_asset_authority": ["mesh_assets"],
            "tcp_offset_authority": ["tcp_offset"],
            "base_to_board_alignment_authority": ["base_to_board_alignment"],
        },
        "rerun_command": bundle_intake_command_template("supply_reviewed_manifest"),
        "manifest_template": reviewed_manifest_template_payload(),
        "caveats": [
            "This reviewed-manifest template is not reviewed physical SO-101 authority.",
            "Placeholder values must be replaced with reviewed model, digest, provenance, authority, TCP, and board-alignment data.",
            "After editing a copy of manifest_template, rerun the manifest checker and require physical_so101_model_authority_ready before trusting model-backed IK.",
        ],
    }


def build_bundle_manifest_intake_checklist(summary: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for action in summary.get("next_required_for_goal") or []:
        if not isinstance(action, dict):
            continue
        action_id = action.get("action_id")
        missing_input = action.get("missing_input")
        if not isinstance(action_id, str) or not action_id:
            continue
        missing_input = str(missing_input) if missing_input else ""
        field_check_context = bundle_intake_field_check_context(
            summary,
            missing_input,
        )
        actions.append(
            {
                "priority": len(actions) + 1,
                "action_id": action_id,
                "status": "pending",
                "gate": action.get("gate"),
                "title": action.get("title"),
                "detail": action.get("detail"),
                "missing_input": missing_input,
                "manifest_fields": bundle_intake_manifest_fields(missing_input),
                "command": bundle_intake_command_template(action_id),
                "required_inputs": bundle_intake_required_inputs(missing_input),
                "related_requirement_ids": bundle_intake_related_requirement_ids(
                    field_check_context
                ),
                "field_check_diagnostics": bundle_intake_field_check_diagnostics(
                    field_check_context
                ),
                "field_check_context": field_check_context,
            }
        )
    return {
        "schema": BUNDLE_INTAKE_SCHEMA,
        "ok": True,
        "status": bundle_intake_status(summary),
        "model_authority": "bundle_manifest_intake_not_authority",
        "manifest_status": summary.get("status"),
        "manifest_request_status": (
            summary.get("manifest_request", {}).get("status")
            if isinstance(summary.get("manifest_request"), dict)
            else None
        ),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "physical_so101_model_authority_ready": summary.get(
            "physical_so101_model_authority_ready"
        ),
        "physical_authority_gate_status": summary.get("physical_authority_gate_status"),
        "physical_authority_blockers": summary.get("physical_authority_blockers") or [],
        "hardware_free_regression_fixture_ready": summary.get(
            "hardware_free_regression_fixture_ready"
        ),
        "synthetic_fixture_authority_fields": summary.get(
            "synthetic_fixture_authority_fields"
        )
        or [],
        "missing_inputs": summary.get("missing_inputs") or [],
        "next_required_for_goal": summary.get("next_required_for_goal") or [],
        "next_required_action_ids": summary.get("next_required_action_ids") or [],
        "action_count": len(actions),
        "actions": actions,
        "observed_evidence_is_authority": False,
        "physical_so101_truth_claimed": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "artifacts": summary.get("artifacts"),
        "caveats": [
            "This bundle-manifest intake checklist is operator guidance, not reviewed physical SO-101 authority.",
            "Command templates rerun the manifest checker after a reviewed manifest is supplied or updated; they do not create authority by themselves.",
            "Fixture-only readiness remains explicitly non-physical SO-101 truth until physical bundle authority and reviewed MuJoCo motion are both proven.",
        ],
    }


def build_checklist_rows(
    manifest_request: dict[str, Any],
    model_path: dict[str, Any],
    model_identity: dict[str, Any],
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
            "model_sha256",
            "model_identity",
            "ok" if model_identity["status"] == "present" else "action_required",
            "warning",
            f"manifest.{'|'.join(MODEL_SHA256_FIELDS)}",
            model_identity,
            {"matches_resolved_model_file_sha256": True},
            None if model_identity["status"] == "present" else ["model_sha256"],
            model_identity.get("diagnostics", []),
            "The reviewed manifest must pin the exact model file contents so a path cannot silently drift after review.",
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
        f"- `model_authority`: `{summary['model_authority']}`",
        f"- `physical_authority_gate_status`: `{summary['physical_authority_gate_status']}`",
        f"- `physical_so101_model_authority_ready`: `{str(summary['physical_so101_model_authority_ready']).lower()}`",
        f"- `physical_authority_blockers`: `{'; '.join(summary['physical_authority_blockers']) if summary['physical_authority_blockers'] else 'none'}`",
        f"- `hardware_free_regression_fixture_ready`: `{str(summary['hardware_free_regression_fixture_ready']).lower()}`",
        f"- `synthetic_fixture_authority_fields`: `{'; '.join(summary['synthetic_fixture_authority_fields']) if summary['synthetic_fixture_authority_fields'] else 'none'}`",
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
        f"- `review_packet_status`: `{summary.get('review_packet_status')}`",
        f"- `review_packet_item_count`: `{summary.get('review_packet_item_count')}`",
        f"- `review_packet_json`: `{summary['artifacts'].get('review_packet_json')}`",
        f"- `review_packet_csv`: `{summary['artifacts'].get('review_packet_csv')}`",
        f"- `review_requirements_status`: `{summary.get('review_requirements_status')}`",
        f"- `review_requirements_model_authority`: `{summary.get('review_requirements_model_authority')}`",
        f"- `review_requirements_requirement_count`: `{summary.get('review_requirements_requirement_count')}`",
        f"- `review_requirements_json`: `{summary['artifacts'].get('review_requirements_json')}`",
        f"- `review_requirements_csv`: `{summary['artifacts'].get('review_requirements_csv')}`",
        f"- `bundle_intake_status`: `{summary.get('bundle_intake_status')}`",
        f"- `bundle_intake_model_authority`: `{summary.get('bundle_intake_model_authority')}`",
        f"- `bundle_intake_action_ids`: `{', '.join(summary.get('bundle_intake_action_ids') or []) if summary.get('bundle_intake_action_ids') else 'none'}`",
        f"- `bundle_intake_checklist_json`: `{summary['artifacts'].get('bundle_intake_checklist_json')}`",
        f"- `bundle_intake_checklist_csv`: `{summary['artifacts'].get('bundle_intake_checklist_csv')}`",
        f"- `reviewed_manifest_template_status`: `{summary.get('reviewed_manifest_template_status')}`",
        f"- `reviewed_manifest_template_model_authority`: `{summary.get('reviewed_manifest_template_model_authority')}`",
        f"- `reviewed_manifest_template_json`: `{summary['artifacts'].get('reviewed_manifest_template_json')}`",
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

    lines.extend(["", "## Next Required For Goal", ""])
    if summary["next_required_for_goal"]:
        for action in summary["next_required_for_goal"]:
            lines.append(
                "- `{priority}` `{action_id}`: {title} (`{missing_input}`)".format(
                    priority=action["priority"],
                    action_id=action["action_id"],
                    title=action["title"],
                    missing_input=action["missing_input"],
                )
            )
            lines.append(f"  - {action['detail']}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Review Requirements",
            "",
            (
                "This artifact lists the required review scopes, evidence groups, "
                "accepted statuses, and placeholder rejection policy for the reviewed "
                "SO-101 bundle. It is operator guidance only, not reviewed physical "
                "SO-101 authority."
            ),
            "",
            f"- `status`: `{summary.get('review_requirements_status')}`",
            f"- `model_authority`: `{summary.get('review_requirements_model_authority')}`",
            f"- `requirement_count`: `{summary.get('review_requirements_requirement_count')}`",
            f"- `json`: `{summary['artifacts'].get('review_requirements_json')}`",
            f"- `csv`: `{summary['artifacts'].get('review_requirements_csv')}`",
        ]
    )

    lines.extend(
        [
            "",
            "## Bundle Manifest Intake Checklist",
            "",
            (
                "This checklist converts the current missing reviewed-bundle fields into "
                "rerun command templates. It is operator guidance only, not reviewed "
                "physical SO-101 authority."
            ),
            "",
            "| Priority | Action | Status | Missing Input | Command |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for action in summary["bundle_intake_checklist"].get("actions") or []:
        command = " ".join(str(part) for part in action.get("command") or []) or "n/a"
        lines.append(
            "| `{priority}` | `{action_id}` | `{status}` | `{missing_input}` | `{command}` |".format(
                priority=action.get("priority"),
                action_id=action.get("action_id"),
                status=action.get("status"),
                missing_input=action.get("missing_input") or "n/a",
                command=command.replace("|", "/"),
            )
        )
    if not summary["bundle_intake_checklist"].get("actions"):
        lines.append("| none | none | n/a | none | n/a |")

    lines.extend(
        [
            "",
            "## Reviewed Manifest Template",
            "",
            (
                "A copyable reviewed-manifest template is written as JSON with "
                "placeholder values. It is not reviewed physical SO-101 authority; "
                "replace every placeholder and rerun this checker before using it."
            ),
            "",
            f"- `status`: `{summary.get('reviewed_manifest_template_status')}`",
            f"- `model_authority`: `{summary.get('reviewed_manifest_template_model_authority')}`",
            f"- `path`: `{summary['artifacts'].get('reviewed_manifest_template_json')}`",
        ]
    )

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
    model_identity = inspect_model_identity(manifest, model_path)
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
        model_identity,
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
    next_required_for_goal = build_next_required_for_goal(sorted(set(missing_inputs)))
    synthetic_flags = synthetic_fixture_authority_flags(
        authority,
        provenance,
        joint_limits,
        mesh_assets,
        target_frame,
        tcp_offset,
        alignment,
    )
    synthetic_fields = [field for field, enabled in synthetic_flags.items() if enabled]
    physical_authority_ready = ready and not synthetic_fields
    physical_authority_blockers = build_physical_authority_blockers(
        next_required_for_goal,
        synthetic_fields,
    )
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status_for(manifest_request, ready),
        "ready_for_model_backed_ik": ready,
        "model_authority": model_authority_class(ready, synthetic_flags),
        "physical_authority_gate_status": physical_authority_gate_status(
            ready,
            physical_authority_ready,
            synthetic_fields,
        ),
        "physical_so101_model_authority_ready": physical_authority_ready,
        "physical_authority_blockers": physical_authority_blockers,
        "hardware_free_regression_fixture_ready": ready and bool(synthetic_fields),
        "synthetic_fixture_authority_fields": synthetic_fields,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "required_inputs": list(REQUIRED_INPUTS),
        "manifest_request": manifest_request,
        "manifest": manifest,
        "model_path": model_path,
        "model_identity": model_identity,
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
        "next_required_for_goal": next_required_for_goal,
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
        model_identity,
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
    review_packet_path = output_dir / "so101_model_bundle_manifest_review_packet.json"
    review_packet_csv_path = output_dir / "so101_model_bundle_manifest_review_packet.csv"
    review_requirements_path = (
        output_dir / "so101_model_bundle_manifest_review_requirements.json"
    )
    review_requirements_csv_path = (
        output_dir / "so101_model_bundle_manifest_review_requirements.csv"
    )
    bundle_intake_path = output_dir / "so101_model_bundle_manifest_intake_checklist.json"
    bundle_intake_csv_path = (
        output_dir / "so101_model_bundle_manifest_intake_checklist.csv"
    )
    reviewed_manifest_template_path = (
        output_dir / "so101_model_bundle_manifest_template.json"
    )
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(csv_path),
        "readme_md": str(readme_path),
        "review_packet_json": str(review_packet_path),
        "review_packet_csv": str(review_packet_csv_path),
        "review_requirements_json": str(review_requirements_path),
        "review_requirements_csv": str(review_requirements_csv_path),
        "bundle_intake_checklist_json": str(bundle_intake_path),
        "bundle_intake_checklist_csv": str(bundle_intake_csv_path),
        "reviewed_manifest_template_json": str(reviewed_manifest_template_path),
    }

    manifest, manifest_request = load_manifest(args.manifest_path)
    summary, rows = build_summary(manifest, manifest_request, args.python, output_dir, artifacts)
    review_packet, review_packet_rows = build_review_packet(summary, rows)
    next_required_action_ids = [
        action["action_id"]
        for action in summary["next_required_for_goal"]
        if isinstance(action.get("action_id"), str) and action["action_id"]
    ]
    summary.update(
        {
            "next_required_action_ids": next_required_action_ids,
            "next_required_action_count": len(next_required_action_ids),
            "review_packet_status": review_packet["status"],
            "review_packet_model_authority": review_packet["model_authority"],
            "review_packet_item_count": review_packet["review_item_count"],
            "review_packet_item_ids": review_packet["review_item_ids"],
            "review_packet_needs_operator_review_item_ids": review_packet[
                "needs_operator_review_item_ids"
            ],
            "review_packet_action_ids": review_packet["review_action_ids"],
            "review_packet_observed_evidence_is_authority": review_packet[
                "observed_evidence_is_authority"
            ],
            "review_packet_development_fixture_evidence_not_physical_so101_truth": review_packet[
                "development_fixture_evidence_not_physical_so101_truth"
            ],
            "review_packet": review_packet,
        }
    )
    review_requirements = build_review_requirements(summary)
    summary.update(
        {
            "review_requirements_status": review_requirements["status"],
            "review_requirements_model_authority": review_requirements[
                "model_authority"
            ],
            "review_requirements_requirement_count": review_requirements[
                "requirement_count"
            ],
            "review_requirements_requirement_ids": review_requirements[
                "requirement_ids"
            ],
            "review_requirements_observed_evidence_is_authority": (
                review_requirements["observed_evidence_is_authority"]
            ),
            "review_requirements_physical_so101_truth_claimed": (
                review_requirements["physical_so101_truth_claimed"]
            ),
            "review_requirements_development_fixture_evidence_not_physical_so101_truth": (
                review_requirements[
                    "development_fixture_evidence_not_physical_so101_truth"
                ]
            ),
            "review_requirements_json_path": artifacts.get(
                "review_requirements_json"
            ),
            "review_requirements_csv_path": artifacts.get(
                "review_requirements_csv"
            ),
            "review_requirements": review_requirements,
        }
    )
    bundle_intake_checklist = build_bundle_manifest_intake_checklist(summary)
    summary.update(
        {
            "bundle_intake_status": bundle_intake_checklist["status"],
            "bundle_intake_model_authority": bundle_intake_checklist[
                "model_authority"
            ],
            "bundle_intake_action_count": bundle_intake_checklist["action_count"],
            "bundle_intake_action_ids": [
                action["action_id"]
                for action in bundle_intake_checklist.get("actions") or []
            ],
            "bundle_intake_observed_evidence_is_authority": (
                bundle_intake_checklist["observed_evidence_is_authority"]
            ),
            "bundle_intake_physical_so101_truth_claimed": bundle_intake_checklist[
                "physical_so101_truth_claimed"
            ],
            "bundle_intake_development_fixture_evidence_not_physical_so101_truth": (
                bundle_intake_checklist[
                    "development_fixture_evidence_not_physical_so101_truth"
                ]
            ),
            "bundle_intake_checklist_json_path": artifacts.get(
                "bundle_intake_checklist_json"
            ),
            "bundle_intake_checklist_csv_path": artifacts.get(
                "bundle_intake_checklist_csv"
            ),
            "bundle_intake_checklist": bundle_intake_checklist,
        }
    )
    reviewed_manifest_template = build_reviewed_manifest_template(summary)
    summary.update(
        {
            "reviewed_manifest_template_status": reviewed_manifest_template["status"],
            "reviewed_manifest_template_model_authority": reviewed_manifest_template[
                "model_authority"
            ],
            "reviewed_manifest_template_observed_evidence_is_authority": (
                reviewed_manifest_template["observed_evidence_is_authority"]
            ),
            "reviewed_manifest_template_physical_so101_truth_claimed": (
                reviewed_manifest_template["physical_so101_truth_claimed"]
            ),
            "reviewed_manifest_template_development_fixture_evidence_not_physical_so101_truth": (
                reviewed_manifest_template[
                    "development_fixture_evidence_not_physical_so101_truth"
                ]
            ),
            "reviewed_manifest_template_json_path": artifacts.get(
                "reviewed_manifest_template_json"
            ),
            "reviewed_manifest_template": reviewed_manifest_template,
        }
    )

    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    write_json(review_packet_path, review_packet)
    write_review_packet_csv(review_packet_csv_path, review_packet_rows)
    write_json(review_requirements_path, review_requirements)
    write_review_requirements_csv(review_requirements_csv_path, review_requirements)
    write_json(bundle_intake_path, bundle_intake_checklist)
    write_bundle_intake_csv(bundle_intake_csv_path, bundle_intake_checklist)
    write_json(reviewed_manifest_template_path, reviewed_manifest_template)
    write_markdown(readme_path, summary, rows)

    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
                "model_authority": summary["model_authority"],
                "physical_authority_gate_status": summary["physical_authority_gate_status"],
                "physical_so101_model_authority_ready": summary["physical_so101_model_authority_ready"],
                "physical_authority_blockers": summary["physical_authority_blockers"],
                "hardware_free_regression_fixture_ready": summary["hardware_free_regression_fixture_ready"],
                "missing_inputs": summary["missing_inputs"],
                "next_required_for_goal": summary["next_required_for_goal"],
                "review_packet_status": summary["review_packet_status"],
                "review_packet_item_count": summary["review_packet_item_count"],
                "review_packet_action_ids": summary["review_packet_action_ids"],
                "bundle_intake_status": summary["bundle_intake_status"],
                "bundle_intake_action_ids": summary["bundle_intake_action_ids"],
                "reviewed_manifest_template_status": summary[
                    "reviewed_manifest_template_status"
                ],
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
                "review_packet_json": str(review_packet_path),
                "review_packet_csv": str(review_packet_csv_path),
                "review_requirements_json": str(review_requirements_path),
                "review_requirements_csv": str(review_requirements_csv_path),
                "bundle_intake_checklist_json": str(bundle_intake_path),
                "bundle_intake_checklist_csv": str(bundle_intake_csv_path),
                "reviewed_manifest_template_json": str(
                    reviewed_manifest_template_path
                ),
                "readme_md": str(readme_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
