#!/usr/bin/env python3
"""
Calibrate T_base_board by recording gripper positions at 4 board corners.

This script:
1. Connects to the robot (with new motor calibration)
2. Prompts you to move the gripper to each corner (a1, h1, h8, a8)
3. Uses FK to compute the EE position for each corner
4. Fits a plane and computes T_base_board
5. Saves to chess_board_model.json

Usage:
    python scripts/calibrate_board_transform.py --port /dev/tty.usbmodemXXXX
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.model.kinematics import RobotKinematics
from lerobot.configs.chessboard import ChessBoardParams


def find_urdf() -> str:
    """Find the URDF file."""
    repo_root = Path(__file__).resolve().parent.parent
    candidates = [
        repo_root / "so101_new_calib.nomesh.urdf",
        repo_root / "so101_new_calib.urdf",
        repo_root / "so101_kinematics.urdf",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    raise FileNotFoundError("Could not find URDF file")


ARM_JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


def get_ee_position(kin: RobotKinematics, joint_angles_deg: list[float]) -> np.ndarray:
    """Get EE position in meters from joint angles in degrees."""
    T = kin.forward_kinematics(np.array(joint_angles_deg))
    return T[:3, 3]  # meters


def fit_board_transform(corners_xyz: dict[str, np.ndarray], square_size_m: float) -> np.ndarray:
    """
    Fit T_base_board (4x4) from recorded corner positions.
    
    Board frame: origin at a1, +X toward h1, +Y toward a8, +Z up.
    """
    a1 = corners_xyz["a1"]
    h1 = corners_xyz["h1"]
    a8 = corners_xyz["a8"]
    h8 = corners_xyz["h8"]
    
    # Board dimensions
    board_width = 8 * square_size_m  # a1 to h1
    board_height = 8 * square_size_m  # a1 to a8
    
    # Compute board axes from measured corners
    # X axis: a1 -> h1 direction
    x_vec = h1 - a1
    x_len = np.linalg.norm(x_vec)
    x_axis = x_vec / x_len
    
    # Y axis: a1 -> a8 direction  
    y_vec = a8 - a1
    y_len = np.linalg.norm(y_vec)
    y_axis_raw = y_vec / y_len
    
    # Make Y perpendicular to X (Gram-Schmidt)
    y_axis = y_axis_raw - np.dot(y_axis_raw, x_axis) * x_axis
    y_axis = y_axis / np.linalg.norm(y_axis)
    
    # Z axis: cross product (board normal, pointing up)
    z_axis = np.cross(x_axis, y_axis)
    z_axis = z_axis / np.linalg.norm(z_axis)
    
    # Ensure Z points up (positive world Z)
    if z_axis[2] < 0:
        z_axis = -z_axis
        # Flip Y to maintain right-handed system
        y_axis = np.cross(z_axis, x_axis)
    
    # Rotation matrix: columns are board axes in base frame
    R = np.column_stack([x_axis, y_axis, z_axis])
    
    # Translation: a1 position is the board origin
    t = a1
    
    # Build 4x4 transform
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    
    # Report measured vs expected dimensions
    print(f"\nBoard geometry check:")
    print(f"  Measured a1-h1 distance: {x_len*1000:.1f} mm (expected {board_width*1000:.1f} mm)")
    print(f"  Measured a1-a8 distance: {y_len*1000:.1f} mm (expected {board_height*1000:.1f} mm)")
    print(f"  Scale error X: {(x_len/board_width - 1)*100:+.1f}%")
    print(f"  Scale error Y: {(y_len/board_height - 1)*100:+.1f}%")
    
    # Check h8 prediction
    h8_predicted = T @ np.array([board_width, board_height, 0, 1])
    h8_error = np.linalg.norm(h8_predicted[:3] - h8) * 1000
    print(f"  h8 prediction error: {h8_error:.1f} mm")
    
    return T


def main():
    parser = argparse.ArgumentParser(description="Calibrate T_base_board from corner positions")
    parser.add_argument("--port", required=True, help="Robot serial port")
    parser.add_argument("--square_size_mm", type=float, default=50.0, help="Chess square size in mm")
    parser.add_argument("--board_height_mm", type=float, default=15.0, help="Board surface height in mm")
    args = parser.parse_args()
    
    square_size_m = args.square_size_mm / 1000.0
    board_height_m = args.board_height_mm / 1000.0
    
    print("=" * 60)
    print("  T_base_board Calibration")
    print("=" * 60)
    
    # Connect robot
    print(f"\nConnecting to robot on {args.port}...")
    robot_cfg = SO101FollowerConfig(port=args.port, id="so101_chess", cameras={}, use_degrees=True)
    robot = SO101Follower(robot_cfg)
    robot.connect(calibrate=False, skip_firmware_check=True)
    print("✓ Robot connected")
    
    # Disable torque so user can move the arm by hand
    print("✓ Disabling torque (you can now move the arm freely)")
    robot.bus.sync_write("Torque_Enable", 0, normalize=False)
    
    # Load kinematics
    urdf_path = find_urdf()
    print(f"✓ Using URDF: {urdf_path}")
    kin = RobotKinematics(urdf_path, target_frame_name="gripper_frame_link", joint_names=ARM_JOINT_NAMES)
    
    # Record corners
    corners = ["a1", "h1", "h8", "a8"]
    corners_xyz: dict[str, np.ndarray] = {}
    corners_joints: dict[str, dict[str, float]] = {}
    
    joint_names = ARM_JOINT_NAMES
    
    print("\n" + "=" * 60)
    print("Move the gripper tip to touch each corner of the chessboard.")
    print("The gripper should be pointing DOWN, touching the board surface.")
    print("=" * 60)
    
    for corner in corners:
        input(f"\nMove gripper to corner {corner.upper()} and press ENTER...")
        
        obs = robot.get_observation()
        joint_angles = [obs[f"{j}.pos"] for j in joint_names]
        gripper_pos = obs.get("gripper.pos", 0)
        
        # Store joint positions
        corners_joints[corner] = {
            **{j: obs[f"{j}.pos"] for j in joint_names},
            "gripper": gripper_pos
        }
        
        # Compute EE position via FK
        ee_pos = get_ee_position(kin, joint_angles)
        corners_xyz[corner] = ee_pos
        
        print(f"  {corner}: joints={[f'{a:.1f}' for a in joint_angles]}")
        print(f"  {corner}: EE position = [{ee_pos[0]*1000:.1f}, {ee_pos[1]*1000:.1f}, {ee_pos[2]*1000:.1f}] mm")
    
    # Fit board transform
    print("\n" + "=" * 60)
    print("Computing T_base_board...")
    T_base_board = fit_board_transform(corners_xyz, square_size_m)
    
    print(f"\nT_base_board:")
    print(T_base_board)
    
    # Save to chess_board_model.json
    calib_dir = robot.calibration_dir
    out_path = calib_dir / "chess_board_model.json"
    
    board_model = {
        "params": {
            "square_size_mm": args.square_size_mm,
            "board_size": [8, 8],
            "board_height_mm": args.board_height_mm,
            "origin_square": "a1"
        },
        "T_base_board": T_base_board.tolist(),
        "_calibration_meta": {
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "corners_xyz_mm": {k: (v * 1000).tolist() for k, v in corners_xyz.items()},
            "corners_joints": corners_joints
        }
    }
    
    out_path.write_text(json.dumps(board_model, indent=2))
    print(f"\n✓ Saved to {out_path}")
    
    # Also save corner joints for reference
    corners_path = calib_dir / "chess_corner_motors.json"
    corners_data = [
        {"name": corner, "motors": corners_joints[corner], "xyz": (corners_xyz[corner] * 1000).tolist()}
        for corner in corners
    ]
    corners_path.write_text(json.dumps(corners_data, indent=2))
    print(f"✓ Saved corner joints to {corners_path}")
    
    robot.disconnect()
    print("\n✓ Calibration complete!")
    print("\nYour IK should now target board squares accurately.")


if __name__ == "__main__":
    main()
