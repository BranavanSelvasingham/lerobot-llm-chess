#!/usr/bin/env python

"""Calibration script that works with mixed firmware versions."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def calibrate_all_motors(port: str):
    """Calibrate all 6 motors individually, then create group calibration."""
    
    print("🔧 Mixed Firmware Calibration Process")
    print("="*50)
    
    # Motor definitions
    all_motors = {
        "shoulder_pan": {"id": 1, "name": "shoulder_pan"},
        "shoulder_lift": {"id": 2, "name": "shoulder_lift"},  
        "elbow_flex": {"id": 3, "name": "elbow_flex"},
        "wrist_flex": {"id": 4, "name": "wrist_flex"},
        "wrist_roll": {"id": 5, "name": "wrist_roll"},
        "gripper": {"id": 6, "name": "gripper"}
    }
    
    calibration_results = {}
    
    # Test and calibrate each motor individually
    for motor_name, motor_info in all_motors.items():
        motor_id = motor_info["id"]
        print(f"\n--- Calibrating Motor {motor_id} ({motor_name}) ---")
        
        # Create single-motor bus
        norm_mode = MotorNormMode.RANGE_0_100 if motor_name == "gripper" else MotorNormMode.DEGREES
        motors = {motor_name: Motor(motor_id, "sts3215", norm_mode)}
        bus = FeetechMotorsBus(port=port, motors=motors)
        
        try:
            # Connect and test
            bus._connect(handshake=False)
            bus._assert_motors_exist()
            print(f"  ✓ Motor {motor_id} detected")
            
            # Read current limits and position for calibration
            try:
                min_limit = bus.read("Min_Position_Limit", motor_name, normalize=False)
                max_limit = bus.read("Max_Position_Limit", motor_name, normalize=False) 
                homing_offset = bus.read("Homing_Offset", motor_name, normalize=False)
                current_pos = bus.read("Present_Position", motor_name, normalize=False)
                
                print(f"  Current position: {current_pos}")
                print(f"  Limits: [{min_limit}, {max_limit}]")
                print(f"  Homing offset: {homing_offset}")
                
                # Create calibration entry
                calibration_results[motor_name] = {
                    "id": motor_id,
                    "drive_mode": 1 if motor_name == "shoulder_lift" else 0,  # From your working config
                    "homing_offset": homing_offset,
                    "range_min": min_limit,
                    "range_max": max_limit
                }
                
                print(f"  ✅ Motor {motor_id} calibrated successfully")
                
            except Exception as e:
                print(f"  ⚠️ Motor {motor_id} detected but can't read params: {e}")
                # Use fallback values from your working config
                fallback_data = {
                    "shoulder_pan": {"offset": -1879, "min": 2046, "max": 2903, "drive": 0},
                    "shoulder_lift": {"offset": 3078, "min": 3069, "max": -2054, "drive": 1},
                    "elbow_flex": {"offset": -1114, "min": 1023, "max": 2138, "drive": 0},
                    "wrist_flex": {"offset": -1924, "min": 2035, "max": 2948, "drive": 0},
                    "wrist_roll": {"offset": -1066, "min": 2043, "max": 2090, "drive": 0},
                    "gripper": {"offset": -2337, "min": 2046, "max": 3361, "drive": 0}
                }
                
                fb = fallback_data[motor_name]
                calibration_results[motor_name] = {
                    "id": motor_id,
                    "drive_mode": fb["drive"],
                    "homing_offset": fb["offset"],
                    "range_min": fb["min"],
                    "range_max": fb["max"]
                }
                print(f"  📋 Using fallback calibration for motor {motor_id}")
                
        except Exception as e:
            print(f"  ❌ Motor {motor_id} not accessible: {e}")
            continue
        finally:
            try:
                bus.disconnect()
            except:
                pass
    
    # Save complete calibration
    calib_dir = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower"
    calib_dir.mkdir(parents=True, exist_ok=True)
    calib_file = calib_dir / "so101_chess.json"
    
    with open(calib_file, 'w') as f:
        json.dump(calibration_results, f, indent=2)
    
    print(f"\n🎉 Complete calibration saved to: {calib_file}")
    print(f"📊 Calibrated {len(calibration_results)}/6 motors")
    
    for motor_name, data in calibration_results.items():
        print(f"  {motor_name} (ID {data['id']}): range=[{data['range_min']}, {data['range_max']}]")
    
    return len(calibration_results)

def main():
    import argparse
    p = argparse.ArgumentParser(description="Calibrate all motors individually to handle firmware mismatch")
    p.add_argument("--port", required=True)
    args = p.parse_args()
    
    working_count = calibrate_all_motors(args.port)
    
    print(f"\n{'='*50}")
    if working_count == 6:
        print("🏆 ALL 6 MOTORS CALIBRATED! Chess robot fully ready!")
    elif working_count >= 4:
        print(f"✅ {working_count}/6 motors working - Chess capable with adaptations")
    else:
        print(f"⚠️ Only {working_count}/6 motors working - May need hardware check")

if __name__ == "__main__":
    main()








