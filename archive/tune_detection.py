#!/usr/bin/env python

"""Interactive tool to tune chess piece detection parameters."""

import cv2
import numpy as np
from pathlib import Path

def tune_detection():
    """Interactive detection parameter tuning."""
    
    print("🔧 Chess Detection Parameter Tuning")
    print("="*40)
    
    test_dir = Path("chess_test_images")
    if not test_dir.exists():
        print("❌ No test images found. Run test_chess_vision.py first.")
        return
    
    # Load test images
    board_with_piece = cv2.imread(str(test_dir / "board_with_piece.jpg"))
    empty_board = cv2.imread(str(test_dir / "empty_board.jpg"))
    
    if board_with_piece is None or empty_board is None:
        print("❌ Could not load test images")
        return
    
    print("✓ Loaded test images")
    print(f"Image size: {board_with_piece.shape}")
    
    # Show current view and ask user to identify board area
    print(f"\n📋 Board Detection Setup:")
    print("Look at current_view.jpg to see your camera view")
    print("We need to identify:")
    print("1. Where is the chessboard in the image?")
    print("2. How big are the squares in pixels?")
    print("3. What's a good detection threshold?")
    
    # Interactive parameter input
    print(f"\n🎯 Parameter Input:")
    
    # Board position
    print("Board position (top-left corner of chessboard):")
    board_x = int(input("  X offset (pixels, try 50-200): ") or "100")
    board_y = int(input("  Y offset (pixels, try 50-200): ") or "100") 
    
    # Square size
    square_size = int(input("Square size (pixels, try 40-80): ") or "60")
    
    # Detection threshold
    threshold = float(input("Detection threshold (try 15-40): ") or "25")
    
    print(f"\n🧪 Testing with parameters:")
    print(f"  Board position: ({board_x}, {board_y})")
    print(f"  Square size: {square_size}px")
    print(f"  Threshold: {threshold}")
    
    # Test detection with new parameters
    from lerobot.perception.chess.piece_detector import OccupancyDetector
    from lerobot.perception.chess.state_builder import build_state_from_occupancy
    
    detector = OccupancyDetector(
        square_size_px=square_size,
        grid_offset_xy=(board_x, board_y),
        threshold=threshold
    )
    
    detector.set_empty_reference(empty_board)
    occupancy = detector.detect(board_with_piece)
    state = build_state_from_occupancy(occupancy)
    
    piece_count = np.sum(occupancy)
    print(f"\n📊 Detection Results:")
    print(f"Detected pieces: {piece_count}")
    
    # Show occupancy grid
    print("Occupancy grid:")
    for row in range(8):
        row_str = ""
        for col in range(8):
            row_str += "♟️ " if occupancy[7-row, col] else "⬜ "
        print(f"  {8-row}: {row_str}")
    print("     a  b  c  d  e  f  g  h")
    
    # Create new overlay with updated parameters
    overlay = board_with_piece.copy()
    
    # Draw grid
    for i in range(9):
        x = board_x + i * square_size
        y = board_y + i * square_size
        if x < overlay.shape[1]:
            cv2.line(overlay, (x, board_y), (x, board_y + 8*square_size), (0, 255, 0), 2)
        if y < overlay.shape[0]:
            cv2.line(overlay, (board_x, y), (board_x + 8*square_size, y), (0, 255, 0), 2)
    
    # Draw detected pieces
    for row in range(8):
        for col in range(8):
            if occupancy[row, col]:
                x = board_x + col * square_size + square_size//2
                y = board_y + row * square_size + square_size//2
                cv2.circle(overlay, (x, y), 15, (0, 0, 255), 3)
    
    # Add square labels
    for row in range(8):
        for col in range(8):
            x = board_x + col * square_size + 5
            y = board_y + row * square_size + 20
            square_name = f"{chr(ord('a') + col)}{8 - row}"
            cv2.putText(overlay, square_name, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    
    tuned_overlay_path = test_dir / "tuned_detection.jpg"
    cv2.imwrite(str(tuned_overlay_path), overlay)
    print(f"💾 Saved tuned overlay to: {tuned_overlay_path}")
    
    if piece_count == 1:
        print("\n🎉 PERFECT! Detected exactly 1 piece!")
        
        # Save good parameters
        params = {
            "board_x": board_x,
            "board_y": board_y, 
            "square_size": square_size,
            "threshold": threshold
        }
        
        params_file = test_dir / "detection_params.json"
        with open(params_file, 'w') as f:
            json.dump(params, f, indent=2)
        print(f"💾 Saved working parameters to: {params_file}")
        
    elif piece_count == 0:
        print("⚠️ No pieces detected. Try:")
        print("  - Lower threshold (more sensitive)")
        print("  - Check board position")
        print("  - Ensure good lighting contrast")
        
    else:
        print(f"⚠️ Detected {piece_count} pieces. Try:")
        print("  - Higher threshold (less sensitive)")
        print("  - Adjust board position/size")
        print("  - Better lighting/contrast")
    
    print(f"\n🔄 Run again with: python tune_detection.py")

if __name__ == "__main__":
    tune_detection()








