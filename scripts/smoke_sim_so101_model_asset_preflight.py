#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEMA = "lerobot.sim.so101_model_asset_preflight.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_asset_preflight"
SUPPORTED_SUFFIXES = {".urdf", ".xml", ".mjcf", ".xacro"}
SUBSTITUTION_PATTERN = re.compile(r"(\$\{[^}]+\}|\$\(.*?\))")
CSV_FIELDNAMES = (
    "reference_id",
    "model_path",
    "model_format",
    "scan_mode",
    "source_tag",
    "source_attribute",
    "raw_reference",
    "normalized_reference",
    "uri_scheme",
    "package_or_model_name",
    "resolution_status",
    "exists",
    "resolved_path",
    "checked_paths",
    "diagnostics",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free SO-101 model asset dependency preflight. URDF mesh "
            "filename references are checked against the model directory and optional "
            "asset roots before RobotKinematics initialization is trusted."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Optional SO-101 model path to inspect. Supported suffixes: .urdf, .xml, .mjcf, .xacro.",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        action="append",
        default=[],
        help="Additional root used to resolve relative, package://, or model:// asset references. Repeatable.",
    )
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


def tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


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


def inspect_model_request(model_path: Path | None) -> dict[str, Any]:
    if model_path is None:
        return {
            "status": "model_not_supplied",
            "path": None,
            "exists": False,
            "supported_suffix": False,
            "suffix": None,
            "reason": (
                "No model path was supplied. Asset dependency preflight is recorded without "
                "claiming a usable kinematic model."
            ),
        }

    resolved = normalize_path(model_path)
    suffix = resolved.suffix.lower()
    exists = resolved.exists()
    supported_suffix = suffix in SUPPORTED_SUFFIXES
    if not exists:
        status = "model_unavailable"
        reason = f"Supplied model path does not exist: {resolved}"
    elif not supported_suffix:
        status = "unsupported_suffix"
        reason = f"Model exists but suffix {suffix!r} is not one of {sorted(SUPPORTED_SUFFIXES)}."
    else:
        status = "model_supplied"
        reason = "Model path exists and has a supported suffix."
    return {
        "status": status,
        "path": str(resolved),
        "exists": exists,
        "supported_suffix": supported_suffix,
        "suffix": suffix,
        "reason": reason,
    }


def parse_model_xml(model_request: dict[str, Any]) -> tuple[ET.Element | None, dict[str, Any]]:
    if model_request["status"] != "model_supplied":
        return None, {"status": "not_inspected", "reason": model_request["reason"]}

    path = Path(str(model_request["path"]))
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return None, {
            "status": "xml_parse_error",
            "reason": f"{type(exc).__name__}: {exc}",
            "path": str(path),
        }

    return root, {
        "status": "xml_parsed",
        "path": str(path),
        "root_tag": tag_name(root),
        "root_name": root.attrib.get("name"),
    }


def classify_scan_mode(path: Path, root: ET.Element | None) -> tuple[str, str, list[str]]:
    suffix = path.suffix.lower()
    root_tag = tag_name(root) if root is not None else None
    limitations: list[str] = []

    if suffix == ".urdf":
        return "urdf_mesh_filename_scan", "urdf", limitations

    if suffix == ".xacro":
        limitations.extend(
            [
                "Xacro macros, includes, $(find ...) expressions, and ${...} substitutions are not expanded.",
                "Only literal mesh filename attributes visible in the XML file are checked.",
            ]
        )
        return "limited_xacro_literal_mesh_scan", "xacro", limitations

    if suffix == ".mjcf":
        limitations.extend(
            [
                "MJCF includes, compiler meshdir, package loaders, and generated assets are not fully resolved.",
                "Only literal mesh file attributes visible in this XML file are checked.",
            ]
        )
        return "limited_mjcf_mesh_file_scan", "mjcf", limitations

    if suffix == ".xml" and root_tag == "robot":
        limitations.append("The .xml suffix is scanned as URDF-like XML, but only literal mesh filename attributes are checked.")
        return "limited_xml_urdf_style_mesh_scan", "urdf_xml", limitations

    if suffix == ".xml" and root_tag == "mujoco":
        limitations.extend(
            [
                "MJCF includes, compiler meshdir, package loaders, and generated assets are not fully resolved.",
                "Only literal mesh file attributes visible in this XML file are checked.",
            ]
        )
        return "limited_xml_mjcf_mesh_file_scan", "mujoco_xml", limitations

    limitations.append("Unsupported XML root for full asset parsing; only literal mesh filename/file attributes are checked.")
    return "limited_generic_xml_mesh_scan", "xml", limitations


def mesh_reference_nodes(root: ET.Element, scan_mode: str) -> list[tuple[ET.Element, str]]:
    references: list[tuple[ET.Element, str]] = []
    for node in root.iter():
        if tag_name(node) != "mesh":
            continue
        if scan_mode in {
            "urdf_mesh_filename_scan",
            "limited_xacro_literal_mesh_scan",
            "limited_xml_urdf_style_mesh_scan",
            "limited_generic_xml_mesh_scan",
        }:
            if node.attrib.get("filename"):
                references.append((node, "filename"))
        if scan_mode in {
            "limited_mjcf_mesh_file_scan",
            "limited_xml_mjcf_mesh_file_scan",
            "limited_generic_xml_mesh_scan",
        }:
            if node.attrib.get("file"):
                references.append((node, "file"))
    return references


def split_package_or_model_uri(raw_reference: str, scheme: str) -> tuple[str | None, str]:
    prefix = f"{scheme}://"
    remainder = raw_reference[len(prefix) :]
    parts = remainder.split("/", 1)
    package_or_model = urllib.parse.unquote(parts[0]) if parts and parts[0] else None
    relative = urllib.parse.unquote(parts[1]) if len(parts) == 2 else ""
    return package_or_model, relative


def normalize_reference(
    raw_reference: str,
    model_dir: Path,
    asset_roots: list[Path],
) -> dict[str, Any]:
    stripped = raw_reference.strip()
    parsed = urllib.parse.urlparse(stripped)
    scheme = parsed.scheme.lower()
    diagnostics: list[str] = []
    checked_paths: list[Path] = []
    normalized_reference = stripped
    package_or_model_name: str | None = None
    notes: str | None = None

    if not stripped:
        return {
            "normalized_reference": "",
            "uri_scheme": "",
            "package_or_model_name": None,
            "checked_paths": [],
            "diagnostics": ["empty_reference"],
            "notes": "Empty mesh reference cannot be resolved.",
        }

    if SUBSTITUTION_PATTERN.search(stripped):
        diagnostics.append("contains_substitution_expression")
        notes = "The reference contains a substitution expression that this static preflight does not expand."

    if scheme in {"package", "model"}:
        package_or_model_name, relative_part = split_package_or_model_uri(stripped, scheme)
        diagnostics.append(f"{scheme}_resolution_not_available")
        normalized_reference = relative_part
        if not package_or_model_name or not relative_part:
            diagnostics.append(f"malformed_{scheme}_uri")
        else:
            candidate_suffixes = [
                Path(package_or_model_name) / relative_part,
                Path(relative_part),
            ]
            search_roots = [model_dir] + asset_roots
            for root in search_roots:
                for suffix in candidate_suffixes:
                    checked_paths.append(normalize_path(root / suffix))
        return {
            "normalized_reference": normalized_reference,
            "uri_scheme": scheme,
            "package_or_model_name": package_or_model_name,
            "checked_paths": checked_paths,
            "diagnostics": diagnostics,
            "notes": notes
            or (
                f"{scheme}:// is checked only as simple paths under the model directory "
                "and supplied asset roots; no ROS/package registry resolution is performed."
            ),
        }

    if scheme == "file":
        if parsed.netloc and parsed.netloc != "localhost":
            diagnostics.append("file_uri_nonempty_authority_treated_as_path_prefix")
            local_text = urllib.parse.unquote(f"{parsed.netloc}{parsed.path}")
        else:
            local_text = urllib.parse.unquote(parsed.path)
        normalized_reference = local_text
        local_path = Path(local_text)
        if local_path.is_absolute():
            checked_paths.append(normalize_path(local_path))
        else:
            checked_paths.extend(normalize_path(root / local_path) for root in [model_dir] + asset_roots)
        return {
            "normalized_reference": normalized_reference,
            "uri_scheme": scheme,
            "package_or_model_name": None,
            "checked_paths": checked_paths,
            "diagnostics": diagnostics,
            "notes": notes,
        }

    if scheme and len(scheme) > 1:
        diagnostics.append(f"unsupported_uri_scheme:{scheme}")
        return {
            "normalized_reference": stripped,
            "uri_scheme": scheme,
            "package_or_model_name": None,
            "checked_paths": [],
            "diagnostics": diagnostics,
            "notes": notes or "Unsupported URI scheme; no filesystem resolution was attempted.",
        }

    raw_path = Path(stripped)
    normalized_reference = str(raw_path)
    if raw_path.is_absolute():
        checked_paths.append(normalize_path(raw_path))
    else:
        checked_paths.extend(normalize_path(root / raw_path) for root in [model_dir] + asset_roots)
    return {
        "normalized_reference": normalized_reference,
        "uri_scheme": "",
        "package_or_model_name": None,
        "checked_paths": checked_paths,
        "diagnostics": diagnostics,
        "notes": notes,
    }


def row_for_reference(
    index: int,
    model_path: Path,
    model_format: str,
    scan_mode: str,
    node: ET.Element,
    attribute: str,
    asset_roots: list[Path],
) -> dict[str, Any]:
    raw_reference = node.attrib[attribute]
    normalized = normalize_reference(raw_reference, model_path.parent, asset_roots)
    checked_paths = normalized["checked_paths"]
    existing_paths = [path for path in checked_paths if path.exists()]
    if existing_paths:
        resolution_status = "present"
        resolved_path = existing_paths[0]
        exists = True
    elif checked_paths:
        resolution_status = "missing"
        resolved_path = None
        exists = False
    else:
        resolution_status = "unresolved"
        resolved_path = None
        exists = False

    return {
        "reference_id": f"mesh_{index:04d}",
        "model_path": str(model_path),
        "model_format": model_format,
        "scan_mode": scan_mode,
        "source_tag": tag_name(node),
        "source_attribute": attribute,
        "raw_reference": raw_reference,
        "normalized_reference": normalized["normalized_reference"],
        "uri_scheme": normalized["uri_scheme"],
        "package_or_model_name": normalized["package_or_model_name"],
        "resolution_status": resolution_status,
        "exists": exists,
        "resolved_path": str(resolved_path) if resolved_path is not None else None,
        "checked_paths": [str(path) for path in checked_paths],
        "diagnostics": normalized["diagnostics"],
        "notes": normalized["notes"],
    }


def inspect_asset_references(
    model_request: dict[str, Any],
    asset_roots: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root, xml_info = parse_model_xml(model_request)
    if root is None or model_request["status"] != "model_supplied":
        return {
            "status": xml_info["status"],
            "reason": xml_info.get("reason"),
            "root_tag": xml_info.get("root_tag"),
            "root_name": xml_info.get("root_name"),
            "scan_mode": None,
            "model_format": None,
            "limitations": [],
        }, []

    model_path = Path(str(model_request["path"]))
    scan_mode, model_format, limitations = classify_scan_mode(model_path, root)
    references = mesh_reference_nodes(root, scan_mode)
    rows = [
        row_for_reference(index, model_path, model_format, scan_mode, node, attribute, asset_roots)
        for index, (node, attribute) in enumerate(references, start=1)
    ]

    return {
        "status": "asset_references_inspected",
        "path": str(model_path),
        "root_tag": xml_info.get("root_tag"),
        "root_name": xml_info.get("root_name"),
        "scan_mode": scan_mode,
        "model_format": model_format,
        "limitations": limitations,
        "mesh_reference_count": len(rows),
    }, rows


def build_status(model_request: dict[str, Any], inspection: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if model_request["status"] == "model_not_supplied":
        return "missing_model"
    if model_request["status"] == "model_unavailable":
        return "model_unavailable"
    if model_request["status"] == "unsupported_suffix":
        return "unsupported_suffix"
    if inspection["status"] == "xml_parse_error":
        return "model_parse_error"

    missing_or_unresolved = [row for row in rows if row["resolution_status"] != "present"]
    if missing_or_unresolved:
        return "asset_preflight_needs_follow_up"
    if inspection.get("limitations"):
        return "asset_preflight_limited_diagnostics"
    return "asset_preflight_checked"


def build_diagnostics(model_request: dict[str, Any], inspection: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if model_request["status"] == "model_not_supplied":
        diagnostics.append(
            {
                "diagnostic": "model_not_supplied",
                "severity": "action_required",
                "reason": model_request["reason"],
            }
        )
    elif model_request["status"] == "model_unavailable":
        diagnostics.append(
            {
                "diagnostic": "model_unavailable",
                "severity": "action_required",
                "reason": model_request["reason"],
            }
        )
    elif model_request["status"] == "unsupported_suffix":
        diagnostics.append(
            {
                "diagnostic": "unsupported_suffix",
                "severity": "action_required",
                "reason": model_request["reason"],
            }
        )

    if inspection["status"] == "xml_parse_error":
        diagnostics.append(
            {
                "diagnostic": "model_xml_parse_error",
                "severity": "action_required",
                "reason": inspection.get("reason"),
            }
        )

    missing_rows = [row for row in rows if row["resolution_status"] == "missing"]
    unresolved_rows = [row for row in rows if row["resolution_status"] == "unresolved"]
    if missing_rows:
        diagnostics.append(
            {
                "diagnostic": "missing_mesh_assets",
                "severity": "action_required",
                "count": len(missing_rows),
                "references": [row["raw_reference"] for row in missing_rows],
            }
        )
    if unresolved_rows:
        diagnostics.append(
            {
                "diagnostic": "unresolved_mesh_references",
                "severity": "action_required",
                "count": len(unresolved_rows),
                "references": [row["raw_reference"] for row in unresolved_rows],
            }
        )
    return diagnostics


def build_summary(
    model_request: dict[str, Any],
    asset_roots: list[Path],
    inspection: dict[str, Any],
    rows: list[dict[str, Any]],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    status = build_status(model_request, inspection, rows)
    present_rows = [row for row in rows if row["resolution_status"] == "present"]
    missing_rows = [row for row in rows if row["resolution_status"] == "missing"]
    unresolved_rows = [row for row in rows if row["resolution_status"] == "unresolved"]

    return {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "model_request": model_request,
        "asset_roots": [str(path) for path in asset_roots],
        "model_asset_inspection": inspection,
        "mesh_reference_count": len(rows),
        "present_asset_count": len(present_rows),
        "missing_asset_count": len(missing_rows),
        "unresolved_reference_count": len(unresolved_rows),
        "missing_assets": missing_rows,
        "unresolved_references": unresolved_rows,
        "asset_references": rows,
        "diagnostics": build_diagnostics(model_request, inspection, rows),
        "artifacts": artifacts,
        "limitations": [
            "This preflight never opens hardware, cameras, serial ports, GUI flows, OpenAI calls, or network resources.",
            "URDF mesh filename references are checked with filesystem heuristics only.",
            "package:// and model:// references are not resolved through ROS, ament, colcon, Gazebo, or package registries.",
            "Xacro macros/includes and MJCF include/compiler meshdir behavior are not fully expanded.",
            "A complete asset preflight does not prove model-to-simulator frame, TCP, collision, or board alignment.",
        ],
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SO-101 Model Asset Preflight",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `model_request`: `{summary['model_request']['status']}`",
        f"- `scan_mode`: `{summary['model_asset_inspection'].get('scan_mode')}`",
        f"- `mesh_reference_count`: `{summary['mesh_reference_count']}`",
        f"- `present_asset_count`: `{summary['present_asset_count']}`",
        f"- `missing_asset_count`: `{summary['missing_asset_count']}`",
        f"- `unresolved_reference_count`: `{summary['unresolved_reference_count']}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `assets_csv`: `{summary['artifacts']['assets_csv']}`",
        "",
        "## Mesh References",
        "",
        "| Reference | Status | Raw reference | Resolved path |",
        "| --- | --- | --- | --- |",
    ]
    if not summary["asset_references"]:
        lines.append("| none | none | n/a | n/a |")
    else:
        for row in summary["asset_references"]:
            resolved = row["resolved_path"] or ""
            lines.append(
                "| `{reference_id}` | `{status}` | `{raw}` | `{resolved}` |".format(
                    reference_id=row["reference_id"],
                    status=row["resolution_status"],
                    raw=str(row["raw_reference"]).replace("|", "/"),
                    resolved=resolved.replace("|", "/"),
                )
            )

    if summary["missing_assets"]:
        lines.extend(["", "## Missing Assets", ""])
        for row in summary["missing_assets"]:
            checked = ", ".join(f"`{path}`" for path in row["checked_paths"])
            lines.append(f"- `{row['raw_reference']}` checked: {checked}")

    limitations = summary["model_asset_inspection"].get("limitations") or []
    if limitations:
        lines.extend(["", "## Limited Diagnostics", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")

    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    asset_roots = unique_paths(list(args.asset_root))
    model_request = inspect_model_request(args.model_path)
    inspection, rows = inspect_asset_references(model_request, asset_roots)

    summary_path = output_dir / "so101_model_asset_preflight_summary.json"
    csv_path = output_dir / "so101_model_asset_preflight_assets.csv"
    readme_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "assets_csv": str(csv_path),
        "readme_md": str(readme_path),
    }
    summary = build_summary(model_request, asset_roots, inspection, rows, artifacts)

    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    write_markdown(readme_path, summary)

    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "model_request_status": model_request["status"],
                "mesh_reference_count": summary["mesh_reference_count"],
                "present_asset_count": summary["present_asset_count"],
                "missing_asset_count": summary["missing_asset_count"],
                "unresolved_reference_count": summary["unresolved_reference_count"],
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
