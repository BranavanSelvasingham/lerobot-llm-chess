<p align="center">
  <img src="https://raw.githubusercontent.com/huggingface/lerobot/main/media/lerobot-logo-thumbnail.png" width="300" alt="LeRobot">
</p>

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

## 🏗️ Architecture

```
lerobot-llm-chess/
├── chess_robot_ui_llm_v2.py      # Main UI: camera view + LLM tool calling
├── so101_ik_visualizer.py        # Interactive IK visualization tool
├── so101_new_calib.urdf          # Robot URDF for kinematics
│
├── llm-tools/                    # LLM tool implementations
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
