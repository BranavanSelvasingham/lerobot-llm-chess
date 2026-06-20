#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

SCHEMA = "lerobot.sim.so101_public_candidate_intake.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_public_candidate_intake"
DEFAULT_REPOSITORY_URL = "https://github.com/TheRobotStudio/SO-ARM100"
DEFAULT_SOURCE_TREE_URL = (
    "https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation/SO101"
)
DEFAULT_MODEL_RELATIVE_PATH = "so101_new_calib.urdf"
EXPECTED_TARGET_FRAME = "gripper_frame_link"
EXPECTED_SO101_JOINTS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
REQUIRED_REVIEW_SCOPES = (
    "model_identity",
    "provenance",
    "license",
    "mesh_assets",
    "joint_limits",
    "target_frame",
    "tcp_offset",
    "base_to_board_alignment",
)
EXPECTED_RELATIVE_PATHS = (
    "README.md",
    "joints_properties.xml",
    "scene.xml",
    "so101_new_calib.urdf",
    "so101_new_calib.xml",
    "so101_old_calib.urdf",
    "so101_old_calib.xml",
    "assets/base_motor_holder_so101_v1.stl",
    "assets/base_so101_v2.stl",
    "assets/moving_jaw_so101_v1.stl",
    "assets/motor_holder_so101_base_v1.stl",
    "assets/motor_holder_so101_wrist_v1.stl",
    "assets/rotation_pitch_so101_v1.stl",
    "assets/sts3215_03a_no_horn_v1.stl",
    "assets/sts3215_03a_v1.stl",
    "assets/under_arm_so101_v1.stl",
    "assets/upper_arm_so101_v1.stl",
    "assets/waveshare_mounting_plate_so101_v2.stl",
    "assets/wrist_roll_follower_so101_v1.stl",
    "assets/wrist_roll_pitch_so101_v2.stl",
)
LOCKABLE_SUFFIXES = {".md", ".part", ".stl", ".urdf", ".xml"}
MODEL_RELATIVE_PATHS = (
    "scene.xml",
    "so101_new_calib.urdf",
    "so101_new_calib.xml",
    "so101_old_calib.urdf",
    "so101_old_calib.xml",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a deterministic hardware-free intake/lock artifact for a local "
            "pinned SO-ARM100 Simulation/SO101 candidate checkout. This does not "
            "declare reviewed physical SO-101 authority."
        )
    )
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--upstream-repository-url", default=DEFAULT_REPOSITORY_URL)
    parser.add_argument("--upstream-source-tree-url", default=DEFAULT_SOURCE_TREE_URL)
    parser.add_argument("--upstream-commit", default=None)
    parser.add_argument("--model-relative-path", default=DEFAULT_MODEL_RELATIVE_PATH)
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def relative_path_for(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def discover_lock_files(source_root: Path) -> list[Path]:
    if not source_root.exists() or not source_root.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in LOCKABLE_SUFFIXES:
            continue
        paths.append(path)
    return paths


def build_file_rows(source_root: Path) -> list[dict[str, Any]]:
    expected = set(EXPECTED_RELATIVE_PATHS)
    rows: list[dict[str, Any]] = []
    discovered = {
        relative_path_for(path, source_root): path for path in discover_lock_files(source_root)
    }
    for relative_path in sorted(expected | set(discovered)):
        path = source_root / relative_path
        exists = path.is_file()
        rows.append(
            {
                "relative_path": relative_path,
                "path": str(path),
                "exists": exists,
                "expected": relative_path in expected,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size if exists else None,
                "sha256": sha256_file(path) if exists else None,
            }
        )
    return rows


def read_text_or_empty(path: Path, limit_bytes: int = 512_000) -> str:
    try:
        return path.read_text(errors="replace")[:limit_bytes]
    except OSError:
        return ""


def detect_readme_caveats(readme_text: str) -> dict[str, Any]:
    text = readme_text.lower()
    caveats = {
        "onshape_to_robot_generated": "onshape-to-robot" in text,
        "relative_mesh_paths_declared": "relative" in text and "mesh" in text,
        "base_collision_meshes_removed": "base collision" in text and "removed" in text,
        "gripper_linear_joint_mapping_not_reflected": (
            "linear" in text
            and "joint" in text
            and "mapping" in text
            and "not" in text
            and ("reflected" in text or "implemented" in text)
        ),
    }
    caveats["review_required"] = any(caveats.values())
    caveats["required_follow_up_scopes"] = [
        scope
        for scope, present in (
            ("provenance", caveats["onshape_to_robot_generated"]),
            ("mesh_assets", caveats["relative_mesh_paths_declared"]),
            ("collision_policy", caveats["base_collision_meshes_removed"]),
            ("gripper_mapping", caveats["gripper_linear_joint_mapping_not_reflected"]),
        )
        if present
    ]
    return caveats


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def xml_model_observation(path: Path, source_root: Path) -> dict[str, Any]:
    relative_path = relative_path_for(path, source_root)
    observation: dict[str, Any] = {
        "relative_path": relative_path,
        "path": str(path),
        "exists": path.is_file(),
        "parse_ok": False,
        "parse_error": None,
        "root_tag": None,
        "model_name": None,
        "joint_count": 0,
        "joint_names": [],
        "joint_limit_or_range_count": 0,
        "mesh_reference_count": 0,
        "mesh_references": [],
    }
    if not path.is_file():
        return observation
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        observation["parse_error"] = f"{type(exc).__name__}: {exc}"
        return observation

    root_tag = local_name(root.tag)
    observation["parse_ok"] = True
    observation["root_tag"] = root_tag
    observation["model_name"] = root.attrib.get("name") or root.attrib.get("model")

    joint_names: list[str] = []
    joint_limit_or_range_count = 0
    mesh_references: list[str] = []
    for element in root.iter():
        tag = local_name(element.tag)
        if tag == "joint":
            name = element.attrib.get("name")
            if name:
                joint_names.append(name)
            if element.attrib.get("range") or any(
                local_name(child.tag) == "limit" for child in list(element)
            ):
                joint_limit_or_range_count += 1
        if tag == "mesh":
            filename = (
                element.attrib.get("filename")
                or element.attrib.get("file")
                or element.attrib.get("name")
            )
            if filename:
                mesh_references.append(filename)
        if tag == "geom" and element.attrib.get("mesh"):
            mesh_references.append(str(element.attrib["mesh"]))

    observation["joint_count"] = len(joint_names)
    observation["joint_names"] = joint_names
    observation["joint_limit_or_range_count"] = joint_limit_or_range_count
    observation["mesh_reference_count"] = len(mesh_references)
    observation["mesh_references"] = mesh_references[:200]
    return observation


def build_candidate_review_observations(source_root: Path | None) -> dict[str, Any]:
    if source_root is None or not source_root.is_dir():
        return {
            "model_authority": "candidate_review_observations_not_authority",
            "observed_evidence_is_physical_so101_authority": False,
            "ready_for_model_backed_ik": False,
            "readme_present": False,
            "readme_caveats": {},
            "model_file_observations": [],
            "model_file_count": 0,
            "parsed_model_file_count": 0,
            "review_required_action_ids": [
                "supply_pinned_public_candidate_source_root",
            ],
        }

    readme_path = source_root / "README.md"
    readme_text = read_text_or_empty(readme_path)
    model_observations = [
        xml_model_observation(source_root / relative_path, source_root)
        for relative_path in MODEL_RELATIVE_PATHS
    ]
    parsed_count = sum(1 for item in model_observations if item.get("parse_ok") is True)
    readme_caveats = detect_readme_caveats(readme_text)
    review_required_action_ids = [
        "review_upstream_readme_caveats",
        "review_model_file_variants_and_select_authoritative_model",
        "review_gripper_linear_joint_mapping",
        "review_base_collision_mesh_policy",
        "review_joint_limits_against_physical_so101",
        "review_mesh_references_and_digests",
    ]
    return {
        "model_authority": "candidate_review_observations_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "readme_present": readme_path.is_file(),
        "readme_caveats": readme_caveats,
        "model_file_observations": model_observations,
        "model_file_count": len(model_observations),
        "parsed_model_file_count": parsed_count,
        "review_required_action_ids": review_required_action_ids,
        "limitations": [
            "XML/URDF parsing records review metadata only; it does not validate physical SO-101 correctness.",
            "Detected README caveats keep gripper mapping and collision policy as explicit review items.",
        ],
    }


def candidate_manifest_draft(
    *,
    source_root: Path | None,
    model_path: Path | None,
    model_sha256: str | None,
    upstream_repository_url: str,
    upstream_source_tree_url: str,
    upstream_commit: str | None,
) -> dict[str, Any]:
    return {
        "schema": "lerobot.sim.so101_public_candidate_manifest_draft.v1",
        "model_path": str(model_path) if model_path is not None else None,
        "model_sha256_observed": model_sha256,
        "asset_roots": [str(source_root)] if source_root is not None else [],
        "upstream": {
            "repository_url": upstream_repository_url,
            "source_tree_url": upstream_source_tree_url,
            "commit": upstream_commit,
        },
        "authority": {},
        "provenance": {},
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "ready_for_model_backed_ik": False,
        "observed_evidence_is_physical_so101_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "notes": [
            "This draft records observed intake data only; it is not a reviewed model bundle manifest.",
            "Copy model_sha256_observed into a reviewed bundle manifest only after model identity and source authority are reviewed.",
            "TCP offset, target-frame authority, joint-limit authority, mesh authority, and base-to-board alignment are intentionally not inferred here.",
        ],
    }


def candidate_seeded_review_manifest_template(
    *,
    source_root: Path | None,
    model_path: Path | None,
    model_sha256: str | None,
    upstream_repository_url: str,
    upstream_source_tree_url: str,
    upstream_commit: str | None,
    candidate_review_observations: dict[str, Any],
) -> dict[str, Any]:
    source_reference_parts = [
        upstream_source_tree_url,
        f"commit:{upstream_commit}" if upstream_commit else "commit:<pin-required>",
    ]
    return {
        "schema": "lerobot.sim.so101_public_candidate_seeded_review_manifest_template.v1",
        "ok": True,
        "status": "candidate_seeded_template_waiting_for_review",
        "model_authority": "candidate_seeded_review_manifest_template_not_authority",
        "ready_for_model_backed_ik": False,
        "physical_so101_model_authority_ready": False,
        "observed_evidence_is_physical_so101_authority": False,
        "physical_so101_truth_claimed": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "source_root": str(source_root) if source_root is not None else None,
        "observed_inputs": {
            "model_path": str(model_path) if model_path is not None else None,
            "model_sha256_observed": model_sha256,
            "asset_roots": [str(source_root)] if source_root is not None else [],
            "upstream": {
                "repository_url": upstream_repository_url,
                "source_tree_url": upstream_source_tree_url,
                "commit": upstream_commit,
            },
            "candidate_review_observations": candidate_review_observations,
        },
        "manifest_template": {
            "model_path": str(model_path) if model_path is not None else "<reviewed-so101-model.urdf-or-mjcf>",
            "model_sha256": "<copy-reviewed-sha256-after-review>",
            "asset_roots": [str(source_root)] if source_root is not None else ["<reviewed-mesh-or-asset-root>"],
            "authority": {
                "source_authority_status": "reviewed",
                "reviewed_by": "<reviewer-or-team>",
                "reviewed_at": "<review-date-YYYY-MM-DD>",
                "review_id": "<stable-review-ticket-commit-or-artifact-id>",
                "review_scopes": ["model_identity", "provenance", "license"],
            },
            "provenance": {
                "source_reference": " ".join(source_reference_parts),
                "export_tool": "<review-onshape-to-robot-version-and-any-manual-edits>",
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
        },
        "copy_rules": [
            "Do not copy model_sha256_observed into model_sha256 until the model identity and source authority review accepts that exact file.",
            "Do not treat candidate README caveats or parsed XML/URDF metadata as physical SO-101 truth.",
            "Replace every placeholder authority/provenance/TCP/base-board value before running the manifest checker as a reviewed bundle.",
        ],
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "next_required_action_ids": [
            "review_candidate_seeded_manifest_template",
            "replace_candidate_observations_with_reviewed_manifest_fields",
            "run_so101_model_bundle_manifest_checker",
            "require_physical_so101_model_authority_ready",
        ],
    }


def build_summary(args: argparse.Namespace, artifacts: dict[str, str]) -> dict[str, Any]:
    source_root = normalize_path(args.source_root) if args.source_root else None
    source_root_supplied = source_root is not None
    source_root_exists = bool(source_root and source_root.exists())
    source_root_is_dir = bool(source_root and source_root.is_dir())
    file_rows = build_file_rows(source_root) if source_root_is_dir and source_root else []
    missing_expected = [
        row["relative_path"]
        for row in file_rows
        if row.get("expected") is True and row.get("exists") is not True
    ]
    model_path = (
        source_root / args.model_relative_path
        if source_root is not None and args.model_relative_path
        else None
    )
    model_row = next(
        (
            row
            for row in file_rows
            if row.get("relative_path") == args.model_relative_path
        ),
        None,
    )
    model_present = bool(model_row and model_row.get("exists") is True)
    model_sha256 = str(model_row.get("sha256")) if model_present and model_row else None
    upstream_commit_supplied = bool(str(args.upstream_commit or "").strip())
    candidate_review_observations = build_candidate_review_observations(
        source_root if source_root_is_dir else None
    )
    seeded_review_manifest_template = candidate_seeded_review_manifest_template(
        source_root=source_root if source_root_is_dir else None,
        model_path=model_path if model_present else None,
        model_sha256=model_sha256,
        upstream_repository_url=args.upstream_repository_url,
        upstream_source_tree_url=args.upstream_source_tree_url,
        upstream_commit=args.upstream_commit,
        candidate_review_observations=candidate_review_observations,
    )

    if not source_root_supplied:
        status = "source_root_not_supplied"
    elif not source_root_exists:
        status = "source_root_unavailable"
    elif not source_root_is_dir:
        status = "source_root_not_directory"
    elif missing_expected or not model_present:
        status = "candidate_intake_incomplete"
    else:
        status = "candidate_intake_checked"

    next_required_action_ids = [
        "pin_upstream_soarm100_commit",
        "review_soarm100_license_and_provenance",
        "declare_single_authoritative_so101_model_path",
        "run_so101_model_bundle_probe",
        "author_review_model_digest_and_mesh_assets",
        "record_reviewed_tcp_and_base_to_board_alignment",
        "supply_reviewed_so101_model_bundle_manifest",
    ]
    if upstream_commit_supplied:
        next_required_action_ids = [
            action_id
            for action_id in next_required_action_ids
            if action_id != "pin_upstream_soarm100_commit"
        ]

    return {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "model_authority": "public_candidate_intake_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "network_skipped": True,
        "upstream": {
            "repository_url": args.upstream_repository_url,
            "source_tree_url": args.upstream_source_tree_url,
            "commit": args.upstream_commit,
            "commit_supplied": upstream_commit_supplied,
        },
        "source_root": str(source_root) if source_root else None,
        "source_root_supplied": source_root_supplied,
        "source_root_exists": source_root_exists,
        "source_root_is_dir": source_root_is_dir,
        "expected_relative_paths": list(EXPECTED_RELATIVE_PATHS),
        "expected_file_count": len(EXPECTED_RELATIVE_PATHS),
        "discovered_file_count": len(file_rows),
        "present_expected_file_count": sum(
            1 for row in file_rows if row.get("expected") and row.get("exists")
        ),
        "missing_expected_relative_paths": missing_expected,
        "model_relative_path": args.model_relative_path,
        "model_path": str(model_path) if model_path else None,
        "model_present": model_present,
        "model_sha256_observed": model_sha256,
        "candidate_manifest_draft": candidate_manifest_draft(
            source_root=source_root if source_root_is_dir else None,
            model_path=model_path if model_present else None,
            model_sha256=model_sha256,
            upstream_repository_url=args.upstream_repository_url,
            upstream_source_tree_url=args.upstream_source_tree_url,
            upstream_commit=args.upstream_commit,
        ),
        "candidate_review_observations_model_authority": candidate_review_observations[
            "model_authority"
        ],
        "candidate_review_observations": candidate_review_observations,
        "candidate_seeded_review_manifest_template_model_authority": (
            seeded_review_manifest_template["model_authority"]
        ),
        "candidate_seeded_review_manifest_template": seeded_review_manifest_template,
        "file_rows": file_rows,
        "review_required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "next_required_action_ids": next_required_action_ids,
        "artifacts": artifacts,
        "limitations": [
            "This smoke reads a local checkout only; it does not clone, fetch, or verify remote Git state.",
            "Observed file digests are lock evidence for review, not reviewed physical SO-101 authority.",
            "The gripper mapping, TCP offset, collision policy, and base-to-board alignment still require separate review.",
        ],
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Public Candidate Intake",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `model_authority`: `{summary['model_authority']}`",
        f"- `observed_evidence_is_physical_so101_authority`: `{str(summary['observed_evidence_is_physical_so101_authority']).lower()}`",
        f"- `ready_for_model_backed_ik`: `{str(summary['ready_for_model_backed_ik']).lower()}`",
        f"- `source_root`: `{summary.get('source_root') or 'none'}`",
        f"- `upstream_commit`: `{summary['upstream'].get('commit') or 'not supplied'}`",
        f"- `model_relative_path`: `{summary['model_relative_path']}`",
        f"- `model_sha256_observed`: `{summary.get('model_sha256_observed') or 'none'}`",
        f"- `candidate_review_observations_model_authority`: `{summary['candidate_review_observations_model_authority']}`",
        f"- `candidate_review_observations_ready_for_model_backed_ik`: `{str(summary['candidate_review_observations']['ready_for_model_backed_ik']).lower()}`",
        f"- `candidate_seeded_review_manifest_template_model_authority`: `{summary['candidate_seeded_review_manifest_template_model_authority']}`",
        f"- `parsed_model_file_count`: `{summary['candidate_review_observations']['parsed_model_file_count']}`",
        f"- `expected_file_count`: `{summary['expected_file_count']}`",
        f"- `present_expected_file_count`: `{summary['present_expected_file_count']}`",
        f"- `missing_expected_relative_paths`: `{', '.join(summary['missing_expected_relative_paths']) if summary['missing_expected_relative_paths'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `files_csv`: `{summary['artifacts']['files_csv']}`",
        f"- `candidate_manifest_draft_json`: `{summary['artifacts']['candidate_manifest_draft_json']}`",
        f"- `candidate_seeded_review_manifest_template_json`: `{summary['artifacts']['candidate_seeded_review_manifest_template_json']}`",
        "",
        "## Next Required Actions",
        "",
    ]
    for action_id in summary["next_required_action_ids"]:
        lines.append(f"- `{action_id}`")
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "This artifact is an intake lock for review. It does not declare reviewed physical SO-101 authority, model-backed IK readiness, or policy-training readiness.",
            "",
            "## Candidate Review Observations",
            "",
            "The `candidate_review_observations` section records README caveats and XML/URDF metadata for reviewer intake only. It is not reviewed physical SO-101 model authority.",
            "",
            "## Candidate-Seeded Reviewed Manifest Template",
            "",
            "The `candidate_seeded_review_manifest_template` artifact follows the reviewed bundle manifest shape but keeps placeholder authority fields and remains non-authoritative until a reviewer replaces observations with reviewed values and the manifest checker reports physical authority ready.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "so101_public_candidate_intake_summary.json"
    files_csv_path = output_dir / "so101_public_candidate_intake_files.csv"
    draft_path = output_dir / "so101_public_candidate_manifest_draft.json"
    seeded_template_path = (
        output_dir / "so101_public_candidate_seeded_review_manifest_template.json"
    )
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "files_csv": str(files_csv_path),
        "candidate_manifest_draft_json": str(draft_path),
        "candidate_seeded_review_manifest_template_json": str(seeded_template_path),
        "readme_md": str(readme_path),
    }
    summary = build_summary(args, artifacts)
    write_json(summary_path, summary)
    write_json(draft_path, summary["candidate_manifest_draft"])
    write_json(
        seeded_template_path,
        summary["candidate_seeded_review_manifest_template"],
    )
    write_csv(
        files_csv_path,
        summary["file_rows"],
        (
            "relative_path",
            "path",
            "exists",
            "expected",
            "suffix",
            "size_bytes",
            "sha256",
        ),
    )
    write_markdown(readme_path, summary)
    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "model_authority": summary["model_authority"],
                "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
                "source_root": summary["source_root"],
                "upstream_commit": summary["upstream"]["commit"],
                "model_relative_path": summary["model_relative_path"],
                "model_present": summary["model_present"],
                "model_sha256_observed": summary["model_sha256_observed"],
                "candidate_review_observations_model_authority": summary[
                    "candidate_review_observations_model_authority"
                ],
                "candidate_seeded_review_manifest_template_model_authority": summary[
                    "candidate_seeded_review_manifest_template_model_authority"
                ],
                "candidate_review_observations_ready_for_model_backed_ik": summary[
                    "candidate_review_observations"
                ]["ready_for_model_backed_ik"],
                "candidate_seeded_review_manifest_template_ready_for_model_backed_ik": summary[
                    "candidate_seeded_review_manifest_template"
                ]["ready_for_model_backed_ik"],
                "candidate_review_observations_parsed_model_file_count": summary[
                    "candidate_review_observations"
                ]["parsed_model_file_count"],
                "expected_file_count": summary["expected_file_count"],
                "present_expected_file_count": summary["present_expected_file_count"],
                "missing_expected_relative_paths": summary[
                    "missing_expected_relative_paths"
                ],
                "next_required_action_ids": summary["next_required_action_ids"],
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
