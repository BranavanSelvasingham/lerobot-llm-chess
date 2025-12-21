# 🚀 Dual Camera Setup - Quick Start

## ✅ What's Done

Your chess robot UI now has **full dual-camera support**:

- ✅ **Main Camera** - Overview of entire chess board
- ✅ **Gripper Camera** - Close-up for precision control
- ✅ **Updated UI** - Both camera feeds displayed
- ✅ **Test Script** - Easy camera identification
- ✅ **Documentation** - Complete setup guides

## 📋 Next Steps (3 Minutes)

### 1️⃣ Find Your Cameras

```bash
python test_dual_cameras.py
```

This will show you something like:
```
✅ Camera 0: Available (1280x720)   ← Your laptop camera
✅ Camera 1: Available (640x480)    ← Your USB webcam
```

### 2️⃣ Update Configuration

Edit `chess_robot_ui.py` (or `chess_robot_ui_llm.py`) around line ~730:

```python
def setup_camera(self):
    # Main camera
    main_camera_cfg = OpenCVCameraConfig(
        index_or_path=0,  # ← Use the index from step 1
        ...
    )
    
    # Gripper camera
    gripper_camera_cfg = OpenCVCameraConfig(
        index_or_path=1,  # ← Use the index from step 1
        ...
    )
```

### 3️⃣ Run Your Robot UI

```bash
python chess_robot_ui.py --port /dev/ttyUSB0
```

You should see:
- ✅ Top panel: Main camera feed (larger)
- ✅ Bottom panel: Gripper camera feed (smaller)
- ✅ FPS counters for both cameras

## 📚 Full Documentation

| Document | Purpose |
|----------|---------|
| **DUAL_CAMERA_SETUP.md** | Complete setup guide (iPhone, USB, RTSP) |
| **DUAL_CAMERA_CHANGES.md** | Summary of code changes |
| **camera_setup_diagram.txt** | Visual diagrams of setup |
| **test_dual_cameras.py** | Camera testing utility |

## 🔧 Common Camera Setups

### Setup A: Laptop + USB Webcam
```python
index_or_path=0  # Laptop built-in camera (main)
index_or_path=1  # USB webcam (gripper)
```

### Setup B: iPhone USB + USB Webcam
```python
index_or_path=1  # iPhone via USB (main)
index_or_path=2  # USB webcam (gripper)
```

### Setup C: iPhone Network + USB Webcam
```python
index_or_path="rtsp://192.168.1.100:8080/..."  # iPhone RTSP (main)
index_or_path=1  # USB webcam (gripper)
```

### Setup D: Two USB Webcams
```python
index_or_path=0  # First USB webcam (main)
index_or_path=1  # Second USB webcam (gripper)
```

## ⚡ Performance Tips

**For Best Performance:**
- Main camera: 1280x720 @ 30fps
- Gripper camera: 640x480 @ 30fps
- Use USB 3.0 ports
- Ensure good lighting

**If Lagging:**
1. Reduce main camera resolution to 640x480
2. Lower FPS to 15fps
3. Check CPU usage
4. Try different USB ports

## 🚨 Troubleshooting

### Problem: Cameras not detected
```bash
# Linux: Check permissions
ls -l /dev/video*
sudo usermod -a -G video $USER
# Then logout/login
```

### Problem: Wrong camera in wrong view
Swap the indices in your config:
```python
# Before
main: index_or_path=0
gripper: index_or_path=1

# Try
main: index_or_path=1
gripper: index_or_path=0
```

### Problem: Only one camera works
- Check both cameras are plugged in
- Run `test_dual_cameras.py` again
- Try different USB ports
- Check USB bandwidth (use different USB controllers)

## 📱 iPhone Setup (Optional)

### Quick USB Method:
1. Connect iPhone via USB
2. Enable USB accessories in Settings
3. iPhone should appear as camera index 1 or 2

### Network Streaming Method:
1. Install [Reincubate Camo](https://reincubate.com/camo/) on iPhone
2. Connect to same WiFi as computer
3. App will show camera device or RTSP URL
4. Use that in your config

## 🎯 Hardware Mounting Tips

### Main Camera:
- Mount 30-50cm above board
- Angle slightly (15-30°)
- Should see entire 8×8 board + robot arm

### Gripper Camera:
- Attach 2-5cm above gripper fingers
- Point straight down
- Use cable clips along robot arm
- Wide angle lens (120-160°) preferred

## ✨ What You Get

### Main Camera Benefits:
- See entire board state
- Monitor robot arm movement
- Plan trajectories
- Safety monitoring
- Better piece detection

### Gripper Camera Benefits:
- Precise piece alignment
- Verify successful grasp
- Confirm placement
- Detect failures early
- Fine-tune positioning

## 📞 Need Help?

1. **Read detailed guide:** [DUAL_CAMERA_SETUP.md](DUAL_CAMERA_SETUP.md)
2. **Test cameras:** `python test_dual_cameras.py`
3. **Check indices:** `lerobot find-cameras`
4. **View diagrams:** `cat camera_setup_diagram.txt`

## 🎉 You're Ready!

Once you see both camera feeds in the UI, you're all set! The dual-camera system will give you much better control over your chess robot, especially for precise piece manipulation.

---

**Files Modified:**
- ✅ `chess_robot_ui.py`
- ✅ `chess_robot_ui_llm.py`

**Files Created:**
- 📄 `DUAL_CAMERA_SETUP.md` (detailed guide)
- 📄 `DUAL_CAMERA_CHANGES.md` (implementation summary)
- 📄 `DUAL_CAMERA_QUICKSTART.md` (this file)
- 📄 `camera_setup_diagram.txt` (visual diagrams)
- 🧪 `test_dual_cameras.py` (test utility)

**Status:** ✅ Complete and tested  
**Version:** 1.0  
**Date:** December 2025




