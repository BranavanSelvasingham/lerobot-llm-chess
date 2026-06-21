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
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lerobot.sim.so101_model_source_inventory.v1"
REVIEW_PACKET_SCHEMA = "lerobot.sim.so101_model_source_inventory_review_packet.v1"
SOURCE_INTAKE_SCHEMA = "lerobot.sim.so101_model_source_intake_checklist.v1"
SOURCE_REVIEW_REQUIREMENTS_SCHEMA = (
    "lerobot.sim.so101_model_source_review_requirements.v1"
)
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
    "review_evidence_invalid_fields",
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
SOURCE_INTAKE_FIELDNAMES = (
    "priority",
    "action_id",
    "status",
    "gate",
    "title",
    "detail",
    "recommended_candidate_path",
    "recommended_candidate_source_root",
    "recommended_candidate_authoritative",
    "command",
    "required_inputs",
)
SOURCE_REVIEW_REQUIREMENTS_FIELDNAMES = (
    "priority",
    "requirement_id",
    "status",
    "gate",
    "required_input",
    "supplied",
    "missing",
    "evidence_fields",
    "next_action_id",
    "operator_action",
)
SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS = (
    "model_identity",
    "provenance",
    "license",
)
SOURCE_AUTHORITY_REVIEW_EVIDENCE_REQUIRED_GROUPS = (
    ("review_actor", ("authority_reviewed_by",)),
    (
        "review_trace",
        ("authority_reviewed_at", "authority_review_id", "authority_review_url"),
    ),
    ("review_artifact", ("authority_review_id", "authority_review_url")),
)
SOURCE_AUTHORITY_REVIEW_SCOPE_DESCRIPTIONS = {
    "model_identity": "Selected model path, digest, and SO-101 joint/frame identity were reviewed.",
    "provenance": "CAD/export source, toolchain, commit or source reference, and local edits were reviewed.",
    "license": "License or redistribution basis for using the model source in this repository was reviewed.",
}

KNOWN_PUBLIC_SO101_CANDIDATE_SOURCES = (
    {
        "source_id": "therobotstudio_soarm100_simulation_so101",
        "name": "TheRobotStudio/SO-ARM100 Simulation/SO101",
        "repository_url": "https://github.com/TheRobotStudio/SO-ARM100",
        "simulation_overview_url": "https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation",
        "source_tree_url": "https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation/SO101",
        "source_path": "Simulation/SO101",
        "candidate_files": [
            "Simulation/SO101/so101_new_calib.urdf",
            "Simulation/SO101/so101_old_calib.urdf",
            "Simulation/SO101/so101_new_calib.xml",
            "Simulation/SO101/so101_old_calib.xml",
            "Simulation/SO101/scene.xml",
            "Simulation/SO101/joints_properties.xml",
            "Simulation/SO101/assets/",
        ],
        "source_notes": [
            "Public candidate upstream bundle only; fetch or vendor at a pinned commit before review.",
            "README says URDF and MJCF files were generated with onshape-to-robot and mesh paths were changed to relative paths.",
            "README says base collision meshes were removed due to collision issues.",
            "README says LeRobot gripper linear-joint mapping is not yet reflected in the current URDF/MuJoCo files.",
        ],
        "authority_boundary": (
            "This source is not reviewed physical SO-101 authority until a pinned commit, "
            "file digests, license/provenance review, joint/TCP/base-board review, and "
            "bundle-manifest validation are recorded."
        ),
        "operator_intake": {
            "pin_source": (
                "Resolve and record an immutable commit SHA before scanning or vendoring "
                "Simulation/SO101."
            ),
            "resolve_pin_command_template": [
                "git",
                "ls-remote",
                "https://github.com/TheRobotStudio/SO-ARM100.git",
                "refs/heads/main",
            ],
            "fetch_command_template": [
                "git",
                "-C",
                "<local-SO-ARM100-checkout>",
                "fetch",
                "--depth=1",
                "origin",
                "<immutable-upstream-commit-sha>",
            ],
            "checkout_command_template": [
                "git",
                "-C",
                "<local-SO-ARM100-checkout>",
                "checkout",
                "--detach",
                "<immutable-upstream-commit-sha>",
            ],
            "candidate_intake_command_template": [
                "python",
                "scripts/smoke_sim_so101_public_candidate_intake.py",
                "--source-root",
                "<local-SO-ARM100-checkout>/Simulation/SO101",
                "--upstream-commit",
                "<immutable-upstream-commit-sha>",
                "--operator-intake-decision",
                "external_pinned_source_root",
                "--output-dir",
                "/private/tmp/lerobot_sim/so101_public_candidate_intake_external",
            ],
            "scan_command_template": [
                "python",
                "scripts/smoke_sim_so101_model_source_inventory.py",
                "--root",
                "<local-SO-ARM100-checkout>/Simulation/SO101",
                "--output-dir",
                "/private/tmp/lerobot_sim/soarm100_so101_source_inventory_candidate",
            ],
            "vendor_lock_command_template": [
                "rsync",
                "-a",
                "--delete",
                "<local-SO-ARM100-checkout>/Simulation/SO101/",
                "<repo-vendored-SO101-asset-root>/",
            ],
            "probe_command_template": [
                "python",
                "scripts/smoke_sim_so101_model_bundle_probe.py",
                "--model-path",
                "<local-SO-ARM100-checkout>/Simulation/SO101/so101_new_calib.urdf",
                "--asset-root",
                "<local-SO-ARM100-checkout>/Simulation/SO101",
                "--output-dir",
                "/private/tmp/lerobot_sim/soarm100_so101_bundle_probe_candidate",
            ],
            "reviewed_source_inventory_command_template": [
                "python",
                "scripts/smoke_sim_so101_model_source_inventory.py",
                "--root",
                "<local-SO-ARM100-checkout>/Simulation/SO101",
                "--authoritative-path",
                "<local-SO-ARM100-checkout>/Simulation/SO101/so101_new_calib.urdf",
                "--authority-source-reference",
                "https://github.com/TheRobotStudio/SO-ARM100/tree/<immutable-upstream-commit-sha>/Simulation/SO101",
                "--authority-license-basis",
                "<reviewed-license-or-redistribution-basis>",
                "--authority-review-scope",
                "model_identity",
                "--authority-review-scope",
                "provenance",
                "--authority-review-scope",
                "license",
                "--authority-reviewed-by",
                "<reviewer-or-team>",
                "--authority-review-id",
                "<stable-source-authority-review-artifact>",
                "--output-dir",
                "/private/tmp/lerobot_sim/soarm100_so101_source_inventory_reviewed",
            ],
        },
    },
)

SOURCE_INVENTORY_ACTIONS = {
    "scan_or_supply_so101_model_source_root": {
        "gate": "reviewed_model_authority",
        "title": "Scan or supply a local SO-101 model-source root",
        "detail": (
            "Run the inventory with --root or --extra-root pointing at candidate "
            "SO-101 URDF/MJCF/Xacro sources. A known public candidate is "
            "TheRobotStudio/SO-ARM100 Simulation/SO101; fetch or vendor it at a "
            "pinned commit before scanning."
        ),
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
            "--authority-reviewed-by, and a stable review artifact handle: "
            "--authority-review-id or --authority-review-url."
        ),
    },
    "select_single_authoritative_so101_model_source": {
        "gate": "reviewed_model_authority",
        "title": "Select exactly one authoritative SO-101 model source",
        "detail": (
            "Rerun with --authoritative-path for the reviewed model file, or narrow "
            "--authoritative-root so it contains only the selected SO-101 model source."
        ),
    },
    "select_so101_relevant_authoritative_model_source": {
        "gate": "reviewed_model_authority",
        "title": "Select an SO-101-relevant authoritative model source",
        "detail": (
            "Rerun with --authoritative-path pointing at a reviewed model file whose "
            "filename, robot name, joints, or target frame match the SO-101 source contract."
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


def known_public_so101_candidate_sources() -> list[dict[str, Any]]:
    return [dict(source) for source in KNOWN_PUBLIC_SO101_CANDIDATE_SOURCES]


def source_inventory_next_required(
    *,
    candidate_count: int,
    likely_candidate_count: int,
    direct_contract_candidate_count: int,
    authoritative_candidate_count: int,
    selected_authoritative_candidate_so101_relevance_ready: bool,
    source_authority_review_ready: bool,
    recommended_contract_check: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    action_ids: list[str] = []
    if candidate_count <= 0:
        action_ids.append("scan_or_supply_so101_model_source_root")
    if authoritative_candidate_count <= 0:
        action_ids.append("review_and_declare_authoritative_so101_model_source")
    elif authoritative_candidate_count > 1:
        action_ids.append("select_single_authoritative_so101_model_source")
    elif not selected_authoritative_candidate_so101_relevance_ready:
        action_ids.append("select_so101_relevant_authoritative_model_source")
    elif not source_authority_review_ready:
        action_ids.append("record_source_authority_review_metadata")
    if authoritative_candidate_count <= 1 and (
        authoritative_candidate_count == 0
        or selected_authoritative_candidate_so101_relevance_ready
    ):
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
    selected_authoritative_candidate_so101_relevance_ready: bool,
    source_authority_review_ready: bool,
) -> str:
    if authoritative_candidate_count <= 0:
        return "source_authority_blocked_missing_authoritative_model"
    if authoritative_candidate_count > 1:
        return "source_authority_blocked_ambiguous_authoritative_model"
    if not selected_authoritative_candidate_so101_relevance_ready:
        return "source_authority_blocked_candidate_not_so101_relevant"
    if not source_authority_review_ready:
        return "source_authority_blocked_review_metadata"
    return "source_authority_ready"


def source_authority_blockers(
    *,
    candidate_count: int,
    authoritative_candidate_count: int,
    selected_authoritative_candidate_so101_relevance_ready: bool,
    source_authority_review_ready: bool,
) -> list[str]:
    blockers: list[str] = []
    if candidate_count <= 0:
        blockers.append("scan_or_supply_so101_model_source_root")
    if authoritative_candidate_count <= 0:
        blockers.append("review_and_declare_authoritative_so101_model_source")
    elif authoritative_candidate_count > 1:
        blockers.append("select_single_authoritative_so101_model_source")
    elif not selected_authoritative_candidate_so101_relevance_ready:
        blockers.append("select_so101_relevant_authoritative_model_source")
    elif not source_authority_review_ready:
        blockers.append("record_source_authority_review_metadata")
    return blockers


def source_inventory_review_packet_status(
    *,
    candidate_count: int,
    authoritative_candidate_count: int,
    selected_authoritative_candidate_so101_relevance_ready: bool,
    source_authority_review_ready: bool,
) -> str:
    if candidate_count <= 0:
        return "review_packet_waiting_for_model_source_root"
    if authoritative_candidate_count <= 0:
        return "review_packet_source_candidates_need_authority_review"
    if authoritative_candidate_count > 1:
        return "review_packet_multiple_authoritative_candidates_need_selection"
    if not selected_authoritative_candidate_so101_relevance_ready:
        return "review_packet_authoritative_candidate_not_so101_relevant"
    if not source_authority_review_ready:
        return "review_packet_source_authority_review_metadata_needed"
    return "review_packet_source_authority_ready"


def authoritative_source_selection_status(authoritative_candidate_count: int) -> str:
    if authoritative_candidate_count <= 0:
        return "missing_authoritative_model"
    if authoritative_candidate_count > 1:
        return "multiple_authoritative_candidates"
    return "single_authoritative_candidate"


def candidate_review_packet_status(candidate: dict[str, Any]) -> str:
    if not candidate.get("authoritative"):
        return "candidate_needs_source_authority_review"
    if candidate.get("likely_so101_relevance") not in {"high", "medium"}:
        return "authoritative_candidate_not_so101_relevant"
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
    if field_name == "authority_reviewed_at":
        return invalid_reviewed_at(value)
    if field_name != "authority_review_url":
        return False
    return invalid_review_url(value)


def review_evidence_group_summary(valid_review_fields: set[str]) -> dict[str, Any]:
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
        help=(
            "Deterministic review date/string for an explicit authoritative source declaration. "
            "A date alone is not enough; also provide --authority-review-id or --authority-review-url."
        ),
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


def relevance_for(
    path: Path,
    sample_text: str,
    xml_info: dict[str, Any],
    source_root: Path | None = None,
) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    try:
        path_for_relevance = (
            str(path.relative_to(source_root)) if source_root is not None else path.name
        )
    except ValueError:
        path_for_relevance = path.name
    path_lower = path_for_relevance.lower()
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
    required_metadata = {
        "authority_source_reference": args.authority_source_reference,
        "authority_license_basis": args.authority_license_basis,
    }
    supplied_review_evidence = {key: value for key, value in review_evidence.items() if non_empty(value)}
    placeholder_review_fields = sorted(
        key for key, value in supplied_review_evidence.items() if placeholder_review_evidence(value)
    )
    invalid_review_fields = sorted(
        key
        for key, value in supplied_review_evidence.items()
        if key not in placeholder_review_fields and invalid_review_evidence(key, value)
    )
    valid_review_evidence = {
        key: value
        for key, value in supplied_review_evidence.items()
        if key not in placeholder_review_fields and key not in invalid_review_fields
    }
    review_evidence_groups = review_evidence_group_summary(set(valid_review_evidence))
    supplied_required_metadata = {
        key: value for key, value in required_metadata.items() if non_empty(value)
    }
    required_metadata_placeholder_fields = sorted(
        key
        for key, value in supplied_required_metadata.items()
        if placeholder_review_evidence(value)
    )
    valid_required_metadata = {
        key: value
        for key, value in supplied_required_metadata.items()
        if key not in required_metadata_placeholder_fields
    }
    supplied_review_scope_ids = normalized_review_scope_ids(args.authority_review_scope)
    missing_review_scope_ids = [
        scope
        for scope in SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS
        if scope not in supplied_review_scope_ids
    ]
    missing_required = []
    diagnostics = [f"authority_review_evidence_placeholder:{field}" for field in placeholder_review_fields]
    diagnostics.extend(
        f"authority_review_evidence_invalid:{field}" for field in invalid_review_fields
    )
    diagnostics.extend(
        f"authority_required_metadata_placeholder:{field}"
        for field in required_metadata_placeholder_fields
    )
    diagnostics.extend(
        f"authority_review_evidence_missing_required_group:{group}"
        for group in review_evidence_groups["missing_required_groups"]
    )
    if not valid_review_evidence:
        missing_required.append("authority_review_evidence")
    else:
        missing_required.extend(
            f"authority_review_evidence:{group}"
            for group in review_evidence_groups["missing_required_groups"]
        )
    missing_required.extend(
        f"authority_review_scope:{scope}" for scope in missing_review_scope_ids
    )
    for field in required_metadata:
        if field not in valid_required_metadata:
            missing_required.append(field)
    return {
        "required_fields": [
            "authority_review_evidence",
            *[
                f"authority_review_scope:{scope}"
                for scope in SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS
            ],
            "authority_source_reference",
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
        "review_evidence_invalid_fields": invalid_review_fields,
        "review_evidence_required_groups": review_evidence_groups["required_groups"],
        "review_evidence_satisfied_required_groups": review_evidence_groups[
            "satisfied_required_groups"
        ],
        "review_evidence_missing_required_groups": review_evidence_groups[
            "missing_required_groups"
        ],
        "required_metadata_fields": sorted(required_metadata),
        "required_metadata_valid_fields": sorted(valid_required_metadata),
        "required_metadata_placeholder_fields": required_metadata_placeholder_fields,
        "diagnostics": diagnostics,
        "missing_required_fields": missing_required,
        "supplied_required_fields": valid_review_evidence,
        "supplied_review_evidence_fields": supplied_review_evidence,
        "supplied_required_metadata_fields": valid_required_metadata,
        "ready_if_authoritative_source_declared": (
            not missing_required
            and not placeholder_review_fields
            and not invalid_review_fields
            and not required_metadata_placeholder_fields
        ),
        "notes": [
            "This metadata describes the inventory-level source-authority review declaration only.",
            "Placeholder review evidence, source references, or license bases such as TODO/TBD/unknown or unedited <...> template tokens do not satisfy source-authority readiness.",
            "If authority_reviewed_at is supplied, it must be an ISO YYYY-MM-DD date or ISO datetime and must not be in the future.",
            "Source-authority review evidence requires reviewer identity plus a stable review artifact handle: authority_review_id or authority_review_url.",
            "Source-authority readiness also requires explicit review scopes for model identity, provenance, and license, plus a non-placeholder source reference and license basis.",
            "The bundle manifest still must declare reviewed provenance, mesh authority, joint limits, gripper mapping, collision policy, target frame, TCP offset, and base-to-board alignment before model-backed IK is trusted.",
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
        "review_evidence_invalid_fields": review_input.get("review_evidence_invalid_fields", []),
        "required_metadata_fields": review_input.get("required_metadata_fields", []),
        "required_metadata_valid_fields": review_input.get("required_metadata_valid_fields", []),
        "required_metadata_placeholder_fields": review_input.get("required_metadata_placeholder_fields", []),
        "review_evidence_required_groups": review_input.get("review_evidence_required_groups", []),
        "review_evidence_satisfied_required_groups": review_input.get(
            "review_evidence_satisfied_required_groups", []
        ),
        "review_evidence_missing_required_groups": review_input.get(
            "review_evidence_missing_required_groups", []
        ),
        "supplied_required_fields": review_input.get("supplied_required_fields", {}),
        "supplied_review_evidence_fields": review_input.get("supplied_review_evidence_fields", {}),
        "supplied_required_metadata_fields": review_input.get("supplied_required_metadata_fields", {}),
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
    relevance, relevance_score, relevance_reasons = relevance_for(
        path, sample_text, xml_info, source_root
    )
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
        "review_evidence_invalid_fields": authority_review_input.get(
            "review_evidence_invalid_fields", []
        ),
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
    relative_path = str(candidate.get("relative_path") or candidate.get("path") or "")
    relative_parts = Path(relative_path).parts
    archived_path_penalty = int(any(part.lower() in {"archive", "archives"} for part in relative_parts))
    nomesh_path_penalty = int("nomesh" in relative_path.lower())
    return (
        not candidate["authoritative"],
        -int(candidate["direct_robot_kinematics_compatible"]),
        -int(candidate["relevance_score"]),
        archived_path_penalty,
        nomesh_path_penalty,
        len(relative_parts),
        candidate["suffix"],
        candidate["path"],
    )


def build_source_inventory_review_packet(summary: dict[str, Any]) -> dict[str, Any]:
    next_required_for_goal = summary.get("next_required_for_goal") or []
    candidates = summary.get("candidates") or []
    authoritative_candidates = [
        candidate for candidate in candidates if candidate.get("authoritative")
    ]
    selected_so101_relevance_ready = (
        summary.get("selected_authoritative_candidate_so101_relevance_ready") is True
    )
    packet_status = source_inventory_review_packet_status(
        candidate_count=int(summary.get("candidate_count") or 0),
        authoritative_candidate_count=int(summary.get("authoritative_candidate_count") or 0),
        selected_authoritative_candidate_so101_relevance_ready=selected_so101_relevance_ready,
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

    if len(authoritative_candidates) > 1:
        append_item(
            item_id="source_inventory:multiple_authoritative_candidates",
            item_type="authoritative_source_selection",
            status="multiple_authoritative_candidates_need_selection",
            gate="reviewed_model_authority",
            required_input="single_authoritative_model_asset",
            candidate_id=None,
            candidate_path=None,
            candidate_relevance=None,
            source_authority_status=summary.get("source_authority_gate_status"),
            source_authority_review_status=summary.get("source_authority_review_status"),
            next_action_id="select_single_authoritative_so101_model_source",
            evidence={
                "authoritative_candidate_count": len(authoritative_candidates),
                "authoritative_candidate_ids": [
                    candidate.get("candidate_id") for candidate in authoritative_candidates
                ],
                "authoritative_candidate_paths": [
                    candidate.get("path") for candidate in authoritative_candidates
                ],
            },
            operator_action=(
                "Select exactly one reviewed SO-101 model source before generating or "
                "supplying the reviewed model bundle manifest."
            ),
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
        if (
            candidate.get("authoritative")
            and candidate.get("likely_so101_relevance") not in {"high", "medium"}
        ):
            next_action_id = "select_so101_relevant_authoritative_model_source"
        elif (
            candidate.get("authoritative")
            and candidate.get("source_authority_review_status")
            != "review_metadata_supplied"
        ):
            next_action_id = "record_source_authority_review_metadata"
        elif not candidate.get("authoritative"):
            next_action_id = "review_and_declare_authoritative_so101_model_source"
        else:
            next_action_id = "run_so101_model_bundle_probe"
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
            next_action_id=next_action_id,
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
            "authoritative_candidate_not_so101_relevant",
            "multiple_authoritative_candidates_need_selection",
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
        "authoritative_source_selection_status": summary.get(
            "authoritative_source_selection_status"
        ),
        "authoritative_candidate_ids": summary.get("authoritative_candidate_ids") or [],
        "authoritative_candidate_paths": summary.get("authoritative_candidate_paths") or [],
        "selected_authoritative_candidate_id": summary.get(
            "selected_authoritative_candidate_id"
        ),
        "selected_authoritative_candidate_path": summary.get(
            "selected_authoritative_candidate_path"
        ),
        "selected_authoritative_candidate_sha256": summary.get(
            "selected_authoritative_candidate_sha256"
        ),
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


def source_intake_status(summary: dict[str, Any]) -> str:
    candidate_count = int(summary.get("candidate_count") or 0)
    authoritative_candidate_count = int(summary.get("authoritative_candidate_count") or 0)
    if candidate_count <= 0:
        return "source_root_required"
    if authoritative_candidate_count <= 0:
        return "source_authority_review_required"
    if authoritative_candidate_count > 1:
        return "single_source_selection_required"
    if summary.get("selected_authoritative_candidate_so101_relevance_ready") is not True:
        return "source_candidate_relevance_required"
    if summary.get("source_authority_review_ready") is not True:
        return "source_review_metadata_required"
    return "source_authority_ready_waiting_for_bundle_manifest"


def source_intake_recommended_candidate(summary: dict[str, Any]) -> dict[str, Any]:
    candidates = summary.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    candidate_by_id = {
        candidate.get("candidate_id"): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("candidate_id")
    }
    selected_id = summary.get("selected_authoritative_candidate_id")
    recommended_contract_check = summary.get("recommended_contract_check")
    recommended_contract_check = (
        recommended_contract_check
        if isinstance(recommended_contract_check, dict)
        else {}
    )
    candidate = candidate_by_id.get(selected_id) if selected_id else None
    if candidate is None:
        candidate = candidate_by_id.get(recommended_contract_check.get("candidate_id"))
    return candidate if isinstance(candidate, dict) else {}


def source_intake_command_template(
    action_id: str,
    summary: dict[str, Any] | None = None,
) -> list[str]:
    summary = summary or {}
    candidate = source_intake_recommended_candidate(summary)
    source_root = candidate.get("source_root") or "<absolute-so101-model-source-root>"
    model_path = candidate.get("path") or "<absolute-reviewed-so101-model-file>"
    if action_id == "scan_or_supply_so101_model_source_root":
        return [
            "python",
            "scripts/smoke_sim_so101_model_source_inventory.py",
            "--root",
            source_root,
            "--output-dir",
            "/private/tmp/lerobot_sim/so101_model_source_inventory_external",
        ]
    if action_id in {
        "review_and_declare_authoritative_so101_model_source",
        "record_source_authority_review_metadata",
        "select_single_authoritative_so101_model_source",
        "select_so101_relevant_authoritative_model_source",
    }:
        return [
            "python",
            "scripts/smoke_sim_so101_model_source_inventory.py",
            "--root",
            source_root,
            "--authoritative-path",
            model_path,
            "--authority-license-basis",
            "<reviewed-license-or-redistribution-basis>",
            "--authority-source-reference",
            "<reviewed-cad-export-source-url-or-commit>",
            "--authority-review-scope",
            "model_identity",
            "--authority-review-scope",
            "provenance",
            "--authority-review-scope",
            "license",
            "--authority-reviewed-by",
            "<reviewer-or-review-system>",
            "--authority-reviewed-at",
            "<YYYY-MM-DD>",
            "--authority-review-id",
            "<review-ticket-commit-or-checklist-id>",
            "--output-dir",
            "/private/tmp/lerobot_sim/so101_model_source_inventory_reviewed",
        ]
    if action_id == "run_so101_model_bundle_probe":
        return [
            "python",
            "scripts/smoke_sim_so101_model_bundle_probe.py",
            "--model-path",
            model_path,
            "--asset-root",
            source_root,
            "--output-dir",
            "/private/tmp/lerobot_sim/so101_model_bundle_probe_review_draft",
        ]
    if action_id == "supply_reviewed_so101_model_bundle_manifest":
        return [
            "python",
            "scripts/smoke_sim_so101_model_bundle_manifest.py",
            "--manifest-path",
            "<reviewed-so101-model-bundle-manifest.json>",
            "--output-dir",
            "/private/tmp/lerobot_sim/so101_model_bundle_manifest_reviewed",
        ]
    return []


def build_source_intake_checklist(summary: dict[str, Any]) -> dict[str, Any]:
    source_authority_review = summary.get("source_authority_review")
    source_authority_review = (
        source_authority_review if isinstance(source_authority_review, dict) else {}
    )
    recommended_candidate = source_intake_recommended_candidate(summary)
    recommended_candidate_context = {
        "candidate_id": recommended_candidate.get("candidate_id"),
        "candidate_path": recommended_candidate.get("path"),
        "source_root": recommended_candidate.get("source_root"),
        "source_root_type": recommended_candidate.get("source_root_type"),
        "authoritative": recommended_candidate.get("authoritative"),
        "likely_so101_relevance": recommended_candidate.get("likely_so101_relevance"),
        "relevance_score": recommended_candidate.get("relevance_score"),
        "file_sha256": recommended_candidate.get("file_sha256"),
    }
    actions: list[dict[str, Any]] = []
    for action in summary.get("next_required_for_goal") or []:
        if not isinstance(action, dict):
            continue
        action_id = action.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            continue
        actions.append(
            {
                "priority": len(actions) + 1,
                "action_id": action_id,
                "status": "pending",
                "gate": action.get("gate"),
                "title": action.get("title"),
                "detail": action.get("detail"),
                "recommended_candidate_id": recommended_candidate_context.get(
                    "candidate_id"
                ),
                "recommended_candidate_path": recommended_candidate_context.get(
                    "candidate_path"
                ),
                "recommended_candidate_source_root": recommended_candidate_context.get(
                    "source_root"
                ),
                "recommended_candidate_authoritative": recommended_candidate_context.get(
                    "authoritative"
                ),
                "recommended_candidate_relevance": recommended_candidate_context.get(
                    "likely_so101_relevance"
                ),
                "recommended_candidate_sha256": recommended_candidate_context.get(
                    "file_sha256"
                ),
                "evidence_context": recommended_candidate_context,
                "command": source_intake_command_template(action_id, summary),
                "required_inputs": (
                    source_authority_review.get("missing_required_fields") or []
                    if action_id
                    in {
                        "review_and_declare_authoritative_so101_model_source",
                        "record_source_authority_review_metadata",
                        "select_single_authoritative_so101_model_source",
                    }
                    else []
                ),
            }
        )
    return {
        "schema": SOURCE_INTAKE_SCHEMA,
        "ok": True,
        "status": source_intake_status(summary),
        "model_authority": "source_intake_not_authority",
        "source_inventory_status": summary.get("status"),
        "source_authority_gate_status": summary.get("source_authority_gate_status"),
        "source_authority_review_status": summary.get("source_authority_review_status"),
        "source_authority_review_ready": summary.get("source_authority_review_ready"),
        "source_authority_review_scope_ready": summary.get(
            "source_authority_review_scope_ready"
        ),
        "candidate_count": summary.get("candidate_count"),
        "likely_candidate_count": summary.get("likely_candidate_count"),
        "direct_contract_candidate_count": summary.get("direct_contract_candidate_count"),
        "authoritative_candidate_count": summary.get("authoritative_candidate_count"),
        "scanned_roots": [
            {
                "path": root.get("path"),
                "exists": root.get("exists"),
                "is_file": root.get("is_file"),
                "source_root_type": root.get("source_root_type"),
                "candidate_count": root.get("candidate_count"),
            }
            for root in summary.get("roots") or []
            if isinstance(root, dict)
        ],
        "root_count": summary.get("root_count"),
        "required_review_scope_ids": summary.get("source_authority_required_review_scope_ids")
        or [],
        "supplied_review_scope_ids": summary.get("source_authority_supplied_review_scope_ids")
        or [],
        "missing_review_scope_ids": summary.get("source_authority_missing_review_scope_ids")
        or [],
        "missing_required_fields": source_authority_review.get("missing_required_fields")
        or [],
        "review_evidence_valid_fields": source_authority_review.get(
            "review_evidence_valid_fields"
        )
        or [],
        "review_evidence_placeholder_fields": source_authority_review.get(
            "review_evidence_placeholder_fields"
        )
        or [],
        "review_evidence_invalid_fields": source_authority_review.get(
            "review_evidence_invalid_fields"
        )
        or [],
        "required_metadata_valid_fields": source_authority_review.get(
            "required_metadata_valid_fields"
        )
        or [],
        "required_metadata_placeholder_fields": source_authority_review.get(
            "required_metadata_placeholder_fields"
        )
        or [],
        "next_required_for_goal": summary.get("next_required_for_goal") or [],
        "next_required_action_ids": summary.get("next_required_action_ids") or [],
        "recommended_candidate": recommended_candidate_context,
        "recommended_contract_check": summary.get("recommended_contract_check"),
        "known_public_candidate_sources": summary.get("known_public_candidate_sources")
        or [],
        "action_count": len(actions),
        "actions": actions,
        "observed_evidence_is_authority": False,
        "physical_so101_model_authority_ready": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "artifacts": summary.get("artifacts"),
        "caveats": [
            "This source-intake checklist is operator guidance, not reviewed physical SO-101 authority.",
            "A candidate path is still untrusted until source identity, provenance, license, and reviewer evidence are explicit.",
            "A source-authority-ready inventory still requires a reviewed model bundle manifest before MuJoCo motion or training gates can close.",
        ],
    }


def build_source_review_requirements(summary: dict[str, Any]) -> dict[str, Any]:
    source_authority_review = summary.get("source_authority_review")
    source_authority_review = (
        source_authority_review if isinstance(source_authority_review, dict) else {}
    )
    missing_required_fields = set(source_authority_review.get("missing_required_fields") or [])
    missing_required_groups = set(
        source_authority_review.get("review_evidence_missing_required_groups") or []
    )
    satisfied_required_groups = set(
        source_authority_review.get("review_evidence_satisfied_required_groups") or []
    )
    missing_review_scope_ids = set(
        summary.get("source_authority_missing_review_scope_ids") or []
    )
    supplied_review_scope_ids = set(
        summary.get("source_authority_supplied_review_scope_ids") or []
    )
    valid_metadata_fields = set(
        source_authority_review.get("required_metadata_valid_fields") or []
    )
    placeholder_metadata_fields = set(
        source_authority_review.get("required_metadata_placeholder_fields") or []
    )

    requirements: list[dict[str, Any]] = []

    def add_requirement(
        requirement_id: str,
        *,
        status: str,
        required_input: str,
        supplied: bool,
        missing: bool,
        evidence_fields: list[str],
        operator_action: str,
        next_action_id: str | None = "record_source_authority_review_metadata",
        gate: str = "reviewed_model_authority",
    ) -> None:
        requirements.append(
            {
                "priority": len(requirements) + 1,
                "requirement_id": requirement_id,
                "status": status,
                "gate": gate,
                "required_input": required_input,
                "supplied": supplied,
                "missing": missing,
                "evidence_fields": evidence_fields,
                "next_action_id": None if status == "satisfied" else next_action_id,
                "operator_action": operator_action,
            }
        )

    authoritative_candidate_count = int(summary.get("authoritative_candidate_count") or 0)
    add_requirement(
        "authoritative_model_selection",
        status=(
            "satisfied"
            if authoritative_candidate_count == 1
            and summary.get("selected_authoritative_candidate_so101_relevance_ready")
            is True
            else "action_required"
        ),
        required_input="exactly_one_so101_relevant_authoritative_model_path",
        supplied=authoritative_candidate_count == 1,
        missing=authoritative_candidate_count != 1,
        evidence_fields=[
            "selected_authoritative_candidate_path",
            "selected_authoritative_candidate_sha256",
            "selected_authoritative_candidate_so101_relevance",
        ],
        next_action_id=(
            "select_single_authoritative_so101_model_source"
            if authoritative_candidate_count > 1
            else "review_and_declare_authoritative_so101_model_source"
        ),
        operator_action=(
            "Select one reviewed SO-101-relevant model source path before source "
            "authority can feed the bundle manifest."
        ),
    )

    review_group_fields = {
        "review_actor": ["authority_reviewed_by"],
        "review_trace": [
            "authority_reviewed_at",
            "authority_review_id",
            "authority_review_url",
        ],
        "review_artifact": ["authority_review_id", "authority_review_url"],
    }
    for group_id, fields in review_group_fields.items():
        missing = group_id in missing_required_groups
        supplied = group_id in satisfied_required_groups
        add_requirement(
            f"review_evidence:{group_id}",
            status="action_required" if missing else "satisfied",
            required_input=f"authority_review_evidence:{group_id}",
            supplied=supplied,
            missing=missing,
            evidence_fields=fields,
            operator_action=(
                "Record reviewer identity, review timestamp, and a stable review "
                "artifact handle; a date-only trace without reviewer and artifact "
                "handle is not enough."
            ),
        )

    for scope_id in SOURCE_AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS:
        missing = scope_id in missing_review_scope_ids
        supplied = scope_id in supplied_review_scope_ids
        add_requirement(
            f"review_scope:{scope_id}",
            status="action_required" if missing else "satisfied",
            required_input=f"authority_review_scope:{scope_id}",
            supplied=supplied,
            missing=missing,
            evidence_fields=["authority_review_scope"],
            operator_action=SOURCE_AUTHORITY_REVIEW_SCOPE_DESCRIPTIONS[scope_id],
        )

    for field, label in (
        (
            "authority_source_reference",
            "CAD/export source URL, commit, package release, or equivalent source handle.",
        ),
        (
            "authority_license_basis",
            "Reviewed license or redistribution basis for using the selected model source.",
        ),
    ):
        missing = field in missing_required_fields
        add_requirement(
            field,
            status="action_required" if missing else "satisfied",
            required_input=field,
            supplied=field in valid_metadata_fields,
            missing=missing,
            evidence_fields=[field],
            operator_action=label,
        )

    ready = (
        authoritative_candidate_count == 1
        and summary.get("selected_authoritative_candidate_so101_relevance_ready") is True
        and source_authority_review.get("ready") is True
    )
    action_required_requirement_ids = [
        requirement["requirement_id"]
        for requirement in requirements
        if requirement.get("status") != "satisfied"
    ]
    return {
        "schema": SOURCE_REVIEW_REQUIREMENTS_SCHEMA,
        "ok": True,
        "status": (
            "source_review_requirements_satisfied"
            if ready
            else "source_review_requirements_action_required"
        ),
        "model_authority": "source_review_requirements_not_authority",
        "source_inventory_status": summary.get("status"),
        "source_authority_gate_status": summary.get("source_authority_gate_status"),
        "source_authority_review_status": summary.get("source_authority_review_status"),
        "source_authority_review_ready": summary.get("source_authority_review_ready"),
        "source_authority_review_scope_ready": summary.get(
            "source_authority_review_scope_ready"
        ),
        "authoritative_candidate_count": summary.get("authoritative_candidate_count"),
        "selected_authoritative_candidate_path": summary.get(
            "selected_authoritative_candidate_path"
        ),
        "selected_authoritative_candidate_sha256": summary.get(
            "selected_authoritative_candidate_sha256"
        ),
        "required_review_scope_ids": summary.get(
            "source_authority_required_review_scope_ids"
        )
        or [],
        "supplied_review_scope_ids": summary.get(
            "source_authority_supplied_review_scope_ids"
        )
        or [],
        "missing_review_scope_ids": summary.get(
            "source_authority_missing_review_scope_ids"
        )
        or [],
        "review_evidence_required_groups": source_authority_review.get(
            "review_evidence_required_groups"
        )
        or [],
        "review_evidence_satisfied_required_groups": source_authority_review.get(
            "review_evidence_satisfied_required_groups"
        )
        or [],
        "review_evidence_missing_required_groups": source_authority_review.get(
            "review_evidence_missing_required_groups"
        )
        or [],
        "required_metadata_valid_fields": sorted(valid_metadata_fields),
        "required_metadata_placeholder_fields": sorted(placeholder_metadata_fields),
        "missing_required_fields": source_authority_review.get("missing_required_fields")
        or [],
        "requirement_count": len(requirements),
        "action_required_requirement_ids": action_required_requirement_ids,
        "next_required_action_ids": summary.get("next_required_action_ids") or [],
        "requirements": requirements,
        "observed_evidence_is_authority": False,
        "physical_so101_model_authority_ready": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "caveats": [
            "This source-review requirements artifact is operator guidance only, not reviewed physical SO-101 authority.",
            "A satisfied source review still only clears source authority; a reviewed bundle manifest and reviewed MuJoCo motion are separate gates.",
            "Placeholder, malformed, future-dated, or local-only review evidence must remain action-required.",
        ],
    }


def build_summary(
    roots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    artifacts: dict[str, str],
    source_authority_review_input: dict[str, Any],
) -> dict[str, Any]:
    authoritative_candidates = [candidate for candidate in candidates if candidate["authoritative"]]
    authoritative_candidate_paths = [candidate["path"] for candidate in authoritative_candidates]
    authoritative_candidate_ids = [
        candidate["candidate_id"] for candidate in authoritative_candidates
    ]
    selected_authoritative_candidate = (
        authoritative_candidates[0] if len(authoritative_candidates) == 1 else None
    )
    selected_authoritative_candidate_so101_relevance_ready = (
        selected_authoritative_candidate is not None
        and selected_authoritative_candidate.get("likely_so101_relevance")
        in {"high", "medium"}
    )
    direct_candidates = [
        candidate
        for candidate in candidates
        if candidate["direct_robot_kinematics_compatible"] and candidate["likely_so101_relevance"] in {"high", "medium"}
    ]
    likely_candidates = [
        candidate for candidate in candidates if candidate["likely_so101_relevance"] in {"high", "medium"}
    ]
    best_candidate = sorted(candidates, key=candidate_sort_key)[0] if candidates else None
    if not authoritative_candidates:
        status = "missing_authoritative_model"
    elif len(authoritative_candidates) > 1:
        status = "ambiguous_authoritative_model"
    elif not selected_authoritative_candidate_so101_relevance_ready:
        status = "authoritative_model_not_so101_relevant"
    else:
        status = "authoritative_model_found"
    selection_status = authoritative_source_selection_status(
        len(authoritative_candidates)
    )
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
    elif len(authoritative_candidates) > 1:
        diagnostics.append(
            {
                "diagnostic": "ambiguous_authoritative_model",
                "severity": "action_required",
                "authoritative_candidate_count": len(authoritative_candidates),
                "authoritative_candidate_ids": authoritative_candidate_ids,
                "authoritative_candidate_paths": authoritative_candidate_paths,
                "reason": (
                    "Multiple model files matched the authoritative path/root. Select one "
                    "reviewed model path before the source-authority gate can close."
                ),
            }
        )
    elif not selected_authoritative_candidate_so101_relevance_ready:
        diagnostics.append(
            {
                "diagnostic": "authoritative_model_not_so101_relevant",
                "severity": "action_required",
                "authoritative_candidate_count": len(authoritative_candidates),
                "selected_authoritative_candidate_id": selected_authoritative_candidate.get(
                    "candidate_id"
                )
                if selected_authoritative_candidate
                else None,
                "selected_authoritative_candidate_path": selected_authoritative_candidate.get(
                    "path"
                )
                if selected_authoritative_candidate
                else None,
                "likely_so101_relevance": selected_authoritative_candidate.get(
                    "likely_so101_relevance"
                )
                if selected_authoritative_candidate
                else None,
                "relevance_score": selected_authoritative_candidate.get("relevance_score")
                if selected_authoritative_candidate
                else None,
                "relevance_reasons": selected_authoritative_candidate.get(
                    "relevance_reasons"
                )
                if selected_authoritative_candidate
                else [],
                "reason": (
                    "The selected authoritative file does not match the SO-101 "
                    "source heuristic. Select a reviewed SO-101-relevant source "
                    "before the source-authority gate can close."
                ),
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
    contract_candidate = (
        selected_authoritative_candidate
        if selected_authoritative_candidate is not None
        else best_candidate
        if not authoritative_candidates
        else None
    )
    if (
        contract_candidate
        and contract_candidate["direct_robot_kinematics_compatible"]
        and contract_candidate["likely_so101_relevance"] in {"high", "medium"}
    ):
        recommended_contract_check = {
            "command": [
                sys.executable,
                "scripts/smoke_sim_so101_model_contract.py",
                "--model-path",
                contract_candidate["path"],
                "--output-dir",
                str(DEFAULT_OUTPUT_DIR.parent / "so101_model_contract_inventory_candidate"),
            ],
            "candidate_id": contract_candidate["candidate_id"],
            "candidate_path": contract_candidate["path"],
            "authoritative": contract_candidate["authoritative"],
        }

    next_required_for_goal = source_inventory_next_required(
        candidate_count=len(candidates),
        likely_candidate_count=len(likely_candidates),
        direct_contract_candidate_count=len(direct_candidates),
        authoritative_candidate_count=len(authoritative_candidates),
        selected_authoritative_candidate_so101_relevance_ready=(
            selected_authoritative_candidate_so101_relevance_ready
        ),
        source_authority_review_ready=authority_review["ready"],
        recommended_contract_check=recommended_contract_check,
    )
    source_blockers = source_authority_blockers(
        candidate_count=len(candidates),
        authoritative_candidate_count=len(authoritative_candidates),
        selected_authoritative_candidate_so101_relevance_ready=(
            selected_authoritative_candidate_so101_relevance_ready
        ),
        source_authority_review_ready=authority_review["ready"],
    )
    public_candidate_sources = known_public_so101_candidate_sources()

    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "model_authority": "model_source_inventory_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "physical_so101_model_authority_ready": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
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
        "authoritative_source_selection_status": selection_status,
        "authoritative_candidate_ids": authoritative_candidate_ids,
        "authoritative_candidate_paths": authoritative_candidate_paths,
        "selected_authoritative_candidate_id": (
            selected_authoritative_candidate["candidate_id"]
            if selected_authoritative_candidate
            else None
        ),
        "selected_authoritative_candidate_path": (
            selected_authoritative_candidate["path"]
            if selected_authoritative_candidate
            else None
        ),
        "selected_authoritative_candidate_sha256": (
            selected_authoritative_candidate["file_sha256"]
            if selected_authoritative_candidate
            else None
        ),
        "selected_authoritative_candidate_so101_relevance": (
            selected_authoritative_candidate.get("likely_so101_relevance")
            if selected_authoritative_candidate
            else None
        ),
        "selected_authoritative_candidate_so101_relevance_score": (
            selected_authoritative_candidate.get("relevance_score")
            if selected_authoritative_candidate
            else None
        ),
        "selected_authoritative_candidate_so101_relevance_reasons": (
            selected_authoritative_candidate.get("relevance_reasons")
            if selected_authoritative_candidate
            else []
        ),
        "selected_authoritative_candidate_so101_relevance_ready": (
            selected_authoritative_candidate_so101_relevance_ready
        ),
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
            selected_authoritative_candidate_so101_relevance_ready=(
                selected_authoritative_candidate_so101_relevance_ready
            ),
            source_authority_review_ready=authority_review["ready"],
        ),
        "source_authority_blockers": source_blockers,
        "roots": roots,
        "candidates": candidates,
        "recommended_contract_check": recommended_contract_check,
        "known_public_candidate_source_count": len(public_candidate_sources),
        "known_public_candidate_sources": public_candidate_sources,
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
    source_intake_checklist = build_source_intake_checklist(summary)
    summary.update(
        {
            "source_intake_status": source_intake_checklist["status"],
            "source_intake_model_authority": source_intake_checklist["model_authority"],
            "source_intake_action_count": source_intake_checklist["action_count"],
            "source_intake_action_ids": [
                action["action_id"] for action in source_intake_checklist["actions"]
            ],
            "source_intake_observed_evidence_is_authority": source_intake_checklist[
                "observed_evidence_is_authority"
            ],
            "source_intake_physical_so101_model_authority_ready": source_intake_checklist[
                "physical_so101_model_authority_ready"
            ],
            "source_intake_development_fixture_evidence_not_physical_so101_truth": source_intake_checklist[
                "development_fixture_evidence_not_physical_so101_truth"
            ],
            "source_intake_checklist_json_path": artifacts.get(
                "source_intake_checklist_json"
            ),
            "source_intake_checklist_csv_path": artifacts.get(
                "source_intake_checklist_csv"
            ),
            "source_intake_checklist": source_intake_checklist,
        }
    )
    source_review_requirements = build_source_review_requirements(summary)
    summary.update(
        {
            "source_review_requirements_status": source_review_requirements["status"],
            "source_review_requirements_model_authority": source_review_requirements[
                "model_authority"
            ],
            "source_review_requirements_requirement_count": source_review_requirements[
                "requirement_count"
            ],
            "source_review_requirements_action_required_requirement_ids": (
                source_review_requirements["action_required_requirement_ids"]
            ),
            "source_review_requirements_observed_evidence_is_authority": (
                source_review_requirements["observed_evidence_is_authority"]
            ),
            "source_review_requirements_physical_so101_model_authority_ready": (
                source_review_requirements["physical_so101_model_authority_ready"]
            ),
            "source_review_requirements_development_fixture_evidence_not_physical_so101_truth": (
                source_review_requirements[
                    "development_fixture_evidence_not_physical_so101_truth"
                ]
            ),
            "source_review_requirements_json_path": artifacts.get(
                "source_review_requirements_json"
            ),
            "source_review_requirements_csv_path": artifacts.get(
                "source_review_requirements_csv"
            ),
            "source_review_requirements": source_review_requirements,
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


def write_source_intake_csv(path: Path, source_intake: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_INTAKE_FIELDNAMES)
        writer.writeheader()
        for action in source_intake.get("actions") or []:
            writer.writerow({field: csv_value(action.get(field)) for field in SOURCE_INTAKE_FIELDNAMES})


def write_source_review_requirements_csv(
    path: Path,
    source_review_requirements: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_REVIEW_REQUIREMENTS_FIELDNAMES)
        writer.writeheader()
        for requirement in source_review_requirements.get("requirements") or []:
            writer.writerow(
                {
                    field: csv_value(requirement.get(field))
                    for field in SOURCE_REVIEW_REQUIREMENTS_FIELDNAMES
                }
            )


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SO-101 Model Source Inventory",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `model_authority`: `{summary['model_authority']}`",
        f"- `observed_evidence_is_physical_so101_authority`: `{str(summary['observed_evidence_is_physical_so101_authority']).lower()}`",
        f"- `observed_evidence_is_policy_training_authority`: `{str(summary['observed_evidence_is_policy_training_authority']).lower()}`",
        f"- `development_fixture_evidence_not_physical_so101_truth`: `{str(summary['development_fixture_evidence_not_physical_so101_truth']).lower()}`",
        f"- `development_fixture_evidence_not_policy_training_truth`: `{str(summary['development_fixture_evidence_not_policy_training_truth']).lower()}`",
        f"- `physical_so101_model_authority_ready`: `{str(summary['physical_so101_model_authority_ready']).lower()}`",
        f"- `ready_for_model_backed_ik`: `{str(summary['ready_for_model_backed_ik']).lower()}`",
        f"- `ready_for_policy_training`: `{str(summary['ready_for_policy_training']).lower()}`",
        f"- `candidate_count`: `{summary['candidate_count']}`",
        f"- `likely_candidate_count`: `{summary['likely_candidate_count']}`",
        f"- `direct_contract_candidate_count`: `{summary['direct_contract_candidate_count']}`",
        f"- `authoritative_candidate_count`: `{summary['authoritative_candidate_count']}`",
        f"- `authoritative_source_selection_status`: `{summary['authoritative_source_selection_status']}`",
        f"- `selected_authoritative_candidate_id`: `{summary.get('selected_authoritative_candidate_id') or 'none'}`",
        f"- `selected_authoritative_candidate_path`: `{summary.get('selected_authoritative_candidate_path') or 'none'}`",
        f"- `selected_authoritative_candidate_sha256`: `{summary.get('selected_authoritative_candidate_sha256') or 'none'}`",
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
        f"- `source_intake_status`: `{summary['source_intake_status']}`",
        f"- `source_intake_model_authority`: `{summary['source_intake_model_authority']}`",
        f"- `source_intake_action_ids`: `{', '.join(summary.get('source_intake_action_ids') or []) if summary.get('source_intake_action_ids') else 'none'}`",
        f"- `source_intake_observed_evidence_is_authority`: `{str(summary['source_intake_observed_evidence_is_authority']).lower()}`",
        f"- `source_intake_physical_so101_model_authority_ready`: `{str(summary['source_intake_physical_so101_model_authority_ready']).lower()}`",
        f"- `source_intake_development_fixture_evidence_not_physical_so101_truth`: `{str(summary['source_intake_development_fixture_evidence_not_physical_so101_truth']).lower()}`",
        f"- `source_review_requirements_status`: `{summary['source_review_requirements_status']}`",
        f"- `source_review_requirements_model_authority`: `{summary['source_review_requirements_model_authority']}`",
        f"- `source_review_requirements_requirement_count`: `{summary['source_review_requirements_requirement_count']}`",
        f"- `source_review_requirements_action_required_requirement_ids`: `{', '.join(summary.get('source_review_requirements_action_required_requirement_ids') or []) if summary.get('source_review_requirements_action_required_requirement_ids') else 'none'}`",
        f"- `source_review_requirements_observed_evidence_is_authority`: `{str(summary['source_review_requirements_observed_evidence_is_authority']).lower()}`",
        f"- `source_review_requirements_physical_so101_model_authority_ready`: `{str(summary['source_review_requirements_physical_so101_model_authority_ready']).lower()}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `candidates_csv`: `{summary['artifacts']['candidates_csv']}`",
        f"- `review_packet_json`: `{summary['artifacts']['review_packet_json']}`",
        f"- `review_packet_csv`: `{summary['artifacts']['review_packet_csv']}`",
        f"- `source_intake_checklist_json`: `{summary['artifacts']['source_intake_checklist_json']}`",
        f"- `source_intake_checklist_csv`: `{summary['artifacts']['source_intake_checklist_csv']}`",
        f"- `source_review_requirements_json`: `{summary['artifacts']['source_review_requirements_json']}`",
        f"- `source_review_requirements_csv`: `{summary['artifacts']['source_review_requirements_csv']}`",
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
            "## Known Public Candidate Sources",
            "",
            (
                "These sources are operator intake pointers only. Fetch or vendor them "
                "at a pinned commit, then run the inventory and bundle probe before "
                "declaring source authority."
            ),
            "",
        ]
    )
    public_sources = summary.get("known_public_candidate_sources") or []
    if not public_sources:
        lines.append("- none")
    for source in public_sources:
        lines.append(f"- `{source.get('source_id')}`: {source.get('name')}")
        lines.append(f"  - Repository: `{source.get('repository_url')}`")
        lines.append(f"  - Source tree: `{source.get('source_tree_url')}`")
        lines.append(f"  - Source path: `{source.get('source_path')}`")
        lines.append(f"  - Authority boundary: {source.get('authority_boundary')}")
        notes = source.get("source_notes") or []
        if notes:
            lines.append(f"  - Notes: {'; '.join(str(note) for note in notes)}")
        operator_intake = source.get("operator_intake")
        operator_intake = operator_intake if isinstance(operator_intake, dict) else {}
        command_template_items = [
            (key, value)
            for key, value in operator_intake.items()
            if key.endswith("_command_template") and isinstance(value, list)
        ]
        if command_template_items:
            lines.append("  - Operator command templates:")
            for key, value in command_template_items:
                lines.append(f"    - `{key}`: `{' '.join(str(part) for part in value)}`")
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
            "## Source Intake Checklist",
            "",
            "This checklist focuses the first unresolved gate action. It is operator guidance only, not reviewed physical SO-101 authority.",
            "",
            "| Priority | Action | Status | Command |",
            "| --- | --- | --- | --- |",
        ]
    )
    for action in summary["source_intake_checklist"].get("actions") or []:
        command = " ".join(str(part) for part in action.get("command") or []) or "n/a"
        lines.append(
            "| `{priority}` | `{action_id}` | `{status}` | `{command}` |".format(
                priority=action.get("priority"),
                action_id=action.get("action_id"),
                status=action.get("status"),
                command=command.replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Source Review Requirements",
            "",
            "This table records the minimum source-review evidence needed before a selected source can feed the reviewed bundle manifest. It is not physical SO-101 authority.",
            "",
            "| Priority | Requirement | Status | Missing | Next Action |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for requirement in summary["source_review_requirements"].get("requirements") or []:
        lines.append(
            "| `{priority}` | `{requirement_id}` | `{status}` | `{missing}` | `{action}` |".format(
                priority=requirement.get("priority"),
                requirement_id=requirement.get("requirement_id"),
                status=requirement.get("status"),
                missing=str(requirement.get("missing")).lower(),
                action=requirement.get("next_action_id") or "n/a",
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
    source_intake_path = output_dir / "so101_model_source_intake_checklist.json"
    source_intake_csv_path = output_dir / "so101_model_source_intake_checklist.csv"
    source_review_requirements_path = (
        output_dir / "so101_model_source_review_requirements.json"
    )
    source_review_requirements_csv_path = (
        output_dir / "so101_model_source_review_requirements.csv"
    )
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "candidates_csv": str(csv_path),
        "review_packet_json": str(review_packet_path),
        "review_packet_csv": str(review_packet_csv_path),
        "source_intake_checklist_json": str(source_intake_path),
        "source_intake_checklist_csv": str(source_intake_csv_path),
        "source_review_requirements_json": str(source_review_requirements_path),
        "source_review_requirements_csv": str(source_review_requirements_csv_path),
        "readme_md": str(readme_path),
    }
    summary = build_summary(root_records, candidates, artifacts, authority_review_input)

    write_json(summary_path, summary)
    write_json(review_packet_path, summary["review_packet"])
    write_json(source_intake_path, summary["source_intake_checklist"])
    write_json(
        source_review_requirements_path,
        summary["source_review_requirements"],
    )
    write_csv(csv_path, candidates)
    write_review_packet_csv(review_packet_csv_path, summary["review_packet"])
    write_source_intake_csv(source_intake_csv_path, summary["source_intake_checklist"])
    write_source_review_requirements_csv(
        source_review_requirements_csv_path,
        summary["source_review_requirements"],
    )
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
                "known_public_candidate_source_count": summary[
                    "known_public_candidate_source_count"
                ],
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
                "source_intake_status": summary["source_intake_status"],
                "source_intake_model_authority": summary["source_intake_model_authority"],
                "source_intake_action_count": summary["source_intake_action_count"],
                "source_intake_action_ids": summary["source_intake_action_ids"],
                "source_intake_observed_evidence_is_authority": summary[
                    "source_intake_observed_evidence_is_authority"
                ],
                "source_intake_physical_so101_model_authority_ready": summary[
                    "source_intake_physical_so101_model_authority_ready"
                ],
                "source_intake_development_fixture_evidence_not_physical_so101_truth": summary[
                    "source_intake_development_fixture_evidence_not_physical_so101_truth"
                ],
                "source_review_requirements_status": summary[
                    "source_review_requirements_status"
                ],
                "source_review_requirements_model_authority": summary[
                    "source_review_requirements_model_authority"
                ],
                "source_review_requirements_requirement_count": summary[
                    "source_review_requirements_requirement_count"
                ],
                "source_review_requirements_action_required_requirement_ids": summary[
                    "source_review_requirements_action_required_requirement_ids"
                ],
                "source_review_requirements_observed_evidence_is_authority": summary[
                    "source_review_requirements_observed_evidence_is_authority"
                ],
                "source_review_requirements_physical_so101_model_authority_ready": summary[
                    "source_review_requirements_physical_so101_model_authority_ready"
                ],
                "source_review_requirements_development_fixture_evidence_not_physical_so101_truth": summary[
                    "source_review_requirements_development_fixture_evidence_not_physical_so101_truth"
                ],
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
