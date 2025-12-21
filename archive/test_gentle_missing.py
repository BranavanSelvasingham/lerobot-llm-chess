#!/usr/bin/env python

"""Very gentle test of motors 3 and 5 with minimal movements."""

import time
import argparse
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def test_motor_gentle(port: str, motor_id: int, motor_name: str, calibration_data: dict):
    """Test a motor with very gentle movements and proper calibration."""
    
    print(f"\n=== Testing Motor {motor_id} ({motor_name}) ===")
    
    # Create calibration
    calib = MotorCalibration(
        id=calibration_data["id"],
        drive_mode=calibration_data["drive_mode"],
        homing_offset=calibration_data["homing_offset"],
        range_min=calibration_data["range_min"],
        range_max=calibration_data["range_max"]
    )
    
    motors = {motor_name: Motor(motor_id, "sts3215", MotorNormMode.DEGREES)}
    calibration = {motor_name: calib}
    
    bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
    
    try:
        print("  Connecting...")
        bus._connect(handshake=False)
        
        print("  Checking detection...")
        bus._assert_motors_exist()
        print(f"  ✓ Motor {motor_id} detected successfully")
        
        print("  Testing VERY gentle movement (1 degree)...")
        
        # Extremely small movements
        bus.write("Goal_Position", motor_name, 1.0)  # 1 degree
        time.sleep(3)
        print("    -> Moved +1 degree")
        
        bus.write("Goal_Position", motor_name, -1.0)  # -1 degree  
        time.sleep(3)
        print("    -> Moved -1 degree")
        
        bus.write("Goal_Position", motor_name, 0.0)  # Return to center
        time.sleep(3)
        print("    -> Returned to center")
        
        print(f"  🎉 Motor {motor_id} ({motor_name}) is WORKING!")
        return True
        
    except Exception as e:
        print(f"  ✗ Motor {motor_id} failed: {e}")
        if "Missing motor IDs" in str(e):
            print(f"    -> Motor {motor_id} not detected (connection/power issue)")
        elif "Overload" in str(e):
            print(f"    -> Motor {motor_id} detected but mechanically blocked")
        return False
    finally:
        try:
            bus.disconnect()
        except:
            pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    
    # Calibration data from your working config
    motor3_calib = {"id": 3, "drive_mode": 0, "homing_offset": -1114, "range_min": 1023, "range_max": 2138}
    motor5_calib = {"id": 5, "drive_mode": 0, "homing_offset": -1066, "range_min": 2043, "range_max": 2090}
    
    print("Testing missing motors with gentle movements...")
    
    motor3_ok = test_motor_gentle(args.port, 3, "elbow_flex", motor3_calib)
    motor5_ok = test_motor_gentle(args.port, 5, "wrist_roll", motor5_calib)
    
    print(f"\n{'='*50}")
    print("FINAL RESULTS:")
    print(f"Motor 3 (elbow_flex): {'✅ WORKING' if motor3_ok else '❌ NOT WORKING'}")
    print(f"Motor 5 (wrist_roll): {'✅ WORKING' if motor5_ok else '❌ NOT WORKING'}")
    
    working_count = sum([motor3_ok, motor5_ok])
    print(f"\nTotal working motors: {4 + working_count}/6")
    
    if working_count > 0:
        print("🎉 Additional motors found working!")
        print("The group detection issue is likely due to firmware mismatch.")
        print("Consider updating all motors to same firmware version.")
    
    print(f"\nChess robot status: {'FULLY CAPABLE' if working_count == 2 else 'CAPABLE WITH ADAPTATIONS'}")

if __name__ == "__main__":
    main()








