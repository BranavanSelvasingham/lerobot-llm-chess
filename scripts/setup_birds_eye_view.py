#!/usr/bin/env python3
"""Set up and save the bird's eye view position for board observation."""

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

# Read current position to get other joints
obs = robot.get_observation()
print("\nCurrent positions:")
for m in robot.bus.motors.keys():
    print(f"  {m}: {obs.get(f'{m}.pos', 0):.1f}")

# Load calibration to get joint limits
calib_path = Path(robot.calibration_dir) / "so101_chess.json"
calib = json.loads(calib_path.read_text())

# Compute joint limits in degrees
# The motor maps raw encoder (0-4095) to degrees via homing_offset
# For now, let's read the actual min/max by looking at the recorded range

def raw_to_deg(raw, homing_offset):
    """Convert raw encoder value to degrees (assuming 0.088 deg/step for STS3215)."""
    return (raw - 2048 - homing_offset) * 0.088

# Get wrist_flex limits
wf_calib = calib["wrist_flex"]
wf_min_deg = raw_to_deg(wf_calib["range_min"], wf_calib["homing_offset"])
wf_max_deg = raw_to_deg(wf_calib["range_max"], wf_calib["homing_offset"])
print(f"\nwrist_flex range: {wf_min_deg:.1f} to {wf_max_deg:.1f} deg")

# Get elbow_flex limits  
ef_calib = calib["elbow_flex"]
ef_min_deg = raw_to_deg(ef_calib["range_min"], ef_calib["homing_offset"])
ef_max_deg = raw_to_deg(ef_calib["range_max"], ef_calib["homing_offset"])
print(f"elbow_flex range: {ef_min_deg:.1f} to {ef_max_deg:.1f} deg")

# Build bird's eye view position per user spec:
# - m2 (shoulder_lift) = 0
# - m3 (elbow_flex) = min position
# - m4 (wrist_flex) = 70% of positive max (to look down)

# For wrist_flex: 70% of the way toward max
wf_target = wf_min_deg + 0.7 * (wf_max_deg - wf_min_deg)

birds_eye = {
    "shoulder_pan": obs.get("shoulder_pan.pos", 0),  # Keep current pan
    "shoulder_lift": 0.0,
    "elbow_flex": ef_min_deg,
    "wrist_flex": wf_target,
    "wrist_roll": obs.get("wrist_roll.pos", 0),  # Keep current roll
    "gripper": obs.get("gripper.pos", 50),
}

print(f"\nBird's eye view position:")
for m, v in birds_eye.items():
    print(f"  {m}: {v:.1f}")

response = input("\nMove to bird's eye view? (y/n): ")
if response.lower() == 'y':
    # Enable torque
    robot.bus.sync_write("Torque_Enable", 1, normalize=False)
    
    action = {f"{m}.pos": float(v) for m, v in birds_eye.items()}
    robot.send_action(action)
    
    import time
    time.sleep(2)
    
    # Read actual position
    obs = robot.get_observation()
    print("\nActual position after move:")
    for m in birds_eye.keys():
        print(f"  {m}: {obs.get(f'{m}.pos', 0):.1f}")
    
    save = input("\nSave as bird's_eye_view? (y/n): ")
    if save.lower() == 'y':
        # Re-read to get actual positions
        actual = {m: float(obs.get(f"{m}.pos", 0)) for m in robot.bus.motors.keys()}
        
        poses_path = Path(robot.calibration_dir) / "saved_positions.json"
        existing = {}
        if poses_path.exists():
            existing = json.loads(poses_path.read_text())
        
        existing["bird's_eye_view"] = {
            "description": "Bird's eye view of chessboard for vision",
            "positions": actual
        }
        
        poses_path.write_text(json.dumps(existing, indent=2))
        print(f"✓ Saved to {poses_path}")

robot.disconnect()
