#!/usr/bin/env python3

"""Minimal Chess Robot UI (LLM v2)

This is a ground-up rewrite of `chess_robot_ui_llm.py` focused on two things only:
- Live camera view
- Tool-call view/log (manual + optional LLM tool-calling)

Kinematics-based tools are implemented via `lerobot.model.kinematics.RobotKinematics`
(placho/IK) and execute joint-space commands on the SO-101 follower arm.

Run:
  python chess_robot_ui_llm_v2.py --port /dev/tty.usbmodemXXXX

Notes:
- Requires a URDF available on disk for IK.
- Uses calibration assets in HF LeRobot cache by default.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# Make `src/` importable when running from repo root.
_REPO_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _REPO_ROOT / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_LLM_TOOLS_DIR = _REPO_ROOT / "llm-tools"
if _LLM_TOOLS_DIR.exists() and str(_LLM_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_LLM_TOOLS_DIR))

from PySide6.QtCore import QFileSystemWatcher, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from openai import OpenAI  # type: ignore

    _OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None  # type: ignore
    _OPENAI_AVAILABLE = False

import cv2

from lerobot.cameras.opencv.configuration_opencv import ColorMode, OpenCVCameraConfig
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
from llm_toolkit import AppConfig, KinematicsTools  # pyright: ignore[reportMissingImports]


class ToolExecutionThread(QThread):
    log_line = Signal(str)
    finished_ok = Signal(bool)

    def __init__(self, tools: KinematicsTools, tool_name: str, tool_args: dict[str, Any]):
        super().__init__()
        self.tools = tools
        self.tool_name = tool_name
        self.tool_args = dict(tool_args or {})

    def run(self) -> None:
        try:
            self.log_line.emit(f"TOOL {self.tool_name} args={json.dumps(self.tool_args)}")
            result = self.tools.execute_tool(self.tool_name, self.tool_args)
            self.log_line.emit(json.dumps(result, indent=2))
            self.finished_ok.emit(bool(result.get("ok", False)))
        except Exception as e:
            self.log_line.emit(json.dumps({"ok": False, "error": str(e)}, indent=2))
            self.finished_ok.emit(False)


class LLMThread(QThread):
    log_line = Signal(str)
    finished_ok = Signal(bool)
    step_update = Signal(int, int)  # (current_step, max_steps)

    def __init__(
        self,
        *,
        ui: "ChessRobotUILLMV2",
        llm_client: Any,
        model: str,
        tools: KinematicsTools,
        command: str,
        enabled_tool_names: list[str] | None = None,
        max_steps: int = 20,
    ):
        super().__init__()
        self.ui = ui
        self.llm_client = llm_client
        self.model = model
        self.tools_impl = tools
        self.command = command
        self.max_steps = int(max_steps)
        self.enabled_tool_names = enabled_tool_names

    def run(self) -> None:
        try:
            tool_schemas = self.tools_impl.tool_schemas()
            enabled_set: set[str] | None = None
            if isinstance(self.enabled_tool_names, list):
                enabled_set = {str(x) for x in self.enabled_tool_names if str(x)}
                tool_schemas = [
                    s
                    for s in tool_schemas
                    if isinstance(s, dict) and str(s.get("name", "")) in enabled_set
                ]
            prev_response_id: str | None = None

            # Log accumulator for conversation context
            log_history: list[str] = []

            # Capture initial camera image
            initial_image = self.ui.capture_frame_base64()
            log_history.append(f"USER: {self.command}")

            # Build initial user message with optional image
            user_content: list[dict[str, Any]] = [
                {"type": "input_text", "text": self.command}
            ]

            # Always include current motor positions so the model can do reliable joint-space control.
            try:
                joints_now = self.tools_impl.execute_tool("read_joints", {"include_gripper": True})
                joints_payload = joints_now
                if isinstance(joints_now, dict) and isinstance(joints_now.get("joints"), dict):
                    joints_payload = joints_now["joints"]
                    # If some joints are unreadable, ensure keys are present (None) so the model still sees all motors.
                    for k in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]:
                        joints_payload.setdefault(k, None)
                user_content.append(
                    {
                        "type": "input_text",
                        "text": "CURRENT_JOINTS (degrees; gripper 0..100):\n"
                        + json.dumps(joints_payload, indent=2),
                    }
                )
                self.log_line.emit("[LLM input includes current joint positions]")
                self.log_line.emit("[LLM joint snapshot]\n" + json.dumps(joints_payload, indent=2))
            except Exception:
                self.log_line.emit("[LLM input joint snapshot failed]")

            # Include a compact URDF summary (dimensions/axes/limits) ONCE at the start.
            try:
                urdf_summary = self.tools_impl.urdf_summary()
                if urdf_summary and isinstance(urdf_summary, dict):
                    user_content.append(
                        {
                            "type": "input_text",
                            "text": "URDF_SUMMARY (axes/limits/link offsets; model-derived):\n"
                            + json.dumps(urdf_summary, indent=2),
                        }
                    )
                    self.log_line.emit("[LLM input includes URDF summary]")
            except Exception:
                self.log_line.emit("[LLM input URDF summary unavailable]")

            # Include URDF-derived local joint effects (FK finite-difference).
            try:
                effects = self.tools_impl.joint_effects_mm_per_deg()
                user_content.append(
                    {
                        "type": "input_text",
                        "text": "JOINT_EFFECTS_MM_PER_DEG (URDF-derived FK sensitivity at CURRENT_JOINTS):\n"
                        + json.dumps(effects, indent=2),
                    }
                )
                self.log_line.emit("[LLM input includes joint effects]")
            except Exception:
                self.log_line.emit("[LLM input joint effects unavailable]")

            if initial_image:
                user_content.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{initial_image}",
                })
                # Avoid printing base64; just show size for observability.
                self.log_line.emit(f"[LLM input includes initial image (base64 chars={len(initial_image)})]")
            else:
                self.log_line.emit("[LLM input has no image available yet]")

            input_items: Any = [{"role": "user", "content": user_content}]

            # System instructions mentioning vision capability
            enabled_line = ""
            try:
                if enabled_set is not None:
                    enabled_line = (
                        "TOOLS ENABLED THIS RUN: "
                        + ", ".join(sorted(enabled_set))
                        + "\n(If a tool is not listed, it is disabled and you cannot call it.)\n\n"
                    )
            except Exception:
                enabled_line = ""
            instructions = (
                "You control a real SO-101 robot arm for chess piece manipulation. "
                "You receive camera images showing the current state after each action.\n\n"
                + enabled_line

                + "AUTONOMOUS EXECUTION POLICY:\n"
                "- Do NOT ask questions; infer reasonable defaults and proceed.\n"
                "- Use camera images and tool results to verify progress and adjust.\n"
                "- Execute multi-step sequences until the goal is achieved.\n"
                "- If stuck after 3 failures, call go_home and report what happened.\n\n"

                "CAMERA SETUP:\n"
                "- Camera is mounted ON THE GRIPPER (eye-in-hand)\n"
                "- Gripper tongs are visible at the bottom of the image\n"
                "- To grab a piece: center it BETWEEN the gripper tongs in the image\n\n"
                
                "WORKFLOW FOR PICKING UP A PIECE:\n"
                "1. go_birds_eye - Get overview of the board to locate the piece\n"
                "2. Identify which square the piece is on from the bird's eye view\n"
                "3. open_gripper - Ensure gripper is open\n"
                "4. move_to_square square='XX' height='hover' - Position above the piece\n"
                "5. CHECK CAMERA: Is the piece centered between gripper tongs?\n"
                "   - If NOT centered: use nudge_gripper to adjust (left/right/forward/back)\n"
                "   - Repeat until piece appears centered\n"
                "6. move_to_square square='XX' height='low' - Lower to grasp height\n"
                "7. CHECK CAMERA AGAIN: Verify piece is still centered\n"
                "8. close_gripper - Grasp the piece (will stop when it grips something)\n"
                "9. move_to_square square='YY' height='hover' - Move to destination\n"
                "10. move_to_square square='YY' height='low' - Lower to place\n"
                "11. open_gripper - Release the piece\n\n"

                "AVAILABLE TOOLS:\n"
                "- go_birds_eye: Move to bird's eye view to see the FULL BOARD. Use this FIRST to locate pieces.\n"
                "- move_to_square: Position gripper above a square. height='hover' (~80mm above) or 'low' (grasp height)\n"
                "- nudge_gripper: Fine adjustment (left/right/forward/back/up/down, distance_mm). Use to center piece in view.\n"
                "- open_gripper: Open gripper to release a piece.\n"
                "- close_gripper: Close gripper until it grips something (stall detection).\n"
                "- move_piece: Full pick-and-place in one step (use only if confident in calibration).\n"
                "- go_home: Return to rest position.\n\n"
                
                "IMPORTANT:\n"
                "- ALWAYS use go_birds_eye FIRST to see where pieces are on the board.\n"
                "- ALWAYS verify piece is centered between gripper tongs before closing.\n"
                "- If piece is not centered, use nudge_gripper to adjust.\n\n"

                "JOINT CHEAT SHEET (SO-101, APPROXIMATE):\n"
                "- shoulder_pan (M1): rotates the whole arm left/right (moves camera view sideways).\n"
                "- shoulder_lift (M2): raises/lowers the upper arm. More negative = arm reaches further forward.\n"
                "- elbow_flex (M3): bends/extends the elbow. More negative = elbow straighter = reaches further.\n"
                "- wrist_flex (M4): pitches the wrist/gripper. Adjust to keep gripper pointing down at board.\n"
                "- wrist_roll (M5): rolls the gripper about its axis (rotates the tongs in the image).\n"
                "- gripper (M6): 0=closed, 100=open.\n"
                "NOTE: Signs may be opposite of intuition. Probe with ±3° and observe image changes.\n\n"

                "JOINT COORDINATION RECIPES (use set_all_joints or move_joints):\n"
                "To EXTEND reach (move gripper away from robot, toward far side of board):\n"
                "  - Decrease shoulder_lift (M2) by ~5° (tilts upper arm forward)\n"
                "  - INCREASE elbow_flex (M3) by ~5° (straightens elbow - OPPOSITE direction from M2!)\n"
                "  - Adjust wrist_flex (M4) to keep gripper pointing down (probe to find direction)\n"
                "To RETRACT (move gripper toward robot, toward near side of board):\n"
                "  - Increase shoulder_lift (M2) by ~5° (tilts upper arm back)\n"
                "  - DECREASE elbow_flex (M3) by ~5° (bends elbow more - OPPOSITE direction from M2!)\n"
                "  - Adjust wrist_flex (M4) accordingly\n"
                "To move DOWN toward board (lower Z):\n"
                "  - Decrease shoulder_lift (M2) by ~3-5° (lowers arm)\n"
                "  - Adjust elbow_flex (M3) and wrist_flex (M4) to compensate\n"
                "To move UP (raise Z):\n"
                "  - Increase shoulder_lift (M2) by ~3-5° (raises arm)\n"
                "  - Adjust M3 and M4 to compensate\n"
                "To move LEFT/RIGHT across board:\n"
                "  - Change shoulder_pan (M1) alone: probe ±5° to find direction\n"
                "KEY INSIGHT: M2 and M3 move in OPPOSITE directions for reach changes!\n\n"

                "HOW TO USE set_all_joints EFFECTIVELY:\n"
                "- Start from CURRENT_JOINTS, copy all values.\n"
                "- For reach: change M2 one direction, M3 the OPPOSITE direction, adjust M4 to keep gripper down.\n"
                "- For sideways: adjust M1 (shoulder_pan) alone.\n"
                "- Call set_all_joints with all 6 targets. The tool clamps per-call deltas for safety.\n"
                "- After each call, check the image + CURRENT_JOINTS to see what changed.\n"
                "- If a move didn't go the right direction, reverse the signs and retry.\n"
                "- If you get lost or near limits, call go_home and retry.\n\n"
                
                "GRABBING A PIECE:\n"
                "- First, ensure gripper is open (set_gripper_percent ~90-100)\n"
                "- Use move_gripper_delta to position the piece between the tongs\n"
                "- The piece should be centered horizontally between the two tong tips\n"
                "- Lower the gripper (dz_mm negative) so tongs are at piece height\n"
                "- Close gripper (set_gripper_percent ~10-30) to grasp\n"
                "- Verify grip in the camera image before lifting\n"
                "- Do NOT claim you gripped/lifted a piece unless you visually confirm it in the image\n\n"
                
                "ACCURACY LIMITATIONS:\n"
                "- Position accuracy is ~5-10mm due to motor backlash and IK solving\n"
                "- Small moves (<10mm) may not register due to motor deadband\n"
                "- Repeated small deltas can accumulate drift\n"
                "- After tool execution, check the updated image to verify the action\n"
                "- For motion tools: if the result has ok=false / ik_ok=false or a large final_error_mm, treat it as a missed move and retry (or switch to move_joints)\n"
                "- If position seems off, consider going home and retrying\n\n"
                
                "BEST PRACTICES:\n"
                "- Prefer medium-sized moves (20-50mm) over many tiny ones\n"
                "- Use the camera image to visually align the piece between tongs\n"
                "- Use move_gripper_delta for fine positioning adjustments\n"
                "- If Cartesian moves are unreliable, switch to joint-space nudges using move_joints + camera feedback\n"
                "- Always verify results in the camera image before proceeding\n"
                "- If unsure about where the pawn is, use look_around to scan; do not ask the user\n"
            )

            for step in range(self.max_steps):
                self.step_update.emit(step + 1, self.max_steps)
                # Log what we're about to send (high signal, no giant blobs)
                in_has_image = False
                try:
                    # Detect image parts in the outbound items (best-effort)
                    for it in input_items:
                        if isinstance(it, dict) and it.get("role") == "user":
                            content = it.get("content", [])
                            if isinstance(content, list):
                                in_has_image = any(
                                    isinstance(c, dict) and c.get("type") in ("input_image", "image_url") for c in content
                                )
                except Exception:
                    pass
                self.log_line.emit(
                    f"[LLM request step={step+1}/{self.max_steps} model={self.model} image={in_has_image} prev_response_id={'set' if prev_response_id else 'none'}]"
                )

                resp = self.llm_client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=input_items,
                    tools=tool_schemas,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                    max_tool_calls=1,
                    max_output_tokens=450,
                    previous_response_id=prev_response_id,
                )

                prev_response_id = str(getattr(resp, "id", prev_response_id) or "") or prev_response_id

                txt = str(getattr(resp, "output_text", "") or "").strip()
                if txt:
                    self.log_line.emit(f"LLM: {txt}")
                    log_history.append(f"LLM: {txt}")
                else:
                    self.log_line.emit("[LLM: (no text output)]")

                calls = [it for it in getattr(resp, "output", []) if getattr(it, "type", None) == "function_call"]
                if not calls:
                    self.finished_ok.emit(True)
                    return

                call = calls[0]
                name = str(getattr(call, "name", ""))
                raw_args = getattr(call, "arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception:
                    args = {}
                if not isinstance(args, dict):
                    args = {}

                self.log_line.emit(f"LLM->TOOL {name} args={json.dumps(args)}")
                log_history.append(f"TOOL {name}: {json.dumps(args)}")

                result = self.tools_impl.execute_tool(name, args)
                result_str = json.dumps(result, indent=2)
                self.log_line.emit(result_str)
                log_history.append(f"RESULT: {result_str}")

                # Capture post-action image
                post_image = self.ui.capture_frame_base64()

                # Build context from recent log entries (last 10)
                context_text = "\n".join(log_history[-10:])
                # Show exactly what context text we're about to send back (no images / no base64).
                self.log_line.emit("[LLM context sent after tool]\n" + context_text)

                # Feed tool output back to the model with image
                input_items = [
                    {
                        "type": "function_call_output",
                        "call_id": str(getattr(call, "call_id", "")),
                        "output": json.dumps(result),
                    }
                ]

                # Always include current motor positions in the next prompt (even if image is missing).
                joints_text = ""
                try:
                    joints_now = self.tools_impl.execute_tool("read_joints", {"include_gripper": True})
                    joints_payload = joints_now
                    if isinstance(joints_now, dict) and isinstance(joints_now.get("joints"), dict):
                        joints_payload = joints_now["joints"]
                        for k in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]:
                            joints_payload.setdefault(k, None)
                    joints_text = "CURRENT_JOINTS (degrees; gripper 0..100):\n" + json.dumps(
                        joints_payload, indent=2
                    )
                    self.log_line.emit("[LLM input includes current joint positions]")
                    self.log_line.emit("[LLM joint snapshot]\n" + json.dumps(joints_payload, indent=2))
                except Exception:
                    joints_text = "CURRENT_JOINTS: [error reading joints]"

                effects_text = ""
                try:
                    effects = self.tools_impl.joint_effects_mm_per_deg()
                    effects_text = "JOINT_EFFECTS_MM_PER_DEG:\n" + json.dumps(effects, indent=2)
                except Exception:
                    effects_text = "JOINT_EFFECTS_MM_PER_DEG: [unavailable]"

                user_parts: list[dict[str, Any]] = [
                    {
                        "type": "input_text",
                        "text": f"[Action complete. Recent log:\n{context_text}]\n\n{joints_text}\n\n{effects_text}",
                    }
                ]
                if post_image:
                    user_parts.append(
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{post_image}"}
                    )
                    self.log_line.emit(f"[LLM input includes post-action image (base64 chars={len(post_image)})]")
                else:
                    self.log_line.emit("[LLM input has no post-action image available]")

                input_items.append({"role": "user", "content": user_parts})

            self.log_line.emit(json.dumps({"ok": False, "error": f"LLM exceeded max_steps={self.max_steps}"}, indent=2))
            self.finished_ok.emit(False)
        except Exception as e:
            self.log_line.emit(json.dumps({"ok": False, "error": str(e)}, indent=2))
            self.finished_ok.emit(False)


class CollapsibleSection(QWidget):
    """Simple collapsible container with an arrow + title header."""

    def __init__(self, title: str, *, expanded: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = str(title)

        self.toggle_btn = QToolButton(text=self._title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(bool(expanded))
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle_btn.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.toggle_btn.clicked.connect(self._on_toggled)

        self.content = QWidget()
        self.content.setVisible(bool(expanded))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addWidget(self.toggle_btn)
        outer.addWidget(self.content)

    def _on_toggled(self, checked: bool) -> None:
        self.content.setVisible(bool(checked))
        self.toggle_btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def setContentWidget(self, widget: QWidget) -> None:
        # Clear existing content
        for child in list(self.content.children()):
            if isinstance(child, QWidget):
                child.setParent(None)
        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)


class ChessRobotUILLMV2(QMainWindow):
    append_log_signal = Signal(str)

    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        # AppConfig is frozen; keep UI-selected values separately.
        self._selected_model: str = str(getattr(cfg, "model", "gpt-4o-mini"))

        self.setWindowTitle("Chess Robot UI (LLM v2) - Camera + Tools")
        self.resize(1280, 720)

        self.tools = KinematicsTools(cfg)
        self._torque_disabled_ui: bool = False

        self._camera: OpenCVCamera | None = None
        self._last_frame_bgr: np.ndarray | None = None

        self._llm_init_error: str | None = None
        self._llm_client: Any | None = None

        # Load API key from repo-local .env if present (optional).
        # Many users keep OPENAI_API_KEY in a .env file but don't export it into the shell.
        try:
            if os.getenv("OPENAI_API_KEY") is None:
                env_path = _REPO_ROOT / ".env"
                if env_path.is_file():
                    for raw in env_path.read_text().splitlines():
                        line = raw.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and (os.getenv(k) is None):
                            os.environ[k] = v
        except Exception:
            # If parsing fails, just fall back to environment variables.
            pass

        if _OPENAI_AVAILABLE:
            api_key = cfg.api_key or os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    self._llm_client = OpenAI(api_key=api_key)
                except Exception as e:
                    self._llm_init_error = str(e)
                    self._llm_client = None

        self._tool_thread: ToolExecutionThread | None = None
        self._llm_thread: LLMThread | None = None

        self.append_log_signal.connect(self._append_log)

        self._build_ui()
        self._setup_camera()
        self._setup_file_watcher()

        self._camera_timer = QTimer(self)
        self._camera_timer.timeout.connect(self._tick_camera)
        self._camera_timer.start(int(1000 / max(5, int(cfg.camera_fps))))

        self._refresh_status()

    # -----------------------------
    # UI
    # -----------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Restart banner (hidden by default)
        self.restart_banner = QFrame()
        self.restart_banner.setStyleSheet(
            "QFrame { background-color: #1a3a5c; border-bottom: 1px solid #2d5a8a; }"
        )
        self.restart_banner.setVisible(False)
        banner_layout = QHBoxLayout(self.restart_banner)
        banner_layout.setContentsMargins(10, 6, 10, 6)
        banner_label = QLabel("🔄 Code changes detected.")
        banner_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
        banner_layout.addWidget(banner_label)
        banner_layout.addStretch()
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setStyleSheet(
            "QPushButton { background-color: #238636; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2ea043; }"
        )
        self.restart_btn.clicked.connect(self._restart_app)
        banner_layout.addWidget(self.restart_btn)
        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setStyleSheet(
            "QPushButton { background-color: #30363d; color: #c9d1d9; padding: 4px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #484f58; }"
        )
        dismiss_btn.clicked.connect(lambda: self.restart_banner.setVisible(False))
        banner_layout.addWidget(dismiss_btn)
        root_layout.addWidget(self.restart_banner)

        # Main content area
        content = QWidget()
        root_layout.addWidget(content, 1)
        layout = QHBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Camera panel
        cam_group = QGroupBox("Camera")
        cam_layout = QVBoxLayout(cam_group)
        cam_layout.setContentsMargins(10, 10, 10, 10)

        self.camera_label = QLabel("(camera not connected)")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(640, 480)
        self.camera_label.setStyleSheet("background: #0b0f14; color: #c9d1d9; border: 1px solid #30363d;")
        cam_layout.addWidget(self.camera_label, 1)

        self.camera_status = QLabel("Camera: --")
        self.camera_status.setStyleSheet("color: #8b949e;")
        cam_layout.addWidget(self.camera_status)

        splitter.addWidget(cam_group)

        # Tools panel
        tools_group = QGroupBox("Tools")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setContentsMargins(10, 10, 10, 10)
        tools_layout.setSpacing(10)

        # Activity status (prominent indicator)
        activity_row = QHBoxLayout()
        self.activity_label = QLabel("● IDLE")
        self.activity_label.setStyleSheet(
            "QLabel { color: #3fb950; font-weight: bold; font-size: 14px; padding: 4px 10px; "
            "background-color: #1a3d2a; border-radius: 4px; }"
        )
        activity_row.addWidget(self.activity_label)
        activity_row.addStretch()
        tools_layout.addLayout(activity_row)

        self.status_label = QLabel("Robot: -- | Kinematics: -- | Board: --")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #c9d1d9;")
        tools_layout.addWidget(self.status_label)

        # Torque + diagnostics row
        torque_row = QHBoxLayout()
        self.torque_off_btn = QPushButton("STOP (Torque OFF)")
        self.torque_off_btn.setStyleSheet(
            "QPushButton { background-color: #da3633; color: white; padding: 6px 12px; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #f85149; }"
        )
        self.torque_off_btn.clicked.connect(self._torque_off)
        torque_row.addWidget(self.torque_off_btn)

        self.torque_on_btn = QPushButton("Torque ON")
        self.torque_on_btn.setStyleSheet(
            "QPushButton { background-color: #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #484f58; }"
        )
        self.torque_on_btn.clicked.connect(self._torque_on)
        torque_row.addWidget(self.torque_on_btn)

        self.diag_btn = QPushButton("Read Motor Diagnostics")
        self.diag_btn.clicked.connect(self._read_motor_diagnostics)
        torque_row.addWidget(self.diag_btn)
        
        # Speed control
        torque_row.addWidget(QLabel("Speed:"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(100, 2000)
        self.speed_spin.setValue(500)
        self.speed_spin.setSingleStep(100)
        self.speed_spin.setDecimals(0)
        self.speed_spin.setToolTip("Motor speed (100=slow, 2000=fast)")
        self.speed_spin.valueChanged.connect(self._set_speed)
        torque_row.addWidget(self.speed_spin)
        
        torque_row.addStretch()
        tools_layout.addLayout(torque_row)

        # LLM controls
        llm_row = QHBoxLayout()

        # Model selector
        model_label = QLabel("Model:")
        llm_row.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            # GPT-5.2 series (latest)
            "gpt-5.2",
            "gpt-5.2-pro",
            "gpt-5.2-chat-latest",
            # GPT-5 family
            "gpt-5.1",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            # GPT-4o series (multimodal, recommended for vision)
            "gpt-4o",
            "gpt-4o-2024-11-20",
            "gpt-4o-2024-08-06",
            "gpt-4o-mini",
            # GPT-4.1 series (latest, up to 1M context)
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            # GPT-4 Turbo
            "gpt-4-turbo",
            "gpt-4-turbo-2024-04-09",
            # o-series reasoning models
            "o1",
            "o1-mini",
            "o1-preview",
            "o3",
            "o3-mini",
            "o4-mini",
        ])
        # Allow typing arbitrary model IDs (future-proof)
        self.model_combo.setEditable(True)
        # Set default from config
        idx = self.model_combo.findText(self._selected_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText(self._selected_model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        llm_row.addWidget(self.model_combo)

        self.llm_input = QLineEdit()
        self.llm_input.setPlaceholderText("Type an LLM command (e.g., 'move forward 25mm')…")
        llm_row.addWidget(self.llm_input, 1)
        self.llm_run_btn = QPushButton("Run LLM")
        self.llm_run_btn.clicked.connect(self._run_llm)
        llm_row.addWidget(self.llm_run_btn)
        tools_layout.addLayout(llm_row)

        # LLM tool directory (enable/disable tools exposed to the model)
        tool_dir_body = QGroupBox()
        tool_dir_layout = QVBoxLayout(tool_dir_body)
        tool_dir_layout.setContentsMargins(10, 10, 10, 10)
        tool_dir_layout.setSpacing(6)
        tool_dir_layout.addWidget(QLabel("Choose which tools the LLM can call for this run:"))

        self.llm_tool_checks: dict[str, QCheckBox] = {}
        self._llm_tool_names_ordered: list[str] = []
        try:
            schemas = self.tools.tool_schemas()
            seen: set[str] = set()
            for s in schemas:
                if not isinstance(s, dict):
                    continue
                n = str(s.get("name", "")).strip()
                if not n or n in seen:
                    continue
                seen.add(n)
                self._llm_tool_names_ordered.append(n)
        except Exception:
            self._llm_tool_names_ordered = []

        cols = QHBoxLayout()
        col_left = QVBoxLayout()
        col_right = QVBoxLayout()
        cols.addLayout(col_left, 1)
        cols.addLayout(col_right, 1)

        for idx, name in enumerate(self._llm_tool_names_ordered):
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.llm_tool_checks[name] = cb
            (col_left if (idx % 2 == 0) else col_right).addWidget(cb)
        col_left.addStretch()
        col_right.addStretch()
        tool_dir_layout.addLayout(cols)

        btn_row = QHBoxLayout()
        self.llm_tools_enable_all_btn = QPushButton("Enable all")
        self.llm_tools_disable_all_btn = QPushButton("Disable all")
        self.llm_tools_enable_all_btn.clicked.connect(lambda: self._set_llm_tools_enabled(True))
        self.llm_tools_disable_all_btn.clicked.connect(lambda: self._set_llm_tools_enabled(False))
        btn_row.addWidget(self.llm_tools_enable_all_btn)
        btn_row.addWidget(self.llm_tools_disable_all_btn)
        btn_row.addStretch()
        tool_dir_layout.addLayout(btn_row)

        self.llm_tool_dir_section = CollapsibleSection("LLM Tool Directory", expanded=False)
        self.llm_tool_dir_section.setContentWidget(tool_dir_body)
        tools_layout.addWidget(self.llm_tool_dir_section)

        # Manual tool controls
        manual_group = QGroupBox()
        manual_layout = QVBoxLayout(manual_group)
        manual_layout.setContentsMargins(10, 10, 10, 10)
        manual_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Tool:"))
        self.tool_combo = QComboBox()
        # Essential chess tools only
        self.tool_combo.addItems(["go_birds_eye", "go_home", "open_gripper", "close_gripper", "move_piece"])
        self.tool_combo.currentTextChanged.connect(self._sync_tool_fields)
        top_row.addWidget(self.tool_combo, 1)
        manual_layout.addLayout(top_row)

        self.tool_fields = QStackedWidget()
        manual_layout.addWidget(self.tool_fields)

        # Fields: go_birds_eye (no args)
        w_birds = QWidget()
        wbl = QHBoxLayout(w_birds)
        wbl.setContentsMargins(0, 0, 0, 0)
        wbl.addWidget(QLabel("Move to bird's eye view to observe board"))
        wbl.addStretch()
        self.tool_fields.addWidget(w_birds)

        # Fields: go_home (no args)
        w_home = QWidget()
        whl = QHBoxLayout(w_home)
        whl.setContentsMargins(0, 0, 0, 0)
        whl.addWidget(QLabel("Return to rest position"))
        whl.addStretch()
        self.tool_fields.addWidget(w_home)

        # Fields: open_gripper (no args)
        w_open = QWidget()
        wol = QHBoxLayout(w_open)
        wol.setContentsMargins(0, 0, 0, 0)
        wol.addWidget(QLabel("Open gripper to release piece"))
        wol.addStretch()
        self.tool_fields.addWidget(w_open)

        # Fields: close_gripper (no args)
        w_close = QWidget()
        wcl = QHBoxLayout(w_close)
        wcl.setContentsMargins(0, 0, 0, 0)
        wcl.addWidget(QLabel("Close gripper to grasp piece"))
        wcl.addStretch()
        self.tool_fields.addWidget(w_close)

        # Fields: move_piece
        w_piece = QWidget()
        wpl = QHBoxLayout(w_piece)
        wpl.setContentsMargins(0, 0, 0, 0)
        self.from_sq = QLineEdit(); self.from_sq.setPlaceholderText("from (e2)"); self.from_sq.setText("e2")
        self.to_sq = QLineEdit(); self.to_sq.setPlaceholderText("to (e4)"); self.to_sq.setText("e4")
        self.hover_spin = QDoubleSpinBox(); self.hover_spin.setRange(0.0, 0.30); self.hover_spin.setDecimals(3); self.hover_spin.setSingleStep(0.005); self.hover_spin.setValue(0.08)
        self.transit_spin = QDoubleSpinBox(); self.transit_spin.setRange(0.0, 0.40); self.transit_spin.setDecimals(3); self.transit_spin.setSingleStep(0.005); self.transit_spin.setValue(0.15)
        wpl.addWidget(QLabel("from")); wpl.addWidget(self.from_sq)
        wpl.addWidget(QLabel("to")); wpl.addWidget(self.to_sq)
        wpl.addWidget(QLabel("hover(m)")); wpl.addWidget(self.hover_spin)
        wpl.addWidget(QLabel("transit(m)")); wpl.addWidget(self.transit_spin)
        self.tool_fields.addWidget(w_piece)

        self.exec_btn = QPushButton("Execute")
        self.exec_btn.clicked.connect(self._run_manual_tool)
        manual_layout.addWidget(self.exec_btn)

        self.manual_section = CollapsibleSection("Manual Tool Call", expanded=True)
        self.manual_section.setContentWidget(manual_group)
        tools_layout.addWidget(self.manual_section)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Menlo, Monaco, Consolas, monospace; font-size: 10pt;")
        self.log_view.setPlaceholderText("Tool calls + results will appear here…")
        tools_layout.addWidget(self.log_view, 1)

        splitter.addWidget(tools_group)
        splitter.setSizes([750, 530])

        self._sync_tool_fields(self.tool_combo.currentText())

        # Disable LLM button if no client
        if self._llm_client is None:
            self.llm_run_btn.setEnabled(False)
            if not _OPENAI_AVAILABLE:
                reason = "OpenAI client unavailable: python package 'openai' is not installed."
            elif (self.cfg.api_key or os.getenv("OPENAI_API_KEY")) is None:
                reason = "OpenAI client unavailable: set OPENAI_API_KEY (or pass --api-key)."
            elif self._llm_init_error:
                reason = f"OpenAI client failed to initialize: {self._llm_init_error}"
            else:
                reason = "OpenAI client unavailable (unknown reason)."
            self.llm_run_btn.setToolTip(reason)
            self._log(reason)

    def _append_log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"{ts} {line}")

    def _log(self, line: str) -> None:
        self.append_log_signal.emit(str(line))

    def _refresh_status(self) -> None:
        robot_ok = bool(self.tools.robot is not None and self.tools.robot.is_connected)
        kin_ok = bool(self.tools.kin is not None)
        board_ok = bool(self.tools.board_model is not None and self.tools.board_model.T_base_board is not None)
        llm_ok = bool(self._llm_client is not None)
        if llm_ok:
            llm_status = "ok"
        elif not _OPENAI_AVAILABLE:
            llm_status = "missing openai pkg"
        elif (self.cfg.api_key or os.getenv("OPENAI_API_KEY")) is None:
            llm_status = "missing API key"
        elif self._llm_init_error:
            llm_status = "init failed"
        else:
            llm_status = "unavailable"

        self.status_label.setText(
            f"Robot: {'connected' if robot_ok else 'disconnected'}"
            f" | Kinematics: {'ok' if kin_ok else 'missing'}"
            f" | Board: {'ok' if board_ok else 'missing T_base_board'}"
            f" | LLM: {llm_status}"
            f" | Torque: {'OFF' if bool(getattr(self.tools, 'torque_disabled', False)) else 'ON'}"
        )

    # -----------------------------
    # File watcher for code changes
    # -----------------------------

    def _setup_file_watcher(self) -> None:
        """Watch Python files for changes and show restart banner."""
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._on_file_changed)
        self._file_watcher.directoryChanged.connect(self._on_directory_changed)

        # Watch the main script
        main_script = Path(__file__).resolve()
        if main_script.exists():
            self._file_watcher.addPath(str(main_script))

        # Watch the llm-tools directory
        llm_tools_dir = _LLM_TOOLS_DIR
        if llm_tools_dir.exists():
            self._file_watcher.addPath(str(llm_tools_dir))
            for py_file in llm_tools_dir.glob("*.py"):
                self._file_watcher.addPath(str(py_file))

    def _on_file_changed(self, path: str) -> None:
        """Called when a watched file changes."""
        self._log(f"File changed: {Path(path).name}")
        self.restart_banner.setVisible(True)
        # Re-add the file to the watcher (some editors replace files)
        if Path(path).exists():
            self._file_watcher.addPath(path)

    def _on_directory_changed(self, path: str) -> None:
        """Called when a watched directory changes."""
        self._log(f"Directory changed: {Path(path).name}")
        self.restart_banner.setVisible(True)
        # Re-add any new .py files
        dir_path = Path(path)
        if dir_path.exists():
            for py_file in dir_path.glob("*.py"):
                if str(py_file) not in self._file_watcher.files():
                    self._file_watcher.addPath(str(py_file))

    def _restart_app(self) -> None:
        """Restart the application to pick up code changes."""
        self._log("Restarting application...")
        # Give a moment for the log to appear
        QTimer.singleShot(100, self._do_restart)

    def _do_restart(self) -> None:
        """Actually perform the restart."""
        # Clean up resources
        try:
            if self._camera_timer:
                self._camera_timer.stop()
        except Exception:
            pass
        try:
            if self._camera is not None and self._camera.is_connected:
                self._camera.disconnect()
        except Exception:
            pass
        try:
            self.tools.disconnect_robot()
        except Exception:
            pass

        # Restart the process
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    def _sync_tool_fields(self, tool_name: str) -> None:
        name = str(tool_name)
        idx = {"go_birds_eye": 0, "go_home": 1, "open_gripper": 2, "close_gripper": 3, "move_piece": 4}.get(name, 0)
        self.tool_fields.setCurrentIndex(int(idx))

    # -----------------------------
    # Camera
    # -----------------------------

    def _setup_camera(self) -> None:
        try:
            cfg = OpenCVCameraConfig(
                index_or_path=int(self.cfg.camera_index),
                width=int(self.cfg.camera_width),
                height=int(self.cfg.camera_height),
                fps=int(self.cfg.camera_fps),
                color_mode=ColorMode.BGR,
            )
            self._camera = OpenCVCamera(cfg)
            self._camera.connect(warmup=True)
            self._log(f"Camera connected (index={self.cfg.camera_index})")
        except Exception as e:
            self._camera = None
            self._log(f"Camera failed to connect: {e}")

    def _tick_camera(self) -> None:
        cam = self._camera
        if cam is None or not cam.is_connected:
            self.camera_status.setText("Camera: disconnected")
            return

        try:
            frame = cam.async_read(timeout_ms=50)
            # Frame is BGR
            self._last_frame_bgr = frame
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = frame_rgb.shape
            bytes_per_line = 3 * w
            qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            self.camera_label.setPixmap(pix.scaled(self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.camera_status.setText(f"Camera: {w}x{h} @ ~{self.cfg.camera_fps}fps")
        except Exception:
            # Don't spam; just keep last frame
            self.camera_status.setText("Camera: read failed")

    def capture_frame_base64(self) -> str | None:
        """Capture current camera frame as base64 JPEG for LLM vision."""
        if self._last_frame_bgr is None:
            return None
        try:
            _, buffer = cv2.imencode('.jpg', self._last_frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return base64.b64encode(buffer).decode('utf-8')
        except Exception:
            return None

    # -----------------------------
    # Tool execution
    # -----------------------------

    def _on_model_changed(self, model: str) -> None:
        self._selected_model = str(model)
        self._log(f"LLM model changed to: {model}")

    def _set_busy(self, busy: bool, context: str = "") -> None:
        # Update activity indicator
        if busy:
            label = "● BUSY" if not context else f"● BUSY ({context})"
            self.activity_label.setText(label)
            self.activity_label.setStyleSheet(
                "QLabel { color: #d29922; font-weight: bold; font-size: 14px; padding: 4px 10px; "
                "background-color: #3d3117; border-radius: 4px; }"
            )
        else:
            self.activity_label.setText("● IDLE")
            self.activity_label.setStyleSheet(
                "QLabel { color: #3fb950; font-weight: bold; font-size: 14px; padding: 4px 10px; "
                "background-color: #1a3d2a; border-radius: 4px; }"
            )

        self.exec_btn.setEnabled(not busy)
        self.tool_combo.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.llm_run_btn.setEnabled((not busy) and (self._llm_client is not None))
        self.llm_input.setEnabled(not busy)
        # LLM tool directory should not change mid-run.
        try:
            for cb in getattr(self, "llm_tool_checks", {}).values():
                cb.setEnabled(not busy)
            if hasattr(self, "llm_tools_enable_all_btn"):
                self.llm_tools_enable_all_btn.setEnabled(not busy)
            if hasattr(self, "llm_tools_disable_all_btn"):
                self.llm_tools_disable_all_btn.setEnabled(not busy)
        except Exception:
            pass
        # Safety: torque buttons should always be available.
        self.torque_off_btn.setEnabled(True)
        self.torque_on_btn.setEnabled(True)
        self.diag_btn.setEnabled(True)

    def _get_enabled_llm_tools(self) -> set[str]:
        enabled: set[str] = set()
        try:
            for name, cb in getattr(self, "llm_tool_checks", {}).items():
                if cb.isChecked():
                    enabled.add(str(name))
        except Exception:
            pass
        return enabled

    def _set_llm_tools_enabled(self, enabled: bool) -> None:
        try:
            for cb in getattr(self, "llm_tool_checks", {}).values():
                cb.setChecked(bool(enabled))
        except Exception:
            pass

    def _run_manual_tool(self) -> None:
        if self._tool_thread is not None and self._tool_thread.isRunning():
            return
        if bool(getattr(self.tools, "torque_disabled", False)):
            self._log("Torque is OFF. Click 'Torque ON' before running tools.")
            return

        tool = str(self.tool_combo.currentText())
        args: dict[str, Any] = {}

        if tool == "go_birds_eye":
            args = {}
        elif tool == "go_home":
            args = {}
        elif tool == "open_gripper":
            args = {}
        elif tool == "close_gripper":
            args = {}
        elif tool == "move_piece":
            args = {
                "from_square": str(self.from_sq.text()).strip(),
                "to_square": str(self.to_sq.text()).strip(),
                "hover_height_m": float(self.hover_spin.value()),
                "transit_height_m": float(self.transit_spin.value()),
            }

        self._set_busy(True, f"Manual: {tool}")
        self._refresh_status()

        t = ToolExecutionThread(self.tools, tool, args)
        self._tool_thread = t
        t.log_line.connect(self._log)
        t.finished_ok.connect(lambda ok: (self._set_busy(False), self._refresh_status()))
        t.start()

    def _run_llm(self) -> None:
        if self._llm_client is None:
            return
        if self._llm_thread is not None and self._llm_thread.isRunning():
            return
        if bool(getattr(self.tools, "torque_disabled", False)):
            self._log("Torque is OFF. Click 'Torque ON' before running LLM tool calls.")
            return

        cmd = str(self.llm_input.text()).strip()
        if not cmd:
            return

        self._set_busy(True, "LLM")
        self._refresh_status()
        self._log(f"LLM command: {cmd}")

        enabled = sorted(self._get_enabled_llm_tools())
        self._log(f"LLM enabled tools: {enabled}")
        t = LLMThread(
            ui=self,
            llm_client=self._llm_client,
            model=str(self._selected_model),
            tools=self.tools,
            command=cmd,
            enabled_tool_names=enabled,
        )
        self._llm_thread = t
        t.log_line.connect(self._log)
        t.step_update.connect(self._on_llm_step)
        t.finished_ok.connect(lambda ok: (self._set_busy(False), self._refresh_status()))
        t.start()

    def _on_llm_step(self, step: int, max_steps: int) -> None:
        """Update activity label with LLM step progress."""
        self.activity_label.setText(f"● BUSY (LLM step {step}/{max_steps})")
        self.activity_label.setStyleSheet(
            "QLabel { color: #d29922; font-weight: bold; font-size: 14px; padding: 4px 10px; "
            "background-color: #3d3117; border-radius: 4px; }"
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            if self._camera_timer:
                self._camera_timer.stop()
        except Exception:
            pass

        try:
            if self._camera is not None and self._camera.is_connected:
                self._camera.disconnect()
        except Exception:
            pass

        try:
            self.tools.disconnect_robot()
        except Exception:
            pass

        super().closeEvent(event)

    def _torque_off(self) -> None:
        try:
            res = self.tools.disable_torque()
            self._log(json.dumps(res, indent=2))
            if bool(res.get("ok", False)):
                self._log("TORQUE OFF: motors are now limp (E-stop).")
        except Exception as e:
            self._log(f"TORQUE OFF failed: {e}")
        self._refresh_status()

    def _torque_on(self) -> None:
        try:
            res = self.tools.enable_torque()
            self._log(json.dumps(res, indent=2))
        except Exception as e:
            self._log(f"TORQUE ON failed: {e}")
        self._refresh_status()

    def _read_motor_diagnostics(self) -> None:
        try:
            diag = self.tools.read_motor_diagnostics()
            self._log(json.dumps(diag, indent=2))
        except Exception as e:
            self._log(f"Diagnostics failed: {e}")

    def _set_speed(self, value: float) -> None:
        try:
            self.tools.set_motor_speed(int(value))
            self._log(f"Motor speed set to {int(value)}")
        except Exception as e:
            self._log(f"Set speed failed: {e}")


def _parse_args() -> AppConfig:
    import argparse

    p = argparse.ArgumentParser(description="Chess Robot UI (LLM v2): camera + tool calls")
    p.add_argument("--port", required=False, help="Robot serial port (SO-101)")
    p.add_argument("--robot-id", default="so101_chess", help="Calibration id (default: so101_chess)")
    p.add_argument("--urdf", default=None, help="URDF path (or set SO101_URDF)")
    p.add_argument("--camera-index", type=int, default=0)
    p.add_argument("--camera-width", type=int, default=640)
    p.add_argument("--camera-height", type=int, default=480)
    p.add_argument("--camera-fps", type=int, default=30)
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.2"))
    p.add_argument("--api-key", default=None, help="OpenAI API key (or set OPENAI_API_KEY)")

    a = p.parse_args()
    return AppConfig(
        port=a.port,
        robot_id=str(a.robot_id),
        urdf_path=str(a.urdf) if a.urdf else None,
        camera_index=int(a.camera_index),
        camera_width=int(a.camera_width),
        camera_height=int(a.camera_height),
        camera_fps=int(a.camera_fps),
        model=str(a.model),
        api_key=str(a.api_key) if a.api_key else None,
    )


def main() -> None:
    cfg = _parse_args()

    app = QApplication([])
    ui = ChessRobotUILLMV2(cfg)
    ui.show()
    app.exec()


if __name__ == "__main__":
    main()
