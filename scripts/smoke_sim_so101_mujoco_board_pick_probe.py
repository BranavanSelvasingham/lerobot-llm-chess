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


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_board_pick_probe"
SUMMARY_NAME = "so101_mujoco_board_pick_probe_summary.json"
ROWS_NAME = "so101_mujoco_board_pick_probe_rows.csv"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.so101_mujoco_board_pick_probe.v1"
SOURCE_SQUARE = "e4"
TARGET_SQUARE = "e5"
CONTACT_FIXTURE_PIECE_RADIUS_M = 0.016
CONTACT_FIXTURE_PIECE_MASS_KG = 0.005
CONTACT_FIXTURE_CONDIM = 6
CONTACT_FIXTURE_FRICTION = (2.0, 0.4, 0.02)
CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M = -0.012
CONTACT_FIXTURE_GRIPPER_CLOSE_M = -0.008
CONTACT_FIXTURE_GRIPPER_KP = 200.0
SOURCE_PAN_RAD = -0.1
TARGET_PAN_RAD = 0.07
LIFT_Z_THRESHOLD_M = 0.02
TARGET_XY_TOLERANCE_M = 0.01
SOURCE_PICK_XY_TOLERANCE_M = 0.02
LOWER_JOINT_TARGETS = {
    "shoulder_lift": 0.0,
    "elbow_flex": 0.0,
    "wrist_flex": 0.0,
}
LIFT_JOINT_TARGETS = {
    "shoulder_lift": math.radians(-20.0),
    "elbow_flex": math.radians(10.0),
    "wrist_flex": math.radians(5.0),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe board-source pick/place in the development SO-101 MuJoCo chess scene. "
            "This is a scaffold smoke, not reviewed model-backed IK evidence."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-square", default=SOURCE_SQUARE)
    parser.add_argument("--target-square", default=TARGET_SQUARE)
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
        "source_xy_error_m",
        "target_xy_error_m",
        "source_to_target_progress_m",
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


def set_robot_pose(
    module: Any,
    model: Any,
    data: Any,
    *,
    shoulder_pan: float,
    joint_targets: dict[str, float],
    gripper: float,
) -> None:
    values = {"shoulder_pan": shoulder_pan, **joint_targets, "gripper": gripper}
    for joint, value in values.items():
        set_joint_qpos(module, model, data, joint, value)
        set_actuator_target(module, model, data, f"{joint}_actuator", value)


def set_robot_targets(
    module: Any,
    model: Any,
    data: Any,
    *,
    shoulder_pan: float,
    joint_targets: dict[str, float],
    gripper: float,
) -> None:
    set_actuator_target(module, model, data, "shoulder_pan_actuator", shoulder_pan)
    for joint, value in joint_targets.items():
        set_actuator_target(module, model, data, f"{joint}_actuator", value)
    set_actuator_target(module, model, data, "gripper_actuator", gripper)


def record_stage(
    module: Any,
    model: Any,
    data: Any,
    *,
    stage: str,
    manual_piece_pose_set: bool,
    initial_piece_z: float,
    source_xy: tuple[float, float],
    target_xy: tuple[float, float],
) -> dict[str, Any]:
    piece = body_position(module, model, data, "piece_source")
    site = site_position(module, model, data, "gripper_frame_link")
    contacts = contact_counts(module, model, data)
    source_xy_error = math.hypot(piece[0] - source_xy[0], piece[1] - source_xy[1])
    target_xy_error = math.hypot(piece[0] - target_xy[0], piece[1] - target_xy[1])
    source_to_target_progress = math.hypot(piece[0] - source_xy[0], piece[1] - source_xy[1])
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
        "source_xy_error_m": source_xy_error,
        "target_xy_error_m": target_xy_error,
        "source_to_target_progress_m": source_to_target_progress,
        "manual_piece_pose_set": manual_piece_pose_set,
        "ok": True,
    }


def row_by_stage(rows: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    for row in rows:
        if row.get("stage") == stage:
            return row
    raise AssertionError(f"Missing row for stage {stage!r}.")


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 MuJoCo Board Pick Probe",
        "",
        "This smoke records board-source pick/place in the generated development MJCF scene.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Source square: `{summary.get('source_square')}`",
        f"- Target square: `{summary.get('target_square')}`",
        f"- Source pick started at source: `{summary.get('source_pick_started_at_source')}`",
        f"- Close two-finger contact observed: `{summary.get('close_two_finger_contact_observed')}`",
        f"- Lift verified: `{summary.get('lift_verified')}`",
        f"- Board contact cleared during lift: `{summary.get('board_contact_cleared_during_lift')}`",
        f"- Transfer verified: `{summary.get('transfer_verified')}`",
        f"- Place verified: `{summary.get('place_without_manual_piece_pose_verified')}`",
        f"- Release contact cleared after retreat: `{summary.get('release_contact_cleared_after_retreat')}`",
        f"- Final target XY error m: `{summary.get('final_target_xy_error_m')}`",
        f"- Rows CSV: `{summary['artifacts']['rows_csv']}`",
        "",
        "The setup resets the free piece onto the source board square once, then leaves the piece free.",
        "The robot source pose is seeded in the development scaffold because reviewed model-backed IK is still missing.",
        "A true board-source pick/place result is development evidence only; reviewed SO-101 model authority remains required before serious policy training.",
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
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "source_square": args.source_square,
        "target_square": args.target_square,
        "source_pick_started_at_source": False,
        "close_two_finger_contact_observed": False,
        "lift_verified": False,
        "board_contact_cleared_during_lift": False,
        "transfer_verified": False,
        "place_without_manual_piece_pose_verified": False,
        "board_source_pick_place_verified": False,
        "release_contact_cleared_after_retreat": False,
        "final_board_contact_observed": False,
        "manual_piece_pose_used_after_reset": False,
        "robot_pose_seeded_for_source_fixture": False,
        "final_target_xy_error_m": None,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
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
        piece_square=args.source_square,
        target_square=args.target_square,
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
    source_x, source_y, source_board_z = square_center_world_m(config.piece_square, config)
    target_x, target_y, target_board_z = square_center_world_m(config.target_square, config)
    source_xy = (source_x, source_y)
    target_xy = (target_x, target_y)
    expected_place_z = target_board_z + config.piece_height_m / 2.0

    source_piece_pos = (source_x, source_y, source_board_z + config.piece_height_m / 2.0)
    set_freejoint_pose(mujoco, model, data, "piece_source_freejoint", pos=source_piece_pos)
    set_robot_pose(
        mujoco,
        model,
        data,
        shoulder_pan=SOURCE_PAN_RAD,
        joint_targets=LOWER_JOINT_TARGETS,
        gripper=gripper_open_m,
    )
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    rows = [
        record_stage(
            mujoco,
            model,
            data,
            stage="source_reset_piece_on_board",
            manual_piece_pose_set=True,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    ]

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=SOURCE_PAN_RAD,
        joint_targets=LOWER_JOINT_TARGETS,
        gripper=gripper_open_m,
    )
    step(mujoco, model, data, 100)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lower_open_at_source",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_joint_qpos(mujoco, model, data, "gripper", gripper_close_m)
    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_close_m)
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="close_on_source_piece_forward",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )
    step(mujoco, model, data, 100)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="close_on_source_piece_after_settle",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    lift_start_piece_z = body_position(mujoco, model, data, "piece_source")[2]
    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=SOURCE_PAN_RAD,
        joint_targets=LIFT_JOINT_TARGETS,
        gripper=gripper_close_m,
    )
    step(mujoco, model, data, 500)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lift_from_source_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=TARGET_PAN_RAD,
        joint_targets=LIFT_JOINT_TARGETS,
        gripper=gripper_close_m,
    )
    step(mujoco, model, data, 700)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="transfer_to_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=TARGET_PAN_RAD,
        joint_targets=LOWER_JOINT_TARGETS,
        gripper=gripper_close_m,
    )
    step(mujoco, model, data, 600)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="lower_to_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_actuator_target(mujoco, model, data, "gripper_actuator", gripper_open_m)
    step(mujoco, model, data, 300)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="release_on_target_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    set_robot_targets(
        mujoco,
        model,
        data,
        shoulder_pan=TARGET_PAN_RAD,
        joint_targets=LIFT_JOINT_TARGETS,
        gripper=gripper_open_m,
    )
    step(mujoco, model, data, 700)
    rows.append(
        record_stage(
            mujoco,
            model,
            data,
            stage="retreat_after_release_without_manual_piece_pose",
            manual_piece_pose_set=False,
            initial_piece_z=source_piece_pos[2],
            source_xy=source_xy,
            target_xy=target_xy,
        )
    )

    source_reset = row_by_stage(rows, "source_reset_piece_on_board")
    close_settle = row_by_stage(rows, "close_on_source_piece_after_settle")
    lift = row_by_stage(rows, "lift_from_source_without_manual_piece_pose")
    transfer = row_by_stage(rows, "transfer_to_target_without_manual_piece_pose")
    final = row_by_stage(rows, "retreat_after_release_without_manual_piece_pose")
    source_pick_started_at_source = (
        source_reset["source_xy_error_m"] <= SOURCE_PICK_XY_TOLERANCE_M
        and close_settle["source_xy_error_m"] <= SOURCE_PICK_XY_TOLERANCE_M
    )
    close_two_finger_contact_observed = (
        close_settle["fixed_finger_contact_count"] > 0
        and close_settle["moving_finger_contact_count"] > 0
    )
    board_contact_cleared_during_lift = lift["board_contact_count"] == 0
    lift_without_manual_piece_pose_m = float(lift["piece_z"]) - lift_start_piece_z
    lift_verified = (
        close_two_finger_contact_observed
        and lift["gripper_contact_count"] > 0
        and board_contact_cleared_during_lift
        and lift_without_manual_piece_pose_m >= LIFT_Z_THRESHOLD_M
    )
    transfer_verified = (
        transfer["gripper_contact_count"] > 0
        and transfer["target_xy_error_m"] < close_settle["target_xy_error_m"]
        and transfer["board_contact_count"] == 0
    )
    final_target_xy_error_m = float(final["target_xy_error_m"])
    final_place_z_error_m = abs(float(final["piece_z"]) - expected_place_z)
    release_contact_cleared_after_retreat = final["gripper_contact_count"] == 0
    final_board_contact_observed = final["board_contact_count"] > 0
    place_without_manual_piece_pose_verified = (
        final_board_contact_observed
        and release_contact_cleared_after_retreat
        and final_target_xy_error_m <= TARGET_XY_TOLERANCE_M
    )
    board_source_pick_place_verified = bool(
        source_pick_started_at_source
        and close_two_finger_contact_observed
        and lift_verified
        and transfer_verified
        and place_without_manual_piece_pose_verified
    )
    if board_source_pick_place_verified:
        status = "development_board_source_pick_place_verified"
    elif lift_verified:
        status = "development_board_source_lift_verified_place_gap_recorded"
    else:
        status = "development_board_source_pick_gap_recorded"

    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status,
        "dependencies": deps,
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "development_manifest": manifest,
        "probe_count": len(rows),
        "source_square": config.piece_square,
        "target_square": config.target_square,
        "source_world_m": {
            "x": source_x,
            "y": source_y,
            "board_z": source_board_z,
            "expected_piece_center_z": source_piece_pos[2],
        },
        "target_world_m": {
            "x": target_x,
            "y": target_y,
            "board_z": target_board_z,
            "expected_piece_center_z": expected_place_z,
        },
        "contact_fixture": {
            "piece_radius_m": CONTACT_FIXTURE_PIECE_RADIUS_M,
            "piece_mass_kg": CONTACT_FIXTURE_PIECE_MASS_KG,
            "contact_condim": CONTACT_FIXTURE_CONDIM,
            "contact_friction": list(CONTACT_FIXTURE_FRICTION),
            "gripper_min_closure_m": CONTACT_FIXTURE_GRIPPER_MIN_CLOSURE_M,
            "gripper_close_m": gripper_close_m,
            "gripper_actuator_kp": CONTACT_FIXTURE_GRIPPER_KP,
            "gripper_open_m": gripper_open_m,
        },
        "source_pick_started_at_source": source_pick_started_at_source,
        "source_pick_xy_tolerance_m": SOURCE_PICK_XY_TOLERANCE_M,
        "close_two_finger_contact_observed": close_two_finger_contact_observed,
        "lift_verified": lift_verified,
        "lift_without_manual_piece_pose_m": lift_without_manual_piece_pose_m,
        "lift_z_threshold_m": LIFT_Z_THRESHOLD_M,
        "board_contact_cleared_during_lift": board_contact_cleared_during_lift,
        "transfer_verified": transfer_verified,
        "transfer_target_xy_error_m": transfer["target_xy_error_m"],
        "transfer_source_to_target_progress_m": transfer["source_to_target_progress_m"],
        "place_without_manual_piece_pose_verified": place_without_manual_piece_pose_verified,
        "board_source_pick_place_verified": board_source_pick_place_verified,
        "release_contact_cleared_after_retreat": release_contact_cleared_after_retreat,
        "final_board_contact_observed": final_board_contact_observed,
        "final_target_xy_error_m": final_target_xy_error_m,
        "target_xy_tolerance_m": TARGET_XY_TOLERANCE_M,
        "final_place_z_error_m": final_place_z_error_m,
        "source_to_target_progress_m": final["source_to_target_progress_m"],
        "piece_reset_to_source_before_run": True,
        "manual_piece_pose_used_after_reset": False,
        "robot_pose_seeded_for_source_fixture": True,
        "robot_motion_mode": "seed_source_pose_position_actuator_close_lift_transfer_lower_release_retreat",
        "source_pose_joint_qpos_rad": {
            "shoulder_pan": SOURCE_PAN_RAD,
            **LOWER_JOINT_TARGETS,
        },
        "lift_target_joint_qpos_rad": LIFT_JOINT_TARGETS,
        "transfer_target_joint_qpos_rad": {"shoulder_pan": TARGET_PAN_RAD},
        "rows": rows,
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "This is a generated development MJCF scaffold, not reviewed SO-101 CAD or calibrated model truth.",
            "The piece is enlarged, lightened, and contact-tuned to probe board-source physics before reviewed geometry is available.",
            "The robot source pose is seeded directly in qpos/ctrl; reviewed model-backed IK remains required.",
            "The piece freejoint is reset onto the source square once before the run and is not manually moved after that reset.",
        ],
        "next_required_for_goal": [
            "Replace the generated scaffold with a reviewed SO-101 URDF/MJCF bundle and mesh roots.",
            "Use reviewed TCP/gripper offset and base-to-board alignment for model-backed IK instead of seeded source pose.",
            "Repeat board-source pick/place with calibrated gripper geometry before treating training rollouts as physical truth.",
        ],
    }
    write_json(summary_path, summary)
    write_rows(rows_path, rows)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": True, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
