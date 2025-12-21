#!/usr/bin/env python
"""
Quick test utility for dual camera setup.
Tests both cameras independently and helps identify camera indices.
"""

import cv2
import sys
import time

def test_camera(index, name="Camera"):
    """Test a single camera at given index."""
    print(f"\n{'='*60}")
    print(f"Testing {name} at index {index}...")
    print(f"{'='*60}")
    
    cap = cv2.VideoCapture(index)
    
    if not cap.isOpened():
        print(f"❌ FAILED: Could not open {name} at index {index}")
        return False
    
    # Get camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    
    print(f"✅ SUCCESS: {name} opened successfully")
    print(f"   Resolution: {width}x{height}")
    print(f"   FPS: {fps}")
    
    # Try to read a few frames
    success_count = 0
    for i in range(10):
        ret, frame = cap.read()
        if ret:
            success_count += 1
        time.sleep(0.1)
    
    print(f"   Frame read success: {success_count}/10")
    
    if success_count > 5:
        # Show a preview window
        ret, frame = cap.read()
        if ret:
            # Resize for display
            display_frame = cv2.resize(frame, (640, 480))
            cv2.putText(display_frame, f"{name} (Index {index})", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (0, 255, 0), 2)
            cv2.imshow(f"{name} - Index {index}", display_frame)
            print(f"   Preview window opened. Press any key to continue...")
            cv2.waitKey(2000)  # Show for 2 seconds
            cv2.destroyAllWindows()
    
    cap.release()
    return success_count > 5

def scan_cameras(max_index=10):
    """Scan for all available cameras."""
    print("\n" + "="*60)
    print("SCANNING FOR AVAILABLE CAMERAS")
    print("="*60)
    
    available_cameras = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            available_cameras.append((i, width, height))
            print(f"✅ Camera {i}: Available ({width}x{height})")
            cap.release()
        else:
            print(f"❌ Camera {i}: Not available")
    
    return available_cameras

def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║         CHESS ROBOT DUAL CAMERA TEST UTILITY               ║
║                                                            ║
║  This tool helps you identify and test your cameras       ║
║  for the dual-camera chess robot setup.                   ║
╚════════════════════════════════════════════════════════════╝
""")
    
    # Scan for available cameras
    available = scan_cameras()
    
    if len(available) < 2:
        print("\n⚠️  WARNING: Found less than 2 cameras!")
        print(f"   Available cameras: {len(available)}")
        print("   You need at least 2 cameras for the dual-camera setup.")
        if len(available) == 0:
            print("\n   Troubleshooting tips:")
            print("   1. Check USB connections")
            print("   2. Check camera permissions (Linux: add user to 'video' group)")
            print("   3. Try different USB ports")
            print("   4. Restart your computer")
            sys.exit(1)
    
    print(f"\n✅ Found {len(available)} camera(s)")
    
    # Determine camera indices based on user input or defaults
    if len(sys.argv) >= 3:
        main_idx = int(sys.argv[1])
        gripper_idx = int(sys.argv[2])
        print(f"\nUsing provided indices:")
        print(f"  Main camera: {main_idx}")
        print(f"  Gripper camera: {gripper_idx}")
    else:
        # Default: first two available cameras
        main_idx = available[0][0]
        gripper_idx = available[1][0] if len(available) > 1 else None
        print(f"\nUsing default indices (first two cameras found):")
        print(f"  Main camera: {main_idx}")
        print(f"  Gripper camera: {gripper_idx}")
        print(f"\nTo test different indices, run:")
        print(f"  python {sys.argv[0]} <main_index> <gripper_index>")
    
    # Test main camera
    time.sleep(1)
    main_success = test_camera(main_idx, "Main Camera (Overview)")
    
    # Test gripper camera
    if gripper_idx is not None:
        time.sleep(1)
        gripper_success = test_camera(gripper_idx, "Gripper Camera (Last Mile)")
    else:
        gripper_success = False
        print("\n❌ No gripper camera to test")
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Main Camera (index {main_idx}):    {'✅ PASS' if main_success else '❌ FAIL'}")
    if gripper_idx is not None:
        print(f"Gripper Camera (index {gripper_idx}): {'✅ PASS' if gripper_success else '❌ FAIL'}")
    
    if main_success and gripper_success:
        print("\n🎉 SUCCESS! Both cameras are working.")
        print("\nNext steps:")
        print("1. Update your UI configuration with these indices:")
        print(f"   - Main camera: index_or_path={main_idx}")
        print(f"   - Gripper camera: index_or_path={gripper_idx}")
        print("\n2. Run your chess robot UI:")
        print("   python chess_robot_ui.py --port /dev/ttyUSB0")
        print("   or")
        print("   python chess_robot_ui_llm.py --port /dev/ttyUSB0")
    elif main_success:
        print("\n⚠️  Main camera works, but gripper camera failed.")
        print("   Check gripper camera connection and try different index.")
    else:
        print("\n❌ Camera tests failed. Please check:")
        print("   1. Camera connections (USB)")
        print("   2. Camera permissions")
        print("   3. Camera indices (try different values)")
        print("   4. System resources")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)




