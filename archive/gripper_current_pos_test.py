#!/usr/bin/env python

"""Test gripper range relative to current position."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def test_gripper_relative(port: str):
    """Test gripper movements relative to current position."""
    
    print("🔧 Gripper Relative Position Test")
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
        
        # Read current position in raw units (not normalized)
        current_raw = bus.read("Present_Position", "gripper", normalize=False)
        print(f"Current raw position: {current_raw}")
        
        # Test small relative movements in raw units
        print("\n🧪 Testing small relative movements...")
        
        safe_positions = []
        
        # Test closing (higher values)
        print("Testing closing direction...")
        for offset in [50, 100, 150, 200, 250, 300]:
            test_pos = current_raw + offset
            try:
                print(f"  Testing raw position {test_pos} (+{offset})...")
                bus.write("Goal_Position", "gripper", test_pos, normalize=False)
                time.sleep(2)
                actual = bus.read("Present_Position", "gripper", normalize=False)
                print(f"    ✓ Success - moved to {actual}")
                safe_positions.append(test_pos)
            except Exception as e:
                print(f"    ❌ Failed: {e}")
                break
        
        # Return to start
        bus.write("Goal_Position", "gripper", current_raw, normalize=False)
        time.sleep(2)
        
        # Test opening (lower values)  
        print("Testing opening direction...")
        for offset in [-50, -100, -150, -200, -250, -300]:
            test_pos = current_raw + offset
            if test_pos < 0:
                continue
            try:
                print(f"  Testing raw position {test_pos} ({offset})...")
                bus.write("Goal_Position", "gripper", test_pos, normalize=False)
                time.sleep(2)
                actual = bus.read("Present_Position", "gripper", normalize=False)
                print(f"    ✓ Success - moved to {actual}")
                safe_positions.append(test_pos)
            except Exception as e:
                print(f"    ❌ Failed: {e}")
                break
        
        if safe_positions:
            safe_min = min(safe_positions)
            safe_max = max(safe_positions)
            
            print(f"\n📊 Safe gripper range (raw units):")
            print(f"  Open: {safe_min}")
            print(f"  Closed: {safe_max}")
            print(f"  Current: {current_raw}")
            
            # Convert to 0-100 scale for chess use
            range_span = safe_max - safe_min
            open_pct = 0
            closed_pct = 100
            
            # Map to raw values
            open_raw = safe_min
            closed_raw = safe_max
            
            print(f"\n🎯 Chess gripper values:")
            print(f"  Open (0%): {open_raw} raw")
            print(f"  Closed (100%): {closed_raw} raw")
            
            # Save to calibration
            calib_data["gripper"]["chess_open_raw"] = int(open_raw)
            calib_data["gripper"]["chess_closed_raw"] = int(closed_raw)
            
            with open(calib_file, 'w') as f:
                json.dump(calib_data, f, indent=2)
            
            print(f"💾 Saved chess gripper values to calibration")
            
            # Final test
            print("\n🎮 Final chess gripper test...")
            bus.write("Goal_Position", "gripper", open_raw, normalize=False)
            time.sleep(2)
            print("  ✓ Opened for chess")
            
            bus.write("Goal_Position", "gripper", closed_raw, normalize=False)
            time.sleep(2)
            print("  ✓ Closed for chess")
            
            bus.write("Goal_Position", "gripper", open_raw, normalize=False)
            time.sleep(2)
            print("  ✓ Chess gripper calibration complete!")
            
        else:
            print("❌ No safe range found")
            
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
    test_gripper_relative(args.port)

if __name__ == "__main__":
    main()








