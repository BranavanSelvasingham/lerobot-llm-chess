#!/usr/bin/env python

"""Careful calibration for motor 5 (wrist_roll) to get it working reliably."""

import time
import json
from pathlib import Path
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode, MotorCalibration

def calibrate_wrist_roll(port: str):
    """Carefully calibrate wrist_roll motor 5."""
    
    print("🔧 Wrist Roll (Motor 5) Calibration")
    print("="*40)
    
    # Load existing calibration
    calib_file = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower/so101_chess.json"
    with open(calib_file) as f:
        calib_data = json.load(f)
    
    # Create single motor setup for wrist_roll
    motors = {"wrist_roll": Motor(5, "sts3215", MotorNormMode.DEGREES)}
    
    # Use existing calibration data for motor 5
    wrist_calib = MotorCalibration(
        id=5,
        drive_mode=calib_data["wrist_roll"]["drive_mode"],
        homing_offset=calib_data["wrist_roll"]["homing_offset"],
        range_min=calib_data["wrist_roll"]["range_min"],
        range_max=calib_data["wrist_roll"]["range_max"]
    )
    
    calibration = {"wrist_roll": wrist_calib}
    bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
    
    try:
        print("🔌 Connecting to wrist_roll motor...")
        bus._connect(handshake=False)
        bus._assert_motors_exist()
        print("✓ Motor 5 detected")
        
        # Read current position
        current_pos = bus.read("Present_Position", "wrist_roll", normalize=False)
        print(f"Current position: {current_pos}")
        print(f"Calibration range: [{calib_data['wrist_roll']['range_min']}, {calib_data['wrist_roll']['range_max']}]")
        
        print(f"\n🧪 Testing wrist roll range around current position...")
        
        # Test very small movements first
        safe_positions = [current_pos]  # Start with current as safe
        
        print("Testing tiny positive movements...")
        for delta in [10, 20, 30, 50, 80, 100, 150, 200]:
            test_pos = current_pos + delta
            try:
                print(f"  Testing +{delta} -> {test_pos}...")
                bus.write("Goal_Position", "wrist_roll", test_pos, normalize=False)
                time.sleep(2)
                actual = bus.read("Present_Position", "wrist_roll", normalize=False)
                print(f"    ✓ Success: moved to {actual}")
                safe_positions.append(test_pos)
            except Exception as e:
                print(f"    ❌ Failed at +{delta}: {e}")
                break
        
        # Return to center
        bus.write("Goal_Position", "wrist_roll", current_pos, normalize=False)
        time.sleep(2)
        
        print("Testing tiny negative movements...")
        for delta in [10, 20, 30, 50, 80, 100, 150, 200]:
            test_pos = current_pos - delta
            if test_pos < 0:
                continue
            try:
                print(f"  Testing -{delta} -> {test_pos}...")
                bus.write("Goal_Position", "wrist_roll", test_pos, normalize=False)
                time.sleep(2)
                actual = bus.read("Present_Position", "wrist_roll", normalize=False)
                print(f"    ✓ Success: moved to {actual}")
                safe_positions.append(test_pos)
            except Exception as e:
                print(f"    ❌ Failed at -{delta}: {e}")
                break
        
        if len(safe_positions) > 1:
            safe_min = min(safe_positions)
            safe_max = max(safe_positions)
            safe_center = current_pos
            
            print(f"\n📊 Safe wrist_roll range found:")
            print(f"  Min: {safe_min}")
            print(f"  Center: {safe_center}")
            print(f"  Max: {safe_max}")
            print(f"  Range: {safe_max - safe_min} units")
            
            # Test the full range
            print(f"\n🎮 Testing full safe range...")
            
            # Go to center
            bus.write("Goal_Position", "wrist_roll", safe_center, normalize=False)
            time.sleep(2)
            print("  ✓ At center")
            
            # Test min
            bus.write("Goal_Position", "wrist_roll", safe_min, normalize=False)
            time.sleep(2)
            print(f"  ✓ At min ({safe_min})")
            
            # Test max
            bus.write("Goal_Position", "wrist_roll", safe_max, normalize=False)
            time.sleep(2)
            print(f"  ✓ At max ({safe_max})")
            
            # Return to center
            bus.write("Goal_Position", "wrist_roll", safe_center, normalize=False)
            time.sleep(2)
            print("  ✓ Returned to center")
            
            # Save safe range
            calib_data["wrist_roll"]["safe_min"] = int(safe_min)
            calib_data["wrist_roll"]["safe_max"] = int(safe_max)
            calib_data["wrist_roll"]["safe_center"] = int(safe_center)
            
            with open(calib_file, 'w') as f:
                json.dump(calib_data, f, indent=2)
            
            print(f"\n💾 Saved wrist_roll safe range to calibration")
            print(f"🎉 Wrist roll is now ready for chess!")
            print(f"\nChess wrist positions:")
            print(f"  Straight: {safe_center}")
            print(f"  Left turn: {safe_min}")  
            print(f"  Right turn: {safe_max}")
            
        else:
            print(f"❌ Only current position {current_pos} is safe")
            print("Check for mechanical obstructions or loose connections")
            
    except Exception as e:
        print(f"❌ Calibration failed: {e}")
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
    calibrate_wrist_roll(args.port)

if __name__ == "__main__":
    main()








