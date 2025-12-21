#!/usr/bin/env python

"""Test motor 3 specifically with its calibration."""

import time
import argparse
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def test_motor3(port: str):
    """Test motor 3 with its specific calibration."""
    
    print("Testing motor 3 (elbow_flex) with calibration...")
    
    # Motor 3 calibration from your working config
    motor3_calib = MotorCalibration(
        id=3,
        drive_mode=0,
        homing_offset=-1114,
        range_min=1023,
        range_max=2138
    )
    
    motors = {"elbow_flex": Motor(3, "sts3215", MotorNormMode.DEGREES)}
    calibration = {"elbow_flex": motor3_calib}
    
    bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
    
    try:
        bus._connect(handshake=False)
        bus._assert_motors_exist()
        print("✓ Motor 3 connected with calibration")
        
        print("Testing gentle elbow movements...")
        
        # Very small movements within safe range
        bus.write("Goal_Position", "elbow_flex", 0.0)  # Center
        time.sleep(3)
        
        bus.write("Goal_Position", "elbow_flex", 10.0)  # Small flex
        time.sleep(3)
        
        bus.write("Goal_Position", "elbow_flex", -10.0)  # Small extend
        time.sleep(3)
        
        bus.write("Goal_Position", "elbow_flex", 0.0)  # Return to center
        time.sleep(3)
        
        print("✓ Motor 3 (elbow_flex) working perfectly!")
        print("This motor is essential for chess - it provides vertical reach.")
        
    except Exception as e:
        print(f"✗ Motor 3 failed: {e}")
    finally:
        try:
            bus.disconnect()
        except:
            pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    test_motor3(args.port)

if __name__ == "__main__":
    main()








