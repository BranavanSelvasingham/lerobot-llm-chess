#!/usr/bin/env python

"""Gentle demo with small movements to avoid overload errors."""

import time
import argparse

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower

def gentle_demo(port: str):
    """Demo with very small, safe movements."""
    
    robot_cfg = SO101FollowerConfig(port=port, id="so101_chess", cameras={}, use_degrees=True)
    robot = SO101Follower(robot_cfg)
    
    try:
        robot.bus._connect(handshake=False)
        robot.bus._assert_motors_exist()
        robot.configure()
        print("✓ Connected to SO-101")
        
        print("Demo: Gentle gripper and small wrist movements...")
        
        # 1. Gentle gripper test
        print("1. Opening gripper...")
        robot.bus.write("Goal_Position", "gripper", 5.0)
        time.sleep(2)
        
        print("2. Closing gripper...")
        robot.bus.write("Goal_Position", "gripper", 50.0)
        time.sleep(2)
        
        # 2. Small wrist movements only (safest joints)
        print("3. Small wrist roll...")
        robot.bus.write("Goal_Position", "wrist_roll", 10.0)
        time.sleep(2)
        
        robot.bus.write("Goal_Position", "wrist_roll", -10.0)
        time.sleep(2)
        
        robot.bus.write("Goal_Position", "wrist_roll", 0.0)
        time.sleep(2)
        
        print("4. Opening gripper to finish...")
        robot.bus.write("Goal_Position", "gripper", 5.0)
        time.sleep(2)
        
        print("✓ Gentle demo completed successfully!")
        print("\nThis proves your SO-101 is working and ready for chess!")
        print("Next: Set up proper calibration and board detection for full chess moves.")
        
    except Exception as e:
        print(f"Demo failed: {e}")
    finally:
        try:
            robot.bus.disconnect()
        except:
            pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    gentle_demo(args.port)

if __name__ == "__main__":
    main()








