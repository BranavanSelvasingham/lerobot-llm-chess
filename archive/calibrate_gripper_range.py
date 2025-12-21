#!/usr/bin/env python

"""Find safe min/max range for the gripper to avoid overload errors."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def find_gripper_range(port: str):
    """Interactively find safe gripper range."""
    
    print("🔧 Gripper Range Calibration")
    print("="*40)
    
    # Load calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    # Setup gripper
    gripper_calib = MotorCalibration(
        id=6,
        drive_mode=calib_data["gripper"]["drive_mode"],
        homing_offset=calib_data["gripper"]["homing_offset"],
        range_min=calib_data["gripper"]["range_min"],
        range_max=calib_data["gripper"]["range_max"]
    )
    
    motors = {"gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100)}
    calibration = {"gripper": gripper_calib}
    bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
    
    try:
        bus._connect(handshake=False)
        bus._assert_motors_exist()
        
        current_pos = bus.read("Present_Position", "gripper", normalize=False)
        print(f"Current gripper position: {current_pos}")
        print(f"Current range: [{calib_data['gripper']['range_min']}, {calib_data['gripper']['range_max']}]")
        
        print("\n🔍 Testing gripper range...")
        
        # Test sequence from current position
        test_positions = [10, 20, 30, 40, 50, 60, 70, 80, 90]
        safe_positions = []
        
        for pos in test_positions:
            try:
                print(f"  Testing position {pos}...")
                bus.write("Goal_Position", "gripper", float(pos))
                time.sleep(1.5)
                
                # Read actual position to verify
                actual = bus.read("Present_Position", "gripper", normalize=False)
                print(f"    ✓ Success - actual position: {actual}")
                safe_positions.append(pos)
                
            except Exception as e:
                print(f"    ❌ Failed at {pos}: {e}")
                break
        
        if safe_positions:
            safe_min = min(safe_positions)
            safe_max = max(safe_positions)
            
            print(f"\n📊 Safe gripper range found:")
            print(f"  Min (open): {safe_min}")
            print(f"  Max (closed): {safe_max}")
            
            # Test the range
            print(f"\n🧪 Testing safe range...")
            print(f"  Opening to {safe_min}...")
            bus.write("Goal_Position", "gripper", float(safe_min))
            time.sleep(2)
            
            print(f"  Closing to {safe_max}...")
            bus.write("Goal_Position", "gripper", float(safe_max))
            time.sleep(2)
            
            print(f"  Opening to {safe_min}...")
            bus.write("Goal_Position", "gripper", float(safe_min))
            time.sleep(2)
            
            print("✅ Safe range verified!")
            
            # Update calibration with safe values
            calib_data["gripper"]["safe_open"] = safe_min
            calib_data["gripper"]["safe_closed"] = safe_max
            
            with open(calib_file, 'w') as f:
                json.dump(calib_data, f, indent=2)
            
            print(f"💾 Updated calibration with safe gripper range:")
            print(f"   Open (for chess): {safe_min}")
            print(f"   Closed (for chess): {safe_max}")
            
        else:
            print("❌ No safe positions found - gripper may need manual adjustment")
            
    except Exception as e:
        print(f"❌ Gripper test failed: {e}")
    finally:
        try:
            bus.disconnect()
        except:
            pass

def main():
    import argparse
    p = argparse.ArgumentParser(description="Find safe gripper range")
    p.add_argument("--port", required=True)
    args = p.parse_args()
    find_gripper_range(args.port)

if __name__ == "__main__":
    main()








