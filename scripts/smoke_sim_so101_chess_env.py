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


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_chess_env"
SUMMARY_NAME = "so101_chess_env_summary.json"
STEPS_NAME = "so101_chess_env_steps.csv"
README_NAME = "README.md"
SO101_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
EXPECTED_OBSERVATION_KEYS: tuple[str, ...] = (
    "joint_positions_deg",
    "source_square_xyz_m",
    "target_square_xyz_m",
    "piece_square_index",
    "holding_piece",
    "phase_index",
    "mujoco_active",
)
EXPECTED_OBSERVATION_SHAPES: dict[str, tuple[int, ...]] = {
    "joint_positions_deg": (len(SO101_JOINTS),),
    "source_square_xyz_m": (3,),
    "target_square_xyz_m": (3,),
    "piece_square_index": (1,),
    "holding_piece": (1,),
    "phase_index": (1,),
    "mujoco_active": (1,),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free Gymnasium-facing SO-101 chess environment smoke. "
            "By default this accepts the existing joint-state fallback and records "
            "whether a supplied MuJoCo model actually loaded."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-square", default="e4")
    parser.add_argument("--target-square", default="e5")
    parser.add_argument("--mujoco-model-path", type=Path, default=None)
    parser.add_argument("--max-steps", type=int, default=96)
    parser.add_argument("--require-gymnasium", action="store_true")
    parser.add_argument("--require-mujoco", action="store_true")
    parser.add_argument("--include-camera", action="store_true")
    return parser.parse_args()


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
        "joint_error_deg",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def joint_positions_from_obs(obs: dict[str, Any]) -> dict[str, float]:
    joints = obs["joint_positions_deg"]
    return {joint: float(joints[index]) for index, joint in enumerate(SO101_JOINTS)}


def waypoint_error_deg(current: dict[str, float], targets: dict[str, float]) -> float:
    total = 0.0
    for joint in SO101_JOINTS:
        total += (float(targets[joint]) - float(current[joint])) ** 2
    return total**0.5


def shape_list(value: Any) -> list[int] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    return [int(item) for item in tuple(shape)]


def dtype_name(value: Any) -> str | None:
    dtype = getattr(value, "dtype", None)
    return str(dtype) if dtype is not None else None


def summarize_observation(obs: dict[str, Any]) -> dict[str, Any]:
    keys = list(obs.keys())
    expected = list(EXPECTED_OBSERVATION_KEYS)
    shapes = {key: shape_list(obs.get(key)) for key in expected}
    dtypes = {key: dtype_name(obs.get(key)) for key in expected}
    return {
        "keys": keys,
        "expected_keys": expected,
        "missing_keys": [key for key in expected if key not in obs],
        "unexpected_keys": [key for key in keys if key not in expected],
        "shapes": shapes,
        "expected_shapes": {
            key: list(shape) for key, shape in EXPECTED_OBSERVATION_SHAPES.items()
        },
        "shape_mismatches": [
            key
            for key, expected_shape in EXPECTED_OBSERVATION_SHAPES.items()
            if shape_list(obs.get(key)) != list(expected_shape)
        ],
        "dtypes": dtypes,
    }


def space_bounds_all(space: Any, expected: float) -> bool | None:
    values = getattr(space, "low" if expected < 0 else "high", None)
    if values is None:
        return None
    try:
        import numpy as np

        return bool(np.all(np.asarray(values, dtype=float) == expected))
    except Exception:
        return None


def summarize_gymnasium_api_contract(
    env: Any,
    *,
    reset_obs: dict[str, Any],
    final_obs: dict[str, Any],
) -> dict[str, Any]:
    action_space = getattr(env, "action_space", None)
    observation_space = getattr(env, "observation_space", None)
    observation_spaces = getattr(observation_space, "spaces", None)
    observation_space_keys = (
        sorted(str(key) for key in observation_spaces.keys())
        if isinstance(observation_spaces, dict)
        else []
    )
    action_shape = shape_list(action_space)
    observation_space_missing_keys = [
        key for key in EXPECTED_OBSERVATION_KEYS if key not in observation_space_keys
    ]
    observation_space_unexpected_keys = [
        key for key in observation_space_keys if key not in EXPECTED_OBSERVATION_KEYS
    ]
    reset_summary = summarize_observation(reset_obs)
    final_summary = summarize_observation(final_obs)
    ok = (
        action_shape == [len(SO101_JOINTS)]
        and dtype_name(action_space) == "float32"
        and space_bounds_all(action_space, -1.0) is True
        and space_bounds_all(action_space, 1.0) is True
        and observation_space_keys == sorted(EXPECTED_OBSERVATION_KEYS)
        and not observation_space_missing_keys
        and not observation_space_unexpected_keys
        and reset_summary["missing_keys"] == []
        and reset_summary["unexpected_keys"] == []
        and reset_summary["shape_mismatches"] == []
        and final_summary["missing_keys"] == []
        and final_summary["unexpected_keys"] == []
        and final_summary["shape_mismatches"] == []
    )
    return {
        "ok": ok,
        "action_space_present": action_space is not None,
        "action_space_type": type(action_space).__name__ if action_space is not None else None,
        "action_space_shape": action_shape,
        "action_space_dtype": dtype_name(action_space),
        "action_space_low_all_minus_one": space_bounds_all(action_space, -1.0),
        "action_space_high_all_one": space_bounds_all(action_space, 1.0),
        "controlled_joint_count": len(SO101_JOINTS),
        "controlled_joints": list(SO101_JOINTS),
        "observation_space_present": observation_space is not None,
        "observation_space_type": type(observation_space).__name__
        if observation_space is not None
        else None,
        "observation_space_keys": observation_space_keys,
        "expected_observation_keys": list(EXPECTED_OBSERVATION_KEYS),
        "observation_space_missing_keys": observation_space_missing_keys,
        "observation_space_unexpected_keys": observation_space_unexpected_keys,
        "reset_observation": reset_summary,
        "final_observation": final_summary,
    }


def run_scripted_pick_place(env: Any, action_toward_targets: Any, *, max_steps: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    obs, info = env.reset()
    reset_obs = obs
    rows: list[dict[str, Any]] = []
    total_reward = 0.0
    terminated = False
    truncated = False

    for step_index in range(max_steps):
        phase_index = int(obs["phase_index"][0])
        waypoint = env.waypoints[min(phase_index, len(env.waypoints) - 1)]
        current = joint_positions_from_obs(obs)
        action = action_toward_targets(
            current,
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
                "joint_error_deg": waypoint_error_deg(joint_positions_from_obs(obs), waypoint.targets_deg),
            }
        )
        if terminated or truncated:
            break

    final_obs = obs
    final_scene = info["scene_state"]
    result = {
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "steps": len(rows),
        "total_reward": float(total_reward),
        "final_phase_index": int(obs["phase_index"][0]),
        "final_piece_square": final_scene["piece"]["square"],
        "final_holding_piece": bool(final_scene["piece"]["held_by_gripper"]),
        "scripted_pick_place_complete": bool(
            terminated
            and final_scene["piece"]["square"] == env.config.target_square
            and not final_scene["piece"]["held_by_gripper"]
        ),
        "final_info": info,
        "gymnasium_api_contract": summarize_gymnasium_api_contract(
            env,
            reset_obs=reset_obs,
            final_obs=final_obs,
        ),
    }
    return result, rows


def write_readme(path: Path, summary: dict[str, Any], steps_path: Path) -> None:
    lines = [
        "# SO-101 Chess Env Smoke",
        "",
        "This hardware-free smoke exercises the training-facing SO-101 chess environment.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Model authority: `{summary['model_authority']}`",
        f"- Physical SO-101 authority: `{summary.get('observed_evidence_is_physical_so101_authority')}`",
        f"- Policy-training authority: `{summary.get('observed_evidence_is_policy_training_authority')}`",
        f"- Development fixture not physical truth: `{summary.get('development_fixture_evidence_not_physical_so101_truth')}`",
        f"- Development fixture not policy truth: `{summary.get('development_fixture_evidence_not_policy_training_truth')}`",
        f"- Ready for model-backed IK: `{str(summary['ready_for_model_backed_ik']).lower()}`",
        f"- Gymnasium available: `{summary['dependencies']['gymnasium']}`",
        f"- MuJoCo available: `{summary['dependencies']['mujoco']}`",
        f"- Gymnasium task wiring: `{summary.get('gymnasium_task_wiring_status')}`",
        f"- Gymnasium API contract ok: `{summary.get('gymnasium_api_contract', {}).get('ok')}`",
        f"- MuJoCo backend ok: `{summary['sim_status'].get('ok')}`",
        f"- Joint-state fallback active: `{summary.get('joint_state_fallback_active')}`",
        f"- Contact model: `{summary['contact_model']}`",
        f"- Scripted pick/place complete: `{summary['scripted_pick_place']['scripted_pick_place_complete']}`",
        f"- Ready for policy training: `{summary.get('ready_for_policy_training')}`",
        f"- Training authority: `{summary.get('training_authority_status')}`",
        f"- Source square: `{summary['config']['source_square']}`",
        f"- Target square: `{summary['config']['target_square']}`",
        f"- Step rows: `{steps_path}`",
        "",
        "The current scene contact model is symbolic until a reviewed MuJoCo robot/world bundle is supplied.",
    ]
    path.write_text("\n".join(lines) + "\n")


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def base_dependency_status() -> dict[str, bool]:
    return {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "gymnasium": module_available("gymnasium"),
        "mujoco": module_available("mujoco"),
    }


def write_dependency_failure(args: argparse.Namespace, deps: dict[str, bool], failures: list[str]) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    steps_path = args.output_dir / STEPS_NAME
    summary_path = args.output_dir / SUMMARY_NAME
    readme_path = args.output_dir / README_NAME
    write_steps(steps_path, [])
    summary = {
        "schema": "lerobot.sim.so101_chess_env_smoke.v1",
        "ok": False,
        "status": "missing_runtime_dependencies",
        "hard_failures": failures,
        "dependencies": deps,
        "model_authority": "runtime_dependencies_missing",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "gymnasium_required": bool(args.require_gymnasium),
        "mujoco_backend_required": bool(args.require_mujoco),
        "mujoco_backend_loaded": False,
        "joint_state_fallback_active": False,
        "gymnasium_task_wiring_status": "runtime_dependencies_missing",
        "training_authority_status": "requirements_failed_not_policy_ready",
        "training_authority_blockers": [
            "runtime_dependencies",
            "reviewed_so101_model_bundle",
            "reviewed_mujoco_scene_contact_validation",
            "reviewed_model_backed_board_source_pick_place",
        ],
        "contact_model": "unavailable_until_runtime_dependencies_install",
        "config": {
            "source_square": args.source_square,
            "target_square": args.target_square,
            "max_steps": args.max_steps,
            "mujoco_model_path": str(args.mujoco_model_path) if args.mujoco_model_path else None,
            "include_camera": args.include_camera,
        },
        "sim_status": {"ok": False, "reason": "Environment could not import project runtime dependencies."},
        "scene_state": {},
        "scripted_pick_place": {"scripted_pick_place_complete": False, "steps": 0},
        "artifacts": {
            "summary_json": str(summary_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Install the project runtime dependencies before environment reset/step validation can run.",
        ],
    }
    write_json(summary_path, summary)
    write_readme(readme_path, summary, steps_path)
    print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 1


def write_invalid_configuration_failure(
    args: argparse.Namespace,
    deps: dict[str, bool],
    message: str,
) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    steps_path = args.output_dir / STEPS_NAME
    summary_path = args.output_dir / SUMMARY_NAME
    readme_path = args.output_dir / README_NAME
    write_steps(steps_path, [])
    summary = {
        "schema": "lerobot.sim.so101_chess_env_smoke.v1",
        "ok": False,
        "status": "invalid_task_configuration",
        "hard_failures": ["invalid_task_configuration"],
        "configuration_error": {
            "type": "ValueError",
            "message": message,
        },
        "dependencies": deps,
        "model_authority": "invalid_task_configuration_not_authority",
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "gymnasium_required": bool(args.require_gymnasium),
        "mujoco_backend_required": bool(args.require_mujoco),
        "mujoco_backend_loaded": False,
        "joint_state_fallback_active": False,
        "gymnasium_task_wiring_status": "invalid_task_configuration",
        "training_authority_status": "requirements_failed_not_policy_ready",
        "training_authority_blockers": [
            "invalid_task_configuration",
            "reviewed_so101_model_bundle",
            "reviewed_mujoco_scene_contact_validation",
            "reviewed_model_backed_board_source_pick_place",
        ],
        "contact_model": "unavailable_invalid_task_configuration",
        "config": {
            "source_square": args.source_square,
            "target_square": args.target_square,
            "max_steps": args.max_steps,
            "mujoco_model_path": str(args.mujoco_model_path) if args.mujoco_model_path else None,
            "include_camera": args.include_camera,
        },
        "sim_status": {"ok": False, "reason": message},
        "scene_state": {},
        "scripted_pick_place": {"scripted_pick_place_complete": False, "steps": 0},
        "artifacts": {
            "summary_json": str(summary_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Invalid task configuration is recorded as a fail-closed Gymnasium gate artifact.",
            "No environment reset, MuJoCo backend, or scripted movement is attempted.",
        ],
    }
    write_json(summary_path, summary)
    write_readme(readme_path, summary, steps_path)
    print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 1


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    deps = base_dependency_status()
    hard_failures: list[str] = []
    missing_core = [name for name in ("numpy", "draccus") if not deps[name]]
    if missing_core:
        hard_failures.extend(f"{name}_missing" for name in missing_core)
        return write_dependency_failure(args, deps, hard_failures)

    try:
        from lerobot.sim.chess_env import (
            SO101ChessEnv,
            SO101ChessEnvConfig,
            action_toward_targets,
            dependency_status,
        )
    except ModuleNotFoundError as exc:
        hard_failures.append(f"import_failed:{exc.name}")
        return write_dependency_failure(args, deps, hard_failures)

    deps = {**deps, **dependency_status()}
    if args.require_gymnasium and not deps["gymnasium"]:
        hard_failures.append("gymnasium_required_but_unavailable")
    if args.require_mujoco and not deps["mujoco"]:
        hard_failures.append("mujoco_required_but_unavailable")

    try:
        config = SO101ChessEnvConfig(
            source_square=args.source_square,
            target_square=args.target_square,
            max_steps=args.max_steps,
            mujoco_model_path=args.mujoco_model_path,
            include_camera=args.include_camera,
        )
    except ValueError as exc:
        return write_invalid_configuration_failure(args, deps, str(exc))

    env = SO101ChessEnv(config)
    try:
        scripted_result, rows = run_scripted_pick_place(
            env,
            action_toward_targets,
            max_steps=args.max_steps,
        )
        sim_status = scripted_result["final_info"]["sim_status"]
        if config.mujoco_model_path is not None and not sim_status.get("ok"):
            hard_failures.append("mujoco_model_path_supplied_but_not_loaded")
        if args.require_mujoco and not sim_status.get("ok"):
            hard_failures.append("mujoco_backend_required_but_not_loaded")
        if not scripted_result["gymnasium_api_contract"].get("ok"):
            hard_failures.append("gymnasium_api_contract_invalid")
        if not scripted_result.get("scripted_pick_place_complete"):
            hard_failures.append("scripted_pick_place_incomplete")
    finally:
        env.close()

    status = "ok" if not hard_failures else "failed_requirements"
    steps_path = args.output_dir / STEPS_NAME
    summary_path = args.output_dir / SUMMARY_NAME
    readme_path = args.output_dir / README_NAME
    write_steps(steps_path, rows)
    sim_status = scripted_result["final_info"]["sim_status"]
    scene_state = scripted_result["final_info"]["scene_state"]
    model_authority = (
        "development_scaffold_not_reviewed"
        if sim_status.get("ok") and config.mujoco_model_path is not None
        else "joint_state_fallback_no_reviewed_model"
    )
    mujoco_backend_loaded = bool(sim_status.get("ok"))
    joint_state_fallback_active = sim_status.get("fallback") == "joint_state"
    if hard_failures:
        gymnasium_task_wiring_status = "failed_requirements"
        training_authority_status = "requirements_failed_not_policy_ready"
    elif mujoco_backend_loaded:
        gymnasium_task_wiring_status = "development_mujoco_env_scripted"
        training_authority_status = "development_mujoco_env_verified_not_policy_ready"
    else:
        gymnasium_task_wiring_status = "joint_state_fallback_env_scripted"
        training_authority_status = "joint_state_fallback_env_verified_not_policy_ready"
    training_authority_blockers = [
        "reviewed_so101_model_bundle",
        "reviewed_mujoco_scene_contact_validation",
        "reviewed_model_backed_board_source_pick_place",
        "reviewed_model_backed_training_rollouts",
    ]
    if not mujoco_backend_loaded:
        training_authority_blockers.insert(0, "mujoco_backend_loaded")

    summary = {
        "schema": "lerobot.sim.so101_chess_env_smoke.v1",
        "ok": status == "ok",
        "status": status,
        "hard_failures": hard_failures,
        "dependencies": deps,
        "model_authority": model_authority,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "gymnasium_required": bool(args.require_gymnasium),
        "mujoco_backend_required": bool(args.require_mujoco),
        "mujoco_backend_loaded": mujoco_backend_loaded,
        "joint_state_fallback_active": joint_state_fallback_active,
        "gymnasium_task_wiring_status": gymnasium_task_wiring_status,
        "gymnasium_api_contract": scripted_result["gymnasium_api_contract"],
        "training_authority_status": training_authority_status,
        "training_authority_blockers": training_authority_blockers,
        "contact_model": scene_state.get("contact_model"),
        "config": {
            "source_square": config.source_square,
            "target_square": config.target_square,
            "max_steps": config.max_steps,
            "mujoco_model_path": str(config.mujoco_model_path) if config.mujoco_model_path else None,
            "include_camera": config.include_camera,
        },
        "sim_status": sim_status,
        "scene_state": scene_state,
        "scripted_pick_place": scripted_result,
        "artifacts": {
            "summary_json": str(summary_path),
            "steps_csv": str(steps_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Default mode allows joint-state fallback when no reviewed MuJoCo model path is supplied.",
            "The chess board and piece contact model is symbolic until the reviewed MuJoCo scene is added.",
            "The scripted policy is a deterministic joint-space scaffold, not calibrated IK.",
        ],
    }
    write_json(summary_path, summary)
    write_readme(readme_path, summary, steps_path)
    print(json.dumps({"ok": summary["ok"], "status": status, "summary_json": str(summary_path)}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
