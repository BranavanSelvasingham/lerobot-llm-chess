#!/usr/bin/env python

"""Quick setup verification script for SO-101 chess robot."""

import sys
from pathlib import Path

def test_imports():
    """Test all chess-related imports."""
    print("Testing imports...")
    try:
        from lerobot.robots.so101_follower.so101_follower import SO101Follower
        from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
        from lerobot.perception.chess import BoardModel, OccupancyDetector
        from lerobot.processor.pipelines.chess_pick_place import build_chess_pick_place_pipeline
        import chess
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_robot_connection():
    """Test SO-101 connection."""
    print("\nTesting robot connection...")
    try:
        from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
        from lerobot.robots.so101_follower.so101_follower import SO101Follower
        
        cfg = SO101FollowerConfig(port="/dev/tty.usbmodem5A460825871", id="so101_chess", cameras={}, use_degrees=True)
        robot = SO101Follower(cfg)
        
        # Test basic motor detection
        robot.bus._connect(handshake=False)
        robot.bus._assert_motors_exist()
        print("✓ Motors detected successfully")
        print(f"  Motor IDs: {list(robot.bus.motors.keys())}")
        print(f"  Calibration dir: {robot.calibration_dir}")
        robot.bus.disconnect()
        return True
    except Exception as e:
        print(f"✗ Robot connection failed: {e}")
        if "firmware" in str(e).lower():
            print("  → Update motor firmware using Feetech software")
        return False

def test_camera():
    """Test camera access."""
    print("\nTesting camera...")
    try:
        from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
        from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
        
        cfg = OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30)  # index=0 for USB camera
        cam = OpenCVCamera(cfg)
        cam.connect()
        frame = cam.read()
        cam.disconnect()
        print(f"✓ Camera successful (shape: {frame.shape})")
        return True
    except Exception as e:
        print(f"✗ Camera failed: {e}")
        if "denied" in str(e) or "authorized" in str(e):
            print("  → Grant camera permissions in System Preferences > Security & Privacy > Camera")
        return False

def main():
    print("SO-101 Chess Robot Setup Verification")
    print("=" * 40)
    
    results = []
    results.append(test_imports())
    results.append(test_robot_connection())
    results.append(test_camera())
    
    print("\n" + "=" * 40)
    if all(results):
        print("🎉 Setup complete! Ready to start chess robot.")
        print("\nNext steps:")
        print("1. Save home pose: python -m lerobot.scripts.chess_home --port /dev/tty.usbmodem5A460825871 --save")
        print("2. Calibrate board: python -m lerobot.scripts.lerobot_calibrate_chessboard --port /dev/tty.usbmodem5A460825871")
        print("3. Execute move: python -m lerobot.scripts.chess_move --port /dev/tty.usbmodem5A460825871 --from e2 --to e4 --skip-calibration")
        print("\nNote: Use --skip-calibration flag if you encounter calibration prompts.")
    else:
        print("❌ Setup incomplete. Fix issues above before proceeding.")
        if not results[1]:  # robot failed
            print("\nFor firmware issues:")
            print("- Download Feetech SCServo software")
            print("- Update motor 3 firmware from 3.10 to 3.9 (or update others to 3.10)")

if __name__ == "__main__":
    main()
