#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smoke_sim_so101_bundle_ready_forwarding import create_fixtures  # noqa: E402

DEFAULT_OUTPUT_DIR = (
    Path("/private/tmp") / "lerobot_sim" / "so101_reviewed_mujoco_bundle_matrix"
)
SCHEMA = "lerobot.sim.so101_reviewed_mujoco_bundle_matrix.v1"
REVIEWED_MUJOCO_SCRIPT = REPO_ROOT / "scripts" / "smoke_sim_so101_reviewed_mujoco_bundle.py"
EXPECTED_MOTION_CHECK_JOINTS = (
    "elbow_flex",
    "gripper",
    "shoulder_lift",
    "shoulder_pan",
    "wrist_flex",
    "wrist_roll",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a compact hardware-free matrix over the SO-101 reviewed MuJoCo "
            "bundle gate. Fixture manifests are generated under the output directory "
            "and remain non-authoritative automation evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child reviewed-bundle checks.",
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_clone(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload))


def create_invalid_numeric_fixtures(output_dir: Path, fixtures: dict[str, Path]) -> dict[str, Path]:
    fixture_dir = output_dir / "fixtures" / "invalid_numeric_bundle"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    ready_payload = json.loads(fixtures["ready_manifest_path"].read_text())
    ready_payload["model_path"] = str(normalize_path(fixtures["ready_model_path"]))
    ready_payload["asset_roots"] = [str(normalize_path(fixtures["ready_asset_root"]))]
    ready_model_path = normalize_path(fixtures["ready_model_path"])
    ready_model_dir = ready_model_path.parent

    tiny_gripper_dir = output_dir / "fixtures" / "tiny_gripper_range_bundle"
    tiny_gripper_model_dir = tiny_gripper_dir / "model"
    tiny_gripper_model_dir.mkdir(parents=True, exist_ok=True)
    ready_mesh_dir = ready_model_dir / "meshes"
    if ready_mesh_dir.exists():
        shutil.copytree(ready_mesh_dir, tiny_gripper_model_dir / "meshes", dirs_exist_ok=True)
    tiny_gripper_model_path = tiny_gripper_model_dir / "synthetic_so101_tiny_gripper_range.xml"
    root = ET.fromstring(ready_model_path.read_text())
    gripper_range_patched = False
    for joint in root.iter("joint"):
        if joint.attrib.get("name") == "gripper":
            joint.set("range", "0 1e-12")
            gripper_range_patched = True
            break
    if not gripper_range_patched:
        raise RuntimeError("failed_to_patch_tiny_gripper_range_fixture")
    tiny_gripper_model_path.write_text(ET.tostring(root, encoding="unicode") + "\n")
    tiny_gripper_payload = json_clone(ready_payload)
    tiny_gripper_payload["model_path"] = str(normalize_path(tiny_gripper_model_path))
    tiny_gripper_payload["model_sha256"] = sha256_file(tiny_gripper_model_path)
    tiny_gripper_manifest_path = tiny_gripper_dir / "so101_model_bundle.tiny_gripper_range.json"
    write_json(tiny_gripper_manifest_path, tiny_gripper_payload)

    unavailable_model_path = json_clone(ready_payload)
    unavailable_model_path["model_path"] = str(
        normalize_path(fixture_dir / "missing_reviewed_so101.xml")
    )
    unavailable_model_path_manifest_path = (
        fixture_dir / "so101_model_bundle.unavailable_model_path.json"
    )
    write_json(unavailable_model_path_manifest_path, unavailable_model_path)

    nonfinite_joint_limits = json_clone(ready_payload)
    nonfinite_joint_limits["joint_limits_deg"]["shoulder_pan"] = ["NaN", 110.0]
    nonfinite_joint_limits_path = fixture_dir / "so101_model_bundle.nonfinite_joint_limits.json"
    write_json(nonfinite_joint_limits_path, nonfinite_joint_limits)

    invalid_asset_roots = json_clone(ready_payload)
    invalid_asset_roots["asset_roots"] = "assets"
    invalid_asset_roots_path = fixture_dir / "so101_model_bundle.invalid_asset_roots.json"
    write_json(invalid_asset_roots_path, invalid_asset_roots)

    unavailable_asset_root = json_clone(ready_payload)
    unavailable_asset_root["asset_roots"] = [
        str(normalize_path(fixture_dir / "missing_asset_root"))
    ]
    unavailable_asset_root_path = (
        fixture_dir / "so101_model_bundle.unavailable_asset_root.json"
    )
    write_json(unavailable_asset_root_path, unavailable_asset_root)

    file_asset_root = json_clone(ready_payload)
    file_asset_root_path = fixture_dir / "asset_root_is_file.txt"
    file_asset_root_path.write_text("not a directory\n")
    file_asset_root["asset_roots"] = [str(normalize_path(file_asset_root_path))]
    file_asset_root_manifest_path = (
        fixture_dir / "so101_model_bundle.file_asset_root.json"
    )
    write_json(file_asset_root_manifest_path, file_asset_root)

    missing_mesh_dir = output_dir / "fixtures" / "missing_mesh_bundle"
    missing_mesh_model_dir = missing_mesh_dir / "model"
    missing_mesh_model_dir.mkdir(parents=True, exist_ok=True)
    missing_mesh_model_path = missing_mesh_model_dir / "synthetic_so101_missing_mesh.xml"
    missing_mesh_model_path.write_text(ready_model_path.read_text())
    missing_mesh_payload = json_clone(ready_payload)
    missing_mesh_payload["model_path"] = str(normalize_path(missing_mesh_model_path))
    missing_mesh_payload["model_sha256"] = sha256_file(missing_mesh_model_path)
    missing_mesh_payload["asset_roots"] = []
    missing_mesh_manifest_path = missing_mesh_dir / "so101_model_bundle.missing_mesh_assets.json"
    write_json(missing_mesh_manifest_path, missing_mesh_payload)

    reversed_joint_limits = json_clone(ready_payload)
    reversed_joint_limits["joint_limits_deg"]["shoulder_pan"] = [110.0, -110.0]
    reversed_joint_limits_path = fixture_dir / "so101_model_bundle.reversed_joint_limits.json"
    write_json(reversed_joint_limits_path, reversed_joint_limits)

    nonfinite_tcp = json_clone(ready_payload)
    nonfinite_tcp["tcp_offset_m"]["z"] = "Infinity"
    nonfinite_tcp_path = fixture_dir / "so101_model_bundle.nonfinite_tcp_offset.json"
    write_json(nonfinite_tcp_path, nonfinite_tcp)

    out_of_range_tcp = json_clone(ready_payload)
    out_of_range_tcp["tcp_offset_m"]["z"] = 1.25
    out_of_range_tcp_path = fixture_dir / "so101_model_bundle.out_of_range_tcp_offset.json"
    write_json(out_of_range_tcp_path, out_of_range_tcp)

    nonfinite_alignment = json_clone(ready_payload)
    nonfinite_alignment["base_to_board_transform"]["rotation_rpy_rad"]["yaw"] = "NaN"
    nonfinite_alignment_path = fixture_dir / "so101_model_bundle.nonfinite_alignment.json"
    write_json(nonfinite_alignment_path, nonfinite_alignment)

    out_of_range_alignment = json_clone(ready_payload)
    out_of_range_alignment["base_to_board_transform"]["translation_m"] = {
        "x": 2.25,
        "y": 0.0,
        "z": 0.0,
    }
    out_of_range_alignment_path = (
        fixture_dir / "so101_model_bundle.out_of_range_alignment.json"
    )
    write_json(out_of_range_alignment_path, out_of_range_alignment)

    nonstandard_json_constant = json_clone(ready_payload)
    nonstandard_json_constant["tcp_offset_m"]["z"] = float("nan")
    nonstandard_json_constant_path = (
        fixture_dir / "so101_model_bundle.nonstandard_json_constant.json"
    )
    nonstandard_json_constant_path.write_text(
        json.dumps(nonstandard_json_constant, indent=2, sort_keys=True, allow_nan=True) + "\n"
    )

    mismatched_joint_limits = json_clone(ready_payload)
    mismatched_joint_limits["joint_limits_deg"]["shoulder_pan"] = [-90.0, 90.0]
    mismatched_joint_limits_path = fixture_dir / "so101_model_bundle.mismatched_joint_limits.json"
    write_json(mismatched_joint_limits_path, mismatched_joint_limits)

    mismatched_model_sha = json_clone(ready_payload)
    mismatched_model_sha["model_sha256"] = "0" * 64
    mismatched_model_sha_path = fixture_dir / "so101_model_bundle.mismatched_model_sha.json"
    write_json(mismatched_model_sha_path, mismatched_model_sha)

    return {
        "tiny_gripper_range_manifest_path": tiny_gripper_manifest_path,
        "tiny_gripper_range_model_path": tiny_gripper_model_path,
        "unavailable_model_path_manifest_path": unavailable_model_path_manifest_path,
        "nonfinite_joint_limits_manifest_path": nonfinite_joint_limits_path,
        "invalid_asset_roots_manifest_path": invalid_asset_roots_path,
        "unavailable_asset_root_manifest_path": unavailable_asset_root_path,
        "file_asset_root_manifest_path": file_asset_root_manifest_path,
        "missing_mesh_manifest_path": missing_mesh_manifest_path,
        "reversed_joint_limits_manifest_path": reversed_joint_limits_path,
        "nonfinite_tcp_manifest_path": nonfinite_tcp_path,
        "out_of_range_tcp_manifest_path": out_of_range_tcp_path,
        "nonfinite_alignment_manifest_path": nonfinite_alignment_path,
        "out_of_range_alignment_manifest_path": out_of_range_alignment_path,
        "nonstandard_json_constant_manifest_path": nonstandard_json_constant_path,
        "mismatched_joint_limits_manifest_path": mismatched_joint_limits_path,
        "mismatched_model_sha_manifest_path": mismatched_model_sha_path,
    }


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
        "gate_ok",
        "status",
        "manifest_status",
        "model_path_status",
        "model_identity_status",
        "authority_status",
        "provenance_status",
        "asset_roots_status",
        "joint_limits_status",
        "mesh_assets_status",
        "target_frame_status",
        "ready_for_model_backed_ik",
        "model_authority",
        "physical_so101_model_authority_ready",
        "hardware_free_regression_fixture_ready",
        "reviewed_model_motion_checked",
        "simrobot_sync_ok",
        "all_so101_joints_motion_checked",
        "motion_check_joint_names",
        "gripper_motion_check",
        "motion_authority_status",
        "physical_reviewed_model_motion_checked",
        "hardware_free_fixture_motion_checked",
        "motion_evidence_not_physical_so101_authority",
        "downstream_handoff_status",
        "downstream_handoff_ready",
        "fixture_handoff_ready_not_physical_so101_authority",
        "downstream_handoff_csv_exists",
        "downstream_handoff_csv_item_ids",
        "missing_inputs",
        "tcp_offset_status",
        "alignment_status",
        "joint_limit_model_consistency_status",
        "expected_status",
        "summary_path",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def case_specs(fixtures: dict[str, Path]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": "missing_manifest_nonfailing",
            "manifest_path": None,
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
            },
        },
        {
            "case_id": "missing_manifest_require_ready_fails",
            "manifest_path": None,
            "require_ready": True,
            "expect": {
                "return_code": 1,
                "gate_ok": False,
                "status": "reviewed_mujoco_bundle_required_but_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
            },
        },
        {
            "case_id": "placeholder_manifest_not_ready",
            "manifest_path": fixtures["placeholder_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
            },
        },
        {
            "case_id": "placeholder_review_metadata_not_ready",
            "manifest_path": fixtures["placeholder_review_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "needs_review",
                "provenance_status": "present",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "needs_review",
                "alignment_status": "needs_review",
                "missing_inputs_contains": [
                    "authority",
                    "joint_limit_authority",
                    "mesh_asset_authority",
                    "target_frame_authority",
                    "tcp_offset_authority",
                    "base_to_board_alignment_authority",
                ],
                "authority_diagnostics_contains": ["authority_review_evidence_placeholder"],
                "joint_limits_diagnostics_contains": [
                    "joint_limit_authority_review_evidence_placeholder"
                ],
                "mesh_assets_diagnostics_contains": [
                    "mesh_asset_authority_review_evidence_placeholder"
                ],
                "target_frame_diagnostics_contains": [
                    "target_frame_authority_review_evidence_placeholder"
                ],
                "tcp_offset_diagnostics_contains": [
                    "tcp_offset_authority_review_evidence_placeholder"
                ],
                "alignment_diagnostics_contains": [
                    "base_to_board_alignment_authority_review_evidence_placeholder"
                ],
            },
        },
        {
            "case_id": "generic_review_scope_not_ready",
            "manifest_path": fixtures["generic_review_scope_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "needs_review",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "needs_review",
                "alignment_status": "needs_review",
                "missing_inputs_contains": [
                    "authority",
                    "joint_limit_authority",
                    "mesh_asset_authority",
                    "target_frame_authority",
                    "tcp_offset_authority",
                    "base_to_board_alignment_authority",
                ],
                "authority_diagnostics_contains": [
                    "authority_review_scope_missing:model_identity",
                    "authority_review_scope_missing:provenance",
                    "authority_review_scope_missing:license",
                ],
                "joint_limits_diagnostics_contains": [
                    "joint_limit_authority_review_scope_missing:joint_limits"
                ],
                "mesh_assets_diagnostics_contains": [
                    "mesh_asset_authority_review_scope_missing:mesh_assets"
                ],
                "target_frame_diagnostics_contains": [
                    "target_frame_authority_review_scope_missing:target_frame"
                ],
                "tcp_offset_diagnostics_contains": [
                    "tcp_offset_authority_review_scope_missing:tcp_offset"
                ],
                "alignment_diagnostics_contains": [
                    "base_to_board_alignment_authority_review_scope_missing:base_to_board_alignment"
                ],
            },
        },
        {
            "case_id": "pending_review_metadata_not_ready",
            "manifest_path": fixtures["pending_review_metadata_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "needs_review",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "needs_review",
                "alignment_status": "needs_review",
                "missing_inputs_contains": [
                    "authority",
                    "joint_limit_authority",
                    "mesh_asset_authority",
                    "target_frame_authority",
                    "tcp_offset_authority",
                    "base_to_board_alignment_authority",
                ],
                "authority_diagnostics_contains": [
                    "authority_review_evidence_open_work:missing_inputs",
                    "authority_review_evidence_open_work:next_required_action_ids",
                ],
                "joint_limits_diagnostics_contains": [
                    "joint_limit_authority_review_evidence_open_work:next_required_action_ids"
                ],
                "mesh_assets_diagnostics_contains": [
                    "mesh_asset_authority_review_evidence_open_work:next_required_action_ids"
                ],
                "target_frame_diagnostics_contains": [
                    "target_frame_authority_review_evidence_open_work:next_required_action_ids"
                ],
                "tcp_offset_diagnostics_contains": [
                    "tcp_offset_authority_review_evidence_open_work:next_required_action_ids"
                ],
                "alignment_diagnostics_contains": [
                    "base_to_board_alignment_authority_review_evidence_open_work:next_required_action_ids"
                ],
            },
        },
        {
            "case_id": "weak_review_manifest_not_ready",
            "manifest_path": fixtures["weak_review_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "needs_review",
                "provenance_status": "needs_review",
                "joint_limits_status": "present",
                "mesh_assets_status": "present",
                "target_frame_status": "present",
                "tcp_offset_status": "present",
                "alignment_status": "present",
                "missing_inputs_contains": ["authority", "provenance"],
            },
        },
        {
            "case_id": "weak_joint_limit_authority_not_ready",
            "manifest_path": fixtures["weak_joint_limits_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "needs_review",
                "mesh_assets_status": "present",
                "target_frame_status": "present",
                "tcp_offset_status": "present",
                "alignment_status": "present",
                "missing_inputs_contains": ["joint_limit_authority"],
                "joint_limits_diagnostics_contains": [
                    "joint_limit_authority_review_missing"
                ],
            },
        },
        {
            "case_id": "weak_mesh_asset_authority_not_ready",
            "manifest_path": fixtures["weak_mesh_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "present",
                "mesh_assets_status": "needs_review",
                "target_frame_status": "present",
                "tcp_offset_status": "present",
                "alignment_status": "present",
                "missing_inputs_contains": ["mesh_asset_authority"],
                "mesh_assets_diagnostics_contains": [
                    "mesh_asset_authority_review_missing"
                ],
            },
        },
        {
            "case_id": "weak_target_frame_authority_not_ready",
            "manifest_path": fixtures["weak_target_frame_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "present",
                "mesh_assets_status": "present",
                "target_frame_status": "needs_review",
                "tcp_offset_status": "present",
                "alignment_status": "present",
                "missing_inputs_contains": ["target_frame_authority"],
                "target_frame_diagnostics_contains": [
                    "target_frame_authority_review_missing"
                ],
            },
        },
        {
            "case_id": "wrong_target_frame_not_ready",
            "manifest_path": fixtures["wrong_target_frame_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "present",
                "mesh_assets_status": "present",
                "target_frame_status": "invalid",
                "tcp_offset_status": "present",
                "alignment_status": "present",
                "missing_inputs_contains": ["target_frame"],
                "target_frame_diagnostics_contains": ["target_frame_differs_from_default"],
            },
        },
        {
            "case_id": "model_missing_target_frame_not_ready",
            "manifest_path": fixtures["model_missing_target_frame_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "present",
                "mesh_assets_status": "present",
                "target_frame_status": "present",
                "tcp_offset_status": "present",
                "alignment_status": "present",
                "missing_inputs_contains": ["non_blocking_contract_checker_result"],
            },
        },
        {
            "case_id": "weak_tcp_offset_authority_not_ready",
            "manifest_path": fixtures["weak_tcp_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "present",
                "mesh_assets_status": "present",
                "target_frame_status": "present",
                "tcp_offset_status": "needs_review",
                "alignment_status": "present",
                "missing_inputs_contains": ["tcp_offset_authority"],
                "tcp_offset_diagnostics_contains": [
                    "tcp_offset_authority_review_missing"
                ],
            },
        },
        {
            "case_id": "weak_alignment_authority_not_ready",
            "manifest_path": fixtures["weak_alignment_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "authority_status": "present",
                "provenance_status": "present",
                "joint_limits_status": "present",
                "mesh_assets_status": "present",
                "target_frame_status": "present",
                "tcp_offset_status": "present",
                "alignment_status": "needs_review",
                "missing_inputs_contains": ["base_to_board_alignment_authority"],
                "alignment_diagnostics_contains": [
                    "base_to_board_alignment_authority_review_missing"
                ],
            },
        },
        {
            "case_id": "nonstandard_json_constant_parse_error",
            "manifest_path": fixtures["nonstandard_json_constant_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "manifest_status": "model_bundle_manifest_parse_error",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "missing_inputs_contains": ["--manifest-path"],
            },
        },
        {
            "case_id": "unavailable_model_path_not_ready",
            "manifest_path": fixtures["unavailable_model_path_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "model_path_status": "unavailable",
                "model_identity_status": "invalid",
                "missing_inputs_contains": ["model_path", "model_sha256"],
                "model_path_diagnostics_contains": ["model_path_unavailable"],
                "model_identity_diagnostics_contains": [
                    "model_sha256_observed_unavailable"
                ],
            },
        },
        {
            "case_id": "invalid_tcp_offset_shape_not_ready",
            "manifest_path": fixtures["invalid_tcp_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "tcp_offset_status": "invalid",
                "missing_inputs_contains": ["tcp_offset_m"],
                "tcp_offset_diagnostics_contains": ["missing_axis:z"],
            },
        },
        {
            "case_id": "invalid_nonfinite_joint_limits_not_ready",
            "manifest_path": fixtures["nonfinite_joint_limits_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "joint_limits_status": "invalid",
                "missing_inputs_contains": ["joint_limits_deg"],
                "joint_limits_diagnostics_contains": [
                    "joint_limit_invalid:shoulder_pan:joint_limit_non_finite"
                ],
            },
        },
        {
            "case_id": "missing_mesh_assets_not_ready",
            "manifest_path": fixtures["missing_mesh_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "mesh_assets_status": "needs_follow_up",
                "missing_inputs_contains": ["mesh_assets"],
                "mesh_assets_diagnostics_contains": ["missing_asset_count:1"],
            },
        },
        {
            "case_id": "invalid_asset_roots_not_ready",
            "manifest_path": fixtures["invalid_asset_roots_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "asset_roots_status": "invalid",
                "missing_inputs_contains": ["asset_roots"],
                "asset_roots_diagnostics_contains": ["asset_roots_not_list"],
            },
        },
        {
            "case_id": "unavailable_asset_root_not_ready",
            "manifest_path": fixtures["unavailable_asset_root_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "asset_roots_status": "needs_follow_up",
                "missing_inputs_contains": ["asset_roots"],
                "asset_roots_diagnostics_contains": ["asset_root_unavailable"],
            },
        },
        {
            "case_id": "file_asset_root_not_ready",
            "manifest_path": fixtures["file_asset_root_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "asset_roots_status": "needs_follow_up",
                "missing_inputs_contains": ["asset_roots"],
                "asset_roots_diagnostics_contains": ["asset_root_not_directory"],
            },
        },
        {
            "case_id": "invalid_reversed_joint_limits_not_ready",
            "manifest_path": fixtures["reversed_joint_limits_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "joint_limits_status": "invalid",
                "missing_inputs_contains": ["joint_limits_deg"],
                "joint_limits_diagnostics_contains": [
                    "joint_limit_invalid:shoulder_pan:joint_limit_lower_not_below_upper"
                ],
            },
        },
        {
            "case_id": "invalid_nonfinite_tcp_offset_not_ready",
            "manifest_path": fixtures["nonfinite_tcp_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "tcp_offset_status": "invalid",
                "missing_inputs_contains": ["tcp_offset_m"],
                "tcp_offset_diagnostics_contains": ["non_finite_axis:z"],
            },
        },
        {
            "case_id": "invalid_out_of_range_tcp_offset_not_ready",
            "manifest_path": fixtures["out_of_range_tcp_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "tcp_offset_status": "invalid",
                "missing_inputs_contains": ["tcp_offset_m"],
                "tcp_offset_diagnostics_contains": ["tcp_offset_norm_exceeds_limit"],
            },
        },
        {
            "case_id": "invalid_base_to_board_transform_not_ready",
            "manifest_path": fixtures["invalid_alignment_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "alignment_status": "invalid",
                "missing_inputs_contains": ["base_to_board_transform"],
                "alignment_diagnostics_contains": ["base_to_board_rotation_rpy_missing"],
            },
        },
        {
            "case_id": "invalid_nonfinite_base_to_board_transform_not_ready",
            "manifest_path": fixtures["nonfinite_alignment_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "alignment_status": "invalid",
                "missing_inputs_contains": ["base_to_board_transform"],
                "alignment_diagnostics_contains": ["rotation_rpy:non_finite_axis:yaw"],
            },
        },
        {
            "case_id": "invalid_out_of_range_base_to_board_transform_not_ready",
            "manifest_path": fixtures["out_of_range_alignment_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "alignment_status": "invalid",
                "missing_inputs_contains": ["base_to_board_transform"],
                "alignment_diagnostics_contains": [
                    "translation:base_to_board_translation_norm_exceeds_limit"
                ],
            },
        },
        {
            "case_id": "mismatched_model_sha_not_ready",
            "manifest_path": fixtures["mismatched_model_sha_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_not_ready",
                "ready_for_model_backed_ik": False,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "not_checked_manifest_not_ready",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "model_identity_status": "invalid",
                "missing_inputs_contains": ["model_sha256"],
                "model_identity_diagnostics_contains": ["model_sha256_mismatch"],
            },
        },
        {
            "case_id": "ready_manifest_mismatched_mujoco_joint_limits",
            "manifest_path": fixtures["mismatched_joint_limits_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 1,
                "gate_ok": False,
                "status": "reviewed_mujoco_bundle_motion_failed",
                "ready_for_model_backed_ik": True,
                "model_authority": (
                    "hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_so101_model_authority_ready": False,
                "hardware_free_regression_fixture_ready": True,
                "reviewed_model_motion_checked": False,
                "motion_authority_status": "hardware_free_fixture_motion_failed",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "missing_inputs_contains": ["joint_limit_model_consistency"],
                "joint_limit_model_consistency_status": "joint_limits_mismatch_mujoco_model",
                "joint_limit_model_consistency_diagnostics_contains": [
                    "joint_limit_mismatch:shoulder_pan"
                ],
            },
        },
        {
            "case_id": "ready_manifest_gripper_range_not_moving",
            "manifest_path": fixtures["tiny_gripper_range_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 1,
                "gate_ok": False,
                "status": "reviewed_mujoco_bundle_motion_failed",
                "ready_for_model_backed_ik": True,
                "model_authority": (
                    "hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_so101_model_authority_ready": False,
                "hardware_free_regression_fixture_ready": True,
                "reviewed_model_motion_checked": False,
                "simrobot_sync_ok": False,
                "all_so101_joints_motion_checked": True,
                "motion_check_joint_names": list(EXPECTED_MOTION_CHECK_JOINTS),
                "gripper_motion_check": {
                    "ok": False,
                    "target_ok": True,
                    "moved": False,
                    "range_ok": False,
                },
                "motion_authority_status": "hardware_free_fixture_motion_failed",
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": False,
                "motion_evidence_not_physical_so101_authority": False,
                "missing_inputs_contains": ["simrobot_mujoco_joint_motion"],
            },
        },
        {
            "case_id": "ready_synthetic_fixture_motion_not_physical",
            "manifest_path": fixtures["ready_manifest_path"],
            "require_ready": False,
            "expect": {
                "return_code": 0,
                "gate_ok": True,
                "status": "reviewed_mujoco_bundle_motion_checked",
                "ready_for_model_backed_ik": True,
                "model_authority": (
                    "hardware_free_regression_fixture_not_physical_so101_authority"
                ),
                "physical_so101_model_authority_ready": False,
                "hardware_free_regression_fixture_ready": True,
                "reviewed_model_motion_checked": True,
                "simrobot_sync_ok": True,
                "all_so101_joints_motion_checked": True,
                "motion_check_joint_names": list(EXPECTED_MOTION_CHECK_JOINTS),
                "gripper_motion_check": {
                    "ok": True,
                    "target_ok": True,
                    "moved": True,
                    "range_ok": True,
                },
                "motion_authority_status": (
                    "hardware_free_fixture_motion_checked_not_physical_so101_authority"
                ),
                "physical_reviewed_model_motion_checked": False,
                "hardware_free_fixture_motion_checked": True,
                "motion_evidence_not_physical_so101_authority": True,
            },
        },
    ]


def run_case(
    *,
    spec: dict[str, Any],
    python_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = str(spec["case_id"])
    case_dir = output_dir / "cases" / case_id
    summary_path = case_dir / "so101_reviewed_mujoco_bundle_summary.json"
    python_executable = executable_arg(python_path)
    command = [
        python_executable,
        str(REVIEWED_MUJOCO_SCRIPT),
        "--output-dir",
        str(case_dir),
        "--python",
        python_executable,
    ]
    manifest_path = spec.get("manifest_path")
    if isinstance(manifest_path, Path):
        command.extend(["--manifest-path", str(manifest_path)])
    if spec.get("require_ready") is True:
        command.append("--require-ready-reviewed-model")

    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout_path = case_dir / f"{case_id}_stdout.txt"
    stderr_path = case_dir / f"{case_id}_stderr.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)

    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        summary = {
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
    return record, summary


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def read_motion_checks_csv(path: Path) -> tuple[list[dict[str, str]], str | None]:
    try:
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle)), None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def expected_downstream_handoff_status(summary: dict[str, Any]) -> str:
    if summary.get("physical_reviewed_model_motion_checked") is True:
        return "physical_reviewed_mujoco_handoff_ready"
    if summary.get("hardware_free_fixture_motion_checked") is True:
        return "fixture_mujoco_handoff_ready_not_physical_authority"
    if summary.get("ready_for_model_backed_ik") is True:
        return "manifest_ready_motion_handoff_blocked"
    return "waiting_for_reviewed_bundle_authority"


def summarize_case(
    *,
    record: dict[str, Any],
    summary: dict[str, Any],
    expect: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    case_id = str(record["case_id"])
    add_error(errors, f"{case_id}.return_code", record.get("return_code"), expect["return_code"])
    add_error(errors, f"{case_id}.gate_ok", summary.get("ok"), expect["gate_ok"])
    for key in (
        "status",
        "manifest_status",
        "ready_for_model_backed_ik",
        "model_authority",
        "physical_so101_model_authority_ready",
        "hardware_free_regression_fixture_ready",
        "reviewed_model_motion_checked",
        "motion_authority_status",
        "physical_reviewed_model_motion_checked",
        "hardware_free_fixture_motion_checked",
        "motion_evidence_not_physical_so101_authority",
    ):
        if key in expect:
            add_error(errors, f"{case_id}.{key}", summary.get(key), expect[key])

    motion_authority = summary.get("motion_authority")
    if not isinstance(motion_authority, dict):
        errors.append(f"{case_id}.motion_authority: expected dict")
    else:
        add_error(
            errors,
            f"{case_id}.motion_authority_status_nested",
            motion_authority.get("status"),
            summary.get("motion_authority_status"),
        )
        add_error(
            errors,
            f"{case_id}.physical_motion_nested",
            motion_authority.get("physical_reviewed_model_motion_checked"),
            summary.get("physical_reviewed_model_motion_checked"),
        )
        add_error(
            errors,
            f"{case_id}.fixture_motion_nested",
            motion_authority.get("hardware_free_fixture_motion_checked"),
            summary.get("hardware_free_fixture_motion_checked"),
        )

    if "missing_inputs_contains" in expect:
        missing_inputs = summary.get("missing_inputs")
        if not isinstance(missing_inputs, list):
            errors.append(f"{case_id}.missing_inputs: expected list, got {missing_inputs!r}")
        else:
            for expected_input in expect["missing_inputs_contains"]:
                if expected_input not in missing_inputs:
                    errors.append(
                        f"{case_id}.missing_inputs: missing {expected_input!r} in {missing_inputs!r}"
                    )
    for expect_key, summary_key in (
        ("model_path_status", "model_path"),
        ("model_identity_status", "model_identity"),
        ("authority_status", "authority"),
        ("provenance_status", "provenance"),
        ("asset_roots_status", "asset_roots"),
        ("joint_limits_status", "joint_limits"),
        ("mesh_assets_status", "mesh_assets"),
        ("target_frame_status", "target_frame"),
        ("joint_limit_model_consistency_status", "joint_limit_model_consistency"),
    ):
        if expect_key in expect:
            add_error(
                errors,
                f"{case_id}.{expect_key}",
                (summary.get(summary_key) or {}).get("status"),
                expect[expect_key],
            )
    if "tcp_offset_status" in expect:
        add_error(
            errors,
            f"{case_id}.tcp_offset_status",
            (summary.get("tcp_offset") or {}).get("status"),
            expect["tcp_offset_status"],
        )
    if "alignment_status" in expect:
        add_error(
            errors,
            f"{case_id}.alignment_status",
            (summary.get("base_to_board_alignment") or {}).get("status"),
            expect["alignment_status"],
        )
    for diagnostics_key, summary_key in (
        ("model_path_diagnostics_contains", "model_path"),
        ("model_identity_diagnostics_contains", "model_identity"),
        ("authority_diagnostics_contains", "authority"),
        ("provenance_diagnostics_contains", "provenance"),
        ("asset_roots_diagnostics_contains", "asset_roots"),
        ("joint_limits_diagnostics_contains", "joint_limits"),
        ("mesh_assets_diagnostics_contains", "mesh_assets"),
        ("target_frame_diagnostics_contains", "target_frame"),
        ("tcp_offset_diagnostics_contains", "tcp_offset"),
        ("alignment_diagnostics_contains", "base_to_board_alignment"),
        ("joint_limit_model_consistency_diagnostics_contains", "joint_limit_model_consistency"),
    ):
        if diagnostics_key not in expect:
            continue
        diagnostics = (summary.get(summary_key) or {}).get("diagnostics")
        diagnostics_text = "\n".join(str(item) for item in diagnostics or [])
        for expected_diagnostic in expect[diagnostics_key]:
            if expected_diagnostic not in diagnostics_text:
                errors.append(
                    f"{case_id}.{summary_key}.diagnostics: missing {expected_diagnostic!r} in {diagnostics!r}"
                )

    if summary.get("ready_for_model_backed_ik") is not True:
        add_error(
            errors,
            f"{case_id}.mujoco_load_absent_when_not_ready",
            "mujoco_model_load" in summary,
            False,
        )
        add_error(
            errors,
            f"{case_id}.simrobot_absent_when_not_ready",
            "sim_robot_mujoco_sync" in summary,
            False,
        )
    if summary.get("ready_for_model_backed_ik") is True:
        model_load = summary.get("mujoco_model_load")
        sim_sync = summary.get("sim_robot_mujoco_sync")
        if not isinstance(model_load, dict) or model_load.get("ok") is not True:
            errors.append(f"{case_id}.mujoco_model_load: expected ok true")
        expected_sync_ok = expect.get("simrobot_sync_ok", True)
        actual_sync_ok = sim_sync.get("ok") if isinstance(sim_sync, dict) else None
        add_error(
            errors,
            f"{case_id}.simrobot_sync_ok",
            actual_sync_ok,
            expected_sync_ok,
        )
    sim_sync = summary.get("sim_robot_mujoco_sync")
    sim_sync = sim_sync if isinstance(sim_sync, dict) else {}
    if "all_so101_joints_motion_checked" in expect:
        add_error(
            errors,
            f"{case_id}.all_so101_joints_motion_checked",
            sim_sync.get("all_so101_joints_motion_checked"),
            expect["all_so101_joints_motion_checked"],
        )
    if "motion_check_joint_names" in expect:
        add_error(
            errors,
            f"{case_id}.motion_check_joint_names",
            sim_sync.get("motion_check_joint_names"),
            expect["motion_check_joint_names"],
        )
    motion_checks = sim_sync.get("motion_checks")
    motion_checks = motion_checks if isinstance(motion_checks, list) else []
    gripper_motion_checks = [
        check
        for check in motion_checks
        if isinstance(check, dict) and check.get("joint") == "gripper"
    ]
    gripper_motion_check = gripper_motion_checks[0] if gripper_motion_checks else {}
    if "gripper_motion_check" in expect:
        for key, expected_value in expect["gripper_motion_check"].items():
            add_error(
                errors,
                f"{case_id}.gripper_motion_check.{key}",
                gripper_motion_check.get(key),
                expected_value,
            )

    artifacts = summary.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    motion_checks_csv_path_raw = artifacts.get("motion_checks_csv")
    motion_checks_csv_path = (
        Path(motion_checks_csv_path_raw)
        if isinstance(motion_checks_csv_path_raw, str) and motion_checks_csv_path_raw
        else None
    )
    motion_checks_csv_exists = (
        motion_checks_csv_path is not None and motion_checks_csv_path.is_file()
    )
    motion_checks_csv_rows: list[dict[str, str]] = []
    motion_checks_csv_error: str | None = None
    if not motion_checks_csv_exists:
        errors.append(f"{case_id}.motion_checks_csv: expected file at {motion_checks_csv_path_raw!r}")
    else:
        motion_checks_csv_rows, motion_checks_csv_error = read_motion_checks_csv(
            motion_checks_csv_path
        )
        if motion_checks_csv_error is not None:
            errors.append(f"{case_id}.motion_checks_csv: {motion_checks_csv_error}")
    expected_motion_joints = sorted(EXPECTED_MOTION_CHECK_JOINTS)
    motion_checks_csv_joint_names = sorted(
        row.get("joint", "")
        for row in motion_checks_csv_rows
        if row.get("joint")
    )
    if motion_checks_csv_rows:
        add_error(
            errors,
            f"{case_id}.motion_checks_csv_joint_names",
            motion_checks_csv_joint_names,
            expected_motion_joints,
        )
        motion_checks_csv_statuses = [
            row.get("status", "") for row in motion_checks_csv_rows
        ]
        if summary.get("ready_for_model_backed_ik") is not True:
            add_error(
                errors,
                f"{case_id}.motion_checks_csv_statuses",
                sorted(set(motion_checks_csv_statuses)),
                ["not_attempted_manifest_not_ready"],
            )
        elif motion_checks:
            expected_from_summary = sorted(
                str(check.get("joint"))
                for check in motion_checks
                if isinstance(check, dict) and check.get("joint")
            )
            add_error(
                errors,
                f"{case_id}.motion_checks_csv_matches_summary_joints",
                motion_checks_csv_joint_names,
                expected_from_summary,
            )
            if summary.get("reviewed_model_motion_checked") is True:
                add_error(
                    errors,
                    f"{case_id}.motion_checks_csv_statuses",
                    sorted(set(motion_checks_csv_statuses)),
                    ["motion_checked"],
                )
            else:
                unexpected_statuses = sorted(
                    set(motion_checks_csv_statuses)
                    - {"motion_checked", "motion_check_failed"}
                )
                add_error(
                    errors,
                    f"{case_id}.motion_checks_csv_unexpected_statuses",
                    unexpected_statuses,
                    [],
                )
        else:
            add_error(
                errors,
                f"{case_id}.motion_checks_csv_statuses",
                sorted(set(motion_checks_csv_statuses)),
                ["motion_not_attempted_ready_manifest"],
            )

    downstream_handoff_json_path_raw = artifacts.get("downstream_handoff_json")
    downstream_handoff_json_path = (
        Path(downstream_handoff_json_path_raw)
        if isinstance(downstream_handoff_json_path_raw, str)
        and downstream_handoff_json_path_raw
        else None
    )
    downstream_handoff_csv_path_raw = artifacts.get("downstream_handoff_csv")
    downstream_handoff_csv_path = (
        Path(downstream_handoff_csv_path_raw)
        if isinstance(downstream_handoff_csv_path_raw, str)
        and downstream_handoff_csv_path_raw
        else None
    )
    downstream_handoff_csv_rows: list[dict[str, str]] = []
    downstream_handoff_csv_error: str | None = None
    downstream_handoff = {}
    if downstream_handoff_json_path is None or not downstream_handoff_json_path.is_file():
        errors.append(
            f"{case_id}.downstream_handoff_json: expected file at {downstream_handoff_json_path_raw!r}"
        )
    else:
        try:
            downstream_handoff = json.loads(downstream_handoff_json_path.read_text())
        except Exception as exc:
            errors.append(f"{case_id}.downstream_handoff_json: {type(exc).__name__}: {exc}")
            downstream_handoff = {}
    downstream_handoff_csv_exists = (
        downstream_handoff_csv_path is not None and downstream_handoff_csv_path.is_file()
    )
    if not downstream_handoff_csv_exists:
        errors.append(
            f"{case_id}.downstream_handoff_csv: expected file at {downstream_handoff_csv_path_raw!r}"
        )
    else:
        downstream_handoff_csv_rows, downstream_handoff_csv_error = read_motion_checks_csv(
            downstream_handoff_csv_path
        )
        if downstream_handoff_csv_error is not None:
            errors.append(
                f"{case_id}.downstream_handoff_csv: {downstream_handoff_csv_error}"
            )
    expected_handoff_status = expected_downstream_handoff_status(summary)
    add_error(
        errors,
        f"{case_id}.downstream_handoff_status",
        summary.get("downstream_handoff_status"),
        expected_handoff_status,
    )
    add_error(
        errors,
        f"{case_id}.downstream_handoff_ready",
        summary.get("downstream_handoff_ready"),
        summary.get("physical_reviewed_model_motion_checked") is True,
    )
    add_error(
        errors,
        f"{case_id}.fixture_handoff_ready_not_physical_so101_authority",
        summary.get("fixture_handoff_ready_not_physical_so101_authority"),
        summary.get("hardware_free_fixture_motion_checked") is True,
    )
    if downstream_handoff:
        add_error(
            errors,
            f"{case_id}.downstream_handoff_json.status",
            downstream_handoff.get("status"),
            expected_handoff_status,
        )
        add_error(
            errors,
            f"{case_id}.downstream_handoff_json.model_authority",
            downstream_handoff.get("model_authority"),
            "downstream_handoff_not_authority",
        )
        add_error(
            errors,
            f"{case_id}.downstream_handoff_json.physical_so101_truth_claimed",
            downstream_handoff.get("physical_so101_truth_claimed"),
            False,
        )
        add_error(
            errors,
            f"{case_id}.downstream_handoff_json.observed_evidence_is_authority",
            downstream_handoff.get("observed_evidence_is_authority"),
            False,
        )
        if "downstream_gate_handoff" not in set(
            downstream_handoff.get("handoff_item_ids") or []
        ):
            errors.append(
                f"{case_id}.downstream_handoff_json.handoff_item_ids: missing downstream_gate_handoff"
            )
        if downstream_handoff_csv_rows:
            add_error(
                errors,
                f"{case_id}.downstream_handoff_csv_count",
                len(downstream_handoff_csv_rows),
                downstream_handoff.get("handoff_item_count"),
            )
    downstream_handoff_csv_item_ids = sorted(
        row.get("handoff_key", "")
        for row in downstream_handoff_csv_rows
        if row.get("handoff_key")
    )
    if downstream_handoff_csv_rows and "downstream_gate_handoff" not in set(
        downstream_handoff_csv_item_ids
    ):
        errors.append(
            f"{case_id}.downstream_handoff_csv: missing downstream_gate_handoff row"
        )

    return {
        "case_id": case_id,
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "record": record,
        "summary_path": record["summary_path"],
        "observations": {
            "gate_ok": summary.get("ok"),
            "status": summary.get("status"),
            "manifest_status": summary.get("manifest_status"),
            "model_path_status": (summary.get("model_path") or {}).get("status"),
            "model_path_diagnostics": (summary.get("model_path") or {}).get("diagnostics"),
            "model_identity_status": (summary.get("model_identity") or {}).get("status"),
            "model_identity_diagnostics": (summary.get("model_identity") or {}).get("diagnostics"),
            "authority_status": (summary.get("authority") or {}).get("status"),
            "provenance_status": (summary.get("provenance") or {}).get("status"),
            "asset_roots_status": (summary.get("asset_roots") or {}).get("status"),
            "asset_roots_diagnostics": (summary.get("asset_roots") or {}).get("diagnostics"),
            "joint_limits_status": (summary.get("joint_limits") or {}).get("status"),
            "joint_limits_diagnostics": (summary.get("joint_limits") or {}).get("diagnostics"),
            "mesh_assets_status": (summary.get("mesh_assets") or {}).get("status"),
            "mesh_assets_diagnostics": (summary.get("mesh_assets") or {}).get("diagnostics"),
            "target_frame_status": (summary.get("target_frame") or {}).get("status"),
            "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
            "model_authority": summary.get("model_authority"),
            "physical_so101_model_authority_ready": summary.get(
                "physical_so101_model_authority_ready"
            ),
            "hardware_free_regression_fixture_ready": summary.get(
                "hardware_free_regression_fixture_ready"
            ),
            "reviewed_model_motion_checked": summary.get("reviewed_model_motion_checked"),
            "simrobot_sync_ok": sim_sync.get("ok"),
            "all_so101_joints_motion_checked": sim_sync.get(
                "all_so101_joints_motion_checked"
            ),
            "motion_check_joint_names": sim_sync.get("motion_check_joint_names"),
            "motion_checks_csv_exists": motion_checks_csv_exists,
            "motion_checks_csv_path": str(motion_checks_csv_path)
            if motion_checks_csv_path is not None
            else None,
            "motion_checks_csv_joint_names": motion_checks_csv_joint_names,
            "motion_checks_csv_statuses": [
                row.get("status", "") for row in motion_checks_csv_rows
            ],
            "gripper_motion_check": gripper_motion_check,
            "motion_authority_status": summary.get("motion_authority_status"),
            "physical_reviewed_model_motion_checked": summary.get(
                "physical_reviewed_model_motion_checked"
            ),
            "hardware_free_fixture_motion_checked": summary.get(
                "hardware_free_fixture_motion_checked"
            ),
            "motion_evidence_not_physical_so101_authority": summary.get(
                "motion_evidence_not_physical_so101_authority"
            ),
            "downstream_handoff_status": summary.get("downstream_handoff_status"),
            "downstream_handoff_ready": summary.get("downstream_handoff_ready"),
            "fixture_handoff_ready_not_physical_so101_authority": summary.get(
                "fixture_handoff_ready_not_physical_so101_authority"
            ),
            "downstream_handoff_csv_exists": downstream_handoff_csv_exists,
            "downstream_handoff_csv_path": str(downstream_handoff_csv_path)
            if downstream_handoff_csv_path is not None
            else None,
            "downstream_handoff_csv_item_ids": downstream_handoff_csv_item_ids,
            "missing_inputs": summary.get("missing_inputs"),
            "tcp_offset_status": (summary.get("tcp_offset") or {}).get("status"),
            "tcp_offset_diagnostics": (summary.get("tcp_offset") or {}).get("diagnostics"),
            "alignment_status": (summary.get("base_to_board_alignment") or {}).get("status"),
            "alignment_diagnostics": (summary.get("base_to_board_alignment") or {}).get("diagnostics"),
            "joint_limit_model_consistency_status": (
                summary.get("joint_limit_model_consistency") or {}
            ).get("status"),
            "joint_limit_model_consistency_diagnostics": (
                summary.get("joint_limit_model_consistency") or {}
            ).get("diagnostics"),
            "artifacts": summary.get("artifacts"),
        },
    }


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    observations = case["observations"]
    expected = case["expected"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "return_code": case["record"].get("return_code"),
        "expected_return_code": expected.get("return_code"),
        "gate_ok": observations.get("gate_ok"),
        "status": observations.get("status"),
        "manifest_status": observations.get("manifest_status"),
        "model_path_status": observations.get("model_path_status"),
        "model_identity_status": observations.get("model_identity_status"),
        "authority_status": observations.get("authority_status"),
        "provenance_status": observations.get("provenance_status"),
        "asset_roots_status": observations.get("asset_roots_status"),
        "joint_limits_status": observations.get("joint_limits_status"),
        "mesh_assets_status": observations.get("mesh_assets_status"),
        "target_frame_status": observations.get("target_frame_status"),
        "ready_for_model_backed_ik": observations.get("ready_for_model_backed_ik"),
        "model_authority": observations.get("model_authority"),
        "physical_so101_model_authority_ready": observations.get(
            "physical_so101_model_authority_ready"
        ),
        "hardware_free_regression_fixture_ready": observations.get(
            "hardware_free_regression_fixture_ready"
        ),
        "reviewed_model_motion_checked": observations.get("reviewed_model_motion_checked"),
        "simrobot_sync_ok": observations.get("simrobot_sync_ok"),
        "all_so101_joints_motion_checked": observations.get(
            "all_so101_joints_motion_checked"
        ),
        "motion_check_joint_names": observations.get("motion_check_joint_names"),
        "motion_checks_csv_exists": observations.get("motion_checks_csv_exists"),
        "motion_checks_csv_joint_names": observations.get("motion_checks_csv_joint_names"),
        "motion_checks_csv_statuses": observations.get("motion_checks_csv_statuses"),
        "gripper_motion_check": observations.get("gripper_motion_check"),
        "motion_authority_status": observations.get("motion_authority_status"),
        "physical_reviewed_model_motion_checked": observations.get(
            "physical_reviewed_model_motion_checked"
        ),
        "hardware_free_fixture_motion_checked": observations.get(
            "hardware_free_fixture_motion_checked"
        ),
        "motion_evidence_not_physical_so101_authority": observations.get(
            "motion_evidence_not_physical_so101_authority"
        ),
        "downstream_handoff_status": observations.get("downstream_handoff_status"),
        "downstream_handoff_ready": observations.get("downstream_handoff_ready"),
        "fixture_handoff_ready_not_physical_so101_authority": observations.get(
            "fixture_handoff_ready_not_physical_so101_authority"
        ),
        "downstream_handoff_csv_exists": observations.get(
            "downstream_handoff_csv_exists"
        ),
        "downstream_handoff_csv_item_ids": observations.get(
            "downstream_handoff_csv_item_ids"
        ),
        "missing_inputs": observations.get("missing_inputs"),
        "tcp_offset_status": observations.get("tcp_offset_status"),
        "alignment_status": observations.get("alignment_status"),
        "joint_limit_model_consistency_status": observations.get(
            "joint_limit_model_consistency_status"
        ),
        "expected_status": expected.get("status"),
        "summary_path": case["summary_path"],
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Reviewed MuJoCo Bundle Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "Synthetic fixture caveat: ready fixture manifests are automation fixtures only. They prove MuJoCo load and SimRobot motion plumbing, not reviewed physical SO-101 authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Gate OK | Ready | Motion | Motion Authority | Physical Motion | Fixture Motion | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        obs = case["observations"]
        lines.append(
            "| `{case_id}` | `{status}` | `{gate_ok}` | `{ready}` | `{motion}` | `{authority}` | `{physical}` | `{fixture}` | `{summary_path}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                gate_ok=obs.get("gate_ok"),
                ready=obs.get("ready_for_model_backed_ik"),
                motion=obs.get("reviewed_model_motion_checked"),
                authority=obs.get("motion_authority_status"),
                physical=obs.get("physical_reviewed_model_motion_checked"),
                fixture=obs.get("hardware_free_fixture_motion_checked"),
                summary_path=case["summary_path"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Missing or not-ready manifests must not attempt MuJoCo motion.",
            "- Generic or missing field-specific review scopes must keep the manifest not-ready before MuJoCo motion.",
            "- The `--require-ready-reviewed-model` case must fail closed when no ready manifest exists.",
            "- The tiny-gripper-range fixture must reach manifest readiness but fail the SimRobot motion gate on `simrobot_mujoco_joint_motion`.",
            "- Ready synthetic fixture motion must remain `hardware_free_fixture_motion_checked_not_physical_so101_authority`.",
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

    fixtures = create_fixtures(output_dir)
    fixtures.update(create_invalid_numeric_fixtures(output_dir, fixtures))
    cases: list[dict[str, Any]] = []
    for spec in case_specs(fixtures):
        record, summary = run_case(
            spec=spec,
            python_path=args.python,
            output_dir=output_dir,
        )
        cases.append(summarize_case(record=record, summary=summary, expect=spec["expect"]))

    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_reviewed_mujoco_bundle_matrix_summary.json"
    csv_path = output_dir / "so101_reviewed_mujoco_bundle_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "reviewed_mujoco_bundle_matrix_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "fixtures": {key: str(normalize_path(value)) for key, value in fixtures.items()},
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "Synthetic fixture manifests live under the smoke output directory and are not physical SO-101 calibration truth.",
            "The ready fixture case exercises reviewed-bundle MuJoCo/SimRobot plumbing only.",
            "This smoke does not open robot hardware, cameras, GUI flows, network resources, or LLM/OpenAI paths.",
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
