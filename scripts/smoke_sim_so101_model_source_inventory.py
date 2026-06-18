#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lerobot.sim.so101_model_source_inventory.v1"
REVIEW_PACKET_SCHEMA = "lerobot.sim.so101_model_source_inventory_review_packet.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_source_inventory"
SUPPORTED_SUFFIXES = {".urdf", ".xacro", ".xml", ".mjcf"}
DIRECT_ROBOT_KINEMATICS_SUFFIXES = {".urdf"}
EXPECTED_BODY_JOINTS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
)
EXPECTED_TARGET_FRAME = "gripper_frame_link"
SO101_TERMS = ("so101", "so-101", "so_101", "so 101")
EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "htmlcov",
    "node_modules",
    "venv",
}
LICENSE_FILENAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.md",
    "NOTICE",
    "NOTICE.md",
)
CSV_FIELDNAMES = (
    "candidate_id",
    "source_root",
    "source_root_type",
    "relative_path",
    "path",
    "exists",
    "suffix",
    "model_format",
    "likely_so101_relevance",
    "relevance_score",
    "relevance_reasons",
    "contract_checker_suffix_supported",
    "direct_robot_kinematics_compatible",
    "provenance_status",
    "license_status",
    "source_authority_status",
    "source_authority_review_status",
    "authoritative",
    "diagnostics",
)
REVIEW_PACKET_FIELDNAMES = (
    "item_id",
    "item_type",
    "status",
    "priority",
    "gate",
    "required_input",
    "candidate_id",
    "candidate_path",
    "candidate_relevance",
    "source_authority_status",
    "source_authority_review_status",
    "next_action_id",
    "evidence",
    "operator_action",
)
SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS = (
    "model_identity",
    "provenance",
    "license",
)
SOURCE_AUTHORITY_REVIEW_SCOPE_DESCRIPTIONS = {
    "model_identity": "Selected model path, digest, and SO-101 joint/frame identity were reviewed.",
    "provenance": "CAD/export source, toolchain, commit or source reference, and local edits were reviewed.",
    "license": "License or redistribution basis for using the model source in this repository was reviewed.",
}

SOURCE_INVENTORY_ACTIONS = {
    "scan_or_supply_so101_model_source_root": {
        "gate": "reviewed_model_authority",
        "title": "Scan or supply a local SO-101 model-source root",
        "detail": "Run the inventory with --root or --extra-root pointing at candidate SO-101 URDF/MJCF/Xacro sources.",
    },
    "review_and_declare_authoritative_so101_model_source": {
        "gate": "reviewed_model_authority",
        "title": "Review and declare the authoritative SO-101 model source",
        "detail": "After provenance, license, and source authority review, rerun with --authoritative-path or --authoritative-root.",
    },
    "record_source_authority_review_metadata": {
        "gate": "reviewed_model_authority",
        "title": "Record source-authority review metadata",
        "detail": (
            "Rerun with --authority-license-basis, all required --authority-review-scope values, "
            "and at least one of --authority-reviewed-by, --authority-reviewed-at, "
            "--authority-review-id, or --authority-review-url."
        ),
    },
    "run_so101_model_bundle_probe": {
        "gate": "reviewed_model_authority",
        "title": "Generate a reviewed-bundle manifest draft",
        "detail": "Run smoke_sim_so101_model_bundle_probe.py with the selected model path and mesh roots to produce review artifacts.",
    },
    "supply_reviewed_so101_model_bundle_manifest": {
        "gate": "reviewed_model_authority",
        "title": "Supply the reviewed SO-101 model bundle manifest",
        "detail": "Provide the manifest to smoke_sim_so101_model_bundle_manifest.py so readiness can be checked together with meshes, authority, TCP, and board alignment.",
    },
}


def source_inventory_next_required(
    *,
    candidate_count: int,
    likely_candidate_count: int,
    direct_contract_candidate_count: int,
    authoritative_candidate_count: int,
    source_authority_review_ready: bool,
    recommended_contract_check: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    action_ids: list[str] = []
    if candidate_count <= 0:
        action_ids.append("scan_or_supply_so101_model_source_root")
    if authoritative_candidate_count <= 0:
        action_ids.append("review_and_declare_authoritative_so101_model_source")
    elif not source_authority_review_ready:
        action_ids.append("record_source_authority_review_metadata")
    if recommended_contract_check:
        action_ids.append("run_so101_model_bundle_probe")
    elif direct_contract_candidate_count > 0 or likely_candidate_count > 0:
        action_ids.append("run_so101_model_bundle_probe")
    action_ids.append("supply_reviewed_so101_model_bundle_manifest")

    seen: set[str] = set()
    actions: list[dict[str, Any]] = []
    for action_id in action_ids:
        if action_id in seen:
            continue
        seen.add(action_id)
        template = SOURCE_INVENTORY_ACTIONS[action_id]
        actions.append(
            {
                "priority": len(actions) + 1,
                "action_id": action_id,
                **template,
            }
        )
    return actions


def action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [action["action_id"] for action in actions if action.get("action_id")]


def source_authority_gate_status(
    *,
    authoritative_candidate_count: int,
    source_authority_review_ready: bool,
) -> str:
    if authoritative_candidate_count <= 0:
        return "source_authority_blocked_missing_authoritative_model"
    if not source_authority_review_ready:
        return "source_authority_blocked_review_metadata"
    return "source_authority_ready"


def source_authority_blockers(
    *,
    candidate_count: int,
    authoritative_candidate_count: int,
    source_authority_review_ready: bool,
) -> list[str]:
    blockers: list[str] = []
    if candidate_count <= 0:
        blockers.append("scan_or_supply_so101_model_source_root")
    if authoritative_candidate_count <= 0:
        blockers.append("review_and_declare_authoritative_so101_model_source")
    elif not source_authority_review_ready:
        blockers.append("record_source_authority_review_metadata")
    return blockers


def source_inventory_review_packet_status(
    *,
    candidate_count: int,
    authoritative_candidate_count: int,
    source_authority_review_ready: bool,
) -> str:
    if candidate_count <= 0:
        return "review_packet_waiting_for_model_source_root"
    if authoritative_candidate_count <= 0:
        return "review_packet_source_candidates_need_authority_review"
    if not source_authority_review_ready:
        return "review_packet_source_authority_review_metadata_needed"
    return "review_packet_source_authority_ready"


def candidate_review_packet_status(candidate: dict[str, Any]) -> str:
    if not candidate.get("authoritative"):
        return "candidate_needs_source_authority_review"
    if candidate.get("source_authority_review_status") != "review_metadata_supplied":
        return "authoritative_candidate_needs_review_metadata"
    return "source_authority_review_metadata_supplied"


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


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def normalized_review_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def placeholder_review_evidence(value: Any) -> bool:
    if not non_empty(value) or not isinstance(value, str):
        return False
    normalized = normalized_review_text(value)
    return normalized in PLACEHOLDER_REVIEW_EVIDENCE_VALUES or any(
        normalized.startswith(prefix) for prefix in PLACEHOLDER_REVIEW_EVIDENCE_PREFIXES
    )


def normalized_review_scope_ids(values: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values or []:
        for raw_scope in str(value).split(","):
            scope = raw_scope.strip().lower().replace("-", "_")
            if not scope or scope in seen:
                continue
            seen.add(scope)
            normalized.append(scope)
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory local SO-101 kinematic model-source candidates without touching hardware. "
            "The script scans configurable roots for .urdf/.xacro/.xml/.mjcf files, records "
            "provenance/authority signals, and emits deterministic JSON and CSV artifacts."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        help=(
            "Root to scan instead of the default repo roots. Repeatable. A file path is allowed "
            "and is inspected only if it has a supported suffix."
        ),
    )
    parser.add_argument(
        "--extra-root",
        type=Path,
        action="append",
        default=[],
        help="Additional root to append to the default repo roots. Repeatable.",
    )
    parser.add_argument(
        "--authoritative-path",
        type=Path,
        action="append",
        default=[],
        help=(
            "Explicitly mark this candidate path as authoritative for this inventory run. "
            "Use only after provenance/license/source authority have been reviewed."
        ),
    )
    parser.add_argument(
        "--authoritative-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "Explicitly mark candidates below this root as authoritative for this inventory run. "
            "Use only for reviewed model-source locations."
        ),
    )
    parser.add_argument(
        "--sample-bytes",
        type=int,
        default=256_000,
        help="Maximum leading bytes to read from each candidate for lightweight inspection.",
    )
    parser.add_argument(
        "--authority-reviewed-by",
        default=None,
        help=(
            "Reviewer/operator identifier for an explicit authoritative source declaration. "
            "Recorded as evidence only; it does not copy or modify model assets."
        ),
    )
    parser.add_argument(
        "--authority-reviewed-at",
        default=None,
        help="Deterministic review date/string for an explicit authoritative source declaration.",
    )
    parser.add_argument(
        "--authority-review-id",
        default=None,
        help="Optional review ticket, issue, commit, or checklist identifier for source authority.",
    )
    parser.add_argument(
        "--authority-review-url",
        default=None,
        help="Optional URL to the reviewed source-authority record.",
    )
    parser.add_argument(
        "--authority-source-reference",
        default=None,
        help="Optional CAD/export/source reference used during source-authority review.",
    )
    parser.add_argument(
        "--authority-review-scope",
        action="append",
        choices=SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS,
        default=[],
        help=(
            "Required source-authority review scope. Repeat for every required scope: "
            f"{', '.join(SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS)}."
        ),
    )
    parser.add_argument(
        "--authority-license-basis",
        default=None,
        help="Reviewed license or redistribution basis for the authoritative model source.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def default_roots() -> list[Path]:
    return [
        REPO_ROOT / "models",
        REPO_ROOT / "assets",
        REPO_ROOT / "SO101",
        REPO_ROOT / "src",
        REPO_ROOT / "docs",
        REPO_ROOT / "archive",
        REPO_ROOT / "data",
        REPO_ROOT,
    ]


def root_type(root: Path, supplied_by: str) -> str:
    if supplied_by == "authoritative":
        return "explicit_authoritative_root"
    if root == REPO_ROOT:
        return "repo_root"
    if is_relative_to(root, REPO_ROOT):
        if root.name == "lerobot":
            return "repo_local_lerobot_package"
        return "repo_subroot"
    parts = {part.lower() for part in root.parts}
    lowered = str(root).lower()
    if "site-packages" in parts and "lerobot" in lowered:
        return "installed_lerobot_package"
    if "lerobot" in lowered:
        return "local_lerobot_related"
    return "user_supplied"


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


def tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def read_text_sample(path: Path, max_bytes: int) -> tuple[str, str | None]:
    try:
        data = path.read_bytes()[:max(0, max_bytes)]
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    return data.decode("utf-8", errors="replace"), None


def sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except Exception:
        return None
    return digest.hexdigest()


def iter_candidate_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_SUFFIXES else []
    candidates: list[Path] = []
    for current, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in EXCLUDED_DIR_NAMES and not (Path(current) / name).is_symlink()
        )
        for file_name in sorted(file_names):
            path = Path(current) / file_name
            if path.suffix.lower() in SUPPORTED_SUFFIXES:
                candidates.append(path)
    return candidates


def inspect_xml(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return {"status": "not_xml_model_suffix"}
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return {"status": "xml_parse_error", "reason": f"{type(exc).__name__}: {exc}"}

    links: set[str] = set()
    joints: set[str] = set()
    for node in root.iter():
        node_name = tag_name(node)
        name = node.attrib.get("name")
        if not name:
            continue
        if node_name == "link":
            links.add(name)
        elif node_name == "joint":
            joints.add(name)

    return {
        "status": "xml_inspected",
        "root_tag": tag_name(root),
        "root_name": root.attrib.get("name"),
        "link_count": len(links),
        "joint_count": len(joints),
        "link_names": sorted(links),
        "joint_names": sorted(joints),
        "expected_body_joints_present": sorted(set(EXPECTED_BODY_JOINTS) & joints),
        "expected_body_joints_missing": [joint for joint in EXPECTED_BODY_JOINTS if joint not in joints],
        "target_frame_present": EXPECTED_TARGET_FRAME in links or EXPECTED_TARGET_FRAME in joints,
    }


def infer_model_format(path: Path, xml_info: dict[str, Any]) -> str:
    suffix = path.suffix.lower()
    if suffix == ".urdf":
        return "urdf"
    if suffix == ".xacro":
        return "xacro"
    if suffix == ".mjcf":
        return "mjcf"
    if suffix == ".xml":
        root_tag = xml_info.get("root_tag")
        if root_tag == "robot":
            return "urdf_xml"
        if root_tag == "mujoco":
            return "mujoco_xml"
        return "xml"
    return "unknown"


def relevance_for(path: Path, sample_text: str, xml_info: dict[str, Any]) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    path_lower = str(path).lower()
    sample_lower = sample_text.lower()
    root_name = str(xml_info.get("root_name") or "").lower()

    if any(term in path_lower for term in SO101_TERMS):
        score += 35
        reasons.append("path_or_filename_mentions_so101")
    if any(term in sample_lower[:20_000] for term in SO101_TERMS):
        score += 25
        reasons.append("file_header_or_sample_mentions_so101")
    if any(term in root_name for term in SO101_TERMS):
        score += 35
        reasons.append("xml_robot_name_mentions_so101")
    if xml_info.get("root_tag") in {"robot", "mujoco"}:
        score += 10
        reasons.append(f"xml_root_tag_{xml_info['root_tag']}")

    present_joints = xml_info.get("expected_body_joints_present") or []
    if present_joints:
        score += 8 * len(present_joints)
        reasons.append(f"expected_body_joint_names_present:{len(present_joints)}")
    if len(present_joints) == len(EXPECTED_BODY_JOINTS):
        score += 20
        reasons.append("all_expected_body_joint_names_present")
    if xml_info.get("target_frame_present"):
        score += 15
        reasons.append(f"target_frame_present:{EXPECTED_TARGET_FRAME}")

    if score >= 85:
        label = "high"
    elif score >= 45:
        label = "medium"
    elif score > 0:
        label = "low"
    else:
        label = "none"
    return label, score, reasons


def nearest_license(path: Path, source_root: Path) -> dict[str, Any]:
    current = path.parent if path.is_file() else path
    root = source_root if source_root.exists() else current
    checked = 0
    while True:
        checked += 1
        for file_name in LICENSE_FILENAMES:
            candidate = current / file_name
            if candidate.exists() and candidate.is_file():
                return {
                    "status": "license_file_detected",
                    "path": str(candidate),
                    "checked_parent_count": checked,
                }
        if current == root or current.parent == current or checked >= 12:
            break
        if not is_relative_to(current.parent, root) and current.parent != root:
            break
        current = current.parent
    return {"status": "unknown", "path": None, "checked_parent_count": checked}


def provenance_for(path: Path, sample_text: str, source_root: Path) -> dict[str, Any]:
    evidence: list[str] = []
    lowered = sample_text.lower()
    license_info = nearest_license(path, source_root)
    spdx_match = re.search(r"SPDX-License-Identifier:\s*([A-Za-z0-9_.+\-]+)", sample_text)
    onshape_urls = sorted(set(re.findall(r"https://cad\.onshape\.com/[^\s\"'<>]+", sample_text)))

    if "onshape-to-robot" in lowered:
        evidence.append("onshape-to-robot_header")
    if onshape_urls:
        evidence.append("onshape_cad_url")
    if spdx_match:
        evidence.append(f"spdx:{spdx_match.group(1)}")
    if license_info["status"] == "license_file_detected":
        evidence.append("nearest_license_file")

    if onshape_urls or "onshape-to-robot" in lowered:
        provenance_status = "source_reference_detected"
    elif spdx_match or license_info["status"] == "license_file_detected":
        provenance_status = "license_context_detected"
    else:
        provenance_status = "unknown"

    return {
        "provenance_status": provenance_status,
        "evidence": evidence,
        "onshape_urls": onshape_urls,
        "spdx_license_identifier": spdx_match.group(1) if spdx_match else None,
        "license": license_info,
    }


def is_authoritative(
    path: Path,
    authoritative_paths: set[Path],
    authoritative_roots: set[Path],
) -> tuple[bool, str, list[str]]:
    normalized = normalize_path(path)
    if normalized in authoritative_paths:
        return True, "explicit_authoritative_path", ["path_supplied_by_cli"]
    for root in authoritative_roots:
        if normalized == root or is_relative_to(normalized, root):
            return True, "explicit_authoritative_root", [f"root_supplied_by_cli:{root}"]
    return False, "unverified", []


def source_authority_review_input(args: argparse.Namespace) -> dict[str, Any]:
    review_evidence = {
        "authority_reviewed_by": args.authority_reviewed_by,
        "authority_reviewed_at": args.authority_reviewed_at,
        "authority_review_id": args.authority_review_id,
        "authority_review_url": args.authority_review_url,
    }
    other_optional = {
        "authority_source_reference": args.authority_source_reference,
    }
    supplied_review_evidence = {key: value for key, value in review_evidence.items() if non_empty(value)}
    placeholder_review_fields = sorted(
        key for key, value in supplied_review_evidence.items() if placeholder_review_evidence(value)
    )
    valid_review_evidence = {
        key: value
        for key, value in supplied_review_evidence.items()
        if key not in placeholder_review_fields
    }
    supplied_optional = {key: value for key, value in other_optional.items() if value}
    if args.authority_license_basis:
        supplied_optional["authority_license_basis"] = args.authority_license_basis
    supplied_review_scope_ids = normalized_review_scope_ids(args.authority_review_scope)
    missing_review_scope_ids = [
        scope
        for scope in SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS
        if scope not in supplied_review_scope_ids
    ]
    missing_required = []
    diagnostics = [f"authority_review_evidence_placeholder:{field}" for field in placeholder_review_fields]
    if not valid_review_evidence:
        missing_required.append("authority_review_evidence")
    missing_required.extend(
        f"authority_review_scope:{scope}" for scope in missing_review_scope_ids
    )
    if not args.authority_license_basis:
        missing_required.append("authority_license_basis")
    return {
        "required_fields": [
            "authority_review_evidence",
            *[
                f"authority_review_scope:{scope}"
                for scope in SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS
            ],
            "authority_license_basis",
        ],
        "required_review_scope_ids": list(SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
        "supplied_review_scope_ids": supplied_review_scope_ids,
        "missing_review_scope_ids": missing_review_scope_ids,
        "review_scope_descriptions": SOURCE_AUTHORITY_REVIEW_SCOPE_DESCRIPTIONS,
        "review_scope_ready": not missing_review_scope_ids,
        "review_evidence_fields": sorted(review_evidence),
        "review_evidence_valid_fields": sorted(valid_review_evidence),
        "review_evidence_placeholder_fields": placeholder_review_fields,
        "diagnostics": diagnostics,
        "optional_fields": sorted(other_optional),
        "missing_required_fields": missing_required,
        "supplied_required_fields": valid_review_evidence,
        "supplied_review_evidence_fields": supplied_review_evidence,
        "supplied_optional_fields": supplied_optional,
        "ready_if_authoritative_source_declared": not missing_required and not placeholder_review_fields,
        "notes": [
            "This metadata describes the inventory-level source-authority review declaration only.",
            "Placeholder review evidence such as TODO/TBD/unknown does not satisfy source-authority readiness.",
            "Source-authority readiness also requires explicit review scopes for model identity, provenance, and license.",
            "The bundle manifest still must declare reviewed provenance, mesh authority, joint limits, target frame, TCP offset, and base-to-board alignment before model-backed IK is trusted.",
        ],
    }


def source_authority_review_status_for_candidate(
    authoritative: bool,
    review_input: dict[str, Any],
) -> str:
    if not authoritative:
        return "not_applicable"
    if review_input.get("ready_if_authoritative_source_declared") is True:
        return "review_metadata_supplied"
    return "review_metadata_missing"


def source_authority_review_summary(
    *,
    authoritative_candidate_count: int,
    review_input: dict[str, Any],
) -> dict[str, Any]:
    if authoritative_candidate_count <= 0:
        status = "not_applicable_no_authoritative_candidate"
        ready = False
    elif review_input.get("ready_if_authoritative_source_declared") is True:
        status = "review_metadata_supplied"
        ready = True
    else:
        status = "review_metadata_missing"
        ready = False
    return {
        "status": status,
        "ready": ready,
        "authoritative_candidate_count": authoritative_candidate_count,
        "required_fields": review_input.get("required_fields", []),
        "optional_fields": review_input.get("optional_fields", []),
        "missing_required_fields": review_input.get("missing_required_fields", []),
        "required_review_scope_ids": review_input.get("required_review_scope_ids", []),
        "supplied_review_scope_ids": review_input.get("supplied_review_scope_ids", []),
        "missing_review_scope_ids": review_input.get("missing_review_scope_ids", []),
        "review_scope_descriptions": review_input.get("review_scope_descriptions", {}),
        "review_scope_ready": review_input.get("review_scope_ready", False),
        "diagnostics": review_input.get("diagnostics", []),
        "review_evidence_valid_fields": review_input.get("review_evidence_valid_fields", []),
        "review_evidence_placeholder_fields": review_input.get("review_evidence_placeholder_fields", []),
        "supplied_required_fields": review_input.get("supplied_required_fields", {}),
        "supplied_review_evidence_fields": review_input.get("supplied_review_evidence_fields", {}),
        "supplied_optional_fields": review_input.get("supplied_optional_fields", {}),
        "notes": review_input.get("notes", []),
    }


def candidate_id_for(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    return f"candidate_{digest}"


def build_candidate(
    path: Path,
    source_root: Path,
    source_root_type: str,
    sample_bytes: int,
    authoritative_paths: set[Path],
    authoritative_roots: set[Path],
    authority_review_input: dict[str, Any],
) -> dict[str, Any]:
    path = normalize_path(path)
    exists = path.exists()
    suffix = path.suffix.lower()
    diagnostics: list[str] = []
    sample_text = ""
    read_error: str | None = None
    xml_info: dict[str, Any] = {"status": "not_inspected"}

    if exists:
        sample_text, read_error = read_text_sample(path, sample_bytes)
        if read_error:
            diagnostics.append(f"sample_read_error:{read_error}")
        xml_info = inspect_xml(path)
        if xml_info.get("status") == "xml_parse_error":
            diagnostics.append(f"xml_parse_error:{xml_info.get('reason')}")
    else:
        diagnostics.append("candidate_path_missing")

    model_format = infer_model_format(path, xml_info)
    relevance, relevance_score, relevance_reasons = relevance_for(path, sample_text, xml_info)
    provenance = provenance_for(path, sample_text, source_root) if exists else {
        "provenance_status": "unknown",
        "evidence": [],
        "onshape_urls": [],
        "spdx_license_identifier": None,
        "license": {"status": "unknown", "path": None},
    }
    authoritative, authority_status, authority_evidence = is_authoritative(
        path,
        authoritative_paths,
        authoritative_roots,
    )
    authority_review_status = source_authority_review_status_for_candidate(
        authoritative,
        authority_review_input,
    )
    contract_supported = suffix in SUPPORTED_SUFFIXES and exists
    direct_compatible = suffix in DIRECT_ROBOT_KINEMATICS_SUFFIXES and exists

    if relevance == "none":
        diagnostics.append("not_likely_so101")
    if not direct_compatible:
        diagnostics.append("not_direct_robot_kinematics_urdf")
    if not authoritative:
        diagnostics.append("source_authority_not_verified")
    elif authority_review_status != "review_metadata_supplied":
        diagnostics.append("source_authority_review_metadata_missing")
    if provenance["provenance_status"] == "unknown":
        diagnostics.append("provenance_unknown")
    if provenance["license"]["status"] == "unknown":
        diagnostics.append("license_unknown")

    try:
        relative_path = str(path.relative_to(source_root))
    except ValueError:
        relative_path = str(path)

    return {
        "candidate_id": candidate_id_for(path),
        "source_root": str(source_root),
        "source_root_type": source_root_type,
        "relative_path": relative_path,
        "path": str(path),
        "exists": exists,
        "suffix": suffix,
        "model_format": model_format,
        "file_sha256": sha256_file(path) if exists else None,
        "likely_so101_relevance": relevance,
        "relevance_score": relevance_score,
        "relevance_reasons": relevance_reasons,
        "contract_checker_suffix_supported": contract_supported,
        "direct_robot_kinematics_compatible": direct_compatible,
        "xml_inspection": xml_info,
        "provenance": provenance,
        "provenance_status": provenance["provenance_status"],
        "license_status": provenance["license"]["status"],
        "source_authority_status": authority_status,
        "source_authority_review_status": authority_review_status,
        "source_authority_evidence": authority_evidence,
        "authoritative": authoritative,
        "diagnostics": diagnostics,
    }


def missing_source_requirements() -> list[dict[str, str]]:
    return [
        {
            "input": "authoritative_model_asset",
            "requirement": (
                "A repo-local or explicitly declared SO-101 URDF/MJCF/Xacro source with stable provenance, "
                "license, and source authority."
            ),
        },
        {
            "input": "model_generation_provenance",
            "requirement": "CAD/export source URL or commit, export tool/version, and any local edits from that source.",
        },
        {
            "input": "license_and_redistribution_basis",
            "requirement": "Clear license file or SPDX/header evidence that permits use in this repository.",
        },
        {
            "input": "joint_and_frame_alignment",
            "requirement": (
                "Confirmation that model joints match shoulder_pan through wrist_roll and target frame "
                f"{EXPECTED_TARGET_FRAME} matches simulator expectations."
            ),
        },
        {
            "input": "tcp_and_board_alignment",
            "requirement": "Calibrated gripper-frame/TCP offset plus base-to-board alignment for chess residuals.",
        },
        {
            "input": "contract_checker_result",
            "requirement": (
                "Run scripts/smoke_sim_so101_model_contract.py --model-path <candidate> before forwarding "
                "the same path through --ik-model-path."
            ),
        },
    ]


def build_root_records(roots: list[Path], root_source: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for root in roots:
        records.append(
            {
                "path": str(root),
                "exists": root.exists(),
                "is_file": root.is_file(),
                "source_root_type": root_type(root, root_source),
                "candidate_count": 0,
            }
        )
    return records


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        not candidate["authoritative"],
        -int(candidate["direct_robot_kinematics_compatible"]),
        -int(candidate["relevance_score"]),
        candidate["suffix"],
        candidate["path"],
    )


def build_source_inventory_review_packet(summary: dict[str, Any]) -> dict[str, Any]:
    next_required_for_goal = summary.get("next_required_for_goal") or []
    candidates = summary.get("candidates") or []
    packet_status = source_inventory_review_packet_status(
        candidate_count=int(summary.get("candidate_count") or 0),
        authoritative_candidate_count=int(summary.get("authoritative_candidate_count") or 0),
        source_authority_review_ready=summary.get("source_authority_review_ready") is True,
    )
    items: list[dict[str, Any]] = []

    def append_item(**item: Any) -> None:
        items.append({"priority": len(items) + 1, **item})

    if not candidates:
        append_item(
            item_id="source_inventory:no_candidate_found",
            item_type="missing_source_candidate",
            status="needs_operator_input",
            gate="reviewed_model_authority",
            required_input="authoritative_model_asset",
            candidate_id=None,
            candidate_path=None,
            candidate_relevance=None,
            source_authority_status="missing",
            source_authority_review_status=summary.get("source_authority_review_status"),
            next_action_id="scan_or_supply_so101_model_source_root",
            evidence={
                "root_count": summary.get("root_count"),
                "candidate_count": summary.get("candidate_count"),
            },
            operator_action="Run the inventory with a local SO-101 model-source root or supply an authoritative model path/root.",
        )

    for requirement in missing_source_requirements():
        append_item(
            item_id=f"source_requirement:{requirement['input']}",
            item_type="source_requirement",
            status=(
                "needs_reviewed_bundle_manifest"
                if summary.get("source_authority_review_ready") is True
                else "needs_operator_review"
            ),
            gate="reviewed_model_authority",
            required_input=requirement["input"],
            candidate_id=None,
            candidate_path=None,
            candidate_relevance=None,
            source_authority_status=summary.get("source_authority_gate_status"),
            source_authority_review_status=summary.get("source_authority_review_status"),
            next_action_id=None,
            evidence={"requirement": requirement["requirement"]},
            operator_action=requirement["requirement"],
        )

    source_authority_review = summary.get("source_authority_review")
    source_authority_review = (
        source_authority_review if isinstance(source_authority_review, dict) else {}
    )
    supplied_review_scope_ids = set(
        source_authority_review.get("supplied_review_scope_ids") or []
    )
    missing_review_scope_ids = set(
        source_authority_review.get("missing_review_scope_ids") or []
    )
    review_scope_descriptions = source_authority_review.get("review_scope_descriptions")
    review_scope_descriptions = (
        review_scope_descriptions if isinstance(review_scope_descriptions, dict) else {}
    )
    for scope_id in source_authority_review.get("required_review_scope_ids") or []:
        missing = scope_id in missing_review_scope_ids
        append_item(
            item_id=f"source_review_scope:{scope_id}",
            item_type="source_authority_review_scope",
            status="needs_operator_review" if missing else "scope_supplied",
            gate="reviewed_model_authority",
            required_input=f"authority_review_scope:{scope_id}",
            candidate_id=None,
            candidate_path=None,
            candidate_relevance=None,
            source_authority_status=summary.get("source_authority_gate_status"),
            source_authority_review_status=summary.get("source_authority_review_status"),
            next_action_id="record_source_authority_review_metadata" if missing else None,
            evidence={
                "scope_id": scope_id,
                "description": review_scope_descriptions.get(scope_id),
                "supplied": scope_id in supplied_review_scope_ids,
            },
            operator_action=(
                "Rerun with "
                f"--authority-review-scope {scope_id} after this source-authority review "
                "scope has been explicitly checked."
            ),
        )

    review_candidates = [
        candidate
        for candidate in sorted(candidates, key=candidate_sort_key)
        if candidate.get("authoritative")
        or candidate.get("likely_so101_relevance") in {"high", "medium"}
        or candidate.get("direct_robot_kinematics_compatible") is True
    ]
    for candidate in review_candidates[:20]:
        append_item(
            item_id=f"candidate:{candidate.get('candidate_id')}",
            item_type="candidate_source_evidence",
            status=candidate_review_packet_status(candidate),
            gate="reviewed_model_authority",
            required_input="authoritative_model_asset",
            candidate_id=candidate.get("candidate_id"),
            candidate_path=candidate.get("path"),
            candidate_relevance=candidate.get("likely_so101_relevance"),
            source_authority_status=candidate.get("source_authority_status"),
            source_authority_review_status=candidate.get("source_authority_review_status"),
            next_action_id=(
                "record_source_authority_review_metadata"
                if candidate.get("authoritative")
                and candidate.get("source_authority_review_status") != "review_metadata_supplied"
                else "review_and_declare_authoritative_so101_model_source"
                if not candidate.get("authoritative")
                else "run_so101_model_bundle_probe"
            ),
            evidence={
                "model_format": candidate.get("model_format"),
                "relevance_score": candidate.get("relevance_score"),
                "relevance_reasons": candidate.get("relevance_reasons"),
                "provenance_status": candidate.get("provenance_status"),
                "license_status": candidate.get("license_status"),
                "direct_robot_kinematics_compatible": candidate.get("direct_robot_kinematics_compatible"),
                "diagnostics": candidate.get("diagnostics"),
            },
            operator_action=(
                "Review provenance, license, source authority, mesh assets, frames, TCP offset, and board alignment before treating this candidate as physical SO-101 truth."
            ),
        )

    for action in next_required_for_goal:
        append_item(
            item_id=f"next_action:{action.get('action_id')}",
            item_type="next_required_action",
            status="pending",
            gate=action.get("gate"),
            required_input=None,
            candidate_id=None,
            candidate_path=None,
            candidate_relevance=None,
            source_authority_status=summary.get("source_authority_gate_status"),
            source_authority_review_status=summary.get("source_authority_review_status"),
            next_action_id=action.get("action_id"),
            evidence={
                "title": action.get("title"),
                "detail": action.get("detail"),
            },
            operator_action=action.get("detail"),
        )

    needs_operator_review_item_ids = [
        item["item_id"]
        for item in items
        if item.get("status")
        in {
            "needs_operator_input",
            "needs_operator_review",
            "needs_reviewed_bundle_manifest",
            "candidate_needs_source_authority_review",
            "authoritative_candidate_needs_review_metadata",
            "pending",
        }
    ]
    return {
        "schema": REVIEW_PACKET_SCHEMA,
        "ok": True,
        "status": packet_status,
        "model_authority": "review_packet_not_authority",
        "source_inventory_status": summary.get("status"),
        "source_authority_gate_status": summary.get("source_authority_gate_status"),
        "source_authority_review_status": summary.get("source_authority_review_status"),
        "source_authority_review_ready": summary.get("source_authority_review_ready"),
        "source_authority_blockers": summary.get("source_authority_blockers") or [],
        "candidate_count": summary.get("candidate_count"),
        "likely_candidate_count": summary.get("likely_candidate_count"),
        "direct_contract_candidate_count": summary.get("direct_contract_candidate_count"),
        "authoritative_candidate_count": summary.get("authoritative_candidate_count"),
        "review_candidate_item_count": len(review_candidates[:20]),
        "item_count": len(items),
        "item_ids": [item["item_id"] for item in items],
        "needs_operator_review_item_ids": needs_operator_review_item_ids,
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": summary.get("next_required_action_ids") or [],
        "recommended_contract_check": summary.get("recommended_contract_check"),
        "observed_evidence_is_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "physical_so101_model_authority_ready": False,
        "artifacts": summary.get("artifacts"),
        "items": items,
        "caveats": [
            "This packet organizes inventory findings for review; it is not reviewed physical SO-101 model authority.",
            "Observed source hints, filenames, joint names, and local license/provenance signals require operator review before forwarding to model-bundle readiness.",
            "A source-authority-ready inventory still requires a reviewed bundle manifest with mesh roots, joint limits, target frame, TCP offset, and base-to-board alignment.",
        ],
    }


def build_summary(
    roots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    artifacts: dict[str, str],
    source_authority_review_input: dict[str, Any],
) -> dict[str, Any]:
    authoritative_candidates = [candidate for candidate in candidates if candidate["authoritative"]]
    direct_candidates = [
        candidate
        for candidate in candidates
        if candidate["direct_robot_kinematics_compatible"] and candidate["likely_so101_relevance"] in {"high", "medium"}
    ]
    likely_candidates = [
        candidate for candidate in candidates if candidate["likely_so101_relevance"] in {"high", "medium"}
    ]
    best_candidate = sorted(candidates, key=candidate_sort_key)[0] if candidates else None
    status = "authoritative_model_found" if authoritative_candidates else "missing_authoritative_model"
    authority_review = source_authority_review_summary(
        authoritative_candidate_count=len(authoritative_candidates),
        review_input=source_authority_review_input,
    )
    diagnostics = []
    if not authoritative_candidates:
        diagnostics.append(
            {
                "diagnostic": "missing_authoritative_model",
                "severity": "action_required",
                "candidate_count": len(candidates),
                "likely_candidate_count": len(likely_candidates),
                "direct_contract_candidate_count": len(direct_candidates),
                "missing_source_requirements": missing_source_requirements(),
            }
        )
    elif not authority_review["ready"]:
        diagnostics.append(
            {
                "diagnostic": "source_authority_review_metadata_missing",
                "severity": "action_required",
                "authoritative_candidate_count": len(authoritative_candidates),
                "missing_required_fields": authority_review["missing_required_fields"],
                "reason": (
                    "An authoritative path/root was supplied, but inventory-level review metadata "
                    "is incomplete. This is still not reviewed physical SO-101 authority."
                ),
            }
        )

    recommended_contract_check = None
    if best_candidate and best_candidate["direct_robot_kinematics_compatible"]:
        recommended_contract_check = {
            "command": [
                sys.executable,
                "scripts/smoke_sim_so101_model_contract.py",
                "--model-path",
                best_candidate["path"],
                "--output-dir",
                str(DEFAULT_OUTPUT_DIR.parent / "so101_model_contract_inventory_candidate"),
            ],
            "candidate_id": best_candidate["candidate_id"],
            "candidate_path": best_candidate["path"],
            "authoritative": best_candidate["authoritative"],
        }

    next_required_for_goal = source_inventory_next_required(
        candidate_count=len(candidates),
        likely_candidate_count=len(likely_candidates),
        direct_contract_candidate_count=len(direct_candidates),
        authoritative_candidate_count=len(authoritative_candidates),
        source_authority_review_ready=authority_review["ready"],
        recommended_contract_check=recommended_contract_check,
    )
    source_blockers = source_authority_blockers(
        candidate_count=len(candidates),
        authoritative_candidate_count=len(authoritative_candidates),
        source_authority_review_ready=authority_review["ready"],
    )

    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "direct_robot_kinematics_suffixes": sorted(DIRECT_ROBOT_KINEMATICS_SUFFIXES),
        "expected_contract": {
            "body_joints": list(EXPECTED_BODY_JOINTS),
            "target_frame": EXPECTED_TARGET_FRAME,
        },
        "root_count": len(roots),
        "candidate_count": len(candidates),
        "likely_candidate_count": len(likely_candidates),
        "direct_contract_candidate_count": len(direct_candidates),
        "authoritative_candidate_count": len(authoritative_candidates),
        "source_authority_review_status": authority_review["status"],
        "source_authority_review_ready": authority_review["ready"],
        "source_authority_review": authority_review,
        "source_authority_review_scope_ready": authority_review["review_scope_ready"],
        "source_authority_required_review_scope_ids": authority_review[
            "required_review_scope_ids"
        ],
        "source_authority_supplied_review_scope_ids": authority_review[
            "supplied_review_scope_ids"
        ],
        "source_authority_missing_review_scope_ids": authority_review[
            "missing_review_scope_ids"
        ],
        "source_authority_gate_status": source_authority_gate_status(
            authoritative_candidate_count=len(authoritative_candidates),
            source_authority_review_ready=authority_review["ready"],
        ),
        "source_authority_blockers": source_blockers,
        "roots": roots,
        "candidates": candidates,
        "recommended_contract_check": recommended_contract_check,
        "next_required_for_goal": next_required_for_goal,
        "next_required_action_ids": action_ids(next_required_for_goal),
        "diagnostics": diagnostics,
        "artifacts": artifacts,
        "limitations": [
            "This inventory never opens hardware, cameras, serial ports, GUI flows, or network resources.",
            "The script does not copy model assets into the repository.",
            "SO-101 relevance is heuristic until provenance and source authority are reviewed.",
            "A candidate URDF being directly compatible with RobotKinematics does not prove TCP, board, or simulator-frame alignment.",
        ],
    }
    review_packet = build_source_inventory_review_packet(summary)
    summary.update(
        {
            "review_packet_status": review_packet["status"],
            "review_packet_model_authority": review_packet["model_authority"],
            "review_packet_item_count": review_packet["item_count"],
            "review_packet_item_ids": review_packet["item_ids"],
            "review_packet_needs_operator_review_item_ids": review_packet[
                "needs_operator_review_item_ids"
            ],
            "review_packet_action_ids": review_packet["next_required_action_ids"],
            "review_packet_observed_evidence_is_authority": review_packet[
                "observed_evidence_is_authority"
            ],
            "review_packet_development_fixture_evidence_not_physical_so101_truth": review_packet[
                "development_fixture_evidence_not_physical_so101_truth"
            ],
            "review_packet_physical_so101_model_authority_ready": review_packet[
                "physical_so101_model_authority_ready"
            ],
            "review_packet": review_packet,
        }
    )
    return summary


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def write_csv(path: Path, candidates: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({field: csv_value(candidate.get(field)) for field in CSV_FIELDNAMES})


def write_review_packet_csv(path: Path, review_packet: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_PACKET_FIELDNAMES)
        writer.writeheader()
        for item in review_packet.get("items") or []:
            writer.writerow({field: csv_value(item.get(field)) for field in REVIEW_PACKET_FIELDNAMES})


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SO-101 Model Source Inventory",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `candidate_count`: `{summary['candidate_count']}`",
        f"- `likely_candidate_count`: `{summary['likely_candidate_count']}`",
        f"- `direct_contract_candidate_count`: `{summary['direct_contract_candidate_count']}`",
        f"- `authoritative_candidate_count`: `{summary['authoritative_candidate_count']}`",
        f"- `source_authority_review_status`: `{summary['source_authority_review_status']}`",
        f"- `source_authority_review_ready`: `{str(summary['source_authority_review_ready']).lower()}`",
        f"- `source_authority_review_scope_ready`: `{str(summary['source_authority_review_scope_ready']).lower()}`",
        f"- `source_authority_required_review_scope_ids`: `{', '.join(summary.get('source_authority_required_review_scope_ids') or [])}`",
        f"- `source_authority_supplied_review_scope_ids`: `{', '.join(summary.get('source_authority_supplied_review_scope_ids') or []) if summary.get('source_authority_supplied_review_scope_ids') else 'none'}`",
        f"- `source_authority_missing_review_scope_ids`: `{', '.join(summary.get('source_authority_missing_review_scope_ids') or []) if summary.get('source_authority_missing_review_scope_ids') else 'none'}`",
        f"- `source_authority_gate_status`: `{summary['source_authority_gate_status']}`",
        f"- `source_authority_blockers`: `{', '.join(summary.get('source_authority_blockers') or []) if summary.get('source_authority_blockers') else 'none'}`",
        f"- `next_required_action_ids`: `{', '.join(summary.get('next_required_action_ids') or []) if summary.get('next_required_action_ids') else 'none'}`",
        f"- `review_packet_status`: `{summary['review_packet_status']}`",
        f"- `review_packet_model_authority`: `{summary['review_packet_model_authority']}`",
        f"- `review_packet_item_count`: `{summary['review_packet_item_count']}`",
        f"- `review_packet_observed_evidence_is_authority`: `{str(summary['review_packet_observed_evidence_is_authority']).lower()}`",
        f"- `review_packet_development_fixture_evidence_not_physical_so101_truth`: `{str(summary['review_packet_development_fixture_evidence_not_physical_so101_truth']).lower()}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `candidates_csv`: `{summary['artifacts']['candidates_csv']}`",
        f"- `review_packet_json`: `{summary['artifacts']['review_packet_json']}`",
        f"- `review_packet_csv`: `{summary['artifacts']['review_packet_csv']}`",
        "",
        "## Candidates",
        "",
        "| Candidate | Relevance | Direct URDF | Authority | Review Metadata | Provenance | Path |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not summary["candidates"]:
        lines.append("| none | none | false | missing | n/a | unknown | n/a |")
    else:
        for candidate in summary["candidates"]:
            lines.append(
                "| `{candidate_id}` | `{relevance}` | `{direct}` | `{authority}` | `{review}` | `{provenance}` | `{path}` |".format(
                    candidate_id=candidate["candidate_id"],
                    relevance=candidate["likely_so101_relevance"],
                    direct=str(candidate["direct_robot_kinematics_compatible"]).lower(),
                    authority=candidate["source_authority_status"],
                    review=candidate["source_authority_review_status"],
                    provenance=candidate["provenance_status"],
                    path=candidate["path"].replace("|", "/"),
                )
            )
    lines.extend(
        [
            "",
            "## Next Required For Goal",
            "",
        ]
    )
    if summary.get("next_required_for_goal"):
        for action in summary["next_required_for_goal"]:
            lines.append(
                "- `{priority}` `{action_id}`: {title}".format(
                    priority=action.get("priority"),
                    action_id=action.get("action_id"),
                    title=action.get("title"),
                )
            )
            lines.append(f"  - {action.get('detail')}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Review Packet",
            "",
            (
                "This packet organizes source-inventory findings for operator review. "
                "It is not reviewed physical SO-101 model authority."
            ),
            "",
            "| Item | Type | Status | Candidate | Next Action |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in summary["review_packet"].get("items") or []:
        lines.append(
            "| `{item_id}` | `{item_type}` | `{status}` | `{candidate}` | `{action}` |".format(
                item_id=item.get("item_id"),
                item_type=item.get("item_type"),
                status=item.get("status"),
                candidate=item.get("candidate_id") or "n/a",
                action=item.get("next_action_id") or "n/a",
            )
        )
    lines.extend(
        [
            "",
            "## Missing Authoritative Source Requirements",
            "",
        ]
    )
    for requirement in missing_source_requirements():
        lines.append(f"- `{requirement['input']}`: {requirement['requirement']}")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.root:
        roots = unique_paths(args.root)
        root_source = "user"
    else:
        roots = unique_paths(default_roots() + list(args.extra_root))
        root_source = "default"

    authoritative_paths = {normalize_path(path) for path in args.authoritative_path}
    authoritative_roots = {normalize_path(path) for path in args.authoritative_root}
    authority_review_input = source_authority_review_input(args)
    root_records = build_root_records(roots, root_source)

    candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for index, root in enumerate(roots):
        root_record = root_records[index]
        root_candidate_count = 0
        for candidate_path in iter_candidate_paths(root):
            normalized_candidate = normalize_path(candidate_path)
            key = str(normalized_candidate)
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            root_candidate_count += 1
            candidates.append(
                build_candidate(
                    normalized_candidate,
                    root,
                    root_record["source_root_type"],
                    args.sample_bytes,
                    authoritative_paths,
                    authoritative_roots,
                    authority_review_input,
                )
            )
        root_record["candidate_count"] = root_candidate_count

    candidates.sort(key=lambda candidate: candidate["path"])

    summary_path = output_dir / "so101_model_source_inventory_summary.json"
    csv_path = output_dir / "so101_model_source_candidates.csv"
    review_packet_path = output_dir / "so101_model_source_inventory_review_packet.json"
    review_packet_csv_path = output_dir / "so101_model_source_inventory_review_packet.csv"
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "candidates_csv": str(csv_path),
        "review_packet_json": str(review_packet_path),
        "review_packet_csv": str(review_packet_csv_path),
        "readme_md": str(readme_path),
    }
    summary = build_summary(root_records, candidates, artifacts, authority_review_input)

    write_json(summary_path, summary)
    write_json(review_packet_path, summary["review_packet"])
    write_csv(csv_path, candidates)
    write_review_packet_csv(review_packet_csv_path, summary["review_packet"])
    write_markdown(readme_path, summary)

    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "candidate_count": summary["candidate_count"],
                "likely_candidate_count": summary["likely_candidate_count"],
                "direct_contract_candidate_count": summary["direct_contract_candidate_count"],
                "authoritative_candidate_count": summary["authoritative_candidate_count"],
                "source_authority_review_status": summary["source_authority_review_status"],
                "source_authority_review_ready": summary["source_authority_review_ready"],
                "source_authority_review_scope_ready": summary[
                    "source_authority_review_scope_ready"
                ],
                "source_authority_missing_review_scope_ids": summary[
                    "source_authority_missing_review_scope_ids"
                ],
                "source_authority_gate_status": summary["source_authority_gate_status"],
                "source_authority_blockers": summary["source_authority_blockers"],
                "next_required_action_ids": summary["next_required_action_ids"],
                "review_packet_status": summary["review_packet_status"],
                "review_packet_model_authority": summary["review_packet_model_authority"],
                "review_packet_item_count": summary["review_packet_item_count"],
                "review_packet_action_ids": summary["review_packet_action_ids"],
                "review_packet_observed_evidence_is_authority": summary[
                    "review_packet_observed_evidence_is_authority"
                ],
                "review_packet_development_fixture_evidence_not_physical_so101_truth": summary[
                    "review_packet_development_fixture_evidence_not_physical_so101_truth"
                ],
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
