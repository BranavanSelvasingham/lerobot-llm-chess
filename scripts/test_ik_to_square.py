#!/usr/bin/env python3
"""
Test IK by moving to a chess square.

Usage:
    python scripts/test_ik_to_square.py --port /dev/tty.usbmodemXXXX --square e4
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.model.kinematics import RobotKinematics

ARM_JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


def find_urdf() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    for name in ["so101_new_calib.nomesh.urdf", "so101_new_calib.urdf"]:
        p = repo_root / name
        if p.exists():
            return str(p)
    raise FileNotFoundError("URDF not found")


def square_to_board_xy(square: str, square_size_x_m: float, square_size_y_m: float) -> tuple[float, float]:
    """Convert chess square (e.g. 'e4') to board XY in meters. Origin at a1 corner."""
    file = square[0].lower()  # a-h
    rank = int(square[1])     # 1-8
    
    # Center of square
    x = (ord(file) - ord('a') + 0.5) * square_size_x_m
    y = (rank - 1 + 0.5) * square_size_y_m
    return x, y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--square", default="e4", help="Target square (e.g. e4)")
    parser.add_argument("--height_mm", type=float, default=50.0, help="Height above board in mm")
    args = parser.parse_args()

    # Load board model
    calib_dir = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so101_follower"
    board_model_path = calib_dir / "chess_board_model.json"
    
    if not board_model_path.exists():
        raise FileNotFoundError(f"No board model at {board_model_path}. Run calibrate_board_transform.py first.")
    
    with open(board_model_path) as f:
        board_model = json.load(f)
    
    T_base_board = np.array(board_model["T_base_board"])
    params = board_model["params"]
    
    # Support both single square_size and separate X/Y sizes
    if "square_size_x_mm" in params:
        square_size_x_m = params["square_size_x_mm"] / 1000.0
        square_size_y_m = params["square_size_y_mm"] / 1000.0
        print(f"Board model loaded: square_size_x={square_size_x_m*1000:.1f}mm, square_size_y={square_size_y_m*1000:.1f}mm")
    else:
        square_size_x_m = square_size_y_m = params["square_size_mm"] / 1000.0
        print(f"Board model loaded: square_size={square_size_x_m*1000:.1f}mm")
    
    # Compute target position
    bx, by = square_to_board_xy(args.square, square_size_x_m, square_size_y_m)
    bz = args.height_mm / 1000.0  # height above board
    
    # Transform to robot base frame
    pt_board = np.array([bx, by, bz, 1.0])
    pt_base = T_base_board @ pt_board
    target_xyz = pt_base[:3]
    
    print(f"\nTarget: {args.square}")
    print(f"  Board coords: [{bx*1000:.1f}, {by*1000:.1f}, {bz*1000:.1f}] mm")
    print(f"  Base coords:  [{target_xyz[0]*1000:.1f}, {target_xyz[1]*1000:.1f}, {target_xyz[2]*1000:.1f}] mm")
    
    # Connect robot
    print(f"\nConnecting to robot...")
    robot_cfg = SO101FollowerConfig(port=args.port, id="so101_chess", cameras={}, use_degrees=True)
    robot = SO101Follower(robot_cfg)
    robot.connect(calibrate=False, skip_firmware_check=True)
    
    # Load kinematics
    urdf_path = find_urdf()
    kin = RobotKinematics(urdf_path, target_frame_name="gripper_frame_link", joint_names=ARM_JOINT_NAMES)
    
    # Get current joint positions
    obs = robot.get_observation()
    current_joints = np.array([obs[f"{j}.pos"] for j in ARM_JOINT_NAMES])
    print(f"Current joints: {[f'{j:.1f}' for j in current_joints]}")
    
    # Get current EE pose via FK (to preserve orientation)
    T_current = kin.forward_kinematics(current_joints)
    R_current = T_current[:3, :3]  # Keep current orientation
    xyz_current = T_current[:3, 3]
    print(f"Current EE: [{xyz_current[0]*1000:.1f}, {xyz_current[1]*1000:.1f}, {xyz_current[2]*1000:.1f}] mm")
    
    # Build target pose (new position, preserve orientation)
    target_pose = np.eye(4)
    target_pose[:3, 3] = target_xyz
    target_pose[:3, :3] = R_current  # Keep current orientation
    
    # Iterative IK (like llm_toolkit does)
    print("\nComputing IK (iterative)...")
    q_best = current_joints.copy()
    best_err = float("inf")
    
    for iteration in range(5):
        result_joints = kin.inverse_kinematics(
            q_best,
            target_pose,
            position_weight=1.0,
            orientation_weight=0.0  # Position only
        )
        
        T_check = kin.forward_kinematics(result_joints)
        xyz_check = T_check[:3, 3]
        err = np.linalg.norm(xyz_check - target_xyz) * 1000
        
        if err < best_err:
            best_err = err
            q_best = result_joints.copy()
        
        if err < 5.0:  # 5mm tolerance
            break
    
    result_joints = q_best
    print(f"IK solution: {[f'{j:.1f}' for j in result_joints]}")
    
    # Verify with FK
    T_fk = kin.forward_kinematics(result_joints)
    fk_pos = T_fk[:3, 3]
    error = np.linalg.norm(fk_pos - target_xyz) * 1000
    print(f"FK verification: [{fk_pos[0]*1000:.1f}, {fk_pos[1]*1000:.1f}, {fk_pos[2]*1000:.1f}] mm")
    print(f"Position error: {error:.1f} mm")
    
    if error > 20:
        print(f"\n⚠️  Large error! IK may not have converged.")
        print("Try moving closer to the target first (e.g., go to a1 corner).")
    
    # Ask to move
    action = {f"{j}.pos": float(result_joints[i]) for i, j in enumerate(ARM_JOINT_NAMES)}
    print(f"\nAction to send: {action}")
    
    response = input(f"\nMove to {args.square}? (y/n): ")
    if response.lower() == 'y':
        # Enable torque first (may have been disabled during calibration)
        robot.bus.sync_write("Torque_Enable", 1, normalize=False)
        
        robot.send_action(action)
        print("Sent action, waiting...")
        
        import time
        time.sleep(2)
        
        # Check where we ended up
        obs = robot.get_observation()
        print("\nPosition after move:")
        for i, j in enumerate(ARM_JOINT_NAMES):
            target = result_joints[i]
            actual = obs.get(f"{j}.pos", 0)
            diff = abs(actual - target)
            print(f"  {j}: target={target:.1f}, actual={actual:.1f}, diff={diff:.1f}")
        print("✓ Done!")
    else:
        print("Cancelled.")
    
    robot.disconnect()


if __name__ == "__main__":
    main()
