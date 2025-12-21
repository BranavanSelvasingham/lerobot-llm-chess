#!/usr/bin/env python

"""Create calibration for only the working motors."""

import json
from pathlib import Path

def create_working_calibration():
    """Create calibration for motors 1,2,4,6 only."""
    
    # From your working calibration, extract only the detected motors
    old_calib = {
        "homing_offset": [-1879, 3078, -1114, -1924, -1066, -2337], 
        "drive_mode": [0, 1, 0, 0, 0, 0], 
        "start_pos": [2046, 3069, 1023, 2035, 2043, 2046], 
        "end_pos": [2903, -2054, 2138, 2948, 2090, 3361], 
        "motor_names": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    }
    
    # Only include working motors (IDs 1,2,4,6)
    working_indices = [0, 1, 3, 5]  # shoulder_pan, shoulder_lift, wrist_flex, gripper
    working_names = ["shoulder_pan", "shoulder_lift", "wrist_flex", "gripper"]
    working_ids = [1, 2, 4, 6]
    
    new_calibration = {}
    for i, motor_name in enumerate(working_names):
        old_idx = working_indices[i]
        new_calibration[motor_name] = {
            "id": working_ids[i],
            "drive_mode": old_calib["drive_mode"][old_idx],
            "homing_offset": old_calib["homing_offset"][old_idx],
            "range_min": old_calib["start_pos"][old_idx],
            "range_max": old_calib["end_pos"][old_idx]
        }
    
    # Save calibration
    calib_dir = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower"
    calib_dir.mkdir(parents=True, exist_ok=True)
    calib_file = calib_dir / "so101_chess.json"
    
    with open(calib_file, 'w') as f:
        json.dump(new_calibration, f, indent=2)
    
    print(f"✓ Working motors calibration saved to: {calib_file}")
    print("Working motors calibration:")
    for motor, data in new_calibration.items():
        print(f"  {motor}: offset={data['homing_offset']}, range=[{data['range_min']}, {data['range_max']}]")

if __name__ == "__main__":
    create_working_calibration()








