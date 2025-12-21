#!/usr/bin/env python

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.utils.utils import log_say


@dataclass
class HomeConfig:
    port: str
    save: bool = False
    go: bool = True
    name: str = "rest_position"
    skip_calibration: bool = False


def _parse_args() -> HomeConfig:
    p = argparse.ArgumentParser(description="Save or go to a home joint pose")
    p.add_argument("--port", required=True)
    p.add_argument("--save", action="store_true")
    p.add_argument("--go", action="store_true")
    p.add_argument(
        "--name",
        default="rest_position",
        help="Pose name in saved_positions.json (default: rest_position).",
    )
    p.add_argument("--skip-calibration", action="store_true", help="Skip robot calibration")
    a = p.parse_args()
    # Default to go if neither flag set
    if not a.save and not a.go:
        a.go = True
    return HomeConfig(
        port=a.port,
        save=a.save,
        go=a.go,
        name=str(getattr(a, "name", "rest_position")),
        skip_calibration=getattr(a, "skip_calibration", False),
    )


def main(cfg: HomeConfig | None = None) -> None:
    if cfg is None:
        cfg = _parse_args()
    robot_cfg = SO101FollowerConfig(port=cfg.port, id="so101_chess", cameras={}, use_degrees=True)
    robot = SO101Follower(robot_cfg)
    robot.connect(calibrate=not cfg.skip_calibration, skip_firmware_check=True)

    poses_path = Path(robot.calibration_dir) / "saved_positions.json"
    pose_name = (cfg.name or "rest_position").strip()

    if cfg.save:
        obs = robot.get_observation()
        positions = {m: float(obs.get(f"{m}.pos")) for m in robot.bus.motors.keys()}

        payload: dict = {}
        if poses_path.exists():
            try:
                payload = json.loads(poses_path.read_text())
            except Exception:
                payload = {}

        payload[pose_name] = {
            "description": f"Saved position: {pose_name}",
            "positions": positions,
        }
        poses_path.write_text(json.dumps(payload, indent=2))
        log_say(f"Saved pose '{pose_name}' to {poses_path}")
        return

    if cfg.go:
        if not poses_path.exists():
            raise SystemExit(f"No saved poses found at {poses_path}. Run with --save first.")
        obj = json.loads(poses_path.read_text())
        pos = (obj.get(pose_name) or {}).get("positions") or {}
        if not isinstance(pos, dict) or not pos:
            raise SystemExit(f"Pose '{pose_name}' not found in {poses_path}.")

        action = {f"{m}.pos": float(pos[m]) for m in robot.bus.motors.keys() if m in pos}
        if not action:
            raise SystemExit(f"Pose '{pose_name}' has no motor positions.")
        robot.send_action(action)
        log_say(f"Moved to pose '{pose_name}'.")


if __name__ == "__main__":
    main()


