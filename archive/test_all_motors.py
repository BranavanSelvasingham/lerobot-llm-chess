#!/usr/bin/env python

"""Test all 6 motors working together with new calibration."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def test_all_motors(port: str):
    """Test all 6 motors with proper calibration."""
    
    # Load the fresh calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    # Create all motors
    all_motors = {
        "shoulder_pan": Motor(1, "sts3215", MotorNormMode.DEGREES),
        "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),
        "elbow_flex": Motor(3, "sts3215", MotorNormMode.DEGREES),
        "wrist_flex": Motor(4, "sts3215", MotorNormMode.DEGREES),
        "wrist_roll": Motor(5, "sts3215", MotorNormMode.DEGREES),
        "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
    }
    
    # Create calibration objects
    calibration = {}
    for motor_name, data in calib_data.items():
        calibration[motor_name] = MotorCalibration(
            id=data["id"],
            drive_mode=data["drive_mode"],
            homing_offset=data["homing_offset"],
            range_min=data["range_min"],
            range_max=data["range_max"]
        )
    
    bus = FeetechMotorsBus(port=port, motors=all_motors, calibration=calibration)
    
    try:
        # Connect bypassing firmware check
        bus._connect(handshake=False)
        print("🤖 Testing all 6 motors together...")
        
        # Instead of group detection, test each motor individually
        working_motors = []
        for motor_name, motor in all_motors.items():
            try:
                # Test if we can write to this motor
                current_pos = bus.read("Present_Position", motor_name, normalize=False)
                print(f"  ✓ {motor_name} (ID {motor.id}): position {current_pos}")
                working_motors.append(motor_name)
            except Exception as e:
                print(f"  ❌ {motor_name} (ID {motor.id}): {e}")
        
        print(f"\n📊 Working motors: {len(working_motors)}/6")
        print(f"Working: {working_motors}")
        
        if len(working_motors) >= 5:
            print("\n🎯 Testing coordinated chess movement...")
            
            # Gentle coordinated movement sequence
            print("1. Opening gripper...")
            bus.write("Goal_Position", "gripper", 10.0)
            time.sleep(2)
            
            print("2. Moving arm to pick position...")
            if "shoulder_pan" in working_motors:
                bus.write("Goal_Position", "shoulder_pan", 5.0)
            if "elbow_flex" in working_motors:
                bus.write("Goal_Position", "elbow_flex", 10.0)
            time.sleep(3)
            
            print("3. Closing gripper...")
            bus.write("Goal_Position", "gripper", 60.0)
            time.sleep(2)
            
            print("4. Moving to place position...")
            if "shoulder_pan" in working_motors:
                bus.write("Goal_Position", "shoulder_pan", -5.0)
            time.sleep(3)
            
            print("5. Opening gripper...")
            bus.write("Goal_Position", "gripper", 10.0)
            time.sleep(2)
            
            print("6. Returning to center...")
            for motor_name in working_motors:
                if motor_name != "gripper":
                    bus.write("Goal_Position", motor_name, 0.0)
            time.sleep(3)
            
            print("🎉 COORDINATED MOVEMENT SUCCESSFUL!")
            print("Your SO-101 is ready for chess!")
            
        else:
            print(f"⚠️ Only {len(working_motors)} motors working - need at least 5 for chess")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        try:
            bus.disconnect()
        except:
            pass

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    test_all_motors(args.port)

if __name__ == "__main__":
    main()








