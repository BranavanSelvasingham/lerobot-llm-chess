# 🚀 Vision LLM - Quick Start (2 Minutes)

## What's New

Your LLM can now **see the camera feeds**! 👁️

## Quick Start

### 1️⃣ Select a Vision Model

In the LLM Control panel, select a model with 👁️ icon:
- **gpt-4o** 👁️ (recommended)
- **gpt-4o-mini** 👁️ (faster, cheaper)
- **gpt-5.1** 👁️ (best quality)

### 2️⃣ Enable Vision

```
☑ Enable Vision (Send Images to LLM)
Camera: Main Camera
Resolution: 768x768 ✅ (recommended)
```

### 3️⃣ Try Vision Commands

**Ask what the LLM sees:**
```
"What pieces are on the board?"
"Describe the current board state"
"What's at position e4?"
```

**Request actions based on vision:**
```
"Move to the white queen"
"Pick up the piece you see at center"
"Check if the piece is properly grasped"
```

## Settings

### Camera Selection
- **Main Camera**: See entire board (best for most commands)
- **Gripper Camera**: Close-up view (for grasp verification)
- **Both Cameras**: Maximum context

### Resolution (Cost vs Quality)
- **512x512**: Fast & cheap
- **768x768**: ✅ **Recommended**
- **1024x1024**: High detail
- **Original**: Use sparingly

### Auto-Update (Optional)
```
☑ Auto-update    Every: [10] sec
```
LLM will periodically analyze the scene and provide insights.

## Cost

**Approximate costs per request:**
- Text-only: $0.0005
- With image (768x768): $0.002
- With 2 images: $0.004

**Tip:** Use 512x512 for quick checks, 768x768 for normal use.

## Quick Tips

✅ **Do:**
- Use gpt-4o or gpt-4o-mini for vision
- Start with main camera + 768x768
- Ask visual questions ("What do you see?")

❌ **Don't:**
- Use o1/o3/o4 models (no vision)
- Use original resolution unless needed
- Enable auto-update for short sessions

## Example Session

```bash
# Start UI with LLM control
python chess_robot_ui_llm.py --port /dev/ttyUSB0
```

**In the UI:**
1. Select "gpt-4o 👁️"
2. Check "Enable Vision"
3. Type: "What pieces are on the chess board?"
4. Click "Execute"
5. LLM analyzes image and responds!

## Full Documentation

For complete details:
- **VISION_LLM_GUIDE.md** - Complete guide
- **DUAL_CAMERA_SETUP.md** - Camera setup

---

**Status:** ✅ Ready to use  
**Time to first vision command:** < 2 minutes




