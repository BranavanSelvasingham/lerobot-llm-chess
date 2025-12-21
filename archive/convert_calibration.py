#!/usr/bin/env python

"""Convert existing calibration to LeRobot MotorCalibration format."""

import json
from pathlib import Path

def convert_calibration():
    # Your working calibration data
    old_calib = {
        "homing_offset": [-1879, 3078, -1114, -1924, -1066, -2337], 
        "drive_mode": [0, 1, 0, 0, 0, 0], 
        "start_pos": [2046, 3069, 1023, 2035, 2043, 2046], 
        "end_pos": [2903, -2054, 2138, 2948, 2090, 3361], 
        "calib_mode": ["DEGREE", "DEGREE", "DEGREE", "DEGREE", "DEGREE", "LINEAR"], 
        "motor_names": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    }
    
    # Convert to MotorCalibration format
    new_calibration = {}
    for i, motor_name in enumerate(old_calib["motor_names"]):
        new_calibration[motor_name] = {
            "id": i + 1,  # Motor IDs 1-6
            "drive_mode": old_calib["drive_mode"][i],
            "homing_offset": old_calib["homing_offset"][i],
            "range_min": old_calib["start_pos"][i],
            "range_max": old_calib["end_pos"][i]
        }
    
    # Save to the expected location
    calib_dir = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower"
    calib_dir.mkdir(parents=True, exist_ok=True)
    calib_file = calib_dir / "so101_chess.json"
    
    with open(calib_file, 'w') as f:
        json.dump(new_calibration, f, indent=2)
    
    print(f"✓ Converted calibration saved to: {calib_file}")
    print("Motor calibration data:")
    for motor, data in new_calibration.items():
        print(f"  {motor}: offset={data['homing_offset']}, range=[{data['range_min']}, {data['range_max']}]")

if __name__ == "__main__":
    convert_calibration()

