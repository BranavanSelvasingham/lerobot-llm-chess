#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
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
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.sim.mujoco_scene import SO101DevelopmentMJCFConfig, build_so101_development_mjcf

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
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help=(
            "Run only the named case id. Repeat for multiple cases. "
            "By default all forwarding cases run."
        ),
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


def write_manifest_json(path: Path, payload: dict[str, Any], model_path: Path) -> None:
    payload["model_sha256"] = sha256_file(model_path)
    write_json(path, payload)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "case_id",
        "ok",
        "suite_status",
        "bundle_ready",
        "model_identity_status",
        "authority_status",
        "provenance_status",
        "joint_limits_status",
        "mesh_assets_status",
        "target_frame_status",
        "tcp_offset_status",
        "alignment_status",
        "missing_inputs",
        "reviewed_mujoco_status",
        "reviewed_model_motion_checked",
        "motion_authority_status",
        "physical_reviewed_model_motion_checked",
        "hardware_free_fixture_motion_checked",
        "motion_evidence_not_physical_so101_authority",
        "forwarding_diagnostic_only",
        "diagnostic_only_reason",
        "ik_model_path_source",
        "ik_model_asset_root_source",
        "source_inventory_used_bundle",
        "source_inventory_diagnostic_only_reason",
        "source_inventory_requires_physical_authority",
        "source_inventory_physical_authority_ready",
        "source_inventory_fixture_ready",
        "source_inventory_model_source_root_source",
        "source_inventory_authoritative_model_path_source",
        "source_authority_review_source",
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
        f"- `missing_model_file_manifest`: `{summary['fixtures']['missing_model_file_manifest_path']}`",
        f"- `model_path_directory_manifest`: `{summary['fixtures']['model_path_directory_manifest_path']}`",
        f"- `invalid_asset_roots_manifest`: `{summary['fixtures']['invalid_asset_roots_manifest_path']}`",
        f"- `unavailable_asset_root_manifest`: `{summary['fixtures']['unavailable_asset_root_manifest_path']}`",
        f"- `file_asset_root_manifest`: `{summary['fixtures']['file_asset_root_manifest_path']}`",
        f"- `mismatched_model_sha_manifest`: `{summary['fixtures']['mismatched_model_sha_manifest_path']}`",
        f"- `placeholder_manifest`: `{summary['fixtures']['placeholder_manifest_path']}`",
        f"- `placeholder_review_manifest`: `{summary['fixtures']['placeholder_review_manifest_path']}`",
        f"- `thin_review_manifest`: `{summary['fixtures']['thin_review_manifest_path']}`",
        f"- `invalid_review_url_manifest`: `{summary['fixtures']['invalid_review_url_manifest_path']}`",
        f"- `generic_review_scope_manifest`: `{summary['fixtures']['generic_review_scope_manifest_path']}`",
        f"- `pending_review_metadata_manifest`: `{summary['fixtures']['pending_review_metadata_manifest_path']}`",
        f"- `weak_review_manifest`: `{summary['fixtures']['weak_review_manifest_path']}`",
        f"- `placeholder_provenance_manifest`: `{summary['fixtures']['placeholder_provenance_manifest_path']}`",
        f"- `invalid_provenance_url_manifest`: `{summary['fixtures']['invalid_provenance_url_manifest_path']}`",
        f"- `fixture_provenance_reviewed_authority_manifest`: `{summary['fixtures']['fixture_provenance_reviewed_authority_manifest_path']}`",
        f"- `weak_joint_limits_manifest`: `{summary['fixtures']['weak_joint_limits_manifest_path']}`",
        f"- `weak_mesh_manifest`: `{summary['fixtures']['weak_mesh_manifest_path']}`",
        f"- `weak_target_frame_manifest`: `{summary['fixtures']['weak_target_frame_manifest_path']}`",
        f"- `wrong_target_frame_manifest`: `{summary['fixtures']['wrong_target_frame_manifest_path']}`",
        f"- `model_missing_target_frame_manifest`: `{summary['fixtures']['model_missing_target_frame_manifest_path']}`",
        f"- `weak_tcp_manifest`: `{summary['fixtures']['weak_tcp_manifest_path']}`",
        f"- `invalid_tcp_manifest`: `{summary['fixtures']['invalid_tcp_manifest_path']}`",
        f"- `weak_alignment_manifest`: `{summary['fixtures']['weak_alignment_manifest_path']}`",
        f"- `invalid_alignment_manifest`: `{summary['fixtures']['invalid_alignment_manifest_path']}`",
        f"- `explicit_model_path`: `{summary['fixtures']['explicit_model_path']}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "## Cases",
        "",
        "| Case | Status | Model Identity | Authority | Provenance | Joint Limits | Mesh Assets | Target Frame | TCP | Alignment | Reviewed MuJoCo | Motion Authority | Forwarding | Artifact index missing | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        forwarding = case["observations"]["bundle_forwarding"]
        reviewed_mujoco = case["observations"]["reviewed_mujoco_bundle"]
        lines.append(
            "| `{case_id}` | `{status}` | `{model_identity}` | `{authority}` | `{provenance}` | `{joint_limits}` | `{mesh_assets}` | `{target_frame}` | `{tcp}` | `{alignment}` | `{reviewed_status}`, motion `{motion}` | `{motion_authority}` | source `{source}`, diagnostic `{diagnostic}` | `{missing}` | `{summary_path}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                model_identity=case["observations"].get("bundle_model_identity_status"),
                authority=case["observations"].get("bundle_authority_status"),
                provenance=case["observations"].get("bundle_provenance_status"),
                joint_limits=case["observations"].get("bundle_joint_limits_status"),
                mesh_assets=case["observations"].get("bundle_mesh_assets_status"),
                target_frame=case["observations"].get("bundle_target_frame_status"),
                tcp=case["observations"].get("bundle_tcp_offset_status"),
                alignment=case["observations"].get("bundle_alignment_status"),
                reviewed_status=reviewed_mujoco.get("status"),
                motion=reviewed_mujoco.get("reviewed_model_motion_checked"),
                motion_authority=reviewed_mujoco.get("motion_authority_status"),
                source=forwarding.get("ik_model_path_source"),
                diagnostic=forwarding.get("diagnostic_only"),
                missing=case["observations"].get("artifact_index_missing_count"),
                summary_path=case["summary_path"],
            )
        )
    path.write_text("\n".join(lines) + "\n")


def obj_text() -> str:
    return """v 0 0 0
v 0.01 0 0
v 0 0.01 0
v 0 0 0.01
f 1 2 3
f 1 3 4
f 1 4 2
f 2 4 3
"""


def mjcf_with_mesh_reference() -> str:
    root = ET.fromstring(
        build_so101_development_mjcf(
            SO101DevelopmentMJCFConfig(model_name="synthetic_so101_reviewed_mujoco_fixture")
        )
    )
    asset = root.find("asset")
    if asset is None:
        asset = ET.SubElement(root, "asset")
    ET.SubElement(
        asset,
        "mesh",
        {
            "name": "synthetic_gripper_shell",
            "file": "meshes/synthetic_gripper_shell.obj",
        },
    )
    return ET.tostring(root, encoding="unicode")


def mjcf_missing_target_frame_with_mesh_reference() -> str:
    root = ET.fromstring(mjcf_with_mesh_reference())
    for parent in root.iter():
        for child in list(parent):
            if child.attrib.get("name") == EXPECTED_TARGET_FRAME:
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def mjcf_with_unexpected_joint_reference() -> str:
    root = ET.fromstring(mjcf_with_mesh_reference())
    worldbody = root.find("worldbody")
    if worldbody is None:
        worldbody = ET.SubElement(root, "worldbody")
    aux_body = ET.SubElement(
        worldbody,
        "body",
        {"name": "unknown_aux_link", "pos": "0 0 0"},
    )
    ET.SubElement(
        aux_body,
        "joint",
        {
            "name": "unknown_aux_joint",
            "type": "hinge",
            "axis": "0 0 1",
            "range": "-1 1",
            "limited": "true",
        },
    )
    return ET.tostring(root, encoding="unicode")


def synthetic_urdf(*, include_mesh: bool) -> str:
    visual = ""
    if include_mesh:
        visual = """
    <visual>
      <geometry>
        <mesh filename="meshes/synthetic_gripper_shell.obj"/>
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


def manifest_payload(*, ready: bool, model_filename: str = "synthetic_so101.urdf") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_path": f"model/{model_filename}",
        "asset_roots": ["assets"],
        "authority": {
            "source_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-16",
            "review_id": "bundle-ready-forwarding:source-authority",
            "review_scopes": ["model_identity", "provenance", "license"],
            "scope": "hardware-free forwarding regression only",
        },
        "provenance": {
            "source_path": "local synthetic fixture",
            "source_commit": "not_applicable",
            "export_tool": "smoke_sim_so101_bundle_ready_forwarding.py",
            "license": "test-only",
        },
        "target_frame": EXPECTED_TARGET_FRAME,
        "target_frame_authority": {
            "target_frame_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:target-frame",
            "review_scope": "target_frame",
            "scope": "hardware-free forwarding regression only",
        },
        "joint_limits_deg": {
            "shoulder_pan": [-110.0, 110.0],
            "shoulder_lift": [-110.0, 110.0],
            "elbow_flex": [-120.0, 120.0],
            "wrist_flex": [-120.0, 120.0],
            "wrist_roll": [-180.0, 180.0],
            "gripper": [0.0, 100.0],
        },
        "joint_limit_authority": {
            "joint_limit_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:joint-limits",
            "review_scope": "joint_limits",
            "scope": "hardware-free forwarding regression only",
        },
        "mesh_asset_authority": {
            "mesh_asset_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:mesh-assets",
            "review_scope": "mesh_assets",
            "scope": "hardware-free forwarding regression only",
        },
        "tcp_offset_authority": {
            "tcp_offset_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:tcp-offset",
            "review_scope": "tcp_offset",
            "scope": "hardware-free forwarding regression only",
        },
        "base_to_board_alignment_authority": {
            "base_to_board_alignment_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:base-to-board",
            "review_scope": "base_to_board_alignment",
            "scope": "hardware-free forwarding regression only",
        },
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


def weak_review_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["authority"] = {
        "note": "non-empty authority object without accepted reviewed status or reviewer evidence",
    }
    payload["provenance"] = {
        "source_url": "local synthetic fixture without export or license fields",
    }
    return payload


def placeholder_provenance_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["provenance"] = {
        "source_url": "TODO",
        "export_tool": "unknown",
        "license": "TBD",
    }
    return payload


def invalid_provenance_url_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["provenance"] = {
        "source_url": "local synthetic fixture",
        "export_tool": "smoke_sim_so101_bundle_ready_forwarding.py",
        "license": "test-only",
    }
    return payload


def fixture_provenance_reviewed_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for field_name, status_field in (
        ("authority", "source_authority_status"),
        ("target_frame_authority", "target_frame_authority_status"),
        ("joint_limit_authority", "joint_limit_authority_status"),
        ("mesh_asset_authority", "mesh_asset_authority_status"),
        ("tcp_offset_authority", "tcp_offset_authority_status"),
        ("base_to_board_alignment_authority", "base_to_board_alignment_authority_status"),
    ):
        payload[field_name][status_field] = "reviewed"
        payload[field_name].pop("scope", None)
    return payload


def mismatched_model_sha_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["model_sha256"] = "0" * 64
    return payload


def conflicting_model_sha_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["model_digest"] = "0" * 64
    return payload


def placeholder_review_metadata_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        payload[review_field]["reviewed_by"] = "<reviewer-or-team>"
        payload[review_field]["reviewed_at"] = "<review-date-YYYY-MM-DD>"
        payload[review_field]["review_id"] = "<stable-review-ticket-commit-or-artifact-id>"
    return payload


def thin_review_evidence_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        for trace_field in ("reviewed_at", "review_id", "review_url"):
            payload[review_field].pop(trace_field, None)
    return payload


def invalid_review_url_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        payload[review_field].pop("review_id", None)
        payload[review_field]["review_url"] = "bundle-ready-forwarding-review"
    return payload


def invalid_reviewed_at_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        payload[review_field]["reviewed_at"] = "not-a-date"
    return payload


def future_reviewed_at_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        payload[review_field]["reviewed_at"] = "2999-01-01"
    return payload


def generic_review_scope_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        payload[review_field].pop("review_scopes", None)
        payload[review_field]["review_scope"] = "model_bundle"
    return payload


def pending_review_metadata_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    for review_field in (
        "authority",
        "target_frame_authority",
        "joint_limit_authority",
        "mesh_asset_authority",
        "tcp_offset_authority",
        "base_to_board_alignment_authority",
    ):
        payload[review_field]["next_required_action_ids"] = [
            f"resolve_{review_field}_open_review_item",
        ]
    payload["authority"]["missing_inputs"] = [
        "reviewed_so101_source_authority_signoff",
    ]
    return payload


def weak_joint_limit_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("joint_limit_authority", None)
    return payload


def unexpected_joint_limit_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["joint_limits_deg"]["unknown_aux_joint"] = [-1.0, 1.0]
    return payload


def conflicting_joint_limit_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["joint_limits"] = copy.deepcopy(payload["joint_limits_deg"])
    payload["joint_limits"]["shoulder_pan"] = [-90.0, 90.0]
    return payload


def conflicting_joint_limit_nested_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["joint_limit_authority"]["joint_limits_deg"] = copy.deepcopy(
        payload["joint_limits_deg"]
    )
    payload["joint_limit_authority"]["limits_deg"] = copy.deepcopy(
        payload["joint_limits_deg"]
    )
    payload["joint_limit_authority"]["limits_deg"]["shoulder_lift"] = [
        -95.0,
        105.0,
    ]
    return payload


def weak_mesh_asset_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("mesh_asset_authority", None)
    return payload


def conflicting_mesh_asset_review_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["mesh_assets_review"] = {
        "review_status": "needs_review",
        "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
        "review_id": "bundle-ready-forwarding:mesh-assets-follow-up",
        "review_scope": "mesh_assets",
        "next_required_action_ids": [
            "resolve_conflicting_mesh_asset_review_alias",
        ],
    }
    return payload


def weak_target_frame_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("target_frame_authority", None)
    return payload


def conflicting_target_frame_review_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["target_frame_review"] = {
        "review_status": "needs_review",
        "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
        "review_id": "bundle-ready-forwarding:target-frame-follow-up",
        "review_scope": "target_frame",
        "next_required_action_ids": [
            "resolve_conflicting_target_frame_review_alias",
        ],
    }
    return payload


def wrong_target_frame_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["target_frame"] = "not_gripper_frame_link"
    return payload


def weak_tcp_offset_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("tcp_offset_authority", None)
    return payload


def invalid_tcp_offset_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["tcp_offset_m"] = {"x": 0.0, "y": 0.0}
    return payload


def nonfinite_tcp_offset_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["tcp_offset_m"] = {"x": 0.0, "y": "NaN", "z": 0.075}
    return payload


def conflicting_tcp_offset_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["gripper_tip_offset_m"] = {"x": 0.125, "y": 0.0, "z": 0.075}
    return payload


def weak_alignment_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("base_to_board_alignment_authority", None)
    return payload


def invalid_alignment_transform_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["base_to_board_transform"] = {
        "translation_m": {"x": 0.10, "y": -0.175, "z": 0.09},
    }
    return payload


def nonfinite_alignment_transform_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["base_to_board_transform"] = {
        "translation_m": {"x": 0.10, "y": "inf", "z": 0.09},
        "rotation_rpy_rad": {"roll": 0.0, "pitch": 0.0, "yaw": "NaN"},
    }
    return payload


def oversized_alignment_rotation_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["base_to_board_transform"] = {
        "translation_m": {"x": 0.10, "y": -0.175, "z": 0.09},
        "rotation_rpy_rad": {"roll": 0.0, "pitch": 0.0, "yaw": 1000.0},
    }
    return payload


def conflicting_alignment_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["base_to_board_alignment"] = {
        "translation_m": {"x": 0.20, "y": -0.175, "z": 0.09},
        "rotation_rpy_rad": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    }
    return payload


def conflicting_alignment_nested_alias_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload["base_to_board_transform"]["position_m"] = {
        "x": 0.20,
        "y": -0.175,
        "z": 0.09,
    }
    payload["base_to_board_transform"]["rpy_rad"] = {
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.25,
    }
    return payload


def create_fixtures(output_dir: Path) -> dict[str, Path]:
    fixture_dir = output_dir / "fixtures"
    raw_nonstandard_json_dir = fixture_dir / "raw_nonstandard_json_bundle"
    bundle_dir = fixture_dir / "ready_bundle"
    missing_model_file_dir = fixture_dir / "missing_model_file_bundle"
    unsupported_suffix_dir = fixture_dir / "unsupported_suffix_bundle"
    model_path_directory_dir = fixture_dir / "model_path_directory_bundle"
    invalid_asset_roots_dir = fixture_dir / "invalid_asset_roots_bundle"
    unavailable_asset_root_dir = fixture_dir / "unavailable_asset_root_bundle"
    file_asset_root_dir = fixture_dir / "file_asset_root_bundle"
    mismatched_model_sha_dir = fixture_dir / "mismatched_model_sha_bundle"
    conflicting_model_sha_alias_dir = fixture_dir / "conflicting_model_sha_alias_bundle"
    placeholder_dir = fixture_dir / "placeholder_bundle"
    placeholder_review_dir = fixture_dir / "placeholder_review_bundle"
    thin_review_dir = fixture_dir / "thin_review_bundle"
    invalid_review_url_dir = fixture_dir / "invalid_review_url_bundle"
    invalid_reviewed_at_dir = fixture_dir / "invalid_reviewed_at_bundle"
    future_reviewed_at_dir = fixture_dir / "future_reviewed_at_bundle"
    generic_review_scope_dir = fixture_dir / "generic_review_scope_bundle"
    pending_review_metadata_dir = fixture_dir / "pending_review_metadata_bundle"
    weak_review_dir = fixture_dir / "weak_review_bundle"
    placeholder_provenance_dir = fixture_dir / "placeholder_provenance_bundle"
    invalid_provenance_url_dir = fixture_dir / "invalid_provenance_url_bundle"
    fixture_provenance_reviewed_authority_dir = (
        fixture_dir / "fixture_provenance_reviewed_authority_bundle"
    )
    weak_joint_limits_dir = fixture_dir / "weak_joint_limits_bundle"
    unexpected_joint_limit_dir = fixture_dir / "unexpected_joint_limit_bundle"
    nonfinite_joint_limit_dir = fixture_dir / "nonfinite_joint_limit_bundle"
    reversed_joint_limit_dir = fixture_dir / "reversed_joint_limit_bundle"
    unexpected_model_joint_dir = fixture_dir / "unexpected_model_joint_bundle"
    conflicting_joint_limit_alias_dir = fixture_dir / "conflicting_joint_limit_alias_bundle"
    conflicting_joint_limit_nested_alias_dir = (
        fixture_dir / "conflicting_joint_limit_nested_alias_bundle"
    )
    weak_mesh_dir = fixture_dir / "weak_mesh_bundle"
    conflicting_mesh_review_alias_dir = (
        fixture_dir / "conflicting_mesh_review_alias_bundle"
    )
    weak_target_frame_dir = fixture_dir / "weak_target_frame_bundle"
    conflicting_target_frame_review_alias_dir = (
        fixture_dir / "conflicting_target_frame_review_alias_bundle"
    )
    wrong_target_frame_dir = fixture_dir / "wrong_target_frame_bundle"
    model_missing_target_frame_dir = fixture_dir / "model_missing_target_frame_bundle"
    weak_tcp_dir = fixture_dir / "weak_tcp_bundle"
    invalid_tcp_dir = fixture_dir / "invalid_tcp_bundle"
    nonfinite_tcp_dir = fixture_dir / "nonfinite_tcp_bundle"
    conflicting_tcp_alias_dir = fixture_dir / "conflicting_tcp_alias_bundle"
    weak_alignment_dir = fixture_dir / "weak_alignment_bundle"
    invalid_alignment_dir = fixture_dir / "invalid_alignment_bundle"
    nonfinite_alignment_dir = fixture_dir / "nonfinite_alignment_bundle"
    oversized_alignment_rotation_dir = (
        fixture_dir / "oversized_alignment_rotation_bundle"
    )
    conflicting_alignment_alias_dir = fixture_dir / "conflicting_alignment_alias_bundle"
    conflicting_alignment_nested_alias_dir = (
        fixture_dir / "conflicting_alignment_nested_alias_bundle"
    )
    explicit_dir = fixture_dir / "explicit_cli"

    raw_nonstandard_json_dir.mkdir(parents=True, exist_ok=True)
    for root in (
        bundle_dir,
        missing_model_file_dir,
        unsupported_suffix_dir,
        model_path_directory_dir,
        invalid_asset_roots_dir,
        unavailable_asset_root_dir,
        file_asset_root_dir,
        mismatched_model_sha_dir,
        conflicting_model_sha_alias_dir,
        placeholder_dir,
        placeholder_review_dir,
        thin_review_dir,
        invalid_review_url_dir,
        invalid_reviewed_at_dir,
        future_reviewed_at_dir,
        generic_review_scope_dir,
        pending_review_metadata_dir,
        weak_review_dir,
        placeholder_provenance_dir,
        invalid_provenance_url_dir,
        fixture_provenance_reviewed_authority_dir,
        weak_joint_limits_dir,
        unexpected_joint_limit_dir,
        nonfinite_joint_limit_dir,
        reversed_joint_limit_dir,
        unexpected_model_joint_dir,
        conflicting_joint_limit_alias_dir,
        conflicting_joint_limit_nested_alias_dir,
        weak_mesh_dir,
        conflicting_mesh_review_alias_dir,
        weak_target_frame_dir,
        conflicting_target_frame_review_alias_dir,
        wrong_target_frame_dir,
        model_missing_target_frame_dir,
        weak_tcp_dir,
        invalid_tcp_dir,
        nonfinite_tcp_dir,
        conflicting_tcp_alias_dir,
        weak_alignment_dir,
        invalid_alignment_dir,
        nonfinite_alignment_dir,
        oversized_alignment_rotation_dir,
        conflicting_alignment_alias_dir,
        conflicting_alignment_nested_alias_dir,
    ):
        (root / "model").mkdir(parents=True, exist_ok=True)
        (root / "model" / "meshes").mkdir(parents=True, exist_ok=True)
        (root / "assets" / "meshes").mkdir(parents=True, exist_ok=True)
        (root / "model" / "synthetic_so101.urdf").write_text(synthetic_urdf(include_mesh=True))
        (root / "model" / "meshes" / "synthetic_gripper_shell.obj").write_text(obj_text())
        (root / "assets" / "meshes" / "synthetic_gripper_shell.obj").write_text(obj_text())

    ready_model_path = bundle_dir / "model" / "synthetic_so101_mujoco.xml"
    ready_model_path.write_text(mjcf_with_mesh_reference())
    unsupported_suffix_model_path = (
        unsupported_suffix_dir / "model" / "synthetic_so101_not_robot.txt"
    )
    unsupported_suffix_model_path.write_text(
        "This fixture intentionally is not a URDF, MJCF, XML, or Xacro model.\n"
    )
    mismatched_model_sha_model_path = (
        mismatched_model_sha_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    mismatched_model_sha_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_model_sha_alias_model_path = (
        conflicting_model_sha_alias_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    conflicting_model_sha_alias_model_path.write_text(mjcf_with_mesh_reference())
    placeholder_review_model_path = placeholder_review_dir / "model" / "synthetic_so101_mujoco.xml"
    placeholder_review_model_path.write_text(mjcf_with_mesh_reference())
    thin_review_model_path = thin_review_dir / "model" / "synthetic_so101_mujoco.xml"
    thin_review_model_path.write_text(mjcf_with_mesh_reference())
    invalid_review_url_model_path = invalid_review_url_dir / "model" / "synthetic_so101_mujoco.xml"
    invalid_review_url_model_path.write_text(mjcf_with_mesh_reference())
    invalid_reviewed_at_model_path = (
        invalid_reviewed_at_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    invalid_reviewed_at_model_path.write_text(mjcf_with_mesh_reference())
    future_reviewed_at_model_path = (
        future_reviewed_at_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    future_reviewed_at_model_path.write_text(mjcf_with_mesh_reference())
    generic_review_scope_model_path = generic_review_scope_dir / "model" / "synthetic_so101_mujoco.xml"
    generic_review_scope_model_path.write_text(mjcf_with_mesh_reference())
    pending_review_metadata_model_path = (
        pending_review_metadata_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    pending_review_metadata_model_path.write_text(mjcf_with_mesh_reference())
    weak_review_model_path = weak_review_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_review_model_path.write_text(mjcf_with_mesh_reference())
    placeholder_provenance_model_path = (
        placeholder_provenance_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    placeholder_provenance_model_path.write_text(mjcf_with_mesh_reference())
    invalid_provenance_url_model_path = (
        invalid_provenance_url_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    invalid_provenance_url_model_path.write_text(mjcf_with_mesh_reference())
    fixture_provenance_reviewed_authority_model_path = (
        fixture_provenance_reviewed_authority_dir
        / "model"
        / "synthetic_so101_mujoco.xml"
    )
    fixture_provenance_reviewed_authority_model_path.write_text(
        mjcf_with_mesh_reference()
    )
    weak_joint_limits_model_path = weak_joint_limits_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_joint_limits_model_path.write_text(mjcf_with_mesh_reference())
    unexpected_joint_limit_model_path = (
        unexpected_joint_limit_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    unexpected_joint_limit_model_path.write_text(mjcf_with_mesh_reference())
    nonfinite_joint_limit_model_path = (
        nonfinite_joint_limit_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    nonfinite_joint_limit_model_path.write_text(mjcf_with_mesh_reference())
    reversed_joint_limit_model_path = (
        reversed_joint_limit_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    reversed_joint_limit_model_path.write_text(mjcf_with_mesh_reference())
    unexpected_model_joint_model_path = (
        unexpected_model_joint_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    unexpected_model_joint_model_path.write_text(mjcf_with_unexpected_joint_reference())
    conflicting_joint_limit_alias_model_path = (
        conflicting_joint_limit_alias_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    conflicting_joint_limit_alias_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_joint_limit_nested_alias_model_path = (
        conflicting_joint_limit_nested_alias_dir
        / "model"
        / "synthetic_so101_mujoco.xml"
    )
    conflicting_joint_limit_nested_alias_model_path.write_text(
        mjcf_with_mesh_reference()
    )
    weak_mesh_model_path = weak_mesh_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_mesh_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_mesh_review_alias_model_path = (
        conflicting_mesh_review_alias_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    conflicting_mesh_review_alias_model_path.write_text(mjcf_with_mesh_reference())
    weak_target_frame_model_path = weak_target_frame_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_target_frame_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_target_frame_review_alias_model_path = (
        conflicting_target_frame_review_alias_dir
        / "model"
        / "synthetic_so101_mujoco.xml"
    )
    conflicting_target_frame_review_alias_model_path.write_text(
        mjcf_with_mesh_reference()
    )
    wrong_target_frame_model_path = wrong_target_frame_dir / "model" / "synthetic_so101_mujoco.xml"
    wrong_target_frame_model_path.write_text(mjcf_with_mesh_reference())
    model_missing_target_frame_path = model_missing_target_frame_dir / "model" / "synthetic_so101_mujoco.xml"
    model_missing_target_frame_path.write_text(mjcf_missing_target_frame_with_mesh_reference())
    weak_tcp_model_path = weak_tcp_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_tcp_model_path.write_text(mjcf_with_mesh_reference())
    invalid_tcp_model_path = invalid_tcp_dir / "model" / "synthetic_so101_mujoco.xml"
    invalid_tcp_model_path.write_text(mjcf_with_mesh_reference())
    nonfinite_tcp_model_path = nonfinite_tcp_dir / "model" / "synthetic_so101_mujoco.xml"
    nonfinite_tcp_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_tcp_alias_model_path = (
        conflicting_tcp_alias_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    conflicting_tcp_alias_model_path.write_text(mjcf_with_mesh_reference())
    weak_alignment_model_path = weak_alignment_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_alignment_model_path.write_text(mjcf_with_mesh_reference())
    invalid_alignment_model_path = invalid_alignment_dir / "model" / "synthetic_so101_mujoco.xml"
    invalid_alignment_model_path.write_text(mjcf_with_mesh_reference())
    nonfinite_alignment_model_path = (
        nonfinite_alignment_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    nonfinite_alignment_model_path.write_text(mjcf_with_mesh_reference())
    oversized_alignment_rotation_model_path = (
        oversized_alignment_rotation_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    oversized_alignment_rotation_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_alignment_alias_model_path = (
        conflicting_alignment_alias_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    conflicting_alignment_alias_model_path.write_text(mjcf_with_mesh_reference())
    conflicting_alignment_nested_alias_model_path = (
        conflicting_alignment_nested_alias_dir
        / "model"
        / "synthetic_so101_mujoco.xml"
    )
    conflicting_alignment_nested_alias_model_path.write_text(
        mjcf_with_mesh_reference()
    )

    explicit_dir.mkdir(parents=True, exist_ok=True)
    explicit_model_path = explicit_dir / "explicit_cli_so101.urdf"
    explicit_model_path.write_text(synthetic_urdf(include_mesh=False))
    placeholder_model_path = placeholder_dir / "model" / "synthetic_so101.urdf"

    raw_nonstandard_json_manifest_path = (
        raw_nonstandard_json_dir / "so101_model_bundle.raw_nonstandard_json_constant.json"
    )
    ready_manifest_path = bundle_dir / "so101_model_bundle.ready.json"
    missing_model_file_manifest_path = (
        missing_model_file_dir / "so101_model_bundle.missing_model_file.json"
    )
    unsupported_suffix_manifest_path = (
        unsupported_suffix_dir / "so101_model_bundle.unsupported_suffix.json"
    )
    model_path_directory_manifest_path = (
        model_path_directory_dir / "so101_model_bundle.model_path_directory.json"
    )
    invalid_asset_roots_manifest_path = (
        invalid_asset_roots_dir / "so101_model_bundle.invalid_asset_roots.json"
    )
    unavailable_asset_root_manifest_path = (
        unavailable_asset_root_dir / "so101_model_bundle.unavailable_asset_root.json"
    )
    file_asset_root_manifest_path = (
        file_asset_root_dir / "so101_model_bundle.file_asset_root.json"
    )
    mismatched_model_sha_manifest_path = (
        mismatched_model_sha_dir / "so101_model_bundle.mismatched_model_sha.json"
    )
    conflicting_model_sha_alias_manifest_path = (
        conflicting_model_sha_alias_dir
        / "so101_model_bundle.conflicting_model_sha_alias.json"
    )
    placeholder_manifest_path = placeholder_dir / "so101_model_bundle.placeholder.json"
    placeholder_review_manifest_path = placeholder_review_dir / "so101_model_bundle.placeholder_review.json"
    thin_review_manifest_path = thin_review_dir / "so101_model_bundle.thin_review.json"
    invalid_review_url_manifest_path = invalid_review_url_dir / "so101_model_bundle.invalid_review_url.json"
    invalid_reviewed_at_manifest_path = (
        invalid_reviewed_at_dir / "so101_model_bundle.invalid_reviewed_at.json"
    )
    future_reviewed_at_manifest_path = (
        future_reviewed_at_dir / "so101_model_bundle.future_reviewed_at.json"
    )
    generic_review_scope_manifest_path = generic_review_scope_dir / "so101_model_bundle.generic_review_scope.json"
    pending_review_metadata_manifest_path = (
        pending_review_metadata_dir / "so101_model_bundle.pending_review_metadata.json"
    )
    weak_review_manifest_path = weak_review_dir / "so101_model_bundle.weak_review.json"
    placeholder_provenance_manifest_path = (
        placeholder_provenance_dir / "so101_model_bundle.placeholder_provenance.json"
    )
    invalid_provenance_url_manifest_path = (
        invalid_provenance_url_dir / "so101_model_bundle.invalid_provenance_url.json"
    )
    fixture_provenance_reviewed_authority_manifest_path = (
        fixture_provenance_reviewed_authority_dir
        / "so101_model_bundle.fixture_provenance_reviewed_authority.json"
    )
    weak_joint_limits_manifest_path = weak_joint_limits_dir / "so101_model_bundle.weak_joint_limits.json"
    unexpected_joint_limit_manifest_path = (
        unexpected_joint_limit_dir / "so101_model_bundle.unexpected_joint_limit.json"
    )
    nonfinite_joint_limit_manifest_path = (
        nonfinite_joint_limit_dir / "so101_model_bundle.nonfinite_joint_limit.json"
    )
    reversed_joint_limit_manifest_path = (
        reversed_joint_limit_dir / "so101_model_bundle.reversed_joint_limit.json"
    )
    unexpected_model_joint_manifest_path = (
        unexpected_model_joint_dir / "so101_model_bundle.unexpected_model_joint.json"
    )
    conflicting_joint_limit_alias_manifest_path = (
        conflicting_joint_limit_alias_dir
        / "so101_model_bundle.conflicting_joint_limit_alias.json"
    )
    conflicting_joint_limit_nested_alias_manifest_path = (
        conflicting_joint_limit_nested_alias_dir
        / "so101_model_bundle.conflicting_joint_limit_nested_alias.json"
    )
    weak_mesh_manifest_path = weak_mesh_dir / "so101_model_bundle.weak_mesh_assets.json"
    conflicting_mesh_review_alias_manifest_path = (
        conflicting_mesh_review_alias_dir
        / "so101_model_bundle.conflicting_mesh_review_alias.json"
    )
    weak_target_frame_manifest_path = weak_target_frame_dir / "so101_model_bundle.weak_target_frame.json"
    conflicting_target_frame_review_alias_manifest_path = (
        conflicting_target_frame_review_alias_dir
        / "so101_model_bundle.conflicting_target_frame_review_alias.json"
    )
    wrong_target_frame_manifest_path = wrong_target_frame_dir / "so101_model_bundle.wrong_target_frame.json"
    model_missing_target_frame_manifest_path = (
        model_missing_target_frame_dir / "so101_model_bundle.model_missing_target_frame.json"
    )
    weak_tcp_manifest_path = weak_tcp_dir / "so101_model_bundle.weak_tcp_offset.json"
    invalid_tcp_manifest_path = invalid_tcp_dir / "so101_model_bundle.invalid_tcp_offset.json"
    nonfinite_tcp_manifest_path = (
        nonfinite_tcp_dir / "so101_model_bundle.nonfinite_tcp_offset.json"
    )
    conflicting_tcp_alias_manifest_path = (
        conflicting_tcp_alias_dir
        / "so101_model_bundle.conflicting_tcp_offset_alias.json"
    )
    weak_alignment_manifest_path = weak_alignment_dir / "so101_model_bundle.weak_alignment.json"
    invalid_alignment_manifest_path = invalid_alignment_dir / "so101_model_bundle.invalid_alignment.json"
    nonfinite_alignment_manifest_path = (
        nonfinite_alignment_dir / "so101_model_bundle.nonfinite_alignment.json"
    )
    oversized_alignment_rotation_manifest_path = (
        oversized_alignment_rotation_dir
        / "so101_model_bundle.oversized_alignment_rotation.json"
    )
    conflicting_alignment_alias_manifest_path = (
        conflicting_alignment_alias_dir
        / "so101_model_bundle.conflicting_alignment_alias.json"
    )
    conflicting_alignment_nested_alias_manifest_path = (
        conflicting_alignment_nested_alias_dir
        / "so101_model_bundle.conflicting_alignment_nested_alias.json"
    )
    raw_nonstandard_json_manifest_path.write_text(
        '{"model_path": "synthetic_so101_mujoco.xml", "tcp_offset_m": {"x": NaN, "y": 0.0, "z": 0.075}}\n'
    )
    write_manifest_json(
        ready_manifest_path,
        manifest_payload(ready=True, model_filename=ready_model_path.name),
        ready_model_path,
    )
    missing_model_file_payload = manifest_payload(
        ready=True,
        model_filename="synthetic_so101_mujoco_missing.xml",
    )
    missing_model_file_payload["model_sha256"] = "1" * 64
    write_json(missing_model_file_manifest_path, missing_model_file_payload)
    write_manifest_json(
        unsupported_suffix_manifest_path,
        manifest_payload(ready=True, model_filename=unsupported_suffix_model_path.name),
        unsupported_suffix_model_path,
    )
    model_path_directory_payload = manifest_payload(ready=True, model_filename=".")
    model_path_directory_payload["model_sha256"] = "1" * 64
    write_json(model_path_directory_manifest_path, model_path_directory_payload)
    invalid_asset_roots_payload = manifest_payload(ready=True)
    invalid_asset_roots_payload["asset_roots"] = "assets"
    write_manifest_json(
        invalid_asset_roots_manifest_path,
        invalid_asset_roots_payload,
        invalid_asset_roots_dir / "model" / "synthetic_so101.urdf",
    )
    unavailable_asset_root_payload = manifest_payload(ready=True)
    unavailable_asset_root_payload["asset_roots"] = ["missing_assets"]
    write_manifest_json(
        unavailable_asset_root_manifest_path,
        unavailable_asset_root_payload,
        unavailable_asset_root_dir / "model" / "synthetic_so101.urdf",
    )
    file_asset_root_path = file_asset_root_dir / "assets" / "not_a_directory.txt"
    file_asset_root_path.write_text("asset-root negative fixture file\n")
    file_asset_root_payload = manifest_payload(ready=True)
    file_asset_root_payload["asset_roots"] = ["assets/not_a_directory.txt"]
    write_manifest_json(
        file_asset_root_manifest_path,
        file_asset_root_payload,
        file_asset_root_dir / "model" / "synthetic_so101.urdf",
    )
    write_json(
        mismatched_model_sha_manifest_path,
        mismatched_model_sha_manifest_payload(
            model_filename=mismatched_model_sha_model_path.name
        ),
    )
    write_manifest_json(
        conflicting_model_sha_alias_manifest_path,
        conflicting_model_sha_alias_manifest_payload(
            model_filename=conflicting_model_sha_alias_model_path.name
        ),
        conflicting_model_sha_alias_model_path,
    )
    write_manifest_json(placeholder_manifest_path, manifest_payload(ready=False), placeholder_model_path)
    write_manifest_json(
        placeholder_review_manifest_path,
        placeholder_review_metadata_manifest_payload(model_filename=placeholder_review_model_path.name),
        placeholder_review_model_path,
    )
    write_manifest_json(
        thin_review_manifest_path,
        thin_review_evidence_manifest_payload(model_filename=thin_review_model_path.name),
        thin_review_model_path,
    )
    write_manifest_json(
        invalid_review_url_manifest_path,
        invalid_review_url_manifest_payload(model_filename=invalid_review_url_model_path.name),
        invalid_review_url_model_path,
    )
    write_manifest_json(
        invalid_reviewed_at_manifest_path,
        invalid_reviewed_at_manifest_payload(
            model_filename=invalid_reviewed_at_model_path.name
        ),
        invalid_reviewed_at_model_path,
    )
    write_manifest_json(
        future_reviewed_at_manifest_path,
        future_reviewed_at_manifest_payload(
            model_filename=future_reviewed_at_model_path.name
        ),
        future_reviewed_at_model_path,
    )
    write_manifest_json(
        generic_review_scope_manifest_path,
        generic_review_scope_manifest_payload(model_filename=generic_review_scope_model_path.name),
        generic_review_scope_model_path,
    )
    write_manifest_json(
        pending_review_metadata_manifest_path,
        pending_review_metadata_manifest_payload(
            model_filename=pending_review_metadata_model_path.name
        ),
        pending_review_metadata_model_path,
    )
    write_manifest_json(
        weak_review_manifest_path,
        weak_review_manifest_payload(model_filename=weak_review_model_path.name),
        weak_review_model_path,
    )
    write_manifest_json(
        placeholder_provenance_manifest_path,
        placeholder_provenance_manifest_payload(
            model_filename=placeholder_provenance_model_path.name
        ),
        placeholder_provenance_model_path,
    )
    write_manifest_json(
        invalid_provenance_url_manifest_path,
        invalid_provenance_url_manifest_payload(
            model_filename=invalid_provenance_url_model_path.name
        ),
        invalid_provenance_url_model_path,
    )
    write_manifest_json(
        fixture_provenance_reviewed_authority_manifest_path,
        fixture_provenance_reviewed_authority_manifest_payload(
            model_filename=fixture_provenance_reviewed_authority_model_path.name
        ),
        fixture_provenance_reviewed_authority_model_path,
    )
    write_manifest_json(
        weak_joint_limits_manifest_path,
        weak_joint_limit_authority_manifest_payload(model_filename=weak_joint_limits_model_path.name),
        weak_joint_limits_model_path,
    )
    write_manifest_json(
        unexpected_joint_limit_manifest_path,
        unexpected_joint_limit_manifest_payload(
            model_filename=unexpected_joint_limit_model_path.name
        ),
        unexpected_joint_limit_model_path,
    )
    nonfinite_joint_limit_payload = manifest_payload(
        ready=True,
        model_filename=nonfinite_joint_limit_model_path.name,
    )
    nonfinite_joint_limit_payload["joint_limits_deg"]["shoulder_pan"] = ["NaN", 110.0]
    write_manifest_json(
        nonfinite_joint_limit_manifest_path,
        nonfinite_joint_limit_payload,
        nonfinite_joint_limit_model_path,
    )
    reversed_joint_limit_payload = manifest_payload(
        ready=True,
        model_filename=reversed_joint_limit_model_path.name,
    )
    reversed_joint_limit_payload["joint_limits_deg"]["shoulder_pan"] = [110.0, -110.0]
    write_manifest_json(
        reversed_joint_limit_manifest_path,
        reversed_joint_limit_payload,
        reversed_joint_limit_model_path,
    )
    write_manifest_json(
        unexpected_model_joint_manifest_path,
        manifest_payload(ready=True, model_filename=unexpected_model_joint_model_path.name),
        unexpected_model_joint_model_path,
    )
    write_manifest_json(
        conflicting_joint_limit_alias_manifest_path,
        conflicting_joint_limit_alias_manifest_payload(
            model_filename=conflicting_joint_limit_alias_model_path.name
        ),
        conflicting_joint_limit_alias_model_path,
    )
    write_manifest_json(
        conflicting_joint_limit_nested_alias_manifest_path,
        conflicting_joint_limit_nested_alias_manifest_payload(
            model_filename=conflicting_joint_limit_nested_alias_model_path.name
        ),
        conflicting_joint_limit_nested_alias_model_path,
    )
    write_manifest_json(
        weak_mesh_manifest_path,
        weak_mesh_asset_authority_manifest_payload(model_filename=weak_mesh_model_path.name),
        weak_mesh_model_path,
    )
    write_manifest_json(
        conflicting_mesh_review_alias_manifest_path,
        conflicting_mesh_asset_review_alias_manifest_payload(
            model_filename=conflicting_mesh_review_alias_model_path.name
        ),
        conflicting_mesh_review_alias_model_path,
    )
    write_manifest_json(
        weak_target_frame_manifest_path,
        weak_target_frame_authority_manifest_payload(model_filename=weak_target_frame_model_path.name),
        weak_target_frame_model_path,
    )
    write_manifest_json(
        conflicting_target_frame_review_alias_manifest_path,
        conflicting_target_frame_review_alias_manifest_payload(
            model_filename=conflicting_target_frame_review_alias_model_path.name
        ),
        conflicting_target_frame_review_alias_model_path,
    )
    write_manifest_json(
        wrong_target_frame_manifest_path,
        wrong_target_frame_manifest_payload(model_filename=wrong_target_frame_model_path.name),
        wrong_target_frame_model_path,
    )
    write_manifest_json(
        model_missing_target_frame_manifest_path,
        manifest_payload(ready=True, model_filename=model_missing_target_frame_path.name),
        model_missing_target_frame_path,
    )
    write_manifest_json(
        weak_tcp_manifest_path,
        weak_tcp_offset_authority_manifest_payload(model_filename=weak_tcp_model_path.name),
        weak_tcp_model_path,
    )
    write_manifest_json(
        invalid_tcp_manifest_path,
        invalid_tcp_offset_manifest_payload(model_filename=invalid_tcp_model_path.name),
        invalid_tcp_model_path,
    )
    write_manifest_json(
        nonfinite_tcp_manifest_path,
        nonfinite_tcp_offset_manifest_payload(model_filename=nonfinite_tcp_model_path.name),
        nonfinite_tcp_model_path,
    )
    write_manifest_json(
        conflicting_tcp_alias_manifest_path,
        conflicting_tcp_offset_alias_manifest_payload(
            model_filename=conflicting_tcp_alias_model_path.name
        ),
        conflicting_tcp_alias_model_path,
    )
    write_manifest_json(
        weak_alignment_manifest_path,
        weak_alignment_authority_manifest_payload(model_filename=weak_alignment_model_path.name),
        weak_alignment_model_path,
    )
    write_manifest_json(
        invalid_alignment_manifest_path,
        invalid_alignment_transform_manifest_payload(model_filename=invalid_alignment_model_path.name),
        invalid_alignment_model_path,
    )
    write_manifest_json(
        nonfinite_alignment_manifest_path,
        nonfinite_alignment_transform_manifest_payload(
            model_filename=nonfinite_alignment_model_path.name
        ),
        nonfinite_alignment_model_path,
    )
    write_manifest_json(
        oversized_alignment_rotation_manifest_path,
        oversized_alignment_rotation_manifest_payload(
            model_filename=oversized_alignment_rotation_model_path.name
        ),
        oversized_alignment_rotation_model_path,
    )
    write_manifest_json(
        conflicting_alignment_alias_manifest_path,
        conflicting_alignment_alias_manifest_payload(
            model_filename=conflicting_alignment_alias_model_path.name
        ),
        conflicting_alignment_alias_model_path,
    )
    write_manifest_json(
        conflicting_alignment_nested_alias_manifest_path,
        conflicting_alignment_nested_alias_manifest_payload(
            model_filename=conflicting_alignment_nested_alias_model_path.name
        ),
        conflicting_alignment_nested_alias_model_path,
    )

    return {
        "raw_nonstandard_json_manifest_path": raw_nonstandard_json_manifest_path,
        "ready_manifest_path": ready_manifest_path,
        "missing_model_file_manifest_path": missing_model_file_manifest_path,
        "unsupported_suffix_manifest_path": unsupported_suffix_manifest_path,
        "model_path_directory_manifest_path": model_path_directory_manifest_path,
        "invalid_asset_roots_manifest_path": invalid_asset_roots_manifest_path,
        "unavailable_asset_root_manifest_path": unavailable_asset_root_manifest_path,
        "file_asset_root_manifest_path": file_asset_root_manifest_path,
        "mismatched_model_sha_manifest_path": mismatched_model_sha_manifest_path,
        "conflicting_model_sha_alias_manifest_path": (
            conflicting_model_sha_alias_manifest_path
        ),
        "placeholder_manifest_path": placeholder_manifest_path,
        "placeholder_review_manifest_path": placeholder_review_manifest_path,
        "thin_review_manifest_path": thin_review_manifest_path,
        "invalid_review_url_manifest_path": invalid_review_url_manifest_path,
        "invalid_reviewed_at_manifest_path": invalid_reviewed_at_manifest_path,
        "future_reviewed_at_manifest_path": future_reviewed_at_manifest_path,
        "generic_review_scope_manifest_path": generic_review_scope_manifest_path,
        "pending_review_metadata_manifest_path": pending_review_metadata_manifest_path,
        "weak_review_manifest_path": weak_review_manifest_path,
        "placeholder_provenance_manifest_path": placeholder_provenance_manifest_path,
        "invalid_provenance_url_manifest_path": invalid_provenance_url_manifest_path,
        "fixture_provenance_reviewed_authority_manifest_path": (
            fixture_provenance_reviewed_authority_manifest_path
        ),
        "weak_joint_limits_manifest_path": weak_joint_limits_manifest_path,
        "unexpected_joint_limit_manifest_path": unexpected_joint_limit_manifest_path,
        "nonfinite_joint_limit_manifest_path": nonfinite_joint_limit_manifest_path,
        "reversed_joint_limit_manifest_path": reversed_joint_limit_manifest_path,
        "unexpected_model_joint_manifest_path": unexpected_model_joint_manifest_path,
        "conflicting_joint_limit_alias_manifest_path": (
            conflicting_joint_limit_alias_manifest_path
        ),
        "conflicting_joint_limit_nested_alias_manifest_path": (
            conflicting_joint_limit_nested_alias_manifest_path
        ),
        "weak_mesh_manifest_path": weak_mesh_manifest_path,
        "conflicting_mesh_review_alias_manifest_path": (
            conflicting_mesh_review_alias_manifest_path
        ),
        "weak_target_frame_manifest_path": weak_target_frame_manifest_path,
        "conflicting_target_frame_review_alias_manifest_path": (
            conflicting_target_frame_review_alias_manifest_path
        ),
        "wrong_target_frame_manifest_path": wrong_target_frame_manifest_path,
        "model_missing_target_frame_manifest_path": model_missing_target_frame_manifest_path,
        "weak_tcp_manifest_path": weak_tcp_manifest_path,
        "invalid_tcp_manifest_path": invalid_tcp_manifest_path,
        "nonfinite_tcp_manifest_path": nonfinite_tcp_manifest_path,
        "conflicting_tcp_alias_manifest_path": conflicting_tcp_alias_manifest_path,
        "weak_alignment_manifest_path": weak_alignment_manifest_path,
        "invalid_alignment_manifest_path": invalid_alignment_manifest_path,
        "nonfinite_alignment_manifest_path": nonfinite_alignment_manifest_path,
        "oversized_alignment_rotation_manifest_path": (
            oversized_alignment_rotation_manifest_path
        ),
        "conflicting_alignment_alias_manifest_path": conflicting_alignment_alias_manifest_path,
        "conflicting_alignment_nested_alias_manifest_path": (
            conflicting_alignment_nested_alias_manifest_path
        ),
        "ready_model_path": ready_model_path,
        "unsupported_suffix_model_path": unsupported_suffix_model_path,
        "mismatched_model_sha_model_path": mismatched_model_sha_model_path,
        "conflicting_model_sha_alias_model_path": (
            conflicting_model_sha_alias_model_path
        ),
        "ready_asset_root": bundle_dir / "assets",
        "placeholder_review_model_path": placeholder_review_model_path,
        "thin_review_model_path": thin_review_model_path,
        "invalid_review_url_model_path": invalid_review_url_model_path,
        "invalid_reviewed_at_model_path": invalid_reviewed_at_model_path,
        "future_reviewed_at_model_path": future_reviewed_at_model_path,
        "generic_review_scope_model_path": generic_review_scope_model_path,
        "pending_review_metadata_model_path": pending_review_metadata_model_path,
        "weak_review_model_path": weak_review_model_path,
        "placeholder_provenance_model_path": placeholder_provenance_model_path,
        "invalid_provenance_url_model_path": invalid_provenance_url_model_path,
        "fixture_provenance_reviewed_authority_model_path": (
            fixture_provenance_reviewed_authority_model_path
        ),
        "weak_joint_limits_model_path": weak_joint_limits_model_path,
        "unexpected_joint_limit_model_path": unexpected_joint_limit_model_path,
        "nonfinite_joint_limit_model_path": nonfinite_joint_limit_model_path,
        "reversed_joint_limit_model_path": reversed_joint_limit_model_path,
        "unexpected_model_joint_model_path": unexpected_model_joint_model_path,
        "conflicting_joint_limit_alias_model_path": (
            conflicting_joint_limit_alias_model_path
        ),
        "conflicting_joint_limit_nested_alias_model_path": (
            conflicting_joint_limit_nested_alias_model_path
        ),
        "weak_mesh_model_path": weak_mesh_model_path,
        "conflicting_mesh_review_alias_model_path": (
            conflicting_mesh_review_alias_model_path
        ),
        "weak_target_frame_model_path": weak_target_frame_model_path,
        "conflicting_target_frame_review_alias_model_path": (
            conflicting_target_frame_review_alias_model_path
        ),
        "wrong_target_frame_model_path": wrong_target_frame_model_path,
        "model_missing_target_frame_path": model_missing_target_frame_path,
        "weak_tcp_model_path": weak_tcp_model_path,
        "invalid_tcp_model_path": invalid_tcp_model_path,
        "nonfinite_tcp_model_path": nonfinite_tcp_model_path,
        "conflicting_tcp_alias_model_path": conflicting_tcp_alias_model_path,
        "weak_alignment_model_path": weak_alignment_model_path,
        "invalid_alignment_model_path": invalid_alignment_model_path,
        "nonfinite_alignment_model_path": nonfinite_alignment_model_path,
        "oversized_alignment_rotation_model_path": (
            oversized_alignment_rotation_model_path
        ),
        "conflicting_alignment_alias_model_path": conflicting_alignment_alias_model_path,
        "conflicting_alignment_nested_alias_model_path": (
            conflicting_alignment_nested_alias_model_path
        ),
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


def load_json_object(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        return {}
    try:
        payload = json.loads(Path(path_value).read_text())
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def assert_contains_all(
    errors: list[str],
    label: str,
    actual: Any,
    expected_values: list[str],
) -> None:
    if not isinstance(actual, list):
        errors.append(f"{label}: expected list containing {expected_values!r}, got {actual!r}")
        return
    missing = [value for value in expected_values if value not in actual]
    if missing:
        errors.append(f"{label}: missing {missing!r} from {actual!r}")


def review_group_names(review: Any, key: str) -> list[str]:
    if not isinstance(review, dict):
        return []
    values = review.get(key)
    if key == "review_evidence_required_groups" and isinstance(values, list):
        return [
            str(item.get("group"))
            for item in values
            if isinstance(item, dict) and item.get("group")
        ]
    return values if isinstance(values, list) else []


def assert_traceable_review_evidence(
    errors: list[str],
    label: str,
    review: Any,
    *,
    expected_missing_groups: list[str],
) -> None:
    if not isinstance(review, dict):
        errors.append(f"{label}: expected review dict, got {review!r}")
        return
    assert_contains_all(
        errors,
        f"{label}.review_evidence_required_groups",
        review_group_names(review, "review_evidence_required_groups"),
        ["review_actor", "review_trace", "review_artifact"],
    )
    assert_contains_all(
        errors,
        f"{label}.review_evidence_valid_fields",
        review.get("review_evidence_valid_fields"),
        ["reviewed_by"],
    )
    assert_contains_all(
        errors,
        f"{label}.review_evidence_satisfied_required_groups",
        review_group_names(review, "review_evidence_satisfied_required_groups"),
        ["review_actor"],
    )
    assert_contains_all(
        errors,
        f"{label}.review_evidence_missing_required_groups",
        review_group_names(review, "review_evidence_missing_required_groups"),
        expected_missing_groups,
    )


def assert_missing_review_scopes(
    errors: list[str],
    label: str,
    review: Any,
    *,
    expected_missing_scopes: list[str],
) -> None:
    if not isinstance(review, dict):
        errors.append(f"{label}: expected review dict, got {review!r}")
        return
    assert_contains_all(
        errors,
        f"{label}.missing_review_scope_ids",
        review.get("missing_review_scope_ids"),
        expected_missing_scopes,
    )
    assert_equal(errors, f"{label}.review_scope_ready", review.get("review_scope_ready"), False)


def assert_review_open_work_fields(
    errors: list[str],
    label: str,
    review: Any,
    *,
    expected_open_work_fields: list[str],
) -> None:
    if not isinstance(review, dict):
        errors.append(f"{label}: expected review dict, got {review!r}")
        return
    assert_equal(
        errors,
        f"{label}.review_evidence_open_work_fields",
        review.get("review_evidence_open_work_fields"),
        expected_open_work_fields,
    )
    assert_true(
        errors,
        f"{label}.review_evidence_ready_has_open_work",
        review.get("review_evidence_ready_has_open_work"),
    )


def assert_not_ready_motion_authority(
    errors: list[str],
    case_id: str,
    reviewed_mujoco: dict[str, Any],
) -> None:
    assert_equal(
        errors,
        f"{case_id}.reviewed_mujoco_motion_authority_status",
        reviewed_mujoco.get("motion_authority_status"),
        "not_checked_manifest_not_ready",
    )
    assert_false(
        errors,
        f"{case_id}.reviewed_mujoco_physical_reviewed_model_motion_checked",
        reviewed_mujoco.get("physical_reviewed_model_motion_checked"),
    )
    assert_false(
        errors,
        f"{case_id}.reviewed_mujoco_hardware_free_fixture_motion_checked",
        reviewed_mujoco.get("hardware_free_fixture_motion_checked"),
    )
    assert_false(
        errors,
        f"{case_id}.reviewed_mujoco_motion_evidence_not_physical",
        reviewed_mujoco.get("motion_evidence_not_physical_so101_authority"),
    )


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
    source_config = get_nested(suite_summary, ("so101_model_source_inventory_config",), {})
    source_inventory_forwarding = get_nested(source_config, ("bundle_manifest",), {})
    source_authority_review = get_nested(source_config, ("source_authority_review",), {})
    bundle = get_nested(suite_summary, ("so101_model_bundle_manifest",), {})
    contract = get_nested(suite_summary, ("so101_model_contract",), {})
    contract_preflight = get_nested(suite_summary, ("so101_model_contract", "model_asset_preflight"), {})
    bundle_preflight = get_nested(suite_summary, ("so101_model_bundle_manifest", "model_asset_preflight"), {})
    reviewed_mujoco = get_nested(suite_summary, ("so101_reviewed_mujoco_bundle",), {})
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
        assert_equal(
            errors,
            f"{case_id}.bundle_model_authority",
            bundle.get("model_authority"),
            "hardware_free_regression_fixture_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.bundle_physical_so101_model_authority_ready",
            bundle.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.bundle_hardware_free_regression_fixture_ready",
            bundle.get("hardware_free_regression_fixture_ready"),
        )
        synthetic_fields = bundle.get("synthetic_fixture_authority_fields") or []
        if "provenance" not in synthetic_fields:
            errors.append(
                f"{case_id}.synthetic_fixture_authority_fields: expected provenance in {synthetic_fields!r}"
            )
        assert_equal(
            errors,
            f"{case_id}.model_identity_status",
            get_nested(bundle, ("model_identity", "status")),
            "present",
        )
        assert_true(
            errors,
            f"{case_id}.model_identity_matches",
            get_nested(bundle, ("model_identity", "matches")),
        )
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
        if not isinstance(get_nested(bundle, ("mesh_assets", "mesh_reference_count")), int) or get_nested(bundle, ("mesh_assets", "mesh_reference_count")) <= 0:
            errors.append(f"{case_id}.mesh_reference_count: expected > 0, got {get_nested(bundle, ('mesh_assets', 'mesh_reference_count'))!r}")
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_motion_checked",
        )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_model_authority",
            reviewed_mujoco.get("model_authority"),
            "hardware_free_regression_fixture_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.reviewed_mujoco_physical_so101_model_authority_ready",
            reviewed_mujoco.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.reviewed_mujoco_hardware_free_regression_fixture_ready",
            reviewed_mujoco.get("hardware_free_regression_fixture_ready"),
        )
        assert_true(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_motion_authority_status",
            reviewed_mujoco.get("motion_authority_status"),
            "hardware_free_fixture_motion_checked_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.reviewed_mujoco_physical_reviewed_model_motion_checked",
            reviewed_mujoco.get("physical_reviewed_model_motion_checked"),
        )
        assert_true(
            errors,
            f"{case_id}.reviewed_mujoco_hardware_free_fixture_motion_checked",
            reviewed_mujoco.get("hardware_free_fixture_motion_checked"),
        )
        assert_true(
            errors,
            f"{case_id}.reviewed_mujoco_motion_evidence_not_physical",
            reviewed_mujoco.get("motion_evidence_not_physical_so101_authority"),
        )
        assert_false(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_false(
            errors,
            f"{case_id}.forwarding_physical_so101_model_authority_ready",
            forwarding.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.forwarding_hardware_free_regression_fixture_ready",
            forwarding.get("hardware_free_regression_fixture_ready"),
        )
        assert_true(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "so101_model_bundle_manifest")
        assert_equal(errors, f"{case_id}.ik_model_asset_root_source", forwarding.get("ik_model_asset_root_source"), "so101_model_bundle_manifest")
        assert_false(
            errors,
            f"{case_id}.source_inventory_used_bundle",
            source_inventory_forwarding.get("used_for_source_inventory"),
        )
        assert_true(
            errors,
            f"{case_id}.source_inventory_diagnostic_only",
            source_inventory_forwarding.get("diagnostic_only"),
        )
        assert_equal(
            errors,
            f"{case_id}.source_inventory_diagnostic_only_reason",
            source_inventory_forwarding.get("diagnostic_only_reason"),
            "bundle_ready_fixture_not_physical_source_authority",
        )
        assert_true(
            errors,
            f"{case_id}.source_inventory_requires_physical_so101_model_authority",
            source_inventory_forwarding.get("requires_physical_so101_model_authority"),
        )
        assert_false(
            errors,
            f"{case_id}.source_inventory_physical_so101_model_authority_ready",
            source_inventory_forwarding.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.source_inventory_hardware_free_regression_fixture_ready",
            source_inventory_forwarding.get("hardware_free_regression_fixture_ready"),
        )
        assert_equal(
            errors,
            f"{case_id}.source_inventory_model_source_root_source",
            source_inventory_forwarding.get("model_source_root_source"),
            "default_repo_roots",
        )
        assert_equal(
            errors,
            f"{case_id}.source_inventory_authoritative_model_path_source",
            source_inventory_forwarding.get("authoritative_model_path_source"),
            "not_supplied",
        )
        assert_equal(
            errors,
            f"{case_id}.source_authority_review_source",
            source_authority_review.get("source"),
            "not_supplied",
        )
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
        if not isinstance(bundle_preflight.get("mesh_reference_count"), int) or bundle_preflight.get("mesh_reference_count") <= 0:
            errors.append(f"{case_id}.bundle_preflight_mesh_reference_count: expected > 0, got {bundle_preflight.get('mesh_reference_count')!r}")
    elif expectation == "explicit_cli_precedence":
        assert_true(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.bundle_model_authority",
            bundle.get("model_authority"),
            "hardware_free_regression_fixture_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.bundle_physical_so101_model_authority_ready",
            bundle.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.bundle_hardware_free_regression_fixture_ready",
            bundle.get("hardware_free_regression_fixture_ready"),
        )
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
        synthetic_fields = bundle.get("synthetic_fixture_authority_fields") or []
        if "provenance" not in synthetic_fields:
            errors.append(
                f"{case_id}.synthetic_fixture_authority_fields: expected provenance in {synthetic_fields!r}"
            )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_motion_checked",
        )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_model_authority",
            reviewed_mujoco.get("model_authority"),
            "hardware_free_regression_fixture_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.reviewed_mujoco_physical_so101_model_authority_ready",
            reviewed_mujoco.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.reviewed_mujoco_hardware_free_regression_fixture_ready",
            reviewed_mujoco.get("hardware_free_regression_fixture_ready"),
        )
        assert_true(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_motion_authority_status",
            reviewed_mujoco.get("motion_authority_status"),
            "hardware_free_fixture_motion_checked_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.reviewed_mujoco_physical_reviewed_model_motion_checked",
            reviewed_mujoco.get("physical_reviewed_model_motion_checked"),
        )
        assert_true(
            errors,
            f"{case_id}.reviewed_mujoco_hardware_free_fixture_motion_checked",
            reviewed_mujoco.get("hardware_free_fixture_motion_checked"),
        )
        assert_true(
            errors,
            f"{case_id}.reviewed_mujoco_motion_evidence_not_physical",
            reviewed_mujoco.get("motion_evidence_not_physical_so101_authority"),
        )
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(errors, f"{case_id}.diagnostic_reason", forwarding.get("diagnostic_only_reason"), "explicit_ik_model_path_supplied")
        assert_false(
            errors,
            f"{case_id}.source_inventory_used_bundle",
            source_inventory_forwarding.get("used_for_source_inventory"),
        )
        assert_equal(
            errors,
            f"{case_id}.source_inventory_diagnostic_only_reason",
            source_inventory_forwarding.get("diagnostic_only_reason"),
            "bundle_ready_fixture_not_physical_source_authority",
        )
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
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
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
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
    elif expectation == "mismatched_model_sha_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "not_supplied")
        assert_equal(errors, f"{case_id}.model_identity_status", get_nested(bundle, ("model_identity", "status")), "invalid")
        assert_false(errors, f"{case_id}.model_identity_matches", get_nested(bundle, ("model_identity", "matches")))
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "model_sha256" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected model_sha256, got {missing_inputs!r}")
        diagnostics = get_nested(bundle, ("model_identity", "diagnostics"), [])
        if "model_sha256_mismatch" not in diagnostics:
            errors.append(f"{case_id}.model_identity_diagnostic_missing:{diagnostics!r}")
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "placeholder_review_metadata_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        missing_inputs = set(bundle.get("missing_inputs") or [])
        expected_missing = {
            "authority",
            "joint_limit_authority",
            "mesh_asset_authority",
            "target_frame_authority",
            "tcp_offset_authority",
            "base_to_board_alignment_authority",
        }
        if not expected_missing.issubset(missing_inputs):
            errors.append(
                f"{case_id}.missing_inputs: expected {sorted(expected_missing)!r} subset, got {sorted(missing_inputs)!r}"
            )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "needs_review")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "needs_review")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "needs_review",
        )
        for label, diagnostics in (
            ("authority", bundle.get("authority_diagnostics")),
            ("joint_limits", get_nested(bundle, ("joint_limits", "diagnostics"), [])),
            ("mesh_assets", get_nested(bundle, ("mesh_assets", "diagnostics"), [])),
            ("target_frame", get_nested(bundle, ("target_frame", "diagnostics"), [])),
            ("tcp_offset", get_nested(bundle, ("tcp_offset", "diagnostics"), [])),
            ("alignment", get_nested(bundle, ("base_to_board_alignment", "diagnostics"), [])),
        ):
            if not any("review_evidence_placeholder" in str(item) for item in (diagnostics or [])):
                errors.append(f"{case_id}.{label}_placeholder_diagnostic_missing:{diagnostics!r}")
    elif expectation == "thin_review_evidence_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        missing_inputs = set(bundle.get("missing_inputs") or [])
        expected_missing = {
            "authority",
            "joint_limit_authority",
            "mesh_asset_authority",
            "target_frame_authority",
            "tcp_offset_authority",
            "base_to_board_alignment_authority",
        }
        if not expected_missing.issubset(missing_inputs):
            errors.append(
                f"{case_id}.missing_inputs: expected {sorted(expected_missing)!r} subset, got {sorted(missing_inputs)!r}"
            )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "needs_review")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "needs_review")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "needs_review",
        )
        for label, diagnostics in (
            ("authority", bundle.get("authority_diagnostics")),
            ("joint_limits", get_nested(bundle, ("joint_limits", "diagnostics"), [])),
            ("mesh_assets", get_nested(bundle, ("mesh_assets", "diagnostics"), [])),
            ("target_frame", get_nested(bundle, ("target_frame", "diagnostics"), [])),
            ("tcp_offset", get_nested(bundle, ("tcp_offset", "diagnostics"), [])),
            ("alignment", get_nested(bundle, ("base_to_board_alignment", "diagnostics"), [])),
        ):
            if not any("review_evidence_missing_required_group:review_trace" in str(item) for item in (diagnostics or [])):
                errors.append(f"{case_id}.{label}_review_trace_diagnostic_missing:{diagnostics!r}")
            if not any("review_evidence_missing_required_group:review_artifact" in str(item) for item in (diagnostics or [])):
                errors.append(f"{case_id}.{label}_review_artifact_diagnostic_missing:{diagnostics!r}")
        manifest_summary = load_json_object(
            get_nested(bundle, ("artifact_paths", "summary_json"))
            or get_nested(bundle, ("artifacts", "summary_json"))
        )
        for label, review in (
            ("authority", get_nested(manifest_summary, ("authority",), {})),
            ("joint_limits", get_nested(manifest_summary, ("joint_limits", "review"), {})),
            ("mesh_assets", get_nested(manifest_summary, ("mesh_assets", "review"), {})),
            ("target_frame", get_nested(manifest_summary, ("target_frame", "review"), {})),
            ("tcp_offset", get_nested(manifest_summary, ("tcp_offset", "review"), {})),
            (
                "alignment",
                get_nested(manifest_summary, ("base_to_board_alignment", "review"), {}),
            ),
        ):
            assert_traceable_review_evidence(
                errors,
                f"{case_id}.{label}",
                review,
                expected_missing_groups=["review_trace", "review_artifact"],
            )
    elif expectation == "invalid_review_url_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        missing_inputs = set(bundle.get("missing_inputs") or [])
        expected_missing = {
            "authority",
            "joint_limit_authority",
            "mesh_asset_authority",
            "target_frame_authority",
            "tcp_offset_authority",
            "base_to_board_alignment_authority",
        }
        if not expected_missing.issubset(missing_inputs):
            errors.append(
                f"{case_id}.missing_inputs: expected {sorted(expected_missing)!r} subset, got {sorted(missing_inputs)!r}"
            )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "needs_review")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "needs_review")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "needs_review",
        )
        manifest_summary = load_json_object(
            get_nested(bundle, ("artifact_paths", "summary_json"))
            or get_nested(bundle, ("artifacts", "summary_json"))
        )
        for label, review in (
            ("authority", get_nested(manifest_summary, ("authority",), {})),
            ("joint_limits", get_nested(manifest_summary, ("joint_limits", "review"), {})),
            ("mesh_assets", get_nested(manifest_summary, ("mesh_assets", "review"), {})),
            ("target_frame", get_nested(manifest_summary, ("target_frame", "review"), {})),
            ("tcp_offset", get_nested(manifest_summary, ("tcp_offset", "review"), {})),
            (
                "alignment",
                get_nested(manifest_summary, ("base_to_board_alignment", "review"), {}),
            ),
        ):
            assert_contains_all(
                errors,
                f"{case_id}.{label}.review_evidence_invalid_fields",
                review.get("review_evidence_invalid_fields"),
                ["review_url"],
            )
            assert_contains_all(
                errors,
                f"{case_id}.{label}.review_evidence_missing_required_groups",
                review_group_names(review, "review_evidence_missing_required_groups"),
                ["review_artifact"],
            )
    elif expectation == "generic_review_scope_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        missing_inputs = set(bundle.get("missing_inputs") or [])
        expected_missing = {
            "authority",
            "joint_limit_authority",
            "mesh_asset_authority",
            "target_frame_authority",
            "tcp_offset_authority",
            "base_to_board_alignment_authority",
        }
        if not expected_missing.issubset(missing_inputs):
            errors.append(
                f"{case_id}.missing_inputs: expected {sorted(expected_missing)!r} subset, got {sorted(missing_inputs)!r}"
            )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "needs_review")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "needs_review")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "needs_review",
        )
        manifest_summary = load_json_object(
            get_nested(bundle, ("artifact_paths", "summary_json"))
            or get_nested(bundle, ("artifacts", "summary_json"))
        )
        for label, review, missing_scopes in (
            ("authority", get_nested(manifest_summary, ("authority",), {}), ["model_identity", "provenance", "license"]),
            ("joint_limits", get_nested(manifest_summary, ("joint_limits", "review"), {}), ["joint_limits"]),
            ("mesh_assets", get_nested(manifest_summary, ("mesh_assets", "review"), {}), ["mesh_assets"]),
            ("target_frame", get_nested(manifest_summary, ("target_frame", "review"), {}), ["target_frame"]),
            ("tcp_offset", get_nested(manifest_summary, ("tcp_offset", "review"), {}), ["tcp_offset"]),
            (
                "alignment",
                get_nested(manifest_summary, ("base_to_board_alignment", "review"), {}),
                ["base_to_board_alignment"],
            ),
        ):
            assert_missing_review_scopes(
                errors,
                f"{case_id}.{label}",
                review,
                expected_missing_scopes=missing_scopes,
            )
    elif expectation == "pending_review_metadata_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        missing_inputs = set(bundle.get("missing_inputs") or [])
        expected_missing = {
            "authority",
            "joint_limit_authority",
            "mesh_asset_authority",
            "target_frame_authority",
            "tcp_offset_authority",
            "base_to_board_alignment_authority",
        }
        if not expected_missing.issubset(missing_inputs):
            errors.append(
                f"{case_id}.missing_inputs: expected {sorted(expected_missing)!r} subset, got {sorted(missing_inputs)!r}"
            )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "needs_review")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "needs_review")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "needs_review",
        )
        manifest_summary = load_json_object(
            get_nested(bundle, ("artifact_paths", "summary_json"))
            or get_nested(bundle, ("artifacts", "summary_json"))
        )
        for label, review, expected_open_work_fields in (
            (
                "authority",
                get_nested(manifest_summary, ("authority",), {}),
                ["missing_inputs", "next_required_action_ids"],
            ),
            (
                "joint_limits",
                get_nested(manifest_summary, ("joint_limits", "review"), {}),
                ["next_required_action_ids"],
            ),
            (
                "mesh_assets",
                get_nested(manifest_summary, ("mesh_assets", "review"), {}),
                ["next_required_action_ids"],
            ),
            (
                "target_frame",
                get_nested(manifest_summary, ("target_frame", "review"), {}),
                ["next_required_action_ids"],
            ),
            (
                "tcp_offset",
                get_nested(manifest_summary, ("tcp_offset", "review"), {}),
                ["next_required_action_ids"],
            ),
            (
                "alignment",
                get_nested(manifest_summary, ("base_to_board_alignment", "review"), {}),
                ["next_required_action_ids"],
            ),
        ):
            assert_review_open_work_fields(
                errors,
                f"{case_id}.{label}",
                review,
                expected_open_work_fields=expected_open_work_fields,
            )
    elif expectation == "weak_review_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "needs_review")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "needs_review")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "authority" not in missing_inputs or "provenance" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected authority and provenance, got {missing_inputs!r}")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "placeholder_provenance_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "not_supplied")
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "needs_review")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "provenance" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected provenance, got {missing_inputs!r}")
        diagnostics = bundle.get("provenance_diagnostics") or []
        expected_diagnostics = {
            "provenance_source_reference_placeholder:source_url",
            "provenance_export_tool_placeholder:export_tool",
            "provenance_license_basis_placeholder:license",
        }
        missing_diagnostics = [
            diagnostic
            for diagnostic in sorted(expected_diagnostics)
            if diagnostic not in diagnostics
        ]
        if missing_diagnostics:
            errors.append(
                f"{case_id}.provenance_diagnostics: missing {missing_diagnostics!r} from {diagnostics!r}"
            )
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "invalid_provenance_url_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "not_supplied")
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "needs_review")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "provenance" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected provenance, got {missing_inputs!r}")
        diagnostics = bundle.get("provenance_diagnostics") or []
        expected_diagnostics = {
            "provenance_source_reference_invalid:source_url",
        }
        missing_diagnostics = [
            diagnostic
            for diagnostic in sorted(expected_diagnostics)
            if diagnostic not in diagnostics
        ]
        if missing_diagnostics:
            errors.append(
                f"{case_id}.provenance_diagnostics: missing {missing_diagnostics!r} from {diagnostics!r}"
            )
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "fixture_provenance_reviewed_authority_not_physical":
        assert_true(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.bundle_model_authority",
            bundle.get("model_authority"),
            "hardware_free_regression_fixture_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.bundle_physical_so101_model_authority_ready",
            bundle.get("physical_so101_model_authority_ready"),
        )
        assert_true(
            errors,
            f"{case_id}.bundle_hardware_free_regression_fixture_ready",
            bundle.get("hardware_free_regression_fixture_ready"),
        )
        assert_equal(
            errors,
            f"{case_id}.synthetic_fixture_authority_fields",
            bundle.get("synthetic_fixture_authority_fields"),
            ["provenance"],
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_true(
            errors,
            f"{case_id}.provenance_synthetic_fixture_only",
            bundle.get("provenance_synthetic_fixture_only"),
        )
        assert_equal(
            errors,
            f"{case_id}.provenance_fixture_only_fields",
            bundle.get("provenance_fixture_only_fields"),
            ["source_path", "export_tool", "license"],
        )
        diagnostics = bundle.get("provenance_diagnostics") or []
        expected_diagnostics = {
            "provenance_fixture_only:source_path",
            "provenance_fixture_only:export_tool",
            "provenance_fixture_only:license",
        }
        missing_diagnostics = [
            diagnostic
            for diagnostic in sorted(expected_diagnostics)
            if diagnostic not in diagnostics
        ]
        if missing_diagnostics:
            errors.append(
                f"{case_id}.provenance_diagnostics: missing {missing_diagnostics!r} from {diagnostics!r}"
            )
        assert_equal(errors, f"{case_id}.missing_inputs", bundle.get("missing_inputs"), [])
        assert_equal(
            errors,
            f"{case_id}.physical_authority_blockers",
            bundle.get("physical_authority_blockers"),
            ["synthetic_fixture_authority_not_physical_so101:provenance"],
        )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_motion_checked",
        )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_model_authority",
            reviewed_mujoco.get("model_authority"),
            "hardware_free_regression_fixture_not_physical_so101_authority",
        )
        assert_false(
            errors,
            f"{case_id}.reviewed_mujoco_physical_so101_model_authority_ready",
            reviewed_mujoco.get("physical_so101_model_authority_ready"),
        )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_synthetic_fields",
            reviewed_mujoco.get("synthetic_fixture_authority_fields"),
            ["provenance"],
        )
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_motion_authority_status",
            reviewed_mujoco.get("motion_authority_status"),
            "hardware_free_fixture_motion_checked_not_physical_so101_authority",
        )
        assert_false(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.ik_model_path_source",
            forwarding.get("ik_model_path_source"),
            "so101_model_bundle_manifest",
        )
        assert_false(
            errors,
            f"{case_id}.source_inventory_used_bundle",
            source_inventory_forwarding.get("used_for_source_inventory"),
        )
        assert_equal(
            errors,
            f"{case_id}.source_inventory_diagnostic_only_reason",
            source_inventory_forwarding.get("diagnostic_only_reason"),
            "bundle_ready_fixture_not_physical_source_authority",
        )
        assert_true(
            errors,
            f"{case_id}.source_inventory_requires_physical_so101_model_authority",
            source_inventory_forwarding.get("requires_physical_so101_model_authority"),
        )
        assert_equal(
            errors,
            f"{case_id}.source_authority_review_source",
            source_authority_review.get("source"),
            "not_supplied",
        )
    elif expectation == "weak_joint_limit_authority_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "needs_review")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "joint_limit_authority" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected joint_limit_authority, got {missing_inputs!r}")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "weak_mesh_asset_authority_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "needs_review")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "mesh_asset_authority" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected mesh_asset_authority, got {missing_inputs!r}")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "weak_target_frame_authority_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "needs_review")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "target_frame_authority" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected target_frame_authority, got {missing_inputs!r}")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "wrong_target_frame_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "invalid")
        assert_equal(errors, f"{case_id}.target_frame_value", get_nested(bundle, ("target_frame", "value")), "not_gripper_frame_link")
        diagnostics = get_nested(bundle, ("target_frame", "diagnostics"), [])
        if "target_frame_differs_from_default" not in diagnostics:
            errors.append(f"{case_id}.target_frame_diagnostic_missing:{diagnostics!r}")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "target_frame" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected target_frame, got {missing_inputs!r}")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
    elif expectation == "model_missing_target_frame_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "non_blocking_contract_checker_result" not in missing_inputs:
            errors.append(
                f"{case_id}.missing_inputs: expected non_blocking_contract_checker_result, got {missing_inputs!r}"
            )
        contract_checker = bundle.get("contract_checker")
        structure = get_nested(contract_checker or {}, ("child_diagnostics", "model_structure_inspection"), {})
        assert_false(
            errors,
            f"{case_id}.contract_model_target_frame_present",
            structure.get("target_frame_present"),
        )
        diagnostics = []
        for field_check in bundle.get("field_checks") or []:
            if isinstance(field_check, dict) and field_check.get("requirement_id") == "contract_checker_result":
                diagnostics = field_check.get("diagnostics") or []
                break
        if not any("model_structure_target_frame_present:False" == str(item) for item in diagnostics):
            errors.append(f"{case_id}.contract_checker_diagnostic_missing:{diagnostics!r}")
    elif expectation == "weak_tcp_offset_authority_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "needs_review")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "tcp_offset_authority" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected tcp_offset_authority, got {missing_inputs!r}")
    elif expectation == "invalid_tcp_offset_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "not_supplied")
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "invalid")
        assert_equal(errors, f"{case_id}.alignment_status", get_nested(bundle, ("base_to_board_alignment", "status")), "present")
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "tcp_offset_m" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected tcp_offset_m, got {missing_inputs!r}")
        diagnostics = get_nested(bundle, ("tcp_offset", "diagnostics"), [])
        if "missing_axis:z" not in diagnostics:
            errors.append(f"{case_id}.tcp_offset_diagnostic_missing:{diagnostics!r}")
    elif expectation == "weak_alignment_authority_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "needs_review",
        )
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "base_to_board_alignment_authority" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected base_to_board_alignment_authority, got {missing_inputs!r}")
    elif expectation == "invalid_alignment_transform_not_forwarded":
        assert_false(errors, f"{case_id}.bundle_ready", bundle.get("ready_for_model_backed_ik"))
        assert_equal(
            errors,
            f"{case_id}.reviewed_mujoco_status",
            reviewed_mujoco.get("status"),
            "reviewed_mujoco_bundle_not_ready",
        )
        assert_false(errors, f"{case_id}.reviewed_mujoco_motion_checked", reviewed_mujoco.get("reviewed_model_motion_checked"))
        assert_not_ready_motion_authority(errors, case_id, reviewed_mujoco)
        assert_true(errors, f"{case_id}.forwarding_diagnostic_only", forwarding.get("diagnostic_only"))
        assert_equal(
            errors,
            f"{case_id}.diagnostic_reason",
            forwarding.get("diagnostic_only_reason"),
            "bundle_not_ready_for_model_backed_ik:model_bundle_manifest_needs_follow_up",
        )
        assert_false(errors, f"{case_id}.used_for_downstream_contract", forwarding.get("used_for_downstream_contract"))
        assert_equal(errors, f"{case_id}.ik_model_path_source", forwarding.get("ik_model_path_source"), "not_supplied")
        assert_equal(errors, f"{case_id}.authority_status", bundle.get("authority_status"), "present")
        assert_equal(errors, f"{case_id}.provenance_status", bundle.get("provenance_status"), "present")
        assert_equal(errors, f"{case_id}.joint_limits_status", get_nested(bundle, ("joint_limits", "status")), "present")
        assert_equal(errors, f"{case_id}.mesh_assets_status", get_nested(bundle, ("mesh_assets", "status")), "present")
        assert_equal(errors, f"{case_id}.target_frame_status", get_nested(bundle, ("target_frame", "status")), "present")
        assert_equal(errors, f"{case_id}.tcp_offset_status", get_nested(bundle, ("tcp_offset", "status")), "present")
        assert_equal(
            errors,
            f"{case_id}.alignment_status",
            get_nested(bundle, ("base_to_board_alignment", "status")),
            "invalid",
        )
        missing_inputs = bundle.get("missing_inputs")
        if not isinstance(missing_inputs, list) or "base_to_board_transform" not in missing_inputs:
            errors.append(f"{case_id}.missing_inputs: expected base_to_board_transform, got {missing_inputs!r}")
        diagnostics = get_nested(bundle, ("base_to_board_alignment", "diagnostics"), [])
        if "base_to_board_rotation_rpy_missing" not in diagnostics:
            errors.append(f"{case_id}.alignment_diagnostic_missing:{diagnostics!r}")
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
            "bundle_model_authority": bundle.get("model_authority"),
            "bundle_physical_so101_model_authority_ready": bundle.get(
                "physical_so101_model_authority_ready"
            ),
            "bundle_hardware_free_regression_fixture_ready": bundle.get(
                "hardware_free_regression_fixture_ready"
            ),
            "bundle_synthetic_fixture_authority_fields": bundle.get("synthetic_fixture_authority_fields"),
            "bundle_forwarding": forwarding,
            "source_inventory_forwarding": source_inventory_forwarding,
            "source_authority_review": source_authority_review,
            "bundle_model_identity_status": get_nested(bundle, ("model_identity", "status")),
            "bundle_model_identity_matches": get_nested(bundle, ("model_identity", "matches")),
            "bundle_authority_status": bundle.get("authority_status"),
            "bundle_provenance_status": bundle.get("provenance_status"),
            "bundle_joint_limits_status": get_nested(bundle, ("joint_limits", "status")),
            "bundle_mesh_assets_status": get_nested(bundle, ("mesh_assets", "status")),
            "bundle_target_frame_status": get_nested(bundle, ("target_frame", "status")),
            "bundle_tcp_offset_status": get_nested(bundle, ("tcp_offset", "status")),
            "bundle_alignment_status": get_nested(bundle, ("base_to_board_alignment", "status")),
            "bundle_missing_inputs": bundle.get("missing_inputs"),
            "contract_model_request": contract.get("model_request"),
            "contract_asset_preflight": contract_preflight,
            "bundle_asset_preflight": bundle_preflight,
            "bundle_joint_limits": bundle.get("joint_limits"),
            "bundle_mesh_assets": bundle.get("mesh_assets"),
            "bundle_target_frame": bundle.get("target_frame"),
            "bundle_tcp_offset": bundle.get("tcp_offset"),
            "bundle_alignment": bundle.get("base_to_board_alignment"),
            "reviewed_mujoco_bundle": reviewed_mujoco,
            "artifact_index_missing_count": artifact_index_missing_count,
        },
    }


def flatten_case_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        forwarding = case["observations"]["bundle_forwarding"]
        source_inventory_forwarding = case["observations"]["source_inventory_forwarding"]
        source_authority_review = case["observations"]["source_authority_review"]
        reviewed_mujoco = case["observations"]["reviewed_mujoco_bundle"]
        rows.append(
            {
                "case_id": case["case_id"],
                "ok": case["ok"],
                "suite_status": case["observations"]["suite_status"],
                "bundle_ready": case["observations"]["bundle_ready"],
                "model_identity_status": case["observations"].get("bundle_model_identity_status"),
                "authority_status": case["observations"].get("bundle_authority_status"),
                "provenance_status": case["observations"].get("bundle_provenance_status"),
                "joint_limits_status": case["observations"].get("bundle_joint_limits_status"),
                "mesh_assets_status": case["observations"].get("bundle_mesh_assets_status"),
                "target_frame_status": case["observations"].get("bundle_target_frame_status"),
                "tcp_offset_status": case["observations"].get("bundle_tcp_offset_status"),
                "alignment_status": case["observations"].get("bundle_alignment_status"),
                "missing_inputs": case["observations"].get("bundle_missing_inputs"),
                "reviewed_mujoco_status": reviewed_mujoco.get("status"),
                "reviewed_model_motion_checked": reviewed_mujoco.get("reviewed_model_motion_checked"),
                "motion_authority_status": reviewed_mujoco.get("motion_authority_status"),
                "physical_reviewed_model_motion_checked": reviewed_mujoco.get(
                    "physical_reviewed_model_motion_checked"
                ),
                "hardware_free_fixture_motion_checked": reviewed_mujoco.get("hardware_free_fixture_motion_checked"),
                "motion_evidence_not_physical_so101_authority": reviewed_mujoco.get(
                    "motion_evidence_not_physical_so101_authority"
                ),
                "forwarding_diagnostic_only": forwarding.get("diagnostic_only"),
                "diagnostic_only_reason": forwarding.get("diagnostic_only_reason"),
                "ik_model_path_source": forwarding.get("ik_model_path_source"),
                "ik_model_asset_root_source": forwarding.get("ik_model_asset_root_source"),
                "source_inventory_used_bundle": source_inventory_forwarding.get(
                    "used_for_source_inventory"
                ),
                "source_inventory_diagnostic_only_reason": (
                    source_inventory_forwarding.get("diagnostic_only_reason")
                ),
                "source_inventory_requires_physical_authority": (
                    source_inventory_forwarding.get(
                        "requires_physical_so101_model_authority"
                    )
                ),
                "source_inventory_physical_authority_ready": (
                    source_inventory_forwarding.get(
                        "physical_so101_model_authority_ready"
                    )
                ),
                "source_inventory_fixture_ready": source_inventory_forwarding.get(
                    "hardware_free_regression_fixture_ready"
                ),
                "source_inventory_model_source_root_source": (
                    source_inventory_forwarding.get("model_source_root_source")
                ),
                "source_inventory_authoritative_model_path_source": (
                    source_inventory_forwarding.get("authoritative_model_path_source")
                ),
                "source_authority_review_source": source_authority_review.get("source"),
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
            "case_id": "mismatched_model_sha_not_forwarded",
            "manifest_path": fixtures["mismatched_model_sha_manifest_path"],
            "explicit_model_path": None,
            "expectation": "mismatched_model_sha_not_forwarded",
        },
        {
            "case_id": "placeholder_manifest_not_forwarded",
            "manifest_path": fixtures["placeholder_manifest_path"],
            "explicit_model_path": None,
            "expectation": "placeholder_not_forwarded",
        },
        {
            "case_id": "placeholder_review_metadata_not_forwarded",
            "manifest_path": fixtures["placeholder_review_manifest_path"],
            "explicit_model_path": None,
            "expectation": "placeholder_review_metadata_not_forwarded",
        },
        {
            "case_id": "thin_review_evidence_not_forwarded",
            "manifest_path": fixtures["thin_review_manifest_path"],
            "explicit_model_path": None,
            "expectation": "thin_review_evidence_not_forwarded",
        },
        {
            "case_id": "invalid_review_url_not_forwarded",
            "manifest_path": fixtures["invalid_review_url_manifest_path"],
            "explicit_model_path": None,
            "expectation": "invalid_review_url_not_forwarded",
        },
        {
            "case_id": "generic_review_scope_not_forwarded",
            "manifest_path": fixtures["generic_review_scope_manifest_path"],
            "explicit_model_path": None,
            "expectation": "generic_review_scope_not_forwarded",
        },
        {
            "case_id": "pending_review_metadata_not_forwarded",
            "manifest_path": fixtures["pending_review_metadata_manifest_path"],
            "explicit_model_path": None,
            "expectation": "pending_review_metadata_not_forwarded",
        },
        {
            "case_id": "weak_review_manifest_not_forwarded",
            "manifest_path": fixtures["weak_review_manifest_path"],
            "explicit_model_path": None,
            "expectation": "weak_review_not_forwarded",
        },
        {
            "case_id": "placeholder_provenance_not_forwarded",
            "manifest_path": fixtures["placeholder_provenance_manifest_path"],
            "explicit_model_path": None,
            "expectation": "placeholder_provenance_not_forwarded",
        },
        {
            "case_id": "invalid_provenance_url_not_forwarded",
            "manifest_path": fixtures["invalid_provenance_url_manifest_path"],
            "explicit_model_path": None,
            "expectation": "invalid_provenance_url_not_forwarded",
        },
        {
            "case_id": "fixture_provenance_reviewed_authority_not_physical",
            "manifest_path": fixtures[
                "fixture_provenance_reviewed_authority_manifest_path"
            ],
            "explicit_model_path": None,
            "expectation": "fixture_provenance_reviewed_authority_not_physical",
        },
        {
            "case_id": "weak_joint_limit_authority_not_forwarded",
            "manifest_path": fixtures["weak_joint_limits_manifest_path"],
            "explicit_model_path": None,
            "expectation": "weak_joint_limit_authority_not_forwarded",
        },
        {
            "case_id": "weak_mesh_asset_authority_not_forwarded",
            "manifest_path": fixtures["weak_mesh_manifest_path"],
            "explicit_model_path": None,
            "expectation": "weak_mesh_asset_authority_not_forwarded",
        },
        {
            "case_id": "weak_target_frame_authority_not_forwarded",
            "manifest_path": fixtures["weak_target_frame_manifest_path"],
            "explicit_model_path": None,
            "expectation": "weak_target_frame_authority_not_forwarded",
        },
        {
            "case_id": "wrong_target_frame_not_forwarded",
            "manifest_path": fixtures["wrong_target_frame_manifest_path"],
            "explicit_model_path": None,
            "expectation": "wrong_target_frame_not_forwarded",
        },
        {
            "case_id": "model_missing_target_frame_not_forwarded",
            "manifest_path": fixtures["model_missing_target_frame_manifest_path"],
            "explicit_model_path": None,
            "expectation": "model_missing_target_frame_not_forwarded",
        },
        {
            "case_id": "weak_tcp_offset_authority_not_forwarded",
            "manifest_path": fixtures["weak_tcp_manifest_path"],
            "explicit_model_path": None,
            "expectation": "weak_tcp_offset_authority_not_forwarded",
        },
        {
            "case_id": "invalid_tcp_offset_not_forwarded",
            "manifest_path": fixtures["invalid_tcp_manifest_path"],
            "explicit_model_path": None,
            "expectation": "invalid_tcp_offset_not_forwarded",
        },
        {
            "case_id": "weak_alignment_authority_not_forwarded",
            "manifest_path": fixtures["weak_alignment_manifest_path"],
            "explicit_model_path": None,
            "expectation": "weak_alignment_authority_not_forwarded",
        },
        {
            "case_id": "invalid_alignment_transform_not_forwarded",
            "manifest_path": fixtures["invalid_alignment_manifest_path"],
            "explicit_model_path": None,
            "expectation": "invalid_alignment_transform_not_forwarded",
        },
    ]
    if args.case_id:
        selected_case_ids = set(args.case_id)
        known_case_ids = {case["case_id"] for case in case_specs}
        unknown_case_ids = sorted(selected_case_ids - known_case_ids)
        if unknown_case_ids:
            raise SystemExit(f"unknown --case-id value(s): {', '.join(unknown_case_ids)}")
        case_specs = [case for case in case_specs if case["case_id"] in selected_case_ids]

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
