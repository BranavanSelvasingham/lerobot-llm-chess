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
        f"- `mismatched_model_sha_manifest`: `{summary['fixtures']['mismatched_model_sha_manifest_path']}`",
        f"- `placeholder_manifest`: `{summary['fixtures']['placeholder_manifest_path']}`",
        f"- `placeholder_review_manifest`: `{summary['fixtures']['placeholder_review_manifest_path']}`",
        f"- `thin_review_manifest`: `{summary['fixtures']['thin_review_manifest_path']}`",
        f"- `weak_review_manifest`: `{summary['fixtures']['weak_review_manifest_path']}`",
        f"- `placeholder_provenance_manifest`: `{summary['fixtures']['placeholder_provenance_manifest_path']}`",
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
            "scope": "hardware-free forwarding regression only",
        },
        "provenance": {
            "source_url": "local synthetic fixture",
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
            "scope": "hardware-free forwarding regression only",
        },
        "mesh_asset_authority": {
            "mesh_asset_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:mesh-assets",
            "scope": "hardware-free forwarding regression only",
        },
        "tcp_offset_authority": {
            "tcp_offset_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:tcp-offset",
            "scope": "hardware-free forwarding regression only",
        },
        "base_to_board_alignment_authority": {
            "base_to_board_alignment_authority_status": "synthetic_fixture_reviewed_for_automation_only",
            "reviewed_by": "smoke_sim_so101_bundle_ready_forwarding",
            "reviewed_at": "2026-06-18",
            "review_id": "bundle-ready-forwarding:base-to-board",
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
        payload[review_field]["reviewed_by"] = "TODO"
        payload[review_field]["reviewed_at"] = "TBD"
        payload[review_field]["review_id"] = "TODO"
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


def weak_joint_limit_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("joint_limit_authority", None)
    return payload


def weak_mesh_asset_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("mesh_asset_authority", None)
    return payload


def weak_target_frame_authority_manifest_payload(model_filename: str) -> dict[str, Any]:
    payload = manifest_payload(ready=True, model_filename=model_filename)
    payload.pop("target_frame_authority", None)
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


def create_fixtures(output_dir: Path) -> dict[str, Path]:
    fixture_dir = output_dir / "fixtures"
    bundle_dir = fixture_dir / "ready_bundle"
    mismatched_model_sha_dir = fixture_dir / "mismatched_model_sha_bundle"
    placeholder_dir = fixture_dir / "placeholder_bundle"
    placeholder_review_dir = fixture_dir / "placeholder_review_bundle"
    thin_review_dir = fixture_dir / "thin_review_bundle"
    invalid_review_url_dir = fixture_dir / "invalid_review_url_bundle"
    weak_review_dir = fixture_dir / "weak_review_bundle"
    placeholder_provenance_dir = fixture_dir / "placeholder_provenance_bundle"
    fixture_provenance_reviewed_authority_dir = (
        fixture_dir / "fixture_provenance_reviewed_authority_bundle"
    )
    weak_joint_limits_dir = fixture_dir / "weak_joint_limits_bundle"
    weak_mesh_dir = fixture_dir / "weak_mesh_bundle"
    weak_target_frame_dir = fixture_dir / "weak_target_frame_bundle"
    wrong_target_frame_dir = fixture_dir / "wrong_target_frame_bundle"
    model_missing_target_frame_dir = fixture_dir / "model_missing_target_frame_bundle"
    weak_tcp_dir = fixture_dir / "weak_tcp_bundle"
    invalid_tcp_dir = fixture_dir / "invalid_tcp_bundle"
    weak_alignment_dir = fixture_dir / "weak_alignment_bundle"
    invalid_alignment_dir = fixture_dir / "invalid_alignment_bundle"
    explicit_dir = fixture_dir / "explicit_cli"

    for root in (
        bundle_dir,
        mismatched_model_sha_dir,
        placeholder_dir,
        placeholder_review_dir,
        thin_review_dir,
        invalid_review_url_dir,
        weak_review_dir,
        placeholder_provenance_dir,
        fixture_provenance_reviewed_authority_dir,
        weak_joint_limits_dir,
        weak_mesh_dir,
        weak_target_frame_dir,
        wrong_target_frame_dir,
        model_missing_target_frame_dir,
        weak_tcp_dir,
        invalid_tcp_dir,
        weak_alignment_dir,
        invalid_alignment_dir,
    ):
        (root / "model").mkdir(parents=True, exist_ok=True)
        (root / "model" / "meshes").mkdir(parents=True, exist_ok=True)
        (root / "assets" / "meshes").mkdir(parents=True, exist_ok=True)
        (root / "model" / "synthetic_so101.urdf").write_text(synthetic_urdf(include_mesh=True))
        (root / "model" / "meshes" / "synthetic_gripper_shell.obj").write_text(obj_text())
        (root / "assets" / "meshes" / "synthetic_gripper_shell.obj").write_text(obj_text())

    ready_model_path = bundle_dir / "model" / "synthetic_so101_mujoco.xml"
    ready_model_path.write_text(mjcf_with_mesh_reference())
    mismatched_model_sha_model_path = (
        mismatched_model_sha_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    mismatched_model_sha_model_path.write_text(mjcf_with_mesh_reference())
    placeholder_review_model_path = placeholder_review_dir / "model" / "synthetic_so101_mujoco.xml"
    placeholder_review_model_path.write_text(mjcf_with_mesh_reference())
    thin_review_model_path = thin_review_dir / "model" / "synthetic_so101_mujoco.xml"
    thin_review_model_path.write_text(mjcf_with_mesh_reference())
    invalid_review_url_model_path = invalid_review_url_dir / "model" / "synthetic_so101_mujoco.xml"
    invalid_review_url_model_path.write_text(mjcf_with_mesh_reference())
    weak_review_model_path = weak_review_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_review_model_path.write_text(mjcf_with_mesh_reference())
    placeholder_provenance_model_path = (
        placeholder_provenance_dir / "model" / "synthetic_so101_mujoco.xml"
    )
    placeholder_provenance_model_path.write_text(mjcf_with_mesh_reference())
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
    weak_mesh_model_path = weak_mesh_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_mesh_model_path.write_text(mjcf_with_mesh_reference())
    weak_target_frame_model_path = weak_target_frame_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_target_frame_model_path.write_text(mjcf_with_mesh_reference())
    wrong_target_frame_model_path = wrong_target_frame_dir / "model" / "synthetic_so101_mujoco.xml"
    wrong_target_frame_model_path.write_text(mjcf_with_mesh_reference())
    model_missing_target_frame_path = model_missing_target_frame_dir / "model" / "synthetic_so101_mujoco.xml"
    model_missing_target_frame_path.write_text(mjcf_missing_target_frame_with_mesh_reference())
    weak_tcp_model_path = weak_tcp_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_tcp_model_path.write_text(mjcf_with_mesh_reference())
    invalid_tcp_model_path = invalid_tcp_dir / "model" / "synthetic_so101_mujoco.xml"
    invalid_tcp_model_path.write_text(mjcf_with_mesh_reference())
    weak_alignment_model_path = weak_alignment_dir / "model" / "synthetic_so101_mujoco.xml"
    weak_alignment_model_path.write_text(mjcf_with_mesh_reference())
    invalid_alignment_model_path = invalid_alignment_dir / "model" / "synthetic_so101_mujoco.xml"
    invalid_alignment_model_path.write_text(mjcf_with_mesh_reference())

    explicit_dir.mkdir(parents=True, exist_ok=True)
    explicit_model_path = explicit_dir / "explicit_cli_so101.urdf"
    explicit_model_path.write_text(synthetic_urdf(include_mesh=False))
    placeholder_model_path = placeholder_dir / "model" / "synthetic_so101.urdf"

    ready_manifest_path = bundle_dir / "so101_model_bundle.ready.json"
    mismatched_model_sha_manifest_path = (
        mismatched_model_sha_dir / "so101_model_bundle.mismatched_model_sha.json"
    )
    placeholder_manifest_path = placeholder_dir / "so101_model_bundle.placeholder.json"
    placeholder_review_manifest_path = placeholder_review_dir / "so101_model_bundle.placeholder_review.json"
    thin_review_manifest_path = thin_review_dir / "so101_model_bundle.thin_review.json"
    invalid_review_url_manifest_path = invalid_review_url_dir / "so101_model_bundle.invalid_review_url.json"
    weak_review_manifest_path = weak_review_dir / "so101_model_bundle.weak_review.json"
    placeholder_provenance_manifest_path = (
        placeholder_provenance_dir / "so101_model_bundle.placeholder_provenance.json"
    )
    fixture_provenance_reviewed_authority_manifest_path = (
        fixture_provenance_reviewed_authority_dir
        / "so101_model_bundle.fixture_provenance_reviewed_authority.json"
    )
    weak_joint_limits_manifest_path = weak_joint_limits_dir / "so101_model_bundle.weak_joint_limits.json"
    weak_mesh_manifest_path = weak_mesh_dir / "so101_model_bundle.weak_mesh_assets.json"
    weak_target_frame_manifest_path = weak_target_frame_dir / "so101_model_bundle.weak_target_frame.json"
    wrong_target_frame_manifest_path = wrong_target_frame_dir / "so101_model_bundle.wrong_target_frame.json"
    model_missing_target_frame_manifest_path = (
        model_missing_target_frame_dir / "so101_model_bundle.model_missing_target_frame.json"
    )
    weak_tcp_manifest_path = weak_tcp_dir / "so101_model_bundle.weak_tcp_offset.json"
    invalid_tcp_manifest_path = invalid_tcp_dir / "so101_model_bundle.invalid_tcp_offset.json"
    weak_alignment_manifest_path = weak_alignment_dir / "so101_model_bundle.weak_alignment.json"
    invalid_alignment_manifest_path = invalid_alignment_dir / "so101_model_bundle.invalid_alignment.json"
    write_manifest_json(
        ready_manifest_path,
        manifest_payload(ready=True, model_filename=ready_model_path.name),
        ready_model_path,
    )
    write_json(
        mismatched_model_sha_manifest_path,
        mismatched_model_sha_manifest_payload(
            model_filename=mismatched_model_sha_model_path.name
        ),
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
        weak_mesh_manifest_path,
        weak_mesh_asset_authority_manifest_payload(model_filename=weak_mesh_model_path.name),
        weak_mesh_model_path,
    )
    write_manifest_json(
        weak_target_frame_manifest_path,
        weak_target_frame_authority_manifest_payload(model_filename=weak_target_frame_model_path.name),
        weak_target_frame_model_path,
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
        weak_alignment_manifest_path,
        weak_alignment_authority_manifest_payload(model_filename=weak_alignment_model_path.name),
        weak_alignment_model_path,
    )
    write_manifest_json(
        invalid_alignment_manifest_path,
        invalid_alignment_transform_manifest_payload(model_filename=invalid_alignment_model_path.name),
        invalid_alignment_model_path,
    )

    return {
        "ready_manifest_path": ready_manifest_path,
        "mismatched_model_sha_manifest_path": mismatched_model_sha_manifest_path,
        "placeholder_manifest_path": placeholder_manifest_path,
        "placeholder_review_manifest_path": placeholder_review_manifest_path,
        "thin_review_manifest_path": thin_review_manifest_path,
        "invalid_review_url_manifest_path": invalid_review_url_manifest_path,
        "weak_review_manifest_path": weak_review_manifest_path,
        "placeholder_provenance_manifest_path": placeholder_provenance_manifest_path,
        "fixture_provenance_reviewed_authority_manifest_path": (
            fixture_provenance_reviewed_authority_manifest_path
        ),
        "weak_joint_limits_manifest_path": weak_joint_limits_manifest_path,
        "weak_mesh_manifest_path": weak_mesh_manifest_path,
        "weak_target_frame_manifest_path": weak_target_frame_manifest_path,
        "wrong_target_frame_manifest_path": wrong_target_frame_manifest_path,
        "model_missing_target_frame_manifest_path": model_missing_target_frame_manifest_path,
        "weak_tcp_manifest_path": weak_tcp_manifest_path,
        "invalid_tcp_manifest_path": invalid_tcp_manifest_path,
        "weak_alignment_manifest_path": weak_alignment_manifest_path,
        "invalid_alignment_manifest_path": invalid_alignment_manifest_path,
        "ready_model_path": ready_model_path,
        "mismatched_model_sha_model_path": mismatched_model_sha_model_path,
        "ready_asset_root": bundle_dir / "assets",
        "placeholder_review_model_path": placeholder_review_model_path,
        "thin_review_model_path": thin_review_model_path,
        "invalid_review_url_model_path": invalid_review_url_model_path,
        "weak_review_model_path": weak_review_model_path,
        "placeholder_provenance_model_path": placeholder_provenance_model_path,
        "fixture_provenance_reviewed_authority_model_path": (
            fixture_provenance_reviewed_authority_model_path
        ),
        "weak_joint_limits_model_path": weak_joint_limits_model_path,
        "weak_mesh_model_path": weak_mesh_model_path,
        "weak_target_frame_model_path": weak_target_frame_model_path,
        "wrong_target_frame_model_path": wrong_target_frame_model_path,
        "model_missing_target_frame_path": model_missing_target_frame_path,
        "weak_tcp_model_path": weak_tcp_model_path,
        "invalid_tcp_model_path": invalid_tcp_model_path,
        "weak_alignment_model_path": weak_alignment_model_path,
        "invalid_alignment_model_path": invalid_alignment_model_path,
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
            ["source_url", "export_tool", "license"],
        )
        diagnostics = bundle.get("provenance_diagnostics") or []
        expected_diagnostics = {
            "provenance_fixture_only:source_url",
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
