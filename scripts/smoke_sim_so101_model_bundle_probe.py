#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = "lerobot.sim.so101_model_bundle_probe.v1"
CANDIDATE_SCHEMA = "lerobot.sim.so101_model_bundle_candidate.v1"
REVIEW_PACKET_SCHEMA = "lerobot.sim.so101_model_bundle_review_packet.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_bundle_probe"
REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_contract.py"
MANIFEST_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_manifest.py"
EXPECTED_TARGET_FRAME = "gripper_frame_link"
SOURCE_SAMPLE_BYTES = 256_000
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
ONSHAPE_URL_PATTERN = re.compile(r"https://cad\.onshape\.com/[^\s\"'<>]+")
LICENSE_FILENAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.md",
    "NOTICE",
    "NOTICE.md",
)
EXPECTED_SO101_JOINTS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS = (
    "model_identity",
    "provenance",
    "license",
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
)

CSV_FIELDNAMES = (
    "requirement_id",
    "category",
    "status",
    "severity",
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
    "observed_evidence",
    "review_action",
    "caveat",
)


def next_required_action_ids(actions: Any) -> list[str]:
    if not isinstance(actions, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_id = action.get("action_id")
        if not isinstance(action_id, str) or not action_id or action_id in seen:
            continue
        seen.add(action_id)
        result.append(action_id)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a hardware-free SO-101 model bundle manifest draft from a candidate "
            "URDF/MJCF path plus optional mesh asset roots, then run the existing contract "
            "and bundle-manifest diagnostics against that draft."
        )
    )
    parser.add_argument("--model-path", type=Path, default=None)
    parser.add_argument(
        "--asset-root",
        type=Path,
        action="append",
        default=[],
        help="Additional mesh/asset root for the candidate bundle. Repeatable.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-frame", default=EXPECTED_TARGET_FRAME)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used for child contract/manifest tooling.",
    )
    parser.add_argument(
        "--authority-reviewed-by",
        default=None,
        help=(
            "Optional reviewed-by identifier. Authority is populated only with a stable "
            "review artifact handle supplied by --authority-review-id or --authority-review-url."
        ),
    )
    parser.add_argument(
        "--authority-reviewed-at",
        default=None,
        help=(
            "Optional deterministic review date/string. A date alone does not satisfy "
            "review authority; also supply --authority-review-id or --authority-review-url."
        ),
    )
    parser.add_argument(
        "--authority-review-id",
        default=None,
        help="Optional review ticket, commit, checklist, or artifact identifier for source authority.",
    )
    parser.add_argument(
        "--authority-review-url",
        default=None,
        help="Optional URL to the reviewed source-authority record.",
    )
    parser.add_argument(
        "--authority-review-scope",
        action="append",
        default=[],
        choices=AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS,
        help=(
            "Repeatable source-authority review scope for the top-level authority "
            f"block. Required values: {', '.join(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS)}."
        ),
    )
    parser.add_argument("--provenance-source-url", default=None)
    parser.add_argument("--provenance-source-commit", default=None)
    parser.add_argument("--provenance-export-tool", default=None)
    parser.add_argument("--provenance-license", default=None)
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


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


def executable_arg(path: Path) -> str:
    raw = str(path)
    if path.is_absolute() or "/" in raw:
        return str(normalize_path(path))
    return raw


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


def write_review_packet_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_PACKET_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: csv_value(row.get(field)) for field in REVIEW_PACKET_FIELDNAMES}
            )


def sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except Exception:
        return None
    return digest.hexdigest()


def read_text_sample(path: Path, max_bytes: int = SOURCE_SAMPLE_BYTES) -> tuple[str, str | None]:
    try:
        data = path.read_bytes()[:max(0, max_bytes)]
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    return data.decode("utf-8", errors="replace"), None


def nearest_license_file(path: Path) -> dict[str, Any]:
    if path is None:
        return {"status": "not_checked", "path": None, "checked_directories": []}
    start = path.parent if path.is_file() else path
    checked: list[str] = []
    current = start
    for _ in range(8):
        checked.append(str(current))
        for file_name in LICENSE_FILENAMES:
            candidate = current / file_name
            if candidate.is_file():
                return {
                    "status": "license_file_detected",
                    "path": str(candidate),
                    "file_name": file_name,
                    "checked_directories": checked,
                }
        if current.parent == current:
            break
        current = current.parent
    return {"status": "license_file_not_found", "path": None, "checked_directories": checked}


def run_child(command: list[str], summary_path: Path) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    base: dict[str, Any] = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "summary_json": str(summary_path),
    }
    if result.returncode != 0:
        return {
            **base,
            "ok": False,
            "status": "child_failed",
            "diagnostics": [
                {
                    "diagnostic": "child_nonzero",
                    "severity": "action_required",
                    "returncode": result.returncode,
                }
            ],
        }
    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        return {
            **base,
            "ok": False,
            "status": "child_summary_unavailable",
            "diagnostics": [
                {
                    "diagnostic": "child_summary_unavailable",
                    "severity": "action_required",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            ],
        }
    if not isinstance(summary, dict):
        return {
            **base,
            "ok": False,
            "status": "child_summary_not_object",
            "diagnostics": [
                {
                    "diagnostic": "child_summary_not_object",
                    "severity": "action_required",
                }
            ],
        }
    return {**base, "ok": bool(summary.get("ok")), "status": summary.get("status"), "summary": summary}


def run_contract_checker(
    python_path: Path,
    output_dir: Path,
    model_path: Path | None,
    asset_roots: list[Path],
    target_frame: str,
) -> dict[str, Any]:
    contract_dir = output_dir / "so101_model_contract"
    summary_path = contract_dir / "so101_model_contract_summary.json"
    command = [
        executable_arg(python_path),
        str(CONTRACT_CHECKER_PATH),
        "--output-dir",
        str(contract_dir),
        "--target-frame",
        target_frame,
    ]
    if model_path is not None:
        command.extend(["--model-path", str(model_path)])
    for asset_root in asset_roots:
        command.extend(["--model-asset-root", str(asset_root)])
    result = run_child(command, summary_path)
    result["artifacts"] = {
        "summary_json": str(summary_path),
        "checklist_csv": str(contract_dir / "so101_model_contract_checklist.csv"),
        "readme_md": str(contract_dir / "README.md"),
    }
    summary = result.get("summary") or {}
    asset_preflight = summary.get("model_asset_preflight") or {}
    result["diagnostic_excerpt"] = {
        "status": summary.get("status", result.get("status")),
        "model_request_status": (summary.get("model_request") or {}).get("status"),
        "robot_kinematics_status": (summary.get("robot_kinematics_path") or {}).get("status"),
        "robot_kinematics_initialization_status": (summary.get("robot_kinematics_initialization") or {}).get("status"),
        "model_asset_preflight": {
            "status": asset_preflight.get("status"),
            "asset_roots": asset_preflight.get("asset_roots"),
            "mesh_reference_count": asset_preflight.get("mesh_reference_count"),
            "present_asset_count": asset_preflight.get("present_asset_count"),
            "missing_asset_count": asset_preflight.get("missing_asset_count"),
            "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
            "diagnostics": asset_preflight.get("diagnostics", []),
            "limitations": asset_preflight.get("limitations", []),
            "artifacts": asset_preflight.get("artifacts"),
        },
        "artifacts": result["artifacts"],
    }
    return result


def run_manifest_checker(
    python_path: Path,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest_dir = output_dir / "so101_model_bundle_manifest_check"
    summary_path = manifest_dir / "so101_model_bundle_manifest_summary.json"
    command = [
        executable_arg(python_path),
        str(MANIFEST_CHECKER_PATH),
        "--output-dir",
        str(manifest_dir),
        "--manifest-path",
        str(manifest_path),
    ]
    result = run_child(command, summary_path)
    result["artifacts"] = {
        "summary_json": str(summary_path),
        "checklist_csv": str(manifest_dir / "so101_model_bundle_manifest_checklist.csv"),
        "readme_md": str(manifest_dir / "README.md"),
    }
    summary = result.get("summary") or {}
    contract = summary.get("contract_checker") or {}
    asset_preflight = contract.get("model_asset_preflight") or {}
    result["diagnostic_excerpt"] = {
        "status": summary.get("status", result.get("status")),
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
        "missing_inputs": summary.get("missing_inputs", []),
        "next_required_for_goal": summary.get("next_required_for_goal", []),
        "next_required_action_ids": next_required_action_ids(summary.get("next_required_for_goal")),
        "model_path": summary.get("model_path"),
        "asset_roots": summary.get("asset_roots"),
        "target_frame": summary.get("target_frame"),
        "tcp_offset": summary.get("tcp_offset"),
        "base_to_board_alignment": summary.get("base_to_board_alignment"),
        "contract_status": contract.get("status"),
        "asset_preflight_status": asset_preflight.get("status"),
        "asset_preflight_missing_asset_count": asset_preflight.get("missing_asset_count"),
        "asset_preflight_unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
        "artifacts": result["artifacts"],
    }
    return result


def build_model_request(model_path: Path | None) -> dict[str, Any]:
    if model_path is None:
        return {
            "status": "model_not_supplied",
            "path": None,
            "exists": False,
            "diagnostics": [
                {
                    "diagnostic": "candidate_model_path_missing",
                    "severity": "action_required",
                    "reason": "Supply --model-path to probe a concrete URDF/MJCF/Xacro/XML candidate.",
                }
            ],
        }
    exists = model_path.exists()
    return {
        "status": "model_supplied" if exists else "model_unavailable",
        "path": str(model_path),
        "exists": exists,
        "suffix": model_path.suffix.lower(),
        "diagnostics": []
        if exists
        else [
            {
                "diagnostic": "candidate_model_path_unavailable",
                "severity": "action_required",
                "reason": f"Model path does not exist: {model_path}",
            }
        ],
    }


def inspect_asset_roots(asset_roots: list[Path]) -> dict[str, Any]:
    checks = [
        {
            "path": str(root),
            "exists": root.exists(),
            "is_dir": root.is_dir(),
        }
        for root in asset_roots
    ]
    diagnostics: list[dict[str, Any]] = []
    for check in checks:
        if not check["exists"]:
            diagnostics.append(
                {
                    "diagnostic": "candidate_asset_root_unavailable",
                    "severity": "action_required",
                    "path": check["path"],
                }
            )
        elif not check["is_dir"]:
            diagnostics.append(
                {
                    "diagnostic": "candidate_asset_root_not_directory",
                    "severity": "action_required",
                    "path": check["path"],
                }
            )
    return {
        "asset_roots": [str(root) for root in asset_roots],
        "asset_root_count": len(asset_roots),
        "asset_root_checks": checks,
        "diagnostics": diagnostics,
        "notes": (
            "An explicit empty asset_roots list is allowed when the model directory alone resolves meshes. "
            "Non-empty roots are forwarded to the contract checker asset preflight."
        ),
    }


def observed_source_hints_from_model(model_path: Path | None) -> dict[str, Any]:
    if model_path is None:
        return {
            "status": "model_not_supplied",
            "model_path": None,
            "exists": False,
            "diagnostics": ["model_path_missing"],
            "review_required": True,
            "notes": (
                "Source hints are review evidence only. They do not populate the "
                "reviewed provenance manifest field."
            ),
        }

    exists = model_path.exists()
    digest = sha256_file(model_path) if exists else None
    sample_text, sample_error = read_text_sample(model_path) if exists else ("", "model_path_unavailable")
    urls = sorted(set(URL_PATTERN.findall(sample_text)))
    onshape_urls = sorted(set(ONSHAPE_URL_PATTERN.findall(sample_text)))
    export_tool_hints = []
    lowered = sample_text.lower()
    if "onshape-to-robot" in lowered:
        export_tool_hints.append("onshape-to-robot")
    license_info = nearest_license_file(model_path) if exists else {
        "status": "not_checked",
        "path": None,
        "checked_directories": [],
    }

    diagnostics: list[str] = []
    if sample_error:
        diagnostics.append(f"source_sample_unavailable:{sample_error}")
    if not onshape_urls and not export_tool_hints:
        diagnostics.append("cad_export_source_not_observed")
    if license_info.get("status") != "license_file_detected":
        diagnostics.append("nearby_license_file_not_observed")

    if onshape_urls or export_tool_hints:
        status = "source_reference_detected"
    elif license_info.get("status") == "license_file_detected":
        status = "license_context_detected"
    elif digest:
        status = "model_fingerprint_only"
    else:
        status = "source_hints_unavailable"

    return {
        "status": status,
        "model_path": str(model_path),
        "exists": exists,
        "file_size_bytes": model_path.stat().st_size if exists else None,
        "sha256": digest,
        "sample_bytes": SOURCE_SAMPLE_BYTES,
        "urls": urls,
        "onshape_urls": onshape_urls,
        "export_tool_hints": export_tool_hints,
        "license": license_info,
        "diagnostics": diagnostics,
        "review_required": True,
        "notes": (
            "Detected source URLs, export tools, license files, and file fingerprints "
            "are provenance review aids only. They do not populate the manifest "
            "provenance object or create source authority."
        ),
    }


def observed_joint_limits_from_contract(contract_result: dict[str, Any]) -> dict[str, Any]:
    summary = contract_result.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    structure = summary.get("model_structure_inspection")
    structure = structure if isinstance(structure, dict) else {}
    raw_joints = structure.get("joints")
    raw_joints = raw_joints if isinstance(raw_joints, list) else []

    values: dict[str, list[float]] = {}
    diagnostics: list[str] = []
    for item in raw_joints:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        limits = item.get("limits_deg")
        if name not in EXPECTED_SO101_JOINTS or name in values:
            continue
        if isinstance(limits, list) and len(limits) == 2:
            try:
                values[str(name)] = [float(limits[0]), float(limits[1])]
            except (TypeError, ValueError):
                diagnostics.append(f"joint_limit_non_numeric:{name}")

    missing_joints = [joint for joint in EXPECTED_SO101_JOINTS if joint not in values]
    diagnostics.extend(f"joint_limit_not_observed:{joint}" for joint in missing_joints)
    return {
        "status": "observed_unreviewed_limits_complete"
        if not missing_joints
        else "observed_unreviewed_limits_incomplete",
        "source": "contract_checker.model_structure_inspection.joints",
        "values_deg": values,
        "expected_joints": list(EXPECTED_SO101_JOINTS),
        "missing_joints": missing_joints,
        "complete": not missing_joints,
        "diagnostics": diagnostics,
        "notes": (
            "Observed model limits are review evidence only. They are not copied into "
            "joint_limits_deg and do not create reviewed joint-limit authority."
        ),
    }


def _unique_asset_references(rows: list[Any]) -> list[str]:
    seen: set[str] = set()
    references: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        reference = row.get("normalized_reference") or row.get("raw_reference")
        if not isinstance(reference, str) or not reference:
            continue
        if reference in seen:
            continue
        seen.add(reference)
        references.append(reference)
    return references


def mesh_asset_review_from_contract(contract_result: dict[str, Any]) -> dict[str, Any]:
    summary = contract_result.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    preflight = summary.get("model_asset_preflight")
    preflight = preflight if isinstance(preflight, dict) else {}
    missing_assets = preflight.get("missing_assets")
    missing_assets = missing_assets if isinstance(missing_assets, list) else []
    unresolved_references = preflight.get("unresolved_references")
    unresolved_references = unresolved_references if isinstance(unresolved_references, list) else []
    missing_references = _unique_asset_references(missing_assets)
    unresolved_reference_values = _unique_asset_references(unresolved_references)

    if missing_references:
        status = "missing_mesh_assets_detected"
    elif unresolved_reference_values:
        status = "unresolved_mesh_references_detected"
    elif preflight.get("mesh_reference_count"):
        status = "mesh_references_resolved"
    else:
        status = "mesh_references_not_observed"

    return {
        "status": status,
        "source": "contract_checker.model_asset_preflight",
        "asset_roots": preflight.get("asset_roots") or [],
        "mesh_reference_count": preflight.get("mesh_reference_count"),
        "present_asset_count": preflight.get("present_asset_count"),
        "missing_asset_count": preflight.get("missing_asset_count"),
        "unresolved_reference_count": preflight.get("unresolved_reference_count"),
        "unique_missing_reference_count": len(missing_references),
        "missing_references": missing_references,
        "unique_unresolved_reference_count": len(unresolved_reference_values),
        "unresolved_references": unresolved_reference_values,
        "artifacts": preflight.get("artifacts"),
        "notes": (
            "Missing mesh references are review evidence for selecting asset roots. "
            "They do not prove reviewed geometry, collision policy, or model authority."
        ),
    }


def build_authority(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    supplied_review_scope_ids = normalized_review_scope_ids(args.authority_review_scope)
    missing_review_scope_ids = [
        scope_id
        for scope_id in AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS
        if scope_id not in supplied_review_scope_ids
    ]
    supplied = {
        "reviewed_by": args.authority_reviewed_by,
        "reviewed_at": args.authority_reviewed_at,
        "review_id": args.authority_review_id,
        "review_url": args.authority_review_url,
        "review_scopes": supplied_review_scope_ids,
    }
    supplied_review_fields = {
        key: value
        for key, value in supplied.items()
        if key != "review_scopes" and non_empty(value)
    }
    placeholder_fields = sorted(
        key
        for key, value in supplied_review_fields.items()
        if placeholder_review_evidence(value)
    )
    invalid_fields = sorted(
        key
        for key, value in supplied_review_fields.items()
        if key not in placeholder_fields
        and (
            (key == "review_url" and invalid_review_url(value))
            or (key == "reviewed_at" and invalid_reviewed_at(value))
        )
    )
    valid_review_fields = {
        key: value
        for key, value in supplied_review_fields.items()
        if key not in placeholder_fields and key not in invalid_fields
    }
    missing = []
    if "reviewed_by" not in valid_review_fields:
        missing.append("reviewed_by")
    if "review_id" not in valid_review_fields and "review_url" not in valid_review_fields:
        missing.append("review_id_or_review_url")
    missing.extend(f"review_scope:{scope_id}" for scope_id in missing_review_scope_ids)
    if missing or placeholder_fields:
        return {}, {
            "status": "TODO_authority_review_required",
            "required_fields": [
                "reviewed_by",
                "review_id_or_review_url",
                *[f"review_scope:{scope_id}" for scope_id in AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS],
            ],
            "optional_fields": ["reviewed_at"],
            "missing_fields": missing,
            "placeholder_fields": placeholder_fields,
            "invalid_fields": invalid_fields,
            "supplied_fields": {key: value for key, value in supplied.items() if value},
            "required_review_scope_ids": list(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
            "supplied_review_scope_ids": supplied_review_scope_ids,
            "missing_review_scope_ids": missing_review_scope_ids,
            "review_scope_ready": not missing_review_scope_ids,
            "reason": (
                "The probe never infers reviewed model authority from a path or asset root; "
                "reviewed authority needs reviewer identity, review_id or review_url, "
                "explicit model_identity/provenance/license review scopes, and no "
                "placeholder review evidence."
            ),
        }
    if invalid_fields and "review_id" not in valid_review_fields:
        return {}, {
            "status": "TODO_authority_review_required",
            "required_fields": [
                "reviewed_by",
                "review_id_or_review_url",
                *[f"review_scope:{scope_id}" for scope_id in AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS],
            ],
            "optional_fields": ["reviewed_at"],
            "missing_fields": ["review_id_or_valid_review_url"],
            "placeholder_fields": placeholder_fields,
            "invalid_fields": invalid_fields,
            "supplied_fields": {key: value for key, value in supplied.items() if value},
            "required_review_scope_ids": list(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
            "supplied_review_scope_ids": supplied_review_scope_ids,
            "missing_review_scope_ids": missing_review_scope_ids,
            "review_scope_ready": not missing_review_scope_ids,
            "reason": (
                "review_url must be an http(s) URL; use review_id for ticket IDs, "
                "commit IDs, or other non-URL artifact handles."
            ),
        }
    if invalid_fields:
        return {}, {
            "status": "TODO_authority_review_required",
            "required_fields": [
                "reviewed_by",
                "review_id_or_review_url",
                *[f"review_scope:{scope_id}" for scope_id in AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS],
            ],
            "optional_fields": ["reviewed_at"],
            "missing_fields": [],
            "placeholder_fields": placeholder_fields,
            "invalid_fields": invalid_fields,
            "supplied_fields": {key: value for key, value in supplied.items() if value},
            "required_review_scope_ids": list(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
            "supplied_review_scope_ids": supplied_review_scope_ids,
            "missing_review_scope_ids": missing_review_scope_ids,
            "review_scope_ready": not missing_review_scope_ids,
            "reason": "Remove or fix invalid reviewed_at/review_url before recording authority.",
        }
    authority = {
        "source_authority_status": "operator_reviewed",
        "reviewed_by": valid_review_fields["reviewed_by"],
        "review_scopes": supplied_review_scope_ids,
    }
    if "reviewed_at" in valid_review_fields:
        authority["reviewed_at"] = valid_review_fields["reviewed_at"]
    if "review_id" in valid_review_fields:
        authority["review_id"] = valid_review_fields["review_id"]
    if "review_url" in valid_review_fields:
        authority["review_url"] = valid_review_fields["review_url"]
    return authority, {
        "status": "operator_supplied",
        "required_fields": [
            "reviewed_by",
            "review_id_or_review_url",
            *[f"review_scope:{scope_id}" for scope_id in AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS],
        ],
        "optional_fields": ["reviewed_at"],
        "missing_fields": [],
        "placeholder_fields": [],
        "invalid_fields": [],
        "required_review_scope_ids": list(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
        "supplied_review_scope_ids": supplied_review_scope_ids,
        "missing_review_scope_ids": [],
        "review_scope_ready": True,
    }


def build_provenance(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    required = {
        "source_url": args.provenance_source_url,
        "export_tool": args.provenance_export_tool,
        "license": args.provenance_license,
    }
    optional = {"source_commit": args.provenance_source_commit}
    supplied_required = {key: value for key, value in required.items() if non_empty(value)}
    supplied_optional = {key: value for key, value in optional.items() if non_empty(value)}
    placeholder_fields = sorted(
        [
            key
            for key, value in {
                **supplied_required,
                **supplied_optional,
            }.items()
            if placeholder_review_evidence(value)
        ]
    )
    valid_required = {
        key: value for key, value in supplied_required.items() if key not in placeholder_fields
    }
    valid_optional = {
        key: value for key, value in supplied_optional.items() if key not in placeholder_fields
    }
    missing = [key for key in required if key not in valid_required]
    if missing or placeholder_fields:
        supplied = {**supplied_required, **supplied_optional}
        return {}, {
            "status": "TODO_provenance_review_required",
            "required_fields": sorted(required),
            "optional_fields": ["source_commit"],
            "missing_fields": missing,
            "placeholder_fields": placeholder_fields,
            "supplied_fields": supplied,
            "reason": (
                "The probe records source provenance only when deterministic, "
                "non-placeholder provenance inputs are supplied."
            ),
        }
    provenance = {
        "source_url": valid_required["source_url"],
        "export_tool": valid_required["export_tool"],
        "license": valid_required["license"],
    }
    if "source_commit" in valid_optional:
        provenance["source_commit"] = valid_optional["source_commit"]
    return provenance, {
        "status": "operator_supplied",
        "required_fields": sorted(required),
        "optional_fields": ["source_commit"],
        "missing_fields": [],
        "placeholder_fields": [],
    }


def build_candidate_manifest(
    *,
    model_request: dict[str, Any],
    asset_root_config: dict[str, Any],
    target_frame: str,
    authority: dict[str, Any],
    authority_placeholder: dict[str, Any],
    provenance: dict[str, Any],
    provenance_placeholder: dict[str, Any],
    observed_source_hints: dict[str, Any],
    contract_result: dict[str, Any],
    observed_joint_limits: dict[str, Any],
    mesh_asset_review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": CANDIDATE_SCHEMA,
        "generated_by": "scripts/smoke_sim_so101_model_bundle_probe.py",
        "review_state": "draft_candidate_not_ready_for_model_backed_ik",
        "model_path": model_request["path"] or "",
        "model_path_placeholder": {
            "status": "TODO_model_path_required" if model_request["path"] is None else model_request["status"],
            "reason": "Set model_path to the reviewed SO-101 URDF/MJCF/Xacro/XML candidate.",
        },
        "asset_roots": asset_root_config["asset_roots"],
        "authority": authority,
        "authority_placeholder": authority_placeholder,
        "provenance": provenance,
        "provenance_placeholder": provenance_placeholder,
        "observed_source_hints_from_model": observed_source_hints,
        "target_frame": target_frame,
        "target_frame_authority_placeholder": {
            "status": "TODO_reviewed_target_frame_authority_required",
            "accepted_manifest_fields": [
                "target_frame_authority",
                "target_frame_review",
                "tcp_frame_authority",
                "target_frame_metadata",
            ],
            "required_review_scope_ids": ["target_frame"],
            "reason": "The probe records the requested target frame for diagnostics but cannot infer reviewed TCP-frame authority.",
        },
        "joint_limits_placeholder": {
            "status": "TODO_reviewed_joint_limits_required",
            "accepted_manifest_fields": ["joint_limits_deg", "joint_limits", "joint_limit_authority"],
            "required_joints": [
                "shoulder_pan",
                "shoulder_lift",
                "elbow_flex",
                "wrist_flex",
                "wrist_roll",
                "gripper",
            ],
            "required_review_scope_ids": ["joint_limits"],
            "reason": "The probe cannot infer reviewed joint-limit authority from model existence alone.",
        },
        "gripper_mapping_authority_placeholder": {
            "status": "TODO_reviewed_gripper_mapping_authority_required",
            "accepted_manifest_fields": [
                "gripper_mapping_authority",
                "gripper_mapping_review",
                "gripper_linear_joint_mapping_review",
                "gripper_mapping_metadata",
            ],
            "required_review_scope_ids": ["gripper_mapping"],
            "reason": "The probe cannot resolve the SO-ARM100 gripper linear-joint mapping caveat from model existence alone.",
        },
        "observed_joint_limits_deg_from_model": observed_joint_limits,
        "observed_mesh_asset_references_from_model": mesh_asset_review,
        "collision_policy_authority_placeholder": {
            "status": "TODO_reviewed_collision_policy_authority_required",
            "accepted_manifest_fields": [
                "collision_policy_authority",
                "collision_policy_review",
                "base_collision_mesh_policy_review",
                "collision_policy_metadata",
            ],
            "required_review_scope_ids": ["collision_policy"],
            "reason": "The probe cannot resolve removed base collision meshes or collision policy from model existence alone.",
        },
        "tcp_offset_placeholder": {
            "status": "TODO_calibrated_target_frame_to_tcp_offset_required",
            "accepted_manifest_fields": [
                "tcp_offset_m",
                "gripper_tip_offset_m",
                "target_frame_to_tcp_m",
                "tool_center_point_offset_m",
            ],
            "required_shape": {"x": "meters", "y": "meters", "z": "meters"},
            "required_review_scope_ids": ["tcp_offset"],
            "reason": "The probe cannot infer gripper contact TCP from the model alone.",
        },
        "base_to_board_alignment_placeholder": {
            "status": "TODO_calibrated_base_to_board_transform_required",
            "accepted_manifest_fields": ["base_to_board_transform", "base_to_board_alignment"],
            "required_review_scope_ids": ["base_to_board_alignment"],
            "reason": "Future model-backed IK residuals need the simulator base frame aligned to the chess board frame.",
        },
        "probe_child_diagnostics": {
            "model_request": model_request,
            "asset_roots": asset_root_config,
            "contract_checker": contract_result["diagnostic_excerpt"],
        },
        "notes": [
            "This candidate manifest is a review draft. It should stay diagnostic-only until authority, provenance, target-frame authority, joint limits, gripper mapping, collision policy, TCP, and base-to-board fields are replaced with reviewed values and field-specific review scopes.",
            "The probe does not copy, ingest, or modify model/mesh assets.",
            "Extra probe_child_diagnostics fields are for operator review; the bundle manifest checker derives readiness from the declared manifest fields.",
            "Populate target_frame_authority or an equivalent target-frame review field with review_scope target_frame before expecting ready_for_model_backed_ik.",
            "Populate joint_limits_deg or an equivalent joint-limit authority field with review_scope joint_limits before expecting ready_for_model_backed_ik.",
            "Populate gripper_mapping_authority or an equivalent gripper mapping review field with review_scope gripper_mapping before expecting ready_for_model_backed_ik.",
            "Populate collision_policy_authority or an equivalent collision policy review field with review_scope collision_policy before expecting ready_for_model_backed_ik.",
            "observed_source_hints_from_model is raw candidate evidence for review only; copy source URL/export/license fields into provenance only after separate authority review.",
            "observed_joint_limits_deg_from_model is raw candidate evidence for review only; copy it into joint_limits_deg only after separate authority review.",
            "observed_mesh_asset_references_from_model is raw candidate evidence for review only; supply reviewed asset roots before expecting mesh readiness.",
        ],
    }


def row(
    requirement_id: str,
    category: str,
    status: str,
    severity: str,
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
        "observed_value": observed_value,
        "expected_value": expected_value,
        "missing_inputs": missing_inputs,
        "diagnostics": diagnostics,
        "notes": notes,
    }


def build_rows(
    *,
    model_request: dict[str, Any],
    asset_root_config: dict[str, Any],
    authority: dict[str, Any],
    authority_placeholder: dict[str, Any],
    provenance: dict[str, Any],
    provenance_placeholder: dict[str, Any],
    observed_source_hints: dict[str, Any],
    contract_result: dict[str, Any],
    manifest_result: dict[str, Any],
    observed_joint_limits: dict[str, Any],
    mesh_asset_review: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    missing_inputs = manifest_excerpt.get("missing_inputs") or []
    contract_excerpt = contract_result["diagnostic_excerpt"]
    asset_preflight = contract_excerpt.get("model_asset_preflight") or {}
    return [
        row(
            "candidate_model_path",
            "model_path",
            "ok" if model_request["status"] == "model_supplied" else "action_required",
            "warning",
            model_request,
            {"exists": True},
            None if model_request["status"] == "model_supplied" else ["--model-path"],
            model_request.get("diagnostics", []),
            "Missing or unavailable model paths are diagnostic-only and still produce a manifest draft.",
        ),
        row(
            "candidate_asset_roots",
            "mesh_assets",
            "ok" if not asset_root_config["diagnostics"] else "action_required",
            "warning",
            asset_root_config,
            {"all_supplied_roots_exist": True, "all_supplied_roots_are_directories": True},
            None if not asset_root_config["diagnostics"] else ["--asset-root"],
            asset_root_config["diagnostics"],
            "Repeat --asset-root for separate mesh directories; an empty list is explicit and valid.",
        ),
        row(
            "observed_candidate_mesh_references",
            "mesh_assets",
            "ok" if not mesh_asset_review.get("missing_references") else "action_required",
            "info",
            mesh_asset_review,
            {"missing_references": [], "unresolved_references": []},
            None
            if not mesh_asset_review.get("missing_references")
            and not mesh_asset_review.get("unresolved_references")
            else ["mesh_assets"],
            mesh_asset_review.get("missing_references")
            or mesh_asset_review.get("unresolved_references")
            or [],
            "Raw mesh references help choose reviewed asset roots; they do not satisfy mesh readiness.",
        ),
        row(
            "authority",
            "authority",
            "ok" if authority else "action_required",
            "warning",
            authority or authority_placeholder,
            {"authority": "non-empty reviewed authority object"},
            None if authority else ["authority"],
            [] if authority else [authority_placeholder],
            "Defaults to an empty authority object so placeholders are not treated as reviewed authority.",
        ),
        row(
            "provenance",
            "provenance",
            "ok" if provenance else "action_required",
            "warning",
            provenance or provenance_placeholder,
            {"provenance": "non-empty reviewed provenance object"},
            None if provenance else ["provenance"],
            [] if provenance else [provenance_placeholder],
            "Defaults to an empty provenance object so placeholders are not treated as reviewed provenance.",
        ),
        row(
            "observed_candidate_source_hints",
            "provenance",
            "ok"
            if observed_source_hints.get("status")
            in {"source_reference_detected", "license_context_detected", "model_fingerprint_only"}
            else "action_required",
            "info",
            observed_source_hints,
            {"reviewed_manifest_field_still_required": "provenance"},
            None
            if observed_source_hints.get("status")
            in {"source_reference_detected", "license_context_detected", "model_fingerprint_only"}
            else ["source_provenance_hints"],
            observed_source_hints.get("diagnostics", []),
            "Raw source hints help review; they do not satisfy reviewed provenance.",
        ),
        row(
            "target_frame_authority",
            "tcp_frame",
            "action_required",
            "warning",
            {"target_frame": manifest_excerpt.get("target_frame"), "target_frame_authority_placeholder": True},
            {"reviewed_target_frame_authority": True},
            ["target_frame_authority"],
            ["target_frame_authority_placeholder_declared_without_reviewed_authority"],
            "The probe records target_frame for diagnostics but cannot prove reviewed TCP-frame authority.",
        ),
        row(
            "tcp_offset_m",
            "tcp_frame",
            "action_required",
            "warning",
            {"tcp_offset_placeholder": True},
            {"x": "meters", "y": "meters", "z": "meters"},
            ["tcp_offset_m"],
            ["tcp_offset_placeholder_declared_without_calibrated_vector"],
            "The probe intentionally does not invent TCP/gripper-tip offsets.",
        ),
        row(
            "joint_limits_deg",
            "joint_contract",
            "action_required",
            "warning",
            {"joint_limits_placeholder": True},
            {"required_joints": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]},
            ["joint_limits_deg"],
            ["joint_limits_placeholder_declared_without_reviewed_limits"],
            "The probe intentionally does not invent reviewed joint-limit authority.",
        ),
        row(
            "observed_candidate_joint_limits",
            "joint_contract",
            "ok" if observed_joint_limits.get("complete") else "action_required",
            "info",
            observed_joint_limits,
            {
                "complete_raw_candidate_limits": True,
                "reviewed_manifest_field_still_required": "joint_limits_deg",
            },
            None
            if observed_joint_limits.get("complete")
            else ["observed_candidate_joint_limits"],
            observed_joint_limits.get("diagnostics", []),
            "Raw observed limits help review; they do not satisfy reviewed joint-limit authority.",
        ),
        row(
            "gripper_mapping_authority",
            "joint_contract",
            "action_required",
            "warning",
            {"gripper_mapping_authority_placeholder": True},
            {"reviewed_gripper_mapping_authority": True},
            ["gripper_mapping_authority"],
            ["gripper_mapping_placeholder_declared_without_reviewed_mapping"],
            "The generated placeholder keeps model-backed IK disabled until the gripper linear-joint mapping caveat is reviewed.",
        ),
        row(
            "collision_policy_authority",
            "mesh_assets",
            "action_required",
            "warning",
            {"collision_policy_authority_placeholder": True},
            {"reviewed_collision_policy_authority": True},
            ["collision_policy_authority"],
            ["collision_policy_placeholder_declared_without_reviewed_policy"],
            "The generated placeholder keeps model-backed IK disabled until the collision policy and removed-base-collision caveat are reviewed.",
        ),
        row(
            "base_to_board_transform",
            "alignment",
            "action_required",
            "warning",
            {"base_to_board_alignment_placeholder": True},
            {"calibrated_base_to_board_transform": True},
            ["base_to_board_transform"],
            ["alignment_placeholder_declared_without_transform"],
            "The generated placeholder keeps model-backed IK disabled until calibration is reviewed.",
        ),
        row(
            "child_contract_checker",
            "child_diagnostics",
            "ok"
            if contract_excerpt.get("status")
            in {"model_contract_checked", "model_contract_needs_follow_up"}
            and asset_preflight.get("missing_asset_count") in {0, None}
            and asset_preflight.get("unresolved_reference_count") in {0, None}
            else "action_required",
            "warning",
            contract_excerpt,
            {"missing_asset_count": 0, "unresolved_reference_count": 0},
            None
            if contract_excerpt.get("status") in {"model_contract_checked", "model_contract_needs_follow_up"}
            else ["non_blocking_contract_checker_result"],
            contract_result.get("diagnostics", []),
            "This reuses the existing SO-101 model contract checker and nested asset preflight.",
        ),
        row(
            "bundle_manifest_checker",
            "readiness",
            "ok" if manifest_excerpt.get("ready_for_model_backed_ik") else "action_required",
            "warning",
            manifest_excerpt,
            {"ready_for_model_backed_ik": True},
            None if manifest_excerpt.get("ready_for_model_backed_ik") else missing_inputs,
            [] if manifest_excerpt.get("ready_for_model_backed_ik") else ["candidate_manifest_not_ready"],
            "This is the same readiness gate used by the integrated simulator regression suite.",
        ),
    ]


def review_packet_row(
    priority: int,
    review_item_id: str,
    gate: str,
    status: str,
    manifest_fields: list[str],
    observed_evidence: dict[str, Any],
    review_action: str,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "review_item_id": review_item_id,
        "gate": gate,
        "status": status,
        "manifest_fields": manifest_fields,
        "observed_evidence": observed_evidence,
        "review_action": review_action,
        "caveat": (
            "Review-packet evidence is operator intake only; copying values into the "
            "manifest requires separate reviewed authority and does not happen here."
        ),
    }


def build_review_packet(
    *,
    model_request: dict[str, Any],
    asset_root_config: dict[str, Any],
    candidate_manifest_path: Path,
    observed_source_hints: dict[str, Any],
    observed_joint_limits: dict[str, Any],
    mesh_asset_review: dict[str, Any],
    manifest_result: dict[str, Any],
    contract_result: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    contract_excerpt = contract_result["diagnostic_excerpt"]
    asset_preflight = contract_excerpt.get("model_asset_preflight") or {}
    missing_inputs = manifest_excerpt.get("missing_inputs")
    missing_inputs = missing_inputs if isinstance(missing_inputs, list) else []
    source_hints_available = observed_source_hints.get("status") in {
        "source_reference_detected",
        "license_context_detected",
        "model_fingerprint_only",
    }
    rows = [
        review_packet_row(
            1,
            "review_model_source_authority",
            "reviewed_model_authority",
            "evidence_available" if model_request.get("status") == "model_supplied" else "needs_candidate_model",
            ["authority"],
            {
                "model_request_status": model_request.get("status"),
                "model_path": model_request.get("path"),
                "sha256": observed_source_hints.get("sha256"),
                "required_review_scope_ids": list(AUTHORITY_REQUIRED_REVIEW_SCOPE_IDS),
            },
            "Choose the authoritative SO-101 model source and record reviewer identity, review_id or review_url, and review scopes: model_identity, provenance, license.",
        ),
        review_packet_row(
            2,
            "review_model_provenance",
            "reviewed_model_authority",
            "evidence_available" if source_hints_available else "needs_source_provenance_review",
            ["provenance"],
            {
                "source_hints_status": observed_source_hints.get("status"),
                "onshape_urls": observed_source_hints.get("onshape_urls"),
                "export_tool_hints": observed_source_hints.get("export_tool_hints"),
                "license": observed_source_hints.get("license"),
            },
            "Review source/export/license evidence before copying provenance into the manifest.",
        ),
        review_packet_row(
            3,
            "resolve_reviewed_mesh_assets",
            "reviewed_model_authority",
            "needs_mesh_assets"
            if not isinstance(mesh_asset_review.get("mesh_reference_count"), int)
            or mesh_asset_review.get("mesh_reference_count") <= 0
            or mesh_asset_review.get("missing_references")
            or mesh_asset_review.get("unresolved_references")
            else "evidence_available",
            ["asset_roots", "mesh_asset_authority"],
            {
                "asset_roots": asset_root_config.get("asset_roots"),
                "mesh_reference_count": mesh_asset_review.get("mesh_reference_count"),
                "missing_references": mesh_asset_review.get("missing_references"),
                "unresolved_references": mesh_asset_review.get("unresolved_references"),
                "asset_preflight_status": asset_preflight.get("status"),
            },
            "Supply reviewed asset roots until mesh preflight has no missing or unresolved references, then record mesh authority with review_scope mesh_assets.",
        ),
        review_packet_row(
            4,
            "review_joint_limits",
            "reviewed_model_authority",
            "evidence_available"
            if observed_joint_limits.get("complete") is True
            else "needs_complete_joint_limit_evidence",
            ["joint_limits_deg", "joint_limit_authority"],
            {
                "observed_joint_limits_status": observed_joint_limits.get("status"),
                "values_deg": observed_joint_limits.get("values_deg"),
                "missing_joints": observed_joint_limits.get("missing_joints"),
            },
            "Review raw candidate limits before declaring reviewed joint_limits_deg and joint-limit authority with review_scope joint_limits.",
        ),
        review_packet_row(
            5,
            "review_gripper_mapping",
            "reviewed_model_authority",
            "needs_gripper_mapping_review",
            ["gripper_mapping_authority"],
            {
                "candidate_manifest": str(candidate_manifest_path),
                "source_caveat": "SO-ARM100 README gripper linear-joint mapping caveat must be resolved in reviewed fields.",
            },
            "Review the SO-101 gripper actuator/linear-joint mapping and record authority with review_scope gripper_mapping.",
        ),
        review_packet_row(
            6,
            "review_collision_policy",
            "reviewed_model_authority",
            "needs_collision_policy_review",
            ["collision_policy_authority"],
            {
                "candidate_manifest": str(candidate_manifest_path),
                "source_caveat": "SO-ARM100 README removed-base-collision caveat must be resolved in reviewed fields.",
                "asset_preflight_status": asset_preflight.get("status"),
            },
            "Review mesh collision policy, including removed base collision meshes, and record authority with review_scope collision_policy.",
        ),
        review_packet_row(
            7,
            "review_target_frame",
            "reviewed_model_authority",
            "needs_reviewed_target_frame_authority",
            ["target_frame", "target_frame_authority"],
            {
                "target_frame": manifest_excerpt.get("target_frame"),
                "contract_status": contract_excerpt.get("status"),
            },
            "Confirm the target frame is the intended SO-101 gripper/TCP frame and record review metadata with review_scope target_frame.",
        ),
        review_packet_row(
            8,
            "calibrate_tcp_offset",
            "reviewed_model_authority",
            "needs_tcp_calibration",
            ["tcp_offset_m", "tcp_offset_authority"],
            {
                "manifest_tcp_offset": manifest_excerpt.get("tcp_offset"),
                "candidate_manifest": str(candidate_manifest_path),
            },
            "Measure or review target-frame-to-TCP/gripper-tip offset and record authority with review_scope tcp_offset.",
        ),
        review_packet_row(
            9,
            "calibrate_base_to_board_alignment",
            "reviewed_model_authority",
            "needs_base_to_board_calibration",
            ["base_to_board_transform", "base_to_board_alignment_authority"],
            {
                "manifest_base_to_board_alignment": manifest_excerpt.get("base_to_board_alignment"),
                "candidate_manifest": str(candidate_manifest_path),
            },
            "Record reviewed base-to-board translation and roll/pitch/yaw alignment for the chess scene with review_scope base_to_board_alignment.",
        ),
        review_packet_row(
            10,
            "clear_model_contract_and_asset_preflight",
            "mujoco_scene_validity",
            "evidence_available"
            if contract_excerpt.get("status")
            in {"model_contract_checked", "model_contract_needs_follow_up"}
            and asset_preflight.get("missing_asset_count") in {0, None}
            and asset_preflight.get("unresolved_reference_count") in {0, None}
            else "needs_contract_or_asset_follow_up",
            ["non_blocking_contract_checker_result"],
            {
                "contract_status": contract_excerpt.get("status"),
                "asset_preflight_status": asset_preflight.get("status"),
                "missing_asset_count": asset_preflight.get("missing_asset_count"),
                "unresolved_reference_count": asset_preflight.get("unresolved_reference_count"),
                "artifacts": contract_result.get("artifacts"),
            },
            "Rerun the contract checker and asset preflight until the reviewed model has non-blocking diagnostics.",
        ),
    ]
    packet_ready = model_request.get("status") == "model_supplied"
    packet = {
        "schema": REVIEW_PACKET_SCHEMA,
        "ok": True,
        "status": "review_packet_ready_for_operator_review"
        if packet_ready
        else "review_packet_waiting_for_candidate_model",
        "model_authority": "review_packet_not_authority",
        "candidate_manifest_path": str(candidate_manifest_path),
        "model_request_status": model_request.get("status"),
        "selected_model_path": model_request.get("path"),
        "ready_for_model_backed_ik": False,
        "manifest_status": manifest_excerpt.get("status"),
        "manifest_missing_inputs": missing_inputs,
        "review_item_count": len(rows),
        "review_item_ids": [row["review_item_id"] for row in rows],
        "review_items": rows,
        "observed_evidence_is_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "notes": [
            "The review packet organizes evidence already produced by the bundle probe.",
            "It does not copy observed source hints, joint limits, or mesh references into reviewed manifest fields.",
            "A human/operator review still has to fill the candidate manifest and rerun the manifest checker.",
        ],
    }
    return packet, rows


def status_for(model_request: dict[str, Any], manifest_result: dict[str, Any]) -> str:
    if model_request["status"] == "model_not_supplied":
        return "candidate_model_missing"
    if model_request["status"] == "model_unavailable":
        return "candidate_model_unavailable"
    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    if manifest_excerpt.get("ready_for_model_backed_ik"):
        return "candidate_manifest_ready_for_model_backed_ik"
    return "candidate_manifest_needs_review"


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    contract = summary["contract_checker"]["diagnostic_excerpt"]
    manifest = summary["manifest_checker"]["diagnostic_excerpt"]
    asset_preflight = contract.get("model_asset_preflight") or {}
    lines = [
        "# SO-101 Model Bundle Probe",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `model_authority`: `{summary['model_authority']}`",
        f"- `observed_evidence_is_physical_so101_authority`: `{str(summary['observed_evidence_is_physical_so101_authority']).lower()}`",
        f"- `observed_evidence_is_policy_training_authority`: `{str(summary['observed_evidence_is_policy_training_authority']).lower()}`",
        f"- `development_fixture_evidence_not_physical_so101_truth`: `{str(summary['development_fixture_evidence_not_physical_so101_truth']).lower()}`",
        f"- `development_fixture_evidence_not_policy_training_truth`: `{str(summary['development_fixture_evidence_not_policy_training_truth']).lower()}`",
        f"- `physical_so101_model_authority_ready`: `{str(summary['physical_so101_model_authority_ready']).lower()}`",
        f"- `ready_for_policy_training`: `{str(summary['ready_for_policy_training']).lower()}`",
        f"- `candidate_manifest`: `{summary['artifacts']['candidate_manifest_json']}`",
        f"- `model_path`: `{summary['model_request']['path']}`",
        f"- `asset_roots`: `{'; '.join(summary['asset_roots']['asset_roots']) if summary['asset_roots']['asset_roots'] else 'none'}`",
        f"- `target_frame`: `{summary['target_frame']}`",
        f"- `contract_status`: `{contract.get('status')}`",
        f"- `asset_preflight_status`: `{asset_preflight.get('status')}`",
        f"- `asset_preflight_missing_asset_count`: `{asset_preflight.get('missing_asset_count')}`",
        f"- `asset_preflight_unresolved_reference_count`: `{asset_preflight.get('unresolved_reference_count')}`",
        f"- `observed_source_hints_status`: `{summary.get('observed_source_hints_status')}`",
        f"- `observed_source_hints_export_tool_hints`: `{', '.join(summary.get('observed_source_hints_export_tool_hints') or []) if summary.get('observed_source_hints_export_tool_hints') else 'none'}`",
        f"- `observed_source_hints_onshape_urls`: `{', '.join(summary.get('observed_source_hints_onshape_urls') or []) if summary.get('observed_source_hints_onshape_urls') else 'none'}`",
        f"- `observed_source_hints_license_status`: `{summary.get('observed_source_hints_license_status')}`",
        f"- `observed_joint_limits_status`: `{summary.get('observed_joint_limits_status')}`",
        f"- `observed_joint_limits_complete`: `{str(summary.get('observed_joint_limits_complete')).lower()}`",
        f"- `observed_joint_limits_missing_joints`: `{', '.join(summary.get('observed_joint_limits_missing_joints') or []) if summary.get('observed_joint_limits_missing_joints') else 'none'}`",
        f"- `mesh_asset_review_status`: `{summary.get('mesh_asset_review_status')}`",
        f"- `mesh_asset_review_unique_missing_reference_count`: `{summary.get('mesh_asset_review_unique_missing_reference_count')}`",
        f"- `mesh_asset_review_unique_unresolved_reference_count`: `{summary.get('mesh_asset_review_unique_unresolved_reference_count')}`",
        f"- `manifest_status`: `{manifest.get('status')}`",
        f"- `ready_for_model_backed_ik`: `{str(manifest.get('ready_for_model_backed_ik')).lower()}`",
        f"- `manifest_missing_inputs`: `{', '.join(manifest.get('missing_inputs') or []) if manifest.get('missing_inputs') else 'none'}`",
        f"- `review_packet_status`: `{summary.get('review_packet_status')}`",
        f"- `review_packet_item_count`: `{summary.get('review_packet_item_count')}`",
        f"- `review_packet_json`: `{summary['artifacts']['review_packet_json']}`",
        f"- `review_packet_csv`: `{summary['artifacts']['review_packet_csv']}`",
        f"- `next_required_action_ids`: `{', '.join(summary.get('next_required_action_ids') or []) if summary.get('next_required_action_ids') else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `checklist_csv`: `{summary['artifacts']['checklist_csv']}`",
        "",
        "## Checklist",
        "",
        "| Requirement | Status | Notes |",
        "| --- | --- | --- |",
    ]
    for checklist_row in rows:
        notes = checklist_row["notes"] or checklist_row["diagnostics"] or checklist_row["observed_value"] or ""
        lines.append(
            "| `{requirement}` | `{status}` | {notes} |".format(
                requirement=checklist_row["requirement_id"],
                status=checklist_row["status"],
                notes=str(notes).replace("|", "/"),
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
                "- `{priority}` `{action_id}`: {title} (`{missing_input}`)".format(
                    priority=action.get("priority"),
                    action_id=action.get("action_id"),
                    title=action.get("title"),
                    missing_input=action.get("missing_input"),
                )
            )
            lines.append(f"  - {action.get('detail')}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Next Inputs",
            "",
            "- Replace empty `authority` and `provenance` placeholders with reviewed source fields.",
            "- Top-level `authority` requires `reviewed_by`, `review_id` or HTTP(S) `review_url`, and `review_scopes`: `model_identity`, `provenance`, `license`.",
            "- Review `observed_source_hints_from_model` before copying source URL/export/license evidence into `provenance`.",
            "- Supply reviewed mesh asset roots that resolve every `mesh_asset_review_missing_references` entry and record `review_scope: mesh_assets`.",
            "- Replace `gripper_mapping_authority_placeholder` with a reviewed gripper mapping authority field carrying `review_scope: gripper_mapping`.",
            "- Replace `collision_policy_authority_placeholder` with a reviewed collision policy authority field carrying `review_scope: collision_policy`.",
            "- Replace `target_frame_authority_placeholder` with accepted reviewed target-frame/TCP-frame authority carrying `review_scope: target_frame`.",
            "- Replace `tcp_offset_placeholder` with one accepted calibrated TCP/gripper-tip offset field carrying `review_scope: tcp_offset`.",
            "- Replace `base_to_board_alignment_placeholder` with a real base-to-board transform/alignment carrying `review_scope: base_to_board_alignment`.",
            "- Re-run `scripts/smoke_sim_so101_model_bundle_manifest.py` on the candidate manifest before enabling model-backed IK.",
            "- Use `so101_model_bundle_review_packet.json` and `.csv` as review intake only; they are not model authority.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = normalize_path(args.model_path) if args.model_path is not None else None
    asset_roots = unique_paths(list(args.asset_root))
    model_request = build_model_request(model_path)
    asset_root_config = inspect_asset_roots(asset_roots)
    authority, authority_placeholder = build_authority(args)
    provenance, provenance_placeholder = build_provenance(args)
    observed_source_hints = observed_source_hints_from_model(model_path)

    contract_result = run_contract_checker(
        args.python,
        output_dir,
        model_path,
        asset_roots,
        str(args.target_frame),
    )
    observed_joint_limits = observed_joint_limits_from_contract(contract_result)
    mesh_asset_review = mesh_asset_review_from_contract(contract_result)

    candidate_manifest_path = output_dir / "so101_model_bundle.candidate.json"
    candidate_manifest = build_candidate_manifest(
        model_request=model_request,
        asset_root_config=asset_root_config,
        target_frame=str(args.target_frame),
        authority=authority,
        authority_placeholder=authority_placeholder,
        provenance=provenance,
        provenance_placeholder=provenance_placeholder,
        observed_source_hints=observed_source_hints,
        contract_result=contract_result,
        observed_joint_limits=observed_joint_limits,
        mesh_asset_review=mesh_asset_review,
    )
    write_json(candidate_manifest_path, candidate_manifest)

    manifest_result = run_manifest_checker(args.python, output_dir, candidate_manifest_path)
    review_packet, review_packet_rows = build_review_packet(
        model_request=model_request,
        asset_root_config=asset_root_config,
        candidate_manifest_path=candidate_manifest_path,
        observed_source_hints=observed_source_hints,
        observed_joint_limits=observed_joint_limits,
        mesh_asset_review=mesh_asset_review,
        manifest_result=manifest_result,
        contract_result=contract_result,
    )
    rows = build_rows(
        model_request=model_request,
        asset_root_config=asset_root_config,
        authority=authority,
        authority_placeholder=authority_placeholder,
        provenance=provenance,
        provenance_placeholder=provenance_placeholder,
        observed_source_hints=observed_source_hints,
        contract_result=contract_result,
        manifest_result=manifest_result,
        observed_joint_limits=observed_joint_limits,
        mesh_asset_review=mesh_asset_review,
    )

    summary_path = output_dir / "so101_model_bundle_probe_summary.json"
    csv_path = output_dir / "so101_model_bundle_probe_checklist.csv"
    review_packet_path = output_dir / "so101_model_bundle_review_packet.json"
    review_packet_csv_path = output_dir / "so101_model_bundle_review_packet.csv"
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(csv_path),
        "readme_md": str(readme_path),
        "candidate_manifest_json": str(candidate_manifest_path),
        "review_packet_json": str(review_packet_path),
        "review_packet_csv": str(review_packet_csv_path),
        "contract_summary_json": contract_result["artifacts"]["summary_json"],
        "contract_checklist_csv": contract_result["artifacts"]["checklist_csv"],
        "manifest_check_summary_json": manifest_result["artifacts"]["summary_json"],
        "manifest_checklist_csv": manifest_result["artifacts"]["checklist_csv"],
    }
    contract_excerpt = contract_result["diagnostic_excerpt"]
    asset_preflight_excerpt = contract_excerpt.get("model_asset_preflight") or {}
    manifest_excerpt = manifest_result["diagnostic_excerpt"]
    next_required = manifest_excerpt.get("next_required_for_goal") or []
    next_action_ids = manifest_excerpt.get("next_required_action_ids") or []
    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status_for(model_request, manifest_result),
        "model_authority": "draft_candidate_not_reviewed",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "physical_so101_model_authority_ready": False,
        "model_request_status": model_request["status"],
        "contract_status": contract_excerpt.get("status"),
        "asset_preflight_status": asset_preflight_excerpt.get("status"),
        "asset_preflight_mesh_reference_count": asset_preflight_excerpt.get("mesh_reference_count"),
        "asset_preflight_present_asset_count": asset_preflight_excerpt.get("present_asset_count"),
        "asset_preflight_missing_asset_count": asset_preflight_excerpt.get("missing_asset_count"),
        "asset_preflight_unresolved_reference_count": asset_preflight_excerpt.get("unresolved_reference_count"),
        "observed_source_hints_status": observed_source_hints.get("status"),
        "observed_source_hints_onshape_urls": observed_source_hints.get("onshape_urls"),
        "observed_source_hints_export_tool_hints": observed_source_hints.get("export_tool_hints"),
        "observed_source_hints_license_status": (
            observed_source_hints.get("license") or {}
        ).get("status"),
        "observed_source_hints_license_path": (
            observed_source_hints.get("license") or {}
        ).get("path"),
        "observed_source_hints_sha256": observed_source_hints.get("sha256"),
        "observed_joint_limits_status": observed_joint_limits.get("status"),
        "observed_joint_limits_complete": observed_joint_limits.get("complete"),
        "observed_joint_limits_deg": observed_joint_limits.get("values_deg"),
        "observed_joint_limits_missing_joints": observed_joint_limits.get("missing_joints"),
        "mesh_asset_review_status": mesh_asset_review.get("status"),
        "mesh_asset_review_unique_missing_reference_count": mesh_asset_review.get(
            "unique_missing_reference_count"
        ),
        "mesh_asset_review_missing_references": mesh_asset_review.get("missing_references"),
        "mesh_asset_review_unique_unresolved_reference_count": mesh_asset_review.get(
            "unique_unresolved_reference_count"
        ),
        "mesh_asset_review_unresolved_references": mesh_asset_review.get("unresolved_references"),
        "manifest_status": manifest_excerpt.get("status"),
        "ready_for_model_backed_ik": manifest_excerpt.get("ready_for_model_backed_ik") is True,
        "ready_for_policy_training": False,
        "missing_inputs": manifest_excerpt.get("missing_inputs") or [],
        "review_packet_status": review_packet["status"],
        "review_packet_model_authority": review_packet["model_authority"],
        "review_packet_item_count": review_packet["review_item_count"],
        "review_packet_item_ids": review_packet["review_item_ids"],
        "review_packet_observed_evidence_is_authority": review_packet[
            "observed_evidence_is_authority"
        ],
        "review_packet_development_fixture_evidence_not_physical_so101_truth": review_packet[
            "development_fixture_evidence_not_physical_so101_truth"
        ],
        "next_required_for_goal": next_required,
        "next_required_action_ids": next_action_ids,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "target_frame": str(args.target_frame),
        "model_request": model_request,
        "asset_roots": asset_root_config,
        "authority": {
            "value": authority,
            "placeholder": authority_placeholder,
        },
        "provenance": {
            "value": provenance,
            "placeholder": provenance_placeholder,
        },
        "candidate_manifest": candidate_manifest,
        "review_packet": review_packet,
        "contract_checker": {
            "status": contract_result.get("status"),
            "ok": contract_result.get("ok"),
            "returncode": contract_result.get("returncode"),
            "diagnostic_excerpt": contract_result["diagnostic_excerpt"],
            "artifacts": contract_result["artifacts"],
            "command": contract_result.get("command"),
        },
        "manifest_checker": {
            "status": manifest_result.get("status"),
            "ok": manifest_result.get("ok"),
            "returncode": manifest_result.get("returncode"),
            "diagnostic_excerpt": manifest_result["diagnostic_excerpt"],
            "artifacts": manifest_result["artifacts"],
            "command": manifest_result.get("command"),
        },
        "checklist": rows,
        "artifacts": artifacts,
        "limitations": [
            "This probe is hardware-free and never opens robot motors, serial ports, cameras, GUI flows, OpenAI calls, or network resources.",
            "The generated candidate manifest is a draft and does not copy, ingest, or modify model/mesh assets.",
            "Authority, provenance, gripper mapping, collision policy, TCP, and base-to-board placeholders are not treated as readiness fields by default.",
            "Future model-backed IK residuals remain diagnostic-only until the bundle manifest checker reports ready_for_model_backed_ik true.",
        ],
    }

    write_json(review_packet_path, review_packet)
    write_review_packet_csv(review_packet_csv_path, review_packet_rows)
    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    write_markdown(readme_path, summary, rows)

    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "candidate_manifest_json": str(candidate_manifest_path),
                "summary_json": str(summary_path),
                "checklist_csv": str(csv_path),
                "readme_md": str(readme_path),
                "model_authority": summary["model_authority"],
                "model_request_status": summary["model_request_status"],
                "contract_status": summary["contract_status"],
                "asset_preflight_status": summary["asset_preflight_status"],
                "asset_preflight_missing_asset_count": summary[
                    "asset_preflight_missing_asset_count"
                ],
                "asset_preflight_unresolved_reference_count": summary[
                    "asset_preflight_unresolved_reference_count"
                ],
                "observed_source_hints_status": summary["observed_source_hints_status"],
                "observed_source_hints_export_tool_hints": summary[
                    "observed_source_hints_export_tool_hints"
                ],
                "observed_source_hints_onshape_urls": summary[
                    "observed_source_hints_onshape_urls"
                ],
                "observed_source_hints_license_status": summary[
                    "observed_source_hints_license_status"
                ],
                "observed_joint_limits_status": summary["observed_joint_limits_status"],
                "observed_joint_limits_complete": summary["observed_joint_limits_complete"],
                "observed_joint_limits_missing_joints": summary[
                    "observed_joint_limits_missing_joints"
                ],
                "mesh_asset_review_status": summary["mesh_asset_review_status"],
                "mesh_asset_review_unique_missing_reference_count": summary[
                    "mesh_asset_review_unique_missing_reference_count"
                ],
                "mesh_asset_review_unique_unresolved_reference_count": summary[
                    "mesh_asset_review_unique_unresolved_reference_count"
                ],
                "manifest_status": summary["manifest_status"],
                "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
                "missing_inputs": summary["missing_inputs"],
                "review_packet_status": summary["review_packet_status"],
                "review_packet_item_count": summary["review_packet_item_count"],
                "review_packet_json": str(review_packet_path),
                "review_packet_csv": str(review_packet_csv_path),
                "next_required_action_ids": summary["next_required_action_ids"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
