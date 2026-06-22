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


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_env_resets"
SUMMARY_NAME = "so101_env_resets_summary.json"
RESETS_NAME = "so101_env_resets.csv"
INVALID_RESETS_NAME = "so101_env_reset_invalid_cases.csv"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.so101_env_resets.v1"
DEFAULT_TASK_POOL: tuple[tuple[str, str], ...] = (
    ("e4", "e5"),
    ("a4", "a5"),
    ("b8", "c8"),
    ("e2", "e3"),
    ("d4", "f4"),
)
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
        description="Validate SO-101 chess env reset task overrides and sampled task resets in strict MuJoCo mode."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_reset_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "mode",
        "seed",
        "source_square",
        "target_square",
        "piece_square_index",
        "phase_index",
        "step_count",
        "mujoco_active",
        "fallback",
        "mujoco_piece_freejoint_ok",
        "mujoco_piece_position_error_m",
        "first_step_reward",
        "ok",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_invalid_reset_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "seed",
        "options",
        "rejected",
        "error_type",
        "error_message",
        "expected_error_contains",
        "recovery_source_square",
        "recovery_target_square",
        "recovery_piece_square_index",
        "recovery_phase_index",
        "recovery_mujoco_active",
        "recovery_fallback",
        "recovery_error_type",
        "recovery_error_message",
        "recovery_ok",
        "ok",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = {}
            for field in fieldnames:
                value = row.get(field, "")
                if isinstance(value, (dict, list, tuple)):
                    value = json.dumps(value, sort_keys=True)
                normalized[field] = value
            writer.writerow(normalized)


def joint_positions_from_obs(obs: dict[str, Any]) -> dict[str, float]:
    joints = obs["joint_positions_deg"]
    return {joint: float(joints[index]) for index, joint in enumerate(SO101_JOINTS)}


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Env Reset Smoke",
        "",
        "This smoke verifies per-episode source/target reset behavior in strict MuJoCo mode.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Model authority: `{summary.get('model_authority')}`",
        f"- Physical SO-101 authority: `{summary.get('observed_evidence_is_physical_so101_authority')}`",
        f"- Policy-training authority: `{summary.get('observed_evidence_is_policy_training_authority')}`",
        f"- Development fixture not physical truth: `{summary.get('development_fixture_evidence_not_physical_so101_truth')}`",
        f"- Development fixture not policy truth: `{summary.get('development_fixture_evidence_not_policy_training_truth')}`",
        f"- Ready for model-backed IK: `{summary.get('ready_for_model_backed_ik')}`",
        f"- Ready for policy training: `{summary.get('ready_for_policy_training')}`",
        f"- Reset count: `{summary['reset_count']}`",
        f"- All resets ok: `{summary['all_resets_ok']}`",
        f"- All MuJoCo fallback-free: `{summary['all_mujoco_fallback_free']}`",
        f"- Invalid reset count: `{summary.get('invalid_reset_count')}`",
        f"- All invalid resets rejected: `{summary.get('all_invalid_resets_rejected')}`",
        f"- Recovery after invalid resets ok: `{summary.get('recovery_after_invalid_resets_ok')}`",
        f"- Rows CSV: `{summary['artifacts']['resets_csv']}`",
        f"- Invalid rows CSV: `{summary['artifacts']['invalid_reset_cases_csv']}`",
        "",
        "The model remains the generated development scaffold and is not reviewed SO-101 calibration truth.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    deps = {
        "numpy": module_available("numpy"),
        "draccus": module_available("draccus"),
        "gymnasium": module_available("gymnasium"),
        "mujoco": module_available("mujoco"),
    }
    summary_path = args.output_dir / SUMMARY_NAME
    resets_path = args.output_dir / RESETS_NAME
    invalid_resets_path = args.output_dir / INVALID_RESETS_NAME
    model_path = args.output_dir / MODEL_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    readme_path = args.output_dir / README_NAME
    missing = [name for name, available in deps.items() if not available]
    if missing:
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "status": "missing_runtime_dependencies",
            "missing_dependencies": missing,
            "dependencies": deps,
            "model_authority": None,
            "observed_evidence_is_physical_so101_authority": False,
            "observed_evidence_is_policy_training_authority": False,
            "development_fixture_evidence_not_physical_so101_truth": True,
            "development_fixture_evidence_not_policy_training_truth": True,
            "ready_for_model_backed_ik": False,
            "ready_for_policy_training": False,
            "reset_count": 0,
            "all_resets_ok": False,
            "all_mujoco_fallback_free": False,
            "invalid_reset_count": 0,
            "all_invalid_resets_rejected": False,
            "recovery_after_invalid_resets_ok": False,
            "invalid_reset_failed_case_ids": [],
            "artifacts": {
                "summary_json": str(summary_path),
                "resets_csv": str(resets_path),
                "invalid_reset_cases_csv": str(invalid_resets_path),
                "model_xml": str(model_path),
                "manifest_json": str(manifest_path),
                "readme": str(readme_path),
            },
        }
        write_json(summary_path, summary)
        write_reset_rows(resets_path, [])
        write_invalid_reset_rows(invalid_resets_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    from lerobot.sim import SO101ChessEnv, SO101ChessEnvConfig, action_toward_targets, square_index
    from lerobot.sim.chess_env import square_center_m
    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        write_so101_development_mjcf,
    )

    first_source, first_target = DEFAULT_TASK_POOL[0]
    manifest = write_so101_development_mjcf(
        model_path,
        SO101DevelopmentMJCFConfig(piece_square=first_source, target_square=first_target),
        manifest_path=manifest_path,
    )
    env = SO101ChessEnv(
        SO101ChessEnvConfig(
            source_square=first_source,
            target_square=first_target,
            task_pool=DEFAULT_TASK_POOL,
            use_mujoco=True,
            mujoco_model_path=model_path,
        )
    )
    cases = [
        {"case_id": "explicit_center", "mode": "explicit", "seed": 101, "options": {"source_square": "e4", "target_square": "e5"}},
        {"case_id": "explicit_edge", "mode": "explicit", "seed": 102, "options": {"task": ("a4", "a5")}},
        {"case_id": "explicit_back_rank", "mode": "explicit", "seed": 103, "options": {"task": {"source": "b8", "target": "c8"}}},
        {"case_id": "sample_seed_11", "mode": "sample", "seed": 11, "options": {"sample_task": True}},
        {"case_id": "sample_seed_12", "mode": "sample", "seed": 12, "options": {"sample_task": True}},
    ]
    invalid_cases = [
        {
            "case_id": "invalid_source_square_rejected",
            "seed": 201,
            "options": {"source_square": "i9", "target_square": "e5"},
            "expected_error_contains": "Invalid chess square",
        },
        {
            "case_id": "invalid_target_square_rejected",
            "seed": 202,
            "options": {"source_square": "e4", "target_square": "i9"},
            "expected_error_contains": "Invalid chess square",
        },
        {
            "case_id": "identical_source_target_rejected",
            "seed": 203,
            "options": {"source_square": "e4", "target_square": "e4"},
            "expected_error_contains": "source_square and target_square must differ",
        },
        {
            "case_id": "malformed_task_option_rejected",
            "seed": 204,
            "options": {"task": "e4:e5"},
            "expected_error_contains": "reset option 'task' must be a dict or a 2-item sequence",
        },
        {
            "case_id": "sample_without_task_pool_rejected",
            "seed": 205,
            "options": {"sample_task": True, "task_pool": []},
            "expected_error_contains": "sample_task requested but no task_pool was supplied",
        },
    ]
    rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    def evaluate_reset_case(case: dict[str, Any]) -> dict[str, Any]:
        obs, info = env.reset(seed=case["seed"], options=case["options"])
        task = info["task"]
        sim_status = info["sim_status"]
        mujoco_piece = info["scene_state"]["piece"].get("mujoco_freejoint") or {}
        source_center = square_center_m(task["source_square"], env.config.board_params)
        expected_piece_xyz = (
            float(env.config.board_origin_m[0] + source_center[0]),
            float(env.config.board_origin_m[1] + source_center[1]),
            float(env.config.board_origin_m[2] + source_center[2] + env.config.piece_height_m / 2.0),
        )
        actual_piece_xyz = mujoco_piece.get("position_xyz_m") if isinstance(mujoco_piece, dict) else None
        if isinstance(actual_piece_xyz, list) and len(actual_piece_xyz) >= 3:
            piece_error = sum((float(actual_piece_xyz[index]) - expected_piece_xyz[index]) ** 2 for index in range(3)) ** 0.5
        else:
            piece_error = float("inf")
        piece_freejoint_ok = bool(mujoco_piece.get("ok")) and piece_error < 1e-6
        waypoint = env.waypoints[0]
        action = action_toward_targets(
            joint_positions_from_obs(obs),
            waypoint.targets_deg,
            action_scale_deg=env.config.action_scale_deg,
        )
        _, reward, _, _, step_info = env.step(action)
        reset_ok = (
            int(obs["phase_index"][0]) == 0
            and int(obs["piece_square_index"][0]) == square_index(task["source_square"])
            and float(obs["holding_piece"][0]) == 0.0
            and float(obs["mujoco_active"][0]) == 1.0
            and sim_status.get("fallback") is None
            and piece_freejoint_ok
            and step_info["step_count"] == 1
        )
        return {
            "case_id": case["case_id"],
            "mode": case["mode"],
            "seed": case["seed"],
            "source_square": task["source_square"],
            "target_square": task["target_square"],
            "piece_square_index": int(obs["piece_square_index"][0]),
            "phase_index": int(obs["phase_index"][0]),
            "step_count": info["step_count"],
            "mujoco_active": bool(sim_status.get("ok")),
            "fallback": sim_status.get("fallback"),
            "mujoco_piece_freejoint_ok": piece_freejoint_ok,
            "mujoco_piece_position_error_m": piece_error,
            "first_step_reward": float(reward),
            "ok": bool(reset_ok),
        }

    try:
        for case in cases:
            rows.append(evaluate_reset_case(case))
        for case in invalid_cases:
            rejected = False
            error_type = ""
            error_message = ""
            try:
                env.reset(seed=case["seed"], options=case["options"])
            except Exception as exc:  # noqa: BLE001 - the artifact records unexpected exception classes.
                rejected = True
                error_type = type(exc).__name__
                error_message = str(exc)

            recovery_error_type = ""
            recovery_error_message = ""
            recovery_row: dict[str, Any] = {}
            try:
                recovery_row = evaluate_reset_case(
                    {
                        "case_id": f"{case['case_id']}_recovery",
                        "mode": "recovery",
                        "seed": int(case["seed"]) + 1000,
                        "options": {"source_square": "e4", "target_square": "e5"},
                    }
                )
            except Exception as exc:  # noqa: BLE001 - recovery failures should be captured as evidence.
                recovery_error_type = type(exc).__name__
                recovery_error_message = str(exc)

            expected_error = str(case["expected_error_contains"])
            row = {
                "case_id": case["case_id"],
                "seed": case["seed"],
                "options": case["options"],
                "rejected": rejected,
                "error_type": error_type,
                "error_message": error_message,
                "expected_error_contains": expected_error,
                "recovery_source_square": recovery_row.get("source_square"),
                "recovery_target_square": recovery_row.get("target_square"),
                "recovery_piece_square_index": recovery_row.get("piece_square_index"),
                "recovery_phase_index": recovery_row.get("phase_index"),
                "recovery_mujoco_active": recovery_row.get("mujoco_active"),
                "recovery_fallback": recovery_row.get("fallback"),
                "recovery_error_type": recovery_error_type,
                "recovery_error_message": recovery_error_message,
                "recovery_ok": bool(recovery_row.get("ok")),
            }
            row["ok"] = bool(
                row["rejected"]
                and row["error_type"] == "ValueError"
                and expected_error in row["error_message"]
                and row["recovery_ok"]
            )
            invalid_rows.append(row)
    finally:
        env.close()

    all_ok = all(bool(row["ok"]) for row in rows)
    all_fallback_free = all(bool(row["mujoco_active"]) and row["fallback"] in (None, "") for row in rows)
    all_invalid_rejected = bool(invalid_rows) and all(
        bool(row["rejected"])
        and row["error_type"] == "ValueError"
        and str(row["expected_error_contains"]) in str(row["error_message"])
        for row in invalid_rows
    )
    recovery_after_invalid_ok = bool(invalid_rows) and all(bool(row["recovery_ok"]) for row in invalid_rows)
    invalid_failed_case_ids = [str(row["case_id"]) for row in invalid_rows if not row["ok"]]
    sampled_tasks = sorted({(row["source_square"], row["target_square"]) for row in rows if row["mode"] == "sample"})
    summary = {
        "schema": SCHEMA,
        "ok": bool(rows) and all_ok and all_fallback_free and not invalid_failed_case_ids,
        "status": "ok" if bool(rows) and all_ok and all_fallback_free and not invalid_failed_case_ids else "failed",
        "dependencies": deps,
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "observed_evidence_is_physical_so101_authority": False,
        "observed_evidence_is_policy_training_authority": False,
        "development_fixture_evidence_not_physical_so101_truth": True,
        "development_fixture_evidence_not_policy_training_truth": True,
        "ready_for_model_backed_ik": False,
        "ready_for_policy_training": False,
        "development_manifest": manifest,
        "task_pool": [{"source_square": source, "target_square": target} for source, target in DEFAULT_TASK_POOL],
        "reset_count": len(rows),
        "all_resets_ok": all_ok,
        "all_mujoco_fallback_free": all_fallback_free,
        "invalid_reset_count": len(invalid_rows),
        "invalid_reset_case_ids": [str(row["case_id"]) for row in invalid_rows],
        "invalid_reset_failed_case_ids": invalid_failed_case_ids,
        "all_invalid_resets_rejected": all_invalid_rejected,
        "recovery_after_invalid_resets_ok": recovery_after_invalid_ok,
        "sampled_tasks": [{"source_square": source, "target_square": target} for source, target in sampled_tasks],
        "rows": rows,
        "invalid_reset_rows": invalid_rows,
        "artifacts": {
            "summary_json": str(summary_path),
            "resets_csv": str(resets_path),
            "invalid_reset_cases_csv": str(invalid_resets_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "Reset validation uses the development MJCF scaffold, not a reviewed SO-101 model bundle.",
            "Reset task changes update the symbolic env scene; reviewed MuJoCo contact reset state still needs real model/TCP alignment.",
            "Invalid reset cases prove fail-closed Gymnasium task wiring only, not physical calibration safety.",
        ],
    }
    write_json(summary_path, summary)
    write_reset_rows(resets_path, rows)
    write_invalid_reset_rows(invalid_resets_path, invalid_rows)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": summary["ok"], "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
