#!/usr/bin/env python

"""Manual calibration helper for SO-101 with firmware mismatch."""

import json
from pathlib import Path

def create_dummy_calibration():
    """Create a dummy calibration file to bypass the calibration requirement."""
    
    # Default calibration dir
    calib_dir = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower"
    calib_dir.mkdir(parents=True, exist_ok=True)
    calib_file = calib_dir / "so101_chess.json"
    
    # Create dummy calibration data matching MotorCalibration dataclass
    dummy_calibration = {
        "shoulder_pan": {
            "id": 1,
            "drive_mode": 0,
            "homing_offset": 0,
            "range_min": 0,
            "range_max": 4095
        },
        "shoulder_lift": {
            "id": 2,
            "drive_mode": 0, 
            "homing_offset": 0,
            "range_min": 0,
            "range_max": 4095
        },
        "elbow_flex": {
            "id": 3,
            "drive_mode": 0,
            "homing_offset": 0, 
            "range_min": 0,
            "range_max": 4095
        },
        "wrist_flex": {
            "id": 4,
            "drive_mode": 0,
            "homing_offset": 0,
            "range_min": 0,
            "range_max": 4095
        },
        "wrist_roll": {
            "id": 5,
            "drive_mode": 0,
            "homing_offset": 0,
            "range_min": 0,
            "range_max": 4095
        },
        "gripper": {
            "id": 6,
            "drive_mode": 0,
            "homing_offset": 0,
            "range_min": 0,
            "range_max": 4095
        }
    }
    
    with open(calib_file, 'w') as f:
        json.dump(dummy_calibration, f, indent=2)
    
    print(f"✓ Created dummy calibration at: {calib_file}")
    print("This bypasses calibration requirements. Adjust offsets manually if needed.")

if __name__ == "__main__":
    create_dummy_calibration()
