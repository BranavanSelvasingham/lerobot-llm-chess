<h1 align="center">♟️ LeRobot Chess</h1>

<p align="center">
  <strong>An SO-101 robot arm that plays chess using computer vision and LLM-powered natural language control</strong>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-llm-tools">LLM Tools</a> •
  <a href="#-hardware">Hardware</a>
</p>

---

## 🎯 Project Goals

This project extends [HuggingFace LeRobot](https://github.com/huggingface/lerobot) to create an autonomous chess-playing robot with:

1. **Natural Language Control** — Talk to your robot using plain English ("Move the knight to e4")
2. **Computer Vision** — Live camera feed for board monitoring
3. **Precision Manipulation** — IK-based gripper control for chess piece movement
4. **LLM Tool Calling** — GPT-powered interpretation of commands into robot actions

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- SO-101 robot arm (Feetech STS3215 motors)
- USB camera
- OpenAI API key (for LLM features)

### Installation

```bash
# Clone the repository
git clone https://github.com/BranavanSelvasingham/lerobot-llm-chess.git
cd lerobot-llm-chess

# Create virtual environment
conda create -y -n lerobot-chess python=3.10
conda activate lerobot-chess

# Install ffmpeg
conda install ffmpeg -c conda-forge

# Install the package
pip install -e ".[feetech]"

# Install UI dependencies
pip install PySide6 python-dotenv openai
```

### Configuration

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your-api-key-here
```

### Find Your Hardware

```bash
# Find robot serial port
python -m lerobot.scripts.lerobot_find_port

# Find camera index
python -m lerobot.scripts.lerobot_find_cameras opencv
```

### Run the UI

```bash
python chess_robot_ui_llm_v2.py --port /dev/tty.usbmodemXXXX
```

### Simulator Calibration Regression

Before simulator, camera profile, or perception calibration changes, run the hardware-free local regression gate documented in [docs/sim_calibration_regression.md](docs/sim_calibration_regression.md). A focused GitHub Actions workflow runs the same gate for relevant pull requests into `feat/telemetry-recording`. The suite records its summary and artifacts under `/private/tmp/lerobot_sim/calibration_regression_suite` locally and skips robot hardware and GUI display paths.

## 🏗️ Architecture

```
lerobot-llm-chess/
├── chess_robot_ui_llm_v2.py      # Main UI: camera view + LLM tool calling
├── so101_ik_visualizer.py        # Interactive IK visualization tool
├── so101_new_calib.urdf          # Robot URDF for kinematics
│
├── skills/                       # ⭐ Skill API layer (abstraction boundary)
│   ├── __init__.py               # Public exports
│   ├── skill_api.py              # High-level manipulation primitives
│   └── demo.py                   # CLI demo: python -m skills.demo
│
├── llm-tools/                    # LLM tool implementations (use Skill API)
│   ├── llm_toolkit.py            # Robot connection, FK/IK, tool dispatch
│   ├── tool_go_home.py           # Return to home position
│   ├── tool_move_to_square.py    # Move gripper to chess square
│   ├── tool_move_piece.py        # Pick and place chess piece
│   ├── tool_move_gripper_delta.py # Move gripper by delta XYZ
│   ├── tool_open_gripper.py      # Open gripper
│   ├── tool_close_gripper.py     # Close gripper
│   ├── tool_set_gripper_percent.py # Set gripper to specific %
│   ├── tool_read_joints.py       # Read current joint positions
│   ├── tool_move_joints.py       # Move specific joints
│   ├── tool_set_all_joints.py    # Set all joint positions
│   ├── tool_go_birds_eye.py      # Move to bird's eye view
│   ├── tool_look_around.py       # Scan workspace
│   └── tool_nudge_gripper.py     # Small gripper adjustments
│
├── scripts/                      # Calibration & testing utilities
│   ├── calibrate_board_transform.py
│   ├── setup_birds_eye_view.py
│   ├── save_current_as_rest.py
│   └── test_ik_to_square.py
│
├── docs/
│   └── sim_calibration_regression.md # Hardware-free simulator calibration gate
│
├── src/lerobot/                  # Core lerobot modules used
│   ├── model/kinematics.py       # FK/IK via placo library
│   ├── cameras/opencv/           # OpenCV camera interface
│   ├── robots/so101_follower/    # SO-101 robot configuration
│   ├── motors/feetech/           # Feetech motor control
│   ├── configs/chessboard.py     # Chess board parameters
│   ├── perception/chess/         # Board model & geometry
│   └── utils/                    # Constants & utilities
│
└── archive/                      # Legacy code (not actively used)
```

## 🎯 Skill API

The Skill API (`skills/skill_api.py`) provides a **canonical abstraction boundary** between high-level manipulation primitives and low-level motor/IK control. All LLM tools route through this layer.

### Design Principles

1. **Stable Names**: Skill function names are stable across versions
2. **Deterministic Delegation**: Skills delegate to existing IK/trajectory/motor code
3. **Rich Return Dicts**: Every skill returns `{"ok": bool, ...}` with context
4. **No Behavior Changes**: The Skill API wraps existing logic without modification

### Available Skills

| Skill | Description |
|-------|-------------|
| `home()` | Move robot to saved home/rest position |
| `reach_square(square, approach_height_mm)` | Position gripper above a chess square |
| `reach_pose(pose, frame)` | Move gripper to arbitrary XYZ pose |
| `grasp(profile)` | Close gripper with stall detection |
| `release(percent)` | Open gripper to release |
| `place_square(square, retreat_height_mm)` | Lower, release, and retreat from square |
| `recover(reason)` | Attempt recovery (open gripper, go home) |
| `scan_board()` | Move to bird's eye view (stub for vision) |
| `nudge(direction, distance_mm)` | Small position adjustment |
| `move_delta(dx_mm, dy_mm, dz_mm)` | Cartesian delta move |
| `set_gripper(percent)` | Set gripper opening percentage |
| `read_joints(include_gripper)` | Read current joint positions |
| `move_joints(targets, relative, max_step_deg)` | Direct joint control |

### Usage Examples

**Via SkillContext (recommended)**:
```python
from skills import SkillContext

with SkillContext(port="/dev/tty.usbmodem...") as ctx:
    ctx.home()
    ctx.reach_square("e2", approach_height_mm=80)
    ctx.grasp()
    ctx.place_square("e4", retreat_height_mm=80)
    ctx.home()
```

**Via module-level functions**:
```python
from skills.skill_api import home, reach_square, grasp
from llm_toolkit import AppConfig, KinematicsTools

tools = KinematicsTools(AppConfig(port="/dev/tty.usbmodem..."))
home(tools)
reach_square(tools, "e2", approach_height_mm=80)
grasp(tools, profile="default")
```

### CLI Demo

Run a simple pick-and-place sequence:

```bash
# With robot connected
python -m skills.demo --port /dev/tty.usbmodem...

# Dry run (prints planned sequence)
python -m skills.demo --dry-run
```

### Tool → Skill Mapping

| LLM Tool | Skill API Call |
|----------|----------------|
| `go_home` | `home()` |
| `go_birds_eye` | `scan_board()` |
| `move_to_square` | `reach_square()` |
| `open_gripper` | `release()` |
| `close_gripper` | `grasp()` |
| `move_piece` | Sequence: `release` → `reach_square` → `grasp` → `reach_square` → `release` |
| `nudge_gripper` | `nudge()` |
| `set_gripper_percent` | `set_gripper()` |
| `read_joints` | `read_joints()` |
| `move_joints` | `move_joints()` |
| `set_all_joints` | `move_joints()` |
| `look_around` | `move_delta()` |
| `move_gripper_delta` | `reach_pose()` (with polar conversion) |

## 🛠️ LLM Tools

The robot is controlled via LLM tool calls. Available tools:

| Tool | Description |
|------|-------------|
| `go_home` | Return gripper to home position |
| `move_to_square` | Move gripper above a chess square (e.g., "e4") |
| `move_piece` | Pick piece from one square, place on another |
| `move_gripper_delta` | Move gripper by delta XYZ in meters |
| `open_gripper` | Fully open the gripper |
| `close_gripper` | Close gripper to grasp |
| `set_gripper_percent` | Set gripper opening (0-100%) |
| `read_joints` | Get current joint positions |
| `move_joints` | Move specific joints to positions |
| `go_birds_eye` | Move to overhead view position |

### Example Commands

In the UI chat, type natural language:

```
"Go to home position"
"Move above square e4"
"Pick up the piece on e2 and place it on e4"
"Open the gripper"
"Move the gripper up 5 centimeters"
```

## 🔧 Hardware

### SO-101 Robot Arm

| Motor | Joint | Function |
|-------|-------|----------|
| 1 | shoulder_pan | Left/right rotation |
| 2 | shoulder_lift | Up/down arm lift |
| 3 | elbow_flex | Elbow bend |
| 4 | wrist_flex | Wrist up/down |
| 5 | wrist_roll | Gripper rotation |
| 6 | gripper | Open/close |

### Specifications

- **Motors**: Feetech STS3215 (12-bit, 4096 positions)
- **Kinematics**: URDF-based FK/IK via placo library
- **Camera**: USB webcam (640x480)

## 📜 License

Apache 2.0 — See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- **[HuggingFace LeRobot](https://github.com/huggingface/lerobot)** — The foundation this project builds upon
- **[TheRobotStudio](https://www.therobotstudio.com/)** — SO-101 robot arm design
- **OpenAI** — GPT for natural language understanding

---

<p align="center">
  <sub>Built with ❤️ for robot chess enthusiasts</sub>
</p>
