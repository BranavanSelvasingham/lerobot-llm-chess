#!/usr/bin/env python

"""Clean calibration file to remove extra fields."""

import json
from pathlib import Path

def clean_calibration():
    """Remove extra fields from calibration that aren't part of MotorCalibration."""
    
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    # Clean each motor calibration to only include MotorCalibration fields
    cleaned_calibration = {}
    for motor_name, data in calib_data.items():
        cleaned_calibration[motor_name] = {
            "id": data["id"],
            "drive_mode": data["drive_mode"],
            "homing_offset": data["homing_offset"],
            "range_min": data["range_min"],
            "range_max": data["range_max"]
        }
    
    # Save cleaned version
    with open(calib_file, 'w') as f:
        json.dump(cleaned_calibration, f, indent=2)
    
    print(f"✓ Cleaned calibration file: {calib_file}")
    print("Removed extra fields, kept only MotorCalibration fields")

if __name__ == "__main__":
    clean_calibration()








