#!/usr/bin/env python

"""Demo with only the working motors (1,2,4,6)."""

import time
import argparse
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode

def working_motors_demo(port: str):
    """Demo with only detected motors: 1,2,4,6."""
    
    # Only use the motors that were detected
    working_motors = {
        "shoulder_pan": Motor(1, "sts3215", MotorNormMode.DEGREES),     # ID 1 ✓
        "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),    # ID 2 ✓  
        "wrist_flex": Motor(4, "sts3215", MotorNormMode.DEGREES),       # ID 4 ✓
        "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),      # ID 6 ✓
    }
    
    bus = FeetechMotorsBus(port=port, motors=working_motors)
    
    try:
        bus._connect(handshake=False)
        bus._assert_motors_exist()
        print("✓ Connected to working motors:", list(working_motors.keys()))
        
        print("Demo: Simple chess-like movements...")
        
        # 1. Gripper test
        print("1. Testing gripper...")
        bus.write("Goal_Position", "gripper", 10.0)  # Open
        time.sleep(2)
        bus.write("Goal_Position", "gripper", 70.0)  # Close
        time.sleep(2)
        bus.write("Goal_Position", "gripper", 10.0)  # Open
        time.sleep(2)
        
        # 2. Gentle arm movements
        print("2. Testing arm movements...")
        bus.write("Goal_Position", "shoulder_pan", 15.0)  # Small pan
        time.sleep(2)
        bus.write("Goal_Position", "shoulder_pan", -15.0)  # Other direction
        time.sleep(2)
        bus.write("Goal_Position", "shoulder_pan", 0.0)  # Center
        time.sleep(2)
        
        print("3. Testing wrist...")
        bus.write("Goal_Position", "wrist_flex", 20.0)  # Small flex
        time.sleep(2)
        bus.write("Goal_Position", "wrist_flex", 0.0)  # Return
        time.sleep(2)
        
        print("✓ Working motors demo successful!")
        print("\nWorking motors: shoulder_pan, shoulder_lift, wrist_flex, gripper")
        print("Missing motors: elbow_flex (ID 3), wrist_roll (ID 5)")
        print("This is sufficient for basic chess moves!")
        
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
    working_motors_demo(args.port)

if __name__ == "__main__":
    main()








