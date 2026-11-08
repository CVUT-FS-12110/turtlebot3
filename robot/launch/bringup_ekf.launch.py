"""Kept for old commands: the same as bringup.launch.py ekf:=true. Run on the ROBOT.

    ros2 launch ~/turtlebot3-setup/robot/launch/bringup_ekf.launch.py

Other arguments (gamepad:=true, usb_port:=..., lidar_yaw:=...) are passed on.
"""

import os

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    here = os.path.dirname(os.path.abspath(__file__))
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(here, 'bringup.launch.py')),
            launch_arguments={'ekf': 'true'}.items()),
    ])
