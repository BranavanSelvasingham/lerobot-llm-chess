#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_grasp_probe"
SUMMARY_NAME = "so101_mujoco_grasp_probe_summary.json"
ROWS_NAME = "so101_mujoco_grasp_probe_rows.csv"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.so101_mujoco_grasp_probe.v1"
CONTACT_FIXTURE_PIECE_RADIUS_M = 0.016
CONTACT_FIXTURE_PIECE_MASS_KG = 0.005
CONTACT_FIXTURE_CONDIM = 6
CONTACT_FIXTURE_FRICTION = (2.0, 0.4, 0.02)
CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M = -0.008
CONTACT_FIXTURE_GRIPPER_CLOSE_M = -0.004
CONTACT_FIXTURE_GRIPPER_KP = 50.0
LIFT_Z_THRESHOLD_M = 0.02
TRANSFER_PAN_RAD = math.radians(4.0)
TRANSFER_XY_THRESHOLD_M = 0.015
TARGET_XY_TOLERANCE_M = 0.01


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe gripper/piece contact and the current grasp/lift/place physics gap "
            "in the development SO-101 MuJoCo chess scene."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stage",
        "sim_time_s",
        "piece_x",
        "piece_y",
        "piece_z",
        "site_x",
        "site_y",
        "site_z",
        "gripper_qpos_m",
        "fixed_finger_contact_count",
        "moving_finger_contact_count",
        "gripper_contact_count",
        "board_contact_count",
        "any_contact_count",
        "piece_z_delta_m",
        "target_xy_error_m",
        "transfer_xy_m",
        "manual_piece_pose_set",
        "ok",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def object_id(module: Any, model: Any, kind: Any, name: str) -> int:
    object_id_value = module.mj_name2id(model, kind, name)
    if object_id_value < 0:
        raise AssertionError(f"{name} is missing from generated model.")
    return int(object_id_value)


def joint_qpos_addr(module: Any, model: Any, joint_name: str) -> int:
    joint_id = object_id(module, model, module.mjtObj.mjOBJ_JOINT, joint_name)
    return int(model.jnt_qposadr[joint_id])


def joint_qpos(module: Any, model: Any, data: Any, joint_name: str) -> float:
    return float(data.qpos[joint_qpos_addr(module, model, joint_name)])


def set_joint_qpos(module: Any, model: Any, data: Any, joint_name: str, value: float) -> None:
    data.qpos[joint_qpos_addr(module, model, joint_name)] = float(value)


def actuator_id(module: Any, model: Any, actuator_name: str) -> int | None:
    actuator = module.mj_name2id(model, module.mjtObj.mjOBJ_ACTUATOR, actuator_name)
    return int(actuator) if actuator >= 0 else None


def set_actuator_target(module: Any, model: Any, data: Any, actuator_name: str, value: float) -> None:
    actuator = actuator_id(module, model, actuator_name)
    if actuator is not None:
        data.ctrl[actuator] = float(value)


def set_freejoint_pose(
    module: Any,
    model: Any,
    data: Any,
    joint_name: str,
    *,
    pos: tuple[float, float, float],
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
) -> None:
    qpos_addr = joint_qpos_addr(module, model, joint_name)
    data.qpos[qpos_addr : qpos_addr + 7] = [*pos, *quat]


def geom_position(module: Any, model: Any, data: Any, geom_name: str) -> tuple[float, float, float]:
    geom_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, geom_name)
    values = data.geom_xpos[geom_id]
    return float(values[0]), float(values[1]), float(values[2])


def site_position(module: Any, model: Any, data: Any, site_name: str) -> tuple[float, float, float]:
    site_id = object_id(module, model, module.mjtObj.mjOBJ_SITE, site_name)
    values = data.site_xpos[site_id]
    return float(values[0]), float(values[1]), float(values[2])


def body_position(module: Any, model: Any, data: Any, body_name: str) -> tuple[float, float, float]:
    body_id = object_id(module, model, module.mjtObj.mjOBJ_BODY, body_name)
    values = data.xpos[body_id]
    return float(values[0]), float(values[1]), float(values[2])


def contact_counts(module: Any, model: Any, data: Any) -> dict[str, int]:
    piece_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "piece_source_collision")
    fixed_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "gripper_fixed_finger_collision")
    moving_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "gripper_moving_finger_collision")
    board_id = object_id(module, model, module.mjtObj.mjOBJ_GEOM, "chess_board_collision")
    fixed = 0
    moving = 0
    board = 0
    for index in range(data.ncon):
        contact = data.contact[index]
        pair = {int(contact.geom1), int(contact.geom2)}
        if pair == {piece_id, fixed_id}:
            fixed += 1
        if pair == {piece_id, moving_id}:
            moving += 1
        if pair == {piece_id, board_id}:
            board += 1
    return {
        "fixed_finger_contact_count": fixed,
        "moving_finger_contact_count": moving,
        "gripper_contact_count": fixed + moving,
        "board_contact_count": board,
        "any_contact_count": int(data.ncon),
    }


def step(module: Any, model: Any, data: Any, steps: int) -> None:
    for _ in range(steps):
        module.mj_step(model, data)


def midpoint(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)


def record_stage(
    module: Any,
    model: Any,
    data: Any,
    *,
    stage: str,
    manual_piece_pose_set: bool,
    initial_piece_z: float,
    initial_piece_xy: tuple[float, float],
    target_xy: tuple[float, float],
) -> dict[str, Any]:
    piece = body_position(module, model, data, "piece_source")
    site = site_position(module, model, data, "gripper_frame_link")
    contacts = contact_counts(module, model, data)
    target_xy_error = math.hypot(piece[0] - target_xy[0], piece[1] - target_xy[1])
    transfer_xy = math.hypot(piece[0] - initial_piece_xy[0], piece[1] - initial_piece_xy[1])
    return {
        "stage": stage,
        "sim_time_s": float(data.time),
        "piece_x": piece[0],
        "piece_y": piece[1],
        "piece_z": piece[2],
        "site_x": site[0],
        "site_y": site[1],
        "site_z": site[2],
        "gripper_qpos_m": joint_qpos(module, model, data, "gripper"),
        **contacts,
        "piece_z_delta_m": piece[2] - initial_piece_z,
        "target_xy_error_m": target_xy_error,
        "transfer_xy_m": transfer_xy,
        "manual_piece_pose_set": manual_piece_pose_set,
        "ok": True,
    }


def find_lift_target(module: Any, model: Any, data: Any) -> dict[str, float]:
    saved_qpos = data.qpos.copy()
    saved_qvel = data.qvel.copy()
    baseline_z = site_position(module, model, data, "gripper_frame_link")[2]
    candidates = [
        {"shoulder_lift": math.radians(-15), "elbow_flex": math.radians(20), "wrist_flex": math.radians(-5)},
        {"shoulder_lift": math.radians(-25), "elbow_flex": math.radians(30), "wrist_flex": math.radians(-10)},
        {"shoulder_lift": math.radians(-35), "elbow_flex": math.radians(45), "wrist_flex": math.radians(-15)},
        {"shoulder_lift": math.radians(-20), "elbow_flex": math.radians(10), "wrist_flex": math.radians(5)},
    ]
    best = candidates[0]
    best_delta = float("-inf")
    for candidate in candidates:
        data.qpos[:] = saved_qpos
        data.qvel[:] = saved_qvel
        for joint, value in candidate.items():
            set_joint_qpos(module, model, data, joint, value)
        module.mj_forward(model, data)
        delta = site_position(module, model, data, "gripper_frame_link")[2] - baseline_z
        if delta > best_delta:
            best = candidate
            best_delta = delta
    data.qpos[:] = saved_qpos
    data.qvel[:] = saved_qvel
    module.mj_forward(model, data)
    return best


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 MuJoCo Grasp Probe",
        "",
        "This smoke records the current gripper contact and grasp/lift/place physics state in the generated development MJCF scene.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Gripper contact observed: `{summary['gripper_contact_observed']}`",
        f"- Two-finger contact observed: `{summary['two_finger_contact_observed']}`",
        f"- Lift verified: `{summary.get('lift_verified')}`",
        f"- Transfer verified: `{summary.get('transfer_verified')}`",
        f"- Place verified: `{summary.get('place_without_manual_piece_pose_verified')}`",
        f"- Lift/place physics verified: `{summary['lift_place_physics_verified']}`",
        f"- Release contact cleared: `{summary['release_contact_cleared']}`",
        f"- Physical SO-101 authority: `{summary.get('observed_evidence_is_physical_so101_authority')}`",
        f"- Policy-training authority: `{summary.get('observed_evidence_is_policy_training_authority')}`",
        f"- Ready for policy training: `{summary.get('ready_for_policy_training')}`",
        f"- Final target XY error m: `{summary.get('final_target_xy_error_m')}`",
        f"- Rows CSV: `{summary['artifacts']['rows_csv']}`",
        "",
        "The setup manually places a fixture piece between the development gripper fingers once.",
        "The lift, transfer, lower, release, and retreat sequence then leaves the piece free and does not manually move its freejoint.",
        "A true `lift_place_physics_verified` value is development-fixture evidence only; reviewed SO-101 model authority remains required before serious policy training.",
    ]
    path.write_text("\n".join(lines) + "\n")


def missing_dependency_summary(args: argparse.Namespace, deps: dict[str, bool], missing: list[str]) -> dict[str, Any]:
    summary_path = args.output_dir / SUMMARY_NAME
    rows_path = args.output_dir / ROWS_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    readme_path = args.output_dir / README_NAME
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "missing_runtime_dependencies",
        "missing_dependencies": missing,
        "dependencies": deps,
        "probe_count": 0,
        "model_authority": None,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "gripper_contact_observed": False,
        "two_finger_contact_observed": False,
        "lift_verified": False,
        "transfer_verified": False,
        "place_without_manual_piece_pose_verified": False,
        "lift_place_physics_verified": False,
        "release_contact_cleared": False,
        "final_board_contact_observed": False,
        "final_target_xy_error_m": None,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
        "manual_piece_pose_used_for_fixture": False,
        "manual_piece_pose_used_after_fixture": False,
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    deps = {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "mujoco": module_available("mujoco"),
    }
    summary_path = args.output_dir / SUMMARY_NAME
    rows_path = args.output_dir / ROWS_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    readme_path = args.output_dir / README_NAME
    missing = [name for name, available in deps.items() if not available]
    if missing:
        summary = missing_dependency_summary(args, deps, missing)
        write_json(summary_path, summary)
        write_rows(rows_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    import mujoco

    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        square_center_world_m,
        write_so101_development_mjcf,
    )

    config = SO101DevelopmentMJCFConfig(
        piece_square="e4",
        target_square="e5",
        contact_condim=CONTACT_FIXTURE_CONDIM,
        contact_friction=CONTACT_FIXTURE_FRICTION,
        gripper_min_closure_m=CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M,
        gripper_actuator_kp=CONTACT_FIXTURE_GRIPPER_KP,
        piece_radius_m=CONTACT_FIXTURE_PIECE_RADIUS_M,
        piece_mass_kg=CONTACT_FIXTURE_PIECE_MASS_KG,
    )
    manifest = write_so101_development_mjcf(model_path, config, manifest_path=manifest_path)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)

    gripper_joint_id = object_id(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, "gripper")
    gripper_open_m = float(model.jnt_range[gripper_joint_id][1])
    gripper_close_m = CONTACT_FIXTURE_GRIPPER_CLOSE_M
    target_x, target_y, target_board_z = square_center_world_m(config.target_square, config)
    target_xy = (target_x, target_y)
    expected_place_z = target_board_z + config.piece_height_m / 2.0
    set_joint_qpos(mujoco, model, data, "gripper", gripper_close_m)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    mujoco.mj_forward(model, data)
    closed_midpoint = midpoint(
        geom_position(mujoco, model, data, "gripper_fixed_finger_collision"),
        geom_position(mujoco, model, data, "gripper_moving_finger_collision"),
    )

    set_joint_qpos(mujoco, model, data, "gripper", gripper_open_m)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_open_m)
    set_freejoint_pose(mujoco, model, data, "piece_source_freejoint", pos=closed_midpoint)
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    initial_piece = body_position(mujoco, model, data, "piece_source")
    initial_piece_z = initial_piece[2]
    initial_piece_xy = (initial_piece[0], initial_piece[1])
    rows = [
        record_stage(
            mujoco,
            model,
            data,
            stage="manual_fixture_piece_between_open_fingers",
            manual_piece_pose_set=True,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    ]

    set_joint_qpos(mujoco, model, data, "gripper", gripper_close_m)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    closed_contact_counts = contact_counts(mujoco, model, data)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="closed_gripper_contact_forward",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )
    step(mujoco, model, data, 100)
    settled_contact_counts = contact_counts(mujoco, model, data)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="closed_gripper_contact_after_settle",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )

    gripper_contact_observed = closed_contact_counts["gripper_contact_count"] > 0
    two_finger_contact_observed = (
        closed_contact_counts["fixed_finger_contact_count"] > 0
        and closed_contact_counts["moving_finger_contact_count"] > 0
    )
    lift_start_piece_z = body_position(mujoco, model, data, "piece_source")[2]
    lift_target = find_lift_target(mujoco, model, data)
    for joint, target in lift_target.items():
        set_actuator_target(mujoco, model, data, f"{joint}_actuator", target)
    set_actuator_target(mujoco, model, data, "shoulder_pan_actuator", 0.0)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    step(mujoco, model, data, 500)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lift_attempt_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )
    lift_end_piece = body_position(mujoco, model, data, "piece_source")
    lift_end_piece_z = lift_end_piece[2]
    lift_end_piece_xy = (lift_end_piece[0], lift_end_piece[1])
    lift_without_manual_piece_pose_m = lift_end_piece_z - lift_start_piece_z
    lift_contact_counts = contact_counts(mujoco, model, data)

    set_actuator_target(mujoco, model, data, "shoulder_pan_actuator", TRANSFER_PAN_RAD)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    step(mujoco, model, data, 500)
    transfer_piece = body_position(mujoco, model, data, "piece_source")
    transfer_xy_m = math.hypot(transfer_piece[0] - lift_end_piece_xy[0], transfer_piece[1] - lift_end_piece_xy[1])
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="transfer_attempt_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )

    for joint in ("shoulder_lift", "elbow_flex", "wrist_flex"):
        set_actuator_target(mujoco, model, data, f"{joint}_actuator", 0.0)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    step(mujoco, model, data, 500)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lower_to_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )

    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_open_m)
    step(mujoco, model, data, 250)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="release_attempt_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )

    for joint, target in lift_target.items():
        set_actuator_target(mujoco, model, data, f"{joint}_actuator", target)
    set_actuator_target(mujoco, model, data, "shoulder_pan_actuator", TRANSFER_PAN_RAD)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_open_m)
    step(mujoco, model, data, 700)
    final_counts = contact_counts(mujoco, model, data)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="retreat_after_release_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=initial_piece_z,
            initial_piece_xy=initial_piece_xy,
            target_xy=target_xy,
        )
    )
    final_piece = body_position(mujoco, model, data, "piece_source")
    final_target_xy_error_m = math.hypot(final_piece[0] - target_x, final_piece[1] - target_y)
    final_place_z_error_m = abs(final_piece[2] - expected_place_z)
    release_contact_cleared = final_counts["gripper_contact_count"] == 0
    final_board_contact_observed = final_counts["board_contact_count"] > 0
    lift_verified = (
        lift_contact_counts["gripper_contact_count"] > 0
        and lift_without_manual_piece_pose_m >= LIFT_Z_THRESHOLD_M
    )
    transfer_verified = transfer_xy_m >= TRANSFER_XY_THRESHOLD_M
    place_without_manual_piece_pose_verified = (
        final_board_contact_observed
        and final_target_xy_error_m <= TARGET_XY_TOLERANCE_M
        and release_contact_cleared
    )
    lift_place_physics_verified = bool(
        gripper_contact_observed
        and two_finger_contact_observed
        and settled_contact_counts["gripper_contact_count"] > 0
        and lift_verified
        and transfer_verified
        and lift_without_manual_piece_pose_m >= LIFT_Z_THRESHOLD_M
        and place_without_manual_piece_pose_verified
        and release_contact_cleared
    )
    if lift_place_physics_verified:
        status = "contact_grasp_lift_place_physics_verified"
    elif gripper_contact_observed:
        status = "gripper_contact_observed_lift_place_gap_recorded"
    else:
        status = "gripper_contact_gap_recorded"

    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "dependencies": deps,
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "development_manifest": manifest,
        "probe_count": len(rows),
        "contact_fixture": {
            "piece_radius_m": CONTACT_FIXTURE_PIECE_RADIUS_M,
            "piece_mass_kg": CONTACT_FIXTURE_PIECE_MASS_KG,
            "contact_condim": CONTACT_FIXTURE_CONDIM,
            "contact_friction": list(CONTACT_FIXTURE_FRICTION),
            "gripper_min_closure_m": CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M,
            "gripper_close_m": gripper_close_m,
            "gripper_actuator_kp": CONTACT_FIXTURE_GRIPPER_KP,
            "gripper_open_m": gripper_open_m,
            "closed_finger_midpoint_world_m": closed_midpoint,
        },
        "target_square": config.target_square,
        "target_world_m": {
            "x": target_x,
            "y": target_y,
            "board_z": target_board_z,
            "expected_piece_center_z": expected_place_z,
        },
        "gripper_contact_observed": gripper_contact_observed,
        "two_finger_contact_observed": two_finger_contact_observed,
        "settled_gripper_contact_observed": settled_contact_counts["gripper_contact_count"] > 0,
        "lift_verified": lift_verified,
        "lift_without_manual_piece_pose_m": lift_without_manual_piece_pose_m,
        "lift_z_threshold_m": LIFT_Z_THRESHOLD_M,
        "transfer_verified": transfer_verified,
        "transfer_xy_m": transfer_xy_m,
        "transfer_xy_threshold_m": TRANSFER_XY_THRESHOLD_M,
        "place_without_manual_piece_pose_verified": place_without_manual_piece_pose_verified,
        "lift_place_physics_verified": lift_place_physics_verified,
        "release_contact_cleared": release_contact_cleared,
        "final_board_contact_observed": final_board_contact_observed,
        "final_target_xy_error_m": final_target_xy_error_m,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
        "final_place_z_error_m": final_place_z_error_m,
        "manual_piece_pose_used_for_fixture": True,
        "manual_piece_pose_used_after_fixture": False,
        "robot_motion_mode": "position_actuator_lift_transfer_lower_release_retreat_without_manual_piece_pose",
        "lift_target_joint_qpos_rad": lift_target,
        "transfer_target_joint_qpos_rad": {"shoulder_pan": TRANSFER_PAN_RAD},
        "rows": rows,
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "This is a generated development MJCF fixture, not reviewed SO-101 CAD or calibrated model truth.",
            "The setup manually places an enlarged, contact-tuned fixture piece between the gripper fingers to probe scripted physics.",
            "Lift/place is considered verified only when the free piece moves, transfers, lands near the target square, and clears gripper contact without manual freejoint edits after fixture setup.",
        ],
        "next_required_for_goal": [
            "Replace the generated scaffold with a reviewed SO-101 URDF/MJCF bundle and mesh roots.",
            "Use reviewed TCP/gripper offset and base-to-board alignment before treating lift/place as training truth.",
            "Move from fixture-start grasp validation to board-source pickup using reviewed model-backed IK and calibrated gripper geometry.",
        ],
    }
    write_json(summary_path, summary)
    write_rows(rows_path, rows)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": True, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
