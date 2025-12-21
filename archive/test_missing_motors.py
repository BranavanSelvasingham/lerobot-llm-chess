#!/usr/bin/env python

"""Test motors 3 and 5 (elbow_flex, wrist_roll) individually."""

import time
import argparse
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode

def test_individual_motor(port: str, motor_id: int, motor_name: str):
    """Test a single motor individually."""
    
    print(f"\nTesting motor {motor_id} ({motor_name})...")
    
    motors = {motor_name: Motor(motor_id, "sts3215", MotorNormMode.DEGREES)}
    bus = FeetechMotorsBus(port=port, motors=motors)
    
    try:
        bus._connect(handshake=False)
        
        # Check if motor exists
        try:
            bus._assert_motors_exist()
            print(f"✓ Motor {motor_id} detected")
        except Exception as e:
            print(f"✗ Motor {motor_id} not detected: {e}")
            return False
        
        # Try gentle movement
        print(f"  Testing gentle movement...")
        bus.write("Goal_Position", motor_name, 5.0)  # Very small movement
        time.sleep(2)
        
        bus.write("Goal_Position", motor_name, -5.0)  # Return
        time.sleep(2)
        
        bus.write("Goal_Position", motor_name, 0.0)  # Center
        time.sleep(2)
        
        print(f"✓ Motor {motor_id} movement successful")
        return True
        
    except Exception as e:
        print(f"✗ Motor {motor_id} failed: {e}")
        return False
    finally:
        try:
            bus.disconnect()
        except:
            pass

def test_missing_motors(port: str):
    """Test the two missing motors individually."""
    
    print("Testing missing motors individually...")
    
    # Test motor 3 (elbow_flex)
    motor3_ok = test_individual_motor(port, 3, "elbow_flex")
    
    # Test motor 5 (wrist_roll) 
    motor5_ok = test_individual_motor(port, 5, "wrist_roll")
    
    print(f"\n=== Results ===")
    print(f"Motor 3 (elbow_flex): {'✓ Working' if motor3_ok else '✗ Not working'}")
    print(f"Motor 5 (wrist_roll): {'✓ Working' if motor5_ok else '✗ Not working'}")
    
    if motor3_ok or motor5_ok:
        print("\nSome missing motors are actually working!")
        print("The issue might be with detecting them in a group due to firmware mismatch.")
    else:
        print("\nMotors 3 and 5 are not responding.")
        print("Check connections, power, or ID conflicts.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    test_missing_motors(args.port)

if __name__ == "__main__":
    main()








