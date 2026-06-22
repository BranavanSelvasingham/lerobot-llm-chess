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


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_training_rollouts"
SUMMARY_NAME = "so101_training_rollouts_summary.json"
TRANSITIONS_NAME = "so101_training_rollouts.jsonl"
EPISODES_NAME = "so101_training_rollout_episodes.csv"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.so101_training_rollouts.v1"
BOARD_PICK_PREREQUISITE_SCHEMA = SCHEMA + ".board_pick_prerequisite.v1"
DEFAULT_TASKS: tuple[tuple[str, str], ...] = (
    ("e4", "e5"),
    ("a4", "a5"),
    ("b8", "c8"),
    ("e2", "e3"),
    ("d4", "f4"),
)
INVALID_TASK_MODEL_AUTHORITY = "invalid_task_configuration_not_authority"
SO101_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
BOARD_PICK_REQUIRED_STAGE_SEQUENCE: tuple[str, ...] = (
    "source_reset_piece_on_board",
    "lower_open_at_source",
    "close_on_source_piece_forward",
    "close_on_source_piece_after_settle",
    "lift_from_source_without_manual_piece_pose",
    "transfer_to_target_without_manual_piece_pose",
    "lower_to_target_without_manual_piece_pose",
    "release_on_target_without_manual_piece_pose",
    "retreat_after_release_without_manual_piece_pose",
)
ROLLOUT_NEXT_REQUIRED_FOR_GOAL: tuple[dict[str, Any], ...] = (
    {
        "priority": 1,
        "missing_input": "reviewed_so101_model_bundle",
        "action_id": "supply_reviewed_so101_model_bundle_manifest",
        "gate": "reviewed_model_authority",
    },
    {
        "priority": 2,
        "missing_input": "reviewed_tcp_and_base_to_board_alignment",
        "action_id": "calibrate_reviewed_tcp_and_base_to_board_alignment",
        "gate": "reviewed_model_authority",
    },
    {
        "priority": 3,
        "missing_input": "reviewed_model_backed_board_source_pick_place",
        "action_id": "repeat_board_pick_with_reviewed_model_backed_ik",
        "gate": "scripted_contact_grasp_pick_place",
    },
    {
        "priority": 4,
        "missing_input": "reviewed_model_backed_training_rollouts",
        "action_id": "run_focused_training_rollouts_after_reviewed_pick_place",
        "gate": "focused_training_rollouts",
    },
)
ROLLOUT_SERIOUS_POLICY_TRAINING_BLOCKERS: tuple[str, ...] = tuple(
    str(action["missing_input"]) for action in ROLLOUT_NEXT_REQUIRED_FOR_GOAL
)


def rollout_next_required_for_goal() -> list[dict[str, Any]]:
    return [dict(action) for action in ROLLOUT_NEXT_REQUIRED_FOR_GOAL]


def action_ids_from_next_required(next_required_for_goal: list[dict[str, Any]]) -> list[str]:
    return [
        str(action["action_id"])
        for action in next_required_for_goal
        if isinstance(action, dict) and action.get("action_id")
    ]


def rollout_action_contract(next_required_for_goal: list[dict[str, Any]]) -> dict[str, Any]:
    action_ids = action_ids_from_next_required(next_required_for_goal)
    return {
        "serious_policy_training_blocker_action_ids": action_ids,
        "next_required_action_ids": action_ids,
        "next_required_for_goal_action_ids": action_ids,
        "next_required_action_ids_match_next_required": True,
        "next_required_action_ids_missing_from_next_required": [],
        "next_required_actions_missing_from_action_ids": [],
        "next_required_action_count": len(action_ids),
    }


def json_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect deterministic scripted expert rollouts for focused SO-101 chess "
            "pick/place tasks in the development MuJoCo scene."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-steps", type=int, default=96)
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Task pair as SOURCE:TARGET, for example e4:e5. Repeatable. Defaults to a small board-zone curriculum.",
    )
    parser.add_argument(
        "--development-board-pick-summary-json",
        type=Path,
        required=True,
        help=(
            "Summary JSON from smoke_sim_so101_mujoco_board_pick_probe.py. "
            "Training rollouts are collected only after this development board-source pick/place gate is explicit."
        ),
    )
    return parser.parse_args()


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def write_episode_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "episode",
        "source_square",
        "target_square",
        "steps",
        "terminated",
        "truncated",
        "total_reward",
        "final_phase_index",
        "final_piece_square",
        "final_holding_piece",
        "mujoco_active",
        "fallback",
        "mujoco_piece_release_synced",
        "mujoco_piece_release_error_m",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def validate_square(square: str) -> None:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")


def parse_tasks(values: list[str]) -> tuple[tuple[str, str], ...]:
    if not values:
        return DEFAULT_TASKS
    tasks: list[tuple[str, str]] = []
    for value in values:
        if ":" not in value:
            raise ValueError(f"Task must be SOURCE:TARGET, got {value!r}.")
        source, target = value.split(":", 1)
        source_square = source.strip().lower()
        target_square = target.strip().lower()
        validate_square(source_square)
        validate_square(target_square)
        if source_square == target_square:
            raise ValueError("source_square and target_square must differ.")
        tasks.append((source_square, target_square))
    return tuple(tasks)


def task_configuration_error(args: argparse.Namespace) -> str | None:
    if args.max_steps <= 0:
        return "max_steps must be positive."
    try:
        parse_tasks(args.task)
    except ValueError as exc:
        return str(exc)
    return None


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return payload


def inspect_board_pick_prerequisite(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": BOARD_PICK_PREREQUISITE_SCHEMA,
        "path": str(path),
        "ok": False,
        "status": "unavailable",
        "required_status": "development_board_source_pick_place_verified",
        "required_authority": "development_scaffold_not_reviewed",
        "ready_for_model_backed_ik_required": False,
        "diagnostics": [],
    }
    if not path.is_file():
        result["status"] = "missing"
        result["diagnostics"] = ["development_board_pick_summary_missing"]
        return result
    try:
        summary = load_json_object(path)
    except Exception as exc:
        result["status"] = "parse_error"
        result["diagnostics"] = [f"{type(exc).__name__}: {exc}"]
        return result

    required_checks = {
        "summary_ok": summary.get("ok") is True,
        "status": summary.get("status") == "development_board_source_pick_place_verified",
        "model_authority": summary.get("model_authority") == "development_scaffold_not_reviewed",
        "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik") is False,
        "ready_for_policy_training": summary.get("ready_for_policy_training") is False,
        "observed_evidence_is_physical_so101_authority": summary.get(
            "observed_evidence_is_physical_so101_authority"
        )
        is False,
        "observed_evidence_is_policy_training_authority": summary.get(
            "observed_evidence_is_policy_training_authority"
        )
        is False,
        "board_source_pick_place_verified": summary.get("board_source_pick_place_verified") is True,
        "source_pick_started_at_source": summary.get("source_pick_started_at_source") is True,
        "close_two_finger_contact_observed": summary.get("close_two_finger_contact_observed") is True,
        "lift_verified": summary.get("lift_verified") is True,
        "board_contact_cleared_during_lift": summary.get("board_contact_cleared_during_lift") is True,
        "transfer_verified": summary.get("transfer_verified") is True,
        "lower_contact_retained_before_release": summary.get(
            "lower_contact_retained_before_release"
        )
        is True,
        "lower_board_contact_observed_before_release": summary.get(
            "lower_board_contact_observed_before_release"
        )
        is True,
        "lower_target_within_tolerance_before_release": summary.get(
            "lower_target_within_tolerance_before_release"
        )
        is True,
        "lower_place_z_within_tolerance_before_release": summary.get(
            "lower_place_z_within_tolerance_before_release"
        )
        is True,
        "place_without_manual_piece_pose_verified": summary.get("place_without_manual_piece_pose_verified") is True,
        "release_contact_cleared_after_retreat": summary.get("release_contact_cleared_after_retreat") is True,
        "final_board_contact_observed": summary.get("final_board_contact_observed") is True,
        "final_target_xy_within_tolerance": (
            (final_target_xy_error_m := json_number(summary.get("final_target_xy_error_m")))
            is not None
            and (target_xy_tolerance_m := json_number(summary.get("target_xy_tolerance_m")))
            is not None
            and final_target_xy_error_m <= target_xy_tolerance_m
        ),
        "lower_target_xy_within_tolerance": (
            (lower_target_xy_error_m := json_number(summary.get("lower_target_xy_error_m")))
            is not None
            and (target_xy_tolerance_m := json_number(summary.get("target_xy_tolerance_m")))
            is not None
            and lower_target_xy_error_m <= target_xy_tolerance_m
        ),
        "lower_place_z_within_tolerance": (
            (lower_place_z_error_m := json_number(summary.get("lower_place_z_error_m")))
            is not None
            and (place_z_tolerance_m := json_number(summary.get("place_z_tolerance_m")))
            is not None
            and lower_place_z_error_m <= place_z_tolerance_m
        ),
        "final_place_z_within_tolerance": (
            (final_place_z_error_m := json_number(summary.get("final_place_z_error_m"))) is not None
            and (place_z_tolerance_m := json_number(summary.get("place_z_tolerance_m"))) is not None
            and final_place_z_error_m <= place_z_tolerance_m
        ),
        "manual_piece_pose_used_after_reset": summary.get("manual_piece_pose_used_after_reset") is False,
        "stage_sequence_contract": (
            summary.get("required_stage_sequence") == list(BOARD_PICK_REQUIRED_STAGE_SEQUENCE)
            and summary.get("observed_stage_sequence") == list(BOARD_PICK_REQUIRED_STAGE_SEQUENCE)
            and summary.get("missing_stage_ids") == []
            and summary.get("unexpected_stage_ids") == []
            and summary.get("stage_sequence_order_ok") is True
            and summary.get("stage_sequence_contract_ok") is True
            and summary.get("stage_sequence_contract_errors") == []
            and summary.get("manual_piece_pose_after_reset_stage_ids") == []
        ),
        "robot_pose_seeded_for_source_fixture": summary.get("robot_pose_seeded_for_source_fixture") is True,
    }
    missing = [key for key, ok in required_checks.items() if not ok]
    result.update(
        {
            "ok": not missing,
            "status": "development_board_pick_prerequisite_verified" if not missing else "development_board_pick_prerequisite_failed",
            "source_square": summary.get("source_square"),
            "target_square": summary.get("target_square"),
            "model_authority": summary.get("model_authority"),
            "ready_for_model_backed_ik": summary.get("ready_for_model_backed_ik"),
            "ready_for_policy_training": summary.get("ready_for_policy_training"),
            "observed_evidence_is_physical_so101_authority": summary.get(
                "observed_evidence_is_physical_so101_authority"
            ),
            "observed_evidence_is_policy_training_authority": summary.get(
                "observed_evidence_is_policy_training_authority"
            ),
            "board_source_pick_place_verified": summary.get("board_source_pick_place_verified"),
            "manual_piece_pose_used_after_reset": summary.get("manual_piece_pose_used_after_reset"),
            "required_stage_sequence": summary.get("required_stage_sequence"),
            "observed_stage_sequence": summary.get("observed_stage_sequence"),
            "missing_stage_ids": summary.get("missing_stage_ids"),
            "unexpected_stage_ids": summary.get("unexpected_stage_ids"),
            "stage_sequence_order_ok": summary.get("stage_sequence_order_ok"),
            "stage_sequence_contract_ok": summary.get("stage_sequence_contract_ok"),
            "stage_sequence_contract_errors": summary.get("stage_sequence_contract_errors"),
            "manual_piece_pose_after_reset_stage_ids": summary.get(
                "manual_piece_pose_after_reset_stage_ids"
            ),
            "robot_pose_seeded_for_source_fixture": summary.get("robot_pose_seeded_for_source_fixture"),
            "final_target_xy_error_m": summary.get("final_target_xy_error_m"),
            "target_xy_tolerance_m": summary.get("target_xy_tolerance_m"),
            "lower_contact_retained_before_release": summary.get(
                "lower_contact_retained_before_release"
            ),
            "lower_board_contact_observed_before_release": summary.get(
                "lower_board_contact_observed_before_release"
            ),
            "lower_target_within_tolerance_before_release": summary.get(
                "lower_target_within_tolerance_before_release"
            ),
            "lower_place_z_within_tolerance_before_release": summary.get(
                "lower_place_z_within_tolerance_before_release"
            ),
            "lower_target_xy_error_m": summary.get("lower_target_xy_error_m"),
            "lower_place_z_error_m": summary.get("lower_place_z_error_m"),
            "final_place_z_error_m": summary.get("final_place_z_error_m"),
            "place_z_tolerance_m": summary.get("place_z_tolerance_m"),
            "final_board_contact_observed": summary.get("final_board_contact_observed"),
            "required_checks": required_checks,
            "failed_checks": missing,
            "diagnostics": missing,
        }
    )
    return result


def observation_payload(obs: dict[str, Any]) -> dict[str, Any]:
    return {
        "joint_positions_deg": [float(value) for value in obs["joint_positions_deg"].tolist()],
        "source_square_xyz_m": [float(value) for value in obs["source_square_xyz_m"].tolist()],
        "target_square_xyz_m": [float(value) for value in obs["target_square_xyz_m"].tolist()],
        "piece_square_index": int(obs["piece_square_index"][0]),
        "holding_piece": float(obs["holding_piece"][0]),
        "phase_index": int(obs["phase_index"][0]),
        "mujoco_active": float(obs["mujoco_active"][0]),
    }


def joint_positions_from_obs(obs: dict[str, Any]) -> dict[str, float]:
    joints = obs["joint_positions_deg"]
    return {joint: float(joints[index]) for index, joint in enumerate(SO101_JOINTS)}


def piece_release_error_m(env: Any, scene_state: dict[str, Any], target_square: str) -> float:
    from lerobot.sim.chess_env import square_center_m

    mujoco_piece = scene_state["piece"].get("mujoco_freejoint") or {}
    actual_piece_xyz = mujoco_piece.get("position_xyz_m") if isinstance(mujoco_piece, dict) else None
    if not isinstance(actual_piece_xyz, list) or len(actual_piece_xyz) < 3 or not mujoco_piece.get("ok"):
        return float("inf")
    target_center = square_center_m(target_square, env.config.board_params)
    expected_piece_xyz = (
        float(env.config.board_origin_m[0] + target_center[0]),
        float(env.config.board_origin_m[1] + target_center[1]),
        float(env.config.board_origin_m[2] + target_center[2] + env.config.piece_height_m / 2.0),
    )
    return sum((float(actual_piece_xyz[index]) - expected_piece_xyz[index]) ** 2 for index in range(3)) ** 0.5


def collect_episode(
    *,
    episode_index: int,
    source_square: str,
    target_square: str,
    model_path: Path,
    max_steps: int,
    action_toward_targets: Any,
    env_cls: Any,
    env_config_cls: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    env = env_cls(
        env_config_cls(
            source_square=source_square,
            target_square=target_square,
            max_steps=max_steps,
            use_mujoco=True,
            mujoco_model_path=model_path,
        )
    )
    transitions: list[dict[str, Any]] = []
    try:
        obs, info = env.reset()
        total_reward = 0.0
        terminated = False
        truncated = False
        for step_index in range(max_steps):
            phase_index = int(obs["phase_index"][0])
            waypoint = env.waypoints[min(phase_index, len(env.waypoints) - 1)]
            action = action_toward_targets(
                joint_positions_from_obs(obs),
                waypoint.targets_deg,
                action_scale_deg=env.config.action_scale_deg,
            )
            prev_obs = observation_payload(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += float(reward)
            transitions.append(
                {
                    "schema": SCHEMA + ".transition",
                    "episode": episode_index,
                    "step": step_index + 1,
                    "task": {
                        "source_square": source_square,
                        "target_square": target_square,
                    },
                    "expert": {
                        "policy": "scripted_joint_waypoint_tracker",
                        "waypoint": waypoint.name,
                        "waypoint_index": phase_index,
                        "waypoint_targets_deg": dict(waypoint.targets_deg),
                    },
                    "observation": prev_obs,
                    "action": [float(value) for value in action.tolist()],
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "next_observation": observation_payload(obs),
                    "info": {
                        "sim_status": info["sim_status"],
                        "scene_state": info["scene_state"],
                    },
                }
            )
            if terminated or truncated:
                break
        final_scene = info["scene_state"]
        sim_status = info["sim_status"]
        release_error = piece_release_error_m(env, final_scene, target_square)
        release_synced = release_error < 1e-6
        episode = {
            "episode": episode_index,
            "source_square": source_square,
            "target_square": target_square,
            "steps": len(transitions),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "total_reward": float(total_reward),
            "final_phase_index": int(obs["phase_index"][0]),
            "final_piece_square": final_scene["piece"]["square"],
            "final_holding_piece": bool(final_scene["piece"]["held_by_gripper"]),
            "mujoco_active": bool(sim_status.get("ok")),
            "fallback": sim_status.get("fallback"),
            "mujoco_piece_release_synced": release_synced,
            "mujoco_piece_release_error_m": release_error,
            "scripted_pick_place_complete": bool(
                terminated
                and final_scene["piece"]["square"] == target_square
                and not final_scene["piece"]["held_by_gripper"]
                and sim_status.get("fallback") is None
                and release_synced
            ),
        }
        return episode, transitions
    finally:
        env.close()


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Training Rollouts",
        "",
        "This artifact records deterministic scripted expert rollouts for focused chess pick/place tasks.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Episodes: `{summary['episode_count']}`",
        f"- Transition count: `{summary['transition_count']}`",
        f"- All episodes complete: `{summary['all_scripted_pick_place_complete']}`",
        f"- MuJoCo fallback-free: `{summary['all_mujoco_fallback_free']}`",
        f"- MuJoCo piece release synced: `{summary['all_mujoco_piece_release_synced']}`",
        f"- Development board-pick prerequisite: `{summary['development_prerequisites_satisfied']}`",
        f"- Physical SO-101 authority: `{summary.get('observed_evidence_is_physical_so101_authority')}`",
        f"- Policy-training authority: `{summary.get('observed_evidence_is_policy_training_authority')}`",
        f"- Development fixture not physical truth: `{summary.get('development_fixture_evidence_not_physical_so101_truth')}`",
        f"- Development fixture not policy truth: `{summary.get('development_fixture_evidence_not_policy_training_truth')}`",
        f"- Ready for serious policy training: `{summary['ready_for_policy_training']}`",
        f"- Serious-policy blocker actions: `{summary.get('serious_policy_training_blocker_action_ids')}`",
        f"- Next action IDs sync: `{summary.get('next_required_action_ids_match_next_required')}`",
        f"- Rollouts JSONL: `{summary['artifacts']['transitions_jsonl']}`",
        "",
        "The rollouts use the development MJCF scaffold and are not physical SO-101 training truth.",
        "The board-pick prerequisite must include final board contact plus target XY and placement Z tolerance evidence, but still proves only development-fixture board-source pick/place before rollout collection.",
    ]
    path.write_text("\n".join(lines) + "\n")


def invalid_task_summary(
    *,
    args: argparse.Namespace,
    deps: dict[str, bool],
    summary_path: Path,
    transitions_path: Path,
    episodes_path: Path,
    model_path: Path,
    manifest_path: Path,
    readme_path: Path,
    message: str,
) -> dict[str, Any]:
    next_required_for_goal = [
        {
            "priority": 0,
            "missing_input": "valid_rollout_task_configuration",
            "action_id": "provide_valid_rollout_task_configuration",
            "gate": "focused_training_rollouts",
        },
        *rollout_next_required_for_goal(),
    ]
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "invalid_task_configuration",
        "dependencies": deps,
        "configuration_error": {
            "type": "ValueError",
            "message": message,
        },
        "requested_tasks": list(args.task),
        "max_steps": args.max_steps,
        "episode_count": 0,
        "transition_count": 0,
        "all_scripted_pick_place_complete": False,
        "all_mujoco_fallback_free": False,
        "all_mujoco_piece_release_synced": False,
        "development_prerequisites_satisfied": False,
        "model_authority": INVALID_TASK_MODEL_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "training_authority_status": "invalid_task_configuration",
        "board_pick_prerequisite": {
            "schema": BOARD_PICK_PREREQUISITE_SCHEMA,
            "path": str(args.development_board_pick_summary_json),
            "ok": False,
            "status": "not_checked_invalid_task_configuration",
        },
        "rollout_use": "not_collected_invalid_task_configuration",
        "serious_policy_training_blockers": [
            "valid_rollout_task_configuration",
            *ROLLOUT_SERIOUS_POLICY_TRAINING_BLOCKERS,
        ],
        **rollout_action_contract(next_required_for_goal),
        "tasks": [],
        "episodes": [],
        "artifacts": {
            "summary_json": str(summary_path),
            "transitions_jsonl": str(transitions_path),
            "episodes_csv": str(episodes_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Invalid rollout task configuration is recorded as a fail-closed artifact.",
            "No MuJoCo model generation, Gymnasium rollout, or transition collection is attempted.",
            "This failure is hardware-free and does not claim physical SO-101 or policy-training evidence.",
        ],
        "next_required_for_goal": next_required_for_goal,
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    deps = {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "gymnasium": module_available("gymnasium"),
        "mujoco": module_available("mujoco"),
    }
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    summary_path = args.output_dir / SUMMARY_NAME
    transitions_path = args.output_dir / TRANSITIONS_NAME
    episodes_path = args.output_dir / EPISODES_NAME
    readme_path = args.output_dir / README_NAME
    missing = [name for name, available in deps.items() if not available]
    configuration_error = task_configuration_error(args)
    if configuration_error is not None:
        summary = invalid_task_summary(
            args=args,
            deps=deps,
            summary_path=summary_path,
            transitions_path=transitions_path,
            episodes_path=episodes_path,
            model_path=model_path,
            manifest_path=manifest_path,
            readme_path=readme_path,
            message=configuration_error,
        )
        write_json(summary_path, summary)
        append_jsonl(transitions_path, [])
        write_episode_csv(episodes_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1
    if missing:
        next_required_for_goal = rollout_next_required_for_goal()
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "status": "missing_runtime_dependencies",
            "missing_dependencies": missing,
            "dependencies": deps,
            "episode_count": 0,
            "transition_count": 0,
            "all_scripted_pick_place_complete": False,
            "all_mujoco_fallback_free": False,
            "all_mujoco_piece_release_synced": False,
            "development_prerequisites_satisfied": False,
            "model_authority": None,
            "observed_evidence_is_physical_so101_authority": False,
            "observed_evidence_is_policy_training_authority": False,
            "development_fixture_evidence_not_physical_so101_truth": True,
            "development_fixture_evidence_not_policy_training_truth": True,
            "ready_for_model_backed_ik": False,
            "ready_for_policy_training": False,
            "training_authority_status": "missing_runtime_dependencies",
            "board_pick_prerequisite": {
                "schema": BOARD_PICK_PREREQUISITE_SCHEMA,
                "path": str(args.development_board_pick_summary_json),
                "ok": False,
                "status": "not_checked_due_to_missing_runtime_dependencies",
            },
            "serious_policy_training_blockers": list(ROLLOUT_SERIOUS_POLICY_TRAINING_BLOCKERS),
            **rollout_action_contract(next_required_for_goal),
            "next_required_for_goal": next_required_for_goal,
            "artifacts": {
                "summary_json": str(summary_path),
                "transitions_jsonl": str(transitions_path),
                "episodes_csv": str(episodes_path),
                "model_xml": str(model_path),
                "manifest_json": str(manifest_path),
                "readme": str(readme_path),
            },
        }
        write_json(summary_path, summary)
        append_jsonl(transitions_path, [])
        write_episode_csv(episodes_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    from lerobot.sim import SO101ChessEnv, SO101ChessEnvConfig, action_toward_targets
    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        write_so101_development_mjcf,
    )

    tasks = parse_tasks(args.task)
    board_pick_prerequisite = inspect_board_pick_prerequisite(args.development_board_pick_summary_json)
    first_source, first_target = tasks[0]
    manifest = write_so101_development_mjcf(
        model_path,
        SO101DevelopmentMJCFConfig(piece_square=first_source, target_square=first_target),
        manifest_path=manifest_path,
    )
    episode_rows: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for index, (source, target) in enumerate(tasks, start=1):
        episode, episode_transitions = collect_episode(
            episode_index=index,
            source_square=source,
            target_square=target,
            model_path=model_path,
            max_steps=args.max_steps,
            action_toward_targets=action_toward_targets,
            env_cls=SO101ChessEnv,
            env_config_cls=SO101ChessEnvConfig,
        )
        episode_rows.append(episode)
        transitions.extend(episode_transitions)

    all_complete = all(row["scripted_pick_place_complete"] for row in episode_rows)
    all_fallback_free = all(row["mujoco_active"] and row["fallback"] is None for row in episode_rows)
    all_release_synced = all(row["mujoco_piece_release_synced"] for row in episode_rows)
    development_prerequisites_satisfied = bool(board_pick_prerequisite.get("ok"))
    next_required_for_goal = rollout_next_required_for_goal()
    ok = (
        bool(episode_rows)
        and bool(transitions)
        and all_complete
        and all_fallback_free
        and all_release_synced
        and development_prerequisites_satisfied
    )
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "failed_prerequisite_or_rollout_check",
        "dependencies": deps,
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "development_prerequisites_satisfied": development_prerequisites_satisfied,
        "board_pick_prerequisite": board_pick_prerequisite,
        "training_authority_status": (
            "development_rollouts_prerequisites_verified_not_policy_ready"
            if development_prerequisites_satisfied
            else "missing_or_failed_development_board_pick_prerequisite"
        ),
        "ready_for_policy_training": False,
        "rollout_use": "debug_imitation_curriculum_only",
        "serious_policy_training_blockers": list(ROLLOUT_SERIOUS_POLICY_TRAINING_BLOCKERS),
        **rollout_action_contract(next_required_for_goal),
        "development_manifest": manifest,
        "tasks": [{"source_square": source, "target_square": target} for source, target in tasks],
        "episode_count": len(episode_rows),
        "transition_count": len(transitions),
        "all_scripted_pick_place_complete": all_complete,
        "all_mujoco_fallback_free": all_fallback_free,
        "all_mujoco_piece_release_synced": all_release_synced,
        "episodes": episode_rows,
        "artifacts": {
            "summary_json": str(summary_path),
            "transitions_jsonl": str(transitions_path),
            "episodes_csv": str(episodes_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Rollouts use a generated development MJCF scaffold, not a reviewed SO-101 model bundle.",
            "The expert policy tracks deterministic joint-space waypoints, not calibrated IK or learned contact behavior.",
            "The piece transfer in the environment remains symbolic until reviewed MuJoCo contact manipulation is implemented.",
            "The development board-pick prerequisite uses seeded source pose and is not reviewed model-backed IK.",
        ],
        "next_required_for_goal": next_required_for_goal,
    }
    write_json(summary_path, summary)
    append_jsonl(transitions_path, transitions)
    write_episode_csv(episodes_path, episode_rows)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": ok, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
