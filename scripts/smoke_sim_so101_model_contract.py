#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SCHEMA = "lerobot.sim.so101_model_contract.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_model_contract"
ROBOT_METADATA_PATH = REPO_ROOT / "src" / "lerobot" / "sim" / "robot.py"
KINEMATICS_PATH = REPO_ROOT / "src" / "lerobot" / "model" / "kinematics.py"
DRILL_PATH = REPO_ROOT / "scripts" / "smoke_sim_ik_reachability_drill.py"
SUPPORTED_SUFFIXES = {".urdf", ".xml", ".mjcf", ".xacro"}
EXPECTED_TARGET_FRAME = "gripper_frame_link"
EXPECTED_TCP_FIELD_NAMES = (
    "tcp_offset",
    "gripper_tip_offset",
    "tool_center_point",
    "tool_frame",
    "gripper_frame_link",
)
CSV_FIELDNAMES = (
    "requirement_id",
    "category",
    "status",
    "severity",
    "source",
    "observed_value",
    "expected_value",
    "missing_inputs",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free SO-101 simulator model contract check. This records whether an "
            "optional model path is present and directly usable for RobotKinematics/placo, plus "
            "the joint/frame/TCP alignment inputs that still gate meaningful model-backed IK residuals."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Optional model path to inspect. Supported suffixes: .urdf, .xml, .mjcf, .xacro.",
    )
    parser.add_argument(
        "--target-frame",
        default=EXPECTED_TARGET_FRAME,
        help="Expected tool frame for RobotKinematics when a URDF-backed path is available.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row[key], sort_keys=True)
                    if isinstance(row.get(key), (dict, list, tuple))
                    else ("" if row.get(key) is None else row.get(key))
                    for key in CSV_FIELDNAMES
                }
            )


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SO-101 Model Contract Check",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `model_request`: `{summary['model_request']['status']}`",
        f"- `direct_robot_kinematics_status`: `{summary['robot_kinematics_path']['status']}`",
        f"- `target_frame`: `{summary['expected_contract']['target_frame']}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `checklist_csv`: `{summary['artifacts']['checklist_csv']}`",
        "",
        "## Checklist",
        "",
        "| Requirement | Status | Notes |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        requirement = row["requirement_id"]
        status = row["status"]
        notes = row["notes"] or row["observed_value"] or ""
        lines.append(f"| `{requirement}` | `{status}` | {str(notes).replace('|', '/')} |")
    path.write_text("\n".join(lines) + "\n")


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def load_sim_robot_metadata() -> dict[str, Any]:
    tree = ast.parse(ROBOT_METADATA_PATH.read_text())
    assignments: dict[str, Any] = {}
    desired_names = {"JOINT_LIMITS_DEG", "SO101_BODY_JOINTS", "DEFAULT_JOINT_POSITIONS_DEG"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in desired_names:
                    assignments[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in desired_names and node.value is not None:
                assignments[node.target.id] = ast.literal_eval(node.value)
    missing = sorted(desired_names - set(assignments))
    if missing:
        raise KeyError(f"Could not read simulator robot metadata from {ROBOT_METADATA_PATH}: {missing}")
    body_joints = tuple(str(joint) for joint in assignments["SO101_BODY_JOINTS"])
    joint_limits = {
        str(name): (float(bounds[0]), float(bounds[1]))
        for name, bounds in assignments["JOINT_LIMITS_DEG"].items()
    }
    default_positions = {
        str(name): float(value) for name, value in assignments["DEFAULT_JOINT_POSITIONS_DEG"].items()
    }
    return {
        "source_path": str(ROBOT_METADATA_PATH),
        "body_joints": body_joints,
        "joint_limits_deg": joint_limits,
        "default_joint_positions_deg": default_positions,
    }


def inspect_model_request(model_path: Path | None) -> dict[str, Any]:
    if model_path is None:
        return {
            "status": "model_not_supplied",
            "path": None,
            "exists": False,
            "supported_suffix": False,
            "suffix": None,
            "reason": "No model path was supplied. Contract requirements are recorded without claiming a usable model.",
        }

    resolved = model_path.expanduser().resolve()
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


def inspect_robot_kinematics_path(model_request: dict[str, Any]) -> dict[str, Any]:
    placo_ready = module_available("placo")
    if model_request["status"] == "model_not_supplied":
        status = "missing_model"
        directly_usable = False
        reason = "RobotKinematics cannot be exercised until a URDF path is supplied."
    elif not model_request["exists"]:
        status = "model_unavailable"
        directly_usable = False
        reason = "RobotKinematics cannot open a missing file."
    elif model_request["suffix"] != ".urdf":
        status = "supported_suffix_not_directly_usable"
        directly_usable = False
        reason = "Current RobotKinematics initializes placo.RobotWrapper from a URDF path only."
    elif not placo_ready:
        status = "urdf_requires_placo"
        directly_usable = False
        reason = "URDF is structurally aligned with RobotKinematics, but placo is unavailable in this environment."
    else:
        status = "directly_usable"
        directly_usable = True
        reason = "URDF path is directly usable by the current RobotKinematics/placo code path."
    return {
        "status": status,
        "directly_usable": directly_usable,
        "placo_available": placo_ready,
        "reason": reason,
        "robot_kinematics_source": str(KINEMATICS_PATH),
    }


def tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def parse_urdf_limits_deg(limit_node: ET.Element | None) -> list[float] | None:
    if limit_node is None:
        return None
    lower_text = limit_node.attrib.get("lower")
    upper_text = limit_node.attrib.get("upper")
    if lower_text is None or upper_text is None:
        return None
    try:
        lower = math.degrees(float(lower_text))
        upper = math.degrees(float(upper_text))
    except ValueError:
        return None
    return [lower, upper]


def inspect_xml_model(model_request: dict[str, Any], target_frame: str, expected_joints: tuple[str, ...]) -> dict[str, Any]:
    if not model_request["exists"] or not model_request["supported_suffix"]:
        return {
            "status": "not_inspected",
            "reason": model_request["reason"],
        }
    path = Path(str(model_request["path"]))
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return {
            "status": "xml_parse_error",
            "reason": f"{type(exc).__name__}: {exc}",
            "path": str(path),
        }

    links = sorted(
        {
            node.attrib["name"]
            for node in root.iter()
            if tag_name(node) == "link" and node.attrib.get("name")
        }
    )
    joints: list[dict[str, Any]] = []
    for node in root.iter():
        if tag_name(node) != "joint" or not node.attrib.get("name"):
            continue
        joints.append(
            {
                "name": node.attrib["name"],
                "type": node.attrib.get("type"),
                "limits_deg": parse_urdf_limits_deg(next((child for child in node if tag_name(child) == "limit"), None)),
            }
        )
    joint_names = [joint["name"] for joint in joints]
    present_expected = [joint for joint in expected_joints if joint in joint_names]
    missing_expected = [joint for joint in expected_joints if joint not in joint_names]
    target_frame_present = target_frame in links or target_frame in joint_names

    status = "xml_inspected"
    if path.suffix.lower() == ".urdf" and not missing_expected and target_frame_present:
        status = "urdf_contract_visible"

    return {
        "status": status,
        "path": str(path),
        "root_tag": tag_name(root),
        "link_names": links,
        "joint_names": joint_names,
        "joints": joints,
        "expected_joint_names_present": present_expected,
        "expected_joint_names_missing": missing_expected,
        "target_frame_present": target_frame_present,
    }


def try_robot_kinematics_init(model_request: dict[str, Any], target_frame: str, expected_joints: tuple[str, ...]) -> dict[str, Any]:
    if model_request["status"] == "model_not_supplied":
        return {"status": "not_attempted", "reason": "No model was supplied."}
    if not model_request["exists"]:
        return {"status": "not_attempted", "reason": "Supplied model path does not exist."}
    if model_request["suffix"] != ".urdf":
        return {"status": "not_attempted", "reason": "RobotKinematics only accepts URDF paths today."}
    if not module_available("placo"):
        return {"status": "not_attempted", "reason": "placo is unavailable in this environment."}

    try:
        from lerobot.model.kinematics import RobotKinematics

        solver = RobotKinematics(
            str(model_request["path"]),
            target_frame_name=target_frame,
            joint_names=list(expected_joints),
        )
    except Exception as exc:
        return {
            "status": "initialization_failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "path": str(model_request["path"]),
            "target_frame": target_frame,
            "joint_names": list(expected_joints),
        }

    try:
        discovered_joint_names = list(solver.robot.joint_names())
    except Exception:
        discovered_joint_names = list(expected_joints)
    return {
        "status": "initialized",
        "path": str(model_request["path"]),
        "target_frame": target_frame,
        "requested_joint_names": list(expected_joints),
        "solver_joint_names": discovered_joint_names,
    }


def inspect_tcp_configuration_sources() -> dict[str, Any]:
    source_paths = [KINEMATICS_PATH, DRILL_PATH, ROBOT_METADATA_PATH]
    field_hits: dict[str, list[dict[str, Any]]] = {name: [] for name in EXPECTED_TCP_FIELD_NAMES}
    for path in source_paths:
        lines = path.read_text(errors="replace").splitlines()
        for line_no, line in enumerate(lines, start=1):
            lowered = line.lower()
            for field_name in EXPECTED_TCP_FIELD_NAMES:
                if field_name.lower() in lowered:
                    field_hits[field_name].append(
                        {
                            "path": str(path),
                            "line": line_no,
                            "text": line.strip(),
                        }
                    )
    configured_fields = {name: hits for name, hits in field_hits.items() if hits}
    missing_fields = [name for name, hits in field_hits.items() if not hits]
    return {
        "configured_field_hits": configured_fields,
        "missing_expected_fields": missing_fields,
        "notes": (
            "The repo exposes the target frame name but no dedicated calibrated TCP/gripper-tip offset field "
            "for the simulator IK contract yet."
        ),
    }


def build_alignment_inputs_missing() -> list[dict[str, str]]:
    return [
        {
            "input": "authoritative_model_source",
            "reason": "Need a repo-local SO-101 URDF or MuJoCo/MJCF source that matches simulator joint axes and link lengths.",
        },
        {
            "input": "target_frame_to_contact_point",
            "reason": "Need the calibrated relation between gripper_frame_link and chess-piece contact TCP/gripper-tip point.",
        },
        {
            "input": "joint_name_order_mapping",
            "reason": "Need explicit confirmation that model joint names/order match shoulder_pan through wrist_roll.",
        },
        {
            "input": "joint_limit_authority",
            "reason": "Need the model-source limits reconciled against src/lerobot/sim/robot.py simulator limits.",
        },
        {
            "input": "base_board_alignment",
            "reason": "Need the board pose/base-frame alignment used when interpreting residuals for simulator chess waypoints.",
        },
        {
            "input": "collision_and_margin_policy",
            "reason": "Need model-backed collision/TCP safety policy before treating low residuals as execution-safe.",
        },
    ]


def row(
    requirement_id: str,
    category: str,
    status: str,
    severity: str,
    source: str,
    observed_value: Any,
    expected_value: Any,
    missing_inputs: Any = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "category": category,
        "status": status,
        "severity": severity,
        "source": source,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "missing_inputs": missing_inputs,
        "notes": notes,
    }


def build_checklist_rows(
    metadata: dict[str, Any],
    model_request: dict[str, Any],
    robot_kinematics_path: dict[str, Any],
    xml_inspection: dict[str, Any],
    kinematics_init: dict[str, Any],
    tcp_sources: dict[str, Any],
    missing_alignment_inputs: list[dict[str, str]],
    target_frame: str,
) -> list[dict[str, Any]]:
    expected_joints = list(metadata["body_joints"])
    rows = [
        row(
            "model_request",
            "model_path",
            "ok" if model_request["status"] == "model_supplied" else "action_required",
            "info",
            "cli",
            model_request,
            {"supported_suffixes": sorted(SUPPORTED_SUFFIXES)},
            None,
            model_request["reason"],
        ),
        row(
            "robot_kinematics_path",
            "direct_usability",
            "ok" if robot_kinematics_path["directly_usable"] else "action_required",
            "warning",
            str(KINEMATICS_PATH),
            robot_kinematics_path,
            {"suffix": ".urdf", "placo_available": True},
            None,
            robot_kinematics_path["reason"],
        ),
        row(
            "body_joints",
            "joint_contract",
            "ok",
            "info",
            str(ROBOT_METADATA_PATH),
            list(metadata["body_joints"]),
            expected_joints,
            None,
            "Expected SO-101 simulator body-joint order for RobotKinematics joint_names.",
        ),
        row(
            "joint_limits_deg",
            "joint_contract",
            "ok",
            "info",
            str(ROBOT_METADATA_PATH),
            metadata["joint_limits_deg"],
            metadata["joint_limits_deg"],
            None,
            "Simulator joint limits currently treated as the minimum contract until an authoritative model is reconciled.",
        ),
        row(
            "target_frame",
            "frame_contract",
            "ok" if target_frame == EXPECTED_TARGET_FRAME else "action_required",
            "warning",
            str(KINEMATICS_PATH),
            target_frame,
            EXPECTED_TARGET_FRAME,
            None,
            "Default target frame for current RobotKinematics usage.",
        ),
        row(
            "tcp_offset_source",
            "tcp_contract",
            "action_required" if tcp_sources["missing_expected_fields"] else "ok",
            "warning",
            f"{KINEMATICS_PATH},{DRILL_PATH},{ROBOT_METADATA_PATH}",
            tcp_sources["configured_field_hits"],
            {"expected_field_names": list(EXPECTED_TCP_FIELD_NAMES)},
            tcp_sources["missing_expected_fields"],
            tcp_sources["notes"],
        ),
        row(
            "model_to_sim_alignment_inputs",
            "alignment",
            "action_required",
            "warning",
            "simulator+future_model",
            {"missing_input_count": len(missing_alignment_inputs)},
            {"required": [item["input"] for item in missing_alignment_inputs]},
            missing_alignment_inputs,
            "These inputs must be sourced before model-backed residuals can be treated as meaningful reachability truth.",
        ),
    ]

    if xml_inspection["status"] != "not_inspected":
        rows.append(
            row(
                "xml_joint_visibility",
                "model_structure",
                "ok" if not xml_inspection.get("expected_joint_names_missing") else "action_required",
                "warning",
                str(model_request.get("path")),
                {
                    "present": xml_inspection.get("expected_joint_names_present"),
                    "missing": xml_inspection.get("expected_joint_names_missing"),
                },
                expected_joints,
                xml_inspection.get("expected_joint_names_missing"),
                "Static XML inspection only. This does not prove dynamic FK/IK compatibility.",
            )
        )
        rows.append(
            row(
                "xml_target_frame_visibility",
                "model_structure",
                "ok" if xml_inspection.get("target_frame_present") else "action_required",
                "warning",
                str(model_request.get("path")),
                xml_inspection.get("target_frame_present"),
                True,
                None if xml_inspection.get("target_frame_present") else [target_frame],
                "Checks whether the expected target frame name is visible as a link or joint name in the XML tree.",
            )
        )

    if kinematics_init["status"] != "not_attempted":
        rows.append(
            row(
                "robot_kinematics_initialization",
                "model_runtime",
                "ok" if kinematics_init["status"] == "initialized" else "action_required",
                "warning",
                str(KINEMATICS_PATH),
                kinematics_init,
                {"status": "initialized", "target_frame": target_frame, "joint_names": expected_joints},
                None,
                "Non-destructive RobotKinematics initialization attempt for a supplied URDF only.",
            )
        )
    return rows


def build_summary(
    target_frame: str,
    metadata: dict[str, Any],
    model_request: dict[str, Any],
    robot_kinematics_path: dict[str, Any],
    xml_inspection: dict[str, Any],
    kinematics_init: dict[str, Any],
    tcp_sources: dict[str, Any],
    missing_alignment_inputs: list[dict[str, str]],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    if model_request["status"] == "model_not_supplied":
        status = "missing_model"
    elif not model_request["exists"]:
        status = "model_unavailable"
    elif kinematics_init["status"] == "initialized":
        status = "model_contract_checked"
    elif model_request["suffix"] == ".urdf":
        status = "model_contract_needs_follow_up"
    else:
        status = "model_suffix_supported_not_directly_usable"

    return {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "model_request": model_request,
        "robot_kinematics_path": robot_kinematics_path,
        "expected_contract": {
            "body_joints": list(metadata["body_joints"]),
            "joint_limits_deg": metadata["joint_limits_deg"],
            "target_frame": target_frame,
            "default_joint_positions_deg": metadata["default_joint_positions_deg"],
            "tcp_expected_field_names": list(EXPECTED_TCP_FIELD_NAMES),
        },
        "model_structure_inspection": xml_inspection,
        "robot_kinematics_initialization": kinematics_init,
        "tcp_or_gripper_tip_sources": tcp_sources,
        "model_to_sim_alignment_inputs_missing": missing_alignment_inputs,
        "artifacts": artifacts,
        "limitations": [
            "This checker is hardware-free and does not open motors, serial ports, cameras, GUI flows, or real robot execution paths.",
            "XML inspection can confirm visible names and URDF-declared limits, but it does not prove simulator alignment or collision safety.",
            "A low model-backed residual should not be treated as meaningful until the target frame/TCP offset and simulator-model alignment inputs are sourced.",
        ],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_sim_robot_metadata()
    model_request = inspect_model_request(args.model_path)
    robot_kinematics_path = inspect_robot_kinematics_path(model_request)
    xml_inspection = inspect_xml_model(model_request, str(args.target_frame), metadata["body_joints"])
    kinematics_init = try_robot_kinematics_init(model_request, str(args.target_frame), metadata["body_joints"])
    tcp_sources = inspect_tcp_configuration_sources()
    missing_alignment_inputs = build_alignment_inputs_missing()

    checklist_rows = build_checklist_rows(
        metadata,
        model_request,
        robot_kinematics_path,
        xml_inspection,
        kinematics_init,
        tcp_sources,
        missing_alignment_inputs,
        str(args.target_frame),
    )

    summary_path = output_dir / "so101_model_contract_summary.json"
    csv_path = output_dir / "so101_model_contract_checklist.csv"
    md_path = output_dir / "README.md"
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(csv_path),
        "readme_md": str(md_path),
    }
    summary = build_summary(
        str(args.target_frame),
        metadata,
        model_request,
        robot_kinematics_path,
        xml_inspection,
        kinematics_init,
        tcp_sources,
        missing_alignment_inputs,
        artifacts,
    )

    write_json(summary_path, summary)
    write_csv(csv_path, checklist_rows)
    write_markdown(md_path, summary, checklist_rows)

    print(
        json.dumps(
            {
                "ok": True,
                "status": summary["status"],
                "model_request_status": model_request["status"],
                "robot_kinematics_status": robot_kinematics_path["status"],
                "summary_json": str(summary_path),
                "checklist_csv": str(csv_path),
                "readme_md": str(md_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
