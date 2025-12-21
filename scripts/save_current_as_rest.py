#!/usr/bin/env python3
"""Save current robot position as rest_position."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower

PORT = "/dev/tty.usbmodem5A460825871"

print("Connecting...")
robot_cfg = SO101FollowerConfig(port=PORT, id="so101_chess", cameras={}, use_degrees=True)
robot = SO101Follower(robot_cfg)
robot.connect(calibrate=False, skip_firmware_check=True)

# Disable torque so you can position the arm
print("Torque disabled - move arm to rest position, then press ENTER")
robot.bus.sync_write("Torque_Enable", 0, normalize=False)

input("Press ENTER when arm is in rest position...")

# Read current positions
obs = robot.get_observation()
positions = {m: float(obs.get(f"{m}.pos", 0)) for m in robot.bus.motors.keys()}

print(f"\nCurrent positions:")
for m, v in positions.items():
    print(f"  {m}: {v:.1f}")

# Load existing saved_positions.json
poses_path = Path(robot.calibration_dir) / "saved_positions.json"
existing = {}
if poses_path.exists():
    existing = json.loads(poses_path.read_text())

# Update rest_position
existing["rest_position"] = {
    "description": "Rest position (with new calibration)",
    "positions": positions
}

poses_path.write_text(json.dumps(existing, indent=2))
print(f"\n✓ Saved rest_position to {poses_path}")

robot.disconnect()
