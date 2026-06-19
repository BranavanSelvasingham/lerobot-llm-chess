#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_scene"
SUMMARY_NAME = "so101_mujoco_scene_summary.json"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
STEPS_NAME = "so101_mujoco_scene_env_steps.csv"
README_NAME = "README.md"
SO101_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
DEVELOPMENT_MODEL_AUTHORITY = "development_scaffold_not_reviewed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate and validate a development-only SO-101 MuJoCo chess scene. "
            "This proves MuJoCo plumbing, board/piece collision geoms, joint sync, "
            "and Gymnasium environment reset/step without claiming reviewed model authority."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--max-steps", type=int, default=96)
    return parser.parse_args()


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_steps(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "step",
        "waypoint",
        "phase_index",
        "reward",
        "terminated",
        "truncated",
        "piece_square",
        "holding_piece",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def joint_positions_from_obs(obs: dict[str, Any]) -> dict[str, float]:
    joints = obs["joint_positions_deg"]
    return {joint: float(joints[index]) for index, joint in enumerate(SO101_JOINTS)}


def run_scripted_env(env: Any, action_toward_targets: Any, *, max_steps: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    obs, info = env.reset()
    rows: list[dict[str, Any]] = []
    terminated = False
    truncated = False
    total_reward = 0.0
    for step_index in range(max_steps):
        phase_index = int(obs["phase_index"][0])
        waypoint = env.waypoints[min(phase_index, len(env.waypoints) - 1)]
        action = action_toward_targets(
            joint_positions_from_obs(obs),
            waypoint.targets_deg,
            action_scale_deg=env.config.action_scale_deg,
        )
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        scene = info["scene_state"]
        rows.append(
            {
                "step": step_index + 1,
                "waypoint": waypoint.name,
                "phase_index": int(obs["phase_index"][0]),
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "piece_square": scene["piece"]["square"],
                "holding_piece": bool(scene["piece"]["held_by_gripper"]),
            }
        )
        if terminated or truncated:
            break
    scene = info["scene_state"]
    result = {
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "steps": len(rows),
        "total_reward": float(total_reward),
        "final_phase_index": int(obs["phase_index"][0]),
        "final_piece_square": scene["piece"]["square"],
        "final_holding_piece": bool(scene["piece"]["held_by_gripper"]),
        "scripted_pick_place_complete": bool(
            terminated
            and scene["piece"]["square"] == env.config.target_square
            and not scene["piece"]["held_by_gripper"]
        ),
        "final_sim_status": info["sim_status"],
        "final_scene_state": scene,
    }
    return result, rows


def mujoco_names(module: Any, model: Any, obj_type: Any, count: int) -> list[str]:
    names: list[str] = []
    for index in range(count):
        name = module.mj_id2name(model, obj_type, index)
        if name:
            names.append(str(name))
    return names


def validate_loaded_model(model_path: Path) -> dict[str, Any]:
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    joint_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
    geom_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom)
    body_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
    site_names = mujoco_names(mujoco, model, mujoco.mjtObj.mjOBJ_SITE, model.nsite)
    required_joints = set(SO101_JOINTS)
    required_model_joints = required_joints | {"piece_source_freejoint"}
    required_bodies = {"piece_source", "chess_board"}
    required_geoms = {
        "chess_board_collision",
        "piece_source_collision",
        "gripper_fixed_finger_collision",
        "gripper_moving_finger_collision",
        "target_square_marker",
    }
    required_sites = {"gripper_frame_link"}
    square_geoms = [name for name in geom_names if name.startswith("square_")]
    return {
        "ok": (
            required_model_joints.issubset(joint_names)
            and required_bodies.issubset(body_names)
            and required_geoms.issubset(geom_names)
            and required_sites.issubset(site_names)
            and len(square_geoms) == 64
        ),
        "model_path": str(model_path),
        "nq": int(model.nq),
        "nv": int(model.nv),
        "joint_names": joint_names,
        "missing_joints": sorted(required_model_joints - set(joint_names)),
        "body_names": body_names,
        "missing_bodies": sorted(required_bodies - set(body_names)),
        "site_names": site_names,
        "missing_required_sites": sorted(required_sites - set(site_names)),
        "geom_count": len(geom_names),
        "body_count": len(body_names),
        "square_geom_count": len(square_geoms),
        "missing_required_geoms": sorted(required_geoms - set(geom_names)),
    }


def validate_sim_robot(model_path: Path) -> dict[str, Any]:
    from lerobot.sim import SimRobot, SimRobotConfig

    robot = SimRobot(
        SimRobotConfig(
            cameras={},
            use_mujoco=True,
            mujoco_model_path=model_path,
            initial_positions={"gripper": 95.0},
        )
    )
    robot.connect()
    try:
        initial_status = robot.sim_status()
        sent = robot.send_action(
            {
                "shoulder_pan.pos": 12.0,
                "shoulder_lift.pos": -24.0,
                "elbow_flex.pos": 52.0,
                "wrist_flex.pos": -30.0,
                "wrist_roll.pos": 35.0,
                "gripper.pos": 80.0,
            }
        )
        after_status = robot.sim_status()
        backend = getattr(robot, "_mujoco_backend", None)
        qpos_snapshot: list[float] = []
        if backend is not None:
            qpos_snapshot = [float(value) for value in backend.data.qpos[: min(8, len(backend.data.qpos))]]
        return {
            "ok": bool(initial_status.get("ok")) and bool(after_status.get("ok")) and not after_status.get("missing_joints"),
            "initial_status": initial_status,
            "after_status": after_status,
            "sent_action": sent,
            "qpos_snapshot": qpos_snapshot,
        }
    finally:
        robot.disconnect()


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Development MuJoCo Scene Smoke",
        "",
        "This smoke validates a generated development-only MJCF scene.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Model authority: `{summary['model_authority']}`",
        f"- MuJoCo model load ok: `{summary['mujoco_model_load'].get('ok')}`",
        f"- SimRobot MuJoCo sync ok: `{summary['sim_robot_mujoco_sync'].get('ok')}`",
        f"- Env scripted pick/place complete: `{summary['env_scripted_pick_place'].get('scripted_pick_place_complete')}`",
        f"- Generated model: `{summary['artifacts']['model_xml']}`",
        "",
        "This is not a reviewed SO-101 model bundle and must not be used as IK truth.",
    ]
    path.write_text("\n".join(lines) + "\n")


def invalid_task_summary(
    *,
    args: argparse.Namespace,
    deps: dict[str, bool],
    summary_path: Path,
    model_path: Path,
    manifest_path: Path,
    steps_path: Path,
    readme_path: Path,
    message: str,
) -> dict[str, Any]:
    summary = {
        "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
        "ok": False,
        "status": "invalid_task_configuration",
        "model_authority": DEVELOPMENT_MODEL_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "mujoco_scene_validity_status": "invalid_task_configuration",
        "source_square": args.source_square,
        "target_square": args.target_square,
        "max_steps": args.max_steps,
        "configuration_error": {
            "type": "ValueError",
            "message": message,
        },
        "dependencies": deps,
        "mujoco_model_load": {
            "ok": False,
            "status": "not_attempted_invalid_task_configuration",
        },
        "sim_robot_mujoco_sync": {
            "ok": False,
            "status": "not_attempted_invalid_task_configuration",
        },
        "env_scripted_pick_place": {
            "scripted_pick_place_complete": False,
            "status": "not_attempted_invalid_task_configuration",
        },
        "artifacts": {
            "summary_json": str(summary_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Invalid task configuration is recorded as a fail-closed scene gate artifact.",
            "No MuJoCo model, SimRobot sync, or Gymnasium scripted movement is attempted.",
            "This failure is hardware-free and does not claim physical SO-101 evidence.",
        ],
        "next_required_for_goal": [
            "Provide valid, distinct source and target chess squares before generating the MuJoCo scene.",
        ],
    }
    write_json(summary_path, summary)
    write_steps(steps_path, [])
    write_readme(readme_path, summary)
    return summary


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    deps = {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "gymnasium": module_available("gymnasium"),
        "mujoco": module_available("mujoco"),
    }
    missing = [name for name, available in deps.items() if not available]
    summary_path = args.output_dir / SUMMARY_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    steps_path = args.output_dir / STEPS_NAME
    readme_path = args.output_dir / README_NAME
    if missing:
        summary = {
            "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
            "ok": False,
            "status": "missing_runtime_dependencies",
            "missing_dependencies": missing,
            "dependencies": deps,
            "artifacts": {
                "summary_json": str(summary_path),
                "model_xml": str(model_path),
                "manifest_json": str(manifest_path),
                "steps_csv": str(steps_path),
                "readme": str(readme_path),
            },
        }
        write_json(summary_path, summary)
        write_steps(steps_path, [])
        write_readme(readme_path, {**summary, "model_authority": "not_generated", "mujoco_model_load": {}, "sim_robot_mujoco_sync": {}, "env_scripted_pick_place": {}})
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    from lerobot.sim import SO101ChessEnv, SO101ChessEnvConfig, action_toward_targets
    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        write_so101_development_mjcf,
    )

    try:
        if args.max_steps <= 0:
            raise ValueError("max_steps must be positive.")
        config = SO101DevelopmentMJCFConfig(piece_square=args.source_square, target_square=args.target_square)
    except ValueError as exc:
        summary = invalid_task_summary(
            args=args,
            deps=deps,
            summary_path=summary_path,
            model_path=model_path,
            manifest_path=manifest_path,
            steps_path=steps_path,
            readme_path=readme_path,
            message=str(exc),
        )
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    manifest = write_so101_development_mjcf(model_path, config, manifest_path=manifest_path)
    model_load = validate_loaded_model(model_path)
    sim_robot_sync = validate_sim_robot(model_path)
    env = SO101ChessEnv(
        SO101ChessEnvConfig(
            source_square=args.source_square,
            target_square=args.target_square,
            max_steps=args.max_steps,
            use_mujoco=True,
            mujoco_model_path=model_path,
        )
    )
    try:
        env_result, rows = run_scripted_env(env, action_toward_targets, max_steps=args.max_steps)
    finally:
        env.close()

    write_steps(steps_path, rows)
    ok = bool(model_load.get("ok")) and bool(sim_robot_sync.get("ok")) and bool(env_result.get("scripted_pick_place_complete"))
    summary = {
        "schema": "lerobot.sim.so101_mujoco_scene_smoke.v1",
        "ok": ok,
        "status": "ok" if ok else "failed",
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "mujoco_scene_validity_status": "development_scene_validated_not_physical_authority",
        "source_square": args.source_square,
        "target_square": args.target_square,
        "max_steps": args.max_steps,
        "square_geom_count": model_load.get("square_geom_count"),
        "target_frame_site_present": not bool(model_load.get("missing_required_sites")),
        "target_marker_present": "target_square_marker" not in set(model_load.get("missing_required_geoms") or []),
        "dependencies": deps,
        "development_manifest": manifest,
        "mujoco_model_load": model_load,
        "sim_robot_mujoco_sync": sim_robot_sync,
        "env_scripted_pick_place": env_result,
        "artifacts": {
            "summary_json": str(summary_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Generated development MJCF is approximate and non-authoritative.",
            "No reviewed mesh assets, source provenance, calibrated TCP offset, or base-to-board alignment are supplied.",
            "Passing this smoke proves MuJoCo plumbing and scene collision availability, not physical SO-101 IK accuracy.",
        ],
        "next_required_for_goal": [
            "Supply reviewed SO-101 URDF/MJCF/Xacro/XML model path.",
            "Supply mesh asset roots and pass asset preflight.",
            "Fill reviewed authority/provenance, TCP offset, and base-to-board transform in the model bundle manifest.",
        ],
    }
    write_json(summary_path, summary)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": ok, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
