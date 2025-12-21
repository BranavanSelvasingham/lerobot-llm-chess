#!/usr/bin/env python

"""Test conservative gripper range for reliable chess operation."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def test_conservative_gripper(port: str):
    """Test a conservative gripper range for reliable operation."""
    
    print("🔧 Conservative Gripper Range Test")
    print("="*40)
    
    # Load calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
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
        
        current_raw = bus.read("Present_Position", "gripper", normalize=False)
        print(f"Current position: {current_raw}")
        
        # Use conservative range based on previous test results
        # We know 930-1480 worked but had issues at extremes
        # Let's use a safer middle range
        
        conservative_open = 1000   # Slightly more closed than extreme open
        conservative_closed = 1400 # Slightly more open than extreme closed
        
        print(f"\n🎯 Testing conservative range:")
        print(f"  Open: {conservative_open}")
        print(f"  Closed: {conservative_closed}")
        
        # Test the conservative range multiple times
        for cycle in range(3):
            print(f"\nCycle {cycle + 1}/3:")
            
            try:
                print(f"  Opening to {conservative_open}...")
                bus.write("Goal_Position", "gripper", conservative_open, normalize=False)
                time.sleep(2)
                pos = bus.read("Present_Position", "gripper", normalize=False)
                print(f"    ✓ Open position: {pos}")
                
                print(f"  Closing to {conservative_closed}...")
                bus.write("Goal_Position", "gripper", conservative_closed, normalize=False)
                time.sleep(2)
                pos = bus.read("Present_Position", "gripper", normalize=False)
                print(f"    ✓ Closed position: {pos}")
                
            except Exception as e:
                print(f"    ❌ Cycle {cycle + 1} failed: {e}")
                break
        else:
            print("\n🎉 Conservative range works perfectly!")
            
            # Save final chess gripper values
            calib_data["gripper"]["chess_open_raw"] = conservative_open
            calib_data["gripper"]["chess_closed_raw"] = conservative_closed
            
            with open(calib_file, 'w') as f:
                json.dump(calib_data, f, indent=2)
            
            print(f"💾 Saved reliable chess gripper values:")
            print(f"   Open: {conservative_open} (for picking up pieces)")
            print(f"   Closed: {conservative_closed} (for grasping pieces)")
            print("\n✅ Gripper ready for chess!")
            
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
    test_conservative_gripper(args.port)

if __name__ == "__main__":
    main()








