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


def run_scripted_pick_place(env: Any, action_toward_targets: Any, *, max_steps: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    obs, info = env.reset()
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
        f"- Ready for model-backed IK: `{str(summary['ready_for_model_backed_ik']).lower()}`",
        f"- Gymnasium available: `{summary['dependencies']['gymnasium']}`",
        f"- MuJoCo available: `{summary['dependencies']['mujoco']}`",
        f"- MuJoCo backend ok: `{summary['sim_status'].get('ok')}`",
        f"- Contact model: `{summary['contact_model']}`",
        f"- Scripted pick/place complete: `{summary['scripted_pick_place']['scripted_pick_place_complete']}`",
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
        "ready_for_model_backed_ik": False,
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

    config = SO101ChessEnvConfig(
        source_square=args.source_square,
        target_square=args.target_square,
        max_steps=args.max_steps,
        mujoco_model_path=args.mujoco_model_path,
        include_camera=args.include_camera,
    )
    env = SO101ChessEnv(config)
    try:
        scripted_result, rows = run_scripted_pick_place(
            env,
            action_toward_targets,
            max_steps=args.max_steps,
        )
        sim_status = scripted_result["final_info"]["sim_status"]
        if args.require_mujoco and not sim_status.get("ok"):
            hard_failures.append("mujoco_backend_required_but_not_loaded")
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

    summary = {
        "schema": "lerobot.sim.so101_chess_env_smoke.v1",
        "ok": status == "ok",
        "status": status,
        "hard_failures": hard_failures,
        "dependencies": deps,
        "model_authority": model_authority,
        "ready_for_model_backed_ik": False,
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
