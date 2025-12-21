#!/usr/bin/env python

"""Minimal robot test to verify motor communication works despite firmware mismatch."""

from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
from lerobot.robots.so101_follower.so101_follower import SO101Follower

def main():
    print("Testing minimal robot functionality...")
    
    cfg = SO101FollowerConfig(port="/dev/tty.usbmodem5A460825871", id="so101_chess", cameras={}, use_degrees=True)
    robot = SO101Follower(cfg)
    
    try:
        # Connect without calibration and bypass firmware check
        robot.bus._connect(handshake=False)
        robot.bus._assert_motors_exist()
        robot.configure()
        print("✓ Basic connection successful")
        
        # Try to read individual motor positions instead of sync read
        print("Testing individual motor reads...")
        for motor_name, motor in robot.bus.motors.items():
            try:
                pos = robot.bus.read("Present_Position", motor_name)
                print(f"  {motor_name}: {pos}")
            except Exception as e:
                print(f"  {motor_name}: ERROR - {e}")
        
        robot.bus.disconnect()
        print("✓ Test completed")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")

if __name__ == "__main__":
    main()

