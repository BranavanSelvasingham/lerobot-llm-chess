# 🔍 Vision-Enabled LLM Control Guide

## Overview

Your chess robot now has **vision-enabled LLM control**! The LLM can now see the camera feeds and make more intelligent decisions based on visual information.

## ✨ Features

### 1. **Camera Image Sending**
- Send screenshots from main camera, gripper camera, or both
- Automatic image resizing and optimization
- Base64 encoding for API transmission

### 2. **Vision-Capable Models**
Models marked with 👁️ support vision:
- **GPT-5 series** (gpt-5.1, gpt-5-mini, gpt-5-nano) 👁️
- **GPT-4.1 series** (gpt-4.1, gpt-4.1-mini) 👁️
- **GPT-4o** (gpt-4o, gpt-4o-mini) 👁️
- **GPT-4 Turbo** (gpt-4-turbo) 👁️
- **GPT-4 Vision** (gpt-4-vision-preview) 👁️

### 3. **Auto-Update Mode**
- Periodic scene analysis
- Configurable update frequency (5-60 seconds)
- Automatic monitoring and recommendations

### 4. **Image Quality Control**
- Adjustable resolution (512x512, 768x768, 1024x1024, or original)
- Lower resolution = faster processing + lower cost
- Higher resolution = better detail recognition

## 🎯 Usage

### Basic Vision Control

1. **Enable Vision**
   - Check "Enable Vision (Send Images to LLM)"
   - Vision status indicator will show "📷 Vision ready"

2. **Select Camera Source**
   - **Main Camera**: Overview of entire board (recommended)
   - **Gripper Camera**: Close-up of gripper action
   - **Both Cameras**: Send both views for maximum context

3. **Choose Image Resolution**
   - **512x512**: Fast, lower cost, adequate for most tasks
   - **768x768**: ✅ Recommended balance
   - **1024x1024**: High detail, slower, more expensive
   - **Original**: Full camera resolution (use sparingly)

4. **Send Commands with Vision**
   ```
   Example: "What pieces do you see on the board? Which one should I pick up?"
   
   The LLM will analyze the camera image and respond based on what it sees.
   ```

### Auto-Update Mode

Enable periodic scene analysis:

1. **Check "Auto-update"**
2. **Set interval** (default: 10 seconds)
3. **LLM will periodically analyze the scene**
   - Identifies pieces
   - Suggests moves
   - Monitors for issues
   - Provides recommendations

**Use Cases:**
- Continuous board monitoring
- Piece position verification
- Anomaly detection
- Game progress tracking

## 📊 Vision-Enhanced Commands

### Example Commands

**Board Analysis:**
```
"What's the current board state?"
"Which pieces are on the board?"
"What color pieces do you see?"
```

**Piece Recognition:**
```
"Identify the piece at e4"
"What piece is under the gripper?"
"Is there a piece at d5?"
```

**Movement Guidance:**
```
"Move the gripper to the white queen"
"Pick up the piece you see at the center"
"Move to the nearest black pawn"
```

**Validation:**
```
"Verify the piece is properly grasped"
"Check if the piece was placed correctly"
"Is the gripper aligned with the piece?"
```

## ⚙️ Configuration

### Vision Settings Panel

Located in the LLM Control panel:

```
┌─ Enable Vision ────────────────────────┐
│ ☑ Enable Vision (Send Images to LLM)  │
│                                        │
│ Camera: [Main Camera     ▼]           │
│ Resolution: [768x768     ▼]           │
│                                        │
│ ☐ Auto-update    Every: [10 ▼] sec   │
│                                        │
│ 📷 Vision ready (capable model)        │
└────────────────────────────────────────┘
```

### Camera Selection Guide

| Camera | Best For | Field of View |
|--------|----------|---------------|
| **Main Camera** | Board overview, piece identification | Entire 8×8 board |
| **Gripper Camera** | Grasp verification, precise alignment | Gripper + 5cm radius |
| **Both Cameras** | Maximum context, complex tasks | Complete scene |

### Resolution Guide

| Resolution | Token Cost* | Speed | Best For |
|------------|-------------|-------|----------|
| 512x512 | ~85 tokens | Fast | Quick checks |
| 768x768 | ~170 tokens | Medium | ✅ Most tasks |
| 1024x1024 | ~255 tokens | Slow | Detailed analysis |
| Original | Varies | Slowest | Special cases |

*Approximate tokens for GPT-4V/GPT-4o

## 💰 Cost Considerations

### Token Usage

**Vision requests use more tokens:**
- Text-only: ~100-500 tokens
- With image (768x768): ~170 + text tokens
- With 2 images: ~340 + text tokens

**Cost examples (GPT-4o):**
- Text command: ~$0.0005
- With 1 image: ~$0.002
- With 2 images: ~$0.004

### Cost Optimization Tips

1. **Use appropriate resolution**
   - 512x512 for simple checks
   - 768x768 for normal use
   - 1024x1024 only when needed

2. **Select minimal cameras**
   - Use main camera for most tasks
   - Only use both cameras when necessary

3. **Auto-update frequency**
   - 10-15 seconds for normal monitoring
   - 30-60 seconds for passive observation
   - Disable when not needed

## 🔧 Technical Details

### Image Capture Process

```python
def capture_camera_image(camera_source):
    1. Read frame from selected camera(s)
    2. Resize to target resolution
    3. Convert BGR → RGB
    4. Encode to JPEG (90% quality)
    5. Encode to base64
    6. Return encoded string
```

### Vision API Format

**Text-only message:**
```json
{
  "role": "user",
  "content": "Move arm to e2"
}
```

**Vision message:**
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "Move arm to e2"},
    {"type": "image_url", "image_url": {
      "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
      "detail": "high"
    }}
  ]
}
```

## 📋 Best Practices

### 1. Model Selection

✅ **Do:**
- Use GPT-4o or GPT-4o-mini for vision (good balance)
- Use GPT-5 models for best accuracy
- Check for 👁️ icon to confirm vision support

❌ **Don't:**
- Use o1/o3/o4 models (no vision support)
- Use gpt-3.5-turbo for vision

### 2. Command Formulation

✅ **Do:**
```
"Look at the board and identify all pieces"
"What piece is under the gripper?"
"Check if the piece is properly placed"
```

❌ **Don't:**
```
"Move to e4" (without visual context - works but doesn't use vision)
```

### 3. Resolution Selection

- **Quick verification:** 512x512
- **Normal commands:** 768x768 ✅
- **Detailed analysis:** 1024x1024
- **Avoid original resolution** unless absolutely needed

### 4. Auto-Update

✅ **Good use cases:**
- Long-running games
- Monitoring during manual moves
- Learning/training sessions

❌ **Avoid when:**
- Actively controlling robot
- Short sessions
- Cost-sensitive scenarios

## 🐛 Troubleshooting

### Vision Not Working

**Symptom:** "⚠️ Selected model may not support vision"

**Solution:**
1. Select a model with 👁️ icon
2. Recommended: gpt-4o or gpt-4o-mini
3. Check model availability with your API key

### Image Capture Failed

**Symptom:** "⚠️ Image capture failed"

**Solutions:**
1. Check camera connections
2. Verify cameras are running in monitoring thread
3. Check camera status indicators
4. Restart UI if needed

### High Costs

**Solutions:**
1. Reduce resolution to 512x512
2. Use main camera only
3. Increase auto-update interval
4. Disable auto-update when not needed
5. Use gpt-4o-mini instead of gpt-4o

### Slow Response

**Solutions:**
1. Reduce image resolution
2. Use single camera instead of both
3. Check internet connection
4. Try gpt-4o-mini for faster inference

## 🎓 Example Workflows

### Workflow 1: Piece Identification

```
1. Enable vision: ☑
2. Camera: Main Camera
3. Resolution: 768x768
4. Command: "What pieces are on the board? List their positions."
5. LLM response: 
   "I can see:
   - White king at e1
   - White queen at d1
   - Black knight at g8
   ..."
```

### Workflow 2: Grasp Verification

```
1. Enable vision: ☑
2. Camera: Gripper Camera
3. Resolution: 512x512
4. Move gripper over piece
5. Command: "Is the piece properly aligned with the gripper?"
6. LLM response: 
   "Yes, the white pawn is centered under the gripper.
   The gripper is at the correct height for pickup."
```

### Workflow 3: Continuous Monitoring

```
1. Enable vision: ☑
2. Camera: Main Camera
3. Resolution: 768x768
4. Auto-update: ☑ Every 15 sec
5. LLM periodically analyzes and reports:
   - Board state changes
   - Piece movements
   - Anomalies
   - Suggestions
```

## 📚 Related Documentation

- **DUAL_CAMERA_SETUP.md** - Camera hardware setup
- **DUAL_CAMERA_QUICKSTART.md** - Quick start guide
- **chess_robot_ui_llm.py** - Implementation code

## 🎉 Next Steps

1. **Test vision with simple commands**
   ```bash
   python chess_robot_ui_llm.py --port /dev/ttyUSB0
   ```

2. **Enable vision and try:**
   - "What pieces do you see?"
   - "Describe the board state"
   - "What's at position e4?"

3. **Experiment with settings:**
   - Try different resolutions
   - Test both cameras
   - Enable auto-update

4. **Integrate into gameplay:**
   - Use vision for move validation
   - Verify piece placement
   - Monitor game progress

---

**Status:** ✅ Vision integration complete  
**Version:** 1.0  
**Date:** December 2025

**Supported Models:**
- GPT-5.1, GPT-5-mini, GPT-5-nano 👁️
- GPT-4.1, GPT-4.1-mini, GPT-4.1-nano 👁️
- GPT-4o, GPT-4o-mini 👁️
- GPT-4-turbo, GPT-4-vision-preview 👁️





