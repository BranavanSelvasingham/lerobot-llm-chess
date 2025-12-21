#!/usr/bin/env python3
"""
Test by going directly to a recorded corner position.

Usage:
    python scripts/test_go_to_corner.py --port /dev/tty.usbmodemXXXX --corner a1
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--corner", default="a1", choices=["a1", "h1", "h8", "a8"])
    args = parser.parse_args()

    # Load recorded corners
    calib_dir = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower"
    board_model_path = calib_dir / "chess_board_model.json"
    
    with open(board_model_path) as f:
        board_model = json.load(f)
    
    corners_joints = board_model["_calibration_meta"]["corners_joints"]
    
    if args.corner not in corners_joints:
        print(f"Corner {args.corner} not found!")
        return
    
    target_joints = corners_joints[args.corner]
    print(f"Target corner: {args.corner}")
    print(f"Joints: {target_joints}")
    
    # Connect robot
    print(f"\nConnecting to robot...")
    robot_cfg = SO101FollowerConfig(port=args.port, id="so101_chess", cameras={}, use_degrees=True)
    robot = SO101Follower(robot_cfg)
    robot.connect(calibrate=False, skip_firmware_check=True)
    
    # Build action (excluding gripper for now)
    action = {}
    for joint_name, value in target_joints.items():
        if joint_name != "gripper":
            action[f"{joint_name}.pos"] = float(value)
    
    print(f"\nAction to send: {action}")
    
    response = input(f"\nMove to corner {args.corner}? (y/n): ")
    if response.lower() == 'y':
        robot.send_action(action)
        print("✓ Sent action!")
        
        # Wait and check position
        import time
        time.sleep(2)
        obs = robot.get_observation()
        print("\nCurrent positions after move:")
        for joint_name in target_joints:
            if joint_name != "gripper":
                actual = obs.get(f"{joint_name}.pos", "?")
                target = target_joints[joint_name]
                print(f"  {joint_name}: target={target:.1f}, actual={actual:.1f}")
    else:
        print("Cancelled.")
    
    robot.disconnect()


if __name__ == "__main__":
    main()
