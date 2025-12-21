#!/usr/bin/env python

"""Full 6-motor chess demo with proper calibration."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def full_chess_demo(port: str):
    """Demo complete chess move with all 6 motors."""
    
    print("🏆 Full 6-Motor Chess Demo")
    print("="*40)
    
    # Load complete calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    # All 6 motors
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
    
    # Get safe gripper values
    gripper_open = calib_data["gripper"]["chess_open_raw"]
    gripper_closed = calib_data["gripper"]["chess_closed_raw"]
    
    bus = FeetechMotorsBus(port=port, motors=all_motors, calibration=calibration)
    
    try:
        bus._connect(handshake=False)
        print("🤖 Connected to all motors")
        
        # Read all current positions
        print("\nCurrent positions:")
        current_positions = {}
        for motor_name in all_motors.keys():
            try:
                pos = bus.read("Present_Position", motor_name, normalize=False)
                current_positions[motor_name] = pos
                print(f"  {motor_name}: {pos}")
            except Exception as e:
                print(f"  {motor_name}: ERROR - {e}")
        
        print(f"\n🎯 Chess Move Demo: e2 → e4")
        print("="*30)
        
        # 1. Home position
        print("1. Moving to chess ready position...")
        home_positions = {
            "shoulder_pan": 0,      # Centered
            "shoulder_lift": 10,    # Slight lift
            "elbow_flex": 20,       # Elbow up for reach
            "wrist_flex": 0,        # Straight wrist
            "wrist_roll": 0,        # Centered rotation
        }
        
        for motor, pos in home_positions.items():
            bus.write("Goal_Position", motor, float(pos))
        time.sleep(4)
        print("   ✓ Ready position")
        
        # 2. Open gripper
        print("2. Opening gripper...")
        bus.write("Goal_Position", "gripper", gripper_open, normalize=False)
        time.sleep(2)
        print("   ✓ Gripper open")
        
        # 3. Move to source square (e2)
        print("3. Moving to source square e2...")
        pick_positions = {
            "shoulder_pan": -15,    # Left side
            "elbow_flex": 35,       # Reach down
            "wrist_flex": 10,       # Angle for approach
        }
        
        for motor, pos in pick_positions.items():
            bus.write("Goal_Position", motor, float(pos))
        time.sleep(3)
        print("   ✓ At source square")
        
        # 4. Close gripper (grasp piece)
        print("4. Grasping piece...")
        bus.write("Goal_Position", "gripper", gripper_closed, normalize=False)
        time.sleep(2)
        print("   ✓ Piece grasped")
        
        # 5. Lift piece
        print("5. Lifting piece...")
        bus.write("Goal_Position", "elbow_flex", 15.0)  # Lift up
        time.sleep(2)
        print("   ✓ Piece lifted")
        
        # 6. Move to destination square (e4)
        print("6. Moving to destination square e4...")
        place_positions = {
            "shoulder_pan": -5,     # Slightly right
            "wrist_roll": 5,        # Small rotation for placement
        }
        
        for motor, pos in place_positions.items():
            bus.write("Goal_Position", motor, float(pos))
        time.sleep(3)
        print("   ✓ At destination square")
        
        # 7. Lower piece
        print("7. Placing piece...")
        bus.write("Goal_Position", "elbow_flex", 35.0)  # Lower down
        time.sleep(2)
        print("   ✓ Piece lowered")
        
        # 8. Release piece
        print("8. Releasing piece...")
        bus.write("Goal_Position", "gripper", gripper_open, normalize=False)
        time.sleep(2)
        print("   ✓ Piece released")
        
        # 9. Return to home
        print("9. Returning to ready position...")
        for motor, pos in home_positions.items():
            bus.write("Goal_Position", motor, float(pos))
        time.sleep(4)
        print("   ✓ Ready for next move")
        
        print("\n🏆 FULL CHESS MOVE COMPLETED!")
        print("🎉 Your SO-101 is 100% ready for chess!")
        print("\nNext steps:")
        print("- Add camera to robot config")
        print("- Calibrate chessboard position")
        print("- Start playing chess!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
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
    full_chess_demo(args.port)

if __name__ == "__main__":
    main()
