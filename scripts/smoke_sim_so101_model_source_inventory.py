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
    "authoritative",
    "diagnostics",
)


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
    contract_supported = suffix in SUPPORTED_SUFFIXES and exists
    direct_compatible = suffix in DIRECT_ROBOT_KINEMATICS_SUFFIXES and exists

    if relevance == "none":
        diagnostics.append("not_likely_so101")
    if not direct_compatible:
        diagnostics.append("not_direct_robot_kinematics_urdf")
    if not authoritative:
        diagnostics.append("source_authority_not_verified")
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


def build_summary(
    roots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    artifacts: dict[str, str],
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

    return {
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
        "roots": roots,
        "candidates": candidates,
        "recommended_contract_check": recommended_contract_check,
        "diagnostics": diagnostics,
        "artifacts": artifacts,
        "limitations": [
            "This inventory never opens hardware, cameras, serial ports, GUI flows, or network resources.",
            "The script does not copy model assets into the repository.",
            "SO-101 relevance is heuristic until provenance and source authority are reviewed.",
            "A candidate URDF being directly compatible with RobotKinematics does not prove TCP, board, or simulator-frame alignment.",
        ],
    }


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
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `candidates_csv`: `{summary['artifacts']['candidates_csv']}`",
        "",
        "## Candidates",
        "",
        "| Candidate | Relevance | Direct URDF | Authority | Provenance | Path |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not summary["candidates"]:
        lines.append("| none | none | false | missing | unknown | n/a |")
    else:
        for candidate in summary["candidates"]:
            lines.append(
                "| `{candidate_id}` | `{relevance}` | `{direct}` | `{authority}` | `{provenance}` | `{path}` |".format(
                    candidate_id=candidate["candidate_id"],
                    relevance=candidate["likely_so101_relevance"],
                    direct=str(candidate["direct_robot_kinematics_compatible"]).lower(),
                    authority=candidate["source_authority_status"],
                    provenance=candidate["provenance_status"],
                    path=candidate["path"].replace("|", "/"),
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
                )
            )
        root_record["candidate_count"] = root_candidate_count

    candidates.sort(key=lambda candidate: candidate["path"])

    summary_path = output_dir / "so101_model_source_inventory_summary.json"
    csv_path = output_dir / "so101_model_source_candidates.csv"
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "candidates_csv": str(csv_path),
        "readme_md": str(readme_path),
    }
    summary = build_summary(root_records, candidates, artifacts)

    write_json(summary_path, summary)
    write_csv(csv_path, candidates)
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
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
