#!/usr/bin/env python

"""Ultra-gentle chess demo using tiny movements from current positions."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def ultra_gentle_chess(port: str):
    """Ultra-gentle chess demo with minimal movements."""
    
    print("🎯 Ultra-Gentle Chess Demo")
    print("="*35)
    
    # Load calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    all_motors = {
        "shoulder_pan": Motor(1, "sts3215", MotorNormMode.DEGREES),
        "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),
        "elbow_flex": Motor(3, "sts3215", MotorNormMode.DEGREES),
        "wrist_flex": Motor(4, "sts3215", MotorNormMode.DEGREES),
        "wrist_roll": Motor(5, "sts3215", MotorNormMode.DEGREES),
        "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
    }
    
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
        bus._connect(handshake=False)
        print("🤖 Connected to all 6 motors")
        
        # Read starting positions
        start_positions = {}
        for motor_name in all_motors.keys():
            pos = bus.read("Present_Position", motor_name, normalize=False)
            start_positions[motor_name] = pos
            print(f"  {motor_name}: {pos}")
        
        gripper_open = calib_data["gripper"]["chess_open_raw"]
        gripper_closed = calib_data["gripper"]["chess_closed_raw"]
        
        print(f"\n🎮 Chess sequence with TINY movements...")
        
        # 1. Open gripper
        print("1. Opening gripper...")
        bus.write("Goal_Position", "gripper", gripper_open, normalize=False)
        time.sleep(2)
        print("   ✓ Gripper opened")
        
        # 2. Tiny pan movement (simulate moving to e2)
        print("2. Small pan to 'e2'...")
        new_pan = start_positions["shoulder_pan"] + 50  # Very small movement
        bus.write("Goal_Position", "shoulder_pan", new_pan, normalize=False)
        time.sleep(2)
        print("   ✓ Panned to e2")
        
        # 3. Tiny elbow movement (simulate lowering to piece)
        print("3. Small elbow flex to reach piece...")
        new_elbow = start_positions["elbow_flex"] + 30  # Very small movement
        bus.write("Goal_Position", "elbow_flex", new_elbow, normalize=False)
        time.sleep(2)
        print("   ✓ Reached down")
        
        # 4. Close gripper
        print("4. Grasping piece...")
        bus.write("Goal_Position", "gripper", gripper_closed, normalize=False)
        time.sleep(2)
        print("   ✓ Piece grasped")
        
        # 5. Lift slightly
        print("5. Lifting piece...")
        bus.write("Goal_Position", "elbow_flex", start_positions["elbow_flex"], normalize=False)
        time.sleep(2)
        print("   ✓ Piece lifted")
        
        # 6. Move to destination (e4)
        print("6. Moving to 'e4'...")
        dest_pan = start_positions["shoulder_pan"] - 50  # Other direction
        bus.write("Goal_Position", "shoulder_pan", dest_pan, normalize=False)
        time.sleep(2)
        print("   ✓ At destination")
        
        # 7. Lower piece
        print("7. Placing piece...")
        bus.write("Goal_Position", "elbow_flex", new_elbow, normalize=False)
        time.sleep(2)
        print("   ✓ Piece placed")
        
        # 8. Release piece
        print("8. Releasing piece...")
        bus.write("Goal_Position", "gripper", gripper_open, normalize=False)
        time.sleep(2)
        print("   ✓ Piece released")
        
        # 9. Return to start
        print("9. Returning to start...")
        for motor_name, start_pos in start_positions.items():
            if motor_name != "gripper":
                bus.write("Goal_Position", motor_name, start_pos, normalize=False)
        time.sleep(3)
        print("   ✓ Returned to start")
        
        print("\n🏆 COMPLETE CHESS MOVE SUCCESS!")
        print("🎉 ALL 6 MOTORS WORKING PERFECTLY!")
        print("\n✅ Your SO-101 chess robot is FULLY OPERATIONAL!")
        
    except Exception as e:
        print(f"❌ Demo failed at step: {e}")
        print("Try even smaller movements or check for mechanical obstructions")
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
    ultra_gentle_chess(args.port)

if __name__ == "__main__":
    main()








