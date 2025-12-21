# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np


class RobotKinematics:
    """Robot kinematics using placo library for forward and inverse kinematics."""

    def __init__(
        self,
        urdf_path: str,
        target_frame_name: str = "gripper_frame_link",
        joint_names: list[str] = None,
    ):
        """
        Initialize placo-based kinematics solver.

        Args:
            urdf_path: Path to the robot URDF file
            target_frame_name: Name of the end-effector frame in the URDF
            joint_names: List of joint names to use for the kinematics solver
        """
        try:
            import placo
        except ImportError as e:
            raise ImportError(
                "placo is required for RobotKinematics. "
                "Please install the optional dependencies of `kinematics` in the package."
            ) from e

        self.robot = placo.RobotWrapper(urdf_path)
        self.solver = placo.KinematicsSolver(self.robot)
        self.solver.mask_fbase(True)  # Fix the base

        self.target_frame_name = target_frame_name

        # Set joint names
        self.joint_names = list(self.robot.joint_names()) if joint_names is None else joint_names

        # Initialize frame task for IK
        self.tip_frame = self.solver.add_frame_task(self.target_frame_name, np.eye(4))

    def forward_kinematics(self, joint_pos_deg):
        """
        Compute forward kinematics for given joint configuration given the target frame name in the constructor.

        Args:
            joint_pos_deg: Joint positions in degrees (numpy array)

        Returns:
            4x4 transformation matrix of the end-effector pose
        """

        # Convert degrees to radians
        joint_pos_rad = np.deg2rad(joint_pos_deg[: len(self.joint_names)])

        # Update joint positions in placo robot
        for i, joint_name in enumerate(self.joint_names):
            self.robot.set_joint(joint_name, joint_pos_rad[i])

        # Update kinematics
        self.robot.update_kinematics()

        # Get the transformation matrix
        return self.robot.get_T_world_frame(self.target_frame_name)

    def inverse_kinematics(
        self, current_joint_pos, desired_ee_pose, position_weight=1.0, orientation_weight=0.01
    ):
        """
        Compute inverse kinematics using placo solver.

        Args:
            current_joint_pos: Current joint positions in degrees (used as initial guess)
            desired_ee_pose: Target end-effector pose as a 4x4 transformation matrix
            position_weight: Weight for position constraint in IK
            orientation_weight: Weight for orientation constraint in IK, set to 0.0 to only constrain position

        Returns:
            Joint positions in degrees that achieve the desired end-effector pose
        """

        # Convert current joint positions to radians for initial guess
        current_joint_rad = np.deg2rad(current_joint_pos[: len(self.joint_names)])

        # Set current joint positions as initial guess
        for i, joint_name in enumerate(self.joint_names):
            self.robot.set_joint(joint_name, current_joint_rad[i])

        # Update the target pose for the frame task
        self.tip_frame.T_world_frame = desired_ee_pose

        # Configure the task based on position_only flag
        self.tip_frame.configure(self.target_frame_name, "soft", position_weight, orientation_weight)

        # Solve IK
        self.solver.solve(True)
        self.robot.update_kinematics()

        # Extract joint positions
        joint_pos_rad = []
        for joint_name in self.joint_names:
            joint = self.robot.get_joint(joint_name)
            joint_pos_rad.append(joint)

        # Convert back to degrees
        joint_pos_deg = np.rad2deg(joint_pos_rad)

        # Preserve gripper position if present in current_joint_pos
        if len(current_joint_pos) > len(self.joint_names):
            result = np.zeros_like(current_joint_pos)
            result[: len(self.joint_names)] = joint_pos_deg
            result[len(self.joint_names) :] = current_joint_pos[len(self.joint_names) :]
            return result
        else:
            return joint_pos_deg

    def compute_jacobian(self, joint_pos_deg):
        """
        Compute the position Jacobian (3xN) at the given joint configuration.

        Args:
            joint_pos_deg: Joint positions in degrees (numpy array)

        Returns:
            3xN numpy array where N is the number of joints.
            Maps joint velocities (rad/s) to EE linear velocity (m/s).
        """
        n = len(self.joint_names)
        # Numerical differentiation step (radians).
        # Too small makes the FK difference drown in solver/float noise; too large reduces linear accuracy.
        eps = 1e-3

        # Get current EE position
        T0 = self.forward_kinematics(joint_pos_deg)
        p0 = T0[:3, 3]

        J = np.zeros((3, n))
        for i in range(n):
            q_plus = joint_pos_deg.copy()
            q_plus[i] += np.rad2deg(eps)  # Perturb in degrees
            T_plus = self.forward_kinematics(q_plus)
            p_plus = T_plus[:3, 3]
            J[:, i] = (p_plus - p0) / eps  # dp/dq (m per rad)

        # Restore original configuration
        self.forward_kinematics(joint_pos_deg)
        return J

    def jacobian_delta_ik(self, joint_pos_deg, delta_xyz_m, max_joint_delta_deg=5.0):
        """
        Compute joint deltas for a small EE position delta using the Jacobian.

        This is more stable than full IK for small movements as it keeps the
        arm in roughly the same configuration.

        Args:
            joint_pos_deg: Current joint positions in degrees
            delta_xyz_m: Desired EE position change [dx, dy, dz] in meters
            max_joint_delta_deg: Maximum allowed joint change per axis (degrees)

        Returns:
            New joint positions in degrees
        """
        J = self.compute_jacobian(joint_pos_deg)

        # Use damped least squares (pseudo-inverse with regularization)
        # J @ dq = dp  =>  dq = J^+ @ dp
        damping = 0.01
        JTJ = J.T @ J + damping * np.eye(J.shape[1])
        dq_rad = np.linalg.solve(JTJ, J.T @ delta_xyz_m)

        dq_deg = np.rad2deg(dq_rad)

        # Clamp joint deltas to avoid large jumps
        dq_deg = np.clip(dq_deg, -max_joint_delta_deg, max_joint_delta_deg)

        return joint_pos_deg[:len(self.joint_names)] + dq_deg
