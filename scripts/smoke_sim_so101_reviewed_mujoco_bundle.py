#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SCHEMA = "lerobot.sim.so101_reviewed_mujoco_bundle.v1"
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_reviewed_mujoco_bundle"
SUMMARY_NAME = "so101_reviewed_mujoco_bundle_summary.json"
CHECKLIST_NAME = "so101_reviewed_mujoco_bundle_checklist.csv"
README_NAME = "README.md"
MANIFEST_CHECKER_PATH = REPO_ROOT / "scripts" / "smoke_sim_so101_model_bundle_manifest.py"
SO101_BODY_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
)
SO101_JOINTS: tuple[str, ...] = (
    *SO101_BODY_JOINTS,
    "gripper",
)
BODY_JOINT_TARGETS_DEG: dict[str, float] = {
    "shoulder_pan": 8.0,
    "shoulder_lift": -18.0,
    "elbow_flex": 34.0,
    "wrist_flex": -20.0,
    "wrist_roll": 22.0,
}
JOINT_LIMIT_RANGE_TOLERANCE_RAD = 1e-6
MOTION_AUTHORITY_STATUSES = {
    "not_checked_manifest_not_ready",
    "physical_reviewed_model_motion_checked",
    "hardware_free_fixture_motion_checked_not_physical_so101_authority",
    "motion_checked_authority_incomplete",
    "physical_reviewed_model_motion_failed",
    "hardware_free_fixture_motion_failed",
    "motion_failed_authority_incomplete",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the reviewed SO-101 model bundle handoff into MuJoCo. Missing or "
            "not-ready manifests are recorded as non-failing diagnostics by default; a ready "
            "bundle must load in MuJoCo, map every SO-101 joint, and move through SimRobot."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--manifest-summary-path",
        type=Path,
        default=None,
        help="Existing so101_model_bundle_manifest_summary.json from the bundle checker.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Optional model bundle manifest. Used only when --manifest-summary-path is not supplied.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used when this smoke runs the bundle manifest checker child.",
    )
    parser.add_argument(
        "--require-ready-reviewed-model",
        action="store_true",
        help="Return nonzero when the reviewed model bundle is missing or not ready.",
    )
    return parser.parse_args()


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def executable_arg(path: Path) -> str:
    raw = str(path)
    if path.is_absolute() or "/" in raw:
        return str(normalize_path(path))
    return raw


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


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
    fieldnames = (
        "requirement_id",
        "category",
        "status",
        "source",
        "observed_value",
        "expected_value",
        "missing_inputs",
        "diagnostics",
        "notes",
    )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def checklist_row(
    requirement_id: str,
    category: str,
    ok: bool,
    source: str,
    observed_value: Any,
    expected_value: Any,
    *,
    missing_inputs: Any = None,
    diagnostics: Any = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "category": category,
        "status": "ok" if ok else "action_required",
        "source": source,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "missing_inputs": missing_inputs,
        "diagnostics": diagnostics,
        "notes": notes,
    }


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:
        return {
            "ok": False,
            "status": f"{label}_unavailable",
            "path": str(path),
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": f"{label}_not_json_object",
            "path": str(path),
            "diagnostics": ["expected_json_object"],
        }
    return payload


def run_manifest_checker(args: argparse.Namespace, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if args.manifest_summary_path is not None:
        summary_path = normalize_path(args.manifest_summary_path)
        summary = read_json_object(summary_path, label="manifest_summary")
        return summary, {
            "mode": "existing_summary",
            "summary_path": str(summary_path),
            "command": None,
            "returncode": None,
        }

    checker_dir = output_dir / "so101_model_bundle_manifest_check"
    summary_path = checker_dir / "so101_model_bundle_manifest_summary.json"
    command = [
        executable_arg(args.python),
        str(MANIFEST_CHECKER_PATH),
        "--output-dir",
        str(checker_dir),
        "--python",
        executable_arg(args.python),
    ]
    if args.manifest_path is not None:
        command.extend(["--manifest-path", str(args.manifest_path.expanduser())])

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    summary = read_json_object(summary_path, label="manifest_summary")
    if result.returncode != 0:
        summary = {
            "ok": False,
            "status": "model_bundle_manifest_checker_failed",
            "ready_for_model_backed_ik": False,
            "manifest_request": {
                "path": str(args.manifest_path.expanduser()) if args.manifest_path is not None else None,
                "status": "model_bundle_manifest_checker_failed",
            },
            "model_path": {"path": None, "exists": False, "diagnostics": ["checker_nonzero"]},
            "missing_inputs": ["model_bundle_manifest_checker_result"],
            "diagnostics": [{"returncode": result.returncode}],
        }
    return summary, {
        "mode": "child_checker",
        "summary_path": str(summary_path),
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def mujoco_names(module: Any, model: Any, obj_type: Any, count: int) -> list[str]:
    names: list[str] = []
    for index in range(count):
        name = module.mj_id2name(model, obj_type, index)
        if name:
            names.append(str(name))
    return names


def target_frame_presence(module: Any, model: Any, target_frame: str | None) -> dict[str, Any]:
    if not target_frame:
        return {"target_frame": target_frame, "present": False, "locations": [], "diagnostics": ["target_frame_missing"]}
    locations = []
    for label, obj_type in (
        ("body", module.mjtObj.mjOBJ_BODY),
        ("site", module.mjtObj.mjOBJ_SITE),
        ("geom", module.mjtObj.mjOBJ_GEOM),
    ):
        if module.mj_name2id(model, obj_type, target_frame) >= 0:
            locations.append(label)
    return {
        "target_frame": target_frame,
        "present": bool(locations),
        "locations": locations,
        "diagnostics": [] if locations else ["target_frame_not_found_in_mujoco_model"],
    }


def inspect_mujoco_model(model_path: Path, target_frame: str | None) -> dict[str, Any]:
    try:
        import mujoco
    except Exception as exc:
        return {
            "ok": False,
            "status": "mujoco_import_failed",
            "model_path": str(model_path),
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }

    if not model_path.is_file():
        return {
            "ok": False,
            "status": "model_path_unavailable",
            "model_path": str(model_path),
            "diagnostics": ["model_path_not_file"],
        }

    try:
        model = mujoco.MjModel.from_xml_path(str(model_path))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
    except Exception as exc:
        return {
            "ok": False,
            "status": "mujoco_model_load_failed",
            "model_path": str(model_path),
            "suffix": model_path.suffix.lower(),
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }

    joint_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
    site_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_SITE, model.nsite)
    body_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
    missing_joints = sorted(set(SO101_JOINTS) - set(joint_names))
    target_presence = target_frame_presence(mujoco, model, target_frame)
    joint_ranges = {}
    for joint_name in SO101_JOINTS:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id >= 0:
            joint_ranges[joint_name] = [float(value) for value in model.jnt_range[joint_id]]
    return {
        "ok": not missing_joints and bool(target_presence["present"]),
        "status": "mujoco_model_loaded",
        "model_path": str(model_path),
        "suffix": model_path.suffix.lower(),
        "nq": int(model.nq),
        "nv": int(model.nv),
        "joint_names": joint_names,
        "site_names": site_names,
        "body_names": body_names,
        "missing_joints": missing_joints,
        "target_frame_presence": target_presence,
        "joint_ranges": joint_ranges,
    }


def manifest_limit_pair_deg(value: Any) -> tuple[float, float] | None:
    if isinstance(value, list) and len(value) == 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    if isinstance(value, dict):
        lower_key = "lower" if "lower" in value else "min" if "min" in value else None
        upper_key = "upper" if "upper" in value else "max" if "max" in value else None
        if lower_key is None or upper_key is None:
            return None
        try:
            return float(value[lower_key]), float(value[upper_key])
        except (TypeError, ValueError):
            return None
    return None


def joint_limit_model_consistency(
    manifest_summary: dict[str, Any],
    model_load: dict[str, Any],
) -> dict[str, Any]:
    manifest_joint_limits = manifest_value(manifest_summary, "joint_limits")
    manifest_values = manifest_joint_limits.get("value")
    model_ranges = model_load.get("joint_ranges")
    if not isinstance(manifest_values, dict):
        return {
            "ok": False,
            "status": "manifest_joint_limits_unavailable",
            "diagnostics": ["manifest_joint_limits_not_object"],
            "compared_joints": [],
            "mismatched_joints": [],
            "skipped_joints": [],
        }
    if not isinstance(model_ranges, dict):
        return {
            "ok": False,
            "status": "mujoco_joint_ranges_unavailable",
            "diagnostics": ["mujoco_joint_ranges_not_object"],
            "compared_joints": [],
            "mismatched_joints": [],
            "skipped_joints": [],
        }

    compared: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for joint_name in SO101_BODY_JOINTS:
        manifest_pair = manifest_limit_pair_deg(manifest_values.get(joint_name))
        model_pair = model_ranges.get(joint_name)
        if manifest_pair is None:
            diagnostics.append(f"manifest_joint_limit_missing_or_invalid:{joint_name}")
            mismatches.append({"joint": joint_name, "reason": "manifest_limit_missing_or_invalid"})
            continue
        if not isinstance(model_pair, list) or len(model_pair) != 2:
            diagnostics.append(f"mujoco_joint_range_missing_or_invalid:{joint_name}")
            mismatches.append({"joint": joint_name, "reason": "mujoco_range_missing_or_invalid"})
            continue
        manifest_rad = [manifest_pair[0] * math.pi / 180.0, manifest_pair[1] * math.pi / 180.0]
        try:
            model_rad = [float(model_pair[0]), float(model_pair[1])]
        except (TypeError, ValueError):
            diagnostics.append(f"mujoco_joint_range_non_numeric:{joint_name}")
            mismatches.append({"joint": joint_name, "reason": "mujoco_range_non_numeric"})
            continue
        deltas = [abs(manifest_rad[index] - model_rad[index]) for index in range(2)]
        record = {
            "joint": joint_name,
            "manifest_limits_deg": [manifest_pair[0], manifest_pair[1]],
            "manifest_limits_rad": manifest_rad,
            "mujoco_limits_rad": model_rad,
            "delta_rad": deltas,
            "tolerance_rad": JOINT_LIMIT_RANGE_TOLERANCE_RAD,
            "ok": all(delta <= JOINT_LIMIT_RANGE_TOLERANCE_RAD for delta in deltas),
        }
        compared.append(record)
        if not record["ok"]:
            diagnostics.append(f"joint_limit_mismatch:{joint_name}")
            mismatches.append(record)

    skipped_joints = [
        {
            "joint": "gripper",
            "reason": "manifest gripper limits are percent-style command limits while MuJoCo gripper ranges may be slide meters.",
        }
    ]
    return {
        "ok": not mismatches,
        "status": "joint_limits_match_mujoco_model" if not mismatches else "joint_limits_mismatch_mujoco_model",
        "compared_joints": compared,
        "mismatched_joints": mismatches,
        "skipped_joints": skipped_joints,
        "diagnostics": diagnostics,
        "notes": [
            "Body-joint manifest limits are declared in degrees and compared to MuJoCo joint ranges after radians conversion.",
            "The gripper command range is not compared here because the manifest uses percent-style command limits while MuJoCo may use a slide-joint opening in meters.",
        ],
    }


def validate_simrobot_motion(model_path: Path) -> dict[str, Any]:
    try:
        from lerobot.sim import SimRobot, SimRobotConfig
    except Exception as exc:
        return {
            "ok": False,
            "status": "simrobot_import_failed",
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }

    robot = SimRobot(
        SimRobotConfig(
            cameras={},
            use_mujoco=True,
            mujoco_model_path=model_path,
            initial_positions={"gripper": 95.0},
        )
    )
    try:
        robot.connect()
    except Exception as exc:
        return {
            "ok": False,
            "status": "simrobot_connect_failed",
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }

    try:
        initial_status = robot.sim_status()
        backend = getattr(robot, "_mujoco_backend", None)
        before_qpos = {}
        if backend is not None:
            before_qpos = {
                joint: float(backend.data.qpos[qpos_addr])
                for joint, qpos_addr in backend.joint_qpos_addr.items()
            }
        action = {
            **{f"{joint}.pos": target for joint, target in BODY_JOINT_TARGETS_DEG.items()},
            "gripper.pos": 78.0,
        }
        sent_action = robot.send_action(action)
        after_status = robot.sim_status()
        backend = getattr(robot, "_mujoco_backend", None)
        motion_checks = []
        if backend is not None:
            for joint, target_deg in BODY_JOINT_TARGETS_DEG.items():
                qpos_addr = backend.joint_qpos_addr.get(joint)
                if qpos_addr is None:
                    motion_checks.append(
                        {
                            "joint": joint,
                            "ok": False,
                            "reason": "joint_not_mapped",
                            "target_deg": target_deg,
                        }
                    )
                    continue
                observed_rad = float(backend.data.qpos[qpos_addr])
                expected_rad = float(target_deg) * 3.141592653589793 / 180.0
                motion_checks.append(
                    {
                        "joint": joint,
                        "ok": abs(observed_rad - expected_rad) <= 1e-6,
                        "before_qpos": before_qpos.get(joint),
                        "after_qpos": observed_rad,
                        "expected_qpos": expected_rad,
                        "target_deg": target_deg,
                    }
                )
        mapped = set(after_status.get("mapped_joints") or [])
        ok = (
            bool(initial_status.get("ok"))
            and bool(after_status.get("ok"))
            and after_status.get("fallback") is None
            and set(SO101_JOINTS).issubset(mapped)
            and all(check.get("ok") for check in motion_checks)
        )
        return {
            "ok": ok,
            "status": "simrobot_motion_checked" if ok else "simrobot_motion_needs_follow_up",
            "initial_status": initial_status,
            "after_status": after_status,
            "sent_action": sent_action,
            "motion_checks": motion_checks,
            "mapped_joints": sorted(mapped),
            "missing_mapped_joints": sorted(set(SO101_JOINTS) - mapped),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "simrobot_motion_failed",
            "initial_status": robot.sim_status(),
            "diagnostics": [f"{type(exc).__name__}: {exc}"],
        }
    finally:
        try:
            robot.disconnect()
        except Exception:
            pass


def manifest_value(summary: dict[str, Any], key: str) -> dict[str, Any]:
    value = summary.get(key)
    return value if isinstance(value, dict) else {}


def motion_authority(
    *,
    motion_checked: bool,
    physical_authority_ready: bool,
    fixture_ready: bool,
    manifest_ready: bool,
) -> dict[str, Any]:
    if not manifest_ready:
        status = "not_checked_manifest_not_ready"
    elif motion_checked and physical_authority_ready:
        status = "physical_reviewed_model_motion_checked"
    elif motion_checked and fixture_ready:
        status = "hardware_free_fixture_motion_checked_not_physical_so101_authority"
    elif motion_checked:
        status = "motion_checked_authority_incomplete"
    elif physical_authority_ready:
        status = "physical_reviewed_model_motion_failed"
    elif fixture_ready:
        status = "hardware_free_fixture_motion_failed"
    else:
        status = "motion_failed_authority_incomplete"
    return {
        "status": status,
        "physical_reviewed_model_motion_checked": bool(motion_checked and physical_authority_ready),
        "hardware_free_fixture_motion_checked": bool(motion_checked and fixture_ready),
        "motion_evidence_not_physical_so101_authority": bool(motion_checked and not physical_authority_ready),
        "notes": [
            "reviewed_model_motion_checked is the compatibility flag for MuJoCo/SimRobot motion.",
            "physical_reviewed_model_motion_checked is true only when the manifest authority is physical SO-101 authority.",
            "hardware_free_fixture_motion_checked is automation coverage only and is not physical SO-101 truth.",
        ],
    }


def build_not_ready_summary(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    manifest_summary: dict[str, Any],
    manifest_source: dict[str, Any],
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_request = manifest_value(manifest_summary, "manifest_request")
    model_path = manifest_value(manifest_summary, "model_path")
    ready = manifest_summary.get("ready_for_model_backed_ik") is True
    physical_authority_ready = bool(manifest_summary.get("physical_so101_model_authority_ready"))
    fixture_ready = bool(manifest_summary.get("hardware_free_regression_fixture_ready"))
    motion_authority_summary = motion_authority(
        motion_checked=False,
        physical_authority_ready=physical_authority_ready,
        fixture_ready=fixture_ready,
        manifest_ready=ready,
    )
    missing_inputs = manifest_summary.get("missing_inputs")
    missing_inputs = missing_inputs if isinstance(missing_inputs, list) else ["ready_reviewed_model_bundle"]
    ok = not args.require_ready_reviewed_model
    status = "reviewed_mujoco_bundle_ready_unchecked" if ready else "reviewed_mujoco_bundle_not_ready"
    if not ok:
        status = "reviewed_mujoco_bundle_required_but_not_ready"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": status,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "manifest_source": manifest_source,
        "manifest_status": manifest_summary.get("status") or manifest_request.get("status"),
        "manifest_request": manifest_request,
        "model_path": model_path,
        "asset_roots": manifest_value(manifest_summary, "asset_roots"),
        "authority": manifest_value(manifest_summary, "authority"),
        "authority_status": manifest_value(manifest_summary, "authority").get("status"),
        "authority_diagnostics": manifest_value(manifest_summary, "authority").get("diagnostics", []),
        "provenance": manifest_value(manifest_summary, "provenance"),
        "provenance_status": manifest_value(manifest_summary, "provenance").get("status"),
        "provenance_diagnostics": manifest_value(manifest_summary, "provenance").get("diagnostics", []),
        "joint_limits": manifest_value(manifest_summary, "joint_limits"),
        "mesh_assets": manifest_value(manifest_summary, "mesh_assets"),
        "target_frame": manifest_value(manifest_summary, "target_frame"),
        "tcp_offset": manifest_value(manifest_summary, "tcp_offset"),
        "base_to_board_alignment": manifest_value(manifest_summary, "base_to_board_alignment"),
        "model_authority": manifest_summary.get("model_authority") or "reviewed_bundle_required",
        "physical_so101_model_authority_ready": physical_authority_ready,
        "hardware_free_regression_fixture_ready": fixture_ready,
        "synthetic_fixture_authority_fields": manifest_summary.get("synthetic_fixture_authority_fields") or [],
        "ready_for_model_backed_ik": ready,
        "reviewed_model_motion_checked": False,
        "motion_authority_status": motion_authority_summary["status"],
        "physical_reviewed_model_motion_checked": motion_authority_summary[
            "physical_reviewed_model_motion_checked"
        ],
        "hardware_free_fixture_motion_checked": motion_authority_summary[
            "hardware_free_fixture_motion_checked"
        ],
        "motion_evidence_not_physical_so101_authority": motion_authority_summary[
            "motion_evidence_not_physical_so101_authority"
        ],
        "motion_authority": motion_authority_summary,
        "require_ready_reviewed_model": bool(args.require_ready_reviewed_model),
        "missing_inputs": sorted(set(str(item) for item in missing_inputs)),
        "dependencies": {
            "mujoco": module_available("mujoco"),
            "numpy": module_available("numpy"),
        },
        "artifacts": artifacts,
        "limitations": [
            "This gate is hardware-free and never opens robot motors, serial ports, cameras, GUI flows, OpenAI calls, or network resources.",
            "When no ready reviewed manifest exists, the gate records the missing inputs without inventing model authority.",
            "MuJoCo motion is attempted only after the bundle manifest reports ready_for_model_backed_ik true.",
        ],
        "next_required_for_goal": manifest_summary.get("next_required_for_goal") or [
            {
                "priority": 1,
                "missing_input": "ready_reviewed_model_bundle",
                "action_id": "make_reviewed_manifest_ready",
                "gate": "reviewed_model_authority",
                "title": "Make the reviewed SO-101 manifest ready",
                "detail": "Make the manifest checker report ready_for_model_backed_ik true, then rerun the reviewed MuJoCo bundle gate.",
            }
        ],
    }
    rows = [
        checklist_row(
            "reviewed_manifest_ready",
            "manifest",
            ready,
            "so101_model_bundle_manifest_summary",
            {"status": summary["manifest_status"], "ready_for_model_backed_ik": ready},
            {"ready_for_model_backed_ik": True},
            missing_inputs=summary["missing_inputs"] if not ready else None,
            diagnostics=manifest_summary.get("field_checks"),
            notes="Default CI keeps this non-failing until a reviewed bundle is supplied.",
        ),
        checklist_row(
            "mujoco_motion_check",
            "mujoco",
            False,
            "reviewed_bundle_gate",
            "not_attempted",
            "model_load_and_joint_motion_checked",
            missing_inputs=["ready_reviewed_model_bundle"],
            diagnostics=["manifest_not_ready_for_mujoco_motion"],
            notes="Motion verification is deliberately skipped until the manifest is ready.",
        ),
    ]
    return summary, rows


def build_ready_summary(
    *,
    args: argparse.Namespace,
    manifest_summary: dict[str, Any],
    manifest_source: dict[str, Any],
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    model_path_info = manifest_value(manifest_summary, "model_path")
    target_frame = manifest_value(manifest_summary, "target_frame")
    model_path_raw = model_path_info.get("path")
    model_path = normalize_path(Path(model_path_raw)) if isinstance(model_path_raw, str) and model_path_raw else None
    dependencies = {
        "mujoco": module_available("mujoco"),
        "numpy": module_available("numpy"),
    }

    model_load = (
        inspect_mujoco_model(model_path, target_frame.get("value")) if model_path is not None else {
            "ok": False,
            "status": "model_path_missing",
            "diagnostics": ["manifest_model_path_missing"],
        }
    )
    simrobot_motion = validate_simrobot_motion(model_path) if model_path is not None and model_load.get("ok") else {
        "ok": False,
        "status": "not_attempted",
        "diagnostics": ["mujoco_model_load_not_ok"],
    }
    joint_limit_consistency = joint_limit_model_consistency(manifest_summary, model_load)
    motion_ok = (
        bool(model_load.get("ok"))
        and bool(simrobot_motion.get("ok"))
        and bool(joint_limit_consistency.get("ok"))
    )
    physical_authority_ready = bool(manifest_summary.get("physical_so101_model_authority_ready"))
    fixture_ready = bool(manifest_summary.get("hardware_free_regression_fixture_ready"))
    motion_authority_summary = motion_authority(
        motion_checked=motion_ok,
        physical_authority_ready=physical_authority_ready,
        fixture_ready=fixture_ready,
        manifest_ready=True,
    )
    missing_inputs = []
    if not dependencies["mujoco"]:
        missing_inputs.append("mujoco")
    if not model_load.get("ok"):
        missing_inputs.append("mujoco_model_load")
    if not simrobot_motion.get("ok"):
        missing_inputs.append("simrobot_mujoco_joint_motion")
    if not joint_limit_consistency.get("ok"):
        missing_inputs.append("joint_limit_model_consistency")

    summary = {
        "schema": SCHEMA,
        "ok": motion_ok,
        "status": "reviewed_mujoco_bundle_motion_checked" if motion_ok else "reviewed_mujoco_bundle_motion_failed",
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "repo_root": str(REPO_ROOT),
        "manifest_source": manifest_source,
        "manifest_status": manifest_summary.get("status"),
        "manifest_request": manifest_value(manifest_summary, "manifest_request"),
        "model_path": model_path_info,
        "asset_roots": manifest_value(manifest_summary, "asset_roots"),
        "authority": manifest_value(manifest_summary, "authority"),
        "authority_status": manifest_value(manifest_summary, "authority").get("status"),
        "authority_diagnostics": manifest_value(manifest_summary, "authority").get("diagnostics", []),
        "provenance": manifest_value(manifest_summary, "provenance"),
        "provenance_status": manifest_value(manifest_summary, "provenance").get("status"),
        "provenance_diagnostics": manifest_value(manifest_summary, "provenance").get("diagnostics", []),
        "joint_limits": manifest_value(manifest_summary, "joint_limits"),
        "mesh_assets": manifest_value(manifest_summary, "mesh_assets"),
        "target_frame": target_frame,
        "tcp_offset": manifest_value(manifest_summary, "tcp_offset"),
        "base_to_board_alignment": manifest_value(manifest_summary, "base_to_board_alignment"),
        "model_authority": manifest_summary.get("model_authority") or "reviewed_so101_model_bundle_manifest",
        "physical_so101_model_authority_ready": physical_authority_ready,
        "hardware_free_regression_fixture_ready": fixture_ready,
        "synthetic_fixture_authority_fields": manifest_summary.get("synthetic_fixture_authority_fields") or [],
        "ready_for_model_backed_ik": True,
        "reviewed_model_motion_checked": motion_ok,
        "motion_authority_status": motion_authority_summary["status"],
        "physical_reviewed_model_motion_checked": motion_authority_summary[
            "physical_reviewed_model_motion_checked"
        ],
        "hardware_free_fixture_motion_checked": motion_authority_summary[
            "hardware_free_fixture_motion_checked"
        ],
        "motion_evidence_not_physical_so101_authority": motion_authority_summary[
            "motion_evidence_not_physical_so101_authority"
        ],
        "motion_authority": motion_authority_summary,
        "require_ready_reviewed_model": bool(args.require_ready_reviewed_model),
        "dependencies": dependencies,
        "mujoco_model_load": model_load,
        "joint_limit_model_consistency": joint_limit_consistency,
        "sim_robot_mujoco_sync": simrobot_motion,
        "missing_inputs": sorted(set(missing_inputs)),
        "artifacts": artifacts,
        "limitations": [
            "This gate proves hardware-free MuJoCo load and SimRobot joint-state motion for the reviewed bundle; it does not prove physical calibration by itself.",
            "Contact-valid grasp/lift/place still needs separate gripper collision and task probes after TCP/base-to-board alignment are reviewed.",
        ],
        "next_required_for_goal": [] if motion_ok else [
            "Fix reviewed model loading or joint naming until every SO-101 joint maps in MuJoCo.",
            "Re-run the suite before trusting model-backed IK or training rollouts.",
        ],
    }
    rows = [
        checklist_row(
            "reviewed_manifest_ready",
            "manifest",
            True,
            "so101_model_bundle_manifest_summary",
            {"status": summary["manifest_status"], "ready_for_model_backed_ik": True},
            {"ready_for_model_backed_ik": True},
        ),
        checklist_row(
            "mujoco_dependency",
            "runtime",
            dependencies["mujoco"],
            "python_import",
            dependencies,
            {"mujoco": True},
            missing_inputs=None if dependencies["mujoco"] else ["mujoco"],
        ),
        checklist_row(
            "mujoco_model_load",
            "mujoco",
            bool(model_load.get("ok")),
            "mujoco.MjModel.from_xml_path",
            model_load,
            {"ok": True, "missing_joints": []},
            missing_inputs=None if model_load.get("ok") else ["mujoco_model_load"],
            diagnostics=model_load.get("diagnostics") or model_load.get("missing_joints"),
        ),
        checklist_row(
            "target_frame_present",
            "model_contract",
            bool((model_load.get("target_frame_presence") or {}).get("present")),
            "manifest.target_frame",
            model_load.get("target_frame_presence"),
            {"present": True},
            missing_inputs=None if (model_load.get("target_frame_presence") or {}).get("present") else ["target_frame"],
        ),
        checklist_row(
            "simrobot_joint_mapping",
            "simrobot",
            not simrobot_motion.get("missing_mapped_joints"),
            "SimRobot.sim_status",
            simrobot_motion.get("mapped_joints"),
            list(SO101_JOINTS),
            missing_inputs=simrobot_motion.get("missing_mapped_joints") or None,
        ),
        checklist_row(
            "joint_limit_model_consistency",
            "mujoco",
            bool(joint_limit_consistency.get("ok")),
            "manifest.joint_limits_deg vs MuJoCo jnt_range",
            joint_limit_consistency,
            {"status": "joint_limits_match_mujoco_model"},
            missing_inputs=None if joint_limit_consistency.get("ok") else ["joint_limit_model_consistency"],
            diagnostics=joint_limit_consistency.get("diagnostics"),
            notes="Body-joint bounds must match the loaded MuJoCo model before model-backed motion evidence is trusted.",
        ),
        checklist_row(
            "simrobot_motion",
            "simrobot",
            bool(simrobot_motion.get("ok")),
            "SimRobot.send_action",
            simrobot_motion,
            {"fallback": None, "all_body_joint_qpos_match_targets": True},
            missing_inputs=None if simrobot_motion.get("ok") else ["simrobot_mujoco_joint_motion"],
            diagnostics=simrobot_motion.get("diagnostics"),
        ),
    ]
    return summary, rows


def write_readme(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# SO-101 Reviewed MuJoCo Bundle Gate",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `ok`: `{str(summary['ok']).lower()}`",
        f"- `manifest_status`: `{summary.get('manifest_status')}`",
        f"- `model_authority`: `{summary.get('model_authority')}`",
        f"- `physical_so101_model_authority_ready`: `{str(summary.get('physical_so101_model_authority_ready')).lower()}`",
        f"- `hardware_free_regression_fixture_ready`: `{str(summary.get('hardware_free_regression_fixture_ready')).lower()}`",
        f"- `ready_for_model_backed_ik`: `{str(summary.get('ready_for_model_backed_ik')).lower()}`",
        f"- `reviewed_model_motion_checked`: `{str(summary.get('reviewed_model_motion_checked')).lower()}`",
        f"- `motion_authority_status`: `{summary.get('motion_authority_status')}`",
        f"- `physical_reviewed_model_motion_checked`: `{str(summary.get('physical_reviewed_model_motion_checked')).lower()}`",
        f"- `hardware_free_fixture_motion_checked`: `{str(summary.get('hardware_free_fixture_motion_checked')).lower()}`",
        f"- `motion_evidence_not_physical_so101_authority`: `{str(summary.get('motion_evidence_not_physical_so101_authority')).lower()}`",
        f"- `model_path`: `{summary.get('model_path', {}).get('path') if isinstance(summary.get('model_path'), dict) else None}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `checklist_csv`: `{summary['artifacts']['checklist_csv']}`",
        "",
        "## Checklist",
        "",
        "| Requirement | Status | Notes |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        notes = row.get("notes") or row.get("diagnostics") or row.get("missing_inputs") or ""
        lines.append(
            "| `{requirement}` | `{status}` | {notes} |".format(
                requirement=row["requirement_id"],
                status=row["status"],
                notes=str(notes).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "This gate is the automation bridge from reviewed model-bundle readiness to MuJoCo motion.",
            "It does not replace later contact-validated gripper grasp/lift/place checks.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_NAME
    csv_path = output_dir / CHECKLIST_NAME
    readme_path = output_dir / README_NAME
    artifacts = {
        "summary_json": str(summary_path),
        "checklist_csv": str(csv_path),
        "readme": str(readme_path),
    }

    manifest_summary, manifest_source = run_manifest_checker(args, output_dir)
    if manifest_summary.get("ready_for_model_backed_ik") is True:
        summary, rows = build_ready_summary(
            args=args,
            manifest_summary=manifest_summary,
            manifest_source=manifest_source,
            artifacts=artifacts,
        )
    else:
        summary, rows = build_not_ready_summary(
            args=args,
            output_dir=output_dir,
            manifest_summary=manifest_summary,
            manifest_source=manifest_source,
            artifacts=artifacts,
        )

    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    write_readme(readme_path, summary, rows)
    print(
        json.dumps(
            {
                "ok": summary["ok"],
                "status": summary["status"],
                "model_authority": summary["model_authority"],
                "physical_so101_model_authority_ready": summary["physical_so101_model_authority_ready"],
                "hardware_free_regression_fixture_ready": summary["hardware_free_regression_fixture_ready"],
                "ready_for_model_backed_ik": summary["ready_for_model_backed_ik"],
                "reviewed_model_motion_checked": summary["reviewed_model_motion_checked"],
                "motion_authority_status": summary["motion_authority_status"],
                "physical_reviewed_model_motion_checked": summary["physical_reviewed_model_motion_checked"],
                "hardware_free_fixture_motion_checked": summary["hardware_free_fixture_motion_checked"],
                "motion_evidence_not_physical_so101_authority": summary[
                    "motion_evidence_not_physical_so101_authority"
                ],
                "summary_json": str(summary_path),
            },
            sort_keys=True,
        )
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
