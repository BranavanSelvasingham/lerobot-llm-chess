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


DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "so101_mujoco_contact_probe"
SUMMARY_NAME = "so101_mujoco_contact_probe_summary.json"
ROWS_NAME = "so101_mujoco_contact_probe_rows.csv"
MODEL_NAME = "so101_chess_development.xml"
MANIFEST_NAME = "so101_chess_development_manifest.json"
README_NAME = "README.md"
SCHEMA = "lerobot.sim.so101_mujoco_contact_probe.v1"
PROBE_SQUARES = ("e4", "a4", "b8", "e2")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe resettable piece freejoint and basic MuJoCo contact plumbing "
            "in the development SO-101 chess scene."
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
        "square",
        "expected_x",
        "expected_y",
        "expected_z",
        "actual_x",
        "actual_y",
        "actual_z",
        "position_error_m",
        "board_contact_count",
        "any_contact_count",
        "ok",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def reset_piece_pose(module: Any, model: Any, data: Any, *, square: str, config: Any) -> tuple[float, float, float]:
    joint_id = module.mj_name2id(model, module.mjtObj.mjOBJ_JOINT, "piece_source_freejoint")
    if joint_id < 0:
        raise AssertionError("piece_source_freejoint missing from generated model.")
    qpos_addr = int(model.jnt_qposadr[joint_id])
    x, y, z = config_square_contact_pose(square, config)
    data.qpos[qpos_addr : qpos_addr + 7] = [x, y, z + 0.012, 1.0, 0.0, 0.0, 0.0]
    data.qvel[:] = 0.0
    module.mj_forward(model, data)
    return x, y, z


def config_square_contact_pose(square: str, config: Any) -> tuple[float, float, float]:
    from lerobot.sim.mujoco_scene import square_center_world_m

    x, y, board_surface_z = square_center_world_m(square, config)
    return x, y, board_surface_z + config.piece_height_m / 2.0


def body_position(module: Any, model: Any, data: Any, body_name: str) -> tuple[float, float, float]:
    body_id = module.mj_name2id(model, module.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise AssertionError(f"{body_name} missing from generated model.")
    values = data.xpos[body_id]
    return float(values[0]), float(values[1]), float(values[2])


def contact_counts(module: Any, model: Any, data: Any) -> tuple[int, int]:
    board_id = module.mj_name2id(model, module.mjtObj.mjOBJ_GEOM, "chess_board_collision")
    piece_id = module.mj_name2id(model, module.mjtObj.mjOBJ_GEOM, "piece_source_collision")
    if board_id < 0 or piece_id < 0:
        raise AssertionError("Required board/piece geoms missing.")
    board_contacts = 0
    for index in range(data.ncon):
        contact = data.contact[index]
        if {int(contact.geom1), int(contact.geom2)} == {board_id, piece_id}:
            board_contacts += 1
    return board_contacts, int(data.ncon)


def settle_piece(module: Any, model: Any, data: Any, *, steps: int = 250) -> None:
    for _ in range(steps):
        module.mj_step(model, data)


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 MuJoCo Contact Probe",
        "",
        "This smoke validates resettable piece-body and contact plumbing in the generated development MJCF scene.",
        "",
        f"- Status: `{summary['status']}`",
        f"- Probe count: `{summary['probe_count']}`",
        f"- All piece resets ok: `{summary['all_piece_resets_ok']}`",
        f"- All board contacts observed: `{summary['all_board_contacts_observed']}`",
        f"- Rows CSV: `{summary['artifacts']['rows_csv']}`",
        "",
        "This remains a development scaffold and does not prove real SO-101 grasp physics.",
    ]
    path.write_text("\n".join(lines) + "\n")


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
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "status": "missing_runtime_dependencies",
            "missing_dependencies": missing,
            "dependencies": deps,
            "probe_count": 0,
            "all_piece_resets_ok": False,
            "all_board_contacts_observed": False,
            "artifacts": {
                "summary_json": str(summary_path),
                "rows_csv": str(rows_path),
                "model_xml": str(model_path),
                "manifest_json": str(manifest_path),
                "readme": str(readme_path),
            },
        }
        write_json(summary_path, summary)
        write_rows(rows_path, [])
        write_readme(readme_path, summary)
        print(json.dumps({"ok": False, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
        return 1

    import mujoco

    from lerobot.sim.mujoco_scene import (
        SO101_DEV_MJCF_AUTHORITY,
        SO101DevelopmentMJCFConfig,
        write_so101_development_mjcf,
    )

    config = SO101DevelopmentMJCFConfig(piece_square="e4", target_square="e5")
    manifest = write_so101_development_mjcf(model_path, config, manifest_path=manifest_path)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    rows: list[dict[str, Any]] = []
    for square in PROBE_SQUARES:
        expected = reset_piece_pose(mujoco, model, data, square=square, config=config)
        settle_piece(mujoco, model, data)
        actual = body_position(mujoco, model, data, "piece_source")
        board_contacts, any_contacts = contact_counts(mujoco, model, data)
        error = sum((actual[index] - expected[index]) ** 2 for index in range(3)) ** 0.5
        rows.append(
            {
                "square": square,
                "expected_x": expected[0],
                "expected_y": expected[1],
                "expected_z": expected[2],
                "actual_x": actual[0],
                "actual_y": actual[1],
                "actual_z": actual[2],
                "position_error_m": error,
                "board_contact_count": board_contacts,
                "any_contact_count": any_contacts,
                "ok": bool(error < 0.02 and board_contacts > 0),
            }
        )

    all_resets_ok = all(float(row["position_error_m"]) < 0.02 for row in rows)
    all_contacts = all(int(row["board_contact_count"]) > 0 for row in rows)
    ok = bool(rows) and all_resets_ok and all_contacts
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "failed",
        "dependencies": deps,
        "model_authority": SO101_DEV_MJCF_AUTHORITY,
        "ready_for_model_backed_ik": False,
        "development_manifest": manifest,
        "probe_count": len(rows),
        "all_piece_resets_ok": all_resets_ok,
        "all_board_contacts_observed": all_contacts,
        "rows": rows,
        "artifacts": {
            "summary_json": str(summary_path),
            "rows_csv": str(rows_path),
            "model_xml": str(model_path),
            "manifest_json": str(manifest_path),
            "readme": str(readme_path),
        },
        "limitations": [
            "This validates freejoint reset and board contact only in the generated development MJCF.",
            "It does not prove gripper grasp, lift, place, friction tuning, calibrated TCP, or real SO-101 geometry.",
        ],
        "next_required_for_goal": [
            "Add gripper/piece contact and lift/place probes after reviewed TCP and model alignment are available.",
            "Replace development scaffold with reviewed model bundle before physical training claims.",
        ],
    }
    write_json(summary_path, summary)
    write_rows(rows_path, rows)
    write_readme(readme_path, summary)
    print(json.dumps({"ok": ok, "status": summary["status"], "summary_json": str(summary_path)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
