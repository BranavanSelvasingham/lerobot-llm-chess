# Dual Camera Setup Guide for Chess Robot

This guide explains how to set up and configure the dual-camera system for your chess robot.

## Overview

Your chess robot now supports **two camera views**:

1. **Main Camera (Overview)** - iPhone or fixed overhead camera showing the entire setup
2. **Gripper Camera (Last Mile)** - USB camera mounted on the gripper for precision operations

## Hardware Setup

### Camera 1: Main Camera (iPhone)

You have **three options** for connecting your iPhone as the main camera:

#### Option A: USB Connection (Recommended for Simplicity)
1. Connect your iPhone to your computer via USB cable
2. On iPhone: Settings → Face ID & Passcode → Enable "USB Accessories" while locked
3. The iPhone should appear as a video device (usually at index 1 or 2)
4. **No additional software needed on iPhone**

#### Option B: Network Streaming (Better Quality, More Setup)
1. Install a camera streaming app on your iPhone:
   - **Recommended Apps:**
     - [Reincubate Camo](https://reincubate.com/camo/) - Professional, works great
     - [EpocCam](https://www.elgato.com/us/en/s/epoccam) - Free version available
     - [DroidCam OBS](https://www.dev47apps.com/) - Free alternative
   
2. For RTSP streaming (more advanced):
   - Install [RTSP Camera](https://apps.apple.com/app/rtsp-camera/id1507497817)
   - Note the RTSP URL shown in the app (e.g., `rtsp://192.168.1.100:8080/h264_ulaw.sdp`)

#### Option C: Use a Regular Webcam
- If you prefer simplicity, just use a regular USB webcam for the main view
- Mount it on a tripod or arm pointing at your chess setup

### Camera 2: Gripper Camera

1. **Hardware Requirements:**
   - Small USB camera module (OV5640 or similar)
   - Recommended: 640x480 resolution minimum
   - Wide angle lens (120-160°) preferred for better coverage
   - Example: $10-20 USB webcams from Amazon

2. **Physical Mounting:**
   - Attach camera to gripper housing or wrist
   - Point camera toward gripper fingers
   - Cable management: run USB cable along arm (use cable clips)
   - Consider using a flexible USB extension if needed

3. **Connection:**
   - Connect via USB to your computer
   - Will appear as video device (usually at index 1, or 2 if iPhone is index 1)

## Software Configuration

### Step 1: Find Your Camera Indices

Run this command to find available cameras:

```bash
python -c "import cv2; [print(f'Camera {i}: {cv2.VideoCapture(i).isOpened()}') for i in range(10)]"
```

Or use the lerobot camera finder:

```bash
lerobot find-cameras
```

### Step 2: Configure Camera Indices

Edit the camera configuration in your UI files (`chess_robot_ui.py` or `chess_robot_ui_llm.py`):

```python
def setup_camera(self):
    """Initialize camera connections for dual-camera setup."""
    
    # Main camera configuration
    main_camera_cfg = OpenCVCameraConfig(
        index_or_path=0,  # ← CHANGE THIS to your main camera index
        width=1280,
        height=720,
        fps=30
    )
    self.main_camera = OpenCVCamera(main_camera_cfg)
    
    # Gripper camera configuration
    gripper_camera_cfg = OpenCVCameraConfig(
        index_or_path=1,  # ← CHANGE THIS to your gripper camera index
        width=640,
        height=480,
        fps=30
    )
    self.gripper_camera = OpenCVCamera(gripper_camera_cfg)
```

### Common Camera Index Configurations:

| Setup | Main Camera | Gripper Camera |
|-------|-------------|----------------|
| Built-in + USB webcam | 0 | 1 |
| iPhone USB + USB webcam | 1 | 2 |
| USB webcam + USB webcam | 0 | 1 |
| RTSP stream + USB | "rtsp://..." | 1 |

### Step 3: Using iPhone with Network Streaming

If using RTSP streaming, replace the `index_or_path` with the RTSP URL:

```python
main_camera_cfg = OpenCVCameraConfig(
    index_or_path="rtsp://192.168.1.100:8080/h264_ulaw.sdp",  # Your iPhone's IP
    width=1280,
    height=720,
    fps=30
)
```

**Note:** Make sure your computer and iPhone are on the same WiFi network.

## Testing Your Setup

### Quick Test Script

Create a test file `test_dual_cameras.py`:

```python
#!/usr/bin/env python
import cv2
import time

# Test main camera
print("Testing main camera (index 0)...")
main_cam = cv2.VideoCapture(0)
if main_cam.isOpened():
    ret, frame = main_cam.read()
    if ret:
        cv2.imshow("Main Camera", frame)
        print("✅ Main camera working!")
    else:
        print("❌ Main camera failed to read frame")
else:
    print("❌ Main camera not detected")
main_cam.release()

cv2.waitKey(1000)

# Test gripper camera
print("\nTesting gripper camera (index 1)...")
gripper_cam = cv2.VideoCapture(1)
if gripper_cam.isOpened():
    ret, frame = gripper_cam.read()
    if ret:
        cv2.imshow("Gripper Camera", frame)
        print("✅ Gripper camera working!")
    else:
        print("❌ Gripper camera failed to read frame")
else:
    print("❌ Gripper camera not detected")
gripper_cam.release()

print("\nPress any key to close...")
cv2.waitKey(0)
cv2.destroyAllWindows()
```

Run it:
```bash
python test_dual_cameras.py
```

### Full System Test

Once cameras are configured, run the full UI:

```bash
# Standard UI
python chess_robot_ui.py --port /dev/ttyUSB0

# LLM UI
python chess_robot_ui_llm.py --port /dev/ttyUSB0
```

You should see:
- ✅ Main camera view in the top panel (larger)
- ✅ Gripper camera view in the bottom panel (smaller)
- ✅ FPS counters for both cameras

## Troubleshooting

### Problem: Camera not detected

**Solutions:**
1. Check USB connections are secure
2. Try different USB ports (USB 3.0 vs 2.0)
3. On Linux, check permissions: `ls -l /dev/video*`
4. Add your user to video group: `sudo usermod -a -G video $USER` (then logout/login)

### Problem: Wrong camera appears in wrong view

**Solution:** Swap the camera indices in `setup_camera()`:
```python
# Try swapping these values
main_camera_cfg = OpenCVCameraConfig(index_or_path=1, ...)  # Was 0
gripper_camera_cfg = OpenCVCameraConfig(index_or_path=0, ...)  # Was 1
```

### Problem: Low FPS or lag

**Solutions:**
1. Reduce camera resolution:
   ```python
   main_camera_cfg = OpenCVCameraConfig(
       index_or_path=0,
       width=640,   # Instead of 1280
       height=480,  # Instead of 720
       fps=30
   )
   ```

2. Lower frame rate:
   ```python
   fps=15  # Instead of 30
   ```

3. Check USB bandwidth (multiple cameras share bandwidth)
4. Use different USB controllers/hubs if possible

### Problem: iPhone keeps disconnecting

**Solutions:**
1. Disable iPhone auto-lock: Settings → Display & Brightness → Auto-Lock → Never
2. Keep iPhone plugged into power
3. Disable "Low Power Mode"
4. Use a high-quality USB cable
5. For network streaming: ensure stable WiFi connection

### Problem: Gripper camera cable gets in the way

**Solutions:**
1. Use thin, flexible USB extension cables
2. Route cable along robot arm segments
3. Add strain relief at connection points
4. Consider wireless USB camera adapters (more expensive)
5. Use cable clips or zip ties for cable management

## Camera Positioning Tips

### Main Camera (Overview)
- **Height:** 30-50cm above chess board
- **Angle:** Slightly angled (15-30° from vertical)
- **Field of View:** Should capture entire 8x8 board + robot arm workspace
- **Lighting:** Ensure even lighting, avoid shadows from robot

### Gripper Camera
- **Position:** 2-5cm above gripper fingers
- **Angle:** Pointing down at gripper center
- **Field of View:** Should see gripper tips + ~5cm radius around them
- **Focus:** Set to close focus (if adjustable)

## Advanced Configuration

### Using Multiple iPhone Cameras (Front + Back)

If your iPhone camera app supports it:
```python
# Back camera (higher quality)
main_camera_cfg = OpenCVCameraConfig(index_or_path=1, ...)

# Front camera (if also exposed)
gripper_camera_cfg = OpenCVCameraConfig(index_or_path=2, ...)
```

### Network Streaming with Custom Settings

For advanced users, you can use custom RTSP parameters:
```python
import cv2

# Create capture with custom options
cap = cv2.VideoCapture("rtsp://192.168.1.100:8080/h264_ulaw.sdp")
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce latency
cap.set(cv2.CAP_PROP_FPS, 30)
```

### Recording Both Camera Streams

Add this to your monitoring thread to record:
```python
# In MonitoringThread.run()
main_writer = cv2.VideoWriter('main_camera.mp4', 
                               cv2.VideoWriter_fourcc(*'mp4v'),
                               30, (1280, 720))
gripper_writer = cv2.VideoWriter('gripper_camera.mp4',
                                  cv2.VideoWriter_fourcc(*'mp4v'),
                                  30, (640, 480))

# In the loop
main_writer.write(frame)
gripper_writer.write(frame)

# When done
main_writer.release()
gripper_writer.release()
```

## Performance Optimization

### Recommended Settings for Smooth Operation

| Camera | Resolution | FPS | Use Case |
|--------|-----------|-----|----------|
| Main | 1280x720 | 30 | Good balance |
| Main | 1920x1080 | 15 | High quality, slower |
| Main | 640x480 | 30 | Fast, lower quality |
| Gripper | 640x480 | 30 | Standard |
| Gripper | 320x240 | 30 | Very fast, adequate |

### System Requirements

- **CPU:** Multi-core processor (4+ cores recommended)
- **RAM:** 4GB minimum, 8GB recommended
- **USB:** USB 3.0 ports preferred
- **OS:** Linux (Ubuntu 20.04+), macOS 11+, Windows 10+

## Next Steps

1. **Test each camera independently** using the test script
2. **Find correct camera indices** for your setup
3. **Update the configuration** in your UI files
4. **Mount the gripper camera** securely
5. **Position the main camera** for best overview
6. **Run the full UI** and verify both feeds work
7. **Adjust resolution/FPS** if needed for performance

## Need Help?

If you encounter issues:
1. Check camera indices with `lerobot find-cameras`
2. Test cameras independently
3. Verify USB connections and permissions
4. Check system resources (CPU, USB bandwidth)
5. Review error messages in terminal output

---

**Last Updated:** December 2025  
**Compatible with:** lerobot v2.0+, chess_robot_ui.py, chess_robot_ui_llm.py




