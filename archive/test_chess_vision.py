#!/usr/bin/env python

"""Test camera and chess board/piece detection."""

import time
import argparse
import cv2
import numpy as np
from pathlib import Path

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.perception.chess.piece_detector import OccupancyDetector
from lerobot.perception.chess.state_builder import build_state_from_occupancy

def test_chess_vision(port: str, camera_index: int = 0):
    """Test camera and chess detection."""
    
    print("📸 Chess Vision Test")
    print("="*30)
    
    # Create robot config with camera
    camera_config = {"arm_camera": OpenCVCameraConfig(index_or_path=camera_index, width=640, height=480, fps=30)}
    robot_cfg = SO101FollowerConfig(
        port=port, 
        id="so101_chess", 
        cameras=camera_config, 
        use_degrees=True
    )
    
    try:
        robot = SO101Follower(robot_cfg)
        
        # Connect robot (bypass firmware check)
        robot.bus._connect(handshake=False)
        robot.bus._assert_motors_exist()
        print("✓ Robot connected")
        
        # Connect camera
        camera = robot.cameras["arm_camera"]
        camera.connect()
        print("✓ Arm camera connected")
        
        print(f"\n📷 Testing camera capture...")
        frame = camera.read()
        print(f"✓ Frame captured: {frame.shape}")
        
        # Save test image
        test_dir = Path("chess_test_images")
        test_dir.mkdir(exist_ok=True)
        
        test_image_path = test_dir / "current_view.jpg"
        cv2.imwrite(str(test_image_path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        print(f"💾 Saved current view to: {test_image_path}")
        
        print(f"\n🏁 Manual Chess Board Setup Instructions:")
        print("="*50)
        print("1. Position a chessboard in the camera view")
        print("2. Place ONE chess piece on the board")
        print("3. Press ENTER when ready...")
        input()
        
        # Capture board with piece
        print("\n📸 Capturing board with piece...")
        board_frame = camera.read()
        board_image_path = test_dir / "board_with_piece.jpg"
        cv2.imwrite(str(board_image_path), cv2.cvtColor(board_frame, cv2.COLOR_RGB2BGR))
        print(f"💾 Saved board image to: {board_image_path}")
        
        print("\n4. Remove the chess piece from the board")
        print("5. Press ENTER when piece is removed...")
        input()
        
        # Capture empty board
        print("\n📸 Capturing empty board...")
        empty_frame = camera.read()
        empty_image_path = test_dir / "empty_board.jpg"
        cv2.imwrite(str(empty_image_path), cv2.cvtColor(empty_frame, cv2.COLOR_RGB2BGR))
        print(f"💾 Saved empty board to: {empty_image_path}")
        
        print("\n🔍 Testing piece detection...")
        
        # Create detector (we'll use rough estimates for now)
        # You'll need to adjust these based on your board size in the image
        detector = OccupancyDetector(
            square_size_px=60,  # Adjust based on your board size
            grid_offset_xy=(100, 100),  # Adjust based on board position
            threshold=25.0
        )
        
        # Set empty reference
        detector.set_empty_reference(cv2.cvtColor(empty_frame, cv2.COLOR_RGB2BGR))
        print("✓ Empty board reference set")
        
        # Detect pieces
        occupancy = detector.detect(cv2.cvtColor(board_frame, cv2.COLOR_RGB2BGR))
        print(f"✓ Piece detection completed")
        
        # Build chess state
        state = build_state_from_occupancy(occupancy)
        print(f"✓ Chess state built")
        
        print(f"\n📊 Detection Results:")
        print(f"Occupancy grid (8x8):")
        for row in range(8):
            row_str = ""
            for col in range(8):
                row_str += "♟️ " if occupancy[7-row, col] else "⬜ "  # Flip for display
            print(f"  {8-row}: {row_str}")
        print("     a  b  c  d  e  f  g  h")
        
        piece_count = np.sum(occupancy)
        print(f"\nDetected pieces: {piece_count}")
        print(f"FEN: {state.fen}")
        
        if piece_count == 1:
            print("🎉 PERFECT! Detected exactly 1 piece as expected!")
        elif piece_count == 0:
            print("⚠️ No pieces detected - check detection parameters")
        else:
            print(f"⚠️ Detected {piece_count} pieces - may need detection tuning")
        
        # Create overlay image
        overlay = cv2.cvtColor(board_frame, cv2.COLOR_RGB2BGR).copy()
        
        # Draw 8x8 grid overlay (rough estimate)
        h, w = overlay.shape[:2]
        for i in range(9):  # 9 lines for 8 squares
            x = 100 + i * 60  # Adjust based on your board
            y = 100 + i * 60
            if x < w:
                cv2.line(overlay, (x, 100), (x, 100 + 8*60), (0, 255, 0), 1)
            if y < h:
                cv2.line(overlay, (100, y), (100 + 8*60, y), (0, 255, 0), 1)
        
        # Mark detected pieces
        for row in range(8):
            for col in range(8):
                if occupancy[row, col]:
                    x = 100 + col * 60 + 30  # Center of square
                    y = 100 + row * 60 + 30
                    cv2.circle(overlay, (x, y), 20, (0, 0, 255), 3)
        
        overlay_path = test_dir / "detection_overlay.jpg"
        cv2.imwrite(str(overlay_path), overlay)
        print(f"💾 Saved detection overlay to: {overlay_path}")
        
        print(f"\n📁 All test images saved to: {test_dir}/")
        print("   - current_view.jpg (initial camera view)")
        print("   - board_with_piece.jpg (board with your piece)")
        print("   - empty_board.jpg (reference empty board)")
        print("   - detection_overlay.jpg (detection results)")
        
        if piece_count == 1:
            print("\n🎉 CHESS VISION TEST SUCCESSFUL!")
            print("Your camera and detection pipeline are working!")
            print("\nNext: Calibrate precise board position for accurate moves")
        
    except Exception as e:
        print(f"❌ Vision test failed: {e}")
    finally:
        try:
            if 'camera' in locals():
                camera.disconnect()
            if 'robot' in locals():
                robot.bus.disconnect()
        except:
            pass

def main():
    p = argparse.ArgumentParser(description="Test chess vision with arm-mounted camera")
    p.add_argument("--port", required=True)
    p.add_argument("--camera", type=int, default=1, help="Camera index (default: 1)")
    args = p.parse_args()
    test_chess_vision(args.port, args.camera)

if __name__ == "__main__":
    main()



