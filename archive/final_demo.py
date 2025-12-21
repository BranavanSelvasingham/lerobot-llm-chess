#!/usr/bin/env python

"""Final working demo with manual calibration loading."""

import time
import argparse
import json
from pathlib import Path

from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def final_demo(port: str):
    """Demo with manually loaded calibration."""
    
    # Load your working calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    # Convert to MotorCalibration objects
    calibration = {}
    for motor_name, data in calib_data.items():
        calibration[motor_name] = MotorCalibration(
            id=data["id"],
            drive_mode=data["drive_mode"], 
            homing_offset=data["homing_offset"],
            range_min=data["range_min"],
            range_max=data["range_max"]
        )
    
    # Only use working motors
    working_motors = {
        "shoulder_pan": Motor(1, "sts3215", MotorNormMode.DEGREES),
        "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),    
        "wrist_flex": Motor(4, "sts3215", MotorNormMode.DEGREES),
        "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
    }
    
    # Create bus with calibration
    bus = FeetechMotorsBus(port=port, motors=working_motors, calibration=calibration)
    
    try:
        bus._connect(handshake=False)
        bus._assert_motors_exist()
        print("✓ Connected with calibration loaded")
        
        print("Chess demo sequence...")
        
        # 1. Open gripper
        print("1. Opening gripper...")
        bus.write("Goal_Position", "gripper", 10.0)
        time.sleep(2)
        
        # 2. Move to "pick" position
        print("2. Moving to pick position...")
        bus.write("Goal_Position", "shoulder_pan", -10.0)
        time.sleep(2)
        
        # 3. Close gripper (grasp)
        print("3. Grasping...")
        bus.write("Goal_Position", "gripper", 70.0)
        time.sleep(2)
        
        # 4. Move to "place" position  
        print("4. Moving to place position...")
        bus.write("Goal_Position", "shoulder_pan", 10.0)
        time.sleep(2)
        
        # 5. Open gripper (release)
        print("5. Releasing...")
        bus.write("Goal_Position", "gripper", 10.0)
        time.sleep(2)
        
        # 6. Return to center
        print("6. Returning to center...")
        bus.write("Goal_Position", "shoulder_pan", 0.0)
        time.sleep(2)
        
        print("🎉 Chess demo successful!")
        print("\nYour SO-101 is ready for chess! Next steps:")
        print("- Add camera to robot config")
        print("- Calibrate board position") 
        print("- Use full chess pipeline with working motors")
        
    except Exception as e:
        print(f"Demo failed: {e}")
    finally:
        try:
            bus.disconnect()
        except:
            pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    final_demo(args.port)

if __name__ == "__main__":
    main()








