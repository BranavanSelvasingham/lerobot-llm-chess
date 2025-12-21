#!/usr/bin/env python3
"""
SO-101 Robot Arm IK Visualizer with Live Motor Detection

Uses the actual URDF-based kinematics (placo library) for accurate visualization
that matches the real robot configuration.

Features:
- Live motor position detection from connected robot
- Accurate FK using placo library and URDF
- 2D profile (side) view of the robot arm
- Top-down view showing shoulder pan
- Interactive sliders for joint angles (m1-m6)
- Distance and angle displays

Author: SO-101 Chess Project
"""

import argparse
import sys
from pathlib import Path
from threading import Lock
from typing import Dict, Any, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from matplotlib.patches import Circle, Rectangle, Wedge, FancyBboxPatch
from matplotlib.animation import FuncAnimation

# Make `src/` importable when running from repo root.
_REPO_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _REPO_ROOT / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ============================================================================
# ROBOT CONNECTION
# ============================================================================

class RobotConnection:
    """Handles connection to the SO-101 robot for reading motor positions."""
    
    JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    
    def __init__(self, port: str | None = None, *, robot_id: str = "so101_chess"):
        self.port = port
        self.robot_id = robot_id
        self.robot = None
        self.connected = False
        self._lock = Lock()
        self._last_positions: Dict[str, float] = {}
        
        if port:
            self.connect(port)
    
    def connect(self, port: str) -> bool:
        """Connect to the robot."""
        try:
            from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
            from lerobot.robots.so101_follower.so101_follower import SO101Follower
            
            robot_cfg = SO101FollowerConfig(
                port=port, 
                id=self.robot_id,
                cameras={}, 
                use_degrees=True
            )
            self.robot = SO101Follower(robot_cfg)
            self.robot.connect(calibrate=False, skip_firmware_check=True)
            self.connected = True
            self.port = port
            print(f"✓ Connected to robot on {port} (id={self.robot_id})")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to robot: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the robot."""
        if self.robot:
            try:
                self.robot.disconnect()
            except:
                pass
        self.robot = None
        self.connected = False
    
    def read_positions(self) -> Dict[str, float | None]:
        """Read current motor positions in degrees."""
        with self._lock:
            if not self.connected or not self.robot:
                return {name: None for name in self.JOINT_NAMES}
            
            positions: Dict[str, float | None] = {}
            
            for name in self.JOINT_NAMES:
                try:
                    val = self.robot.bus.read("Present_Position", name, normalize=True)
                    positions[name] = float(val)
                    self._last_positions[name] = float(val)
                except Exception:
                    positions[name] = self._last_positions.get(name)
            
            return positions


# ============================================================================
# URDF-BASED KINEMATICS (using placo)
# ============================================================================

class URDFKinematics:
    """URDF-based forward kinematics using placo library."""
    
    BODY_JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
    JAW_JOINT_NAME = "gripper"
    
    # Sign corrections to align bus-reported angles with URDF convention.
    # Positive value = no change, Negative = negate the angle.
    # These are determined empirically by checking if the visualization matches physical arm.
    SIGN_CORRECTIONS = {
        "shoulder_pan": 1.0,
        "shoulder_lift": 1.0,   # drive_mode=1 already handled by bus
        "elbow_flex": -1.0,     # elbow appears inverted
        "wrist_flex": 1.0,
        "wrist_roll": 1.0,
    }
    
    # Angle offsets (degrees) to align motor zero with URDF zero.
    # These are added AFTER sign correction: urdf_angle = (bus_angle * sign) + offset
    # Tune these if the visualization looks "off" by a constant amount.
    ANGLE_OFFSETS = {
        "shoulder_pan": 0.0,
        "shoulder_lift": -23.0,  # Physical looks ~23° more negative than reported
        "elbow_flex": 0.0,
        "wrist_flex": 0.0,
        "wrist_roll": 0.0,
    }

    # Link frames (URDF link names) that represent the motor pivot frames along the main chain.
    # IMPORTANT: these are the *child link* frames of each revolute joint in the chain:
    #   base_link -(M1)-> shoulder_link -(M2)-> upper_arm_link -(M3)-> lower_arm_link
    #   -(M4)-> wrist_link -(M5)-> gripper_link -(fixed)-> gripper_frame_link
    CHAIN_FRAMES: Tuple[str, ...] = (
        "base_link",
        "shoulder_link",
        "upper_arm_link",
        "lower_arm_link",
        "wrist_link",
        "gripper_link",
        "gripper_frame_link",
    )

    # Gripper jaw link (child link of the M6 gripper joint).
    JAW_LINK_FRAME = "moving_jaw_so101_v1_link"
    
    def __init__(self, urdf_path: str | None = None):
        self.urdf_path = urdf_path or self._find_urdf()
        self.robot = None
        self.available = False
        self._jaw_limits_rad: Tuple[float, float] | None = None
        
        if self.urdf_path:
            self._init_placo()
            self._load_jaw_limits_from_urdf()
    
    def _find_urdf(self) -> str | None:
        """Find URDF file in common locations."""
        candidates = [
            _REPO_ROOT / "so101_new_calib.nomesh.urdf",
            _REPO_ROOT / "so101_new_calib.urdf",
            _REPO_ROOT / "so101_kinematics.urdf",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None
    
    def _init_placo(self):
        """Initialize placo kinematics."""
        try:
            import placo
            self.robot = placo.RobotWrapper(self.urdf_path)
            self.available = True
            print(f"✓ Loaded kinematics from {self.urdf_path}")
        except ImportError:
            print("✗ placo library not available - using approximate kinematics")
            self.available = False
        except Exception as e:
            print(f"✗ Failed to load URDF: {e}")
            self.available = False

    def _load_jaw_limits_from_urdf(self) -> None:
        """Parse the URDF to get the M6 jaw joint limits (radians) so we can map 0..100% -> radians."""
        try:
            import xml.etree.ElementTree as ET

            if not self.urdf_path:
                self._jaw_limits_rad = None
                return
            root = ET.parse(self.urdf_path).getroot()
            for j in root.findall("joint"):
                if j.attrib.get("name") != self.JAW_JOINT_NAME:
                    continue
                lim = j.find("limit")
                if lim is None:
                    self._jaw_limits_rad = None
                    return
                lower = float(lim.attrib.get("lower", "0"))
                upper = float(lim.attrib.get("upper", "0"))
                if not np.isfinite(lower) or not np.isfinite(upper) or abs(upper - lower) < 1e-9:
                    self._jaw_limits_rad = None
                    return
                self._jaw_limits_rad = (lower, upper)
                return
        except Exception:
            self._jaw_limits_rad = None

    def _jaw_percent_to_rad(self, pct: float) -> float:
        """Convert gripper percent (0..100) to jaw joint radians using URDF limits."""
        if self._jaw_limits_rad is None:
            # Conservative default: match URDF in this repo (-10deg .. 100deg)
            lower, upper = (-0.174533, 1.74533)
        else:
            lower, upper = self._jaw_limits_rad
        p = float(np.clip(pct, 0.0, 100.0)) / 100.0
        return lower + p * (upper - lower)
    
    def get_points_mm(self, joint_angles: Dict[str, float]) -> Dict[str, np.ndarray]:
        """
        Get positions of all key motor pivots + tool frame in 3D space using the URDF kinematics.
        
        Returns (all in mm):
        - base: base_link origin
        - m1: shoulder_link (M1 pivot frame)
        - m2: upper_arm_link (M2 pivot frame)
        - m3: lower_arm_link (M3 pivot frame)
        - m4: wrist_link (M4 pivot frame)
        - m5: gripper_link (M5 pivot frame)
        - tool: gripper_frame_link (tool/TCP frame)
        - m6 (optional): moving_jaw_so101_v1_link (jaw link frame, driven by M6)
        """
        if not self.available or not self.robot:
            return self._approximate_fk(joint_angles)
        
        # Set joint positions (M1..M5 are in degrees in our app; M6 is percent 0..100)
        # Apply sign corrections for motors with drive_mode=1 in calibration
        for name in self.BODY_JOINT_NAMES:
            angle_deg = float(joint_angles.get(name, 0.0))
            # Apply sign correction then offset: urdf_angle = (bus_angle * sign) + offset
            sign = self.SIGN_CORRECTIONS.get(name, 1.0)
            offset = self.ANGLE_OFFSETS.get(name, 0.0)
            corrected_deg = (angle_deg * sign) + offset
            angle_rad = float(np.radians(corrected_deg))
            try:
                self.robot.set_joint(name, angle_rad)
            except Exception:
                # If the joint name isn't present in a given URDF, ignore.
                pass

        # Set jaw (M6) if present
        if self.JAW_JOINT_NAME in (self.robot.joint_names() if hasattr(self.robot, "joint_names") else []):
            try:
                jaw_pct = float(joint_angles.get("gripper", 0.0))
                self.robot.set_joint(self.JAW_JOINT_NAME, self._jaw_percent_to_rad(jaw_pct))
            except Exception:
                pass
        
        self.robot.update_kinematics()
        
        def _pos(frame_name: str) -> np.ndarray:
            try:
                T = self.robot.get_T_world_frame(frame_name)
                return T[:3, 3].astype(float) * 1000.0  # m -> mm
            except Exception:
                return np.zeros(3, dtype=float)

        base = _pos("base_link")
        points: Dict[str, np.ndarray] = {
            "base": base,
            "m1": _pos("shoulder_link"),
            "m2": _pos("upper_arm_link"),
            "m3": _pos("lower_arm_link"),
            "m4": _pos("wrist_link"),
            "m5": _pos("gripper_link"),
            "tool": _pos("gripper_frame_link"),
        }

        # Optional jaw visualization
        jaw = _pos(self.JAW_LINK_FRAME)
        if np.any(jaw != 0.0):
            points["m6"] = jaw

        return points
    
    def _approximate_fk(self, joint_angles: Dict[str, float]) -> Dict[str, np.ndarray]:
        """Fallback approximate FK when placo is not available (simple planar approximation)."""
        # Very rough approximation in the current shoulder_pan plane (kept as a last-resort fallback).
        base_h = 62.4
        shoulder_offset = 38.8
        L12 = 64.0    # shoulder_link -> upper_arm_link
        L23 = 116.0   # upper_arm_link -> lower_arm_link
        L34 = 135.0   # lower_arm_link -> wrist_link
        L45 = 64.0    # wrist_link -> gripper_link
        L5t = 98.5    # gripper_link -> tool (gripper_frame_link)

        # Apply sign corrections for motors with drive_mode=1 in calibration
        # Apply sign corrections and offsets
        def correct(name: str) -> float:
            val = float(joint_angles.get(name, 0.0))
            sign = self.SIGN_CORRECTIONS.get(name, 1.0)
            offset = self.ANGLE_OFFSETS.get(name, 0.0)
            return np.radians((val * sign) + offset)
        
        t1 = correct("shoulder_pan")
        t2 = correct("shoulder_lift")
        t3 = correct("elbow_flex")
        t4 = correct("wrist_flex")

        def rotz(a: float) -> np.ndarray:
            return np.array([[np.cos(a), -np.sin(a), 0.0], [np.sin(a), np.cos(a), 0.0], [0.0, 0.0, 1.0]])

        yaw = rotz(t1)
        base = np.array([0.0, 0.0, 0.0])
        m1 = yaw @ np.array([shoulder_offset, 0.0, base_h])

        # Planar (x-z) chain in yaw-aligned plane
        x = shoulder_offset
        z = base_h
        a = 0.0

        # M2 to upper arm
        a = t2
        x2 = x + L12 * np.cos(a)
        z2 = z + L12 * np.sin(a)
        m2_local = np.array([x2, 0.0, z2])

        # M3
        a = t2 + t3
        x3 = x2 + L23 * np.cos(a)
        z3 = z2 + L23 * np.sin(a)
        m3_local = np.array([x3, 0.0, z3])

        # M4
        a = t2 + t3 + t4
        x4 = x3 + L34 * np.cos(a)
        z4 = z3 + L34 * np.sin(a)
        m4_local = np.array([x4, 0.0, z4])

        # M5 + tool
        m5_local = m4_local + np.array([L45, 0.0, 0.0])
        tool_local = m5_local + np.array([L5t, 0.0, 0.0])

        points = {
            "base": base,
            "m1": m1,
            "m2": yaw @ m2_local,
            "m3": yaw @ m3_local,
            "m4": yaw @ m4_local,
            "m5": yaw @ m5_local,
            "tool": yaw @ tool_local,
        }
        return points


# ============================================================================
# VISUALIZATION
# ============================================================================

class SO101Visualizer:
    """Interactive visualizer for SO-101 robot arm with live motor detection."""
    
    def __init__(self, robot_port: str | None = None, urdf_path: str | None = None, *, robot_id: str = "so101_chess"):
        # Kinematics
        self.kin = URDFKinematics(urdf_path)
        
        # Robot connection
        self.robot = RobotConnection(robot_port, robot_id=robot_id)
        self.live_mode = self.robot.connected
        
        # Home/rest pose (from calibration, if available)
        self.home_pose = self._load_home_pose_fallback()

        # Current joint angles (degrees / percent)
        self.angles: Dict[str, float] = {
            'shoulder_pan': 0,
            'shoulder_lift': 0,
            'elbow_flex': 0,
            'wrist_flex': 0,
            'wrist_roll': 0,
            'gripper': 50,
        }
        # Start in the known safe rest pose (matches the physical "rest" picture)
        self.angles.update(self.home_pose)
        
        # Animation
        self.animation = None
        self._update_interval = 100  # ms
        
        # Colors - Cyberpunk/Industrial theme
        self.colors = {
            'bg': '#0d1117',
            'grid': '#21262d',
            'axis': '#30363d',
            'base': '#f78166',
            'L1': '#58a6ff',
            'L2': '#a371f7',
            'L3': '#3fb950',
            'joint': '#d29922',
            'gripper': '#f85149',
            'target': '#39d353',
            'workspace': '#161b22',
            'text': '#c9d1d9',
            'text_dim': '#8b949e',
            'accent': '#f78166',
            'panel_bg': '#161b22',
            'live': '#3fb950',
            'offline': '#8b949e',
            'motor_bg': '#21262d',
        }
        
        self._setup_figure()
        self._setup_sliders()
        self._setup_buttons()
        self._update_plot()
        
        # Start live update if connected
        if self.live_mode:
            self._start_live_update()
    
    def _setup_figure(self):
        """Create the figure and axes."""
        plt.style.use('dark_background')
        
        self.fig = plt.figure(figsize=(18, 11), facecolor=self.colors['bg'])
        self.fig.canvas.manager.set_window_title('SO-101 Robot Arm IK Visualizer')
        
        # Main 2D profile view (left side)
        self.ax_profile = self.fig.add_axes([0.05, 0.28, 0.45, 0.65], facecolor=self.colors['bg'])
        
        # Top-down view (top right)
        self.ax_top = self.fig.add_axes([0.54, 0.55, 0.20, 0.38], facecolor=self.colors['bg'])
        
        # Gripper view
        self.ax_gripper = self.fig.add_axes([0.76, 0.55, 0.10, 0.38], facecolor=self.colors['bg'])
        
        # Wrist roll indicator
        self.ax_roll = self.fig.add_axes([0.88, 0.55, 0.10, 0.38], facecolor=self.colors['bg'])
        
        # Motor status panel
        self.ax_motors = self.fig.add_axes([0.54, 0.28, 0.44, 0.22], facecolor=self.colors['panel_bg'])
        self.ax_motors.set_xticks([])
        self.ax_motors.set_yticks([])
        
        # Title and status
        status_text = "● LIVE" if self.live_mode else "○ MANUAL"
        status_color = self.colors['live'] if self.live_mode else self.colors['text_dim']
        
        self.fig.text(0.5, 0.96, 'SO-101 Robot Arm Kinematics Visualizer', 
                     fontsize=20, fontweight='bold', color=self.colors['accent'],
                     ha='center', fontfamily='monospace')
        
        kin_status = "URDF (placo)" if self.kin.available else "Approximate"
        self.fig.text(0.5, 0.93, f'FK Mode: {kin_status}',
                     fontsize=9, color=self.colors['text_dim'], ha='center', 
                     fontfamily='monospace')
        
        self.status_text = self.fig.text(0.92, 0.96, status_text,
                     fontsize=11, color=status_color, ha='right', 
                     fontfamily='monospace', fontweight='bold')
        
        port_text = f"Port: {self.robot.port}" if self.robot.port else "No robot connected"
        self.fig.text(0.92, 0.935, port_text,
                     fontsize=8, color=self.colors['text_dim'], ha='right', 
                     fontfamily='monospace')

        # Start pose info (loaded from calibration artifacts)
        if self.home_pose:
            self.fig.text(
                0.08,
                0.935,
                "Start pose: calibration rest/home",
                fontsize=8,
                color=self.colors["text_dim"],
                ha="left",
                fontfamily="monospace",
            )
    
    def _setup_sliders(self):
        """Create sliders for joint angles."""
        slider_y_start = 0.18
        slider_height = 0.018
        slider_gap = 0.028
        
        # M1 - Shoulder Pan
        ax_m1 = self.fig.add_axes([0.12, slider_y_start, 0.25, slider_height], 
                                  facecolor=self.colors['grid'])
        self.slider_m1 = Slider(ax_m1, 'M1 Pan', -110, 110,
                               valinit=float(self.angles['shoulder_pan']), color=self.colors['joint'],
                               valstep=1)
        
        # M2 - Shoulder Lift
        ax_m2 = self.fig.add_axes([0.12, slider_y_start - slider_gap, 0.25, slider_height], 
                                  facecolor=self.colors['grid'])
        self.slider_m2 = Slider(ax_m2, 'M2 Lift', -100, 100,
                               valinit=float(self.angles['shoulder_lift']), color=self.colors['L1'],
                               valstep=1)
        
        # M3 - Elbow Flex
        ax_m3 = self.fig.add_axes([0.12, slider_y_start - 2*slider_gap, 0.25, slider_height],
                                  facecolor=self.colors['grid'])
        self.slider_m3 = Slider(ax_m3, 'M3 Elbow', -97, 97,
                               valinit=float(self.angles['elbow_flex']), color=self.colors['L2'],
                               valstep=1)
        
        # M4 - Wrist Flex
        ax_m4 = self.fig.add_axes([0.55, slider_y_start, 0.25, slider_height],
                                  facecolor=self.colors['grid'])
        self.slider_m4 = Slider(ax_m4, 'M4 Wrist', -95, 95,
                               valinit=float(self.angles['wrist_flex']), color=self.colors['L3'],
                               valstep=1)
        
        # M5 - Wrist Roll
        ax_m5 = self.fig.add_axes([0.55, slider_y_start - slider_gap, 0.25, slider_height],
                                  facecolor=self.colors['grid'])
        self.slider_m5 = Slider(ax_m5, 'M5 Roll', -160, 160,
                               valinit=float(self.angles['wrist_roll']), color=self.colors['accent'],
                               valstep=1)
        
        # M6 - Gripper
        ax_m6 = self.fig.add_axes([0.55, slider_y_start - 2*slider_gap, 0.25, slider_height],
                                  facecolor=self.colors['grid'])
        self.slider_m6 = Slider(ax_m6, 'M6 Grip', 0, 100,
                               valinit=float(self.angles['gripper']), color=self.colors['gripper'],
                               valstep=1)
        
        # Connect callbacks
        self.slider_m1.on_changed(self._on_slider_change)
        self.slider_m2.on_changed(self._on_slider_change)
        self.slider_m3.on_changed(self._on_slider_change)
        self.slider_m4.on_changed(self._on_slider_change)
        self.slider_m5.on_changed(self._on_slider_change)
        self.slider_m6.on_changed(self._on_slider_change)
        
        # Style sliders
        for slider in [self.slider_m1, self.slider_m2, self.slider_m3, 
                      self.slider_m4, self.slider_m5, self.slider_m6]:
            slider.label.set_fontfamily('monospace')
            slider.label.set_fontsize(9)
            slider.valtext.set_fontfamily('monospace')
    
    def _setup_buttons(self):
        """Create control buttons."""
        btn_y = 0.04
        btn_h = 0.035
        btn_w = 0.08
        
        # Live/Manual toggle
        ax_live = self.fig.add_axes([0.12, btn_y, btn_w, btn_h])
        self.btn_live = Button(ax_live, 'LIVE' if self.live_mode else 'MANUAL', 
                              color=self.colors['live'] if self.live_mode else self.colors['grid'],
                              hovercolor=self.colors['accent'])
        self.btn_live.on_clicked(self._toggle_live_mode)
        self.btn_live.label.set_fontfamily('monospace')
        self.btn_live.label.set_fontweight('bold')
        
        # Reset button
        ax_reset = self.fig.add_axes([0.22, btn_y, btn_w, btn_h])
        self.btn_reset = Button(ax_reset, 'Reset', color=self.colors['grid'],
                               hovercolor=self.colors['accent'])
        self.btn_reset.on_clicked(self._reset_pose)
        self.btn_reset.label.set_fontfamily('monospace')
        
        # Home button (common chess position)
        ax_home = self.fig.add_axes([0.32, btn_y, btn_w, btn_h])
        self.btn_home = Button(ax_home, 'Rest', color=self.colors['grid'],
                              hovercolor=self.colors['L1'])
        self.btn_home.on_clicked(self._home_pose)
        self.btn_home.label.set_fontfamily('monospace')
        
        # Torque Off button
        ax_torque = self.fig.add_axes([0.42, btn_y, btn_w, btn_h])
        self.btn_torque = Button(ax_torque, 'Torque Off', color=self.colors['grid'],
                                hovercolor=self.colors['gripper'])
        self.btn_torque.on_clicked(self._disable_torque)
        self.btn_torque.label.set_fontfamily('monospace')

    def _disable_torque(self, event):
        """Disable torque on all motors so arm can be moved by hand."""
        if not self.robot.connected:
            print("No robot connected")
            return
        
        try:
            import scservo_sdk as scs
            port = scs.PortHandler(self.robot.port)
            port.openPort()
            port.setBaudRate(1000000)
            ph = scs.PacketHandler(0)
            
            for motor_id in range(1, 7):
                result, error = ph.write1ByteTxRx(port, motor_id, 40, 0)  # Torque_Enable = addr 40
                if result == scs.COMM_SUCCESS:
                    print(f'M{motor_id}: torque disabled')
                else:
                    print(f'M{motor_id}: {ph.getTxRxResult(result)}')
            
            port.closePort()
            print('✓ All motors free - you can move the arm by hand')
            
            # Update button to show status
            self.btn_torque.label.set_text('Torque OFF')
            self.btn_torque.color = self.colors['gripper']
        except Exception as e:
            print(f'Failed to disable torque: {e}')

    def _load_home_pose_fallback(self) -> Dict[str, float]:
        """Load a safe rest pose from calibration artifacts if present.

        Priority:
        1) saved_positions.json -> rest_position (most likely matches your physical "rest" pose)
        2) home_position.json -> motor_positions (safe neutral)
        """
        # Prefer the connected robot's calibration_dir if available
        candidates: list[Path] = []
        try:
            if self.robot.robot is not None:
                calib_dir = getattr(self.robot.robot, "calibration_dir", None)
                if calib_dir:
                    candidates.append(Path(calib_dir) / "saved_positions.json")
                    candidates.append(Path(calib_dir) / "home_position.json")
        except Exception:
            pass

        # Standard HF cache location
        try:
            from lerobot.utils.constants import HF_LEROBOT_CALIBRATION, ROBOTS

            candidates.append(HF_LEROBOT_CALIBRATION / ROBOTS / "so101_follower" / "saved_positions.json")
            candidates.append(HF_LEROBOT_CALIBRATION / ROBOTS / "so101_follower" / "home_position.json")
        except Exception:
            pass

        # Repo-local fallbacks (none by default, but allow user to drop a file next to script)
        candidates.append(_REPO_ROOT / "saved_positions.json")
        candidates.append(_REPO_ROOT / "home_position.json")

        for p in candidates:
            try:
                if not p.is_file():
                    continue
                import json

                obj = json.loads(p.read_text())

                # saved_positions.json format
                if p.name == "saved_positions.json":
                    rest = (obj.get("rest_position") or {}).get("positions") or {}
                    if isinstance(rest, dict) and rest:
                        out: Dict[str, float] = {}
                        for k in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]:
                            if k in rest:
                                out[k] = float(rest[k])
                        if out:
                            return out

                # home_position.json format
                mp = obj.get("motor_positions") or {}
                out: Dict[str, float] = {}
                for k in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]:
                    if k in mp:
                        out[k] = float(mp[k])
                if out:
                    return out
            except Exception:
                continue

        return {}
    
    def _start_live_update(self):
        """Start the live update animation."""
        self.animation = FuncAnimation(
            self.fig, 
            self._live_update_frame,
            interval=self._update_interval,
            blit=False,
            cache_frame_data=False
        )
    
    def _live_update_frame(self, frame):
        """Update frame for live mode."""
        if not self.live_mode or not self.robot.connected:
            return
        
        positions = self.robot.read_positions()
        
        # Update angles from robot
        for key in ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']:
            if positions.get(key) is not None:
                self.angles[key] = positions[key]
        
        # Update sliders
        self._update_sliders_from_angles()
        self._update_plot()
    
    def _update_sliders_from_angles(self):
        """Update slider positions without triggering callbacks."""
        for slider in [self.slider_m1, self.slider_m2, self.slider_m3,
                      self.slider_m4, self.slider_m5, self.slider_m6]:
            slider.eventson = False
        
        self.slider_m1.set_val(np.clip(self.angles['shoulder_pan'], -110, 110))
        self.slider_m2.set_val(np.clip(self.angles['shoulder_lift'], -100, 100))
        self.slider_m3.set_val(np.clip(self.angles['elbow_flex'], -97, 97))
        self.slider_m4.set_val(np.clip(self.angles['wrist_flex'], -95, 95))
        self.slider_m5.set_val(np.clip(self.angles['wrist_roll'], -160, 160))
        self.slider_m6.set_val(np.clip(self.angles['gripper'], 0, 100))
        
        for slider in [self.slider_m1, self.slider_m2, self.slider_m3,
                      self.slider_m4, self.slider_m5, self.slider_m6]:
            slider.eventson = True
    
    def _on_slider_change(self, val):
        """Handle slider value changes (manual mode only)."""
        if self.live_mode:
            return
            
        self.angles['shoulder_pan'] = self.slider_m1.val
        self.angles['shoulder_lift'] = self.slider_m2.val
        self.angles['elbow_flex'] = self.slider_m3.val
        self.angles['wrist_flex'] = self.slider_m4.val
        self.angles['wrist_roll'] = self.slider_m5.val
        self.angles['gripper'] = self.slider_m6.val
        self._update_plot()
    
    def _toggle_live_mode(self, event):
        """Toggle between live and manual modes."""
        if not self.robot.connected:
            print("Cannot enter live mode - no robot connected")
            return
            
        self.live_mode = not self.live_mode
        
        if self.live_mode:
            self.btn_live.label.set_text('LIVE')
            self.btn_live.color = self.colors['live']
            self.status_text.set_text('● LIVE')
            self.status_text.set_color(self.colors['live'])
            if self.animation is None:
                self._start_live_update()
        else:
            self.btn_live.label.set_text('MANUAL')
            self.btn_live.color = self.colors['grid']
            self.status_text.set_text('○ MANUAL')
            self.status_text.set_color(self.colors['text_dim'])
        
        self._update_plot()
    
    def _reset_pose(self, event):
        """Reset to zero pose."""
        if self.live_mode:
            return
            
        for key in self.angles:
            self.angles[key] = 0 if key != 'gripper' else 50
        self._update_sliders_from_angles()
        self._update_plot()
    
    def _home_pose(self, event):
        """Set to rest/home pose (from home_position.json if available)."""
        if self.live_mode:
            return

        # Refresh home pose in case user updated the calibration file
        self.home_pose = self._load_home_pose_fallback()
        if self.home_pose:
            self.angles.update(self.home_pose)
        else:
            # Fallback: conservative neutral pose
            self.angles.update(
                {
                    "shoulder_pan": 0,
                    "shoulder_lift": -78,
                    "elbow_flex": -50,
                    "wrist_flex": 4,
                    "wrist_roll": 140,
                    "gripper": 25,
                }
            )
        self._update_sliders_from_angles()
        self._update_plot()
    
    def _update_plot(self):
        """Update all plots."""
        # Get points from kinematics (all in mm, URDF-derived)
        pts = self.kin.get_points_mm(self.angles)
        
        self._draw_profile_view(pts)
        self._draw_top_view(pts)
        self._draw_gripper_view()
        self._draw_roll_view()
        self._draw_motor_panel(pts)
        self.fig.canvas.draw_idle()
    
    def _draw_profile_view(self, pts: Dict[str, np.ndarray]):
        """Draw the 2D profile view using the full URDF chain (motor pivots + tool)."""
        ax = self.ax_profile
        ax.clear()
        
        # Build ordered chain: base -> M1 -> M2 -> M3 -> M4 -> M5 -> tool
        chain_keys = ["base", "m1", "m2", "m3", "m4", "m5", "tool"]
        chain_labels = ["BASE", "M1", "M2", "M3", "M4", "M5", "TOOL"]

        chain_3d = [pts.get(k, np.zeros(3, dtype=float)) for k in chain_keys]

        # Profile plane: rotate world by -theta1 so the M1 yaw plane becomes the X'-Z plane.
        theta1_deg = float(self.angles.get("shoulder_pan", 0.0))
        t = np.radians(-theta1_deg)
        Rz = np.array([[np.cos(t), -np.sin(t), 0.0], [np.sin(t), np.cos(t), 0.0], [0.0, 0.0, 1.0]])

        chain_rot = [Rz @ p for p in chain_3d]
        chain_xz = [(float(p[0]), float(p[2])) for p in chain_rot]

        # Optional jaw point (M6) – branch off from gripper_link (M5 frame)
        jaw_3d = pts.get("m6", None)
        jaw_xz = None
        if jaw_3d is not None:
            jaw_rot = Rz @ jaw_3d
            jaw_xz = (float(jaw_rot[0]), float(jaw_rot[2]))
        
        # Draw workspace boundary (approximate)
        max_reach = 420  # mm approximate
        theta_range = np.linspace(-np.pi/2, np.pi/2, 100)
        outer_x = [max_reach * np.cos(tt) + 40 for tt in theta_range]
        outer_z = [max_reach * np.sin(tt) + 60 for tt in theta_range]
        ax.fill(outer_x + [outer_x[-1], outer_x[0]],
               outer_z + [0, 0],
               color=self.colors['workspace'], alpha=0.4)
        ax.plot(outer_x, outer_z, '--', color=self.colors['accent'], alpha=0.3, linewidth=1)
        
        # Draw floor
        ax.axhline(y=0, color=self.colors['axis'], linestyle='-', linewidth=2, alpha=0.5)
        ax.fill_between([-200, 500], [-200, -200], [0, 0], color=self.colors['grid'], alpha=0.5)
        
        # Draw base
        base_h = max(10.0, float(chain_xz[1][1]))  # use M1 pivot height as base height proxy
        base_rect = Rectangle((-25, 0), 70, base_h,
                              linewidth=2, edgecolor=self.colors['base'],
                              facecolor=self.colors['base'], alpha=0.35)
        ax.add_patch(base_rect)
        
        # Draw full chain segments + label true (3D) lengths
        seg_colors = [self.colors["joint"], self.colors["L1"], self.colors["L2"], self.colors["L3"], self.colors["accent"], self.colors["gripper"]]
        seg_widths = [10, 10, 10, 9, 8, 7]

        for i in range(len(chain_xz) - 1):
            p2 = chain_xz[i]
            p3 = chain_xz[i + 1]
            length_3d = float(np.linalg.norm(chain_3d[i + 1] - chain_3d[i]))
            self._draw_link(
                ax,
                p2,
                p3,
                seg_colors[min(i, len(seg_colors) - 1)],
                f"L{i}",
                seg_widths[min(i, len(seg_widths) - 1)],
                length_override_mm=length_3d,
                label_prefix=f"{chain_labels[i]}→{chain_labels[i+1]}",
            )

        # Optional jaw branch: M5 -> M6 jaw link
        if jaw_xz is not None:
            m5_xz = chain_xz[5]
            length_3d = float(np.linalg.norm(jaw_3d - chain_3d[5])) if jaw_3d is not None else 0.0
            self._draw_link(
                ax,
                m5_xz,
                jaw_xz,
                self.colors["gripper"],
                "JAW",
                6,
                length_override_mm=length_3d,
                label_prefix="M5→M6",
                alpha=0.85,
            )
        
        # Draw joints with motor labels
        joint_sizes = {"base": 14, "m1": 14, "m2": 14, "m3": 13, "m4": 12, "m5": 12, "tool": 10}
        joint_colors = {"base": self.colors["base"], "m1": self.colors["joint"], "m2": self.colors["L1"], "m3": self.colors["L2"], "m4": self.colors["L3"], "m5": self.colors["accent"], "tool": self.colors["gripper"]}

        for k, label, (x, z) in zip(chain_keys, chain_labels, chain_xz):
            size = joint_sizes.get(k, 12)
            color = joint_colors.get(k, self.colors["joint"])
            circle = Circle((x, z), size, color=self.colors["joint"], zorder=6, alpha=0.95)
            ax.add_patch(circle)
            ax.text(x, z + 22, label, fontsize=9, color=color, fontfamily="monospace", fontweight="bold", ha="center")

        # Jaw marker
        if jaw_xz is not None:
            ax.plot(jaw_xz[0], jaw_xz[1], "o", color=self.colors["gripper"], markersize=8, zorder=7)
            ax.text(jaw_xz[0] + 20, jaw_xz[1] + 10, "M6", fontsize=9, color=self.colors["gripper"], fontfamily="monospace", fontweight="bold")
        
        # Draw distance line from origin
        tool_xz = chain_xz[-1]
        dist_from_base = float(np.linalg.norm(pts.get("tool", np.zeros(3)) - pts.get("base", np.zeros(3))))
        ax.plot([0, tool_xz[0]], [0, tool_xz[1]], '--',
               color=self.colors['accent'], alpha=0.4, linewidth=1)
        
        # Distance annotation
        mid_x = tool_xz[0] / 2
        mid_y = tool_xz[1] / 2
        ax.text(mid_x - 20, mid_y + 20, f'{dist_from_base:.0f}mm', 
               fontsize=9, color=self.colors['accent'], fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor=self.colors['bg'], alpha=0.8))
        
        # Tool position text (in profile plane)
        ax.text(tool_xz[0] + 30, tool_xz[1],
               f"(x'={tool_xz[0]:.0f}, z={tool_xz[1]:.0f})",
               fontsize=8, color=self.colors['text'], fontfamily='monospace')
        
        # Configure axes
        xs = [p[0] for p in chain_xz] + ([jaw_xz[0]] if jaw_xz is not None else [])
        zs = [p[1] for p in chain_xz] + ([jaw_xz[1]] if jaw_xz is not None else [])
        x_min, x_max = (min(xs) - 80, max(xs) + 120)
        z_min, z_max = (min(zs) - 120, max(zs) + 120)
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(z_min, z_max)
        ax.set_aspect('equal')
        ax.set_xlabel("Reach x' (mm)  [world rotated by -M1]", fontfamily='monospace', color=self.colors['text'], fontsize=10)
        ax.set_ylabel('Height Z (mm)', fontfamily='monospace', color=self.colors['text'], fontsize=10)
        ax.set_title('2D Profile View (URDF chain + segment lengths)', fontfamily='monospace',
                    color=self.colors['accent'], fontsize=12, fontweight='bold')
        ax.text(0.01, 0.98, f"M1={theta1_deg:+.1f}°", transform=ax.transAxes, va="top", ha="left",
                fontsize=9, color=self.colors["joint"], fontfamily="monospace", fontweight="bold")
        
        ax.grid(True, color=self.colors['grid'], alpha=0.3, linestyle=':')
        ax.tick_params(colors=self.colors['text'])
        for spine in ax.spines.values():
            spine.set_color(self.colors['axis'])
    
    def _draw_link(
        self,
        ax,
        start,
        end,
        color,
        label,
        width,
        *,
        length_override_mm: float | None = None,
        label_prefix: str | None = None,
        alpha: float = 1.0,
    ):
        """Draw a link segment in 2D, with an optional length label (in mm)."""
        ax.plot([start[0], end[0]], [start[1], end[1]],
                color=color, linewidth=width, solid_capstyle='round', zorder=3, alpha=alpha)
        ax.plot([start[0], end[0]], [start[1], end[1]],
                color=color, linewidth=width + 6, alpha=0.12 * alpha, solid_capstyle='round', zorder=2)

        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        length_mm = float(length_override_mm) if length_override_mm is not None else float(
            np.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)
        )
        prefix = f"{label_prefix} " if label_prefix else ""
        ax.text(mid_x - 30, mid_y + 14, f"{prefix}{length_mm:.1f}mm",
                fontsize=8, color=color, fontfamily='monospace', alpha=0.9)
    
    def _draw_top_view(self, pts: Dict[str, np.ndarray]):
        """Draw the top-down view (X-Y plane) showing M1 shoulder pan."""
        ax = self.ax_top
        ax.clear()
        
        # Draw workspace circle
        max_reach = 350
        circle = Circle((0, 0), max_reach, fill=False, 
                        color=self.colors['accent'], linestyle='--', alpha=0.3)
        ax.add_patch(circle)
        
        # Draw pan angle sector
        t1 = self.angles['shoulder_pan']
        sector = Wedge((0, 0), max_reach * 0.3, -110, 110, 
                      color=self.colors['joint'], alpha=0.1)
        ax.add_patch(sector)
        
        # Draw full chain projection (X-Y plane)
        chain_keys = ["base", "m1", "m2", "m3", "m4", "m5", "tool"]
        chain_colors = [self.colors["base"], self.colors["joint"], self.colors["L1"], self.colors["L2"], self.colors["L3"], self.colors["accent"], self.colors["gripper"]]

        prev = None
        for k, c in zip(chain_keys, chain_colors):
            p = pts.get(k, np.zeros(3, dtype=float))
            x, y = float(p[0]), float(p[1])
            if prev is not None:
                ax.plot([prev[0], x], [prev[1], y], color=c, linewidth=4, solid_capstyle="round", alpha=0.95)
            ax.plot(x, y, "o", color=c, markersize=8)
            prev = (x, y)
        
        # M1 angle indicator
        t1_rad = np.radians(t1)
        indicator_len = 80
        ax.annotate('', xy=(indicator_len * np.cos(t1_rad), indicator_len * np.sin(t1_rad)),
                   xytext=(0, 0),
                   arrowprops=dict(arrowstyle='->', color=self.colors['accent'], lw=2))
        ax.text(60 * np.cos(t1_rad), 60 * np.sin(t1_rad) + 25, 
               f'M1: {t1:.0f}°',
               fontsize=9, color=self.colors['joint'], fontfamily='monospace',
               fontweight='bold', ha='center')
        
        # Tool marker
        tool = pts.get("tool", np.zeros(3, dtype=float))
        ax.plot(tool[0], tool[1], '*', color=self.colors['gripper'], markersize=18, zorder=10)
        
        ax.set_xlim(-350, 350)
        ax.set_ylim(-350, 350)
        ax.set_aspect('equal')
        ax.set_title('Top View (M1 Pan)', fontfamily='monospace', 
                    color=self.colors['joint'], fontsize=10, fontweight='bold')
        
        ax.grid(True, color=self.colors['grid'], alpha=0.3, linestyle=':')
        ax.axhline(y=0, color=self.colors['axis'], linewidth=0.5, alpha=0.5)
        ax.axvline(x=0, color=self.colors['axis'], linewidth=0.5, alpha=0.5)
        
        ax.tick_params(colors=self.colors['text'], labelsize=7)
        for spine in ax.spines.values():
            spine.set_color(self.colors['axis'])
    
    def _draw_gripper_view(self):
        """Draw gripper state visualization (M6)."""
        ax = self.ax_gripper
        ax.clear()
        
        grip_pct = self.angles['gripper']
        
        # Draw gripper jaws
        jaw_width = 0.3
        max_opening = 0.8
        opening = max_opening * (1 - grip_pct / 100)
        
        left_jaw = Rectangle((-0.5, -opening/2 - jaw_width), 0.4, jaw_width,
                            color=self.colors['gripper'], alpha=0.8)
        ax.add_patch(left_jaw)
        
        right_jaw = Rectangle((-0.5, opening/2), 0.4, jaw_width,
                             color=self.colors['gripper'], alpha=0.8)
        ax.add_patch(right_jaw)
        
        base = Rectangle((-0.1, -0.5), 0.6, 1.0,
                        color=self.colors['L3'], alpha=0.5)
        ax.add_patch(base)
        
        ax.text(0, -0.9, f'M6: {grip_pct:.0f}%',
               fontsize=10, color=self.colors['gripper'], fontfamily='monospace',
               fontweight='bold', ha='center')
        
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1.2, 1.2)
        ax.set_aspect('equal')
        ax.set_title('Gripper (M6)', fontfamily='monospace',
                    color=self.colors['gripper'], fontsize=10, fontweight='bold')
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color(self.colors['axis'])
    
    def _draw_roll_view(self):
        """Draw wrist roll visualization (M5)."""
        ax = self.ax_roll
        ax.clear()
        
        circle = Circle((0, 0), 0.7, fill=False, 
                        color=self.colors['accent'], linewidth=2)
        ax.add_patch(circle)
        
        inner = Circle((0, 0), 0.2, color=self.colors['accent'], alpha=0.5)
        ax.add_patch(inner)
        
        t5 = self.angles['wrist_roll']
        t5_rad = np.radians(t5)
        ax.plot([0, 0.65 * np.sin(t5_rad)], [0, 0.65 * np.cos(t5_rad)],
               color=self.colors['accent'], linewidth=4, solid_capstyle='round')
        
        for angle in range(0, 360, 45):
            rad = np.radians(angle)
            ax.plot([0.6 * np.sin(rad), 0.75 * np.sin(rad)],
                   [0.6 * np.cos(rad), 0.75 * np.cos(rad)],
                   color=self.colors['text_dim'], linewidth=1)
        
        ax.text(0, -0.95, f'M5: {t5:.0f}°',
               fontsize=10, color=self.colors['accent'], fontfamily='monospace',
               fontweight='bold', ha='center')
        
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1.2, 1.2)
        ax.set_aspect('equal')
        ax.set_title('Wrist Roll (M5)', fontfamily='monospace',
                    color=self.colors['accent'], fontsize=10, fontweight='bold')
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color(self.colors['axis'])
    
    def _draw_motor_panel(self, pts: Dict[str, np.ndarray]):
        """Draw the motor status panel."""
        ax = self.ax_motors
        ax.clear()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xticks([])
        ax.set_yticks([])
        
        ax.text(0.5, 0.92, '▶ ALL MOTOR POSITIONS', fontfamily='monospace', fontsize=11,
               color=self.colors['accent'], fontweight='bold', ha='center', va='top')
        
        motors = [
            ('M1', 'Pan', self.angles['shoulder_pan'], self.colors['joint'], '°'),
            ('M2', 'Lift', self.angles['shoulder_lift'], self.colors['L1'], '°'),
            ('M3', 'Elbow', self.angles['elbow_flex'], self.colors['L2'], '°'),
            ('M4', 'Wrist', self.angles['wrist_flex'], self.colors['L3'], '°'),
            ('M5', 'Roll', self.angles['wrist_roll'], self.colors['accent'], '°'),
            ('M6', 'Grip', self.angles['gripper'], self.colors['gripper'], '%'),
        ]
        
        for i, (motor, name, value, color, unit) in enumerate(motors):
            col = i % 3
            row = i // 3
            
            x = 0.05 + col * 0.32
            y = 0.65 - row * 0.45
            
            box = FancyBboxPatch((x, y - 0.25), 0.28, 0.35,
                                boxstyle="round,pad=0.02",
                                facecolor=self.colors['motor_bg'],
                                edgecolor=color, linewidth=2)
            ax.add_patch(box)
            
            ax.text(x + 0.14, y + 0.05, motor, fontfamily='monospace', fontsize=12,
                   color=color, fontweight='bold', ha='center')
            
            ax.text(x + 0.14, y - 0.12, f'{value:+.1f}{unit}' if unit == '°' else f'{value:.0f}{unit}',
                   fontfamily='monospace', fontsize=14,
                   color=self.colors['text'], fontweight='bold', ha='center')
            
            ax.text(x + 0.14, y - 0.20, name, fontfamily='monospace', fontsize=8,
                   color=self.colors['text_dim'], ha='center')
        
        # Tool 3D position (TCP)
        tool = pts.get("tool", np.zeros(3, dtype=float))
        base = pts.get("base", np.zeros(3, dtype=float))
        r = float(np.sqrt(tool[0] ** 2 + tool[1] ** 2))
        dist_3d = float(np.linalg.norm(tool - base))

        pos_text = f'Tool(TCP): X={tool[0]:.0f}  Y={tool[1]:.0f}  Z={tool[2]:.0f}  |  R={r:.0f}  Dist={dist_3d:.0f}mm'
        ax.text(0.5, 0.02, pos_text, fontfamily='monospace', fontsize=9,
               color=self.colors['text'], ha='center',
               bbox=dict(boxstyle='round', facecolor=self.colors['grid'], alpha=0.5))
        
        for spine in ax.spines.values():
            spine.set_color(self.colors['accent'])
            spine.set_linewidth(1)
    
    def run(self):
        """Start the visualization."""
        plt.show()
        
        if self.robot.connected:
            self.robot.disconnect()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='SO-101 Robot Arm IK Visualizer with Live Motor Detection'
    )
    parser.add_argument(
        '--port', '-p',
        type=str,
        default=None,
        help='Serial port for robot connection (e.g., /dev/tty.usbmodem575E0032081)'
    )
    parser.add_argument(
        '--urdf', '-u',
        type=str,
        default=None,
        help='Path to URDF file for kinematics'
    )
    args = parser.parse_args()
    
    print("=" * 65)
    print("  SO-101 Robot Arm IK Visualizer")
    print("  with URDF-based Kinematics")
    print("=" * 65)
    print()
    
    if args.port:
        print(f"Connecting to robot on {args.port}...")
    else:
        print("No port specified - running in MANUAL mode")
        print("Use --port /dev/tty.usbmodemXXXX to enable LIVE mode")
    print()
    
    print("Controls:")
    print("  - LIVE/MANUAL: Toggle live motor reading")
    print("  - Sliders M1-M6: Adjust joint angles (manual mode)")
    print("  - Reset: Return to zero pose")
    print("  - Rest: Load safe neutral rest pose (home_position.json if available)")
    print()
    
    viz = SO101Visualizer(robot_port=args.port, urdf_path=args.urdf)
    viz.run()


if __name__ == '__main__':
    main()
