#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "calibration_regression_suite"
DEFAULT_REFERENCE_IMAGE = REPO_ROOT / "archive" / "chess_test_images" / "current_view.jpg"
DEFAULT_BASE_PROFILE = "current_gripper_reference"
SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
ARTIFACT_ENTRYPOINT_NAME = "README.md"
ARTIFACT_REPORT_NAME = "artifact_index_report.md"
REFERENCE_MEDIA_INVENTORY_DIR_NAME = "reference_media_inventory"
REFERENCE_MEDIA_INVENTORY_JSON_NAME = "reference_media_inventory.json"
REFERENCE_MEDIA_INVENTORY_CSV_NAME = "reference_media_inventory.csv"
REFERENCE_MEDIA_INVENTORY_README_NAME = "README.md"
REFERENCE_CAMERA_TUNING_DIR_NAME = "reference_camera_tuning_diagnostics"
REFERENCE_CAMERA_TUNING_JSON_NAME = "reference_camera_tuning_diagnostics.json"
REFERENCE_CAMERA_TUNING_CSV_NAME = "reference_camera_tuning_diagnostics.csv"
REFERENCE_CAMERA_TUNING_README_NAME = "README.md"
REFERENCE_CAMERA_TUNING_SCORECARD_NAME = "reference_camera_tuning_scorecard.png"
SIM_CAMERA_PROFILE_SWEEP_DIR_NAME = "sim_camera_profile_sweep"
SIM_CAMERA_PROFILE_SWEEP_JSON_NAME = "summary.json"
SIM_CAMERA_PROFILE_SWEEP_MARKER_TIME_SECONDS = 0.0
SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME = "simcamera_tuning_before_after"
SIM_CAMERA_TUNING_BEFORE_AFTER_JSON_NAME = "simcamera_tuning_before_after_summary.json"
SIM_CAMERA_TUNING_BEFORE_AFTER_CSV_NAME = "simcamera_tuning_before_after_rows.csv"
SIM_CAMERA_TUNING_BEFORE_AFTER_README_NAME = "README.md"
SIM_CAMERA_TUNING_BEFORE_AFTER_BASELINE_WIDTH_PX = 72
REFERENCE_CAPTURE_MANIFEST_DIR_NAME = "reference_capture_manifest"
REFERENCE_CAPTURE_MANIFEST_JSON_NAME = "reference_capture_manifest_check.json"
REFERENCE_CAPTURE_MANIFEST_CSV_NAME = "reference_capture_manifest_checklist.csv"
REFERENCE_CAPTURE_MANIFEST_README_NAME = "README.md"
REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_DIR_NAME = "real_depth_capture_plan_artifact_index"
REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_JSON_NAME = "real_depth_capture_plan_artifact_index.json"
REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_CSV_NAME = "real_depth_capture_plan_artifact_index_cases.csv"
REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_README_NAME = "README.md"
REAL_DEPTH_CAPTURE_PLAN_INPUT_READINESS_CAVEAT = (
    "Ready reference-capture-manifest evidence is input readiness only; physical calibration "
    "truth still requires subsequent sidecar validation, intake, and residual comparison artifacts."
)
VISUAL_REVIEW_SUMMARY_NAME = "visual_review_summary.json"
REFERENCE_CAPTURE_CHECKLIST_NAME = "reference_capture_checklist.json"
REAL_PROJECTION_INTAKE_NAME = "real_projection_intake.json"
EVIDENCE_BUNDLE_DIR_NAME = "evidence_bundle"
EVIDENCE_BUNDLE_MD_NAME = "sim_evidence_bundle.md"
EVIDENCE_BUNDLE_JSON_NAME = "sim_evidence_bundle.json"
IK_REACHABILITY_SUMMARY_NAME = "ik_reachability_drill_summary.json"
SO101_MODEL_SOURCE_INVENTORY_SUMMARY_NAME = "so101_model_source_inventory_summary.json"
SO101_MODEL_SOURCE_INVENTORY_REVIEW_PACKET_JSON_NAME = (
    "so101_model_source_inventory_review_packet.json"
)
SO101_MODEL_SOURCE_INVENTORY_REVIEW_PACKET_CSV_NAME = (
    "so101_model_source_inventory_review_packet.csv"
)
SO101_MODEL_SOURCE_INTAKE_CHECKLIST_JSON_NAME = (
    "so101_model_source_intake_checklist.json"
)
SO101_MODEL_SOURCE_INTAKE_CHECKLIST_CSV_NAME = (
    "so101_model_source_intake_checklist.csv"
)
SO101_MODEL_BUNDLE_PROBE_DIR_NAME = "so101_model_bundle_probe"
SO101_MODEL_BUNDLE_PROBE_SUMMARY_NAME = "so101_model_bundle_probe_summary.json"
SO101_MODEL_BUNDLE_MANIFEST_SUMMARY_NAME = "so101_model_bundle_manifest_summary.json"
SO101_MODEL_BUNDLE_MANIFEST_REVIEW_PACKET_JSON_NAME = (
    "so101_model_bundle_manifest_review_packet.json"
)
SO101_MODEL_BUNDLE_MANIFEST_REVIEW_PACKET_CSV_NAME = (
    "so101_model_bundle_manifest_review_packet.csv"
)
SO101_MODEL_BUNDLE_MANIFEST_REVIEW_REQUIREMENTS_JSON_NAME = (
    "so101_model_bundle_manifest_review_requirements.json"
)
SO101_MODEL_BUNDLE_MANIFEST_REVIEW_REQUIREMENTS_CSV_NAME = (
    "so101_model_bundle_manifest_review_requirements.csv"
)
SO101_MODEL_BUNDLE_MANIFEST_INTAKE_CHECKLIST_JSON_NAME = (
    "so101_model_bundle_manifest_intake_checklist.json"
)
SO101_MODEL_BUNDLE_MANIFEST_INTAKE_CHECKLIST_CSV_NAME = (
    "so101_model_bundle_manifest_intake_checklist.csv"
)
SO101_MODEL_BUNDLE_MANIFEST_TEMPLATE_JSON_NAME = (
    "so101_model_bundle_manifest_template.json"
)
SO101_MODEL_CONTRACT_SUMMARY_NAME = "so101_model_contract_summary.json"
SO101_REVIEWED_MODEL_AUTHORITY_GATE_SCHEMA = "lerobot.sim.so101_reviewed_model_authority_gate.v1"
SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME = "so101_reviewed_model_authority_gate"
SO101_REVIEWED_MODEL_AUTHORITY_GATE_SUMMARY_NAME = "so101_reviewed_model_authority_gate.json"
SO101_REVIEWED_MODEL_AUTHORITY_GATE_CHECKLIST_NAME = "so101_reviewed_model_authority_gate_checklist.csv"
SO101_REVIEWED_MODEL_AUTHORITY_GATE_BLOCKER_PACKET_JSON_NAME = (
    "so101_reviewed_model_authority_blocker_packet.json"
)
SO101_REVIEWED_MODEL_AUTHORITY_GATE_BLOCKER_PACKET_CSV_NAME = (
    "so101_reviewed_model_authority_blocker_packet.csv"
)
SO101_REVIEWED_MODEL_AUTHORITY_GATE_README_NAME = "README.md"
SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME = "so101_reviewed_mujoco_bundle"
SO101_REVIEWED_MUJOCO_BUNDLE_SUMMARY_NAME = "so101_reviewed_mujoco_bundle_summary.json"
SO101_REVIEWED_MUJOCO_BUNDLE_MOTION_CHECKS_NAME = (
    "so101_reviewed_mujoco_bundle_motion_checks.csv"
)
SO101_REVIEWED_MUJOCO_BUNDLE_DOWNSTREAM_HANDOFF_NAME = (
    "so101_reviewed_mujoco_bundle_downstream_handoff.json"
)
SO101_REVIEWED_MUJOCO_BUNDLE_DOWNSTREAM_HANDOFF_CSV_NAME = (
    "so101_reviewed_mujoco_bundle_downstream_handoff.csv"
)
SO101_MUJOCO_SCENE_DIR_NAME = "so101_mujoco_scene"
SO101_MUJOCO_SCENE_SUMMARY_NAME = "so101_mujoco_scene_summary.json"
SO101_CHESS_ENV_DIR_NAME = "so101_chess_env"
SO101_CHESS_ENV_SUMMARY_NAME = "so101_chess_env_summary.json"
SO101_ENV_RESETS_DIR_NAME = "so101_env_resets"
SO101_ENV_RESETS_SUMMARY_NAME = "so101_env_resets_summary.json"
SO101_MUJOCO_CONTACT_PROBE_DIR_NAME = "so101_mujoco_contact_probe"
SO101_MUJOCO_CONTACT_PROBE_SUMMARY_NAME = "so101_mujoco_contact_probe_summary.json"
SO101_MUJOCO_GRASP_PROBE_DIR_NAME = "so101_mujoco_grasp_probe"
SO101_MUJOCO_GRASP_PROBE_SUMMARY_NAME = "so101_mujoco_grasp_probe_summary.json"
SO101_MUJOCO_BOARD_PICK_PROBE_DIR_NAME = "so101_mujoco_board_pick_probe"
SO101_MUJOCO_BOARD_PICK_PROBE_SUMMARY_NAME = "so101_mujoco_board_pick_probe_summary.json"
SO101_TRAINING_READINESS_GATE_SCHEMA = "lerobot.sim.so101_training_readiness_gate.v1"
SO101_TRAINING_READINESS_GATE_DIR_NAME = "so101_training_readiness_gate"
SO101_TRAINING_READINESS_GATE_SUMMARY_NAME = "so101_training_readiness_gate.json"
SO101_TRAINING_READINESS_GATE_CHECKLIST_NAME = "so101_training_readiness_gate_checklist.csv"
SO101_TRAINING_READINESS_GATE_PRIORITY_QUEUE_NAME = (
    "so101_training_readiness_gate_priority_queue.csv"
)
SO101_TRAINING_READINESS_GATE_README_NAME = "README.md"
SO101_TRAINING_ROLLOUTS_DIR_NAME = "so101_training_rollouts"
SO101_TRAINING_ROLLOUTS_SUMMARY_NAME = "so101_training_rollouts_summary.json"
REVIEWED_SO101_MODEL_AUTHORITY = "reviewed_so101_model_bundle_manifest"
SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_SCHEMA = (
    "lerobot.sim.so101_reviewed_mujoco_bundle_downstream_handoff.v1"
)
SO101_CONTROL_JOINT_IDS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_ITEM_IDS = (
    "model_authority",
    "model_identity",
    "target_frame",
    "tcp_offset_m",
    "base_to_board_alignment",
    "joint_limits",
    "mesh_assets",
    "mujoco_motion",
    "downstream_gate_handoff",
)
SO101_TRAINING_PRIORITY_STAGE_IDS = (
    "reviewed_model_authority",
    "mujoco_scene_validity",
    "gymnasium_task_wiring",
    "scripted_contact_grasp_pick_place",
    "focused_training_rollouts",
)
SO101_BOARD_PICK_REQUIRED_PHASE_IDS = (
    "source_reset",
    "two_finger_grasp",
    "lift_clearance",
    "transfer_toward_target",
    "release_place",
)
SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE = (
    "source_reset_piece_on_board",
    "lower_open_at_source",
    "close_on_source_piece_forward",
    "close_on_source_piece_after_settle",
    "lift_from_source_without_manual_piece_pose",
    "transfer_to_target_without_manual_piece_pose",
    "lower_to_target_without_manual_piece_pose",
    "release_on_target_without_manual_piece_pose",
    "retreat_after_release_without_manual_piece_pose",
)
BASELINE_CORNERS = [[32, 338], [594, 340], [540, 20], [86, 12]]
PERTURBED_CORNERS = [[34, 337], [592, 342], [538, 22], [88, 14]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the hardware-free simulator calibration regression suite: reference media "
            "inventory, real-reference comparison set, ranked calibration session report, "
            "perception regression fixture manifest, and SimCamera pose fixture."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child smoke scripts.",
    )
    parser.add_argument("--reference-image", type=Path, default=DEFAULT_REFERENCE_IMAGE)
    parser.add_argument(
        "--reference-media-manifest",
        type=Path,
        default=None,
        help=(
            "Optional repo-local reference-media manifest passed only to the inventory child. "
            "Default suite and CI behavior remain manifest-free."
        ),
    )
    parser.add_argument(
        "--reference-media-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "Optional file or directory root forwarded to the reference-media inventory as "
            "--root. Repeatable. Supplying roots replaces the inventory child's default "
            "repo-root scan, so pass --reference-media-root . when adding sibling roots."
        ),
    )
    parser.add_argument(
        "--reference-capture-manifest",
        type=Path,
        default=None,
        help=(
            "Optional local-only real-reference capture manifest passed to the reference "
            "capture manifest checker. Default suite and CI behavior remain no-manifest "
            "diagnostic evidence."
        ),
    )
    parser.add_argument(
        "--ik-model-path",
        type=Path,
        default=None,
        help=(
            "Optional SO-101 kinematic model path forwarded to the SO-101 model contract "
            "checker and IK reachability child. Default suite behavior remains model-free "
            "and non-failing."
        ),
    )
    parser.add_argument(
        "--ik-model-asset-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "Optional SO-101 mesh/assets root forwarded to the model contract checker as "
            "--model-asset-root. Repeatable. This is separate from --ik-model-path and "
            "source authority options."
        ),
    )
    parser.add_argument(
        "--so101-model-bundle-manifest",
        type=Path,
        default=None,
        help=(
            "Optional reviewed SO-101 model bundle manifest passed to the bundle manifest "
            "checker. When the checker reports ready_for_model_backed_ik=true and no "
            "--ik-model-path was supplied, the suite may derive downstream contract/IK "
            "model path and contract asset roots from this manifest."
        ),
    )
    parser.add_argument(
        "--so101-model-source-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "Reviewed SO-101 model-source root passed to the source inventory as --root. "
            "Repeatable. Supplying this replaces the inventory child default repo-local roots."
        ),
    )
    parser.add_argument(
        "--so101-model-source-extra-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "Additional reviewed SO-101 model-source root passed to the source inventory as "
            "--extra-root while retaining its default repo-local roots. Repeatable."
        ),
    )
    parser.add_argument(
        "--so101-authoritative-model-path",
        type=Path,
        action="append",
        default=[],
        help=(
            "Reviewed authoritative SO-101 model path passed to the source inventory as "
            "--authoritative-path. Repeatable. This is separate from --ik-model-path."
        ),
    )
    parser.add_argument(
        "--so101-authoritative-model-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "Reviewed authoritative SO-101 model root passed to the source inventory as "
            "--authoritative-root. Repeatable. This is separate from --ik-model-path."
        ),
    )
    parser.add_argument(
        "--so101-source-authority-reviewed-by",
        default=None,
        help="Reviewer/operator identifier forwarded to the SO-101 model-source inventory.",
    )
    parser.add_argument(
        "--so101-source-authority-reviewed-at",
        default=None,
        help="Deterministic review date/string forwarded to the SO-101 model-source inventory.",
    )
    parser.add_argument(
        "--so101-source-authority-review-id",
        default=None,
        help="Review ticket, issue, commit, or checklist identifier forwarded to the source inventory.",
    )
    parser.add_argument(
        "--so101-source-authority-review-url",
        default=None,
        help="URL to the reviewed source-authority record forwarded to the source inventory.",
    )
    parser.add_argument(
        "--so101-source-authority-source-reference",
        default=None,
        help="CAD/export/source reference forwarded to the SO-101 model-source inventory.",
    )
    parser.add_argument(
        "--so101-source-authority-review-scope",
        action="append",
        choices=SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS,
        default=[],
        help=(
            "Source-authority review scope forwarded to the SO-101 model-source inventory. "
            "Repeat for every required scope: "
            f"{', '.join(SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS)}."
        ),
    )
    parser.add_argument(
        "--so101-source-authority-license-basis",
        default=None,
        help="Reviewed license or redistribution basis forwarded to the SO-101 model-source inventory.",
    )
    parser.add_argument("--base-profile", default=DEFAULT_BASE_PROFILE)
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--select-rank", type=int, default=1)
    parser.add_argument(
        "--include-negative-check",
        action="store_true",
        help=(
            "Also run a deliberate empty-inventory comparison-set check and require it to "
            "fail clearly without making the aggregate suite fail."
        ),
    )
    parser.add_argument(
        "--skip-artifact-index-report",
        action="store_true",
        help="Do not render the optional Markdown artifact-index report at the end of the suite.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def markdown_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def cli_path_values(paths: list[Path] | None) -> list[str]:
    if not paths:
        return []
    return [str(path.expanduser()) for path in paths]


def markdown_list_value(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    return "; ".join(str(value) for value in values)


def markdown_compact_value(value: Any) -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{" + ", ".join(
            f"{key}={markdown_compact_value(mapped)}"
            for key, mapped in sorted(value.items(), key=lambda item: str(item[0]))
        ) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(markdown_compact_value(item) for item in value) + "]"
    if value is None:
        return "none"
    return markdown_bool(value) if isinstance(value, bool) else str(value)


def markdown_mapping_value(values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return "none"
    return "; ".join(
        f"{key}={markdown_compact_value(value)}"
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))
    )


def unique_string_values(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def prioritized_gate_actions(*action_groups: Any) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in action_groups:
        if not isinstance(group, list):
            continue
        for action in group:
            if not isinstance(action, dict):
                continue
            action_id = action.get("action_id")
            if not isinstance(action_id, str) or not action_id or action_id in seen:
                continue
            seen.add(action_id)
            actions.append(
                {
                    "priority": len(actions) + 1,
                    "action_id": action_id,
                    "gate": action.get("gate"),
                    "title": action.get("title"),
                    "detail": action.get("detail"),
                    **(
                        {"missing_input": action.get("missing_input")}
                        if action.get("missing_input") not in (None, "")
                        else {}
                    ),
                }
            )
    return actions


def first_non_empty_mapping_value(value: dict[str, Any], field_names: tuple[str, ...]) -> Any:
    for field_name in field_names:
        field_value = value.get(field_name)
        if isinstance(field_value, str) and field_value.strip():
            return field_value
        if field_value not in (None, "", [], {}):
            return field_value
    return None


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
SOURCE_AUTHORITY_REVIEW_EVIDENCE_KEYS = (
    "authority_reviewed_by",
    "authority_reviewed_at",
    "authority_review_id",
    "authority_review_url",
)
SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS = (
    "model_identity",
    "provenance",
    "license",
)
SOURCE_AUTHORITY_REVIEW_SCOPE_FIELDS = (
    "review_scope",
    "review_scopes",
    "source_review_scope",
    "source_review_scopes",
)


def normalized_review_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def placeholder_review_evidence(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    stripped = value.strip()
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    normalized = normalized_review_text(value)
    return normalized in PLACEHOLDER_REVIEW_EVIDENCE_VALUES or any(
        normalized.startswith(prefix) for prefix in PLACEHOLDER_REVIEW_EVIDENCE_PREFIXES
    )


def invalid_review_url(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if not isinstance(value, str):
        return True
    parsed = urlparse(value.strip())
    return parsed.scheme not in {"http", "https"} or not parsed.netloc


def invalid_reviewed_at(value: Any) -> bool:
    if value in (None, "", [], {}):
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


def invalid_source_authority_review_evidence(field_name: str, value: Any) -> bool:
    if field_name == "authority_reviewed_at":
        return invalid_reviewed_at(value)
    if field_name != "authority_review_url":
        return False
    return invalid_review_url(value)


def normalized_review_scope_ids(value: Any) -> list[str]:
    raw_values: list[Any]
    if value is None:
        raw_values = []
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
    for field_name in SOURCE_AUTHORITY_REVIEW_SCOPE_FIELDS:
        value = mapping.get(field_name)
        scopes = normalized_review_scope_ids(value)
        if scopes:
            return scopes
    return []


SOURCE_AUTHORITY_REVIEW_EVIDENCE_REQUIRED_GROUPS = (
    ("review_actor", ("authority_reviewed_by",)),
    (
        "review_trace",
        ("authority_reviewed_at", "authority_review_id", "authority_review_url"),
    ),
    ("review_artifact", ("authority_review_id", "authority_review_url")),
)


def source_authority_review_evidence_group_summary(valid_review_fields: set[str]) -> dict[str, Any]:
    required_groups = [
        {"group": group_name, "fields": list(group_fields)}
        for group_name, group_fields in SOURCE_AUTHORITY_REVIEW_EVIDENCE_REQUIRED_GROUPS
    ]
    missing_required_groups = [
        group["group"]
        for group in required_groups
        if not any(field in valid_review_fields for field in group["fields"])
    ]
    satisfied_required_groups = [
        group["group"]
        for group in required_groups
        if any(field in valid_review_fields for field in group["fields"])
    ]
    return {
        "required_groups": required_groups,
        "missing_required_groups": missing_required_groups,
        "satisfied_required_groups": satisfied_required_groups,
    }


def so101_source_authority_review_forwarding(
    *,
    args: argparse.Namespace,
    bundle: dict[str, Any] | None,
    bundle_inventory_forwarding: dict[str, Any],
) -> dict[str, Any]:
    values = {
        "authority_reviewed_by": args.so101_source_authority_reviewed_by,
        "authority_reviewed_at": args.so101_source_authority_reviewed_at,
        "authority_review_id": args.so101_source_authority_review_id,
        "authority_review_url": args.so101_source_authority_review_url,
        "authority_source_reference": args.so101_source_authority_source_reference,
        "authority_review_scope_ids": normalized_review_scope_ids(
            args.so101_source_authority_review_scope
        ),
        "authority_license_basis": args.so101_source_authority_license_basis,
    }
    explicit_values = {key: value for key, value in values.items() if value}
    source = "explicit_cli" if explicit_values else "not_supplied"

    if not explicit_values and bundle_inventory_forwarding.get("used_for_source_inventory") is True:
        bundle = bundle if isinstance(bundle, dict) else {}
        authority = bundle.get("authority")
        authority = authority if isinstance(authority, dict) else {}
        authority_value = authority.get("value")
        authority_value = authority_value if isinstance(authority_value, dict) else {}
        provenance = bundle.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        provenance_value = provenance.get("value")
        provenance_value = provenance_value if isinstance(provenance_value, dict) else {}
        values = {
            "authority_reviewed_by": first_non_empty_mapping_value(authority_value, ("reviewed_by",)),
            "authority_reviewed_at": first_non_empty_mapping_value(authority_value, ("reviewed_at",)),
            "authority_review_id": first_non_empty_mapping_value(authority_value, ("review_id",)),
            "authority_review_url": first_non_empty_mapping_value(authority_value, ("review_url",)),
            "authority_source_reference": first_non_empty_mapping_value(
                provenance_value,
                ("source_url", "source_uri", "cad_url", "repository_url", "source_path", "source_reference"),
            ),
            "authority_review_scope_ids": mapping_review_scope_ids(authority_value)
            or mapping_review_scope_ids(provenance_value),
            "authority_license_basis": first_non_empty_mapping_value(
                provenance_value,
                ("license", "license_url", "license_file", "license_review", "license_basis"),
            ),
        }
        source = "so101_model_bundle_manifest"

    supplied_review_fields = [
        key for key in SOURCE_AUTHORITY_REVIEW_EVIDENCE_KEYS if values.get(key)
    ]
    placeholder_review_fields = [
        key for key in supplied_review_fields if placeholder_review_evidence(values.get(key))
    ]
    invalid_review_fields = [
        key
        for key in supplied_review_fields
        if key not in placeholder_review_fields
        and invalid_source_authority_review_evidence(key, values.get(key))
    ]
    valid_review_fields = [
        key
        for key in supplied_review_fields
        if key not in placeholder_review_fields and key not in invalid_review_fields
    ]
    review_evidence_groups = source_authority_review_evidence_group_summary(
        set(valid_review_fields)
    )
    supplied_review_scope_ids = normalized_review_scope_ids(
        values.get("authority_review_scope_ids")
    )
    missing_review_scope_ids = [
        scope
        for scope in SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS
        if scope not in supplied_review_scope_ids
    ]
    missing_required_fields = []
    diagnostics = [f"authority_review_evidence_placeholder:{field}" for field in placeholder_review_fields]
    diagnostics.extend(
        f"authority_review_evidence_invalid:{field}" for field in invalid_review_fields
    )
    required_metadata = {
        "authority_source_reference": values.get("authority_source_reference"),
        "authority_license_basis": values.get("authority_license_basis"),
    }
    supplied_required_metadata = {
        key: value for key, value in required_metadata.items() if value
    }
    required_metadata_placeholder_fields = [
        key
        for key, value in supplied_required_metadata.items()
        if placeholder_review_evidence(value)
    ]
    valid_required_metadata_fields = [
        key
        for key in supplied_required_metadata
        if key not in required_metadata_placeholder_fields
    ]
    diagnostics.extend(
        f"authority_required_metadata_placeholder:{field}"
        for field in required_metadata_placeholder_fields
    )
    diagnostics.extend(
        f"authority_review_evidence_missing_required_group:{group}"
        for group in review_evidence_groups["missing_required_groups"]
    )
    if not valid_review_fields:
        missing_required_fields.append("authority_review_evidence")
    else:
        missing_required_fields.extend(
            f"authority_review_evidence:{group}"
            for group in review_evidence_groups["missing_required_groups"]
        )
    missing_required_fields.extend(
        f"authority_review_scope:{scope}" for scope in missing_review_scope_ids
    )
    for field in required_metadata:
        if field not in valid_required_metadata_fields:
            missing_required_fields.append(field)
    return {
        "source": source,
        "ready_if_authoritative_source_declared": (
            not missing_required_fields
            and not placeholder_review_fields
            and not invalid_review_fields
            and not required_metadata_placeholder_fields
        ),
        "missing_required_fields": missing_required_fields,
        "required_review_scope_ids": list(SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
        "supplied_review_scope_ids": supplied_review_scope_ids,
        "missing_review_scope_ids": missing_review_scope_ids,
        "review_scope_ready": not missing_review_scope_ids,
        "review_evidence_valid_fields": valid_review_fields,
        "review_evidence_placeholder_fields": placeholder_review_fields,
        "review_evidence_invalid_fields": invalid_review_fields,
        "required_metadata_fields": sorted(required_metadata),
        "required_metadata_valid_fields": sorted(valid_required_metadata_fields),
        "required_metadata_placeholder_fields": sorted(required_metadata_placeholder_fields),
        "review_evidence_required_groups": review_evidence_groups["required_groups"],
        "review_evidence_satisfied_required_groups": review_evidence_groups[
            "satisfied_required_groups"
        ],
        "review_evidence_missing_required_groups": review_evidence_groups[
            "missing_required_groups"
        ],
        "diagnostics": diagnostics,
        **values,
        "notes": [
            "These values are forwarded only to the SO-101 model-source inventory.",
            "Placeholder review evidence, source references, or license bases such as TODO/TBD/unknown or unedited <...> template tokens do not satisfy source-authority readiness.",
            "If authority_reviewed_at is supplied, it must be an ISO YYYY-MM-DD date or ISO datetime and must not be in the future.",
            "Source-authority review evidence requires reviewer identity plus a stable artifact handle: authority_review_id or authority_review_url.",
            "Source-authority readiness also requires explicit review scopes for model identity, provenance, and license, plus a non-placeholder source reference and license basis.",
            "They do not replace the bundle manifest's reviewed authority/provenance/readiness gate.",
        ],
    }


def so101_model_source_inventory_config(
    args: argparse.Namespace,
    *,
    model_source_roots: list[Path],
    model_source_extra_roots: list[Path],
    authoritative_model_paths: list[Path],
    authoritative_model_roots: list[Path],
    bundle_inventory_forwarding: dict[str, Any],
    source_authority_review: dict[str, Any],
    effective_ik_model_path: Path | None,
) -> dict[str, Any]:
    roots = cli_path_values(model_source_roots)
    extra_roots = cli_path_values(model_source_extra_roots)
    authoritative_paths = cli_path_values(authoritative_model_paths)
    authoritative_roots = cli_path_values(authoritative_model_roots)
    return {
        "scan_mode": "explicit_roots" if roots else "default_repo_roots",
        "model_source_roots": roots,
        "model_source_extra_roots": extra_roots,
        "authoritative_model_paths": authoritative_paths,
        "authoritative_model_roots": authoritative_roots,
        "source_authority_review": source_authority_review,
        "model_source_root_source": bundle_inventory_forwarding.get("model_source_root_source"),
        "authoritative_model_path_source": bundle_inventory_forwarding.get(
            "authoritative_model_path_source"
        ),
        "ik_model_path_is_authority": False,
        "ik_model_path_forwarded_to_inventory": False,
        "ik_model_path": (
            str(effective_ik_model_path.expanduser()) if effective_ik_model_path is not None else None
        ),
        "explicit_ik_model_path": (
            str(args.ik_model_path.expanduser()) if args.ik_model_path is not None else None
        ),
        "bundle_manifest": bundle_inventory_forwarding,
        "notes": [
            "--ik-model-path is forwarded only to the model contract checker and IK reachability drill.",
            "Inventory authority must be declared with --so101-authoritative-model-path or --so101-authoritative-model-root.",
            "Inventory source-authority review metadata is forwarded separately and does not replace the reviewed bundle manifest gate.",
            "Only a physically reviewed ready bundle manifest may supply an inventory root and authoritative path when no explicit inventory source options were supplied.",
        ],
    }


def so101_inventory_forwarding_decision(
    *,
    args: argparse.Namespace,
    bundle_forwarding: dict[str, Any],
) -> tuple[list[Path], list[Path], list[Path], list[Path], dict[str, Any]]:
    explicit_source_inputs = any(
        [
            args.so101_model_source_root,
            args.so101_model_source_extra_root,
            args.so101_authoritative_model_path,
            args.so101_authoritative_model_root,
        ]
    )
    roots = list(args.so101_model_source_root)
    extra_roots = list(args.so101_model_source_extra_root)
    authoritative_paths = list(args.so101_authoritative_model_path)
    authoritative_roots = list(args.so101_authoritative_model_root)
    model_path = path_from_string(bundle_forwarding.get("model_path"))
    physical_authority_ready = (
        bundle_forwarding.get("physical_so101_model_authority_ready") is True
    )
    fixture_ready = bundle_forwarding.get("hardware_free_regression_fixture_ready") is True
    use_bundle = (
        bundle_forwarding.get("ready_for_model_backed_ik") is True
        and physical_authority_ready
        and not explicit_source_inputs
        and model_path is not None
    )
    if use_bundle:
        roots = [model_path]
        authoritative_paths = [model_path]

    reason = None
    if explicit_source_inputs:
        reason = "explicit_source_inventory_inputs_supplied"
    elif bundle_forwarding.get("ready_for_model_backed_ik") is not True:
        reason = f"bundle_not_ready_for_inventory_authority:{bundle_forwarding.get('manifest_status')}"
    elif not physical_authority_ready:
        reason = (
            "bundle_ready_fixture_not_physical_source_authority"
            if fixture_ready
            else "bundle_ready_without_physical_source_authority"
        )
    elif model_path is None:
        reason = "bundle_ready_without_model_path"

    forwarding = {
        "used_for_source_inventory": use_bundle,
        "diagnostic_only": not use_bundle,
        "diagnostic_only_reason": None if use_bundle else reason,
        "requires_physical_so101_model_authority": True,
        "physical_so101_model_authority_ready": physical_authority_ready,
        "hardware_free_regression_fixture_ready": fixture_ready,
        "model_source_root_source": "so101_model_bundle_manifest" if use_bundle else (
            "explicit_cli" if args.so101_model_source_root else "default_repo_roots"
        ),
        "authoritative_model_path_source": "so101_model_bundle_manifest" if use_bundle else (
            "explicit_cli" if args.so101_authoritative_model_path else "not_supplied"
        ),
        "manifest_status": bundle_forwarding.get("manifest_status"),
        "ready_for_model_backed_ik": bundle_forwarding.get("ready_for_model_backed_ik"),
        "model_path": str(model_path) if model_path is not None else None,
        "notes": [
            "The bundle manifest supplies source-inventory authority only when ready_for_model_backed_ik and physical_so101_model_authority_ready are both true.",
            "Hardware-free fixture-ready bundles may still feed contract/IK regression, but they do not become source-inventory authority.",
            "Explicit source inventory CLI options take precedence over bundle-derived inventory inputs.",
        ],
    }
    return roots, extra_roots, authoritative_paths, authoritative_roots, forwarding


def so101_model_contract_config(
    args: argparse.Namespace,
    *,
    effective_ik_model_path: Path | None,
    effective_asset_roots: list[Path],
    bundle_forwarding: dict[str, Any],
) -> dict[str, Any]:
    explicit_asset_roots = cli_path_values(args.ik_model_asset_root)
    asset_roots = cli_path_values(effective_asset_roots)
    return {
        "ik_model_path": (
            str(effective_ik_model_path.expanduser())
            if effective_ik_model_path is not None
            else None
        ),
        "explicit_ik_model_path": (
            str(args.ik_model_path.expanduser()) if args.ik_model_path is not None else None
        ),
        "ik_model_path_source": bundle_forwarding.get("ik_model_path_source"),
        "ik_model_asset_roots": asset_roots,
        "explicit_ik_model_asset_roots": explicit_asset_roots,
        "ik_model_asset_root_source": bundle_forwarding.get("ik_model_asset_root_source"),
        "asset_root_forwarded_to_ik_reachability": False,
        "ik_model_path_is_authority": False,
        "bundle_manifest": bundle_forwarding,
        "notes": [
            "The effective ik_model_path is forwarded to the contract checker and IK reachability drill.",
            "The effective ik_model_asset_roots are forwarded only to the contract checker asset preflight.",
            "Mesh/assets roots do not mark model-source authority and do not change RobotKinematics arguments.",
            "Manifest-derived model path and asset roots are used only when ready_for_model_backed_ik is true and no explicit --ik-model-path was supplied.",
        ],
    }


def so101_model_bundle_manifest_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "supplied": args.so101_model_bundle_manifest is not None,
        "requested_path": (
            str(args.so101_model_bundle_manifest.expanduser())
            if args.so101_model_bundle_manifest is not None
            else None
        ),
        "notes": [
            "The bundle manifest checker runs in every suite invocation.",
            "No supplied manifest is recorded as explicit non-failing evidence.",
            "Manifest data is diagnostic-only unless the checker reports ready_for_model_backed_ik true.",
        ],
    }


def so101_model_bundle_manifest_command(
    *,
    python: str,
    bundle_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_manifest.py"),
        "--output-dir",
        str(bundle_dir),
        "--python",
        python,
    ]
    if args.so101_model_bundle_manifest is not None:
        command.extend(["--manifest-path", str(args.so101_model_bundle_manifest.expanduser())])
    return command


def path_from_string(value: Any) -> Path | None:
    if isinstance(value, str) and value:
        return Path(value).expanduser()
    return None


def paths_from_strings(values: Any) -> list[Path]:
    if not isinstance(values, list):
        return []
    return [Path(value).expanduser() for value in values if isinstance(value, str) and value]


def so101_bundle_forwarding_decision(
    *,
    args: argparse.Namespace,
    bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    bundle = bundle if isinstance(bundle, dict) else {}
    manifest_request = bundle.get("manifest_request")
    manifest_request = manifest_request if isinstance(manifest_request, dict) else {}
    model_path = bundle.get("model_path")
    model_path = model_path if isinstance(model_path, dict) else {}
    asset_roots = bundle.get("asset_roots")
    asset_roots = asset_roots if isinstance(asset_roots, dict) else {}
    ready = bundle.get("ready_for_model_backed_ik") is True
    physical_authority_ready = bundle.get("physical_so101_model_authority_ready") is True
    fixture_ready = bundle.get("hardware_free_regression_fixture_ready") is True
    explicit_model_path = args.ik_model_path is not None
    explicit_asset_roots = bool(args.ik_model_asset_root)
    manifest_status = bundle.get("status") or manifest_request.get("status")
    bundle_model_path = path_from_string(model_path.get("path"))
    bundle_asset_roots = paths_from_strings(asset_roots.get("asset_roots"))

    effective_model_path = args.ik_model_path
    effective_asset_roots = list(args.ik_model_asset_root)
    model_path_source = "explicit_cli" if explicit_model_path else "not_supplied"
    asset_root_source = "explicit_cli" if explicit_asset_roots else "not_supplied"
    diagnostic_only_reason: str | None = None
    downstream_model_path_forwarded = False
    downstream_asset_roots_forwarded = False

    if explicit_model_path:
        diagnostic_only_reason = "explicit_ik_model_path_supplied"
    elif not ready:
        diagnostic_only_reason = f"bundle_not_ready_for_model_backed_ik:{manifest_status}"
    elif bundle_model_path is None:
        diagnostic_only_reason = "bundle_ready_without_model_path"
    else:
        effective_model_path = bundle_model_path
        model_path_source = "so101_model_bundle_manifest"
        downstream_model_path_forwarded = True
        if explicit_asset_roots:
            asset_root_source = "explicit_cli"
        else:
            effective_asset_roots = bundle_asset_roots
            asset_root_source = "so101_model_bundle_manifest"
            downstream_asset_roots_forwarded = bool(bundle_asset_roots)

    return {
        "manifest_supplied": manifest_request.get("path") is not None,
        "manifest_request_status": manifest_request.get("status"),
        "manifest_status": manifest_status,
        "manifest_path": manifest_request.get("path"),
        "ready_for_model_backed_ik": ready,
        "physical_so101_model_authority_ready": physical_authority_ready,
        "hardware_free_regression_fixture_ready": fixture_ready,
        "model_authority": bundle.get("model_authority"),
        "physical_authority_gate_status": bundle.get("physical_authority_gate_status"),
        "synthetic_fixture_authority_fields": bundle.get(
            "synthetic_fixture_authority_fields"
        )
        or [],
        "model_path": str(bundle_model_path) if bundle_model_path is not None else None,
        "asset_roots": [str(path) for path in bundle_asset_roots],
        "explicit_ik_model_path_supplied": explicit_model_path,
        "explicit_ik_model_asset_roots_supplied": explicit_asset_roots,
        "used_for_downstream_contract": downstream_model_path_forwarded,
        "used_for_downstream_ik": downstream_model_path_forwarded,
        "used_for_downstream_asset_preflight": downstream_asset_roots_forwarded or explicit_asset_roots,
        "diagnostic_only": not downstream_model_path_forwarded,
        "diagnostic_only_reason": diagnostic_only_reason,
        "effective_ik_model_path": (
            str(effective_model_path.expanduser()) if effective_model_path is not None else None
        ),
        "effective_ik_model_asset_roots": [str(path.expanduser()) for path in effective_asset_roots],
        "ik_model_path_source": model_path_source,
        "ik_model_asset_root_source": asset_root_source,
        "notes": [
            "Manifest data is not forwarded to contract or IK unless ready_for_model_backed_ik is true.",
            "An explicit --ik-model-path takes precedence over the bundle manifest.",
            "An explicit --ik-model-asset-root list takes precedence for contract asset preflight roots.",
        ],
    }


def so101_model_source_inventory_command(
    *,
    python: str,
    inventory_dir: Path,
    model_source_roots: list[Path],
    model_source_extra_roots: list[Path],
    authoritative_model_paths: list[Path],
    authoritative_model_roots: list[Path],
    source_authority_review: dict[str, Any],
) -> list[str]:
    command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_so101_model_source_inventory.py"),
        "--output-dir",
        str(inventory_dir),
    ]
    for root in model_source_roots:
        command.extend(["--root", str(root.expanduser())])
    for root in model_source_extra_roots:
        command.extend(["--extra-root", str(root.expanduser())])
    for path in authoritative_model_paths:
        command.extend(["--authoritative-path", str(path.expanduser())])
    for root in authoritative_model_roots:
        command.extend(["--authoritative-root", str(root.expanduser())])
    for source_key, cli_name in (
        ("authority_reviewed_by", "--authority-reviewed-by"),
        ("authority_reviewed_at", "--authority-reviewed-at"),
        ("authority_review_id", "--authority-review-id"),
        ("authority_review_url", "--authority-review-url"),
        ("authority_source_reference", "--authority-source-reference"),
        ("authority_license_basis", "--authority-license-basis"),
    ):
        value = source_authority_review.get(source_key)
        if value:
            command.extend([cli_name, str(value)])
    for scope_id in source_authority_review.get("supplied_review_scope_ids") or []:
        command.extend(["--authority-review-scope", str(scope_id)])
    return command


def recommended_contract_model_path(inventory: dict[str, Any] | None) -> Path | None:
    inventory = inventory if isinstance(inventory, dict) else {}
    recommended = inventory.get("recommended_contract_check")
    recommended = recommended if isinstance(recommended, dict) else {}
    candidate_path = recommended.get("candidate_path")
    return path_from_string(candidate_path)


def so101_model_bundle_probe_command(
    *,
    python: str,
    probe_dir: Path,
    model_path: Path | None,
    asset_roots: list[Path],
    target_frame: str,
    source_authority_review: dict[str, Any],
) -> list[str]:
    command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_probe.py"),
        "--output-dir",
        str(probe_dir),
        "--python",
        python,
        "--target-frame",
        target_frame,
    ]
    if model_path is not None:
        command.extend(["--model-path", str(model_path.expanduser())])
    if (
        model_path is not None
        and source_authority_review.get("ready_if_authoritative_source_declared") is True
    ):
        for source_key, cli_name in (
            ("authority_reviewed_by", "--authority-reviewed-by"),
            ("authority_reviewed_at", "--authority-reviewed-at"),
            ("authority_review_id", "--authority-review-id"),
            ("authority_review_url", "--authority-review-url"),
        ):
            value = source_authority_review.get(source_key)
            if value:
                command.extend([cli_name, str(value)])
        for scope_id in source_authority_review.get("supplied_review_scope_ids") or []:
            command.extend(["--authority-review-scope", str(scope_id)])
    for asset_root in asset_roots:
        command.extend(["--asset-root", str(asset_root.expanduser())])
    return command


def reference_media_inventory_command(
    *,
    python: str,
    inventory_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_inventory.py"),
        "--output-dir",
        str(inventory_dir),
    ]
    for root in args.reference_media_root:
        command.extend(["--root", str(root.expanduser())])
    if args.reference_media_manifest is not None:
        command.extend(["--manifest", str(args.reference_media_manifest.expanduser())])
    return command


def reference_media_inventory_config(args: argparse.Namespace) -> dict[str, Any]:
    roots = cli_path_values(args.reference_media_root)
    return {
        "scan_mode": "explicit_roots" if roots else "repo_root_only",
        "reference_media_roots": roots,
        "manifest": (
            str(args.reference_media_manifest.expanduser())
            if args.reference_media_manifest is not None
            else None
        ),
        "notes": [
            "The default suite scan invokes the inventory without --root, which scans repo_root only.",
            "Supplying --reference-media-root forwards repeatable --root values to the inventory child.",
            "Roots are evidence inputs only; the suite does not copy or claim authority over media assets.",
        ],
    }


def reference_media_inventory_artifact_paths(
    inventory: dict[str, Any] | None,
    inventory_dir: Path,
) -> dict[str, str]:
    inventory = inventory if isinstance(inventory, dict) else {}
    return {
        "summary_json": str(
            inventory.get("output_path") or inventory_dir / REFERENCE_MEDIA_INVENTORY_JSON_NAME
        ),
        "csv": str(inventory.get("csv_path") or inventory_dir / REFERENCE_MEDIA_INVENTORY_CSV_NAME),
        "readme_md": str(
            inventory.get("readme_path") or inventory_dir / REFERENCE_MEDIA_INVENTORY_README_NAME
        ),
    }


def reference_media_inventory_counts(inventory: dict[str, Any] | None) -> dict[str, Any]:
    inventory = inventory if isinstance(inventory, dict) else {}
    summary = inventory.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    return {
        "status": inventory.get("status") or summary.get("status"),
        "candidate_count": summary.get("candidate_count", 0),
        "media_count": summary.get("media_count", 0),
        "image_count": summary.get("image_count", 0),
        "video_count": summary.get("video_count", 0),
        "calibration_data_count": summary.get("calibration_data_count", 0),
        "currently_wired_media_count": summary.get("currently_wired_media_count", 0),
        "reference_gaps": inventory.get("reference_gaps") or summary.get("reference_gaps") or [],
        "current_gripper_reference": {
            "detected": summary.get("active_current_gripper_reference_detected"),
            "path": summary.get("active_current_gripper_reference_path"),
        },
    }


def reference_media_inventory_child_diagnostics(
    *,
    inventory: dict[str, Any] | None,
    inventory_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    inventory = inventory if isinstance(inventory, dict) else {}
    scan = inventory.get("scan")
    scan = scan if isinstance(scan, dict) else {}
    return {
        **reference_media_inventory_counts(inventory),
        "artifact_paths": reference_media_inventory_artifact_paths(inventory, inventory_dir),
        "scan": {
            "roots": scan.get("roots"),
            "default_scan_scope": scan.get("default_scan_scope"),
            "scan_issues": scan.get("scan_issues"),
        },
        "source_configuration": config,
    }


def reference_media_inventory_section(
    *,
    inventory: dict[str, Any] | None,
    inventory_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    inventory = inventory if isinstance(inventory, dict) else {}
    paths = reference_media_inventory_artifact_paths(inventory, inventory_dir)
    diagnostics = reference_media_inventory_child_diagnostics(
        inventory=inventory,
        inventory_dir=inventory_dir,
        config=config,
    )
    return {
        "ok": bool(inventory.get("ok", False)),
        "summary_path": paths["summary_json"],
        "csv_path": paths["csv"],
        "readme_path": paths["readme_md"],
        "output_dir": str(inventory_dir),
        "artifact_paths": paths,
        "summary": inventory.get("summary"),
        "manifest_summary": inventory.get("manifest_summary"),
        "next_recommended_reference_fixture_inputs": inventory.get(
            "next_recommended_reference_fixture_inputs"
        ),
        "visibility_gaps": inventory.get("visibility_gaps"),
        "scan": inventory.get("scan"),
        "source_configuration": config,
        **diagnostics,
    }


def reference_media_inventory_empty(inventory: dict[str, Any] | None) -> bool:
    counts = reference_media_inventory_counts(inventory)
    return counts.get("status") == "media_inventory_empty" or int(counts.get("candidate_count") or 0) == 0


def reference_capture_manifest_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "supplied": args.reference_capture_manifest is not None,
        "requested_path": (
            str(args.reference_capture_manifest.expanduser())
            if args.reference_capture_manifest is not None
            else None
        ),
        "notes": [
            "The capture manifest checker runs in every suite invocation.",
            "No supplied manifest is recorded as explicit non-failing input-readiness evidence.",
            "The checker validates local path/readiness metadata only and never copies media assets.",
        ],
    }


def reference_capture_manifest_command(
    *,
    python: str,
    manifest_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_reference_capture_manifest.py"),
        "--output-dir",
        str(manifest_dir),
    ]
    if args.reference_capture_manifest is not None:
        command.extend(["--manifest-path", str(args.reference_capture_manifest.expanduser())])
    return command


def reference_capture_manifest_artifact_paths(
    manifest: dict[str, Any] | None,
    manifest_dir: Path,
) -> dict[str, str]:
    manifest = manifest if isinstance(manifest, dict) else {}
    return {
        "summary_json": str(
            manifest.get("summary_path") or manifest_dir / REFERENCE_CAPTURE_MANIFEST_JSON_NAME
        ),
        "csv": str(manifest.get("csv_path") or manifest_dir / REFERENCE_CAPTURE_MANIFEST_CSV_NAME),
        "readme_md": str(
            manifest.get("readme_path") or manifest_dir / REFERENCE_CAPTURE_MANIFEST_README_NAME
        ),
    }


def reference_capture_manifest_path_check_counts(manifest: dict[str, Any]) -> dict[str, int]:
    path_checks = manifest.get("path_checks")
    path_checks = [row for row in path_checks if isinstance(row, dict)] if isinstance(path_checks, list) else []
    missing_path_checks = manifest.get("missing_path_checks")
    missing_path_checks = (
        [row for row in missing_path_checks if isinstance(row, dict)]
        if isinstance(missing_path_checks, list)
        else []
    )
    media_count = sum(1 for row in path_checks if row.get("category") == "media")
    sidecar_count = sum(1 for row in path_checks if row.get("category") == "sidecar")
    return {
        "path_check_count": len(path_checks),
        "media_path_check_count": media_count,
        "sidecar_path_check_count": sidecar_count,
        "missing_path_count": len(missing_path_checks),
        "present_path_count": len(path_checks) - len(missing_path_checks),
    }


def reference_capture_manifest_section(
    *,
    manifest: dict[str, Any] | None,
    manifest_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {}
    paths = reference_capture_manifest_artifact_paths(manifest, manifest_dir)
    diagnostics = manifest.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    path_counts = reference_capture_manifest_path_check_counts(manifest)
    return {
        "ok": bool(manifest.get("ok", False)),
        "status": manifest.get("status"),
        "summary_path": paths["summary_json"],
        "csv_path": paths["csv"],
        "readme_path": paths["readme_md"],
        "output_dir": str(manifest_dir),
        "artifact_paths": paths,
        "source_configuration": config,
        "manifest_path": manifest.get("manifest_path"),
        "manifest_schema": manifest.get("manifest_schema"),
        "expected_manifest_schema": manifest.get("expected_manifest_schema"),
        "ready_for_calibration_grade_simcamera_tuning": bool(
            manifest.get("ready_for_calibration_grade_simcamera_tuning", False)
        ),
        "depth_reference_capture_count": int(manifest.get("depth_reference_capture_count") or 0),
        "pick_place_video_capture_count": int(manifest.get("pick_place_video_capture_count") or 0),
        "diagnostics": diagnostics,
        "gaps": diagnostics,
        "media_assets_copied_into_repo": manifest.get("media_assets_copied_into_repo", False),
        "local_only_no_copy_policy": manifest.get("local_only_no_copy_policy"),
        "provenance_present": manifest.get("provenance_present"),
        "review_present": manifest.get("review_present"),
        "path_checks": manifest.get("path_checks") if isinstance(manifest.get("path_checks"), list) else [],
        "missing_path_checks": (
            manifest.get("missing_path_checks")
            if isinstance(manifest.get("missing_path_checks"), list)
            else []
        ),
        **path_counts,
        "notes": [
            "This is an input-readiness gate for local real-reference captures and sidecars.",
            "Readiness does not claim physical calibration accuracy or mutate SimCamera tuning.",
            "Media assets are never copied into the repository or suite artifact directory.",
        ],
    }


def real_depth_capture_plan_artifact_index_command(*, python: str, index_dir: Path) -> list[str]:
    return [
        python,
        str(REPO_ROOT / "scripts" / "smoke_real_depth_capture_plan_artifact_index.py"),
        "--output-dir",
        str(index_dir),
        "--python",
        python,
    ]


def real_depth_capture_plan_artifact_paths(
    index: dict[str, Any] | None,
    index_dir: Path,
) -> dict[str, str]:
    index = index if isinstance(index, dict) else {}
    return {
        "summary_json": str(
            index.get("artifact_index_path")
            or index_dir / REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_JSON_NAME
        ),
        "csv": str(
            index.get("csv_path") or index_dir / REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_CSV_NAME
        ),
        "readme_md": str(
            index.get("readme_path")
            or index_dir / REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_README_NAME
        ),
    }


def int_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def unique_strings(values: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def real_depth_capture_plan_artifact_index_section(
    index: dict[str, Any] | None,
    index_dir: Path,
) -> dict[str, Any]:
    index = index if isinstance(index, dict) else {}
    paths = real_depth_capture_plan_artifact_paths(index, index_dir)
    cases = index.get("cases")
    cases = [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    ready_cases = [
        str(case.get("case_id"))
        for case in cases
        if case.get("ready_for_calibration_grade_simcamera_tuning") is True and case.get("case_id")
    ]
    not_ready_cases = [
        str(case.get("case_id"))
        for case in cases
        if case.get("ready_for_calibration_grade_simcamera_tuning") is not True
        and case.get("case_id")
    ]
    evidence_statuses = unique_strings([case.get("evidence_status") for case in cases])
    no_copy_statuses = unique_strings([case.get("no_copy_status") for case in cases])
    next_operator_action_ids = unique_strings(
        [
            action_id
            for case in cases
            for action_id in (
                case.get("next_operator_action_ids")
                if isinstance(case.get("next_operator_action_ids"), list)
                else []
            )
        ]
    )
    bridge_smoke = index.get("bridge_smoke")
    bridge_smoke = bridge_smoke if isinstance(bridge_smoke, dict) else {}
    caveats = unique_strings(
        [
            *(
                index.get("caveats")
                if isinstance(index.get("caveats"), list)
                else []
            ),
            REAL_DEPTH_CAPTURE_PLAN_INPUT_READINESS_CAVEAT,
        ]
    )
    case_summaries = [
        {
            "case_id": case.get("case_id"),
            "scenario_label": case.get("scenario_label"),
            "evidence_source_kind": case.get("evidence_source_kind"),
            "evidence_status": case.get("evidence_status"),
            "ready_for_calibration_grade_simcamera_tuning": bool(
                case.get("ready_for_calibration_grade_simcamera_tuning")
            ),
            "depth_reference_capture_count": int_count(
                case.get("depth_reference_capture_count")
            ),
            "pick_place_video_capture_count": int_count(
                case.get("pick_place_video_capture_count")
            ),
            "missing_path_count": int_count(case.get("missing_path_count")),
            "no_copy_status": case.get("no_copy_status"),
            "next_operator_action_count": len(
                case.get("next_operator_action_ids")
                if isinstance(case.get("next_operator_action_ids"), list)
                else []
            ),
            "next_operator_action_ids": (
                case.get("next_operator_action_ids")
                if isinstance(case.get("next_operator_action_ids"), list)
                else []
            ),
            "planner_json_path": case.get("planner_json_path"),
            "planner_markdown_path": case.get("planner_markdown_path"),
        }
        for case in cases
    ]
    return {
        "ok": bool(index.get("ok", False)),
        "status": index.get("status"),
        "summary_path": paths["summary_json"],
        "csv_path": paths["csv"],
        "readme_path": paths["readme_md"],
        "output_dir": str(index_dir),
        "artifact_paths": paths,
        "source_mode": index.get("source_mode"),
        "case_count": int_count(index.get("case_count", len(cases))),
        "evidence_statuses": evidence_statuses,
        "ready_case_count": len(ready_cases),
        "not_ready_case_count": len(not_ready_cases),
        "ready_case_ids": ready_cases,
        "not_ready_case_ids": not_ready_cases,
        "depth_reference_capture_count": sum(
            int_count(case.get("depth_reference_capture_count")) for case in cases
        ),
        "pick_place_video_capture_count": sum(
            int_count(case.get("pick_place_video_capture_count")) for case in cases
        ),
        "missing_path_count": sum(int_count(case.get("missing_path_count")) for case in cases),
        "no_copy_statuses": no_copy_statuses,
        "next_operator_action_count": len(next_operator_action_ids),
        "next_operator_action_ids": next_operator_action_ids,
        "bridge_smoke_summary_json": index.get("bridge_smoke_summary_json"),
        "bridge_smoke_status": bridge_smoke.get("status"),
        "bridge_smoke_ok": bridge_smoke.get("ok"),
        "bridge_smoke_child_run": index.get("bridge_smoke_child_run"),
        "bridge_smoke": bridge_smoke,
        "media_assets_copied_into_repo": index.get("media_assets_copied_into_repo", False),
        "media_assets_opened_or_decoded": index.get("media_assets_opened_or_decoded", False),
        "input_readiness_only": True,
        "physical_calibration_truth": False,
        "case_summaries": case_summaries,
        "cases": cases,
        "caveats": caveats,
        "notes": [
            "This hardware-free child runs the real-depth operator plan artifact index under the suite output directory.",
            "Ready evidence is input readiness only, not physical calibration truth.",
            "Photos and videos are not copied, opened, decoded, modified, or committed by this child.",
        ],
    }


def write_artifact_entrypoint_readme(output_dir: Path, summary: dict[str, Any]) -> Path:
    markers = summary.get("skipped_markers")
    markers = markers if isinstance(markers, dict) else {}
    manifest = summary.get("reference_media_manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    manifest_supplied = bool(manifest.get("supplied"))
    reference_inventory = summary.get("reference_media_inventory")
    reference_inventory = (
        reference_inventory
        if isinstance(reference_inventory, dict)
        else summary.get("inventory")
        if isinstance(summary.get("inventory"), dict)
        else {}
    )
    comparison_set = summary.get("comparison_set")
    comparison_set = comparison_set if isinstance(comparison_set, dict) else {}
    profile_sweep = summary.get("sim_camera_profile_sweep")
    profile_sweep = profile_sweep if isinstance(profile_sweep, dict) else {}
    profile_sweep_metrics = profile_sweep.get("current_vs_best_metrics")
    profile_sweep_metrics = profile_sweep_metrics if isinstance(profile_sweep_metrics, dict) else {}
    profile_sweep_paths = profile_sweep.get("artifact_paths")
    profile_sweep_paths = profile_sweep_paths if isinstance(profile_sweep_paths, dict) else {}
    profile_sweep_prompts = profile_sweep.get("remaining_tuning_prompts")
    profile_sweep_prompts = profile_sweep_prompts if isinstance(profile_sweep_prompts, list) else []
    profile_sweep_prompt_ids = [
        prompt.get("candidate_id")
        for prompt in profile_sweep_prompts
        if isinstance(prompt, dict) and prompt.get("candidate_id")
    ]
    tuning_before_after = summary.get("simcamera_tuning_before_after")
    tuning_before_after = tuning_before_after if isinstance(tuning_before_after, dict) else {}
    tuning_before_after_paths = tuning_before_after.get("artifact_paths")
    tuning_before_after_paths = (
        tuning_before_after_paths if isinstance(tuning_before_after_paths, dict) else {}
    )
    tuning_before_after_prompt_ids = sim_camera_tuning_prompt_ids(
        tuning_before_after.get("remaining_tuning_prompts")
    )
    reference_capture_manifest = summary.get("reference_capture_manifest")
    reference_capture_manifest = (
        reference_capture_manifest if isinstance(reference_capture_manifest, dict) else {}
    )
    reference_capture_manifest_paths = reference_capture_manifest.get("artifact_paths")
    reference_capture_manifest_paths = (
        reference_capture_manifest_paths
        if isinstance(reference_capture_manifest_paths, dict)
        else {}
    )
    real_depth_plan_index = summary.get("real_depth_capture_plan_artifact_index")
    real_depth_plan_index = real_depth_plan_index if isinstance(real_depth_plan_index, dict) else {}
    real_depth_plan_index_paths = real_depth_plan_index.get("artifact_paths")
    real_depth_plan_index_paths = (
        real_depth_plan_index_paths if isinstance(real_depth_plan_index_paths, dict) else {}
    )
    reference_inventory_counts_row = reference_media_inventory_counts(reference_inventory)
    reference_gap_ids = {
        str(gap) for gap in reference_inventory_counts_row.get("reference_gaps", []) if gap
    }
    visibility_gap_rows = reference_inventory.get("visibility_gaps")
    visibility_gap_rows = visibility_gap_rows if isinstance(visibility_gap_rows, list) else []
    failure_mode_gap = any(
        isinstance(row, dict)
        and row.get("category") == "failure_mode"
        and row.get("status") == "missing"
        for row in visibility_gap_rows
    )
    visual_review = summary.get("visual_review")
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    recording = visual_review.get("recording")
    recording = recording if isinstance(recording, dict) else {}
    so101_inventory = summary.get("so101_model_source_inventory")
    so101_inventory = so101_inventory if isinstance(so101_inventory, dict) else {}
    so101_source_config = so101_inventory.get("source_configuration")
    so101_source_config = so101_source_config if isinstance(so101_source_config, dict) else {}
    so101_bundle_probe = summary.get("so101_model_bundle_probe")
    so101_bundle_probe = so101_bundle_probe if isinstance(so101_bundle_probe, dict) else {}
    so101_bundle = summary.get("so101_model_bundle_manifest")
    so101_bundle = so101_bundle if isinstance(so101_bundle, dict) else {}
    so101_bundle_forwarding = so101_bundle.get("forwarding")
    so101_bundle_forwarding = so101_bundle_forwarding if isinstance(so101_bundle_forwarding, dict) else {}
    so101_bundle_model_path = so101_bundle.get("model_path")
    so101_bundle_model_path = so101_bundle_model_path if isinstance(so101_bundle_model_path, dict) else {}
    so101_bundle_asset_roots = so101_bundle.get("asset_roots")
    so101_bundle_asset_roots = so101_bundle_asset_roots if isinstance(so101_bundle_asset_roots, dict) else {}
    so101_bundle_tcp = so101_bundle.get("tcp_offset")
    so101_bundle_tcp = so101_bundle_tcp if isinstance(so101_bundle_tcp, dict) else {}
    so101_bundle_alignment = so101_bundle.get("base_to_board_alignment")
    so101_bundle_alignment = so101_bundle_alignment if isinstance(so101_bundle_alignment, dict) else {}
    so101_bundle_next_action_ids = [
        action.get("action_id")
        for action in so101_bundle.get("next_required_for_goal", [])
        if isinstance(action, dict) and action.get("action_id")
    ]
    so101_reviewed_mujoco_bundle = summary.get("so101_reviewed_mujoco_bundle")
    so101_reviewed_mujoco_bundle = (
        so101_reviewed_mujoco_bundle if isinstance(so101_reviewed_mujoco_bundle, dict) else {}
    )
    so101_authority_gate = summary.get("so101_reviewed_model_authority_gate")
    so101_authority_gate = so101_authority_gate if isinstance(so101_authority_gate, dict) else {}
    so101_contract = summary.get("so101_model_contract")
    so101_contract = so101_contract if isinstance(so101_contract, dict) else {}
    so101_contract_config = summary.get("so101_model_contract_config")
    so101_contract_config = so101_contract_config if isinstance(so101_contract_config, dict) else {}
    so101_asset_preflight = so101_contract.get("model_asset_preflight")
    so101_asset_preflight = so101_asset_preflight if isinstance(so101_asset_preflight, dict) else {}
    so101_mujoco_scene = summary.get("so101_mujoco_scene")
    so101_mujoco_scene = so101_mujoco_scene if isinstance(so101_mujoco_scene, dict) else {}
    so101_chess_env = summary.get("so101_chess_env")
    so101_chess_env = so101_chess_env if isinstance(so101_chess_env, dict) else {}
    so101_env_resets = summary.get("so101_env_resets")
    so101_env_resets = so101_env_resets if isinstance(so101_env_resets, dict) else {}
    so101_mujoco_contact_probe = summary.get("so101_mujoco_contact_probe")
    so101_mujoco_contact_probe = (
        so101_mujoco_contact_probe if isinstance(so101_mujoco_contact_probe, dict) else {}
    )
    so101_mujoco_grasp_probe = summary.get("so101_mujoco_grasp_probe")
    so101_mujoco_grasp_probe = (
        so101_mujoco_grasp_probe if isinstance(so101_mujoco_grasp_probe, dict) else {}
    )
    so101_mujoco_board_pick_probe = summary.get("so101_mujoco_board_pick_probe")
    so101_mujoco_board_pick_probe = (
        so101_mujoco_board_pick_probe
        if isinstance(so101_mujoco_board_pick_probe, dict)
        else {}
    )
    so101_training_rollouts = summary.get("so101_training_rollouts")
    so101_training_rollouts = (
        so101_training_rollouts if isinstance(so101_training_rollouts, dict) else {}
    )
    readme_path = output_dir / ARTIFACT_ENTRYPOINT_NAME
    lines = [
        "# Simulator Calibration Regression Artifacts",
        "",
        f"Open `{ARTIFACT_REPORT_NAME}` first. It is the review report for this artifact bundle.",
        f"Open `{EVIDENCE_BUNDLE_DIR_NAME}/{EVIDENCE_BUNDLE_MD_NAME}` for the focused "
        "depth-calibration evidence bundle.",
        "For image-first inspection, open `visual_review/gripper_camera_pov_annotated_contact_sheet.png` "
        "and `visual_review/pick_place_sequence_distance_annotated_contact_sheet.png`.",
        "",
        "Core summaries and metric tables:",
        "",
        "- `calibration_regression_summary.json`",
        "- `artifact_index.json`",
        f"- `{EVIDENCE_BUNDLE_DIR_NAME}/{EVIDENCE_BUNDLE_MD_NAME}`",
        f"- `{EVIDENCE_BUNDLE_DIR_NAME}/{EVIDENCE_BUNDLE_JSON_NAME}`",
        f"- `{REFERENCE_MEDIA_INVENTORY_DIR_NAME}/{REFERENCE_MEDIA_INVENTORY_JSON_NAME}`",
        f"- `{REFERENCE_MEDIA_INVENTORY_DIR_NAME}/{REFERENCE_MEDIA_INVENTORY_CSV_NAME}`",
        f"- `{REFERENCE_MEDIA_INVENTORY_DIR_NAME}/{REFERENCE_MEDIA_INVENTORY_README_NAME}`",
        "- `comparison_set/comparison_set_summary.json`",
        "- `comparison_set/reference_media_comparison_rows.csv`",
        "- `comparison_set/README.md`",
        "- `comparison_set/reference_media_comparison_contact_sheet.png` when produced",
        f"- `{REFERENCE_CAMERA_TUNING_DIR_NAME}/{REFERENCE_CAMERA_TUNING_JSON_NAME}`",
        f"- `{REFERENCE_CAMERA_TUNING_DIR_NAME}/{REFERENCE_CAMERA_TUNING_CSV_NAME}`",
        f"- `{REFERENCE_CAMERA_TUNING_DIR_NAME}/{REFERENCE_CAMERA_TUNING_README_NAME}`",
        f"- `{REFERENCE_CAMERA_TUNING_DIR_NAME}/{REFERENCE_CAMERA_TUNING_SCORECARD_NAME}` when produced",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/{SIM_CAMERA_PROFILE_SWEEP_JSON_NAME}`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/candidate_montage.jpg`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/current_overlay.jpg`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/current_absolute_difference_heatmap.jpg`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/current_side_by_side.jpg`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/best_overlay.jpg`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/best_absolute_difference_heatmap.jpg`",
        f"- `{SIM_CAMERA_PROFILE_SWEEP_DIR_NAME}/best_side_by_side.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/{SIM_CAMERA_TUNING_BEFORE_AFTER_JSON_NAME}`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/{SIM_CAMERA_TUNING_BEFORE_AFTER_CSV_NAME}`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/{SIM_CAMERA_TUNING_BEFORE_AFTER_README_NAME}`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/summary.json`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/candidate_montage.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/current_overlay.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/current_absolute_difference_heatmap.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/current_side_by_side.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/best_overlay.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/best_absolute_difference_heatmap.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/best_side_by_side.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/candidates/`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/summary.json`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/candidate_montage.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/current_overlay.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/current_absolute_difference_heatmap.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/current_side_by_side.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/best_overlay.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/best_absolute_difference_heatmap.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/best_side_by_side.jpg`",
        f"- `{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/candidates/`",
        f"- `{REFERENCE_CAPTURE_MANIFEST_DIR_NAME}/{REFERENCE_CAPTURE_MANIFEST_JSON_NAME}`",
        f"- `{REFERENCE_CAPTURE_MANIFEST_DIR_NAME}/{REFERENCE_CAPTURE_MANIFEST_CSV_NAME}`",
        f"- `{REFERENCE_CAPTURE_MANIFEST_DIR_NAME}/{REFERENCE_CAPTURE_MANIFEST_README_NAME}`",
        f"- `{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_DIR_NAME}/{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_JSON_NAME}`",
        f"- `{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_DIR_NAME}/{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_CSV_NAME}`",
        f"- `{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_DIR_NAME}/{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_README_NAME}`",
        f"- `{REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_DIR_NAME}/bridge_smoke/real_depth_capture_plan_manifest_bridge_smoke_summary.json`",
        "- `session/session_summary.json`",
        "- `fixture/fixture_summary.json`",
        "- `sim_camera_pose_fixture/sim_camera_pose_fixture_summary.json`",
        "- `so101_model_bundle_manifest/so101_model_bundle_manifest_summary.json`",
        "- `so101_model_bundle_manifest/so101_model_bundle_manifest_checklist.csv`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_REVIEW_PACKET_JSON_NAME}`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_REVIEW_PACKET_CSV_NAME}`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_REVIEW_REQUIREMENTS_JSON_NAME}`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_REVIEW_REQUIREMENTS_CSV_NAME}`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_INTAKE_CHECKLIST_JSON_NAME}`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_INTAKE_CHECKLIST_CSV_NAME}`",
        f"- `so101_model_bundle_manifest/{SO101_MODEL_BUNDLE_MANIFEST_TEMPLATE_JSON_NAME}`",
        "- `so101_model_bundle_manifest/README.md`",
        f"- `{SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME}/{SO101_REVIEWED_MODEL_AUTHORITY_GATE_SUMMARY_NAME}`",
        f"- `{SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME}/{SO101_REVIEWED_MODEL_AUTHORITY_GATE_CHECKLIST_NAME}`",
        f"- `{SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME}/{SO101_REVIEWED_MODEL_AUTHORITY_GATE_BLOCKER_PACKET_JSON_NAME}`",
        f"- `{SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME}/{SO101_REVIEWED_MODEL_AUTHORITY_GATE_BLOCKER_PACKET_CSV_NAME}`",
        f"- `{SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME}/{SO101_REVIEWED_MODEL_AUTHORITY_GATE_README_NAME}`",
        f"- `{SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME}/{SO101_REVIEWED_MUJOCO_BUNDLE_SUMMARY_NAME}`",
        f"- `{SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME}/so101_reviewed_mujoco_bundle_checklist.csv`",
        f"- `{SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME}/{SO101_REVIEWED_MUJOCO_BUNDLE_MOTION_CHECKS_NAME}`",
        f"- `{SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME}/{SO101_REVIEWED_MUJOCO_BUNDLE_DOWNSTREAM_HANDOFF_NAME}`",
        f"- `{SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME}/{SO101_REVIEWED_MUJOCO_BUNDLE_DOWNSTREAM_HANDOFF_CSV_NAME}`",
        f"- `{SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME}/README.md`",
        "- `so101_model_source_inventory/so101_model_source_inventory_summary.json`",
        "- `so101_model_source_inventory/so101_model_source_candidates.csv`",
        f"- `so101_model_source_inventory/{SO101_MODEL_SOURCE_INVENTORY_REVIEW_PACKET_JSON_NAME}`",
        f"- `so101_model_source_inventory/{SO101_MODEL_SOURCE_INVENTORY_REVIEW_PACKET_CSV_NAME}`",
        f"- `so101_model_source_inventory/{SO101_MODEL_SOURCE_INTAKE_CHECKLIST_JSON_NAME}`",
        f"- `so101_model_source_inventory/{SO101_MODEL_SOURCE_INTAKE_CHECKLIST_CSV_NAME}`",
        "- `so101_model_source_inventory/README.md`",
        f"- `{SO101_MODEL_BUNDLE_PROBE_DIR_NAME}/{SO101_MODEL_BUNDLE_PROBE_SUMMARY_NAME}`",
        f"- `{SO101_MODEL_BUNDLE_PROBE_DIR_NAME}/so101_model_bundle.candidate.json`",
        f"- `{SO101_MODEL_BUNDLE_PROBE_DIR_NAME}/so101_model_bundle_review_packet.json`",
        f"- `{SO101_MODEL_BUNDLE_PROBE_DIR_NAME}/so101_model_bundle_review_packet.csv`",
        f"- `{SO101_MODEL_BUNDLE_PROBE_DIR_NAME}/so101_model_bundle_probe_checklist.csv`",
        f"- `{SO101_MODEL_BUNDLE_PROBE_DIR_NAME}/README.md`",
        "- `so101_model_contract/so101_model_contract_summary.json`",
        "- `so101_model_contract/so101_model_contract_checklist.csv`",
        "- `so101_model_contract/README.md`",
        "- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_summary.json`",
        "- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_assets.csv`",
        "- `so101_model_contract/so101_model_asset_preflight/README.md`",
        "- `ik_reachability_drill/ik_reachability_drill_summary.json`",
        "- `ik_reachability_drill/ik_reachability_drill_rows.csv`",
        "- `ik_reachability_drill/ik_reachability_drill_heatmap.png`",
        f"- `{SO101_MUJOCO_SCENE_DIR_NAME}/{SO101_MUJOCO_SCENE_SUMMARY_NAME}`",
        f"- `{SO101_CHESS_ENV_DIR_NAME}/{SO101_CHESS_ENV_SUMMARY_NAME}`",
        f"- `{SO101_ENV_RESETS_DIR_NAME}/{SO101_ENV_RESETS_SUMMARY_NAME}`",
        f"- `{SO101_MUJOCO_CONTACT_PROBE_DIR_NAME}/{SO101_MUJOCO_CONTACT_PROBE_SUMMARY_NAME}`",
        f"- `{SO101_MUJOCO_GRASP_PROBE_DIR_NAME}/{SO101_MUJOCO_GRASP_PROBE_SUMMARY_NAME}`",
        f"- `{SO101_MUJOCO_BOARD_PICK_PROBE_DIR_NAME}/{SO101_MUJOCO_BOARD_PICK_PROBE_SUMMARY_NAME}`",
        f"- `{SO101_TRAINING_READINESS_GATE_DIR_NAME}/{SO101_TRAINING_READINESS_GATE_SUMMARY_NAME}`",
        f"- `{SO101_TRAINING_READINESS_GATE_DIR_NAME}/{SO101_TRAINING_READINESS_GATE_CHECKLIST_NAME}`",
        f"- `{SO101_TRAINING_READINESS_GATE_DIR_NAME}/{SO101_TRAINING_READINESS_GATE_PRIORITY_QUEUE_NAME}`",
        f"- `{SO101_TRAINING_READINESS_GATE_DIR_NAME}/{SO101_TRAINING_READINESS_GATE_README_NAME}`",
        f"- `{SO101_TRAINING_ROLLOUTS_DIR_NAME}/{SO101_TRAINING_ROLLOUTS_SUMMARY_NAME}`",
        "- `gripper_camera_pov_review/gripper_camera_pov_review_summary.json`",
        "- `pick_place_scenario_matrix/scenario_matrix_summary.json`",
        "- `app_entrypoint/smoke_sim_app_entrypoints_summary.json`",
        "- `app_entrypoint/smoke_sim_app_metadata.json`",
        "- `visual_review/visual_review_summary.json`",
        "- `visual_review/pick_place_depth_distance_metrics.json`",
        "- `visual_review/pick_place_depth_distance_metrics.csv`",
        "- `visual_review/pick_place_depth_distance_scorecard.png`",
        "- `visual_review/pick_place_depth_distance_scorecard.json`",
        "- `visual_review/pick_place_perceived_depth_comparison.json`",
        "- `visual_review/pick_place_perceived_depth_comparison.csv`",
        "- `visual_review/pick_place_pnp_residual_diagnostics.json`",
        "- `visual_review/pick_place_pnp_residual_diagnostics.csv`",
        "- `visual_review/pick_place_metadata_native_depth_view.png`",
        "- `visual_review/pick_place_metadata_native_depth_view.json`",
        "- `visual_review/pick_place_metadata_native_depth_view.csv`",
        "- `real_projection_intake/real_projection_intake.json`",
        "- `real_projection_intake/real_projection_intake.csv`",
        "- `real_projection_intake/real_projection_intake_contact_sheet.png`",
        "- `real_projection_intake/real_projection_residuals.json` when real_capture sidecars are comparable",
        "- `real_projection_intake/real_projection_residuals.csv` when real_capture sidecars are comparable",
        "- `real_projection_intake/real_projection_residual_overlay_contact_sheet.png` when real_capture sidecars are comparable",
        "- `reference_capture_checklist/reference_capture_checklist.json`",
        "- `reference_capture_checklist/reference_capture_checklist.md`",
        "- `negative_empty_inventory/comparison_set_summary.json`",
        "",
        "Review markers:",
        "",
        (
            f"- `hardware_skipped: {markdown_bool(summary.get('hardware_skipped'))}`: "
            f"{markers.get('hardware', '')}"
        ),
        (
            f"- `gui_skipped: {markdown_bool(summary.get('gui_skipped'))}`: "
            f"{markers.get('gui', '')}"
        ),
        (
            f"- `openai_skipped: {markdown_bool(summary.get('openai_skipped'))}`: "
            f"{markers.get('openai', '')}"
        ),
        (
            f"- `reference_media_manifest.supplied: {markdown_bool(manifest_supplied)}`"
            f"; status: `{manifest.get('status')}`; path: `{manifest.get('path')}`."
        ),
        (
            f"- Manifest-declared media selected for comparison: "
            f"`{manifest.get('selected_declared_media_count')}`."
        ),
        (
            "- Reference media inventory: "
            f"status `{reference_inventory_counts_row.get('status')}`; candidates "
            f"`{reference_inventory_counts_row.get('candidate_count')}`; images "
            f"`{reference_inventory_counts_row.get('image_count')}`; videos "
            f"`{reference_inventory_counts_row.get('video_count')}`; calibration data "
            f"`{reference_inventory_counts_row.get('calibration_data_count')}`; wired "
            f"`{reference_inventory_counts_row.get('currently_wired_media_count')}`; "
            "current gripper reference detected "
            f"`{markdown_bool(reference_inventory_counts_row.get('current_gripper_reference', {}).get('detected'))}`."
        ),
        (
            "- Reference media gaps: "
            f"`{markdown_list_value(reference_inventory_counts_row.get('reference_gaps'))}`."
        ),
        (
            "- Reference media comparison: "
            f"status `{comparison_set.get('status')}`; selected candidates "
            f"`{comparison_set.get('selected_candidate_count')}`; selected media "
            f"`{comparison_set.get('selected_media_count')}`; visual comparisons "
            f"`{comparison_set.get('visual_comparison_count')}`; contact sheet "
            f"`{comparison_set.get('contact_sheet_status')}`."
        ),
        (
            "- Reference media comparison diagnostics: media assets copied into repo "
            f"`{markdown_bool(comparison_set.get('media_assets_copied_into_repo'))}`; "
            f"external selected `{comparison_set.get('external_selected_count')}`; "
            f"missing depth `{markdown_bool(comparison_set.get('missing_depth_reference'))}`; "
            f"missing pick/place video `{markdown_bool(comparison_set.get('missing_pick_place_video'))}`; "
            f"no videos `{markdown_bool(comparison_set.get('no_videos'))}`."
        ),
        (
            "- Reference camera tuning diagnostics: "
            f"status `{summary.get('reference_camera_tuning_diagnostics', {}).get('status')}`; "
            f"selected comparisons `{summary.get('reference_camera_tuning_diagnostics', {}).get('selected_comparison_count')}`; "
            f"visual comparisons `{summary.get('reference_camera_tuning_diagnostics', {}).get('visual_comparison_count')}`; "
            f"metadata-only `{summary.get('reference_camera_tuning_diagnostics', {}).get('metadata_only_count')}`; "
            "media assets copied into repo "
            f"`{markdown_bool(summary.get('reference_camera_tuning_diagnostics', {}).get('media_assets_copied_into_repo'))}`."
        ),
        (
            "- SimCamera profile sweep: "
            f"status `{profile_sweep.get('status')}`; profile `{profile_sweep.get('profile_name')}`; "
            f"current finger width `{profile_sweep.get('current_gripper_finger_width_px')}` px; "
            f"marker time `{profile_sweep.get('marker_time_seconds')}`; candidates "
            f"`{profile_sweep.get('candidate_count')}`; current MAD/RMSE "
            f"`{profile_sweep_metrics.get('current_mean_abs_delta')}`/"
            f"`{profile_sweep_metrics.get('current_rmse')}`; best "
            f"`{profile_sweep.get('best_candidate_id')}` MAD/RMSE "
            f"`{profile_sweep_metrics.get('best_mean_abs_delta')}`/"
            f"`{profile_sweep_metrics.get('best_rmse')}`; delta vs current "
            f"`{profile_sweep_metrics.get('mean_abs_delta_delta_vs_current')}`/"
            f"`{profile_sweep_metrics.get('rmse_delta_vs_current')}`."
        ),
        (
            "- SimCamera profile sweep artifacts: "
            f"summary `{profile_sweep_paths.get('summary_json')}`; montage "
            f"`{profile_sweep_paths.get('candidate_montage_jpg')}`; current/best overlays and "
            "difference heatmaps are indexed under `sim_camera_profile_sweep/`."
        ),
        (
            "- SimCamera profile sweep remaining tuning prompts: "
            f"`{markdown_list_value(profile_sweep_prompt_ids)}`."
        ),
        (
            "- SimCamera profile sweep caveat: "
            f"{profile_sweep.get('full_frame_image_delta_caveat') or 'Full-frame image delta is hardware-free coarse evidence only.'}"
        ),
        (
            "- SimCamera tuning before/after: "
            f"status `{tuning_before_after.get('status')}`; profile "
            f"`{tuning_before_after.get('profile_name')}`; baseline finger width "
            f"`{tuning_before_after.get('baseline_gripper_finger_width_px')}` px; "
            f"current finger width `{tuning_before_after.get('current_gripper_finger_width_px')}` px; "
            f"marker time `{tuning_before_after.get('marker_time_seconds')}`; baseline/current "
            f"candidate counts `{tuning_before_after.get('baseline_candidate_count')}`/"
            f"`{tuning_before_after.get('current_candidate_count')}`; current-vs-baseline "
            "MAD/RMSE "
            f"`{tuning_before_after.get('current_vs_baseline_mean_abs_delta')}`/"
            f"`{tuning_before_after.get('current_vs_baseline_rmse')}`; best-vs-baseline-best "
            "MAD/RMSE "
            f"`{tuning_before_after.get('best_vs_baseline_best_mean_abs_delta')}`/"
            f"`{tuning_before_after.get('best_vs_baseline_best_rmse')}`."
        ),
        (
            "- SimCamera tuning before/after diagnostics: media assets copied into repo "
            f"`{markdown_bool(tuning_before_after.get('media_assets_copied_into_repo'))}`; "
            f"missing real depth `{markdown_bool(tuning_before_after.get('missing_real_depth_reference'))}`; "
            f"missing pick/place video `{markdown_bool(tuning_before_after.get('missing_pick_place_video'))}`; "
            f"remaining prompts `{markdown_list_value(tuning_before_after_prompt_ids)}`."
        ),
        (
            "- SimCamera tuning before/after artifacts: "
            f"summary `{tuning_before_after_paths.get('summary_json')}`; rows "
            f"`{tuning_before_after_paths.get('csv_rows')}`; README "
            f"`{tuning_before_after_paths.get('readme_md')}`; child sweep artifacts stay under "
            f"`{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/baseline_profile_sweep/` and "
            f"`{SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME}/current_profile_sweep/`."
        ),
        (
            "- SimCamera tuning before/after caveat: "
            f"{tuning_before_after.get('full_frame_image_delta_caveat') or 'Full-frame image delta is hardware-free coarse evidence only.'}"
        ),
        (
            "- Reference capture manifest: "
            f"status `{reference_capture_manifest.get('status')}`; ready_for_calibration_grade_simcamera_tuning "
            f"`{markdown_bool(reference_capture_manifest.get('ready_for_calibration_grade_simcamera_tuning'))}`; "
            f"depth captures `{reference_capture_manifest.get('depth_reference_capture_count')}`; "
            f"pick/place videos `{reference_capture_manifest.get('pick_place_video_capture_count')}`; "
            f"path checks `{reference_capture_manifest.get('path_check_count')}`; "
            f"missing paths `{reference_capture_manifest.get('missing_path_count')}`."
        ),
        (
            "- Reference capture manifest diagnostics: "
            f"`{markdown_list_value(reference_capture_manifest.get('diagnostics'))}`; "
            "media assets copied into repo "
            f"`{markdown_bool(reference_capture_manifest.get('media_assets_copied_into_repo'))}`."
        ),
        (
            "- Reference capture manifest artifacts: "
            f"summary `{reference_capture_manifest_paths.get('summary_json')}`; rows "
            f"`{reference_capture_manifest_paths.get('csv')}`; README "
            f"`{reference_capture_manifest_paths.get('readme_md')}`."
        ),
        (
            "- Reference capture manifest caveat: ready means operator-supplied local "
            "capture inputs are present and reviewed; it is not physical calibration truth."
        ),
        (
            "- Real depth capture plan artifact index: "
            f"status `{real_depth_plan_index.get('status')}`; source mode "
            f"`{real_depth_plan_index.get('source_mode')}`; cases "
            f"`{real_depth_plan_index.get('case_count')}`; ready/not-ready "
            f"`{real_depth_plan_index.get('ready_case_count')}`/"
            f"`{real_depth_plan_index.get('not_ready_case_count')}`; evidence statuses "
            f"`{markdown_list_value(real_depth_plan_index.get('evidence_statuses'))}`."
        ),
        (
            "- Real depth capture plan action evidence: "
            f"next actions `{real_depth_plan_index.get('next_operator_action_count')}` "
            f"`{markdown_list_value(real_depth_plan_index.get('next_operator_action_ids'))}`; "
            f"depth captures `{real_depth_plan_index.get('depth_reference_capture_count')}`; "
            f"pick/place videos `{real_depth_plan_index.get('pick_place_video_capture_count')}`; "
            f"missing paths `{real_depth_plan_index.get('missing_path_count')}`; no-copy statuses "
            f"`{markdown_list_value(real_depth_plan_index.get('no_copy_statuses'))}`."
        ),
        (
            "- Real depth capture plan artifacts: "
            f"summary `{real_depth_plan_index_paths.get('summary_json')}`; rows "
            f"`{real_depth_plan_index_paths.get('csv')}`; README "
            f"`{real_depth_plan_index_paths.get('readme_md')}`; bridge smoke summary "
            f"`{real_depth_plan_index.get('bridge_smoke_summary_json')}`."
        ),
        (
            "- Real depth capture plan caveat: ready evidence is input readiness only, "
            "not physical calibration truth; media assets copied/opened/decoded are "
            f"`{markdown_bool(real_depth_plan_index.get('media_assets_copied_into_repo'))}`/"
            f"`{markdown_bool(real_depth_plan_index.get('media_assets_opened_or_decoded'))}`."
        ),
        "- Reference capture checklist status: "
        f"`{summary.get('reference_capture_checklist', {}).get('status')}`.",
        (
            "- No real-world videos are present for motion, recovery, or timing references."
            if "missing_pick_place_video" in reference_gap_ids
            else "- Pick/place video reference gap is not reported by the current inventory."
        ),
        (
            "- No reference media currently documents failure modes."
            if failure_mode_gap
            else "- Failure-mode reference gap is not reported by the current inventory."
        ),
        (
            "- SimCamera pose metadata includes `image_size_px`, `camera_matrix_px`, "
            "`intrinsics`, `distortion_coefficients`, and `extrinsics.board_to_camera`."
        ),
        (
            "- Gripper-camera POV evidence records target center, projected square geometry, "
            "gripper opening, and synthetic visibility/occlusion/clearance rows."
        ),
        (
            "- SO-101 reviewed model authority gate: "
            f"status `{so101_authority_gate.get('status')}`; ready "
            f"`{markdown_bool(so101_authority_gate.get('ready'))}`; source authority "
            f"`{markdown_bool(so101_authority_gate.get('source_authority_ready'))}`; "
            f"physical bundle authority "
            f"`{markdown_bool(so101_authority_gate.get('physical_so101_model_authority_ready'))}`; "
            f"physical reviewed MuJoCo motion "
            f"`{markdown_bool(so101_authority_gate.get('physical_reviewed_model_motion_checked'))}`; "
            "fixture evidence is not physical SO-101 truth "
            f"`{markdown_bool(so101_authority_gate.get('development_fixture_evidence_not_physical_so101_truth'))}`."
        ),
        (
            "- SO-101 reviewed model authority blockers: "
            f"`{markdown_list_value(so101_authority_gate.get('blockers'))}`."
        ),
        (
            "- SO-101 training readiness gate: "
            f"status `{summary.get('so101_training_readiness_gate', {}).get('status')}`; "
            f"ready `{markdown_bool(summary.get('so101_training_readiness_gate', {}).get('ready'))}`; "
            "reviewed model-backed board pick/place "
            f"`{markdown_bool(summary.get('so101_training_readiness_gate', {}).get('reviewed_model_backed_board_source_pick_place'))}`; "
            "rollout ready "
            f"`{markdown_bool(summary.get('so101_training_readiness_gate', {}).get('rollout_ready_for_policy_training'))}`; "
            "fixture evidence is not policy training truth "
            f"`{markdown_bool(summary.get('so101_training_readiness_gate', {}).get('development_fixture_evidence_not_policy_training_truth'))}`."
        ),
        (
            "- SO-101 training readiness blockers: "
            f"`{markdown_list_value(summary.get('so101_training_readiness_gate', {}).get('blockers'))}`."
        ),
        (
            "- SO-101 model-source inventory evidence records repo-local model-source "
            "candidate counts, authoritative-source status, provenance/license diagnostics, "
            "and a recommended contract-check candidate only when one is discovered; "
            "`--ik-model-path` is not treated as authoritative by this inventory gate."
        ),
        (
            "- SO-101 inventory source configuration: "
            f"mode `{so101_source_config.get('scan_mode')}`; roots "
            f"`{markdown_list_value(so101_source_config.get('model_source_roots'))}`; extra roots "
            f"`{markdown_list_value(so101_source_config.get('model_source_extra_roots'))}`; "
            f"authoritative paths "
            f"`{markdown_list_value(so101_source_config.get('authoritative_model_paths'))}`; "
            f"authoritative roots "
            f"`{markdown_list_value(so101_source_config.get('authoritative_model_roots'))}`; "
            "`--ik-model-path` authority `false`."
        ),
        (
            "- SO-101 model bundle probe: "
            f"status `{so101_bundle_probe.get('status')}`; model_authority "
            f"`{so101_bundle_probe.get('model_authority')}`; selected model "
            f"`{so101_bundle_probe.get('selected_model_path') or 'none'}`; "
            f"manifest status `{so101_bundle_probe.get('manifest_status')}`; "
            f"ready_for_model_backed_ik "
            f"`{markdown_bool(so101_bundle_probe.get('ready_for_model_backed_ik'))}`; "
            f"review packet `{so101_bundle_probe.get('review_packet_status')}` with "
            f"`{so101_bundle_probe.get('review_packet_item_count')}` items; "
            f"next actions `{markdown_list_value(so101_bundle_probe.get('next_required_action_ids'))}`."
        ),
        (
            "- SO-101 model bundle probe caveat: the generated candidate manifest is a "
            "review draft only, and the review packet is operator intake only; neither "
            "closes source authority, physical model authority, or physical reviewed "
            "MuJoCo motion."
        ),
        (
            "- SO-101 model bundle manifest evidence records the reviewed bundle request, "
            "model path, asset roots, target frame, TCP/gripper-tip offset, base-to-board "
            "alignment, child contract diagnostics, and nested asset-preflight diagnostics."
        ),
        (
            "- SO-101 model bundle manifest status: "
            f"`{so101_bundle.get('status')}`; ready_for_model_backed_ik "
            f"`{markdown_bool(so101_bundle.get('ready_for_model_backed_ik'))}`; "
            f"model_authority `{so101_bundle.get('model_authority')}`; "
            f"physical authority `{markdown_bool(so101_bundle.get('physical_so101_model_authority_ready'))}`; "
            f"fixture ready `{markdown_bool(so101_bundle.get('hardware_free_regression_fixture_ready'))}`; "
            f"model `{so101_bundle_model_path.get('path') or 'none'}`; roots "
            f"`{markdown_list_value(so101_bundle_asset_roots.get('asset_roots'))}`; "
            f"target frame `{so101_bundle.get('target_frame', {}).get('value') if isinstance(so101_bundle.get('target_frame'), dict) else None}`; "
            f"TCP field `{so101_bundle_tcp.get('field')}`; alignment "
            f"`{so101_bundle_alignment.get('status')}`."
        ),
        (
            "- SO-101 model bundle next required actions: "
            f"`{markdown_list_value(so101_bundle_next_action_ids)}`."
        ),
        (
            "- SO-101 model bundle forwarding: "
            f"diagnostic_only `{markdown_bool(so101_bundle_forwarding.get('diagnostic_only'))}`; "
            f"reason `{so101_bundle_forwarding.get('diagnostic_only_reason')}`; "
            f"effective model path source `{so101_bundle_forwarding.get('ik_model_path_source')}`; "
            f"effective asset-root source `{so101_bundle_forwarding.get('ik_model_asset_root_source')}`."
        ),
        (
            "- SO-101 reviewed MuJoCo bundle gate: "
            f"status `{so101_reviewed_mujoco_bundle.get('status')}`; "
            f"model_authority `{so101_reviewed_mujoco_bundle.get('model_authority')}`; "
            f"physical authority `{markdown_bool(so101_reviewed_mujoco_bundle.get('physical_so101_model_authority_ready'))}`; "
            f"fixture ready `{markdown_bool(so101_reviewed_mujoco_bundle.get('hardware_free_regression_fixture_ready'))}`; "
            f"ready_for_model_backed_ik `{markdown_bool(so101_reviewed_mujoco_bundle.get('ready_for_model_backed_ik'))}`; "
            f"reviewed_model_motion_checked `{markdown_bool(so101_reviewed_mujoco_bundle.get('reviewed_model_motion_checked'))}`; "
            "a ready reviewed bundle must load in MuJoCo and map/move every SO-101 joint before training evidence is trusted."
        ),
        (
            "- SO-101 model contract evidence records model availability, direct "
            "RobotKinematics usability, joint/frame/TCP contract inputs, and the missing "
            "alignment inputs that still gate trustworthy model-backed IK residuals."
        ),
        (
            "- SO-101 model contract configuration: "
            f"`--ik-model-path` `{so101_contract_config.get('ik_model_path') or 'none'}`; "
            f"asset roots `{markdown_list_value(so101_contract_config.get('ik_model_asset_roots'))}`; "
            "asset roots are forwarded only to the nested asset preflight."
        ),
        (
            "- SO-101 model asset preflight configuration: "
            f"roots `{markdown_list_value(so101_asset_preflight.get('asset_roots'))}`; "
            f"mesh `{so101_asset_preflight.get('mesh_reference_count')}`; "
            f"present `{so101_asset_preflight.get('present_asset_count')}`; "
            f"missing `{so101_asset_preflight.get('missing_asset_count')}`; "
            f"unresolved `{so101_asset_preflight.get('unresolved_reference_count')}`."
        ),
        (
            "- IK reachability evidence records deterministic Cartesian/delta/radial command "
            "feasibility with summary JSON, rows CSV, and a heatmap PNG; missing repo-local "
            "SO-101 models remain an explicit non-failing fallback diagnostic."
        ),
        (
            "- SO-101 MuJoCo scene evidence: "
            f"status `{so101_mujoco_scene.get('status')}`; model authority "
            f"`{so101_mujoco_scene.get('model_authority')}`; ready_for_model_backed_ik "
            f"`{markdown_bool(so101_mujoco_scene.get('ready_for_model_backed_ik'))}`; "
            "this proves development-scaffold MuJoCo plumbing, not physical IK truth."
        ),
        (
            "- SO-101 Gymnasium env evidence: "
            f"status `{so101_chess_env.get('status')}`; MuJoCo backend "
            f"`{(so101_chess_env.get('sim_status') or {}).get('ok') if isinstance(so101_chess_env.get('sim_status'), dict) else None}`; "
            f"scripted pick/place `{(so101_chess_env.get('scripted_pick_place') or {}).get('scripted_pick_place_complete') if isinstance(so101_chess_env.get('scripted_pick_place'), dict) else None}`."
        ),
        (
            "- SO-101 reset/contact/rollout evidence: resets "
            f"`{markdown_bool(so101_env_resets.get('all_resets_ok'))}`, board contact "
            f"`{markdown_bool(so101_mujoco_contact_probe.get('all_board_contacts_observed'))}`, "
            f"gripper contact `{markdown_bool(so101_mujoco_grasp_probe.get('gripper_contact_observed'))}`, "
            f"lift/place physics `{markdown_bool(so101_mujoco_grasp_probe.get('lift_place_physics_verified'))}`, "
            f"board-source pick/place `{markdown_bool(so101_mujoco_board_pick_probe.get('board_source_pick_place_verified'))}`, "
            f"board-source final target XY error `{so101_mujoco_board_pick_probe.get('final_target_xy_error_m')}`, "
            f"scripted rollout episodes `{so101_training_rollouts.get('episode_count')}` and transitions "
            f"`{so101_training_rollouts.get('transition_count')}`, rollout prerequisites "
            f"`{markdown_bool(so101_training_rollouts.get('development_prerequisites_satisfied'))}`, "
            f"ready_for_policy_training `{markdown_bool(so101_training_rollouts.get('ready_for_policy_training'))}`."
        ),
        (
            "- SO-101 MuJoCo next required items stay open: reviewed model bundle, mesh roots, "
            "joint/frame/TCP authority, base-to-board alignment, and replacement of the seeded "
            "development board-source pickup with reviewed model-backed IK before serious policy training."
        ),
        (
            "- App-entrypoint metadata evidence runs `smoke_sim_app_entrypoints.py --sim` "
            "compatibility paths against a synthetic SimCamera frame."
        ),
        (
            "- Visual review contact sheets are stable PNG evidence generated from existing "
            "suite frames under `visual_review/`."
        ),
        (
            "- Pick/place sequence evidence shows approach, grasp/contact, lift/transfer, "
            "place/release, and retreat using simulator gripper-camera frames."
        ),
        (
            "- Pick/place depth/distance evidence records simulator-ground-truth camera-to-board, "
            "camera-to-piece, target world/pixel coordinates, projection residuals, and a "
            "labeled gripper-to-piece board-plane proxy; perceived depth is explicitly marked "
            "`not_implemented`."
        ),
        (
            "- Pick/place depth-distance scorecard evidence writes a PNG plus JSON that combines "
            "SimCamera ground truth, the metadata-derived rendered-corner PnP baseline, mm/px "
            "residual severity, and the explicit missing real-camera/depth-sensor reference."
        ),
        (
            "- Pick/place perceived-depth comparison evidence records a metadata-derived "
            "rendered-board-corner PnP baseline beside the simulator ground truth, including "
            "estimated camera-to-piece/board distances and residuals."
        ),
        (
            "- Pick/place PnP residual diagnostics compare simulator ground-truth "
            "extrinsics, rendered-board-corner PnP, and metadata-projected 3D board corners "
            "with source comparability labels."
        ),
        (
            "- Pick/place metadata-native depth view projects known board, piece, and target "
            "points through SimCamera `camera_matrix_px` and `extrinsics.board_to_camera`, "
            "reports camera-frame z/depth/range in millimeters, and does not use rendered "
            "overlay corners as depth authority."
        ),
        (
            "- Real projection intake links selected real reference media to the metadata-native "
            "projection/depth view, writes JSON/CSV plus a contact-sheet PNG, and reports "
            "`real_depth_comparable` only when real_capture=true intrinsics, pose, and depth "
            "sidecars can be compared; otherwise it reports `missing_real_depth_reference`."
        ),
        (
            f"- Optional visual review recording produced: `{markdown_bool(recording.get('produced'))}`; "
            f"skipped reason: `{recording.get('skipped_reason')}`."
        ),
        "- Those extrinsics are simulator reference metadata, not physical calibration truth.",
        "",
        "This bundle does not replace later physical SO-101 validation.",
        "",
    ]
    readme_path.write_text("\n".join(lines))
    return readme_path


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, f"Expected JSON object, got {type(payload).__name__}."
    return payload, None


def run_child(
    *,
    name: str,
    command: list[str],
    output_dir: Path,
    expected_json_path: Path,
    expected_failure: bool = False,
    non_failing_statuses: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{name}_stdout.txt"
    stderr_path = output_dir / f"{name}_stderr.txt"
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)

    payload: dict[str, Any] | None = None
    summary_error: str | None = None
    if expected_json_path.is_file():
        payload, summary_error = read_json_object(expected_json_path)
    elif result.returncode == 0 or not expected_failure:
        summary_error = f"Expected summary JSON was not written: {expected_json_path}"

    payload_ok = bool(payload.get("ok", True)) if payload is not None else False
    payload_status = payload.get("status") if payload else None
    non_failing_status = (
        isinstance(payload_status, str)
        and non_failing_statuses is not None
        and payload_status in non_failing_statuses
        and summary_error is None
    )
    if expected_failure:
        ok = result.returncode != 0 and (payload is None or not payload_ok)
    else:
        ok = (
            result.returncode == 0
            and payload is not None
            and payload_ok
            and summary_error is None
        ) or non_failing_status

    record = {
        "name": name,
        "ok": ok,
        "expected_failure": expected_failure,
        "non_failing_status": payload_status if non_failing_status else None,
        "command": command,
        "return_code": int(result.returncode),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "expected_output_json_path": str(expected_json_path),
        "summary_loaded": payload is not None,
        "summary_error": summary_error,
        "summary_status": payload_status,
    }
    return record, payload


def skipped_child(name: str, reason: str, expected_json_path: Path) -> dict[str, Any]:
    return {
        "name": name,
        "ok": False,
        "status": "skipped",
        "reason": reason,
        "command": None,
        "return_code": None,
        "stdout_path": None,
        "stderr_path": None,
        "expected_output_json_path": str(expected_json_path),
        "summary_loaded": False,
    }


def profile_candidate_payload(
    *,
    label: str,
    corners: list[list[int]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    reference_image = args.reference_image.expanduser().resolve()
    return {
        "schema": "lerobot.sim.manual_corner_profile_candidate.v1",
        "base_profile": str(args.base_profile),
        "status": "candidate_only_not_canonical",
        "reference_image_path": str(reference_image),
        "corner_labels": ["a1", "h1", "h8", "a8"],
        "board_corners_xy": [[float(x), float(y)] for x, y in corners],
        "sim_camera_profile_overrides": {
            "width": 640,
            "height": 480,
            "board_corners_xy": [[float(x), float(y)] for x, y in corners],
            "reference_image_path": str(reference_image),
        },
        "suite_candidate_label": label,
    }


def write_candidate_inputs(args: argparse.Namespace, output_dir: Path) -> dict[str, str]:
    candidates_dir = output_dir / "candidates"
    baseline_path = candidates_dir / "baseline_profile_candidate.json"
    perturbed_path = candidates_dir / "perturbed_profile_candidate.json"
    write_json(
        baseline_path,
        profile_candidate_payload(label="baseline", corners=BASELINE_CORNERS, args=args),
    )
    write_json(
        perturbed_path,
        profile_candidate_payload(label="perturbed", corners=PERTURBED_CORNERS, args=args),
    )
    return {
        "baseline_candidate_path": str(baseline_path),
        "perturbed_candidate_path": str(perturbed_path),
    }


def comparison_artifacts(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    comparisons = summary.get("comparisons")
    if not isinstance(comparisons, list):
        return []
    rows: list[dict[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        details = comparison.get("comparison")
        details = details if isinstance(details, dict) else {}
        rows.append(
            {
                "relative_path": comparison.get("relative_path"),
                "summary_path": details.get("summary_path"),
                "visual_artifact_paths": details.get("visual_artifact_paths"),
                "child_artifact_paths": details.get("child_artifact_paths"),
            }
        )
    return rows


def reference_media_comparison_artifact_paths(
    comparison: dict[str, Any] | None,
    comparison_dir: Path,
    summary_path: Path,
) -> dict[str, str | None]:
    comparison = comparison if isinstance(comparison, dict) else {}
    artifacts = comparison.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    return {
        "summary_json": str(artifacts.get("summary_json") or summary_path),
        "csv_rows": str(artifacts.get("csv_rows") or comparison_dir / "reference_media_comparison_rows.csv"),
        "readme_md": str(artifacts.get("readme_md") or comparison_dir / "README.md"),
        "contact_sheet_png": (
            str(artifacts.get("contact_sheet_png"))
            if isinstance(artifacts.get("contact_sheet_png"), str)
            else None
        ),
    }


def reference_media_comparison_diagnostics(
    comparison: dict[str, Any] | None,
    comparison_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    comparison = comparison if isinstance(comparison, dict) else {}
    diagnostics = comparison.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    contact_sheet = comparison.get("contact_sheet")
    contact_sheet = contact_sheet if isinstance(contact_sheet, dict) else {}
    artifact_paths = reference_media_comparison_artifact_paths(
        comparison,
        comparison_dir,
        summary_path,
    )
    return {
        "summary_path": artifact_paths["summary_json"],
        "csv_path": artifact_paths["csv_rows"],
        "readme_path": artifact_paths["readme_md"],
        "artifact_paths": artifact_paths,
        "status": comparison.get("status"),
        "ok": comparison.get("ok"),
        "selected_candidate_count": comparison.get("selected_candidate_count"),
        "selected_media_count": comparison.get("selected_media_count"),
        "visual_comparison_count": comparison.get("visual_comparison_count"),
        "failed_comparison_count": comparison.get("failed_comparison_count"),
        "skipped_media_count": comparison.get("skipped_media_count"),
        "contact_sheet_path": contact_sheet.get("path") or artifact_paths["contact_sheet_png"],
        "contact_sheet_status": contact_sheet.get("status"),
        "contact_sheet_produced": contact_sheet.get("produced"),
        "media_assets_copied_into_repo": diagnostics.get("media_assets_copied_into_repo", False),
        "external_selected_count": diagnostics.get("external_selected_count"),
        "missing_depth_reference": diagnostics.get("missing_depth_reference"),
        "missing_pick_place_video": diagnostics.get("missing_pick_place_video"),
        "no_videos": diagnostics.get("no_videos"),
        "videos_present": diagnostics.get("videos_present"),
        "reference_gaps": diagnostics.get("reference_gaps"),
        "render_dependencies": diagnostics.get("render_dependencies"),
        "diagnostics": diagnostics,
    }


def reference_media_comparison_section(
    comparison: dict[str, Any] | None,
    comparison_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    comparison = comparison if isinstance(comparison, dict) else {}
    diagnostics = reference_media_comparison_diagnostics(comparison, comparison_dir, summary_path)
    return {
        **diagnostics,
        "output_dir": str(comparison_dir),
        "inventory_json_path": comparison.get("inventory_json_path"),
        "inventory_summary": comparison.get("inventory_summary"),
        "selection_rules": comparison.get("selection_rules"),
        "selected_candidates": comparison.get("selected_candidates"),
        "selected_media": comparison.get("selected_media"),
        "skipped_media": comparison.get("skipped_media"),
        "visibility_gaps": comparison.get("visibility_gaps"),
        "comparisons": comparison.get("comparisons"),
        "contact_sheet": comparison.get("contact_sheet"),
        "artifacts": comparison_artifacts(comparison),
        "notes": comparison.get("notes"),
    }


def reference_camera_tuning_artifact_paths(
    diagnostics: dict[str, Any] | None,
    diagnostics_dir: Path,
    summary_path: Path,
) -> dict[str, str | None]:
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    artifacts = diagnostics.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    scorecard = diagnostics.get("scorecard")
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    return {
        "summary_json": str(artifacts.get("summary_json") or summary_path),
        "csv_rows": str(artifacts.get("csv_rows") or diagnostics_dir / REFERENCE_CAMERA_TUNING_CSV_NAME),
        "readme_md": str(artifacts.get("readme_md") or diagnostics_dir / REFERENCE_CAMERA_TUNING_README_NAME),
        "scorecard_png": (
            str(artifacts.get("scorecard_png") or scorecard.get("path"))
            if scorecard.get("produced") is True
            else None
        ),
    }


def reference_camera_tuning_diagnostics_section(
    diagnostics: dict[str, Any] | None,
    diagnostics_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    paths = reference_camera_tuning_artifact_paths(diagnostics, diagnostics_dir, summary_path)
    scorecard = diagnostics.get("scorecard")
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    gaps = diagnostics.get("reference_gap_carry_through")
    gaps = gaps if isinstance(gaps, dict) else {}
    external = diagnostics.get("external_local_evidence_only")
    external = external if isinstance(external, dict) else {}
    suggestions = diagnostics.get("suggested_tuning_dimensions")
    suggestions = suggestions if isinstance(suggestions, list) else []
    return {
        "summary_path": paths["summary_json"],
        "csv_path": paths["csv_rows"],
        "readme_path": paths["readme_md"],
        "artifact_paths": paths,
        "output_dir": str(diagnostics_dir),
        "ok": diagnostics.get("ok"),
        "status": diagnostics.get("status"),
        "comparison_set_status": diagnostics.get("comparison_set_status"),
        "selected_comparison_count": diagnostics.get("selected_comparison_count"),
        "visual_comparison_count": diagnostics.get("visual_comparison_count"),
        "metadata_only_count": diagnostics.get("metadata_only_count"),
        "suggested_tuning_dimensions": suggestions,
        "suggested_tuning_dimension_names": [
            suggestion.get("dimension")
            for suggestion in suggestions
            if isinstance(suggestion, dict) and suggestion.get("dimension")
        ],
        "scorecard_path": scorecard.get("path") or paths["scorecard_png"],
        "scorecard_status": scorecard.get("status"),
        "scorecard_produced": scorecard.get("produced"),
        "media_assets_copied_into_repo": diagnostics.get("media_assets_copied_into_repo", False),
        "external_local_evidence_only": external,
        "external_selected_count": external.get("external_selected_count"),
        "external_selected_paths": external.get("external_selected_paths"),
        "absolute_sibling_paths_are_local_evidence_only": external.get(
            "absolute_sibling_paths_are_local_evidence_only"
        ),
        "missing_depth_reference": gaps.get("missing_depth_reference"),
        "missing_pick_place_video": gaps.get("missing_pick_place_video"),
        "no_videos": gaps.get("no_videos"),
        "videos_present": gaps.get("videos_present"),
        "reference_gaps": gaps.get("reference_gaps"),
        "render_dependencies": diagnostics.get("render_dependencies"),
        "input": diagnostics.get("input"),
        "limits": diagnostics.get("limits"),
    }


def metric_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def candidate_by_name(candidates: list[dict[str, Any]], name: str | None) -> dict[str, Any]:
    if not name:
        return {}
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("name") == name:
            return candidate
    return {}


def candidate_metric(candidate: dict[str, Any], key: str) -> float | None:
    metrics = candidate.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    return metric_number(metrics.get(key))


def sim_camera_profile_sweep_artifact_paths(
    sweep: dict[str, Any] | None,
    sweep_dir: Path,
    summary_path: Path,
) -> dict[str, str | None]:
    sweep = sweep if isinstance(sweep, dict) else {}
    artifacts = sweep.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    return {
        "summary_json": str(artifacts.get("summary_path") or summary_path),
        "candidate_montage_jpg": str(
            artifacts.get("candidate_montage_path") or sweep_dir / "candidate_montage.jpg"
        ),
        "candidate_dir": str(artifacts.get("candidate_dir") or sweep_dir / "candidates"),
        "current_overlay_jpg": artifacts.get("current_overlay_path"),
        "current_absolute_difference_jpg": artifacts.get("current_absolute_difference_path"),
        "current_side_by_side_jpg": artifacts.get("current_side_by_side_path"),
        "best_overlay_jpg": artifacts.get("best_overlay_path"),
        "best_absolute_difference_jpg": artifacts.get("best_absolute_difference_path"),
        "best_side_by_side_jpg": artifacts.get("best_side_by_side_path"),
    }


def sim_camera_profile_candidate_ranking(
    sweep: dict[str, Any] | None,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    sweep = sweep if isinstance(sweep, dict) else {}
    candidates = sweep.get("candidates")
    candidate_rows = [row for row in candidates if isinstance(row, dict)] if isinstance(candidates, list) else []
    current_mad = candidate_metric(current, "mean_abs_delta")
    current_rmse = candidate_metric(current, "rmse")
    ranked = sorted(
        candidate_rows,
        key=lambda row: (
            candidate_metric(row, "mean_abs_delta")
            if candidate_metric(row, "mean_abs_delta") is not None
            else float("inf"),
            str(row.get("name") or ""),
        ),
    )
    rows: list[dict[str, Any]] = []
    for rank, candidate in enumerate(ranked, start=1):
        mean_abs_delta = candidate_metric(candidate, "mean_abs_delta")
        rmse = candidate_metric(candidate, "rmse")
        rows.append(
            {
                "rank": rank,
                "candidate_id": candidate.get("name"),
                "candidate_name": candidate.get("name"),
                "description": candidate.get("description"),
                "mean_abs_delta": mean_abs_delta,
                "rmse": rmse,
                "mean_abs_delta_delta_vs_current": (
                    mean_abs_delta - current_mad
                    if mean_abs_delta is not None and current_mad is not None
                    else None
                ),
                "rmse_delta_vs_current": (
                    rmse - current_rmse if rmse is not None and current_rmse is not None else None
                ),
                "artifact_paths": {
                    "frame_path": candidate.get("frame_path"),
                    "annotated_path": candidate.get("annotated_path"),
                },
            }
        )
    return rows


def sim_camera_profile_sweep_section(
    sweep: dict[str, Any] | None,
    sweep_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    sweep = sweep if isinstance(sweep, dict) else {}
    candidates = sweep.get("candidates")
    candidate_rows = [row for row in candidates if isinstance(row, dict)] if isinstance(candidates, list) else []
    selection = sweep.get("selection")
    selection = selection if isinstance(selection, dict) else {}
    current = candidate_by_name(candidate_rows, "current")
    best_candidate_id = selection.get("best_candidate")
    best = candidate_by_name(candidate_rows, best_candidate_id if isinstance(best_candidate_id, str) else None)
    if not best and candidate_rows:
        best = min(
            candidate_rows,
            key=lambda row: (
                candidate_metric(row, "mean_abs_delta")
                if candidate_metric(row, "mean_abs_delta") is not None
                else float("inf"),
                str(row.get("name") or ""),
            ),
        )
        best_candidate_id = best.get("name")

    current_mad = candidate_metric(current, "mean_abs_delta")
    current_rmse = candidate_metric(current, "rmse")
    best_mad = candidate_metric(best, "mean_abs_delta")
    best_rmse = candidate_metric(best, "rmse")
    ranked_candidates = sim_camera_profile_candidate_ranking(sweep, current)
    remaining_prompts = [
        {
            "candidate_id": row.get("candidate_id"),
            "candidate_name": row.get("candidate_name"),
            "description": row.get("description"),
            "mean_abs_delta_delta_vs_current": row.get("mean_abs_delta_delta_vs_current"),
            "rmse_delta_vs_current": row.get("rmse_delta_vs_current"),
        }
        for row in ranked_candidates
        if row.get("candidate_id") != "current"
        and metric_number(row.get("mean_abs_delta_delta_vs_current")) is not None
        and float(row["mean_abs_delta_delta_vs_current"]) < 0.0
    ][:5]
    image = sweep.get("image")
    image = image if isinstance(image, dict) else {}
    current_gripper = current.get("gripper") if isinstance(current.get("gripper"), dict) else {}
    effective_profile_values = sweep.get("effective_profile_values")
    effective_profile_values = (
        effective_profile_values if isinstance(effective_profile_values, dict) else {}
    )
    paths = sim_camera_profile_sweep_artifact_paths(sweep, sweep_dir, summary_path)
    caveat = selection.get("caveat") or (
        "Full-frame image delta is hardware-free coarse review evidence only; it is not "
        "physical camera calibration truth."
    )
    if isinstance(caveat, str) and "hardware-free" not in caveat.lower():
        caveat = (
            f"{caveat} This suite treats the full-frame image delta as hardware-free "
            "coarse review evidence only, not physical calibration truth."
        )
    return {
        "summary_path": paths["summary_json"],
        "output_dir": str(sweep_dir),
        "artifact_paths": paths,
        "ok": bool(sweep.get("ok", False)),
        "status": sweep.get("status") or ("ok" if sweep.get("ok") is True else None),
        "profile_name": sweep.get("profile"),
        "reference_image_path": sweep.get("reference_image_path"),
        "current_gripper_finger_width_px": current_gripper.get(
            "finger_width_px",
            effective_profile_values.get("gripper_finger_width_px"),
        ),
        "marker_time_seconds": sweep.get("marker_time_seconds"),
        "candidate_count": image.get("candidate_count", len(candidate_rows)),
        "best_by": selection.get("best_by"),
        "current_candidate_id": current.get("name"),
        "current_candidate_name": current.get("name"),
        "current_mean_abs_delta": current_mad,
        "current_rmse": current_rmse,
        "best_candidate_id": best_candidate_id,
        "best_candidate_name": best.get("name"),
        "best_candidate_description": best.get("description"),
        "best_mean_abs_delta": best_mad,
        "best_rmse": best_rmse,
        "mean_abs_delta_delta_vs_current": (
            best_mad - current_mad if best_mad is not None and current_mad is not None else None
        ),
        "rmse_delta_vs_current": (
            best_rmse - current_rmse
            if best_rmse is not None and current_rmse is not None
            else None
        ),
        "current_vs_best_metrics": {
            "current_candidate_id": current.get("name"),
            "best_candidate_id": best_candidate_id,
            "current_mean_abs_delta": current_mad,
            "current_rmse": current_rmse,
            "best_mean_abs_delta": best_mad,
            "best_rmse": best_rmse,
            "mean_abs_delta_delta_vs_current": (
                best_mad - current_mad
                if best_mad is not None and current_mad is not None
                else None
            ),
            "rmse_delta_vs_current": (
                best_rmse - current_rmse
                if best_rmse is not None and current_rmse is not None
                else None
            ),
        },
        "candidate_ranking": ranked_candidates,
        "remaining_tuning_prompts": remaining_prompts,
        "full_frame_image_delta_caveat": caveat,
        "notes": [
            "This sweep is deterministic simulator-only review evidence and does not mutate SimCamera constants.",
            "Full-frame image delta is a coarse hardware-free ranking signal, not physical calibration truth.",
        ],
    }


def sim_camera_tuning_prompt_ids(prompts: Any) -> list[str]:
    prompt_rows = prompts if isinstance(prompts, list) else []
    ids: list[str] = []
    for prompt in prompt_rows:
        if not isinstance(prompt, dict):
            continue
        sweep = prompt.get("sweep")
        candidate = prompt.get("candidate")
        if isinstance(sweep, str) and isinstance(candidate, str):
            ids.append(f"{sweep}:{candidate}")
    return ids


def sim_camera_tuning_before_after_artifact_paths(
    tuning: dict[str, Any] | None,
    output_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    tuning = tuning if isinstance(tuning, dict) else {}
    artifacts = tuning.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    sweeps = tuning.get("sweeps")
    sweeps = sweeps if isinstance(sweeps, dict) else {}

    sweep_artifacts: dict[str, dict[str, Any]] = {}
    for role in ("baseline", "current"):
        sweep = sweeps.get(role)
        sweep = sweep if isinstance(sweep, dict) else {}
        role_artifacts = sweep.get("artifacts")
        sweep_artifacts[role] = role_artifacts if isinstance(role_artifacts, dict) else {}

    return {
        "summary_json": str(artifacts.get("summary_path") or summary_path),
        "csv_rows": str(artifacts.get("csv_path") or output_dir / SIM_CAMERA_TUNING_BEFORE_AFTER_CSV_NAME),
        "readme_md": str(artifacts.get("readme_path") or output_dir / SIM_CAMERA_TUNING_BEFORE_AFTER_README_NAME),
        "baseline_profile_sweep_dir": str(
            artifacts.get("baseline_profile_sweep_dir") or output_dir / "baseline_profile_sweep"
        ),
        "current_profile_sweep_dir": str(
            artifacts.get("current_profile_sweep_dir") or output_dir / "current_profile_sweep"
        ),
        "sweeps": sweep_artifacts,
    }


def metric_delta_value(deltas: dict[str, Any], key: str, metric: str) -> float | None:
    row = deltas.get(key)
    row = row if isinstance(row, dict) else {}
    return metric_number(row.get(metric))


def sweep_metric_value(sweep: dict[str, Any], candidate_key: str, metric: str) -> float | None:
    candidate = sweep.get(candidate_key)
    candidate = candidate if isinstance(candidate, dict) else {}
    metrics = candidate.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    return metric_number(metrics.get(metric))


def sim_camera_tuning_before_after_section(
    tuning: dict[str, Any] | None,
    output_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    tuning = tuning if isinstance(tuning, dict) else {}
    paths = sim_camera_tuning_before_after_artifact_paths(tuning, output_dir, summary_path)
    sweeps = tuning.get("sweeps")
    sweeps = sweeps if isinstance(sweeps, dict) else {}
    baseline = sweeps.get("baseline")
    baseline = baseline if isinstance(baseline, dict) else {}
    current = sweeps.get("current")
    current = current if isinstance(current, dict) else {}
    deltas = tuning.get("deltas")
    deltas = deltas if isinstance(deltas, dict) else {}
    gaps = tuning.get("open_reference_gaps")
    gaps = gaps if isinstance(gaps, dict) else {}
    caveats = tuning.get("caveats")
    caveats = caveats if isinstance(caveats, list) else []
    prompts = tuning.get("remaining_tuning_prompts")
    prompts = prompts if isinstance(prompts, list) else []
    return {
        "summary_path": paths["summary_json"],
        "csv_path": paths["csv_rows"],
        "readme_path": paths["readme_md"],
        "output_dir": str(output_dir),
        "artifact_paths": paths,
        "ok": bool(tuning.get("ok", False)),
        "status": tuning.get("status"),
        "profile_name": tuning.get("profile"),
        "reference_image_path": tuning.get("reference_image_path"),
        "baseline_gripper_finger_width_px": tuning.get("baseline_gripper_finger_width_px"),
        "current_gripper_finger_width_px": tuning.get("current_gripper_finger_width_px"),
        "marker_time_seconds": tuning.get("marker_time_seconds"),
        "baseline_candidate_count": baseline.get("candidate_count"),
        "current_candidate_count": current.get("candidate_count"),
        "baseline_current_mean_abs_delta": sweep_metric_value(
            baseline, "current_candidate", "mean_abs_delta"
        ),
        "baseline_current_rmse": sweep_metric_value(baseline, "current_candidate", "rmse"),
        "current_profile_mean_abs_delta": sweep_metric_value(
            current, "current_candidate", "mean_abs_delta"
        ),
        "current_profile_rmse": sweep_metric_value(current, "current_candidate", "rmse"),
        "baseline_best_candidate": (
            baseline.get("best_candidate", {}).get("name")
            if isinstance(baseline.get("best_candidate"), dict)
            else None
        ),
        "current_best_candidate": (
            current.get("best_candidate", {}).get("name")
            if isinstance(current.get("best_candidate"), dict)
            else None
        ),
        "baseline_best_mean_abs_delta": sweep_metric_value(
            baseline, "best_candidate", "mean_abs_delta"
        ),
        "baseline_best_rmse": sweep_metric_value(baseline, "best_candidate", "rmse"),
        "current_best_mean_abs_delta": sweep_metric_value(
            current, "best_candidate", "mean_abs_delta"
        ),
        "current_best_rmse": sweep_metric_value(current, "best_candidate", "rmse"),
        "current_vs_baseline_mean_abs_delta": metric_delta_value(
            deltas,
            "current_profile_delta_vs_baseline_current_candidate",
            "mean_abs_delta",
        ),
        "current_vs_baseline_rmse": metric_delta_value(
            deltas,
            "current_profile_delta_vs_baseline_current_candidate",
            "rmse",
        ),
        "best_vs_baseline_best_mean_abs_delta": metric_delta_value(
            deltas,
            "current_best_delta_vs_baseline_best_candidate",
            "mean_abs_delta",
        ),
        "best_vs_baseline_best_rmse": metric_delta_value(
            deltas,
            "current_best_delta_vs_baseline_best_candidate",
            "rmse",
        ),
        "best_vs_baseline_current_mean_abs_delta": metric_delta_value(
            deltas,
            "current_best_delta_vs_baseline_current_candidate",
            "mean_abs_delta",
        ),
        "best_vs_baseline_current_rmse": metric_delta_value(
            deltas,
            "current_best_delta_vs_baseline_current_candidate",
            "rmse",
        ),
        "deltas": deltas,
        "remaining_tuning_prompts": prompts,
        "remaining_tuning_prompt_count": len(prompts),
        "remaining_tuning_prompt_ids": sim_camera_tuning_prompt_ids(prompts),
        "media_assets_copied_into_repo": tuning.get("media_assets_copied_into_repo", False),
        "open_reference_gaps": gaps,
        "missing_real_depth_reference": gaps.get("missing_real_depth_reference"),
        "missing_pick_place_video": gaps.get("missing_pick_place_video"),
        "full_frame_image_delta_caveat": (
            next((str(caveat) for caveat in caveats if "Full-frame image delta" in str(caveat)), None)
            or "Full-frame image delta is hardware-free coarse review evidence only."
        ),
        "caveats": caveats,
        "child_commands": tuning.get("child_commands"),
        "sweeps": sweeps,
    }


def manifest_status_section(
    *,
    requested_manifest: Path | None,
    inventory: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
) -> dict[str, Any]:
    manifest_summary = inventory.get("manifest_summary") if inventory else None
    manifest_summary = manifest_summary if isinstance(manifest_summary, dict) else {}
    inventory_summary = inventory.get("summary") if inventory else None
    inventory_summary = inventory_summary if isinstance(inventory_summary, dict) else {}
    selected_media = comparison.get("selected_media") if comparison else None
    selected_rows = selected_media if isinstance(selected_media, list) else []
    declared_selected = [
        row
        for row in selected_rows
        if isinstance(row, dict)
        and isinstance(row.get("manifest_validation"), dict)
        and row["manifest_validation"].get("declared") is True
    ]
    requested_path = str(requested_manifest) if requested_manifest is not None else None
    return {
        "supplied": bool(manifest_summary.get("supplied", requested_manifest is not None)),
        "requested_path": requested_path,
        "path": manifest_summary.get("path", requested_path),
        "ok": manifest_summary.get("ok"),
        "status": manifest_summary.get("status"),
        "declared_media_count": manifest_summary.get("declared_media_count"),
        "valid_media_count": manifest_summary.get("valid_media_count"),
        "matched_media_count": manifest_summary.get("matched_media_count"),
        "manifest_declared_media_count": inventory_summary.get("manifest_declared_media_count"),
        "selected_declared_media_count": len(declared_selected),
        "selected_declared_media": [
            {
                "relative_path": row.get("relative_path"),
                "capture_id": (
                    row.get("declared_metadata", {}).get("capture_id")
                    if isinstance(row.get("declared_metadata"), dict)
                    else None
                ),
                "declared_target_categories": (
                    row.get("declared_metadata", {}).get("declared_target_categories")
                    if isinstance(row.get("declared_metadata"), dict)
                    else None
                ),
                "failure_mode": (
                    row.get("declared_metadata", {}).get("failure_mode")
                    if isinstance(row.get("declared_metadata"), dict)
                    else None
                ),
                "manifest_validation": row.get("manifest_validation"),
            }
            for row in declared_selected
        ],
        "issue_count": manifest_summary.get("issue_count"),
        "issues": manifest_summary.get("issues"),
    }


def ranking_summary(session: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not session:
        return []
    ranking = session.get("ranking")
    if not isinstance(ranking, list):
        return []
    slim: list[dict[str, Any]] = []
    for item in ranking:
        if not isinstance(item, dict):
            continue
        slim.append(
            {
                "rank": item.get("rank"),
                "candidate_id": item.get("candidate_id"),
                "rank_score": item.get("rank_score"),
                "total_penalty": item.get("total_penalty"),
                "all_smokes_ok": item.get("all_smokes_ok"),
                "smoke_failures": item.get("smoke_failures"),
                "artifact_paths": item.get("artifact_paths"),
            }
        )
    return slim


def selected_from_session(session: dict[str, Any] | None, select_rank: int) -> dict[str, Any] | None:
    for item in ranking_summary(session):
        if item.get("rank") == select_rank:
            return item
    return None


def selected_fixture_artifacts(fixture: dict[str, Any] | None) -> dict[str, str]:
    if not fixture:
        return {}
    artifacts = fixture.get("artifact_paths")
    if not isinstance(artifacts, dict):
        return {}
    wanted_tokens = (
        "comparison_side_by_side",
        "comparison_heatmap",
        "board_pose_annotated",
        "pick_place_release",
        "pick_place_release_capture",
        "fixture",
        "session_summary",
    )
    return {
        str(key): str(value)
        for key, value in sorted(artifacts.items())
        if isinstance(value, str) and any(token in str(key) for token in wanted_tokens)
    }


def sim_camera_pose_fixture_section(pose_fixture: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    artifacts = pose_fixture.get("artifacts") if pose_fixture else None
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    frame_paths = artifacts.get("frame_paths")
    annotated_frame_paths = artifacts.get("annotated_frame_paths")
    metadata_paths = artifacts.get("metadata_paths")
    cases = pose_fixture.get("cases") if pose_fixture else None
    case_rows = cases if isinstance(cases, list) else []
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(pose_fixture.get("ok", False)) if pose_fixture else False,
        "status": pose_fixture.get("status") if pose_fixture else None,
        "case_count": pose_fixture.get("case_count") if pose_fixture else None,
        "case_ids": pose_fixture.get("case_ids") if pose_fixture else None,
        "frame_paths": frame_paths if isinstance(frame_paths, dict) else {},
        "annotated_frame_paths": annotated_frame_paths if isinstance(annotated_frame_paths, dict) else {},
        "metadata_paths": metadata_paths if isinstance(metadata_paths, dict) else {},
        "hardware_skipped": pose_fixture.get("hardware_skipped") if pose_fixture else None,
        "gui_skipped": pose_fixture.get("gui_skipped") if pose_fixture else None,
        "metadata_contract": pose_fixture.get("metadata_contract") if pose_fixture else None,
        "comparisons_to_nominal": pose_fixture.get("comparisons_to_nominal") if pose_fixture else None,
        "cases": [
            {
                "case_id": case.get("case_id"),
                "view": case.get("view"),
                "profile": case.get("profile"),
                "target_square": (
                    case.get("projection", {}).get("target_square", {}).get("square")
                    if isinstance(case.get("projection"), dict)
                    else None
                ),
                "piece_square": (
                    case.get("projection", {}).get("piece_square", {}).get("square")
                    if isinstance(case.get("projection"), dict)
                    else None
                ),
                "unique_colors": (
                    case.get("image", {}).get("unique_colors") if isinstance(case.get("image"), dict) else None
                ),
                "metadata_contract_checks": (
                    case.get("metadata_contract_checks")
                    if isinstance(case.get("metadata_contract_checks"), dict)
                    else None
                ),
            }
            for case in case_rows
            if isinstance(case, dict)
        ],
    }


def app_entrypoint_metadata_section(
    app_entrypoint: dict[str, Any] | None,
    *,
    summary_path: Path,
    frame_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    app_entrypoint = app_entrypoint if isinstance(app_entrypoint, dict) else {}
    camera = app_entrypoint.get("camera")
    camera = camera if isinstance(camera, dict) else {}
    contract = camera.get("metadata_contract")
    contract = contract if isinstance(contract, dict) else {}
    app_camera_status = app_entrypoint.get("app_camera_status")
    if not isinstance(app_camera_status, dict):
        app_camera_status = camera.get("app_camera_status")
    app_camera_status = app_camera_status if isinstance(app_camera_status, dict) else None
    checks = contract.get("checks")
    check_rows = [check for check in checks if isinstance(check, dict)] if isinstance(checks, list) else []
    contract_checks = {
        str(check.get("name")): bool(check.get("ok"))
        for check in check_rows
        if isinstance(check.get("name"), str)
    }
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(app_entrypoint.get("ok", False)),
        "status": app_entrypoint.get("status") or ("ok" if app_entrypoint.get("ok") is True else None),
        "sim_camera_profile": app_entrypoint.get("sim_camera_profile"),
        "frame_path": app_entrypoint.get("frame") if isinstance(app_entrypoint.get("frame"), str) else str(frame_path),
        "metadata_path": (
            app_entrypoint.get("metadata")
            if isinstance(app_entrypoint.get("metadata"), str)
            else str(metadata_path)
        ),
        "hardware_skipped": app_entrypoint.get("hardware_skipped", True),
        "gui_skipped": app_entrypoint.get("gui_skipped", True),
        "openai_skipped": app_entrypoint.get("openai_skipped", True),
        "skipped_markers": app_entrypoint.get("skipped_markers"),
        "metadata_contract": contract,
        "metadata_contract_checks": contract_checks,
        "app_camera_status": app_camera_status,
        "camera": {
            "width": camera.get("width"),
            "height": camera.get("height"),
            "fps": camera.get("fps"),
            "view": camera.get("view"),
            "piece_square": camera.get("piece_square"),
            "piece_layout": camera.get("piece_layout"),
            "gripper_visible": camera.get("gripper_visible"),
        },
    }


def matrix_summary_section(matrix: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    scenarios = matrix.get("scenarios") if matrix else None
    scenario_rows = scenarios if isinstance(scenarios, list) else []
    aggregate_status = matrix.get("aggregate_status") if matrix else None
    aggregate_status = aggregate_status if isinstance(aggregate_status, dict) else {}
    selected_frame_paths: dict[str, dict[str, str]] = {}
    release_frame_paths: dict[str, str] = {}
    piece_visibility_by_scenario: dict[str, dict[str, Any]] = {}
    scenario_ids: list[str] = []
    limitations: list[str] = []

    for scenario in scenario_rows:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str):
            continue
        scenario_ids.append(scenario_id)
        frames = scenario.get("selected_frame_paths")
        if isinstance(frames, dict):
            selected_frame_paths[scenario_id] = {
                str(key): str(value)
                for key, value in sorted(frames.items())
                if isinstance(value, str)
            }
            release_path = frames.get("target_release_open_path")
            if isinstance(release_path, str):
                release_frame_paths[scenario_id] = release_path
        visibility = scenario.get("piece_visibility")
        aggregate = visibility.get("aggregate") if isinstance(visibility, dict) else None
        if isinstance(aggregate, dict):
            piece_visibility_by_scenario[scenario_id] = {
                "available": aggregate.get("available"),
                "all_captures_clear_of_gripper": aggregate.get("all_captures_clear_of_gripper"),
                "min_visible_fraction": aggregate.get("min_visible_fraction"),
                "max_occlusion_fraction": aggregate.get("max_occlusion_fraction"),
                "min_clearance_px": aggregate.get("min_clearance_px"),
                "worst_capture_label": aggregate.get("worst_capture_label"),
                "target_release_open": aggregate.get("target_release_open"),
            }
        for limitation in scenario.get("limitations", []):
            if isinstance(limitation, str) and limitation not in limitations:
                limitations.append(limitation)

    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(matrix.get("ok", False)) if matrix else False,
        "status": matrix.get("status") if matrix else None,
        "aggregate_status": aggregate_status,
        "scenario_count": aggregate_status.get("scenario_count", len(scenario_ids)),
        "scenario_ids": scenario_ids,
        "failed_scenario_ids": aggregate_status.get("failed_scenario_ids", []),
        "selected_frame_paths": selected_frame_paths,
        "release_frame_paths": release_frame_paths,
        "piece_visibility": matrix.get("piece_visibility") if matrix else None,
        "piece_visibility_by_scenario": piece_visibility_by_scenario,
        "limitations": limitations,
    }


def gripper_camera_pov_section(pov: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    artifacts = pov.get("artifacts") if pov else None
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    frame_paths = artifacts.get("frame_paths")
    annotated_frame_paths = artifacts.get("annotated_frame_paths")
    metadata_paths = artifacts.get("metadata_paths")
    states = pov.get("states") if pov else None
    state_rows = states if isinstance(states, list) else []
    visibility_by_state: dict[str, dict[str, Any]] = {}
    projection_by_state: dict[str, dict[str, Any]] = {}
    gripper_by_state: dict[str, dict[str, Any]] = {}
    for state in state_rows:
        if not isinstance(state, dict):
            continue
        state_id = state.get("state_id")
        if not isinstance(state_id, str):
            continue
        visibility = state.get("visibility_row")
        if isinstance(visibility, dict):
            visibility_by_state[state_id] = {
                "available": visibility.get("available"),
                "status": visibility.get("status"),
                "piece_square": visibility.get("piece_square"),
                "piece_center_xy": visibility.get("piece_center_xy"),
                "visible_fraction": visibility.get("visible_fraction"),
                "occlusion_fraction": visibility.get("occlusion_fraction"),
                "min_clearance_px": visibility.get("min_clearance_px"),
                "clear_of_gripper": visibility.get("clear_of_gripper"),
                "current_gripper_opening_px": visibility.get("current_gripper_opening_px"),
                "tracked_gripper_percent": visibility.get("tracked_gripper_percent"),
            }
        projection = state.get("projection")
        if isinstance(projection, dict):
            target_square = projection.get("target_square")
            piece_square = projection.get("piece_square")
            projection_by_state[state_id] = {
                "target_square": target_square if isinstance(target_square, dict) else None,
                "piece_square": piece_square if isinstance(piece_square, dict) else None,
            }
        gripper_state = state.get("gripper_state")
        if isinstance(gripper_state, dict):
            gripper_by_state[state_id] = {
                "action": gripper_state.get("action"),
                "requested_percent": gripper_state.get("requested_percent"),
                "tracked_gripper_percent": gripper_state.get("tracked_gripper_percent"),
                "current_gripper_opening_px": gripper_state.get("current_gripper_opening_px"),
            }

    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(pov.get("ok", False)) if pov else False,
        "status": pov.get("status") if pov else None,
        "target_square": pov.get("target_square") if pov else None,
        "state_count": pov.get("state_count") if pov else None,
        "state_ids": pov.get("state_ids") if pov else None,
        "frame_paths": frame_paths if isinstance(frame_paths, dict) else {},
        "annotated_frame_paths": annotated_frame_paths if isinstance(annotated_frame_paths, dict) else {},
        "metadata_paths": metadata_paths if isinstance(metadata_paths, dict) else {},
        "hardware_skipped": pov.get("hardware_skipped") if pov else None,
        "gui_skipped": pov.get("gui_skipped") if pov else None,
        "openai_skipped": pov.get("openai_skipped") if pov else None,
        "metadata_contract": pov.get("metadata_contract") if pov else None,
        "piece_visibility": pov.get("piece_visibility") if pov else None,
        "visibility_by_state": visibility_by_state,
        "projection_by_state": projection_by_state,
        "gripper_by_state": gripper_by_state,
        "limitations": pov.get("limitations") if pov else None,
    }


def ik_reachability_section(ik: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    ik = ik if isinstance(ik, dict) else {}
    artifacts = ik.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    row_summary = ik.get("summary")
    row_summary = row_summary if isinstance(row_summary, dict) else {}
    model_diagnostic = ik.get("model_diagnostic")
    model_diagnostic = model_diagnostic if isinstance(model_diagnostic, dict) else {}
    model_solver = ik.get("model_solver")
    model_solver = model_solver if isinstance(model_solver, dict) else {}
    explicit_model_path = model_diagnostic.get("explicit_model_path")
    configured_model_path = None
    if isinstance(explicit_model_path, dict):
        candidate_path = explicit_model_path.get("path")
        configured_model_path = candidate_path if isinstance(candidate_path, str) else None
    elif isinstance(explicit_model_path, str):
        configured_model_path = explicit_model_path
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(ik.get("ok", False)),
        "status": ik.get("status"),
        "row_count": row_summary.get("row_count"),
        "counts_by_feasibility": row_summary.get("counts_by_feasibility"),
        "configured_model_path": configured_model_path,
        "configured_model_request": explicit_model_path,
        "artifacts": {
            "summary_json": artifacts.get("summary_json") if isinstance(artifacts.get("summary_json"), str) else str(summary_path),
            "rows_csv": artifacts.get("rows_csv"),
            "heatmap_png": artifacts.get("heatmap_png"),
        },
        "model_diagnostic": {
            "status": model_diagnostic.get("status"),
            "reason": model_diagnostic.get("reason"),
            "selected_model_path": model_diagnostic.get("selected_model_path"),
            "selected_model_source": model_diagnostic.get("selected_model_source"),
            "repo_local_model_count": model_diagnostic.get("repo_local_model_count"),
        },
        "model_solver": {
            "available": model_solver.get("available"),
            "status": model_solver.get("status"),
            "target_frame": model_solver.get("target_frame"),
            "solver_backend": model_solver.get("solver_backend"),
            "reason": model_solver.get("reason"),
        },
        "hardware_skipped": ik.get("hardware_skipped"),
        "gui_skipped": ik.get("gui_skipped"),
        "openai_skipped": ik.get("openai_skipped"),
        "limitations": ik.get("limitations"),
    }


def so101_mujoco_smoke_section(smoke: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    smoke = smoke if isinstance(smoke, dict) else {}
    artifacts = smoke.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    dependencies = smoke.get("dependencies")
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    next_required = smoke.get("next_required_for_goal")
    next_required = next_required if isinstance(next_required, list) else []
    next_required_action_ids = smoke.get("next_required_action_ids")
    next_required_action_ids = (
        unique_string_values(next_required_action_ids)
        if isinstance(next_required_action_ids, list)
        else unique_string_values([action.get("action_id") for action in next_required if isinstance(action, dict)])
    )
    next_required_action_count = smoke.get("next_required_action_count")
    if not isinstance(next_required_action_count, int):
        next_required_action_count = len(next_required)
    section: dict[str, Any] = {
        "summary_path": artifacts.get("summary_json") or str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(smoke.get("ok", False)),
        "status": smoke.get("status"),
        "artifacts": {
            "summary_json": artifacts.get("summary_json") or str(summary_path),
            **{key: value for key, value in artifacts.items() if key != "summary_json"},
        },
        "dependencies": dependencies,
        "model_authority": smoke.get("model_authority"),
        "physical_so101_model_authority_ready": smoke.get("physical_so101_model_authority_ready"),
        "hardware_free_regression_fixture_ready": smoke.get("hardware_free_regression_fixture_ready"),
        "synthetic_fixture_authority_fields": smoke.get("synthetic_fixture_authority_fields"),
        "observed_evidence_is_physical_so101_authority": smoke.get(
            "observed_evidence_is_physical_so101_authority"
        ),
        "observed_evidence_is_policy_training_authority": smoke.get(
            "observed_evidence_is_policy_training_authority"
        ),
        "ready_for_model_backed_ik": smoke.get("ready_for_model_backed_ik"),
        "limitations": smoke.get("limitations"),
        "next_required_for_goal": next_required,
        "next_required_action_ids": next_required_action_ids,
        "next_required_action_count": next_required_action_count,
    }
    for key in (
        "mujoco_model_load",
        "mujoco_joint_limit_enablement",
        "joint_limit_model_consistency",
        "sim_robot_mujoco_sync",
        "env_scripted_pick_place",
        "sim_status",
        "contact_model",
        "scripted_pick_place",
        "reset_count",
        "all_resets_ok",
        "all_mujoco_fallback_free",
        "invalid_reset_count",
        "invalid_reset_case_ids",
        "invalid_reset_failed_case_ids",
        "all_invalid_resets_rejected",
        "recovery_after_invalid_resets_ok",
        "all_piece_resets_ok",
        "all_board_contacts_observed",
        "probe_count",
        "gripper_contact_observed",
        "two_finger_contact_observed",
        "settled_gripper_contact_observed",
        "source_square",
        "source_pick_started_at_source",
        "source_pick_xy_tolerance_m",
        "close_two_finger_contact_observed",
        "lift_verified",
        "lift_without_manual_piece_pose_m",
        "lift_z_threshold_m",
        "board_contact_cleared_during_lift",
        "transfer_verified",
        "transfer_xy_m",
        "transfer_xy_threshold_m",
        "transfer_target_xy_error_m",
        "transfer_source_to_target_progress_m",
        "place_without_manual_piece_pose_verified",
        "lift_place_physics_verified",
        "board_source_pick_place_verified",
        "release_contact_cleared",
        "release_contact_cleared_after_retreat",
        "final_board_contact_observed",
        "final_target_xy_error_m",
        "target_xy_tolerance_m",
        "final_place_z_error_m",
        "place_z_tolerance_m",
        "pick_place_phase_evidence",
        "pick_place_phase_ids",
        "pick_place_failed_phase_ids",
        "pick_place_phase_count",
        "pick_place_all_required_phases_verified",
        "required_stage_sequence",
        "observed_stage_sequence",
        "missing_stage_ids",
        "unexpected_stage_ids",
        "stage_sequence_order_ok",
        "manual_piece_pose_after_reset_stage_ids",
        "stage_sequence_contract_ok",
        "stage_sequence_contract_errors",
        "source_to_target_progress_m",
        "target_square",
        "piece_reset_to_source_before_run",
        "manual_piece_pose_used_for_fixture",
        "manual_piece_pose_used_after_fixture",
        "manual_piece_pose_used_after_reset",
        "robot_pose_seeded_for_source_fixture",
        "robot_motion_mode",
        "episode_count",
        "transition_count",
        "all_scripted_pick_place_complete",
        "all_mujoco_piece_release_synced",
        "development_prerequisites_satisfied",
        "board_pick_prerequisite",
        "gymnasium_required",
        "mujoco_backend_required",
        "mujoco_backend_loaded",
        "joint_state_fallback_active",
        "gymnasium_task_wiring_status",
        "gymnasium_api_contract",
        "mujoco_scene_validity_status",
        "reviewed_mujoco_handoff_requested",
        "reviewed_mujoco_handoff_required",
        "reviewed_mujoco_handoff_path",
        "reviewed_mujoco_handoff_intake_status",
        "reviewed_mujoco_handoff_intake_ok",
        "reviewed_mujoco_handoff_contract_ok",
        "reviewed_mujoco_handoff_ready",
        "reviewed_mujoco_handoff_source_status",
        "reviewed_mujoco_handoff_schema",
        "reviewed_mujoco_handoff_model_authority",
        "reviewed_mujoco_handoff_observed_evidence_is_authority",
        "reviewed_mujoco_handoff_physical_truth_claimed",
        "reviewed_mujoco_fixture_handoff_ready_not_physical_so101_authority",
        "reviewed_mujoco_handoff_motion_authority_status",
        "reviewed_mujoco_handoff_physical_motion_checked",
        "reviewed_mujoco_handoff_hardware_free_fixture_motion_checked",
        "reviewed_mujoco_handoff_motion_evidence_not_physical_so101_authority",
        "reviewed_mujoco_handoff_physical_so101_model_authority_ready",
        "reviewed_mujoco_handoff_joint_limit_enablement_ok",
        "reviewed_mujoco_handoff_joint_limit_enablement_status",
        "reviewed_mujoco_handoff_missing_limited_joints",
        "reviewed_mujoco_handoff_item_ids",
        "reviewed_mujoco_handoff_blockers",
        "scene_uses_reviewed_mujoco_handoff",
        "max_steps",
        "square_geom_count",
        "target_frame_site_present",
        "target_marker_present",
        "training_authority_status",
        "training_authority_blockers",
        "ready_for_policy_training",
        "rollout_use",
        "serious_policy_training_blockers",
        "manifest_status",
        "manifest_request",
        "model_path",
        "asset_roots",
        "target_frame",
        "tcp_offset",
        "base_to_board_alignment",
        "reviewed_model_motion_checked",
        "motion_authority_status",
        "physical_reviewed_model_motion_checked",
        "hardware_free_fixture_motion_checked",
        "motion_evidence_not_physical_so101_authority",
        "motion_authority",
        "downstream_handoff_schema",
        "downstream_handoff_status",
        "downstream_handoff_model_authority",
        "downstream_handoff_ready",
        "fixture_handoff_ready_not_physical_so101_authority",
        "downstream_handoff_observed_evidence_is_authority",
        "downstream_handoff_physical_so101_truth_claimed",
        "downstream_handoff_development_fixture_evidence_not_physical_so101_truth",
        "downstream_handoff_item_count",
        "downstream_handoff_item_ids",
        "require_ready_reviewed_model",
        "missing_inputs",
    ):
        if key in smoke:
            section[key] = smoke.get(key)
    return section


def so101_model_contract_section(contract: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    model_request = contract.get("model_request")
    model_request = model_request if isinstance(model_request, dict) else {}
    robot_kinematics_path = contract.get("robot_kinematics_path")
    robot_kinematics_path = robot_kinematics_path if isinstance(robot_kinematics_path, dict) else {}
    expected_contract = contract.get("expected_contract")
    expected_contract = expected_contract if isinstance(expected_contract, dict) else {}
    artifacts = contract.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    asset_preflight = contract.get("model_asset_preflight")
    asset_preflight = asset_preflight if isinstance(asset_preflight, dict) else {}
    asset_root_configuration = contract.get("model_asset_root_configuration")
    asset_root_configuration = asset_root_configuration if isinstance(asset_root_configuration, dict) else {}
    missing_alignment_inputs = contract.get("model_to_sim_alignment_inputs_missing")
    missing_alignment_inputs = missing_alignment_inputs if isinstance(missing_alignment_inputs, list) else []
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(contract.get("ok", False)),
        "status": contract.get("status"),
        "model_request_status": model_request.get("status"),
        "model_request": {
            "status": model_request.get("status"),
            "path": model_request.get("path"),
            "exists": model_request.get("exists"),
            "supported_suffix": model_request.get("supported_suffix"),
            "suffix": model_request.get("suffix"),
            "reason": model_request.get("reason"),
        },
        "model_asset_root_configuration": {
            "asset_roots": asset_root_configuration.get("asset_roots"),
            "asset_root_count": asset_root_configuration.get("asset_root_count"),
            "asset_root_checks": asset_root_configuration.get("asset_root_checks"),
            "notes": asset_root_configuration.get("notes"),
        },
        "robot_kinematics_status": robot_kinematics_path.get("status"),
        "robot_kinematics_path": {
            "status": robot_kinematics_path.get("status"),
            "directly_usable": robot_kinematics_path.get("directly_usable"),
            "placo_available": robot_kinematics_path.get("placo_available"),
            "reason": robot_kinematics_path.get("reason"),
            "robot_kinematics_source": robot_kinematics_path.get("robot_kinematics_source"),
        },
        "target_frame": expected_contract.get("target_frame"),
        "body_joints": expected_contract.get("body_joints"),
        "model_asset_preflight": {
            "status": asset_preflight.get("status"),
            "ok": asset_preflight.get("ok"),
            "model_request_status": asset_preflight.get("model_request_status"),
            "asset_roots": asset_preflight.get("asset_roots"),
            "asset_root_checks": asset_preflight.get("asset_root_checks"),
            "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
            "present_asset_count": asset_preflight.get("present_asset_count"),
            "missing_asset_count": asset_preflight.get("missing_asset_count"),
            "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
            "missing_assets": asset_preflight.get("missing_assets"),
            "unresolved_references": asset_preflight.get("unresolved_references"),
            "diagnostics": asset_preflight.get("diagnostics"),
            "artifacts": asset_preflight.get("artifacts"),
        },
        "missing_alignment_input_count": len(missing_alignment_inputs),
        "missing_alignment_inputs": missing_alignment_inputs,
        "artifacts": {
            "summary_json": artifacts.get("summary_json")
            if isinstance(artifacts.get("summary_json"), str)
            else str(summary_path),
            "checklist_csv": artifacts.get("checklist_csv"),
            "readme_md": artifacts.get("readme_md"),
        },
        "hardware_skipped": contract.get("hardware_skipped"),
        "gui_skipped": contract.get("gui_skipped"),
        "openai_skipped": contract.get("openai_skipped"),
        "limitations": contract.get("limitations"),
    }


def so101_model_source_inventory_section(
    inventory: dict[str, Any] | None,
    summary_path: Path,
    source_configuration: dict[str, Any],
) -> dict[str, Any]:
    inventory = inventory if isinstance(inventory, dict) else {}
    artifacts = inventory.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    recommended_contract_check = inventory.get("recommended_contract_check")
    recommended_contract_check = (
        recommended_contract_check
        if isinstance(recommended_contract_check, dict)
        else None
    )
    diagnostics = inventory.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(inventory.get("ok", False)),
        "status": inventory.get("status"),
        "candidate_count": inventory.get("candidate_count"),
        "likely_candidate_count": inventory.get("likely_candidate_count"),
        "direct_contract_candidate_count": inventory.get("direct_contract_candidate_count"),
        "authoritative_candidate_count": inventory.get("authoritative_candidate_count"),
        "authoritative_source_selection_status": inventory.get(
            "authoritative_source_selection_status"
        ),
        "authoritative_candidate_ids": inventory.get("authoritative_candidate_ids") or [],
        "authoritative_candidate_paths": inventory.get("authoritative_candidate_paths") or [],
        "selected_authoritative_candidate_id": inventory.get(
            "selected_authoritative_candidate_id"
        ),
        "selected_authoritative_candidate_path": inventory.get(
            "selected_authoritative_candidate_path"
        ),
        "selected_authoritative_candidate_sha256": inventory.get(
            "selected_authoritative_candidate_sha256"
        ),
        "source_authority_review_status": inventory.get("source_authority_review_status"),
        "source_authority_review_ready": inventory.get("source_authority_review_ready"),
        "source_authority_review": inventory.get("source_authority_review"),
        "source_authority_review_scope_ready": inventory.get(
            "source_authority_review_scope_ready"
        ),
        "source_authority_required_review_scope_ids": inventory.get(
            "source_authority_required_review_scope_ids"
        )
        or [],
        "source_authority_supplied_review_scope_ids": inventory.get(
            "source_authority_supplied_review_scope_ids"
        )
        or [],
        "source_authority_missing_review_scope_ids": inventory.get(
            "source_authority_missing_review_scope_ids"
        )
        or [],
        "source_authority_gate_status": inventory.get("source_authority_gate_status"),
        "source_authority_blockers": inventory.get("source_authority_blockers") or [],
        "root_count": inventory.get("root_count"),
        "source_configuration": source_configuration,
        "configured_model_source_roots": source_configuration.get("model_source_roots"),
        "configured_model_source_extra_roots": source_configuration.get("model_source_extra_roots"),
        "configured_authoritative_model_paths": source_configuration.get("authoritative_model_paths"),
        "configured_authoritative_model_roots": source_configuration.get("authoritative_model_roots"),
        "recommended_contract_check": recommended_contract_check,
        "recommended_contract_check_path": (
            recommended_contract_check.get("candidate_path")
            if recommended_contract_check
            else None
        ),
        "next_required_for_goal": inventory.get("next_required_for_goal") or [],
        "next_required_action_ids": inventory.get("next_required_action_ids") or [],
        "review_packet_status": inventory.get("review_packet_status"),
        "review_packet_model_authority": inventory.get("review_packet_model_authority"),
        "review_packet_item_count": inventory.get("review_packet_item_count"),
        "review_packet_item_ids": inventory.get("review_packet_item_ids") or [],
        "review_packet_needs_operator_review_item_ids": inventory.get(
            "review_packet_needs_operator_review_item_ids"
        )
        or [],
        "review_packet_action_ids": inventory.get("review_packet_action_ids") or [],
        "review_packet_observed_evidence_is_authority": inventory.get(
            "review_packet_observed_evidence_is_authority"
        ),
        "review_packet_development_fixture_evidence_not_physical_so101_truth": inventory.get(
            "review_packet_development_fixture_evidence_not_physical_so101_truth"
        ),
        "review_packet_physical_so101_model_authority_ready": inventory.get(
            "review_packet_physical_so101_model_authority_ready"
        ),
        "source_intake_status": inventory.get("source_intake_status"),
        "source_intake_model_authority": inventory.get("source_intake_model_authority"),
        "source_intake_action_count": inventory.get("source_intake_action_count"),
        "source_intake_action_ids": inventory.get("source_intake_action_ids") or [],
        "source_intake_observed_evidence_is_authority": inventory.get(
            "source_intake_observed_evidence_is_authority"
        ),
        "source_intake_physical_so101_model_authority_ready": inventory.get(
            "source_intake_physical_so101_model_authority_ready"
        ),
        "source_intake_development_fixture_evidence_not_physical_so101_truth": inventory.get(
            "source_intake_development_fixture_evidence_not_physical_so101_truth"
        ),
        "source_intake_checklist_json_path": inventory.get(
            "source_intake_checklist_json_path"
        )
        or artifacts.get("source_intake_checklist_json"),
        "source_intake_checklist_csv_path": inventory.get(
            "source_intake_checklist_csv_path"
        )
        or artifacts.get("source_intake_checklist_csv"),
        "source_intake_checklist": inventory.get("source_intake_checklist"),
        "diagnostics": diagnostics,
        "artifacts": {
            "summary_json": artifacts.get("summary_json")
            if isinstance(artifacts.get("summary_json"), str)
            else str(summary_path),
            "candidates_csv": artifacts.get("candidates_csv"),
            "review_packet_json": artifacts.get("review_packet_json"),
            "review_packet_csv": artifacts.get("review_packet_csv"),
            "source_intake_checklist_json": artifacts.get("source_intake_checklist_json"),
            "source_intake_checklist_csv": artifacts.get("source_intake_checklist_csv"),
            "readme_md": artifacts.get("readme_md"),
        },
        "hardware_skipped": inventory.get("hardware_skipped"),
        "gui_skipped": inventory.get("gui_skipped"),
        "openai_skipped": inventory.get("openai_skipped"),
        "limitations": inventory.get("limitations"),
    }


def so101_model_bundle_probe_section(
    probe: dict[str, Any] | None,
    summary_path: Path,
    selected_model_path: Path | None,
    asset_roots: list[Path],
) -> dict[str, Any]:
    probe = probe if isinstance(probe, dict) else {}
    artifacts = probe.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    model_request = probe.get("model_request")
    model_request = model_request if isinstance(model_request, dict) else {}
    asset_root_config = probe.get("asset_roots")
    asset_root_config = asset_root_config if isinstance(asset_root_config, dict) else {}
    authority = probe.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    provenance = probe.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    contract_checker = probe.get("contract_checker")
    contract_checker = contract_checker if isinstance(contract_checker, dict) else {}
    manifest_checker = probe.get("manifest_checker")
    manifest_checker = manifest_checker if isinstance(manifest_checker, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(probe.get("ok", False)),
        "status": probe.get("status"),
        "model_authority": probe.get("model_authority"),
        "selected_model_path": str(selected_model_path.expanduser()) if selected_model_path is not None else None,
        "configured_asset_roots": [str(path.expanduser()) for path in asset_roots],
        "model_request_status": probe.get("model_request_status"),
        "model_request": model_request,
        "contract_status": probe.get("contract_status"),
        "asset_preflight_status": probe.get("asset_preflight_status"),
        "asset_preflight_mesh_reference_count": probe.get("asset_preflight_mesh_reference_count"),
        "asset_preflight_present_asset_count": probe.get("asset_preflight_present_asset_count"),
        "asset_preflight_missing_asset_count": probe.get("asset_preflight_missing_asset_count"),
        "asset_preflight_unresolved_reference_count": probe.get("asset_preflight_unresolved_reference_count"),
        "observed_source_hints_status": probe.get("observed_source_hints_status"),
        "observed_source_hints_onshape_urls": probe.get("observed_source_hints_onshape_urls"),
        "observed_source_hints_export_tool_hints": probe.get("observed_source_hints_export_tool_hints"),
        "observed_source_hints_license_status": probe.get("observed_source_hints_license_status"),
        "observed_source_hints_license_path": probe.get("observed_source_hints_license_path"),
        "observed_source_hints_sha256": probe.get("observed_source_hints_sha256"),
        "observed_joint_limits_status": probe.get("observed_joint_limits_status"),
        "observed_joint_limits_complete": probe.get("observed_joint_limits_complete"),
        "observed_joint_limits_missing_joints": probe.get("observed_joint_limits_missing_joints"),
        "mesh_asset_review_status": probe.get("mesh_asset_review_status"),
        "mesh_asset_review_unique_missing_reference_count": probe.get(
            "mesh_asset_review_unique_missing_reference_count"
        ),
        "mesh_asset_review_missing_references": probe.get("mesh_asset_review_missing_references"),
        "mesh_asset_review_unique_unresolved_reference_count": probe.get(
            "mesh_asset_review_unique_unresolved_reference_count"
        ),
        "mesh_asset_review_unresolved_references": probe.get("mesh_asset_review_unresolved_references"),
        "manifest_status": probe.get("manifest_status"),
        "ready_for_model_backed_ik": probe.get("ready_for_model_backed_ik"),
        "missing_inputs": probe.get("missing_inputs") or [],
        "review_packet_status": probe.get("review_packet_status"),
        "review_packet_model_authority": probe.get("review_packet_model_authority"),
        "review_packet_item_count": probe.get("review_packet_item_count"),
        "review_packet_item_ids": probe.get("review_packet_item_ids") or [],
        "review_packet_observed_evidence_is_authority": probe.get(
            "review_packet_observed_evidence_is_authority"
        ),
        "review_packet_development_fixture_evidence_not_physical_so101_truth": probe.get(
            "review_packet_development_fixture_evidence_not_physical_so101_truth"
        ),
        "next_required_for_goal": probe.get("next_required_for_goal") or [],
        "next_required_action_ids": probe.get("next_required_action_ids") or [],
        "authority": authority,
        "provenance": provenance,
        "asset_roots": asset_root_config,
        "contract_checker": contract_checker,
        "manifest_checker": manifest_checker,
        "artifacts": {
            "summary_json": artifacts.get("summary_json")
            if isinstance(artifacts.get("summary_json"), str)
            else str(summary_path),
            "checklist_csv": artifacts.get("checklist_csv"),
            "readme_md": artifacts.get("readme_md"),
            "candidate_manifest_json": artifacts.get("candidate_manifest_json"),
            "review_packet_json": artifacts.get("review_packet_json"),
            "review_packet_csv": artifacts.get("review_packet_csv"),
            "contract_summary_json": artifacts.get("contract_summary_json"),
            "contract_checklist_csv": artifacts.get("contract_checklist_csv"),
            "manifest_check_summary_json": artifacts.get("manifest_check_summary_json"),
            "manifest_checklist_csv": artifacts.get("manifest_checklist_csv"),
        },
        "hardware_skipped": probe.get("hardware_skipped"),
        "gui_skipped": probe.get("gui_skipped"),
        "openai_skipped": probe.get("openai_skipped"),
        "limitations": probe.get("limitations"),
        "notes": [
            "The suite-indexed bundle probe is a manifest drafting aid.",
            "It never upgrades source authority or physical SO-101 authority on its own.",
            "Use the generated candidate manifest only after replacing placeholders with reviewed authority, provenance, TCP, joint-limit, mesh, and board-alignment evidence.",
        ],
    }


def so101_model_bundle_manifest_section(
    bundle: dict[str, Any] | None,
    summary_path: Path,
    config: dict[str, Any],
    forwarding: dict[str, Any],
) -> dict[str, Any]:
    bundle = bundle if isinstance(bundle, dict) else {}
    artifacts = bundle.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    manifest_request = bundle.get("manifest_request")
    manifest_request = manifest_request if isinstance(manifest_request, dict) else {}
    model_path = bundle.get("model_path")
    model_path = model_path if isinstance(model_path, dict) else {}
    model_identity = bundle.get("model_identity")
    model_identity = model_identity if isinstance(model_identity, dict) else {}
    asset_roots = bundle.get("asset_roots")
    asset_roots = asset_roots if isinstance(asset_roots, dict) else {}
    target_frame = bundle.get("target_frame")
    target_frame = target_frame if isinstance(target_frame, dict) else {}
    tcp_offset = bundle.get("tcp_offset")
    tcp_offset = tcp_offset if isinstance(tcp_offset, dict) else {}
    alignment = bundle.get("base_to_board_alignment")
    alignment = alignment if isinstance(alignment, dict) else {}
    contract = bundle.get("contract_checker")
    contract = contract if isinstance(contract, dict) else {}
    contract_artifacts = contract.get("artifacts")
    contract_artifacts = contract_artifacts if isinstance(contract_artifacts, dict) else {}
    asset_preflight = contract.get("model_asset_preflight")
    asset_preflight = asset_preflight if isinstance(asset_preflight, dict) else {}
    asset_preflight_artifacts = asset_preflight.get("artifacts")
    asset_preflight_artifacts = asset_preflight_artifacts if isinstance(asset_preflight_artifacts, dict) else {}
    authority = bundle.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    provenance = bundle.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    joint_limits = bundle.get("joint_limits")
    joint_limits = joint_limits if isinstance(joint_limits, dict) else {}
    mesh_assets = bundle.get("mesh_assets")
    mesh_assets = mesh_assets if isinstance(mesh_assets, dict) else {}
    field_checks = bundle.get("field_checks")
    field_checks = field_checks if isinstance(field_checks, list) else []
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(bundle.get("ok", False)),
        "status": bundle.get("status"),
        "config": config,
        "forwarding": forwarding,
        "ready_for_model_backed_ik": bundle.get("ready_for_model_backed_ik"),
        "model_authority": bundle.get("model_authority"),
        "physical_authority_gate_status": bundle.get("physical_authority_gate_status"),
        "physical_so101_model_authority_ready": bundle.get("physical_so101_model_authority_ready"),
        "physical_authority_blockers": bundle.get("physical_authority_blockers"),
        "hardware_free_regression_fixture_ready": bundle.get("hardware_free_regression_fixture_ready"),
        "synthetic_fixture_authority_fields": bundle.get("synthetic_fixture_authority_fields"),
        "review_packet_status": bundle.get("review_packet_status"),
        "review_packet_model_authority": bundle.get("review_packet_model_authority"),
        "review_packet_item_count": bundle.get("review_packet_item_count"),
        "review_packet_item_ids": bundle.get("review_packet_item_ids"),
        "review_packet_needs_operator_review_item_ids": bundle.get(
            "review_packet_needs_operator_review_item_ids"
        ),
        "review_packet_action_ids": bundle.get("review_packet_action_ids"),
        "review_packet_observed_evidence_is_authority": bundle.get(
            "review_packet_observed_evidence_is_authority"
        ),
        "review_packet_development_fixture_evidence_not_physical_so101_truth": bundle.get(
            "review_packet_development_fixture_evidence_not_physical_so101_truth"
        ),
        "review_requirements_status": bundle.get("review_requirements_status"),
        "review_requirements_model_authority": bundle.get(
            "review_requirements_model_authority"
        ),
        "review_requirements_requirement_count": bundle.get(
            "review_requirements_requirement_count"
        ),
        "review_requirements_requirement_ids": bundle.get(
            "review_requirements_requirement_ids"
        ),
        "review_requirements_observed_evidence_is_authority": bundle.get(
            "review_requirements_observed_evidence_is_authority"
        ),
        "review_requirements_physical_so101_truth_claimed": bundle.get(
            "review_requirements_physical_so101_truth_claimed"
        ),
        "review_requirements_development_fixture_evidence_not_physical_so101_truth": bundle.get(
            "review_requirements_development_fixture_evidence_not_physical_so101_truth"
        ),
        "review_requirements_json_path": bundle.get("review_requirements_json_path")
        or artifacts.get("review_requirements_json"),
        "review_requirements_csv_path": bundle.get("review_requirements_csv_path")
        or artifacts.get("review_requirements_csv"),
        "review_requirements": bundle.get("review_requirements"),
        "bundle_intake_status": bundle.get("bundle_intake_status"),
        "bundle_intake_model_authority": bundle.get("bundle_intake_model_authority"),
        "bundle_intake_action_count": bundle.get("bundle_intake_action_count"),
        "bundle_intake_action_ids": bundle.get("bundle_intake_action_ids"),
        "bundle_intake_observed_evidence_is_authority": bundle.get(
            "bundle_intake_observed_evidence_is_authority"
        ),
        "bundle_intake_physical_so101_truth_claimed": bundle.get(
            "bundle_intake_physical_so101_truth_claimed"
        ),
        "bundle_intake_development_fixture_evidence_not_physical_so101_truth": bundle.get(
            "bundle_intake_development_fixture_evidence_not_physical_so101_truth"
        ),
        "bundle_intake_checklist_json_path": bundle.get(
            "bundle_intake_checklist_json_path"
        )
        or artifacts.get("bundle_intake_checklist_json"),
        "bundle_intake_checklist_csv_path": bundle.get("bundle_intake_checklist_csv_path")
        or artifacts.get("bundle_intake_checklist_csv"),
        "bundle_intake_checklist": bundle.get("bundle_intake_checklist"),
        "reviewed_manifest_template_status": bundle.get(
            "reviewed_manifest_template_status"
        ),
        "reviewed_manifest_template_model_authority": bundle.get(
            "reviewed_manifest_template_model_authority"
        ),
        "reviewed_manifest_template_observed_evidence_is_authority": bundle.get(
            "reviewed_manifest_template_observed_evidence_is_authority"
        ),
        "reviewed_manifest_template_physical_so101_truth_claimed": bundle.get(
            "reviewed_manifest_template_physical_so101_truth_claimed"
        ),
        "reviewed_manifest_template_development_fixture_evidence_not_physical_so101_truth": bundle.get(
            "reviewed_manifest_template_development_fixture_evidence_not_physical_so101_truth"
        ),
        "reviewed_manifest_template_json_path": bundle.get(
            "reviewed_manifest_template_json_path"
        )
        or artifacts.get("reviewed_manifest_template_json"),
        "reviewed_manifest_template": bundle.get("reviewed_manifest_template"),
        "next_required_for_goal": bundle.get("next_required_for_goal"),
        "next_required_action_ids": bundle.get("next_required_action_ids"),
        "next_required_action_count": bundle.get("next_required_action_count"),
        "manifest_request": {
            "status": manifest_request.get("status"),
            "path": manifest_request.get("path"),
            "exists": manifest_request.get("exists"),
            "diagnostics": manifest_request.get("diagnostics"),
        },
        "model_path": {
            "status": model_path.get("status"),
            "raw": model_path.get("raw"),
            "path": model_path.get("path"),
            "exists": model_path.get("exists"),
            "is_file": model_path.get("is_file"),
            "suffix": model_path.get("suffix"),
            "sha256": model_path.get("sha256"),
            "diagnostics": model_path.get("diagnostics"),
        },
        "model_identity": {
            "status": model_identity.get("status"),
            "field": model_identity.get("field"),
            "declared_sha256": model_identity.get("declared_sha256"),
            "observed_sha256": model_identity.get("observed_sha256"),
            "matches": model_identity.get("matches"),
            "diagnostics": model_identity.get("diagnostics"),
        },
        "asset_roots": {
            "status": asset_roots.get("status"),
            "present": asset_roots.get("present"),
            "asset_roots": asset_roots.get("asset_roots"),
            "asset_root_checks": asset_roots.get("asset_root_checks"),
            "diagnostics": asset_roots.get("diagnostics"),
        },
        "authority_status": authority.get("status"),
        "authority_diagnostics": authority.get("diagnostics"),
        "authority_review_evidence_valid_fields": authority.get("review_evidence_valid_fields"),
        "authority_review_evidence_placeholder_fields": authority.get("review_evidence_placeholder_fields"),
        "authority_review_evidence_invalid_fields": authority.get("review_evidence_invalid_fields"),
        "authority_required_review_scope_ids": authority.get("required_review_scope_ids"),
        "authority_supplied_review_scope_ids": authority.get("supplied_review_scope_ids"),
        "authority_missing_review_scope_ids": authority.get("missing_review_scope_ids"),
        "authority_review_scope_ready": authority.get("review_scope_ready"),
        "provenance_status": provenance.get("status"),
        "provenance_diagnostics": provenance.get("diagnostics"),
        "provenance_synthetic_fixture_only": provenance.get("synthetic_fixture_only"),
        "provenance_fixture_only_fields": provenance.get("fixture_only_fields"),
        "provenance_blocking_diagnostics": provenance.get("blocking_diagnostics"),
        "provenance_source_field": provenance.get("source_field"),
        "provenance_export_field": provenance.get("export_field"),
        "provenance_license_field": provenance.get("license_field"),
        "provenance_source_placeholder_fields": provenance.get("source_placeholder_fields"),
        "provenance_export_placeholder_fields": provenance.get("export_placeholder_fields"),
        "provenance_license_placeholder_fields": provenance.get("license_placeholder_fields"),
        "joint_limits": {
            "status": joint_limits.get("status"),
            "field": joint_limits.get("field"),
            "expected_joints": joint_limits.get("expected_joints"),
            "missing_joints": joint_limits.get("missing_joints"),
            "invalid_joints": joint_limits.get("invalid_joints"),
            "diagnostics": joint_limits.get("diagnostics"),
        },
        "mesh_assets": {
            "status": mesh_assets.get("status"),
            "mesh_reference_count": mesh_assets.get("mesh_reference_count"),
            "present_asset_count": mesh_assets.get("present_asset_count"),
            "missing_asset_count": mesh_assets.get("missing_asset_count"),
            "unresolved_reference_count": mesh_assets.get("unresolved_reference_count"),
            "asset_preflight_status": mesh_assets.get("asset_preflight_status"),
            "diagnostics": mesh_assets.get("diagnostics"),
        },
        "target_frame": {
            "status": target_frame.get("status"),
            "value": target_frame.get("value"),
            "diagnostics": target_frame.get("diagnostics"),
        },
        "tcp_offset": {
            "status": tcp_offset.get("status"),
            "field": tcp_offset.get("field"),
            "value": tcp_offset.get("value"),
            "diagnostics": tcp_offset.get("diagnostics"),
        },
        "base_to_board_alignment": {
            "status": alignment.get("status"),
            "field": alignment.get("field"),
            "value": alignment.get("value"),
            "placeholder_field": alignment.get("placeholder_field"),
            "placeholder_value": alignment.get("placeholder_value"),
            "diagnostics": alignment.get("diagnostics"),
        },
        "contract_checker": {
            "status": contract.get("status"),
            "ok": contract.get("ok"),
            "returncode": contract.get("returncode"),
            "model_request_status": contract.get("model_request_status"),
            "robot_kinematics_status": contract.get("robot_kinematics_status"),
            "robot_kinematics_initialization_status": contract.get(
                "robot_kinematics_initialization_status"
            ),
            "artifacts": contract_artifacts,
            "child_diagnostics": contract.get("child_diagnostics"),
        },
        "model_asset_preflight": {
            "status": asset_preflight.get("status"),
            "asset_roots": asset_preflight.get("asset_roots"),
            "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
            "present_asset_count": asset_preflight.get("present_asset_count"),
            "missing_asset_count": asset_preflight.get("missing_asset_count"),
            "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
            "artifacts": asset_preflight_artifacts,
            "diagnostics": asset_preflight.get("diagnostics"),
            "limitations": asset_preflight.get("limitations"),
        },
        "missing_inputs": bundle.get("missing_inputs"),
        "field_checks": field_checks,
        "artifacts": {
            "summary_json": artifacts.get("summary_json")
            if isinstance(artifacts.get("summary_json"), str)
            else str(summary_path),
            "checklist_csv": artifacts.get("checklist_csv"),
            "review_packet_json": artifacts.get("review_packet_json"),
            "review_packet_csv": artifacts.get("review_packet_csv"),
            "review_requirements_json": artifacts.get("review_requirements_json"),
            "review_requirements_csv": artifacts.get("review_requirements_csv"),
            "bundle_intake_checklist_json": artifacts.get(
                "bundle_intake_checklist_json"
            ),
            "bundle_intake_checklist_csv": artifacts.get("bundle_intake_checklist_csv"),
            "reviewed_manifest_template_json": artifacts.get(
                "reviewed_manifest_template_json"
            ),
            "readme_md": artifacts.get("readme_md"),
        },
        "hardware_skipped": bundle.get("hardware_skipped"),
        "gui_skipped": bundle.get("gui_skipped"),
        "openai_skipped": bundle.get("openai_skipped"),
        "limitations": bundle.get("limitations"),
    }


def normalized_gate_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def normalized_sha256(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:").strip()
    if len(text) != 64:
        return None
    if any(char not in "0123456789abcdef" for char in text):
        return None
    return text


def normalized_path_is_same_or_within(path: str | None, root: str | None) -> bool:
    if not path or not root:
        return False
    try:
        Path(path).relative_to(Path(root))
    except ValueError:
        return False
    return True


def so101_source_bundle_consistency_section(
    source_inventory: dict[str, Any],
    bundle_manifest: dict[str, Any],
    *,
    source_authority_ready: bool,
    physical_authority_ready: bool,
) -> dict[str, Any]:
    source_configuration = source_inventory.get("source_configuration")
    source_configuration = (
        source_configuration if isinstance(source_configuration, dict) else {}
    )
    bundle_model_path = normalized_gate_path(
        (bundle_manifest.get("model_path") or {}).get("path")
        if isinstance(bundle_manifest.get("model_path"), dict)
        else None
    )
    source_authoritative_paths = [
        path
        for path in (
            normalized_gate_path(value)
            for value in source_configuration.get("authoritative_model_paths") or []
        )
        if path
    ]
    source_authoritative_roots = [
        path
        for path in (
            normalized_gate_path(value)
            for value in source_configuration.get("authoritative_model_roots") or []
        )
        if path
    ]
    selected_authoritative_candidate_path = normalized_gate_path(
        source_inventory.get("selected_authoritative_candidate_path")
    )
    selected_authoritative_candidate_sha256 = normalized_sha256(
        source_inventory.get("selected_authoritative_candidate_sha256")
    )
    selected_declared_by_authoritative_path = bool(
        selected_authoritative_candidate_path
        and selected_authoritative_candidate_path in source_authoritative_paths
    )
    selected_within_authoritative_root = bool(
        selected_authoritative_candidate_path
        and any(
            normalized_path_is_same_or_within(
                selected_authoritative_candidate_path,
                root,
            )
            for root in source_authoritative_roots
        )
    )
    source_configuration_declares_authority = bool(
        source_authoritative_paths or source_authoritative_roots
    )
    selected_covered_by_source_configuration = (
        selected_declared_by_authoritative_path or selected_within_authoritative_root
    )
    bundle_model_identity = bundle_manifest.get("model_identity")
    bundle_model_identity = (
        bundle_model_identity if isinstance(bundle_model_identity, dict) else {}
    )
    bundle_model_declared_sha256 = normalized_sha256(
        bundle_model_identity.get("declared_sha256")
    )
    bundle_model_observed_sha256 = normalized_sha256(
        bundle_model_identity.get("observed_sha256")
    )
    bundle_model_sha256 = bundle_model_declared_sha256
    bundle_observed_digest_missing = bool(
        bundle_model_declared_sha256 and not bundle_model_observed_sha256
    )
    bundle_observed_digest_conflicts_with_declared = bool(
        bundle_model_declared_sha256
        and bundle_model_observed_sha256
        and bundle_model_declared_sha256 != bundle_model_observed_sha256
    )

    selected_path_matches_bundle = bool(
        bundle_model_path
        and selected_authoritative_candidate_path
        and bundle_model_path == selected_authoritative_candidate_path
    )
    selected_digest_matches_bundle = bool(
        selected_authoritative_candidate_sha256
        and bundle_model_declared_sha256
        and selected_authoritative_candidate_sha256 == bundle_model_declared_sha256
    )

    prerequisites_ready = source_authority_ready and physical_authority_ready
    if not prerequisites_ready:
        status = "not_checked_prerequisites_not_ready"
        ready = False
        blocker = None
    elif not bundle_model_path:
        status = "bundle_model_path_missing"
        ready = False
        blocker = "select_reviewed_so101_model_path"
    elif not selected_authoritative_candidate_path:
        status = "source_authoritative_model_path_missing"
        ready = False
        blocker = "select_reviewed_authoritative_so101_source_model_path"
    elif not source_configuration_declares_authority:
        status = "source_authoritative_model_selection_unconfigured"
        ready = False
        blocker = "declare_reviewed_authoritative_so101_source_path_or_root"
    elif not selected_covered_by_source_configuration:
        status = "source_authoritative_model_selection_mismatch"
        ready = False
        blocker = "align_selected_so101_source_model_with_authoritative_declaration"
    elif not selected_path_matches_bundle:
        status = "source_bundle_model_path_mismatch"
        ready = False
        blocker = "align_source_inventory_with_bundle_manifest_model_path"
    elif not selected_authoritative_candidate_sha256 or not bundle_model_declared_sha256:
        status = "source_bundle_model_digest_missing"
        ready = False
        blocker = "record_reviewed_so101_model_file_sha256"
    elif bundle_observed_digest_missing:
        status = "bundle_model_observed_digest_missing"
        ready = False
        blocker = "verify_reviewed_so101_bundle_model_file_sha256"
    elif bundle_observed_digest_conflicts_with_declared:
        status = "bundle_model_observed_digest_mismatch"
        ready = False
        blocker = "inspect_reviewed_so101_bundle_model_file_sha256"
    elif not selected_digest_matches_bundle:
        status = "source_bundle_model_digest_mismatch"
        ready = False
        blocker = "align_source_inventory_with_bundle_manifest_model_digest"
    elif selected_path_matches_bundle:
        status = "source_bundle_model_path_and_digest_consistent"
        ready = True
        blocker = None
    matched_by = (
        "selected_authoritative_candidate_path_and_sha256"
        if ready and selected_path_matches_bundle and selected_digest_matches_bundle
        else None
    )

    return {
        "ready": ready,
        "status": status,
        "checked": prerequisites_ready,
        "prerequisites_ready": prerequisites_ready,
        "bundle_model_path": bundle_model_path,
        "source_authoritative_model_paths": source_authoritative_paths,
        "source_authoritative_model_roots": source_authoritative_roots,
        "selected_authoritative_candidate_path": selected_authoritative_candidate_path,
        "selected_authoritative_candidate_declared_by_authoritative_path": (
            selected_declared_by_authoritative_path
        ),
        "selected_authoritative_candidate_within_authoritative_root": (
            selected_within_authoritative_root
        ),
        "selected_authoritative_candidate_covered_by_source_configuration": (
            selected_covered_by_source_configuration
        ),
        "selected_authoritative_candidate_path_matches_bundle": selected_path_matches_bundle,
        "selected_authoritative_candidate_sha256": selected_authoritative_candidate_sha256,
        "bundle_model_declared_sha256": bundle_model_declared_sha256,
        "bundle_model_observed_sha256": bundle_model_observed_sha256,
        "bundle_model_sha256": bundle_model_sha256,
        "bundle_model_observed_sha256_missing": bundle_observed_digest_missing,
        "bundle_model_observed_sha256_matches_declared": bool(
            bundle_model_declared_sha256
            and bundle_model_observed_sha256
            and bundle_model_declared_sha256 == bundle_model_observed_sha256
        ),
        "selected_authoritative_candidate_sha256_matches_bundle": selected_digest_matches_bundle,
        "matched_by": matched_by,
        "blocker": blocker,
        "notes": [
            "This check prevents source authority and bundle authority from closing on different model paths or digests.",
            "It is evaluated only after source authority and physical bundle authority are otherwise ready.",
            "A source-authority-ready inventory must still identify a selected model path covered by the authoritative path/root declarations in that same child summary.",
            "The bundle manifest declared digest must match the selected authoritative model candidate digest.",
            "The observed bundle model digest is diagnostic evidence and does not substitute for a reviewed manifest declaration, but it must not be missing or conflict with the declared digest when the bundle claims physical authority.",
        ],
    }


def so101_reviewed_mujoco_motion_bundle_consistency_section(
    bundle_manifest: dict[str, Any],
    reviewed_mujoco_bundle: dict[str, Any],
    *,
    physical_authority_ready: bool,
    source_bundle_consistency_ready: bool,
    physical_reviewed_motion_child_ready: bool,
) -> dict[str, Any]:
    bundle_model_path = normalized_gate_path(
        (bundle_manifest.get("model_path") or {}).get("path")
        if isinstance(bundle_manifest.get("model_path"), dict)
        else None
    )
    motion_model_path = normalized_gate_path(
        (reviewed_mujoco_bundle.get("model_path") or {}).get("path")
        if isinstance(reviewed_mujoco_bundle.get("model_path"), dict)
        else None
    )
    bundle_model_identity = bundle_manifest.get("model_identity")
    bundle_model_identity = (
        bundle_model_identity if isinstance(bundle_model_identity, dict) else {}
    )
    motion_model_identity = reviewed_mujoco_bundle.get("model_identity")
    motion_model_identity = (
        motion_model_identity if isinstance(motion_model_identity, dict) else {}
    )
    bundle_model_declared_sha256 = normalized_sha256(
        bundle_model_identity.get("declared_sha256")
    )
    motion_model_declared_sha256 = normalized_sha256(
        motion_model_identity.get("declared_sha256")
    )
    motion_model_observed_sha256 = normalized_sha256(
        motion_model_identity.get("observed_sha256")
    )
    prerequisites_ready = (
        physical_authority_ready
        and source_bundle_consistency_ready
        and physical_reviewed_motion_child_ready
    )
    model_path_matches = bool(
        bundle_model_path and motion_model_path and bundle_model_path == motion_model_path
    )
    model_digest_matches = bool(
        bundle_model_declared_sha256
        and motion_model_declared_sha256
        and bundle_model_declared_sha256 == motion_model_declared_sha256
    )
    motion_observed_digest_missing = bool(
        motion_model_declared_sha256 and not motion_model_observed_sha256
    )
    motion_observed_digest_conflicts_with_declared = bool(
        motion_model_declared_sha256
        and motion_model_observed_sha256
        and motion_model_declared_sha256 != motion_model_observed_sha256
    )
    if not prerequisites_ready:
        status = "not_checked_prerequisites_not_ready"
        ready = False
        blocker = None
    elif not motion_model_path:
        status = "reviewed_mujoco_motion_model_path_missing"
        ready = False
        blocker = "rerun_reviewed_mujoco_motion_with_bundle_model_path"
    elif not bundle_model_path:
        status = "bundle_model_path_missing"
        ready = False
        blocker = "select_reviewed_so101_model_path"
    elif not model_path_matches:
        status = "reviewed_mujoco_motion_model_path_mismatch"
        ready = False
        blocker = "align_reviewed_mujoco_motion_with_bundle_model_path"
    elif not motion_model_declared_sha256 or not bundle_model_declared_sha256:
        status = "reviewed_mujoco_motion_model_digest_missing"
        ready = False
        blocker = "record_reviewed_mujoco_motion_model_sha256"
    elif motion_observed_digest_missing:
        status = "reviewed_mujoco_motion_model_observed_digest_missing"
        ready = False
        blocker = "verify_reviewed_mujoco_motion_model_file_sha256"
    elif motion_observed_digest_conflicts_with_declared:
        status = "reviewed_mujoco_motion_model_observed_digest_mismatch"
        ready = False
        blocker = "inspect_reviewed_mujoco_motion_model_file_sha256"
    elif not model_digest_matches:
        status = "reviewed_mujoco_motion_model_digest_mismatch"
        ready = False
        blocker = "align_reviewed_mujoco_motion_with_bundle_model_digest"
    else:
        status = "reviewed_mujoco_motion_matches_bundle_model_identity"
        ready = True
        blocker = None

    return {
        "ready": ready,
        "status": status,
        "checked": prerequisites_ready,
        "prerequisites_ready": prerequisites_ready,
        "bundle_model_path": bundle_model_path,
        "reviewed_mujoco_motion_model_path": motion_model_path,
        "reviewed_mujoco_motion_model_path_matches_bundle": model_path_matches,
        "bundle_model_declared_sha256": bundle_model_declared_sha256,
        "reviewed_mujoco_motion_model_declared_sha256": motion_model_declared_sha256,
        "reviewed_mujoco_motion_model_observed_sha256": motion_model_observed_sha256,
        "reviewed_mujoco_motion_model_sha256_matches_bundle": model_digest_matches,
        "reviewed_mujoco_motion_model_observed_sha256_missing": (
            motion_observed_digest_missing
        ),
        "reviewed_mujoco_motion_model_observed_sha256_matches_declared": bool(
            motion_model_declared_sha256
            and motion_model_observed_sha256
            and motion_model_declared_sha256 == motion_model_observed_sha256
        ),
        "blocker": blocker,
        "notes": [
            "This check prevents physical-reviewed MuJoCo motion evidence from closing authority for a different model path or digest than the reviewed bundle manifest.",
            "It is evaluated only after source-to-bundle identity is ready and the reviewed-MuJoCo child reports physical motion ready.",
            "The reviewed-MuJoCo motion summary must also carry an observed model-file digest that matches its reviewed declared digest.",
        ],
    }


def so101_reviewed_model_authority_gate_section(
    source_inventory: dict[str, Any],
    bundle_manifest: dict[str, Any],
    reviewed_mujoco_bundle: dict[str, Any],
) -> dict[str, Any]:
    source_authority_status_ready = (
        source_inventory.get("source_authority_gate_status") == "source_authority_ready"
    )
    source_authority_blockers = unique_string_values(
        source_inventory.get("source_authority_blockers") or []
    )
    source_next_required = source_inventory.get("next_required_action_ids")
    source_next_required_action_ids = unique_string_values(
        source_next_required if isinstance(source_next_required, list) else []
    )
    source_next_required_for_goal = source_inventory.get("next_required_for_goal")
    source_next_required_for_goal_action_ids = unique_string_values(
        [
            action.get("action_id")
            for action in source_next_required_for_goal
            if isinstance(action, dict)
        ]
        if isinstance(source_next_required_for_goal, list)
        else []
    )
    source_authority_pending_action_ids = unique_string_values(
        [
            *source_next_required_action_ids,
            *source_next_required_for_goal_action_ids,
        ]
    )
    source_authority_contradictory_ready_state = bool(
        source_authority_status_ready
        and (source_authority_blockers or source_authority_pending_action_ids)
    )
    source_authority_ready = (
        source_authority_status_ready
        and not source_authority_blockers
        and not source_authority_pending_action_ids
    )
    physical_bundle_authority_status_ready = (
        bundle_manifest.get("physical_so101_model_authority_ready") is True
    )
    physical_bundle_authority_blockers = unique_string_values(
        bundle_manifest.get("physical_authority_blockers") or []
    )
    bundle_next_required = bundle_manifest.get("next_required_action_ids")
    physical_bundle_next_required_action_ids = unique_string_values(
        bundle_next_required if isinstance(bundle_next_required, list) else []
    )
    bundle_next_required_for_goal = bundle_manifest.get("next_required_for_goal")
    physical_bundle_next_required_for_goal_action_ids = unique_string_values(
        [
            action.get("action_id")
            for action in bundle_next_required_for_goal
            if isinstance(action, dict)
        ]
        if isinstance(bundle_next_required_for_goal, list)
        else []
    )
    physical_bundle_authority_pending_action_ids = unique_string_values(
        [
            *physical_bundle_next_required_action_ids,
            *physical_bundle_next_required_for_goal_action_ids,
        ]
    )
    physical_bundle_authority_contradictory_ready_state = bool(
        physical_bundle_authority_status_ready
        and (
            physical_bundle_authority_blockers
            or physical_bundle_authority_pending_action_ids
        )
    )
    physical_authority_ready = (
        physical_bundle_authority_status_ready
        and not physical_bundle_authority_blockers
        and not physical_bundle_authority_pending_action_ids
    )
    bundle_fixture_ready = bundle_manifest.get("hardware_free_regression_fixture_ready") is True
    physical_reviewed_motion_reported = (
        reviewed_mujoco_bundle.get("physical_reviewed_model_motion_checked") is True
    )
    fixture_motion_checked = reviewed_mujoco_bundle.get("hardware_free_fixture_motion_checked") is True
    development_fixture_evidence_present = bundle_fixture_ready or fixture_motion_checked
    reviewed_mujoco_bundle_status = reviewed_mujoco_bundle.get("status")
    reviewed_mujoco_motion_authority_status = reviewed_mujoco_bundle.get(
        "motion_authority_status"
    )
    reviewed_mujoco_motion_missing_inputs = unique_string_values(
        reviewed_mujoco_bundle.get("missing_inputs") or []
    )
    reviewed_mujoco_next_required = reviewed_mujoco_bundle.get("next_required_for_goal")
    reviewed_mujoco_next_required_action_ids = unique_string_values(
        [
            action.get("action_id") if isinstance(action, dict) else action
            for action in reviewed_mujoco_next_required
        ]
        if isinstance(reviewed_mujoco_next_required, list)
        else []
    )
    physical_reviewed_motion_status_ready = (
        reviewed_mujoco_bundle_status == "reviewed_mujoco_bundle_motion_checked"
        and reviewed_mujoco_motion_authority_status
        == "physical_reviewed_model_motion_checked"
    )
    reviewed_mujoco_motion_contradictory_ready_state = bool(
        physical_reviewed_motion_reported
        and physical_reviewed_motion_status_ready
        and (
            reviewed_mujoco_motion_missing_inputs
            or reviewed_mujoco_next_required_action_ids
        )
    )
    physical_reviewed_motion_child_ready = (
        physical_reviewed_motion_reported and physical_reviewed_motion_status_ready
        and not reviewed_mujoco_motion_missing_inputs
        and not reviewed_mujoco_next_required_action_ids
    )
    source_bundle_consistency = so101_source_bundle_consistency_section(
        source_inventory,
        bundle_manifest,
        source_authority_ready=source_authority_ready,
        physical_authority_ready=physical_authority_ready,
    )
    source_bundle_consistency_ready = source_bundle_consistency.get("ready") is True
    reviewed_mujoco_motion_bundle_consistency = (
        so101_reviewed_mujoco_motion_bundle_consistency_section(
            bundle_manifest,
            reviewed_mujoco_bundle,
            physical_authority_ready=physical_authority_ready,
            source_bundle_consistency_ready=source_bundle_consistency_ready,
            physical_reviewed_motion_child_ready=physical_reviewed_motion_child_ready,
        )
    )
    reviewed_mujoco_motion_bundle_consistency_ready = (
        reviewed_mujoco_motion_bundle_consistency.get("ready") is True
    )
    physical_reviewed_motion_ready = (
        physical_reviewed_motion_child_ready
        and reviewed_mujoco_motion_bundle_consistency_ready
    )
    ready = (
        source_authority_ready
        and physical_authority_ready
        and source_bundle_consistency_ready
        and physical_reviewed_motion_ready
        and not development_fixture_evidence_present
    )

    blockers = unique_string_values(
        [
            *(source_inventory.get("source_authority_blockers") or []),
            *(
                ["resolve_contradictory_source_authority_gate_state"]
                if source_authority_contradictory_ready_state
                else []
            ),
            *physical_bundle_authority_blockers,
            *(
                ["resolve_contradictory_physical_bundle_authority_gate_state"]
                if physical_bundle_authority_contradictory_ready_state
                else []
            ),
            *(
                []
                if source_bundle_consistency.get("blocker") is None
                else [source_bundle_consistency["blocker"]]
            ),
            *(
                []
                if reviewed_mujoco_motion_bundle_consistency.get("blocker") is None
                else [reviewed_mujoco_motion_bundle_consistency["blocker"]]
            ),
            *(
                ["resolve_contradictory_reviewed_mujoco_motion_gate_state"]
                if reviewed_mujoco_motion_contradictory_ready_state
                else []
            ),
            *(
                []
                if physical_reviewed_motion_child_ready
                else [
                    "load_reviewed_model_in_mujoco",
                    "prove_physical_reviewed_model_motion",
                ]
            ),
            *(
                ["replace_development_fixture_evidence_with_reviewed_physical_so101_authority"]
                if development_fixture_evidence_present
                else []
            ),
        ]
    )
    consistency_status = source_bundle_consistency.get("status")
    if consistency_status == "source_bundle_model_path_mismatch":
        consistency_actions = [
            {
                "action_id": "align_source_inventory_with_bundle_manifest_model_path",
                "gate": "reviewed_model_authority",
                "title": "Align source inventory and bundle model paths",
                "detail": (
                    "Use the same reviewed SO-101 model path in the source inventory "
                    "and the reviewed bundle manifest before closing model authority."
                ),
            }
        ]
    elif consistency_status == "source_authoritative_model_path_missing":
        consistency_actions = [
            {
                "action_id": "select_reviewed_authoritative_so101_source_model_path",
                "gate": "reviewed_model_authority",
                "title": "Select reviewed authoritative SO-101 source model path",
                "detail": (
                    "Record selected_authoritative_candidate_path in the source inventory "
                    "before comparing source authority with the reviewed bundle manifest."
                ),
            }
        ]
    elif consistency_status == "source_authoritative_model_selection_unconfigured":
        consistency_actions = [
            {
                "action_id": "declare_reviewed_authoritative_so101_source_path_or_root",
                "gate": "reviewed_model_authority",
                "title": "Declare reviewed authoritative SO-101 source path or root",
                "detail": (
                    "Rerun the source inventory with the reviewed authoritative model "
                    "path or root so the selected source model is covered by explicit "
                    "authority declarations."
                ),
            }
        ]
    elif consistency_status == "source_authoritative_model_selection_mismatch":
        consistency_actions = [
            {
                "action_id": "align_selected_so101_source_model_with_authoritative_declaration",
                "gate": "reviewed_model_authority",
                "title": "Align selected SO-101 source model with authority declaration",
                "detail": (
                    "Resolve the source inventory so selected_authoritative_candidate_path "
                    "matches an authoritative model path or is inside an authoritative "
                    "model root before comparing it with the bundle manifest."
                ),
            }
        ]
    elif consistency_status == "source_bundle_model_digest_mismatch":
        consistency_actions = [
            {
                "action_id": "align_source_inventory_with_bundle_manifest_model_digest",
                "gate": "reviewed_model_authority",
                "title": "Align source inventory and bundle model digests",
                "detail": (
                    "Use the same reviewed SO-101 model file digest in the source inventory "
                    "and the reviewed bundle manifest before closing model authority."
                ),
            }
        ]
    elif consistency_status == "bundle_model_observed_digest_missing":
        consistency_actions = [
            {
                "action_id": "verify_reviewed_so101_bundle_model_file_sha256",
                "gate": "reviewed_model_authority",
                "title": "Verify reviewed SO-101 bundle model file digest",
                "detail": (
                    "Re-run the reviewed bundle manifest check against a readable "
                    "model file so the observed SHA-256 can be compared with the "
                    "reviewed manifest declaration."
                ),
            }
        ]
    elif consistency_status == "bundle_model_observed_digest_mismatch":
        consistency_actions = [
            {
                "action_id": "inspect_reviewed_so101_bundle_model_file_sha256",
                "gate": "reviewed_model_authority",
                "title": "Inspect reviewed SO-101 bundle model file digest",
                "detail": (
                    "Resolve the mismatch between the bundle manifest's reviewed "
                    "model SHA-256 declaration and the observed model file digest "
                    "before closing SO-101 model authority."
                ),
            }
        ]
    elif consistency_status == "source_bundle_model_digest_missing":
        consistency_actions = [
            {
                "action_id": "record_reviewed_so101_model_file_sha256",
                "gate": "reviewed_model_authority",
                "title": "Record reviewed SO-101 model digest",
                "detail": (
                    "Record the selected authoritative source SHA-256 and matching bundle "
                    "model_sha256 before checking source-to-bundle identity consistency."
                ),
            }
        ]
    elif consistency_status == "bundle_model_path_missing":
        consistency_actions = [
            {
                "action_id": "select_reviewed_so101_model_path",
                "gate": "reviewed_model_authority",
                "title": "Select reviewed SO-101 bundle model path",
                "detail": (
                    "Record the reviewed SO-101 model path in the bundle manifest "
                    "before checking source-to-bundle model identity consistency."
                ),
            }
        ]
    else:
        consistency_actions = []
    motion_consistency_status = reviewed_mujoco_motion_bundle_consistency.get("status")
    if motion_consistency_status == "reviewed_mujoco_motion_model_path_missing":
        motion_consistency_actions = [
            {
                "action_id": "rerun_reviewed_mujoco_motion_with_bundle_model_path",
                "gate": "mujoco_scene_validity",
                "title": "Rerun reviewed MuJoCo motion with bundle model path",
                "detail": (
                    "Regenerate the reviewed-MuJoCo bundle evidence from the reviewed "
                    "bundle manifest so the motion summary carries the same model path."
                ),
            }
        ]
    elif motion_consistency_status == "reviewed_mujoco_motion_model_path_mismatch":
        motion_consistency_actions = [
            {
                "action_id": "align_reviewed_mujoco_motion_with_bundle_model_path",
                "gate": "mujoco_scene_validity",
                "title": "Align reviewed MuJoCo motion model path",
                "detail": (
                    "Rerun or replace the reviewed-MuJoCo motion evidence so its model "
                    "path matches the reviewed bundle manifest model path."
                ),
            }
        ]
    elif motion_consistency_status == "reviewed_mujoco_motion_model_digest_missing":
        motion_consistency_actions = [
            {
                "action_id": "record_reviewed_mujoco_motion_model_sha256",
                "gate": "mujoco_scene_validity",
                "title": "Record reviewed MuJoCo motion model digest",
                "detail": (
                    "Ensure the reviewed-MuJoCo motion summary carries the reviewed "
                    "model SHA-256 from the bundle manifest before closing authority."
                ),
            }
        ]
    elif (
        motion_consistency_status
        == "reviewed_mujoco_motion_model_observed_digest_missing"
    ):
        motion_consistency_actions = [
            {
                "action_id": "verify_reviewed_mujoco_motion_model_file_sha256",
                "gate": "mujoco_scene_validity",
                "title": "Verify reviewed MuJoCo motion model file digest",
                "detail": (
                    "Rerun the reviewed-MuJoCo motion check against a readable "
                    "model file so the observed SHA-256 can be compared with the "
                    "reviewed motion declaration."
                ),
            }
        ]
    elif (
        motion_consistency_status
        == "reviewed_mujoco_motion_model_observed_digest_mismatch"
    ):
        motion_consistency_actions = [
            {
                "action_id": "inspect_reviewed_mujoco_motion_model_file_sha256",
                "gate": "mujoco_scene_validity",
                "title": "Inspect reviewed MuJoCo motion model file digest",
                "detail": (
                    "Resolve the mismatch between the reviewed-MuJoCo motion "
                    "model SHA-256 declaration and the observed model file digest "
                    "before closing SO-101 model authority."
                ),
            }
        ]
    elif motion_consistency_status == "reviewed_mujoco_motion_model_digest_mismatch":
        motion_consistency_actions = [
            {
                "action_id": "align_reviewed_mujoco_motion_with_bundle_model_digest",
                "gate": "mujoco_scene_validity",
                "title": "Align reviewed MuJoCo motion model digest",
                "detail": (
                    "Rerun or replace the reviewed-MuJoCo motion evidence so its model "
                    "digest matches the reviewed bundle manifest declaration."
                ),
            }
        ]
    else:
        motion_consistency_actions = []
    source_authority_contradiction_actions = (
        [
            {
                "action_id": "resolve_contradictory_source_authority_gate_state",
                "gate": "reviewed_model_authority",
                "title": "Resolve contradictory source-authority state",
                "detail": (
                    "Rerun or inspect the SO-101 model-source inventory because it "
                    "reports source_authority_ready while still carrying source "
                    "blockers or pending source-authority actions."
                ),
            }
        ]
        if source_authority_contradictory_ready_state
        else []
    )
    physical_bundle_authority_contradiction_actions = (
        [
            {
                "action_id": "resolve_contradictory_physical_bundle_authority_gate_state",
                "gate": "reviewed_model_authority",
                "title": "Resolve contradictory physical-bundle authority state",
                "detail": (
                    "Rerun or inspect the SO-101 model-bundle manifest because it "
                    "reports physical_so101_model_authority_ready while still "
                    "carrying physical-authority blockers or pending bundle actions."
                ),
            }
        ]
        if physical_bundle_authority_contradictory_ready_state
        else []
    )
    reviewed_mujoco_motion_contradiction_actions = (
        [
            {
                "action_id": "resolve_contradictory_reviewed_mujoco_motion_gate_state",
                "gate": "mujoco_scene_validity",
                "title": "Resolve contradictory reviewed MuJoCo motion state",
                "detail": (
                    "Rerun or inspect the reviewed MuJoCo bundle summary because it "
                    "reports physical reviewed motion while still carrying missing "
                    "inputs or pending reviewed-motion actions."
                ),
            }
        ]
        if reviewed_mujoco_motion_contradictory_ready_state
        else []
    )
    motion_actions = (
        [
            {
                "action_id": "load_reviewed_model_in_mujoco",
                "gate": "mujoco_scene_validity",
                "title": "Load the reviewed SO-101 model in MuJoCo",
                "detail": (
                    "Load the reviewed bundle in MuJoCo with the declared mesh roots, "
                    "joint map, target frame, TCP offset, and base-to-board alignment."
                ),
            },
            {
                "action_id": "prove_physical_reviewed_model_motion",
                "gate": "mujoco_scene_validity",
                "title": "Prove reviewed SO-101 joint motion",
                "detail": (
                    "Move every reviewed SO-101 joint in MuJoCo without fallback behavior "
                    "and record physical-reviewed motion evidence."
                ),
            },
        ]
        if not physical_reviewed_motion_reported
        or not physical_reviewed_motion_status_ready
        else []
    )
    fixture_boundary_actions = (
        [
            {
                "action_id": (
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ),
                "gate": "reviewed_model_authority",
                "title": "Replace fixture-only evidence before closing authority",
                "detail": (
                    "Resolve any hardware-free fixture readiness or fixture-motion flags "
                    "before treating the aggregate SO-101 model authority gate as reviewed "
                    "physical truth."
                ),
            }
        ]
        if development_fixture_evidence_present
        else []
    )
    next_required_for_goal = prioritized_gate_actions(
        source_inventory.get("next_required_for_goal"),
        source_authority_contradiction_actions,
        bundle_manifest.get("next_required_for_goal"),
        physical_bundle_authority_contradiction_actions,
        reviewed_mujoco_bundle.get("next_required_for_goal"),
        reviewed_mujoco_motion_contradiction_actions,
        consistency_actions,
        motion_consistency_actions,
        fixture_boundary_actions,
        motion_actions,
    )
    return {
        "status": "reviewed_model_authority_ready"
        if ready
        else "reviewed_model_authority_blocked",
        "ready": ready,
        "reviewed_model_authority_ready": ready,
        "source_authority_ready": source_authority_ready,
        "source_authority_status_ready": source_authority_status_ready,
        "source_authority_gate_status": source_inventory.get("source_authority_gate_status"),
        "source_authority_blockers": source_authority_blockers,
        "source_authority_pending_action_ids": source_authority_pending_action_ids,
        "source_authority_contradictory_ready_state": (
            source_authority_contradictory_ready_state
        ),
        "physical_so101_model_authority_ready": physical_authority_ready,
        "physical_bundle_authority_status_ready": physical_bundle_authority_status_ready,
        "physical_bundle_authority_blockers": physical_bundle_authority_blockers,
        "physical_bundle_authority_pending_action_ids": (
            physical_bundle_authority_pending_action_ids
        ),
        "physical_bundle_authority_contradictory_ready_state": (
            physical_bundle_authority_contradictory_ready_state
        ),
        "hardware_free_regression_fixture_ready": bundle_fixture_ready,
        "physical_authority_gate_status": bundle_manifest.get("physical_authority_gate_status"),
        "source_bundle_consistency_ready": source_bundle_consistency_ready,
        "source_bundle_consistency_status": source_bundle_consistency.get("status"),
        "source_bundle_consistency": source_bundle_consistency,
        "reviewed_mujoco_motion_bundle_consistency_ready": (
            reviewed_mujoco_motion_bundle_consistency_ready
        ),
        "reviewed_mujoco_motion_bundle_consistency_status": (
            reviewed_mujoco_motion_bundle_consistency.get("status")
        ),
        "reviewed_mujoco_motion_bundle_consistency": (
            reviewed_mujoco_motion_bundle_consistency
        ),
        "physical_reviewed_model_motion_checked": physical_reviewed_motion_ready,
        "physical_reviewed_model_motion_reported": physical_reviewed_motion_reported,
        "physical_reviewed_model_motion_status_ready": physical_reviewed_motion_status_ready,
        "physical_reviewed_model_motion_child_ready": physical_reviewed_motion_child_ready,
        "reviewed_mujoco_motion_missing_inputs": reviewed_mujoco_motion_missing_inputs,
        "reviewed_mujoco_motion_pending_action_ids": reviewed_mujoco_next_required_action_ids,
        "reviewed_mujoco_motion_contradictory_ready_state": (
            reviewed_mujoco_motion_contradictory_ready_state
        ),
        "hardware_free_fixture_motion_checked": fixture_motion_checked,
        "development_fixture_evidence_present": development_fixture_evidence_present,
        "reviewed_mujoco_bundle_status": reviewed_mujoco_bundle_status,
        "reviewed_mujoco_motion_authority_status": reviewed_mujoco_motion_authority_status,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": [
            action["action_id"] for action in next_required_for_goal
        ],
        "next_required_action_count": len(next_required_for_goal),
        "source_authority_next_required_action_ids": source_next_required_action_ids,
        "physical_bundle_next_required_action_ids": physical_bundle_next_required_action_ids,
        "reviewed_mujoco_next_required_action_ids": reviewed_mujoco_next_required_action_ids,
        "source_inventory_summary_path": source_inventory.get("summary_path"),
        "bundle_manifest_summary_path": bundle_manifest.get("summary_path"),
        "reviewed_mujoco_bundle_summary_path": reviewed_mujoco_bundle.get("summary_path"),
        "development_fixture_evidence_not_physical_so101_truth": (
            not ready
            or development_fixture_evidence_present
        ),
        "notes": [
            "This top-level gate is a summary over the source inventory, bundle manifest, and reviewed MuJoCo bundle artifacts.",
            "It is ready only when source authority, physical bundle authority, source-to-bundle model path/digest consistency, and physical-reviewed MuJoCo motion are all true.",
            "Any hardware-free fixture readiness or fixture-motion evidence fails the aggregate gate closed, even if another child summary also reports a physical-ready flag.",
            "Physical-reviewed MuJoCo motion must have a matching child status and motion-authority status, not only a lone boolean flag.",
            "Physical-reviewed MuJoCo motion must also carry the same reviewed model path and digest as the reviewed bundle manifest.",
            "The source-authority model path/digest and bundle manifest model path/digest must be consistent before authority can close.",
            "Development fixture evidence remains useful automation coverage but does not close reviewed physical SO-101 authority.",
        ],
    }


def so101_reviewed_model_authority_blocker_packet(gate: dict[str, Any]) -> dict[str, Any]:
    source_bundle_consistency = gate.get("source_bundle_consistency")
    source_bundle_consistency = (
        source_bundle_consistency if isinstance(source_bundle_consistency, dict) else {}
    )
    source_bundle_consistency_ready = gate.get("source_bundle_consistency_ready") is True
    consistency_status = source_bundle_consistency.get("status")
    if consistency_status == "bundle_model_path_missing":
        source_bundle_consistency_next_action_id = "select_reviewed_so101_model_path"
    elif consistency_status == "source_authoritative_model_path_missing":
        source_bundle_consistency_next_action_id = (
            "select_reviewed_authoritative_so101_source_model_path"
        )
    elif consistency_status == "source_authoritative_model_selection_unconfigured":
        source_bundle_consistency_next_action_id = (
            "declare_reviewed_authoritative_so101_source_path_or_root"
        )
    elif consistency_status == "source_authoritative_model_selection_mismatch":
        source_bundle_consistency_next_action_id = (
            "align_selected_so101_source_model_with_authoritative_declaration"
        )
    elif consistency_status == "source_bundle_model_digest_missing":
        source_bundle_consistency_next_action_id = "record_reviewed_so101_model_file_sha256"
    elif consistency_status == "bundle_model_observed_digest_missing":
        source_bundle_consistency_next_action_id = (
            "verify_reviewed_so101_bundle_model_file_sha256"
        )
    elif consistency_status == "bundle_model_observed_digest_mismatch":
        source_bundle_consistency_next_action_id = (
            "inspect_reviewed_so101_bundle_model_file_sha256"
        )
    elif consistency_status == "source_bundle_model_digest_mismatch":
        source_bundle_consistency_next_action_id = (
            "align_source_inventory_with_bundle_manifest_model_digest"
        )
    else:
        source_bundle_consistency_next_action_id = (
            "align_source_inventory_with_bundle_manifest_model_path"
        )
    motion_bundle_consistency = gate.get("reviewed_mujoco_motion_bundle_consistency")
    motion_bundle_consistency = (
        motion_bundle_consistency if isinstance(motion_bundle_consistency, dict) else {}
    )
    motion_bundle_consistency_status = motion_bundle_consistency.get("status")
    if motion_bundle_consistency_status == "reviewed_mujoco_motion_model_path_missing":
        physical_motion_next_action_id = "rerun_reviewed_mujoco_motion_with_bundle_model_path"
    elif motion_bundle_consistency_status == "reviewed_mujoco_motion_model_path_mismatch":
        physical_motion_next_action_id = (
            "align_reviewed_mujoco_motion_with_bundle_model_path"
        )
    elif motion_bundle_consistency_status == "reviewed_mujoco_motion_model_digest_missing":
        physical_motion_next_action_id = "record_reviewed_mujoco_motion_model_sha256"
    elif (
        motion_bundle_consistency_status
        == "reviewed_mujoco_motion_model_observed_digest_missing"
    ):
        physical_motion_next_action_id = (
            "verify_reviewed_mujoco_motion_model_file_sha256"
        )
    elif (
        motion_bundle_consistency_status
        == "reviewed_mujoco_motion_model_observed_digest_mismatch"
    ):
        physical_motion_next_action_id = (
            "inspect_reviewed_mujoco_motion_model_file_sha256"
        )
    elif motion_bundle_consistency_status == "reviewed_mujoco_motion_model_digest_mismatch":
        physical_motion_next_action_id = (
            "align_reviewed_mujoco_motion_with_bundle_model_digest"
        )
    elif gate.get("reviewed_mujoco_motion_contradictory_ready_state") is True:
        reviewed_mujoco_next_required_action_ids = gate.get(
            "reviewed_mujoco_next_required_action_ids"
        )
        reviewed_mujoco_next_required_action_ids = (
            reviewed_mujoco_next_required_action_ids
            if isinstance(reviewed_mujoco_next_required_action_ids, list)
            else []
        )
        physical_motion_next_action_id = (
            reviewed_mujoco_next_required_action_ids[0]
            if reviewed_mujoco_next_required_action_ids
            else "resolve_contradictory_reviewed_mujoco_motion_gate_state"
        )
    else:
        physical_motion_next_action_id = "prove_physical_reviewed_model_motion"
    physical_bundle_authority_ready = (
        gate.get("physical_so101_model_authority_ready") is True
    )
    source_next_required_action_ids = gate.get("source_authority_next_required_action_ids")
    source_next_required_action_ids = (
        source_next_required_action_ids
        if isinstance(source_next_required_action_ids, list)
        else []
    )
    bundle_next_required_action_ids = gate.get("physical_bundle_next_required_action_ids")
    bundle_next_required_action_ids = (
        bundle_next_required_action_ids
        if isinstance(bundle_next_required_action_ids, list)
        else []
    )
    if source_next_required_action_ids:
        source_next_action_id = source_next_required_action_ids[0]
    elif gate.get("source_authority_contradictory_ready_state") is True:
        source_next_action_id = "resolve_contradictory_source_authority_gate_state"
    else:
        source_next_action_id = "review_and_declare_authoritative_so101_model_source"
    bundle_next_action_id = (
        bundle_next_required_action_ids[0]
        if bundle_next_required_action_ids
        else "resolve_contradictory_physical_bundle_authority_gate_state"
        if gate.get("physical_bundle_authority_contradictory_ready_state") is True
        else "supply_reviewed_so101_model_bundle_manifest"
    )
    item_specs = [
        {
            "item_id": "source_authority_ready",
            "gate": "reviewed_model_authority",
            "required_state": "source_authority_ready",
            "observed_ready": gate.get("source_authority_ready") is True,
            "evidence_artifact_path": gate.get("source_inventory_summary_path"),
            "next_action_id": source_next_action_id,
            "operator_action": (
                "Scan or supply candidate SO-101 model-source roots, then review "
                "provenance/license/source authority and rerun the source inventory "
                "with authoritative path/root plus review metadata."
            ),
        },
        {
            "item_id": "physical_bundle_authority_ready",
            "gate": "reviewed_model_authority",
            "required_state": "physical_so101_model_authority_ready",
            "observed_ready": gate.get("physical_so101_model_authority_ready") is True,
            "evidence_artifact_path": gate.get("bundle_manifest_summary_path"),
            "next_action_id": bundle_next_action_id,
            "operator_action": (
                "Supply a reviewed SO-101 model bundle manifest with mesh roots, reviewed "
                "joint limits, target frame, TCP offset, and base-to-board alignment."
            ),
        },
        {
            "item_id": "source_bundle_consistency",
            "gate": "reviewed_model_authority",
            "required_state": "source_bundle_model_path_and_digest_consistent",
            "observed_ready": gate.get("source_bundle_consistency_ready") is True,
            "blocked_by_prior_requirements": (
                source_bundle_consistency.get("status")
                == "not_checked_prerequisites_not_ready"
            ),
            "blocked_by_prior_requirement_ids": [
                "source_authority_ready",
                "physical_bundle_authority_ready",
            ],
            "evidence_artifact_path": gate.get("summary_path"),
            "next_action_id": source_bundle_consistency_next_action_id,
            "operator_action": (
                "Use the same reviewed SO-101 model path in the source inventory and "
                "bundle manifest, and record the same reviewed SHA-256 digest for that "
                "file; an authoritative root alone does not authorize a different "
                "selected model file."
            ),
            "source_bundle_consistency_status": consistency_status,
            "source_bundle_consistency_blocker": source_bundle_consistency.get(
                "blocker"
            ),
            "selected_authoritative_candidate_path": source_bundle_consistency.get(
                "selected_authoritative_candidate_path"
            ),
            "bundle_model_path": source_bundle_consistency.get("bundle_model_path"),
            "selected_authoritative_candidate_sha256": (
                source_bundle_consistency.get("selected_authoritative_candidate_sha256")
            ),
            "bundle_model_declared_sha256": source_bundle_consistency.get(
                "bundle_model_declared_sha256"
            ),
            "bundle_model_observed_sha256": source_bundle_consistency.get(
                "bundle_model_observed_sha256"
            ),
        },
        {
            "item_id": "physical_reviewed_mujoco_motion_checked",
            "gate": "mujoco_scene_validity",
            "required_state": "physical_reviewed_model_motion_checked",
            "observed_ready": gate.get("physical_reviewed_model_motion_checked") is True,
            "blocked_by_prior_requirements": (
                not physical_bundle_authority_ready or not source_bundle_consistency_ready
            ),
            "blocked_by_prior_requirement_ids": [
                "physical_bundle_authority_ready",
                "source_bundle_consistency",
            ],
            "evidence_artifact_path": gate.get("reviewed_mujoco_bundle_summary_path"),
            "next_action_id": physical_motion_next_action_id,
            "operator_action": (
                "Load the reviewed bundle in MuJoCo, map all SO-101 joints, find the target "
                "frame, prove SimRobot joint motion without fallback behavior, and keep "
                "the motion summary tied to the same reviewed model path and digest."
            ),
            "reviewed_mujoco_motion_bundle_consistency_status": (
                motion_bundle_consistency_status
            ),
            "reviewed_mujoco_motion_bundle_consistency_blocker": (
                motion_bundle_consistency.get("blocker")
            ),
            "bundle_model_path": motion_bundle_consistency.get("bundle_model_path"),
            "reviewed_mujoco_motion_model_path": motion_bundle_consistency.get(
                "reviewed_mujoco_motion_model_path"
            ),
            "bundle_model_declared_sha256": motion_bundle_consistency.get(
                "bundle_model_declared_sha256"
            ),
            "reviewed_mujoco_motion_model_declared_sha256": (
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_declared_sha256"
                )
            ),
            "reviewed_mujoco_motion_model_observed_sha256": (
                motion_bundle_consistency.get(
                    "reviewed_mujoco_motion_model_observed_sha256"
                )
            ),
        },
    ]
    items: list[dict[str, Any]] = []
    all_blockers = gate.get("blockers") or []

    def blocker_item_status(spec: dict[str, Any]) -> str:
        if spec["observed_ready"]:
            return "ready"
        if spec.get("blocked_by_prior_requirements"):
            return "blocked_by_prior_requirements"
        return "action_required"

    item_status_by_id = {
        spec["item_id"]: blocker_item_status(spec)
        for spec in item_specs
        if isinstance(spec.get("item_id"), str)
    }

    for priority, spec in enumerate(item_specs, start=1):
        status = blocker_item_status(spec)
        blocked_by_prior_requirement_ids = (
            spec.get("blocked_by_prior_requirement_ids", [])
            if status == "blocked_by_prior_requirements"
            else []
        )
        related_blockers = [
            blocker
            for blocker in all_blockers
            if (
                spec["item_id"] == "source_authority_ready"
                and ("source" in blocker or "authoritative" in blocker)
            )
            or (
                spec["item_id"] == "physical_bundle_authority_ready"
                and (
                    "manifest" in blocker
                    or "mesh" in blocker
                    or "joint" in blocker
                    or "target" in blocker
                    or "tcp" in blocker
                    or "base" in blocker
                    or "contract" in blocker
                    or "physical_bundle" in blocker
                    or "physical_authority" in blocker
                )
            )
            or (
                spec["item_id"] == "source_bundle_consistency"
                and (
                    "align_source_inventory" in blocker
                    or "model_path" in blocker
                    or "model_digest" in blocker
                    or "model_sha256" in blocker
                    or "sha256" in blocker
                    or "declare_reviewed_authoritative_so101_source_path_or_root" in blocker
                    or "align_selected_so101_source_model" in blocker
                    or "record_reviewed_so101_model_file_sha256" in blocker
                    or "verify_reviewed_so101_bundle_model_file_sha256" in blocker
                    or "inspect_reviewed_so101_bundle_model_file_sha256" in blocker
                )
            )
            or (
                spec["item_id"] == "physical_reviewed_mujoco_motion_checked"
                and (
                    (
                        not spec.get("blocked_by_prior_requirements")
                        and (
                            "mujoco" in blocker
                            or "motion" in blocker
                            or "rerun_reviewed_mujoco_motion" in blocker
                            or "align_reviewed_mujoco_motion" in blocker
                            or "record_reviewed_mujoco_motion" in blocker
                            or "reviewed_mujoco_motion" in blocker
                        )
                    )
                    or (
                        spec.get("blocked_by_prior_requirements")
                        and (
                            "manifest" in blocker
                            or "mesh" in blocker
                            or "joint" in blocker
                            or "target" in blocker
                            or "tcp" in blocker
                            or "base" in blocker
                            or "contract" in blocker
                            or "align_source_inventory" in blocker
                            or "model_path" in blocker
                        )
                    )
                )
            )
        ]
        if (
            not related_blockers
            and not spec["observed_ready"]
            and not spec.get("blocked_by_prior_requirements")
        ):
            related_blockers = [spec["next_action_id"]]
        items.append(
            {
                "priority": priority,
                **spec,
                "status": status,
                "blockers": related_blockers,
                "blocked_by_prior_requirement_ids": blocked_by_prior_requirement_ids,
                "blocked_by_prior_requirement_statuses": {
                    requirement_id: item_status_by_id.get(requirement_id)
                    for requirement_id in blocked_by_prior_requirement_ids
                },
                "development_fixture_evidence_not_physical_so101_truth": gate.get(
                    "development_fixture_evidence_not_physical_so101_truth"
                )
                is True,
            }
        )

    if gate.get("development_fixture_evidence_present") is True:
        items.append(
            {
                "priority": len(items) + 1,
                "item_id": "development_fixture_authority_boundary",
                "gate": "authority_boundary",
                "required_state": "no_development_fixture_evidence_in_ready_gate",
                "observed_ready": False,
                "status": "action_required",
                "evidence_artifact_path": gate.get("summary_path"),
                "next_action_id": (
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ),
                "operator_action": (
                    "Resolve hardware-free fixture readiness or fixture-motion evidence "
                    "before treating the aggregate gate as reviewed physical SO-101 truth."
                ),
                "blockers": [
                    "replace_development_fixture_evidence_with_reviewed_physical_so101_authority"
                ],
                "development_fixture_evidence_not_physical_so101_truth": True,
            }
        )
    elif gate.get("development_fixture_evidence_not_physical_so101_truth") is True:
        items.append(
            {
                "priority": len(items) + 1,
                "item_id": "development_fixture_authority_boundary",
                "gate": "authority_boundary",
                "required_state": "development_fixture_evidence_not_physical_so101_truth",
                "observed_ready": True,
                "status": "caveat_enforced",
                "evidence_artifact_path": gate.get("summary_path"),
                "next_action_id": "do_not_promote_fixture_evidence_to_physical_truth",
                "operator_action": (
                    "Keep development scaffold evidence as automation coverage only until the "
                    "reviewed source, bundle, and MuJoCo motion gates are all ready."
                ),
                "blockers": [],
                "development_fixture_evidence_not_physical_so101_truth": True,
            }
        )

    action_required_item_ids = [
        item["item_id"] for item in items if item.get("status") == "action_required"
    ]
    blocked_by_prior_item_ids = [
        item["item_id"]
        for item in items
        if item.get("status") == "blocked_by_prior_requirements"
    ]
    return {
        "schema": "lerobot.sim.so101_reviewed_model_authority_blocker_packet.v1",
        "ok": True,
        "status": (
            "reviewed_model_authority_ready"
            if gate.get("ready") is True
            else "reviewed_model_authority_blocked"
        ),
        "model_authority": "blocker_packet_not_authority",
        "ready": gate.get("ready") is True,
        "action_required_item_ids": action_required_item_ids,
        "action_required_count": len(action_required_item_ids),
        "blocked_by_prior_requirements_item_ids": blocked_by_prior_item_ids,
        "blocked_by_prior_requirements_count": len(blocked_by_prior_item_ids),
        "item_count": len(items),
        "item_ids": [item["item_id"] for item in items],
        "next_action_ids": [
            item["next_action_id"]
            for item in items
            if item.get("status") == "action_required" and item.get("next_action_id")
        ],
        "source_inventory_summary_path": gate.get("source_inventory_summary_path"),
        "bundle_manifest_summary_path": gate.get("bundle_manifest_summary_path"),
        "reviewed_mujoco_bundle_summary_path": gate.get(
            "reviewed_mujoco_bundle_summary_path"
        ),
        "development_fixture_evidence_not_physical_so101_truth": gate.get(
            "development_fixture_evidence_not_physical_so101_truth"
        )
        is True,
        "items": items,
        "caveats": [
            "This packet is a blocker review aid, not reviewed physical SO-101 model authority.",
            "The gate is ready only when source authority, physical bundle authority, source-to-bundle model path/digest consistency, and physical-reviewed MuJoCo motion are all true.",
            "Development fixture evidence remains automation coverage and must not be used as physical calibration truth.",
        ],
    }


def write_so101_reviewed_model_authority_gate_artifacts(
    output_dir: Path,
    gate: dict[str, Any],
) -> dict[str, Any]:
    gate_dir = output_dir / SO101_REVIEWED_MODEL_AUTHORITY_GATE_DIR_NAME
    summary_path = gate_dir / SO101_REVIEWED_MODEL_AUTHORITY_GATE_SUMMARY_NAME
    checklist_path = gate_dir / SO101_REVIEWED_MODEL_AUTHORITY_GATE_CHECKLIST_NAME
    blocker_packet_path = (
        gate_dir / SO101_REVIEWED_MODEL_AUTHORITY_GATE_BLOCKER_PACKET_JSON_NAME
    )
    blocker_packet_csv_path = (
        gate_dir / SO101_REVIEWED_MODEL_AUTHORITY_GATE_BLOCKER_PACKET_CSV_NAME
    )
    readme_path = gate_dir / SO101_REVIEWED_MODEL_AUTHORITY_GATE_README_NAME
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(checklist_path),
        "blocker_packet_json": str(blocker_packet_path),
        "blocker_packet_csv": str(blocker_packet_csv_path),
        "readme_md": str(readme_path),
    }
    blocker_packet = so101_reviewed_model_authority_blocker_packet(
        {
            **gate,
            "summary_path": str(summary_path),
        }
    )
    payload = {
        "schema": SO101_REVIEWED_MODEL_AUTHORITY_GATE_SCHEMA,
        **gate,
        "ok": bool(gate.get("ready")),
        "summary_path": str(summary_path),
        "artifact_dir": str(gate_dir),
        "artifacts": artifacts,
        "review_status": (
            "ready_for_reviewed_model_backed_work"
            if gate.get("ready") is True
            else "blocked_before_reviewed_model_backed_work"
        ),
        "authority_sources": {
            "source_inventory_summary_path": gate.get("source_inventory_summary_path"),
            "bundle_manifest_summary_path": gate.get("bundle_manifest_summary_path"),
            "reviewed_mujoco_bundle_summary_path": gate.get(
                "reviewed_mujoco_bundle_summary_path"
            ),
        },
        "blocker_packet_status": blocker_packet["status"],
        "blocker_packet_model_authority": blocker_packet["model_authority"],
        "blocker_packet_item_count": blocker_packet["item_count"],
        "blocker_packet_action_required_count": blocker_packet["action_required_count"],
        "blocker_packet_action_required_item_ids": blocker_packet[
            "action_required_item_ids"
        ],
        "blocker_packet_blocked_by_prior_requirements_count": blocker_packet[
            "blocked_by_prior_requirements_count"
        ],
        "blocker_packet_blocked_by_prior_requirements_item_ids": blocker_packet[
            "blocked_by_prior_requirements_item_ids"
        ],
        "blocker_packet_next_action_ids": blocker_packet["next_action_ids"],
        "blocker_packet": blocker_packet,
    }
    blocker_items_by_id = {
        item.get("item_id"): item
        for item in blocker_packet.get("items", [])
        if isinstance(item, dict) and item.get("item_id")
    }

    def checklist_priority(item_id: str) -> int | None:
        item = blocker_items_by_id.get(item_id)
        return item.get("priority") if isinstance(item, dict) else None

    def checklist_status(item_id: str, fallback_status: str) -> str:
        item = blocker_items_by_id.get(item_id)
        status = item.get("status") if isinstance(item, dict) else None
        return status if isinstance(status, str) and status else fallback_status

    def checklist_next_action_id(item_id: str) -> str | None:
        item = blocker_items_by_id.get(item_id)
        action_id = item.get("next_action_id") if isinstance(item, dict) else None
        return action_id if isinstance(action_id, str) and action_id else None

    def checklist_blocked_by_prior_requirement_ids(item_id: str) -> list[str]:
        item = blocker_items_by_id.get(item_id)
        blocked = (
            item.get("blocked_by_prior_requirement_ids")
            if isinstance(item, dict)
            else None
        )
        return [str(value) for value in blocked] if isinstance(blocked, list) else []

    def checklist_blocked_by_prior_requirement_statuses(item_id: str) -> dict[str, str]:
        item = blocker_items_by_id.get(item_id)
        statuses = (
            item.get("blocked_by_prior_requirement_statuses")
            if isinstance(item, dict)
            else None
        )
        return (
            {str(key): str(value) for key, value in statuses.items()}
            if isinstance(statuses, dict)
            else {}
        )

    checklist_rows = [
        {
            "requirement_id": "source_authority_ready",
            "category": "reviewed_model_authority",
            "priority": checklist_priority("source_authority_ready"),
            "status": checklist_status(
                "source_authority_ready",
                "ok"
                if gate.get("source_authority_ready") is True
                else "action_required",
            ),
            "observed_value": markdown_bool(gate.get("source_authority_ready")),
            "expected_value": "true",
            "blocked_by_prior_requirement_ids": checklist_blocked_by_prior_requirement_ids(
                "source_authority_ready"
            ),
            "blocked_by_prior_requirement_statuses": checklist_blocked_by_prior_requirement_statuses(
                "source_authority_ready"
            ),
            "next_action_id": checklist_next_action_id("source_authority_ready"),
            "blockers": "; ".join(
                blocker
                for blocker in gate.get("blockers", [])
                if "source" in blocker or "authoritative" in blocker
            ),
            "notes": "Model source authority must be reviewed before the bundle can close the gate.",
        },
        {
            "requirement_id": "physical_bundle_authority_ready",
            "category": "reviewed_model_authority",
            "priority": checklist_priority("physical_bundle_authority_ready"),
            "status": checklist_status(
                "physical_bundle_authority_ready",
                "ok"
                if gate.get("physical_so101_model_authority_ready") is True
                else "action_required",
            ),
            "observed_value": markdown_bool(gate.get("physical_so101_model_authority_ready")),
            "expected_value": "true",
            "blocked_by_prior_requirement_ids": checklist_blocked_by_prior_requirement_ids(
                "physical_bundle_authority_ready"
            ),
            "blocked_by_prior_requirement_statuses": checklist_blocked_by_prior_requirement_statuses(
                "physical_bundle_authority_ready"
            ),
            "next_action_id": checklist_next_action_id(
                "physical_bundle_authority_ready"
            ),
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "The bundle manifest must provide physical SO-101 authority, not only a development fixture.",
        },
        {
            "requirement_id": "source_bundle_consistency",
            "category": "reviewed_model_authority",
            "priority": checklist_priority("source_bundle_consistency"),
            "status": checklist_status(
                "source_bundle_consistency",
                (
                    "ok"
                    if gate.get("source_bundle_consistency_ready") is True
                    else "blocked_by_prior_requirements"
                    if gate.get("source_bundle_consistency_status")
                    == "not_checked_prerequisites_not_ready"
                    else "action_required"
                ),
            ),
            "observed_value": gate.get("source_bundle_consistency_status"),
            "expected_value": "source_bundle_model_path_and_digest_consistent",
            "blocked_by_prior_requirement_ids": checklist_blocked_by_prior_requirement_ids(
                "source_bundle_consistency"
            ),
            "blocked_by_prior_requirement_statuses": checklist_blocked_by_prior_requirement_statuses(
                "source_bundle_consistency"
            ),
            "next_action_id": checklist_next_action_id("source_bundle_consistency"),
            "blockers": "; ".join(
                blocker
                for blocker in gate.get("blockers", [])
                if (
                    "align_source_inventory" in blocker
                    or "model_path" in blocker
                    or "model digest" in blocker
                    or "model_sha256" in blocker
                )
            ),
            "notes": "The reviewed source inventory and reviewed bundle manifest must identify the same SO-101 model path and SHA-256 digest.",
        },
        {
            "requirement_id": "physical_reviewed_mujoco_motion_checked",
            "category": "mujoco_scene_validity",
            "priority": checklist_priority("physical_reviewed_mujoco_motion_checked"),
            "status": checklist_status(
                "physical_reviewed_mujoco_motion_checked",
                "ok"
                if gate.get("physical_reviewed_model_motion_checked") is True
                else "action_required",
            ),
            "observed_value": markdown_bool(gate.get("physical_reviewed_model_motion_checked")),
            "expected_value": "true",
            "blocked_by_prior_requirement_ids": checklist_blocked_by_prior_requirement_ids(
                "physical_reviewed_mujoco_motion_checked"
            ),
            "blocked_by_prior_requirement_statuses": checklist_blocked_by_prior_requirement_statuses(
                "physical_reviewed_mujoco_motion_checked"
            ),
            "next_action_id": checklist_next_action_id(
                "physical_reviewed_mujoco_motion_checked"
            ),
            "blockers": "; ".join(
                blocker
                for blocker in gate.get("blockers", [])
                if "mujoco" in blocker or "motion" in blocker or "model" in blocker
            ),
            "notes": "A ready reviewed manifest must load in MuJoCo and prove SO-101 joint motion.",
        },
        {
            "requirement_id": "development_fixture_caveat",
            "category": "authority_boundary",
            "priority": checklist_priority("development_fixture_authority_boundary"),
            "status": checklist_status(
                "development_fixture_authority_boundary",
                "ok"
                if gate.get("development_fixture_evidence_not_physical_so101_truth") is True
                else "review_required",
            ),
            "observed_value": markdown_bool(
                gate.get("development_fixture_evidence_not_physical_so101_truth")
            ),
            "expected_value": "true while the gate is blocked or fixture-only evidence exists",
            "blocked_by_prior_requirement_ids": checklist_blocked_by_prior_requirement_ids(
                "development_fixture_authority_boundary"
            ),
            "blocked_by_prior_requirement_statuses": checklist_blocked_by_prior_requirement_statuses(
                "development_fixture_authority_boundary"
            ),
            "next_action_id": checklist_next_action_id(
                "development_fixture_authority_boundary"
            ),
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "Development fixture evidence remains automation coverage only.",
        },
    ]
    payload["checklist_status_by_requirement_id"] = {
        row["requirement_id"]: row["status"] for row in checklist_rows
    }
    payload["checklist_next_action_ids_by_requirement_id"] = {
        row["requirement_id"]: row["next_action_id"]
        for row in checklist_rows
        if row.get("next_action_id")
    }
    payload["checklist_blocked_by_prior_requirement_ids_by_requirement_id"] = {
        row["requirement_id"]: row["blocked_by_prior_requirement_ids"]
        for row in checklist_rows
        if row.get("blocked_by_prior_requirement_ids")
    }
    payload["checklist_blocked_by_prior_requirement_statuses_by_requirement_id"] = {
        row["requirement_id"]: row["blocked_by_prior_requirement_statuses"]
        for row in checklist_rows
        if row.get("blocked_by_prior_requirement_statuses")
    }
    gate_dir.mkdir(parents=True, exist_ok=True)
    write_json(summary_path, payload)
    fieldnames = (
        "priority",
        "requirement_id",
        "category",
        "status",
        "observed_value",
        "expected_value",
        "blocked_by_prior_requirement_ids",
        "blocked_by_prior_requirement_statuses",
        "next_action_id",
        "blockers",
        "notes",
    )
    with checklist_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in checklist_rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})
    write_json(blocker_packet_path, blocker_packet)
    blocker_fieldnames = (
        "priority",
        "item_id",
        "gate",
        "required_state",
        "status",
        "observed_ready",
        "blocked_by_prior_requirement_ids",
        "blocked_by_prior_requirement_statuses",
        "next_action_id",
        "source_bundle_consistency_status",
        "source_bundle_consistency_blocker",
        "selected_authoritative_candidate_path",
        "bundle_model_path",
        "selected_authoritative_candidate_sha256",
        "bundle_model_declared_sha256",
        "bundle_model_observed_sha256",
        "reviewed_mujoco_motion_bundle_consistency_status",
        "reviewed_mujoco_motion_bundle_consistency_blocker",
        "reviewed_mujoco_motion_model_path",
        "reviewed_mujoco_motion_model_declared_sha256",
        "reviewed_mujoco_motion_model_observed_sha256",
        "evidence_artifact_path",
        "blockers",
        "operator_action",
        "development_fixture_evidence_not_physical_so101_truth",
    )
    with blocker_packet_csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=blocker_fieldnames)
        writer.writeheader()
        for item in blocker_packet["items"]:
            writer.writerow({field: csv_cell(item.get(field)) for field in blocker_fieldnames})
    blocker_lines = (
        [f"- `{blocker}`" for blocker in gate.get("blockers", [])]
        if gate.get("blockers")
        else ["- none"]
    )
    readme_path.write_text(
        "\n".join(
            [
                "# SO-101 Reviewed Model Authority Gate",
                "",
                f"- Status: `{gate.get('status')}`",
                f"- Ready: `{markdown_bool(gate.get('ready'))}`",
                f"- Source authority ready: `{markdown_bool(gate.get('source_authority_ready'))}`",
                "- Physical SO-101 model authority ready: "
                f"`{markdown_bool(gate.get('physical_so101_model_authority_ready'))}`",
                "- Source/bundle model identity consistency: "
                f"`{gate.get('source_bundle_consistency_status')}`",
                "- Physical reviewed MuJoCo motion checked: "
                f"`{markdown_bool(gate.get('physical_reviewed_model_motion_checked'))}`",
                "- Development fixture evidence is not physical SO-101 truth: "
                f"`{markdown_bool(gate.get('development_fixture_evidence_not_physical_so101_truth'))}`",
                "- Immediate action required items: "
                f"`{markdown_list_value(payload.get('blocker_packet_action_required_item_ids'))}`",
                "- Prioritized next required actions: "
                f"`{markdown_list_value(gate.get('next_required_action_ids'))}`",
                "- Blocked by prior requirement items: "
                f"`{markdown_list_value(payload.get('blocker_packet_blocked_by_prior_requirements_item_ids'))}`",
                "- Blocked prior requirement statuses: "
                f"`{markdown_mapping_value(payload.get('checklist_blocked_by_prior_requirement_statuses_by_requirement_id'))}`",
                f"- Blocker packet: `{blocker_packet_path}`",
                f"- Blocker packet rows: `{blocker_packet_csv_path}`",
                "",
                "## Blockers",
                "",
                *blocker_lines,
                "",
                "## Evidence Sources",
                "",
                f"- Source inventory: `{gate.get('source_inventory_summary_path')}`",
                f"- Bundle manifest: `{gate.get('bundle_manifest_summary_path')}`",
                f"- Reviewed MuJoCo bundle: `{gate.get('reviewed_mujoco_bundle_summary_path')}`",
                "",
                "This artifact is a hardware-free gate summary. It is ready only when source authority, physical bundle authority, source-to-bundle model path/digest consistency, and physical-reviewed MuJoCo motion are all true.",
                "",
            ]
        )
    )
    return payload


def _summary_path(value: dict[str, Any]) -> str | None:
    path = value.get("summary_path")
    return path if isinstance(path, str) and path else None


def _json_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _json_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]


def so101_board_pick_phase_evidence_ready(board_pick: dict[str, Any]) -> bool:
    phase_ids = _json_string_list(board_pick.get("pick_place_phase_ids"))
    failed_phase_ids = _json_string_list(board_pick.get("pick_place_failed_phase_ids"))
    phase_count = board_pick.get("pick_place_phase_count")
    phase_evidence = board_pick.get("pick_place_phase_evidence")
    if (
        phase_ids != list(SO101_BOARD_PICK_REQUIRED_PHASE_IDS)
        or failed_phase_ids
        or phase_count != len(SO101_BOARD_PICK_REQUIRED_PHASE_IDS)
        or board_pick.get("pick_place_all_required_phases_verified") is not True
        or not isinstance(phase_evidence, list)
        or len(phase_evidence) != len(SO101_BOARD_PICK_REQUIRED_PHASE_IDS)
    ):
        return False
    for expected_phase_id, row in zip(SO101_BOARD_PICK_REQUIRED_PHASE_IDS, phase_evidence):
        if not isinstance(row, dict):
            return False
        if row.get("phase_id") != expected_phase_id or row.get("ok") is not True:
            return False
        if not isinstance(row.get("criteria"), list) or not row["criteria"]:
            return False
        if not isinstance(row.get("metrics"), dict) or not row["metrics"]:
            return False
    return True


def so101_board_pick_stage_sequence_ready(board_pick: dict[str, Any]) -> bool:
    required_sequence = _json_string_list(board_pick.get("required_stage_sequence"))
    observed_sequence = _json_string_list(board_pick.get("observed_stage_sequence"))
    missing_stage_ids = _json_string_list(board_pick.get("missing_stage_ids"))
    unexpected_stage_ids = _json_string_list(board_pick.get("unexpected_stage_ids"))
    manual_pose_after_reset_stage_ids = _json_string_list(
        board_pick.get("manual_piece_pose_after_reset_stage_ids")
    )
    stage_contract_errors = _json_string_list(
        board_pick.get("stage_sequence_contract_errors")
    )
    expected_sequence = list(SO101_BOARD_PICK_REQUIRED_STAGE_SEQUENCE)
    return (
        required_sequence == expected_sequence
        and observed_sequence == expected_sequence
        and missing_stage_ids == []
        and unexpected_stage_ids == []
        and board_pick.get("stage_sequence_order_ok") is True
        and board_pick.get("stage_sequence_contract_ok") is True
        and stage_contract_errors == []
        and manual_pose_after_reset_stage_ids == []
    )


def so101_board_pick_detailed_evidence_ready(board_pick: dict[str, Any]) -> bool:
    final_target_xy_error_m = _json_number(board_pick.get("final_target_xy_error_m"))
    target_xy_tolerance_m = _json_number(board_pick.get("target_xy_tolerance_m"))
    final_place_z_error_m = _json_number(board_pick.get("final_place_z_error_m"))
    place_z_tolerance_m = _json_number(board_pick.get("place_z_tolerance_m"))
    final_target_within_tolerance = (
        final_target_xy_error_m is not None
        and target_xy_tolerance_m is not None
        and final_target_xy_error_m <= target_xy_tolerance_m
    )
    final_place_z_within_tolerance = (
        final_place_z_error_m is not None
        and place_z_tolerance_m is not None
        and final_place_z_error_m <= place_z_tolerance_m
    )
    return (
        board_pick.get("board_source_pick_place_verified") is True
        and board_pick.get("source_pick_started_at_source") is True
        and board_pick.get("close_two_finger_contact_observed") is True
        and board_pick.get("lift_verified") is True
        and board_pick.get("board_contact_cleared_during_lift") is True
        and board_pick.get("transfer_verified") is True
        and board_pick.get("place_without_manual_piece_pose_verified") is True
        and board_pick.get("release_contact_cleared_after_retreat") is True
        and board_pick.get("final_board_contact_observed") is True
        and final_target_within_tolerance
        and final_place_z_within_tolerance
        and so101_board_pick_phase_evidence_ready(board_pick)
        and so101_board_pick_stage_sequence_ready(board_pick)
    )


def so101_board_pick_authority_contract(
    board_pick: dict[str, Any],
    *,
    detailed_evidence_ready: bool,
) -> dict[str, Any]:
    reviewed_model_authority_ready = (
        board_pick.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
    )
    ready_for_model_backed_ik = board_pick.get("ready_for_model_backed_ik") is True
    seeded_source_pose = board_pick.get("robot_pose_seeded_for_source_fixture") is True
    manual_pose_after_reset = board_pick.get("manual_piece_pose_used_after_reset") is True
    physical_truth_claimed = (
        board_pick.get("observed_evidence_is_physical_so101_authority") is True
    )
    policy_training_claimed = board_pick.get("ready_for_policy_training") is True
    policy_authority_claimed = (
        board_pick.get("observed_evidence_is_policy_training_authority") is True
    )

    blockers: list[str] = []
    if not detailed_evidence_ready:
        blockers.append("provide_complete_board_pick_detailed_evidence")
    if not reviewed_model_authority_ready:
        blockers.append("use_reviewed_so101_model_authority_for_board_pick")
    if not ready_for_model_backed_ik:
        blockers.append("repeat_board_source_pick_place_with_reviewed_model_backed_ik")
    if seeded_source_pose:
        blockers.append("remove_seeded_source_pose_from_board_pick")
    if manual_pose_after_reset:
        blockers.append("remove_manual_piece_pose_after_reset_from_board_pick")
    if physical_truth_claimed:
        blockers.append("remove_physical_so101_truth_claim_from_board_pick")
    if policy_training_claimed or policy_authority_claimed:
        blockers.append("remove_policy_training_authority_claim_from_board_pick")

    ready = not blockers
    if ready:
        status = "reviewed_model_backed_board_source_pick_place_verified"
    elif not reviewed_model_authority_ready:
        status = "board_pick_not_reviewed_model_authority"
    elif not ready_for_model_backed_ik:
        status = "board_pick_not_model_backed_ik"
    elif seeded_source_pose:
        status = "board_pick_seeded_source_pose_not_reviewed_ik"
    elif manual_pose_after_reset:
        status = "board_pick_manual_piece_pose_after_reset"
    elif physical_truth_claimed:
        status = "board_pick_physical_truth_claimed"
    elif policy_training_claimed or policy_authority_claimed:
        status = "board_pick_policy_training_authority_claimed"
    elif not detailed_evidence_ready:
        status = "board_pick_detailed_evidence_incomplete"
    else:
        status = "board_pick_authority_contract_blocked"

    return {
        "ready": ready,
        "status": status,
        "blockers": blockers,
        "reviewed_model_authority_ready": reviewed_model_authority_ready,
        "ready_for_model_backed_ik": ready_for_model_backed_ik,
        "seeded_source_pose": seeded_source_pose,
        "manual_piece_pose_after_reset": manual_pose_after_reset,
        "physical_truth_claimed": physical_truth_claimed,
        "policy_training_claimed": policy_training_claimed,
        "policy_authority_claimed": policy_authority_claimed,
        "detailed_evidence_ready": detailed_evidence_ready,
    }


def so101_reviewed_mujoco_downstream_handoff_contract(
    reviewed_mujoco_bundle: dict[str, Any],
) -> dict[str, Any]:
    schema = reviewed_mujoco_bundle.get("downstream_handoff_schema")
    item_ids = reviewed_mujoco_bundle.get("downstream_handoff_item_ids")
    item_ids = [str(item) for item in item_ids] if isinstance(item_ids, list) else []
    missing_item_ids = sorted(
        set(SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_ITEM_IDS) - set(item_ids)
    )
    item_count = reviewed_mujoco_bundle.get("downstream_handoff_item_count")
    item_count_ok = (
        isinstance(item_count, int)
        and item_count == len(item_ids)
        and item_count >= len(SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_ITEM_IDS)
    )
    raw_ready = reviewed_mujoco_bundle.get("downstream_handoff_ready") is True
    fixture_ready = (
        reviewed_mujoco_bundle.get("fixture_handoff_ready_not_physical_so101_authority")
        is True
    )
    physical_motion_checked = (
        reviewed_mujoco_bundle.get("physical_reviewed_model_motion_checked") is True
    )
    fixture_motion_checked = (
        reviewed_mujoco_bundle.get("hardware_free_fixture_motion_checked") is True
    )
    reviewed_model_motion_checked = (
        reviewed_mujoco_bundle.get("reviewed_model_motion_checked") is True
    )
    motion_authority_status = reviewed_mujoco_bundle.get("motion_authority_status")
    physical_model_authority_ready = (
        reviewed_mujoco_bundle.get("physical_so101_model_authority_ready") is True
    )
    motion_evidence_not_physical = (
        reviewed_mujoco_bundle.get(
            "motion_evidence_not_physical_so101_authority"
        )
        is True
    )
    status = reviewed_mujoco_bundle.get("downstream_handoff_status")
    physical_truth_claimed = (
        reviewed_mujoco_bundle.get("downstream_handoff_physical_so101_truth_claimed")
        is True
    )
    development_fixture_not_truth = (
        reviewed_mujoco_bundle.get(
            "downstream_handoff_development_fixture_evidence_not_physical_so101_truth"
        )
        is True
    )
    handoff_raw_missing_inputs = reviewed_mujoco_bundle.get("missing_inputs")
    handoff_missing_inputs = unique_string_values(
        handoff_raw_missing_inputs if isinstance(handoff_raw_missing_inputs, list) else []
    )
    handoff_next_required = reviewed_mujoco_bundle.get("next_required_for_goal")
    handoff_next_required_action_ids = unique_string_values(
        [
            action.get("action_id") if isinstance(action, dict) else action
            for action in handoff_next_required
        ]
        if isinstance(handoff_next_required, list)
        else []
    )
    handoff_raw_explicit_action_ids = reviewed_mujoco_bundle.get(
        "next_required_action_ids"
    )
    handoff_explicit_action_ids = unique_string_values(
        handoff_raw_explicit_action_ids
        if isinstance(handoff_raw_explicit_action_ids, list)
        else []
    )
    handoff_pending_action_ids = unique_string_values(
        [
            *handoff_explicit_action_ids,
            *handoff_next_required_action_ids,
        ]
    )
    ready_handoff_has_open_work = (raw_ready or fixture_ready) and bool(
        handoff_missing_inputs or handoff_pending_action_ids
    )
    mujoco_motion_inputs = reviewed_mujoco_bundle.get("mujoco_motion_inputs")
    mujoco_motion_inputs = (
        mujoco_motion_inputs if isinstance(mujoco_motion_inputs, dict) else {}
    )
    joint_limit_enablement = mujoco_motion_inputs.get("mujoco_joint_limit_enablement")
    if not isinstance(joint_limit_enablement, dict):
        joint_limit_enablement = reviewed_mujoco_bundle.get(
            "mujoco_joint_limit_enablement"
        )
    joint_limit_enablement = (
        joint_limit_enablement if isinstance(joint_limit_enablement, dict) else {}
    )
    joint_limit_enablement_ok = joint_limit_enablement.get("ok") is True
    joint_limit_enablement_status = joint_limit_enablement.get("status")
    raw_missing_limited_joints = joint_limit_enablement.get("missing_limited_joints")
    missing_limited_joints = unique_string_values(
        raw_missing_limited_joints
        if isinstance(raw_missing_limited_joints, list)
        else []
    )
    ready_joint_limit_enablement_contract_ok = (
        joint_limit_enablement_ok
        and joint_limit_enablement_status == "so101_mujoco_joints_limited"
        and missing_limited_joints == []
    )

    physical_ready_contract_ok = (
        not raw_ready
        or (
            physical_motion_checked
            and reviewed_model_motion_checked
            and status == "physical_reviewed_mujoco_handoff_ready"
            and motion_authority_status == "physical_reviewed_model_motion_checked"
            and physical_model_authority_ready
            and fixture_ready is False
            and fixture_motion_checked is False
            and motion_evidence_not_physical is False
        )
    )
    fixture_contract_ok = (
        not fixture_ready
        or (
            raw_ready is False
            and physical_motion_checked is False
            and fixture_motion_checked
            and reviewed_model_motion_checked
            and status == "fixture_mujoco_handoff_ready_not_physical_authority"
            and motion_authority_status
            == "hardware_free_fixture_motion_checked_not_physical_so101_authority"
            and motion_evidence_not_physical
        )
    )
    blockers: list[str] = []
    if schema != SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_SCHEMA:
        blockers.append("provide_current_reviewed_mujoco_downstream_handoff_schema")
    if reviewed_mujoco_bundle.get("downstream_handoff_model_authority") != (
        "downstream_handoff_not_authority"
    ):
        blockers.append("repair_reviewed_mujoco_downstream_handoff_authority")
    if (
        reviewed_mujoco_bundle.get(
            "downstream_handoff_observed_evidence_is_authority"
        )
        is not False
    ):
        blockers.append("mark_downstream_handoff_as_non_authority_snapshot")
    if physical_truth_claimed:
        blockers.append("remove_physical_so101_truth_claim_from_downstream_handoff")
    if not development_fixture_not_truth:
        blockers.append("mark_downstream_handoff_development_fixture_boundary")
    if missing_item_ids:
        blockers.append("provide_complete_reviewed_mujoco_downstream_handoff_items")
    if not item_count_ok:
        blockers.append("fix_reviewed_mujoco_downstream_handoff_item_count")
    if (raw_ready or fixture_ready) and handoff_missing_inputs:
        blockers.append("resolve_ready_reviewed_mujoco_handoff_missing_inputs")
    if (raw_ready or fixture_ready) and handoff_pending_action_ids:
        blockers.append("resolve_ready_reviewed_mujoco_handoff_pending_actions")
    if (raw_ready or fixture_ready) and not ready_joint_limit_enablement_contract_ok:
        blockers.append("provide_reviewed_mujoco_joint_limit_enablement_evidence")
    if raw_ready and not physical_ready_contract_ok:
        blockers.append("repair_physical_reviewed_mujoco_handoff_readiness_flags")
    if fixture_ready and not fixture_contract_ok:
        blockers.append("repair_fixture_reviewed_mujoco_handoff_flags")
    if reviewed_mujoco_bundle.get("downstream_handoff_ready") != (
        physical_motion_checked
    ):
        blockers.append("align_downstream_handoff_ready_with_physical_motion_check")
    if reviewed_model_motion_checked != (
        physical_motion_checked or fixture_motion_checked
    ):
        blockers.append("align_reviewed_model_motion_checked_with_motion_source")

    contract_ok = not blockers
    ready = contract_ok and raw_ready
    fixture_contract_ready = contract_ok and fixture_ready
    if not contract_ok:
        contract_status = "handoff_contract_invalid"
    elif ready:
        contract_status = "physical_reviewed_mujoco_handoff_ready"
    elif fixture_contract_ready:
        contract_status = "fixture_handoff_not_physical_so101_authority"
    else:
        contract_status = "reviewed_mujoco_handoff_not_ready"
    next_action_ids = unique_string_values(
        [
            *blockers,
            *([] if ready else ["make_reviewed_mujoco_downstream_handoff_ready"]),
        ]
    )
    return {
        "contract_ok": contract_ok,
        "contract_status": contract_status,
        "ready": ready,
        "raw_ready": raw_ready,
        "fixture_handoff_ready_not_physical_so101_authority": fixture_contract_ready,
        "raw_fixture_handoff_ready_not_physical_so101_authority": fixture_ready,
        "schema": schema,
        "expected_schema": SO101_REVIEWED_MUJOCO_DOWNSTREAM_HANDOFF_SCHEMA,
        "status": status,
        "model_authority": reviewed_mujoco_bundle.get(
            "downstream_handoff_model_authority"
        ),
        "observed_evidence_is_authority": reviewed_mujoco_bundle.get(
            "downstream_handoff_observed_evidence_is_authority"
        ),
        "physical_truth_claimed": physical_truth_claimed,
        "development_fixture_evidence_not_physical_so101_truth": (
            development_fixture_not_truth
        ),
        "item_count": item_count,
        "item_ids": item_ids,
        "missing_item_ids": missing_item_ids,
        "missing_inputs": handoff_missing_inputs,
        "pending_action_ids": handoff_pending_action_ids,
        "ready_handoff_has_open_work": ready_handoff_has_open_work,
        "blockers": blockers,
        "next_action_ids": next_action_ids,
        "physical_motion_checked": physical_motion_checked,
        "hardware_free_fixture_motion_checked": fixture_motion_checked,
        "reviewed_model_motion_checked": reviewed_model_motion_checked,
        "motion_authority_status": motion_authority_status,
        "physical_so101_model_authority_ready": physical_model_authority_ready,
        "motion_evidence_not_physical_so101_authority": motion_evidence_not_physical,
        "joint_limit_enablement_ok": joint_limit_enablement_ok,
        "joint_limit_enablement_status": joint_limit_enablement_status,
        "missing_limited_joints": missing_limited_joints,
        "required_limited_joints": list(SO101_CONTROL_JOINT_IDS),
    }


def so101_training_priority_gate_queue(
    reviewed_authority_gate: dict[str, Any],
    board_pick: dict[str, Any],
    training_rollouts: dict[str, Any],
    *,
    reviewed_mujoco_bundle: dict[str, Any] | None = None,
    mujoco_scene: dict[str, Any] | None = None,
    chess_env: dict[str, Any] | None = None,
    contact_probe: dict[str, Any] | None = None,
    grasp_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reviewed_mujoco_bundle = (
        reviewed_mujoco_bundle if isinstance(reviewed_mujoco_bundle, dict) else {}
    )
    mujoco_scene = mujoco_scene if isinstance(mujoco_scene, dict) else {}
    chess_env = chess_env if isinstance(chess_env, dict) else {}
    contact_probe = contact_probe if isinstance(contact_probe, dict) else {}
    grasp_probe = grasp_probe if isinstance(grasp_probe, dict) else {}

    reviewed_authority_ready = reviewed_authority_gate.get("ready") is True
    reviewed_motion_ready = (
        reviewed_authority_gate.get("physical_reviewed_model_motion_checked") is True
    )
    downstream_handoff_contract = (
        so101_reviewed_mujoco_downstream_handoff_contract(reviewed_mujoco_bundle)
    )
    reviewed_downstream_handoff_ready = downstream_handoff_contract.get("ready") is True
    fixture_downstream_handoff_ready = (
        downstream_handoff_contract.get(
            "fixture_handoff_ready_not_physical_so101_authority"
        )
        is True
    )
    mujoco_scene_automation_ready = mujoco_scene.get("status") == "ok"
    mujoco_scene_training_ready = (
        reviewed_authority_ready
        and reviewed_motion_ready
        and reviewed_downstream_handoff_ready
        and mujoco_scene_automation_ready
        and mujoco_scene.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
    )
    gym_automation_ready = chess_env.get("status") == "ok"
    gym_training_ready = (
        mujoco_scene_training_ready
        and gym_automation_ready
        and chess_env.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
    )
    contact_automation_ready = (
        contact_probe.get("all_board_contacts_observed") is True
        or contact_probe.get("status") == "ok"
    )
    grasp_automation_ready = (
        grasp_probe.get("status") == "contact_grasp_lift_place_physics_verified"
        or grasp_probe.get("contact_grasp_lift_place_physics_verified") is True
    )
    board_pick_reviewed_model_authority_ready = (
        board_pick.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
    )
    board_pick_detailed_evidence_ready = so101_board_pick_detailed_evidence_ready(
        board_pick
    )
    board_pick_authority_contract = so101_board_pick_authority_contract(
        board_pick,
        detailed_evidence_ready=board_pick_detailed_evidence_ready,
    )
    reviewed_model_backed_board_pick_place = (
        board_pick_authority_contract.get("ready") is True
    )
    scripted_pick_place_automation_ready = (
        contact_automation_ready
        and grasp_automation_ready
        and board_pick_detailed_evidence_ready
    )
    scripted_pick_place_training_ready = (
        gym_training_ready and reviewed_model_backed_board_pick_place
    )
    rollout_policy_training_authority_ready = (
        training_rollouts.get("ready_for_policy_training") is True
        and training_rollouts.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
        and training_rollouts.get("status") == "ok"
        and (
            training_rollouts.get("training_authority_status")
            == "reviewed_policy_training_rollouts_ready"
        )
        and training_rollouts.get("rollout_use") == "policy_training"
        and (
            training_rollouts.get("observed_evidence_is_policy_training_authority")
            is True
        )
        and not training_rollouts.get("serious_policy_training_blockers")
    )
    rollout_automation_ready = training_rollouts.get("status") == "ok"
    rollout_training_ready = (
        scripted_pick_place_training_ready and rollout_policy_training_authority_ready
    )

    stage_specs = [
        {
            "gate_id": "reviewed_model_authority",
            "title": "Reviewed SO-101 model authority",
            "required_state": "reviewed_model_authority_ready",
            "training_ready": reviewed_authority_ready,
            "automation_evidence_ready": reviewed_authority_ready,
            "next_action_ids": (
                reviewed_authority_gate.get("next_required_action_ids")
                or reviewed_authority_gate.get("blocker_packet_next_action_ids")
                or reviewed_authority_gate.get("blockers")
                or ["supply_reviewed_so101_model_bundle_manifest"]
            ),
            "evidence_artifact_paths": [
                _summary_path(reviewed_authority_gate),
            ],
        },
        {
            "gate_id": "mujoco_scene_validity",
            "title": "MuJoCo scene validity with reviewed handoff",
            "required_state": "reviewed_mujoco_downstream_handoff_ready",
            "training_ready": mujoco_scene_training_ready,
            "automation_evidence_ready": (
                mujoco_scene_automation_ready
                or fixture_downstream_handoff_ready
            ),
            "next_action_ids": [
                *downstream_handoff_contract.get("next_action_ids", []),
                "make_reviewed_mujoco_downstream_handoff_ready",
                "load_reviewed_model_in_mujoco",
                "prove_physical_reviewed_model_motion",
            ],
            "evidence_artifact_paths": [
                _summary_path(reviewed_authority_gate),
                _summary_path(reviewed_mujoco_bundle),
                _summary_path(mujoco_scene),
            ],
        },
        {
            "gate_id": "gymnasium_task_wiring",
            "title": "Gymnasium SO-101 chess task wiring",
            "required_state": "reviewed_model_backed_gymnasium_task_wiring",
            "training_ready": gym_training_ready,
            "automation_evidence_ready": gym_automation_ready,
            "next_action_ids": ["wire_reviewed_so101_chess_gymnasium_task"],
            "evidence_artifact_paths": [
                _summary_path(chess_env),
            ],
        },
        {
            "gate_id": "scripted_contact_grasp_pick_place",
            "title": "Scripted contact, grasp, pick, place, and release evidence",
            "required_state": "reviewed_model_backed_board_source_pick_place",
            "training_ready": scripted_pick_place_training_ready,
            "automation_evidence_ready": scripted_pick_place_automation_ready,
            "next_action_ids": [
                "repeat_board_source_pick_place_with_reviewed_model_backed_ik"
            ],
            "evidence_artifact_paths": [
                _summary_path(contact_probe),
                _summary_path(grasp_probe),
                _summary_path(board_pick),
            ],
        },
        {
            "gate_id": "focused_training_rollouts",
            "title": "Focused training rollouts",
            "required_state": "policy_training_rollouts_ready",
            "training_ready": rollout_training_ready,
            "automation_evidence_ready": rollout_automation_ready,
            "next_action_ids": (
                training_rollouts.get("serious_policy_training_blockers")
                or ["run_focused_training_rollouts_after_reviewed_pick_place"]
            ),
            "evidence_artifact_paths": [
                _summary_path(training_rollouts),
            ],
        },
    ]

    stages: list[dict[str, Any]] = []
    prior_ready = True
    for priority, spec in enumerate(stage_specs, start=1):
        training_ready = bool(spec["training_ready"])
        automation_ready = bool(spec["automation_evidence_ready"])
        if training_ready:
            status = "ready"
        elif not prior_ready:
            status = "blocked_by_prior_requirements"
        elif automation_ready:
            status = "development_evidence_only"
        else:
            status = "action_required"
        next_action_ids = unique_string_values(spec.get("next_action_ids") or [])
        development_evidence_only_not_training_truth = (
            automation_ready and not training_ready
        )
        stages.append(
            {
                "priority": priority,
                "gate_id": spec["gate_id"],
                "title": spec["title"],
                "required_state": spec["required_state"],
                "status": status,
                "training_ready": training_ready,
                "automation_evidence_ready": automation_ready,
                "automation_evidence_is_training_authority": training_ready,
                "development_evidence_only_not_training_truth": (
                    development_evidence_only_not_training_truth
                ),
                "training_blocker_action_ids": (
                    [] if training_ready else next_action_ids
                ),
                "blocked_by_prior_gate_ids": [
                    stage["gate_id"] for stage in stages if stage["training_ready"] is False
                ]
                if status == "blocked_by_prior_requirements"
                else [],
                "next_action_ids": [] if training_ready else next_action_ids,
                "evidence_artifact_paths": [
                    path
                    for path in spec.get("evidence_artifact_paths", [])
                    if isinstance(path, str) and path
                ],
            }
        )
        prior_ready = prior_ready and training_ready

    next_stage = next(
        (
            stage
            for stage in stages
            if stage.get("status") in {"action_required", "development_evidence_only"}
        ),
        None,
    )
    blocked_stage_ids = [
        stage["gate_id"]
        for stage in stages
        if stage.get("status") == "blocked_by_prior_requirements"
    ]
    development_only_stage_ids = [
        stage["gate_id"]
        for stage in stages
        if stage.get("status") == "development_evidence_only"
    ]
    return {
        "priority_gate_queue": stages,
        "priority_gate_order": list(SO101_TRAINING_PRIORITY_STAGE_IDS),
        "next_priority_gate_id": next_stage.get("gate_id") if next_stage else None,
        "next_priority_action_ids": (
            next_stage.get("next_action_ids") if next_stage else []
        ),
        "blocked_by_prior_gate_ids": blocked_stage_ids,
        "development_evidence_only_gate_ids": development_only_stage_ids,
        "priority_gate_training_blocker_action_ids_by_gate_id": {
            stage["gate_id"]: stage["training_blocker_action_ids"]
            for stage in stages
        },
        "priority_gate_development_evidence_only_not_training_truth_by_gate_id": {
            stage["gate_id"]: stage["development_evidence_only_not_training_truth"]
            for stage in stages
        },
    }


def so101_training_readiness_gate_section(
    reviewed_authority_gate: dict[str, Any],
    board_pick: dict[str, Any],
    training_rollouts: dict[str, Any],
    *,
    reviewed_mujoco_bundle: dict[str, Any] | None = None,
    mujoco_scene: dict[str, Any] | None = None,
    chess_env: dict[str, Any] | None = None,
    contact_probe: dict[str, Any] | None = None,
    grasp_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reviewed_mujoco_bundle = (
        reviewed_mujoco_bundle if isinstance(reviewed_mujoco_bundle, dict) else {}
    )
    reviewed_authority_ready = reviewed_authority_gate.get("ready") is True
    reviewed_model_physical_motion_checked = (
        reviewed_authority_gate.get("physical_reviewed_model_motion_checked") is True
    )
    downstream_handoff_contract = (
        so101_reviewed_mujoco_downstream_handoff_contract(reviewed_mujoco_bundle)
    )
    reviewed_mujoco_downstream_handoff_ready = (
        downstream_handoff_contract.get("ready") is True
    )
    reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority = (
        downstream_handoff_contract.get(
            "fixture_handoff_ready_not_physical_so101_authority"
        )
        is True
    )
    reviewed_mujoco_downstream_handoff_physical_truth_claimed = (
        downstream_handoff_contract.get("physical_truth_claimed") is True
    )
    board_pick_reviewed_model_authority_ready = (
        board_pick.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
    )
    board_pick_detailed_evidence_ready = so101_board_pick_detailed_evidence_ready(
        board_pick
    )
    board_pick_authority_contract = so101_board_pick_authority_contract(
        board_pick,
        detailed_evidence_ready=board_pick_detailed_evidence_ready,
    )
    reviewed_model_backed_board_pick_place = (
        board_pick_authority_contract.get("ready") is True
    )
    rollout_policy_training_authority_ready = (
        training_rollouts.get("ready_for_policy_training") is True
        and training_rollouts.get("model_authority") == REVIEWED_SO101_MODEL_AUTHORITY
        and training_rollouts.get("status") == "ok"
        and (
            training_rollouts.get("training_authority_status")
            == "reviewed_policy_training_rollouts_ready"
        )
        and training_rollouts.get("rollout_use") == "policy_training"
        and (
            training_rollouts.get("observed_evidence_is_policy_training_authority")
            is True
        )
        and not training_rollouts.get("serious_policy_training_blockers")
    )
    priority_queue = so101_training_priority_gate_queue(
        reviewed_authority_gate,
        board_pick,
        training_rollouts,
        reviewed_mujoco_bundle=reviewed_mujoco_bundle,
        mujoco_scene=mujoco_scene,
        chess_env=chess_env,
        contact_probe=contact_probe,
        grasp_probe=grasp_probe,
    )
    priority_gate_queue_ready = all(
        stage.get("training_ready") is True
        for stage in priority_queue.get("priority_gate_queue", [])
    )
    blockers = unique_string_values(
        [
            *(
                []
                if downstream_handoff_contract.get("contract_ok") is True
                else downstream_handoff_contract.get("blockers", [])
            ),
            *(
                []
                if reviewed_authority_ready
                else reviewed_authority_gate.get("blockers", [])
            ),
            *(
                []
                if reviewed_model_backed_board_pick_place
                else ["reviewed_model_backed_board_source_pick_place"]
            ),
            *(
                []
                if rollout_policy_training_authority_ready
                else (
                    training_rollouts.get("serious_policy_training_blockers")
                    or ["reviewed_model_backed_training_rollouts"]
                )
            ),
            *(
                []
                if priority_gate_queue_ready
                else priority_queue.get("next_priority_action_ids", [])
            ),
        ]
    )
    ready = (
        reviewed_authority_ready
        and reviewed_model_backed_board_pick_place
        and rollout_policy_training_authority_ready
        and priority_gate_queue_ready
    )
    return {
        "status": "serious_training_ready" if ready else "serious_training_blocked",
        "ready": ready,
        "reviewed_model_authority_ready": reviewed_authority_ready,
        "reviewed_model_authority_status": reviewed_authority_gate.get("status"),
        "reviewed_model_physical_motion_checked": reviewed_model_physical_motion_checked,
        "reviewed_mujoco_downstream_handoff_status": downstream_handoff_contract.get(
            "status"
        ),
        "reviewed_mujoco_downstream_handoff_contract_status": (
            downstream_handoff_contract.get("contract_status")
        ),
        "reviewed_mujoco_downstream_handoff_contract_ok": (
            downstream_handoff_contract.get("contract_ok")
        ),
        "reviewed_mujoco_downstream_handoff_raw_ready": (
            downstream_handoff_contract.get("raw_ready")
        ),
        "reviewed_mujoco_downstream_handoff_ready": (
            reviewed_mujoco_downstream_handoff_ready
        ),
        "reviewed_mujoco_downstream_handoff_schema": (
            downstream_handoff_contract.get("schema")
        ),
        "reviewed_mujoco_downstream_handoff_expected_schema": (
            downstream_handoff_contract.get("expected_schema")
        ),
        "reviewed_mujoco_downstream_handoff_model_authority": (
            downstream_handoff_contract.get("model_authority")
        ),
        "reviewed_mujoco_downstream_handoff_observed_evidence_is_authority": (
            downstream_handoff_contract.get("observed_evidence_is_authority")
        ),
        "reviewed_mujoco_downstream_handoff_physical_truth_claimed": (
            reviewed_mujoco_downstream_handoff_physical_truth_claimed
        ),
        "reviewed_mujoco_downstream_handoff_development_fixture_evidence_not_physical_so101_truth": (
            downstream_handoff_contract.get(
                "development_fixture_evidence_not_physical_so101_truth"
            )
        ),
        "reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority": (
            reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority
        ),
        "reviewed_mujoco_downstream_handoff_raw_fixture_ready_not_physical_so101_authority": (
            downstream_handoff_contract.get(
                "raw_fixture_handoff_ready_not_physical_so101_authority"
            )
        ),
        "reviewed_mujoco_downstream_handoff_motion_authority_status": (
            downstream_handoff_contract.get("motion_authority_status")
        ),
        "reviewed_mujoco_downstream_handoff_physical_motion_checked": (
            downstream_handoff_contract.get("physical_motion_checked")
        ),
        "reviewed_mujoco_downstream_handoff_hardware_free_fixture_motion_checked": (
            downstream_handoff_contract.get("hardware_free_fixture_motion_checked")
        ),
        "reviewed_mujoco_downstream_handoff_reviewed_model_motion_checked": (
            downstream_handoff_contract.get("reviewed_model_motion_checked")
        ),
        "reviewed_mujoco_downstream_handoff_physical_so101_model_authority_ready": (
            downstream_handoff_contract.get("physical_so101_model_authority_ready")
        ),
        "reviewed_mujoco_downstream_handoff_motion_evidence_not_physical_so101_authority": (
            downstream_handoff_contract.get(
                "motion_evidence_not_physical_so101_authority"
            )
        ),
        "reviewed_mujoco_downstream_handoff_joint_limit_enablement_ok": (
            downstream_handoff_contract.get("joint_limit_enablement_ok")
        ),
        "reviewed_mujoco_downstream_handoff_joint_limit_enablement_status": (
            downstream_handoff_contract.get("joint_limit_enablement_status")
        ),
        "reviewed_mujoco_downstream_handoff_missing_limited_joints": (
            downstream_handoff_contract.get("missing_limited_joints")
        ),
        "reviewed_mujoco_downstream_handoff_required_limited_joints": (
            downstream_handoff_contract.get("required_limited_joints")
        ),
        "reviewed_mujoco_downstream_handoff_item_count": (
            downstream_handoff_contract.get("item_count")
        ),
        "reviewed_mujoco_downstream_handoff_item_ids": (
            downstream_handoff_contract.get("item_ids")
        ),
        "reviewed_mujoco_downstream_handoff_missing_item_ids": (
            downstream_handoff_contract.get("missing_item_ids")
        ),
        "reviewed_mujoco_downstream_handoff_missing_inputs": (
            downstream_handoff_contract.get("missing_inputs")
        ),
        "reviewed_mujoco_downstream_handoff_pending_action_ids": (
            downstream_handoff_contract.get("pending_action_ids")
        ),
        "reviewed_mujoco_downstream_handoff_ready_has_open_work": (
            downstream_handoff_contract.get("ready_handoff_has_open_work")
        ),
        "reviewed_mujoco_downstream_handoff_contract_blockers": (
            downstream_handoff_contract.get("blockers")
        ),
        "reviewed_model_backed_board_source_pick_place": reviewed_model_backed_board_pick_place,
        "board_pick_status": board_pick.get("status"),
        "board_pick_model_authority": board_pick.get("model_authority"),
        "board_pick_reviewed_model_authority_ready": board_pick_reviewed_model_authority_ready,
        "board_pick_authority_status": board_pick_authority_contract.get("status"),
        "board_pick_authority_blockers": board_pick_authority_contract.get("blockers"),
        "board_pick_detailed_evidence_ready": board_pick_detailed_evidence_ready,
        "board_pick_observed_evidence_is_physical_so101_authority": board_pick.get(
            "observed_evidence_is_physical_so101_authority"
        ),
        "board_pick_observed_evidence_is_policy_training_authority": board_pick.get(
            "observed_evidence_is_policy_training_authority"
        ),
        "board_pick_ready_for_policy_training": board_pick.get(
            "ready_for_policy_training"
        ),
        "board_pick_physical_truth_claimed": board_pick_authority_contract.get(
            "physical_truth_claimed"
        ),
        "board_pick_policy_training_claimed": board_pick_authority_contract.get(
            "policy_training_claimed"
        ),
        "board_pick_policy_authority_claimed": board_pick_authority_contract.get(
            "policy_authority_claimed"
        ),
        "board_pick_ready_for_model_backed_ik": board_pick.get("ready_for_model_backed_ik"),
        "board_pick_source_pick_started_at_source": board_pick.get(
            "source_pick_started_at_source"
        ),
        "board_pick_close_two_finger_contact_observed": board_pick.get(
            "close_two_finger_contact_observed"
        ),
        "board_pick_lift_verified": board_pick.get("lift_verified"),
        "board_pick_board_contact_cleared_during_lift": board_pick.get(
            "board_contact_cleared_during_lift"
        ),
        "board_pick_transfer_verified": board_pick.get("transfer_verified"),
        "board_pick_place_without_manual_piece_pose_verified": board_pick.get(
            "place_without_manual_piece_pose_verified"
        ),
        "board_pick_release_contact_cleared_after_retreat": board_pick.get(
            "release_contact_cleared_after_retreat"
        ),
        "board_pick_final_board_contact_observed": board_pick.get(
            "final_board_contact_observed"
        ),
        "board_pick_final_target_xy_error_m": board_pick.get("final_target_xy_error_m"),
        "board_pick_target_xy_tolerance_m": board_pick.get("target_xy_tolerance_m"),
        "board_pick_final_place_z_error_m": board_pick.get("final_place_z_error_m"),
        "board_pick_place_z_tolerance_m": board_pick.get("place_z_tolerance_m"),
        "board_pick_final_place_z_within_tolerance": (
            _json_number(board_pick.get("final_place_z_error_m")) is not None
            and _json_number(board_pick.get("place_z_tolerance_m")) is not None
            and _json_number(board_pick.get("final_place_z_error_m"))
            <= _json_number(board_pick.get("place_z_tolerance_m"))
        ),
        "board_pick_phase_evidence_ready": so101_board_pick_phase_evidence_ready(
            board_pick
        ),
        "board_pick_stage_sequence_ready": so101_board_pick_stage_sequence_ready(
            board_pick
        ),
        "board_pick_phase_ids": board_pick.get("pick_place_phase_ids"),
        "board_pick_failed_phase_ids": board_pick.get("pick_place_failed_phase_ids"),
        "board_pick_phase_count": board_pick.get("pick_place_phase_count"),
        "board_pick_all_required_phases_verified": board_pick.get(
            "pick_place_all_required_phases_verified"
        ),
        "board_pick_phase_evidence_count": len(board_pick.get("pick_place_phase_evidence"))
        if isinstance(board_pick.get("pick_place_phase_evidence"), list)
        else None,
        "board_pick_required_stage_sequence": board_pick.get("required_stage_sequence"),
        "board_pick_observed_stage_sequence": board_pick.get("observed_stage_sequence"),
        "board_pick_missing_stage_ids": board_pick.get("missing_stage_ids"),
        "board_pick_unexpected_stage_ids": board_pick.get("unexpected_stage_ids"),
        "board_pick_stage_sequence_order_ok": board_pick.get("stage_sequence_order_ok"),
        "board_pick_stage_sequence_contract_ok": board_pick.get(
            "stage_sequence_contract_ok"
        ),
        "board_pick_stage_sequence_contract_errors": board_pick.get(
            "stage_sequence_contract_errors"
        ),
        "board_pick_manual_piece_pose_after_reset_stage_ids": board_pick.get(
            "manual_piece_pose_after_reset_stage_ids"
        ),
        "board_pick_robot_pose_seeded_for_source_fixture": board_pick.get(
            "robot_pose_seeded_for_source_fixture"
        ),
        "board_pick_manual_piece_pose_used_after_reset": board_pick.get(
            "manual_piece_pose_used_after_reset"
        ),
        "rollout_ready_for_policy_training": training_rollouts.get(
            "ready_for_policy_training"
        ),
        "rollout_training_authority_status": training_rollouts.get(
            "training_authority_status"
        ),
        "rollout_status": training_rollouts.get("status"),
        "rollout_model_authority": training_rollouts.get("model_authority"),
        "rollout_observed_evidence_is_policy_training_authority": training_rollouts.get(
            "observed_evidence_is_policy_training_authority"
        ),
        "rollout_policy_training_authority_ready": rollout_policy_training_authority_ready,
        "rollout_use": training_rollouts.get("rollout_use"),
        "rollout_serious_policy_training_blockers": training_rollouts.get(
            "serious_policy_training_blockers"
        ),
        "development_fixture_evidence_not_policy_training_truth": (
            not ready
            or not board_pick_reviewed_model_authority_ready
            or not rollout_policy_training_authority_ready
        ),
        "blockers": blockers,
        "blocker_count": len(blockers),
        **priority_queue,
        "reviewed_model_authority_gate_summary_path": reviewed_authority_gate.get(
            "summary_path"
        ),
        "reviewed_mujoco_bundle_summary_path": reviewed_mujoco_bundle.get(
            "summary_path"
        ),
        "board_pick_summary_path": board_pick.get("summary_path"),
        "training_rollouts_summary_path": training_rollouts.get("summary_path"),
        "notes": [
            "This gate is false until the reviewed model-authority gate is ready, the reviewed MuJoCo downstream handoff is ready, board-source pick/place is repeated with reviewed model-backed IK, and policy rollout evidence is no longer development-scaffold-only.",
            "priority_gate_queue preserves the MuJoCo-first gate order: reviewed model authority, reviewed MuJoCo handoff and scene validity, Gymnasium wiring, scripted contact/grasp/pick/place, then focused training rollouts.",
            "Development rollout JSONL remains useful for debugging and narrow imitation-curriculum tests, not serious policy training truth.",
        ],
    }


def write_so101_training_readiness_gate_artifacts(
    output_dir: Path,
    gate: dict[str, Any],
) -> dict[str, Any]:
    gate_dir = output_dir / SO101_TRAINING_READINESS_GATE_DIR_NAME
    summary_path = gate_dir / SO101_TRAINING_READINESS_GATE_SUMMARY_NAME
    checklist_path = gate_dir / SO101_TRAINING_READINESS_GATE_CHECKLIST_NAME
    priority_queue_path = gate_dir / SO101_TRAINING_READINESS_GATE_PRIORITY_QUEUE_NAME
    readme_path = gate_dir / SO101_TRAINING_READINESS_GATE_README_NAME
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(checklist_path),
        "priority_gate_queue_csv": str(priority_queue_path),
        "readme_md": str(readme_path),
    }
    payload = {
        "schema": SO101_TRAINING_READINESS_GATE_SCHEMA,
        **gate,
        "ok": bool(gate.get("ready")),
        "summary_path": str(summary_path),
        "artifact_dir": str(gate_dir),
        "artifacts": artifacts,
    }
    checklist_rows = [
        {
            "requirement_id": "reviewed_model_authority_ready",
            "category": "reviewed_model_authority",
            "status": "ok"
            if gate.get("reviewed_model_authority_ready") is True
            else "action_required",
            "observed_value": markdown_bool(gate.get("reviewed_model_authority_ready")),
            "expected_value": "true",
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "Serious policy training must wait for reviewed SO-101 model authority.",
        },
        {
            "requirement_id": "reviewed_mujoco_downstream_handoff_schema_current",
            "category": "mujoco_scene_validity",
            "status": "ok"
            if gate.get("reviewed_mujoco_downstream_handoff_schema")
            == gate.get("reviewed_mujoco_downstream_handoff_expected_schema")
            else "action_required",
            "observed_value": str(
                gate.get("reviewed_mujoco_downstream_handoff_schema")
            ),
            "expected_value": str(
                gate.get("reviewed_mujoco_downstream_handoff_expected_schema")
            ),
            "blockers": "; ".join(
                gate.get("reviewed_mujoco_downstream_handoff_contract_blockers") or []
            ),
            "notes": "The aggregate training gate fails closed on stale or missing reviewed MuJoCo handoff schemas.",
        },
        {
            "requirement_id": "reviewed_mujoco_downstream_handoff_ready",
            "category": "mujoco_scene_validity",
            "status": "ok"
            if gate.get("reviewed_mujoco_downstream_handoff_ready") is True
            else "action_required",
            "observed_value": markdown_bool(
                gate.get("reviewed_mujoco_downstream_handoff_ready")
            ),
            "expected_value": "true",
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "Scene, Gymnasium, pick/place, and rollout gates must consume a contract-valid reviewed MuJoCo handoff, not a fixture or malformed raw-ready handoff.",
        },
        {
            "requirement_id": "reviewed_model_backed_board_pick_place",
            "category": "scripted_pick_place_evidence",
            "status": "ok"
            if gate.get("reviewed_model_backed_board_source_pick_place") is True
            else "action_required",
            "observed_value": markdown_bool(
                gate.get("reviewed_model_backed_board_source_pick_place")
            ),
            "expected_value": "true",
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "Development seeded board-source pick/place does not close the reviewed model-backed pick/place gate.",
        },
        {
            "requirement_id": "board_pick_authority_contract",
            "category": "scripted_pick_place_evidence",
            "status": "ok"
            if gate.get("board_pick_authority_status")
            == "reviewed_model_backed_board_source_pick_place_verified"
            else "action_required",
            "observed_value": str(gate.get("board_pick_authority_status")),
            "expected_value": "reviewed_model_backed_board_source_pick_place_verified",
            "blockers": "; ".join(gate.get("board_pick_authority_blockers") or []),
            "notes": "This explains why detailed board-pick evidence is still not reviewed-model-backed pick/place authority.",
        },
        {
            "requirement_id": "board_pick_authority_overclaim_boundary",
            "category": "authority_boundary",
            "status": "ok"
            if gate.get("board_pick_physical_truth_claimed") is False
            and gate.get("board_pick_policy_training_claimed") is False
            and gate.get("board_pick_policy_authority_claimed") is False
            else "action_required",
            "observed_value": json.dumps(
                {
                    "physical_truth_claimed": gate.get(
                        "board_pick_physical_truth_claimed"
                    ),
                    "policy_training_claimed": gate.get(
                        "board_pick_policy_training_claimed"
                    ),
                    "policy_authority_claimed": gate.get(
                        "board_pick_policy_authority_claimed"
                    ),
                },
                sort_keys=True,
            ),
            "expected_value": "all false",
            "blockers": "; ".join(gate.get("board_pick_authority_blockers") or []),
            "notes": "Board-source pick/place evidence cannot independently claim physical SO-101 truth or policy-training authority.",
        },
        {
            "requirement_id": "policy_training_rollouts_ready",
            "category": "training_rollouts",
            "status": "ok"
            if gate.get("rollout_policy_training_authority_ready") is True
            else "action_required",
            "observed_value": markdown_bool(
                gate.get("rollout_policy_training_authority_ready")
            ),
            "expected_value": "true with reviewed SO-101 model authority",
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "Development JSONL rollouts or rollouts without reviewed SO-101 model authority are debug/imitation-curriculum evidence only.",
        },
        {
            "requirement_id": "development_fixture_caveat",
            "category": "authority_boundary",
            "status": "ok"
            if gate.get("development_fixture_evidence_not_policy_training_truth") is True
            else "review_required",
            "observed_value": markdown_bool(
                gate.get("development_fixture_evidence_not_policy_training_truth")
            ),
            "expected_value": "true while training is blocked or fixture-only evidence exists",
            "blockers": "; ".join(gate.get("blockers", [])),
            "notes": "This caveat prevents treating scaffold rollouts as serious training truth.",
        },
        {
            "requirement_id": "priority_gate_queue",
            "category": "automation_priority",
            "status": "ok"
            if gate.get("priority_gate_order") == list(SO101_TRAINING_PRIORITY_STAGE_IDS)
            and isinstance(gate.get("priority_gate_queue"), list)
            and len(gate.get("priority_gate_queue")) == len(SO101_TRAINING_PRIORITY_STAGE_IDS)
            else "review_required",
            "observed_value": markdown_list_value(gate.get("priority_gate_order")),
            "expected_value": markdown_list_value(SO101_TRAINING_PRIORITY_STAGE_IDS),
            "blockers": "; ".join(gate.get("next_priority_action_ids") or []),
            "notes": "The gate queue keeps missing work ordered before serious training rollouts.",
        },
    ]
    gate_dir.mkdir(parents=True, exist_ok=True)
    write_json(summary_path, payload)
    fieldnames = (
        "requirement_id",
        "category",
        "status",
        "observed_value",
        "expected_value",
        "blockers",
        "notes",
    )
    with checklist_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in checklist_rows:
            writer.writerow(row)

    priority_fieldnames = (
        "priority",
        "gate_id",
        "title",
        "required_state",
        "status",
        "training_ready",
        "automation_evidence_ready",
        "automation_evidence_is_training_authority",
        "development_evidence_only_not_training_truth",
        "training_blocker_action_ids",
        "blocked_by_prior_gate_ids",
        "next_action_ids",
        "evidence_artifact_paths",
    )
    with priority_queue_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=priority_fieldnames)
        writer.writeheader()
        for stage in gate.get("priority_gate_queue", []):
            if isinstance(stage, dict):
                writer.writerow(
                    {
                        field: csv_cell(stage.get(field))
                        for field in priority_fieldnames
                    }
                )

    blocker_lines = (
        [f"- `{blocker}`" for blocker in gate.get("blockers", [])]
        if gate.get("blockers")
        else ["- none"]
    )
    readme_path.write_text(
        "\n".join(
            [
                "# SO-101 Training Readiness Gate",
                "",
                f"- Status: `{gate.get('status')}`",
                f"- Ready: `{markdown_bool(gate.get('ready'))}`",
                "- Reviewed model authority ready: "
                f"`{markdown_bool(gate.get('reviewed_model_authority_ready'))}`",
                "- Reviewed MuJoCo downstream handoff status: "
                f"`{gate.get('reviewed_mujoco_downstream_handoff_status')}`",
                "- Reviewed MuJoCo downstream handoff contract: "
                f"`{gate.get('reviewed_mujoco_downstream_handoff_contract_status')}` / "
                f"`{markdown_bool(gate.get('reviewed_mujoco_downstream_handoff_contract_ok'))}`",
                "- Reviewed MuJoCo downstream handoff schema: "
                f"`{gate.get('reviewed_mujoco_downstream_handoff_schema')}` "
                f"(expected `{gate.get('reviewed_mujoco_downstream_handoff_expected_schema')}`)",
                "- Reviewed MuJoCo downstream handoff raw ready: "
                f"`{markdown_bool(gate.get('reviewed_mujoco_downstream_handoff_raw_ready'))}`",
                "- Reviewed MuJoCo downstream handoff ready: "
                f"`{markdown_bool(gate.get('reviewed_mujoco_downstream_handoff_ready'))}`",
                "- Fixture MuJoCo handoff is not physical SO-101 authority: "
                f"`{markdown_bool(gate.get('reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority'))}`",
                "- Reviewed MuJoCo downstream handoff missing items: "
                f"`{markdown_list_value(gate.get('reviewed_mujoco_downstream_handoff_missing_item_ids'))}`",
                "- Reviewed model-backed board-source pick/place: "
                f"`{markdown_bool(gate.get('reviewed_model_backed_board_source_pick_place'))}`",
                "- Board-pick reviewed model authority ready: "
                f"`{markdown_bool(gate.get('board_pick_reviewed_model_authority_ready'))}`",
                "- Board-pick authority status: "
                f"`{gate.get('board_pick_authority_status')}`",
                "- Board-pick authority blockers: "
                f"`{markdown_list_value(gate.get('board_pick_authority_blockers'))}`",
                "- Board-pick detailed evidence ready: "
                f"`{markdown_bool(gate.get('board_pick_detailed_evidence_ready'))}`",
                "- Board-pick phase evidence ready: "
                f"`{markdown_bool(gate.get('board_pick_phase_evidence_ready'))}`",
                "- Board-pick phase IDs: "
                f"`{markdown_list_value(gate.get('board_pick_phase_ids'))}`",
                "- Board-pick failed phase IDs: "
                f"`{markdown_list_value(gate.get('board_pick_failed_phase_ids'))}`",
                "- Board-pick final z error/tolerance: "
                f"`{gate.get('board_pick_final_place_z_error_m')}` / "
                f"`{gate.get('board_pick_place_z_tolerance_m')}`",
                "- Rollout ready for policy training: "
                f"`{markdown_bool(gate.get('rollout_ready_for_policy_training'))}`",
                "- Rollout policy-training authority ready: "
                f"`{markdown_bool(gate.get('rollout_policy_training_authority_ready'))}`",
                "- Development fixture evidence is not policy training truth: "
                f"`{markdown_bool(gate.get('development_fixture_evidence_not_policy_training_truth'))}`",
                "- Next priority gate: "
                f"`{gate.get('next_priority_gate_id') or 'none'}`",
                "- Next priority actions: "
                f"`{markdown_list_value(gate.get('next_priority_action_ids'))}`",
                "- Priority gate order: "
                f"`{markdown_list_value(gate.get('priority_gate_order'))}`",
                f"- Priority gate queue rows: `{priority_queue_path}`",
                "",
                "## Blockers",
                "",
                *blocker_lines,
                "",
                "## Evidence Sources",
                "",
                f"- Reviewed model authority gate: `{gate.get('reviewed_model_authority_gate_summary_path')}`",
                f"- Reviewed MuJoCo downstream handoff: `{gate.get('reviewed_mujoco_bundle_summary_path')}`",
                f"- Board-source pick/place: `{gate.get('board_pick_summary_path')}`",
                f"- Training rollouts: `{gate.get('training_rollouts_summary_path')}`",
                "",
                "This artifact is a hardware-free readiness summary. It is ready only when reviewed authority, reviewed model-backed board-source pick/place, and policy-ready rollout evidence are all true.",
                "",
            ]
        )
    )
    return payload


def visual_review_section(visual_review: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    contact_sheets = visual_review.get("contact_sheets")
    contact_sheets = contact_sheets if isinstance(contact_sheets, list) else []
    contact_sheet_paths = visual_review.get("contact_sheet_paths")
    contact_sheet_paths = contact_sheet_paths if isinstance(contact_sheet_paths, dict) else {}
    frame_sequences = visual_review.get("frame_sequences")
    frame_sequences = frame_sequences if isinstance(frame_sequences, list) else []
    distance_metrics = visual_review.get("distance_metrics")
    distance_metrics = distance_metrics if isinstance(distance_metrics, dict) else {}
    perceived_depth_comparison = visual_review.get("perceived_depth_comparison")
    perceived_depth_comparison = (
        perceived_depth_comparison if isinstance(perceived_depth_comparison, dict) else {}
    )
    pnp_residual_diagnostics = visual_review.get("pnp_residual_diagnostics")
    pnp_residual_diagnostics = (
        pnp_residual_diagnostics if isinstance(pnp_residual_diagnostics, dict) else {}
    )
    metadata_native_depth_view = visual_review.get("metadata_native_depth_view")
    metadata_native_depth_view = (
        metadata_native_depth_view if isinstance(metadata_native_depth_view, dict) else {}
    )
    depth_distance_scorecard = visual_review.get("depth_distance_scorecard")
    depth_distance_scorecard = (
        depth_distance_scorecard if isinstance(depth_distance_scorecard, dict) else {}
    )
    recordings = visual_review.get("recordings")
    recordings = recordings if isinstance(recordings, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(visual_review.get("ok", False)),
        "status": visual_review.get("status"),
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet_paths": {
            str(key): str(value)
            for key, value in sorted(contact_sheet_paths.items())
            if isinstance(value, str)
        },
        "contact_sheets": contact_sheets,
        "frame_sequences": frame_sequences,
        "distance_metrics": distance_metrics,
        "perceived_depth_comparison": perceived_depth_comparison,
        "pnp_residual_diagnostics": pnp_residual_diagnostics,
        "metadata_native_depth_view": metadata_native_depth_view,
        "depth_distance_scorecard": depth_distance_scorecard,
        "app_entrypoint_frame": visual_review.get("app_entrypoint_frame"),
        "recording": visual_review.get("recording"),
        "recordings": recordings,
        "hardware_skipped": visual_review.get("hardware_skipped"),
        "gui_skipped": visual_review.get("gui_skipped"),
        "openai_skipped": visual_review.get("openai_skipped"),
        "notes": visual_review.get("notes"),
    }


def reference_capture_checklist_section(checklist: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    checklist = checklist if isinstance(checklist, dict) else {}
    counts = checklist.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    media_summary = checklist.get("media_summary")
    media_summary = media_summary if isinstance(media_summary, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(checklist.get("ok", False)),
        "status": checklist.get("status"),
        "markdown_path": checklist.get("markdown_path"),
        "represented_media_count": media_summary.get("represented_media_count"),
        "represented_media": media_summary.get("represented_media"),
        "video_count": media_summary.get("video_count"),
        "requirement_count": counts.get("requirement_count"),
        "represented_requirement_count": counts.get("represented_requirement_count"),
        "partial_requirement_count": counts.get("partial_requirement_count"),
        "missing_requirement_count": counts.get("missing_requirement_count"),
        "action_item_count": counts.get("action_item_count"),
        "hardware_skipped": checklist.get("hardware_skipped"),
        "gui_skipped": checklist.get("gui_skipped"),
        "real_camera_skipped": checklist.get("real_camera_skipped"),
        "openai_skipped": checklist.get("openai_skipped"),
    }


def real_projection_intake_section(intake: dict[str, Any] | None, summary_path: Path) -> dict[str, Any]:
    intake = intake if isinstance(intake, dict) else {}
    paths = intake.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    residual_artifacts = intake.get("residual_artifacts")
    residual_artifacts = residual_artifacts if isinstance(residual_artifacts, dict) else {}
    return {
        "summary_path": str(summary_path),
        "output_dir": str(summary_path.parent),
        "ok": bool(intake.get("ok", False)),
        "status": intake.get("status"),
        "paths": paths,
        "real_reference_media_count": intake.get("real_reference_media_count"),
        "comparable_count": intake.get("comparable_count"),
        "projection_comparable_count": intake.get("projection_comparable_count"),
        "depth_comparable_count": intake.get("depth_comparable_count"),
        "sidecar_valid_count": intake.get("sidecar_valid_count"),
        "sidecar_invalid_count": intake.get("sidecar_invalid_count"),
        "sidecar_missing_count": intake.get("sidecar_missing_count"),
        "missing_input_count": intake.get("missing_input_count"),
        "missing_inputs": intake.get("missing_inputs"),
        "next_capture_requirements": intake.get("next_capture_requirements"),
        "sim_metadata_native_depth_view_path": intake.get("sim_metadata_native_depth_view_path"),
        "sim_metadata_native_depth_view_png_path": intake.get("sim_metadata_native_depth_view_png_path"),
        "sim_metadata_native_depth_view_csv_path": intake.get("sim_metadata_native_depth_view_csv_path"),
        "sim_expected_projected_point_count": intake.get("sim_expected_projected_point_count"),
        "residual_artifacts": residual_artifacts,
        "records": intake.get("records"),
        "hardware_skipped": intake.get("hardware_skipped"),
        "gui_skipped": intake.get("gui_skipped"),
        "real_camera_capture_skipped": intake.get("real_camera_capture_skipped"),
        "openai_skipped": intake.get("openai_skipped"),
    }


def evidence_bundle_section(bundle: dict[str, Any] | None, bundle_dir: Path) -> dict[str, Any]:
    bundle = bundle if isinstance(bundle, dict) else {}
    output_md = bundle.get("output_md")
    output_json = bundle.get("output_json")
    return {
        "summary_path": str(bundle_dir / EVIDENCE_BUNDLE_JSON_NAME),
        "markdown_path": str(bundle_dir / EVIDENCE_BUNDLE_MD_NAME),
        "output_dir": str(bundle_dir),
        "ok": bool(bundle.get("ok", False)),
        "status": bundle.get("status"),
        "output_md": output_md if isinstance(output_md, str) else str(bundle_dir / EVIDENCE_BUNDLE_MD_NAME),
        "output_json": (
            output_json
            if isinstance(output_json, str)
            else str(bundle_dir / EVIDENCE_BUNDLE_JSON_NAME)
        ),
        "real_depth_reference_status": (
            bundle.get("summaries", {})
            .get("real_depth_reference", {})
            .get("status")
            if isinstance(bundle.get("summaries"), dict)
            else None
        ),
        "missing_required_artifact_count": len(bundle.get("missing_required_artifacts", []))
        if isinstance(bundle.get("missing_required_artifacts"), list)
        else None,
        "capture_plan": {
            "json_supplied": any(
                row.get("key") == "capture_plan_json" and row.get("status") == "available"
                for row in bundle.get("artifacts", [])
                if isinstance(row, dict)
            )
            if isinstance(bundle.get("artifacts"), list)
            else False,
            "markdown_supplied": any(
                row.get("key") == "capture_plan_md" and row.get("status") == "available"
                for row in bundle.get("artifacts", [])
                if isinstance(row, dict)
            )
            if isinstance(bundle.get("artifacts"), list)
            else False,
        },
    }


def run_negative_empty_inventory(
    *,
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    negative_dir = output_dir / "negative_empty_inventory"
    inventory_path = negative_dir / "empty_inventory.json"
    write_json(
        inventory_path,
        {
            "schema": "lerobot.sim.reference_media_inventory.v1",
            "ok": True,
            "repo_root": str(REPO_ROOT),
            "summary": {
                "media_count": 0,
                "image_count": 0,
                "video_count": 0,
                "currently_wired_media_count": 0,
                "active_current_gripper_reference_detected": False,
                "active_current_gripper_reference_path": "archive/chess_test_images/current_view.jpg",
            },
            "media": [],
            "visibility_gaps": [
                {
                    "category": "simulator_reference",
                    "status": "missing",
                    "note": "Synthetic negative-check inventory intentionally contains no media.",
                }
            ],
            "next_recommended_reference_fixture_inputs": [],
        },
    )
    summary_path = negative_dir / "comparison_set_summary.json"
    return run_child(
        name="negative_empty_inventory_comparison_set",
        command=[
            str(args.python.expanduser()),
            str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_comparison_set.py"),
            "--inventory-json",
            str(inventory_path),
            "--output-dir",
            str(negative_dir),
            "--python",
            str(args.python.expanduser()),
        ],
        output_dir=negative_dir,
        expected_json_path=summary_path,
        expected_failure=True,
    )


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_paths = write_candidate_inputs(args, output_dir)
    python = str(args.python.expanduser())

    reference_media_config = reference_media_inventory_config(args)
    inventory_dir = output_dir / REFERENCE_MEDIA_INVENTORY_DIR_NAME
    inventory_json_path = inventory_dir / REFERENCE_MEDIA_INVENTORY_JSON_NAME
    inventory_command = reference_media_inventory_command(
        python=python,
        inventory_dir=inventory_dir,
        args=args,
    )
    inventory_record, inventory = run_child(
        name="reference_media_inventory",
        command=inventory_command,
        output_dir=inventory_dir,
        expected_json_path=inventory_json_path,
    )
    inventory_record["diagnostics"] = reference_media_inventory_child_diagnostics(
        inventory=inventory,
        inventory_dir=inventory_dir,
        config=reference_media_config,
    )

    comparison_dir = output_dir / "comparison_set"
    comparison_summary_path = comparison_dir / "comparison_set_summary.json"
    if inventory_json_path.is_file():
        comparison_non_failing_statuses = (
            {"no_reference_media_selected"}
            if reference_media_inventory_empty(inventory)
            else None
        )
        comparison_record, comparison = run_child(
            name="comparison_set",
            command=[
                python,
                str(REPO_ROOT / "scripts" / "smoke_sim_reference_media_comparison_set.py"),
                "--inventory-json",
                str(inventory_json_path),
                "--output-dir",
                str(comparison_dir),
                "--python",
                python,
            ],
            output_dir=comparison_dir,
            expected_json_path=comparison_summary_path,
            non_failing_statuses=comparison_non_failing_statuses,
        )
    else:
        comparison_record = skipped_child("comparison_set", "inventory JSON was not available", comparison_summary_path)
        comparison = None
    comparison_record["diagnostics"] = reference_media_comparison_diagnostics(
        comparison,
        comparison_dir,
        comparison_summary_path,
    )

    tuning_dir = output_dir / REFERENCE_CAMERA_TUNING_DIR_NAME
    tuning_summary_path = tuning_dir / REFERENCE_CAMERA_TUNING_JSON_NAME
    if comparison_summary_path.is_file():
        tuning_record, tuning_diagnostics = run_child(
            name="reference_camera_tuning_diagnostics",
            command=[
                python,
                str(REPO_ROOT / "scripts" / "smoke_sim_reference_camera_tuning_diagnostics.py"),
                "--comparison-summary-json",
                str(comparison_summary_path),
                "--output-dir",
                str(tuning_dir),
            ],
            output_dir=tuning_dir,
            expected_json_path=tuning_summary_path,
            non_failing_statuses={"metadata_only", "no_reference_media_selected"},
        )
    else:
        tuning_record = skipped_child(
            "reference_camera_tuning_diagnostics",
            "comparison set summary JSON was not available",
            tuning_summary_path,
        )
        tuning_diagnostics = None
    tuning_record["diagnostics"] = reference_camera_tuning_diagnostics_section(
        tuning_diagnostics,
        tuning_dir,
        tuning_summary_path,
    )

    sim_camera_profile_sweep_dir = output_dir / SIM_CAMERA_PROFILE_SWEEP_DIR_NAME
    sim_camera_profile_sweep_summary_path = (
        sim_camera_profile_sweep_dir / SIM_CAMERA_PROFILE_SWEEP_JSON_NAME
    )
    sim_camera_profile_sweep_record, sim_camera_profile_sweep = run_child(
        name="sim_camera_profile_sweep",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_profile_calibration_sweep.py"),
            "--output-dir",
            str(sim_camera_profile_sweep_dir),
            "--reference-image",
            str(args.reference_image.expanduser()),
            "--profile",
            str(args.base_profile),
            "--marker-time-seconds",
            str(SIM_CAMERA_PROFILE_SWEEP_MARKER_TIME_SECONDS),
        ],
        output_dir=sim_camera_profile_sweep_dir,
        expected_json_path=sim_camera_profile_sweep_summary_path,
    )
    sim_camera_profile_sweep_record["diagnostics"] = sim_camera_profile_sweep_section(
        sim_camera_profile_sweep,
        sim_camera_profile_sweep_dir,
        sim_camera_profile_sweep_summary_path,
    )

    sim_camera_tuning_before_after_dir = output_dir / SIM_CAMERA_TUNING_BEFORE_AFTER_DIR_NAME
    sim_camera_tuning_before_after_summary_path = (
        sim_camera_tuning_before_after_dir / SIM_CAMERA_TUNING_BEFORE_AFTER_JSON_NAME
    )
    sim_camera_tuning_before_after_record, sim_camera_tuning_before_after = run_child(
        name="simcamera_tuning_before_after",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_simcamera_tuning_before_after.py"),
            "--output-dir",
            str(sim_camera_tuning_before_after_dir),
            "--reference-image",
            str(args.reference_image.expanduser()),
            "--profile",
            str(args.base_profile),
            "--python",
            python,
            "--baseline-gripper-finger-width-px",
            str(SIM_CAMERA_TUNING_BEFORE_AFTER_BASELINE_WIDTH_PX),
            "--marker-time-seconds",
            str(SIM_CAMERA_PROFILE_SWEEP_MARKER_TIME_SECONDS),
        ],
        output_dir=sim_camera_tuning_before_after_dir,
        expected_json_path=sim_camera_tuning_before_after_summary_path,
        non_failing_statuses={"dependency_unavailable"},
    )
    sim_camera_tuning_before_after_record["diagnostics"] = (
        sim_camera_tuning_before_after_section(
            sim_camera_tuning_before_after,
            sim_camera_tuning_before_after_dir,
            sim_camera_tuning_before_after_summary_path,
        )
    )

    reference_capture_manifest_dir = output_dir / REFERENCE_CAPTURE_MANIFEST_DIR_NAME
    reference_capture_manifest_summary_path = (
        reference_capture_manifest_dir / REFERENCE_CAPTURE_MANIFEST_JSON_NAME
    )
    reference_capture_manifest_config_row = reference_capture_manifest_config(args)
    reference_capture_manifest_record, reference_capture_manifest = run_child(
        name="reference_capture_manifest",
        command=reference_capture_manifest_command(
            python=python,
            manifest_dir=reference_capture_manifest_dir,
            args=args,
        ),
        output_dir=reference_capture_manifest_dir,
        expected_json_path=reference_capture_manifest_summary_path,
    )
    reference_capture_manifest_record["diagnostics"] = reference_capture_manifest_section(
        manifest=reference_capture_manifest,
        manifest_dir=reference_capture_manifest_dir,
        config=reference_capture_manifest_config_row,
    )

    real_depth_capture_plan_artifact_index_dir = (
        output_dir / REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_DIR_NAME
    )
    real_depth_capture_plan_artifact_index_summary_path = (
        real_depth_capture_plan_artifact_index_dir / REAL_DEPTH_CAPTURE_PLAN_ARTIFACT_INDEX_JSON_NAME
    )
    real_depth_capture_plan_artifact_index_record, real_depth_capture_plan_artifact_index = (
        run_child(
            name="real_depth_capture_plan_artifact_index",
            command=real_depth_capture_plan_artifact_index_command(
                python=python,
                index_dir=real_depth_capture_plan_artifact_index_dir,
            ),
            output_dir=real_depth_capture_plan_artifact_index_dir,
            expected_json_path=real_depth_capture_plan_artifact_index_summary_path,
        )
    )
    real_depth_capture_plan_artifact_index_record["diagnostics"] = (
        real_depth_capture_plan_artifact_index_section(
            real_depth_capture_plan_artifact_index,
            real_depth_capture_plan_artifact_index_dir,
        )
    )

    session_dir = output_dir / "session"
    session_summary_path = session_dir / "session_summary.json"
    session_record, session = run_child(
        name="calibration_session_report",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_calibration_session_report.py"),
            candidate_paths["baseline_candidate_path"],
            candidate_paths["perturbed_candidate_path"],
            "--output-dir",
            str(session_dir),
            "--python",
            python,
            "--source-square",
            str(args.source_square),
            "--target-square",
            str(args.target_square),
        ],
        output_dir=session_dir,
        expected_json_path=session_summary_path,
    )

    fixture_dir = output_dir / "fixture"
    fixture_summary_path = fixture_dir / "fixture_summary.json"
    if session_record["ok"]:
        fixture_record, fixture = run_child(
            name="perception_regression_fixture",
            command=[
                python,
                str(REPO_ROOT / "scripts" / "smoke_sim_perception_regression_fixture.py"),
                str(session_summary_path),
                "--select-rank",
                str(int(args.select_rank)),
                "--output-dir",
                str(fixture_dir),
                "--source-square",
                str(args.source_square),
                "--target-square",
                str(args.target_square),
            ],
            output_dir=fixture_dir,
            expected_json_path=fixture_summary_path,
        )
    else:
        fixture_record = skipped_child(
            "perception_regression_fixture",
            "ranked session summary did not validate",
            fixture_summary_path,
        )
        fixture = None

    pose_fixture_dir = output_dir / "sim_camera_pose_fixture"
    pose_fixture_summary_path = pose_fixture_dir / "sim_camera_pose_fixture_summary.json"
    pose_fixture_record, pose_fixture = run_child(
        name="sim_camera_pose_fixture",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_camera_pose_fixture.py"),
            "--output-dir",
            str(pose_fixture_dir),
            "--profile",
            str(args.base_profile),
            "--target-square",
            str(args.source_square),
            "--closed-gripper-square",
            str(args.target_square),
        ],
        output_dir=pose_fixture_dir,
        expected_json_path=pose_fixture_summary_path,
    )

    so101_model_bundle_manifest_dir = output_dir / "so101_model_bundle_manifest"
    so101_model_bundle_manifest_summary_path = (
        so101_model_bundle_manifest_dir / SO101_MODEL_BUNDLE_MANIFEST_SUMMARY_NAME
    )
    so101_bundle_config = so101_model_bundle_manifest_config(args)
    so101_model_bundle_manifest_record, so101_model_bundle_manifest = run_child(
        name="so101_model_bundle_manifest",
        command=so101_model_bundle_manifest_command(
            python=python,
            bundle_dir=so101_model_bundle_manifest_dir,
            args=args,
        ),
        output_dir=so101_model_bundle_manifest_dir,
        expected_json_path=so101_model_bundle_manifest_summary_path,
    )
    so101_bundle_forwarding = so101_bundle_forwarding_decision(
        args=args,
        bundle=so101_model_bundle_manifest,
    )
    so101_reviewed_mujoco_bundle_dir = output_dir / SO101_REVIEWED_MUJOCO_BUNDLE_DIR_NAME
    so101_reviewed_mujoco_bundle_summary_path = (
        so101_reviewed_mujoco_bundle_dir / SO101_REVIEWED_MUJOCO_BUNDLE_SUMMARY_NAME
    )
    so101_reviewed_mujoco_bundle_record, so101_reviewed_mujoco_bundle = run_child(
        name="so101_reviewed_mujoco_bundle",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_reviewed_mujoco_bundle.py"),
            "--output-dir",
            str(so101_reviewed_mujoco_bundle_dir),
            "--manifest-summary-path",
            str(so101_model_bundle_manifest_summary_path),
            "--python",
            python,
        ],
        output_dir=so101_reviewed_mujoco_bundle_dir,
        expected_json_path=so101_reviewed_mujoco_bundle_summary_path,
    )
    effective_ik_model_path = path_from_string(so101_bundle_forwarding.get("effective_ik_model_path"))
    effective_ik_model_asset_roots = paths_from_strings(
        so101_bundle_forwarding.get("effective_ik_model_asset_roots")
    )
    (
        effective_model_source_roots,
        effective_model_source_extra_roots,
        effective_authoritative_model_paths,
        effective_authoritative_model_roots,
        so101_bundle_inventory_forwarding,
    ) = so101_inventory_forwarding_decision(
        args=args,
        bundle_forwarding=so101_bundle_forwarding,
    )

    so101_model_source_inventory_dir = output_dir / "so101_model_source_inventory"
    so101_model_source_inventory_summary_path = (
        so101_model_source_inventory_dir / SO101_MODEL_SOURCE_INVENTORY_SUMMARY_NAME
    )
    so101_source_authority_review = so101_source_authority_review_forwarding(
        args=args,
        bundle=so101_model_bundle_manifest,
        bundle_inventory_forwarding=so101_bundle_inventory_forwarding,
    )
    so101_source_config = so101_model_source_inventory_config(
        args,
        model_source_roots=effective_model_source_roots,
        model_source_extra_roots=effective_model_source_extra_roots,
        authoritative_model_paths=effective_authoritative_model_paths,
        authoritative_model_roots=effective_authoritative_model_roots,
        bundle_inventory_forwarding=so101_bundle_inventory_forwarding,
        source_authority_review=so101_source_authority_review,
        effective_ik_model_path=effective_ik_model_path,
    )
    so101_contract_config = so101_model_contract_config(
        args,
        effective_ik_model_path=effective_ik_model_path,
        effective_asset_roots=effective_ik_model_asset_roots,
        bundle_forwarding=so101_bundle_forwarding,
    )
    so101_model_source_inventory_record, so101_model_source_inventory = run_child(
        name="so101_model_source_inventory",
        command=so101_model_source_inventory_command(
            python=python,
            inventory_dir=so101_model_source_inventory_dir,
            model_source_roots=effective_model_source_roots,
            model_source_extra_roots=effective_model_source_extra_roots,
            authoritative_model_paths=effective_authoritative_model_paths,
            authoritative_model_roots=effective_authoritative_model_roots,
            source_authority_review=so101_source_authority_review,
        ),
        output_dir=so101_model_source_inventory_dir,
        expected_json_path=so101_model_source_inventory_summary_path,
    )

    so101_model_bundle_probe_dir = output_dir / SO101_MODEL_BUNDLE_PROBE_DIR_NAME
    so101_model_bundle_probe_summary_path = (
        so101_model_bundle_probe_dir / SO101_MODEL_BUNDLE_PROBE_SUMMARY_NAME
    )
    so101_model_bundle_probe_model_path = recommended_contract_model_path(
        so101_model_source_inventory
    )
    if so101_model_bundle_probe_model_path is None:
        so101_model_bundle_probe_model_path = effective_ik_model_path
    so101_model_bundle_probe_record, so101_model_bundle_probe = run_child(
        name="so101_model_bundle_probe",
        command=so101_model_bundle_probe_command(
            python=python,
            probe_dir=so101_model_bundle_probe_dir,
            model_path=so101_model_bundle_probe_model_path,
            asset_roots=effective_ik_model_asset_roots,
            target_frame="gripper_frame_link",
            source_authority_review=so101_source_authority_review,
        ),
        output_dir=so101_model_bundle_probe_dir,
        expected_json_path=so101_model_bundle_probe_summary_path,
    )

    so101_model_contract_dir = output_dir / "so101_model_contract"
    so101_model_contract_summary_path = so101_model_contract_dir / SO101_MODEL_CONTRACT_SUMMARY_NAME
    so101_model_contract_command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_so101_model_contract.py"),
        "--output-dir",
        str(so101_model_contract_dir),
    ]
    if effective_ik_model_path is not None:
        so101_model_contract_command.extend(["--model-path", str(effective_ik_model_path)])
    for asset_root in effective_ik_model_asset_roots:
        so101_model_contract_command.extend(["--model-asset-root", str(asset_root.expanduser())])
    so101_model_contract_record, so101_model_contract = run_child(
        name="so101_model_contract",
        command=so101_model_contract_command,
        output_dir=so101_model_contract_dir,
        expected_json_path=so101_model_contract_summary_path,
    )

    ik_reachability_dir = output_dir / "ik_reachability_drill"
    ik_reachability_summary_path = ik_reachability_dir / IK_REACHABILITY_SUMMARY_NAME
    ik_reachability_command = [
        python,
        str(REPO_ROOT / "scripts" / "smoke_sim_ik_reachability_drill.py"),
        "--output-dir",
        str(ik_reachability_dir),
    ]
    if effective_ik_model_path is not None:
        ik_reachability_command.extend(["--model-path", str(effective_ik_model_path)])
    ik_reachability_record, ik_reachability = run_child(
        name="ik_reachability_drill",
        command=ik_reachability_command,
        output_dir=ik_reachability_dir,
        expected_json_path=ik_reachability_summary_path,
    )

    so101_mujoco_scene_dir = output_dir / SO101_MUJOCO_SCENE_DIR_NAME
    so101_mujoco_scene_summary_path = so101_mujoco_scene_dir / SO101_MUJOCO_SCENE_SUMMARY_NAME
    so101_reviewed_mujoco_downstream_handoff_path = (
        so101_reviewed_mujoco_bundle_dir
        / SO101_REVIEWED_MUJOCO_BUNDLE_DOWNSTREAM_HANDOFF_NAME
    )
    so101_mujoco_scene_record, so101_mujoco_scene = run_child(
        name="so101_mujoco_scene",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_scene.py"),
            "--output-dir",
            str(so101_mujoco_scene_dir),
            "--source-square",
            str(args.source_square),
            "--target-square",
            str(args.target_square),
            "--reviewed-mujoco-handoff-json",
            str(so101_reviewed_mujoco_downstream_handoff_path),
        ],
        output_dir=so101_mujoco_scene_dir,
        expected_json_path=so101_mujoco_scene_summary_path,
    )

    so101_chess_env_dir = output_dir / SO101_CHESS_ENV_DIR_NAME
    so101_chess_env_summary_path = so101_chess_env_dir / SO101_CHESS_ENV_SUMMARY_NAME
    so101_mujoco_scene_artifacts = (
        so101_mujoco_scene.get("artifacts") if isinstance(so101_mujoco_scene, dict) else {}
    )
    so101_mujoco_scene_artifacts = (
        so101_mujoco_scene_artifacts if isinstance(so101_mujoco_scene_artifacts, dict) else {}
    )
    so101_development_model_path = so101_mujoco_scene_artifacts.get("model_xml")
    if isinstance(so101_development_model_path, str) and Path(so101_development_model_path).is_file():
        so101_chess_env_record, so101_chess_env = run_child(
            name="so101_chess_env",
            command=[
                python,
                str(REPO_ROOT / "scripts" / "smoke_sim_so101_chess_env.py"),
                "--output-dir",
                str(so101_chess_env_dir),
                "--require-gymnasium",
                "--require-mujoco",
                "--mujoco-model-path",
                so101_development_model_path,
            ],
            output_dir=so101_chess_env_dir,
            expected_json_path=so101_chess_env_summary_path,
        )
    else:
        so101_chess_env_record = skipped_child(
            "so101_chess_env",
            "development MuJoCo scene model was not available",
            so101_chess_env_summary_path,
        )
        so101_chess_env = None

    so101_env_resets_dir = output_dir / SO101_ENV_RESETS_DIR_NAME
    so101_env_resets_summary_path = so101_env_resets_dir / SO101_ENV_RESETS_SUMMARY_NAME
    so101_env_resets_record, so101_env_resets = run_child(
        name="so101_env_resets",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_env_resets.py"),
            "--output-dir",
            str(so101_env_resets_dir),
        ],
        output_dir=so101_env_resets_dir,
        expected_json_path=so101_env_resets_summary_path,
    )

    so101_mujoco_contact_probe_dir = output_dir / SO101_MUJOCO_CONTACT_PROBE_DIR_NAME
    so101_mujoco_contact_probe_summary_path = (
        so101_mujoco_contact_probe_dir / SO101_MUJOCO_CONTACT_PROBE_SUMMARY_NAME
    )
    so101_mujoco_contact_probe_record, so101_mujoco_contact_probe = run_child(
        name="so101_mujoco_contact_probe",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_contact_probe.py"),
            "--output-dir",
            str(so101_mujoco_contact_probe_dir),
        ],
        output_dir=so101_mujoco_contact_probe_dir,
        expected_json_path=so101_mujoco_contact_probe_summary_path,
    )

    so101_mujoco_grasp_probe_dir = output_dir / SO101_MUJOCO_GRASP_PROBE_DIR_NAME
    so101_mujoco_grasp_probe_summary_path = (
        so101_mujoco_grasp_probe_dir / SO101_MUJOCO_GRASP_PROBE_SUMMARY_NAME
    )
    so101_mujoco_grasp_probe_record, so101_mujoco_grasp_probe = run_child(
        name="so101_mujoco_grasp_probe",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_grasp_probe.py"),
            "--output-dir",
            str(so101_mujoco_grasp_probe_dir),
        ],
        output_dir=so101_mujoco_grasp_probe_dir,
        expected_json_path=so101_mujoco_grasp_probe_summary_path,
    )

    so101_mujoco_board_pick_probe_dir = output_dir / SO101_MUJOCO_BOARD_PICK_PROBE_DIR_NAME
    so101_mujoco_board_pick_probe_summary_path = (
        so101_mujoco_board_pick_probe_dir / SO101_MUJOCO_BOARD_PICK_PROBE_SUMMARY_NAME
    )
    so101_mujoco_board_pick_probe_record, so101_mujoco_board_pick_probe = run_child(
        name="so101_mujoco_board_pick_probe",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_mujoco_board_pick_probe.py"),
            "--output-dir",
            str(so101_mujoco_board_pick_probe_dir),
            "--source-square",
            str(args.source_square),
            "--target-square",
            str(args.target_square),
        ],
        output_dir=so101_mujoco_board_pick_probe_dir,
        expected_json_path=so101_mujoco_board_pick_probe_summary_path,
    )

    so101_training_rollouts_dir = output_dir / SO101_TRAINING_ROLLOUTS_DIR_NAME
    so101_training_rollouts_summary_path = (
        so101_training_rollouts_dir / SO101_TRAINING_ROLLOUTS_SUMMARY_NAME
    )
    so101_training_rollouts_record, so101_training_rollouts = run_child(
        name="so101_training_rollouts",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_so101_training_rollouts.py"),
            "--output-dir",
            str(so101_training_rollouts_dir),
            "--development-board-pick-summary-json",
            str(so101_mujoco_board_pick_probe_summary_path),
        ],
        output_dir=so101_training_rollouts_dir,
        expected_json_path=so101_training_rollouts_summary_path,
    )

    pov_dir = output_dir / "gripper_camera_pov_review"
    pov_summary_path = pov_dir / "gripper_camera_pov_review_summary.json"
    pov_record, pov = run_child(
        name="gripper_camera_pov_review",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_gripper_camera_pov_review.py"),
            "--output-dir",
            str(pov_dir),
            "--profile",
            str(args.base_profile),
            "--target-square",
            str(args.source_square),
        ],
        output_dir=pov_dir,
        expected_json_path=pov_summary_path,
    )

    matrix_dir = output_dir / "pick_place_scenario_matrix"
    matrix_summary_path = matrix_dir / "scenario_matrix_summary.json"
    matrix_record, matrix = run_child(
        name="pick_place_scenario_matrix",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_pick_place_scenario_matrix.py"),
            "--output-dir",
            str(matrix_dir),
            "--python",
            python,
            "--sim-camera-profile",
            str(args.base_profile),
        ],
        output_dir=matrix_dir,
        expected_json_path=matrix_summary_path,
    )

    negative_record: dict[str, Any] | None = None
    negative_summary: dict[str, Any] | None = None
    if args.include_negative_check:
        negative_record, negative_summary = run_negative_empty_inventory(args=args, output_dir=output_dir)

    app_entrypoint_dir = output_dir / "app_entrypoint"
    app_entrypoint_summary_path = app_entrypoint_dir / "smoke_sim_app_entrypoints_summary.json"
    app_entrypoint_frame_path = app_entrypoint_dir / "smoke_sim_app_frame.jpg"
    app_entrypoint_metadata_path = app_entrypoint_dir / "smoke_sim_app_metadata.json"
    app_entrypoint_record, app_entrypoint = run_child(
        name="app_entrypoint_metadata",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_app_entrypoints.py"),
            "--sim-camera-profile",
            str(args.base_profile),
            "--frame-out",
            str(app_entrypoint_frame_path),
            "--metadata-out",
            str(app_entrypoint_metadata_path),
            "--summary-out",
            str(app_entrypoint_summary_path),
        ],
        output_dir=app_entrypoint_dir,
        expected_json_path=app_entrypoint_summary_path,
    )

    visual_review_dir = output_dir / "visual_review"
    visual_review_summary_path = visual_review_dir / VISUAL_REVIEW_SUMMARY_NAME

    child_records = {
        "reference_media_inventory": inventory_record,
        "comparison_set": comparison_record,
        "reference_camera_tuning_diagnostics": tuning_record,
        "sim_camera_profile_sweep": sim_camera_profile_sweep_record,
        "simcamera_tuning_before_after": sim_camera_tuning_before_after_record,
        "reference_capture_manifest": reference_capture_manifest_record,
        "real_depth_capture_plan_artifact_index": real_depth_capture_plan_artifact_index_record,
        "calibration_session_report": session_record,
        "perception_regression_fixture": fixture_record,
        "sim_camera_pose_fixture": pose_fixture_record,
        "so101_model_bundle_manifest": so101_model_bundle_manifest_record,
        "so101_reviewed_mujoco_bundle": so101_reviewed_mujoco_bundle_record,
        "so101_model_source_inventory": so101_model_source_inventory_record,
        "so101_model_bundle_probe": so101_model_bundle_probe_record,
        "so101_model_contract": so101_model_contract_record,
        "ik_reachability_drill": ik_reachability_record,
        "so101_mujoco_scene": so101_mujoco_scene_record,
        "so101_chess_env": so101_chess_env_record,
        "so101_env_resets": so101_env_resets_record,
        "so101_mujoco_contact_probe": so101_mujoco_contact_probe_record,
        "so101_mujoco_grasp_probe": so101_mujoco_grasp_probe_record,
        "so101_mujoco_board_pick_probe": so101_mujoco_board_pick_probe_record,
        "so101_training_rollouts": so101_training_rollouts_record,
        "gripper_camera_pov_review": pov_record,
        "pick_place_scenario_matrix": matrix_record,
    }
    if negative_record is not None:
        child_records["negative_empty_inventory_comparison_set"] = negative_record
    child_records["app_entrypoint_metadata"] = app_entrypoint_record

    so101_source_inventory_section = so101_model_source_inventory_section(
        so101_model_source_inventory,
        so101_model_source_inventory_summary_path,
        so101_source_config,
    )
    so101_bundle_probe_section = so101_model_bundle_probe_section(
        so101_model_bundle_probe,
        so101_model_bundle_probe_summary_path,
        so101_model_bundle_probe_model_path,
        effective_ik_model_asset_roots,
    )
    so101_bundle_manifest_section = so101_model_bundle_manifest_section(
        so101_model_bundle_manifest,
        so101_model_bundle_manifest_summary_path,
        so101_bundle_config,
        so101_bundle_forwarding,
    )
    so101_reviewed_mujoco_bundle_section = so101_mujoco_smoke_section(
        so101_reviewed_mujoco_bundle,
        so101_reviewed_mujoco_bundle_summary_path,
    )
    so101_reviewed_authority_gate = so101_reviewed_model_authority_gate_section(
        so101_source_inventory_section,
        so101_bundle_manifest_section,
        so101_reviewed_mujoco_bundle_section,
    )
    so101_reviewed_authority_gate = write_so101_reviewed_model_authority_gate_artifacts(
        output_dir,
        so101_reviewed_authority_gate,
    )
    so101_mujoco_scene_section = so101_mujoco_smoke_section(
        so101_mujoco_scene,
        so101_mujoco_scene_summary_path,
    )
    so101_chess_env_section = so101_mujoco_smoke_section(
        so101_chess_env,
        so101_chess_env_summary_path,
    )
    so101_mujoco_contact_probe_section = so101_mujoco_smoke_section(
        so101_mujoco_contact_probe,
        so101_mujoco_contact_probe_summary_path,
    )
    so101_mujoco_grasp_probe_section = so101_mujoco_smoke_section(
        so101_mujoco_grasp_probe,
        so101_mujoco_grasp_probe_summary_path,
    )
    so101_mujoco_board_pick_probe_section = so101_mujoco_smoke_section(
        so101_mujoco_board_pick_probe,
        so101_mujoco_board_pick_probe_summary_path,
    )
    so101_training_rollouts_section = so101_mujoco_smoke_section(
        so101_training_rollouts,
        so101_training_rollouts_summary_path,
    )
    so101_training_readiness_gate = so101_training_readiness_gate_section(
        so101_reviewed_authority_gate,
        so101_mujoco_board_pick_probe_section,
        so101_training_rollouts_section,
        reviewed_mujoco_bundle=so101_reviewed_mujoco_bundle_section,
        mujoco_scene=so101_mujoco_scene_section,
        chess_env=so101_chess_env_section,
        contact_probe=so101_mujoco_contact_probe_section,
        grasp_probe=so101_mujoco_grasp_probe_section,
    )
    so101_training_readiness_gate = write_so101_training_readiness_gate_artifacts(
        output_dir,
        so101_training_readiness_gate,
    )

    required_ok = all(record["ok"] for record in child_records.values())
    selected_candidate = selected_from_session(session, int(args.select_rank))
    summary_path = output_dir / "calibration_regression_summary.json"
    artifact_index_path = output_dir / "artifact_index.json"
    summary = {
        "schema": SCHEMA,
        "ok": required_ok,
        "status": "ok" if required_ok else "validation_failed",
        "aggregate_status": {
            "ok": required_ok,
            "failed_children": [
                name for name, record in child_records.items() if not bool(record.get("ok"))
            ],
        },
        "summary_path": str(summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "python": python,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "skipped_markers": {
            "hardware": "Suite and child smokes use simulator/reference media only; no robot hardware paths are invoked.",
            "gui": "Suite passes explicit non-interactive inputs and does not request OpenCV click/display flows.",
            "openai": "Suite and child smokes exercise local simulator/tool paths only; no OpenAI credentials or network calls are required.",
        },
        "candidate_inputs": candidate_paths,
        "so101_model_bundle_manifest_config": so101_bundle_config,
        "so101_model_bundle_manifest_forwarding": so101_bundle_forwarding,
        "reference_media_inventory_config": reference_media_config,
        "reference_capture_manifest_config": reference_capture_manifest_config_row,
        "so101_model_source_inventory_config": so101_source_config,
        "so101_model_contract_config": so101_contract_config,
        "child_commands": child_records,
        "reference_media_manifest": manifest_status_section(
            requested_manifest=args.reference_media_manifest,
            inventory=inventory,
            comparison=comparison,
        ),
        "reference_media_inventory": reference_media_inventory_section(
            inventory=inventory,
            inventory_dir=inventory_dir,
            config=reference_media_config,
        ),
        "inventory": reference_media_inventory_section(
            inventory=inventory,
            inventory_dir=inventory_dir,
            config=reference_media_config,
        ),
        "comparison_set": {
            **reference_media_comparison_section(
                comparison,
                comparison_dir,
                comparison_summary_path,
            ),
        },
        "reference_camera_tuning_diagnostics": reference_camera_tuning_diagnostics_section(
            tuning_diagnostics,
            tuning_dir,
            tuning_summary_path,
        ),
        "sim_camera_profile_sweep": sim_camera_profile_sweep_section(
            sim_camera_profile_sweep,
            sim_camera_profile_sweep_dir,
            sim_camera_profile_sweep_summary_path,
        ),
        "simcamera_tuning_before_after": sim_camera_tuning_before_after_section(
            sim_camera_tuning_before_after,
            sim_camera_tuning_before_after_dir,
            sim_camera_tuning_before_after_summary_path,
        ),
        "reference_capture_manifest": reference_capture_manifest_section(
            manifest=reference_capture_manifest,
            manifest_dir=reference_capture_manifest_dir,
            config=reference_capture_manifest_config_row,
        ),
        "real_depth_capture_plan_artifact_index": real_depth_capture_plan_artifact_index_section(
            real_depth_capture_plan_artifact_index,
            real_depth_capture_plan_artifact_index_dir,
        ),
        "calibration_session": {
            "summary_path": str(session_summary_path),
            "candidate_count": session.get("candidate_count") if session else None,
            "ranking": ranking_summary(session),
            "selected_candidate": selected_candidate,
        },
        "perception_fixture": {
            "summary_path": str(fixture_summary_path),
            "status": fixture.get("status") if fixture else None,
            "selected_candidate": fixture.get("selected_candidate") if fixture else None,
            "artifact_paths": selected_fixture_artifacts(fixture),
        },
        "sim_camera_pose_fixture": sim_camera_pose_fixture_section(
            pose_fixture,
            pose_fixture_summary_path,
        ),
        "so101_model_source_inventory": so101_source_inventory_section,
        "so101_model_bundle_probe": so101_bundle_probe_section,
        "so101_model_bundle_manifest": so101_bundle_manifest_section,
        "so101_reviewed_mujoco_bundle": so101_reviewed_mujoco_bundle_section,
        "so101_reviewed_model_authority_gate": so101_reviewed_authority_gate,
        "so101_model_contract": so101_model_contract_section(
            so101_model_contract,
            so101_model_contract_summary_path,
        ),
        "ik_reachability_drill": ik_reachability_section(
            ik_reachability,
            ik_reachability_summary_path,
        ),
        "so101_mujoco_scene": so101_mujoco_scene_section,
        "so101_chess_env": so101_chess_env_section,
        "so101_env_resets": so101_mujoco_smoke_section(
            so101_env_resets,
            so101_env_resets_summary_path,
        ),
        "so101_mujoco_contact_probe": so101_mujoco_contact_probe_section,
        "so101_mujoco_grasp_probe": so101_mujoco_grasp_probe_section,
        "so101_mujoco_board_pick_probe": so101_mujoco_board_pick_probe_section,
        "so101_training_readiness_gate": so101_training_readiness_gate,
        "so101_training_rollouts": so101_training_rollouts_section,
        "gripper_camera_pov_review": gripper_camera_pov_section(pov, pov_summary_path),
        "pick_place_scenario_matrix": matrix_summary_section(matrix, matrix_summary_path),
        "app_entrypoint_metadata": app_entrypoint_metadata_section(
            app_entrypoint,
            summary_path=app_entrypoint_summary_path,
            frame_path=app_entrypoint_frame_path,
            metadata_path=app_entrypoint_metadata_path,
        ),
        "selected_candidate": {
            "requested_rank": int(args.select_rank),
            "candidate_id": selected_candidate.get("candidate_id") if selected_candidate else None,
            "rank": selected_candidate.get("rank") if selected_candidate else None,
            "rank_score": selected_candidate.get("rank_score") if selected_candidate else None,
            "artifact_paths": selected_candidate.get("artifact_paths") if selected_candidate else None,
        },
        "negative_check": {
            "included": bool(args.include_negative_check),
            "record": negative_record,
            "summary_path": negative_summary.get("comparison_set_summary_path") if negative_summary else None,
            "status": negative_summary.get("status") if negative_summary else None,
        },
        "reference_capture_checklist": {
            "summary_path": str(output_dir / "reference_capture_checklist" / REFERENCE_CAPTURE_CHECKLIST_NAME),
            "status": None,
            "represented_media_count": None,
            "missing_requirement_count": None,
        },
        "real_projection_intake": {
            "summary_path": str(output_dir / "real_projection_intake" / REAL_PROJECTION_INTAKE_NAME),
            "status": None,
            "real_reference_media_count": None,
            "comparable_count": None,
        },
        "evidence_bundle": {
            "summary_path": str(output_dir / EVIDENCE_BUNDLE_DIR_NAME / EVIDENCE_BUNDLE_JSON_NAME),
            "markdown_path": str(output_dir / EVIDENCE_BUNDLE_DIR_NAME / EVIDENCE_BUNDLE_MD_NAME),
            "status": None,
        },
        "artifact_index": {
            "path": str(artifact_index_path),
            "status": None,
            "artifact_count": None,
            "missing_artifact_count": None,
        },
        "notes": [
            "This suite intentionally calls existing smoke scripts as subprocesses instead of duplicating their internals.",
            "It does not mutate simulator rendering, camera profiles, perception algorithms, robot execution, dependencies, or canonical calibration constants.",
            "SimCamera intrinsics/extrinsics are simulator reference metadata for downstream tool compatibility, not physical calibration truth.",
            "MuJoCo SO-101 chess evidence is prioritized as a development-plumbing gate until a reviewed model bundle, TCP/gripper offset, and base-to-board alignment make model-backed training evidence trustworthy.",
        ],
    }
    write_json(summary_path, summary)

    visual_review_record, visual_review = run_child(
        name="visual_review",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "render_sim_calibration_visual_review.py"),
            str(summary_path),
            "--output-dir",
            str(visual_review_dir),
            "--try-video",
        ],
        output_dir=visual_review_dir,
        expected_json_path=visual_review_summary_path,
    )
    child_records["visual_review"] = visual_review_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["visual_review"] = visual_review_section(visual_review, visual_review_summary_path)
    write_json(summary_path, summary)

    checklist_dir = output_dir / "reference_capture_checklist"
    checklist_summary_path = checklist_dir / REFERENCE_CAPTURE_CHECKLIST_NAME
    checklist_record, checklist = run_child(
        name="reference_capture_checklist",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_reference_capture_checklist.py"),
            str(summary_path),
            "--output-dir",
            str(checklist_dir),
        ],
        output_dir=checklist_dir,
        expected_json_path=checklist_summary_path,
    )
    child_records["reference_capture_checklist"] = checklist_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["reference_capture_checklist"] = reference_capture_checklist_section(
        checklist,
        checklist_summary_path,
    )
    write_json(summary_path, summary)

    real_projection_intake_dir = output_dir / "real_projection_intake"
    real_projection_intake_summary_path = real_projection_intake_dir / REAL_PROJECTION_INTAKE_NAME
    real_projection_intake_record, real_projection_intake = run_child(
        name="real_projection_intake",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_real_projection_intake.py"),
            str(summary_path),
            "--output-dir",
            str(real_projection_intake_dir),
        ],
        output_dir=real_projection_intake_dir,
        expected_json_path=real_projection_intake_summary_path,
    )
    child_records["real_projection_intake"] = real_projection_intake_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["real_projection_intake"] = real_projection_intake_section(
        real_projection_intake,
        real_projection_intake_summary_path,
    )
    write_json(summary_path, summary)

    visual_review_refresh_record, visual_review_refresh = run_child(
        name="visual_review_real_depth_refresh",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "render_sim_calibration_visual_review.py"),
            str(summary_path),
            "--output-dir",
            str(visual_review_dir),
            "--try-video",
        ],
        output_dir=visual_review_dir,
        expected_json_path=visual_review_summary_path,
    )
    child_records["visual_review_real_depth_refresh"] = visual_review_refresh_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["visual_review"] = visual_review_section(
        visual_review_refresh,
        visual_review_summary_path,
    )
    write_json(summary_path, summary)

    evidence_bundle_dir = output_dir / EVIDENCE_BUNDLE_DIR_NAME
    evidence_bundle_json_path = evidence_bundle_dir / EVIDENCE_BUNDLE_JSON_NAME
    evidence_bundle_record, evidence_bundle = run_child(
        name="evidence_bundle",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "render_sim_evidence_bundle.py"),
            str(summary_path),
            "--output-dir",
            str(evidence_bundle_dir),
        ],
        output_dir=evidence_bundle_dir,
        expected_json_path=evidence_bundle_json_path,
    )
    child_records["evidence_bundle"] = evidence_bundle_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["evidence_bundle"] = evidence_bundle_section(evidence_bundle, evidence_bundle_dir)
    write_json(summary_path, summary)

    artifact_index_record, artifact_index = run_child(
        name="artifact_index",
        command=[
            python,
            str(REPO_ROOT / "scripts" / "smoke_sim_calibration_artifact_index.py"),
            str(summary_path),
            "--output-json",
            str(artifact_index_path),
        ],
        output_dir=output_dir,
        expected_json_path=artifact_index_path,
    )
    child_records["artifact_index"] = artifact_index_record
    required_ok = all(record["ok"] for record in child_records.values())
    summary["ok"] = required_ok
    summary["status"] = "ok" if required_ok else "validation_failed"
    summary["aggregate_status"] = {
        "ok": required_ok,
        "failed_children": [
            name for name, record in child_records.items() if not bool(record.get("ok"))
        ],
    }
    summary["child_commands"] = child_records
    summary["artifact_index"] = {
        "path": str(artifact_index_path),
        "status": artifact_index.get("status") if artifact_index else None,
        "artifact_count": len(artifact_index.get("artifacts", [])) if artifact_index else None,
        "missing_artifact_count": len(artifact_index.get("missing_artifacts", [])) if artifact_index else None,
        "categories": artifact_index.get("categories") if artifact_index else None,
    }
    write_json(summary_path, summary)

    if not args.skip_artifact_index_report:
        report_path = output_dir / ARTIFACT_REPORT_NAME
        report_result = subprocess.run(
            [
                python,
                str(REPO_ROOT / "scripts" / "render_sim_calibration_artifact_index_report.py"),
                str(artifact_index_path),
                "--output-md",
                str(report_path),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if report_result.returncode != 0:
            if report_result.stdout:
                sys.stdout.write(report_result.stdout)
            if report_result.stderr:
                sys.stderr.write(report_result.stderr)
            required_ok = False
            summary["ok"] = False
            summary["status"] = "validation_failed"
            failed_children = list(summary["aggregate_status"].get("failed_children", []))
            failed_children.append("artifact_index_report")
            summary["aggregate_status"] = {
                "ok": False,
                "failed_children": failed_children,
            }
            write_json(summary_path, summary)
        else:
            try:
                write_artifact_entrypoint_readme(output_dir, summary)
            except OSError as exc:
                print(f"ERROR: Could not write artifact entrypoint README: {exc}", file=sys.stderr)
                required_ok = False
                summary["ok"] = False
                summary["status"] = "validation_failed"
                failed_children = list(summary["aggregate_status"].get("failed_children", []))
                failed_children.append("artifact_entrypoint_readme")
                summary["aggregate_status"] = {
                    "ok": False,
                    "failed_children": failed_children,
                }
                write_json(summary_path, summary)

    print(json.dumps(summary, indent=2))
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
