"""Normal TurtleBot3 bring-up plus the battery monitor for the tmux status bar. Run on the ROBOT.

    ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py

Use bringup_ekf.launch.py instead for the EKF odometry; it starts the battery monitor too.
Never run two bring-ups at once.

With the LDS-01 the LiDAR runs on the robust driver (lidar_driver:=stock for the stock one).
With the RPLiDAR A1M8 (LDS_MODEL=RPLIDAR-A1) it runs on rplidar_ros.
gamepad:=true also starts the gamepad teleop (gamepad.launch.py).
"""

import os
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot_common import gamepad_actions, lidar_arguments  # noqa: E402

ROBOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_launch_description():
    bringup = get_package_share_directory('turtlebot3_bringup')
    lidar_declarations, lidar_launch_arguments = lidar_arguments()

    return LaunchDescription([
        *lidar_declarations,
        *gamepad_actions(),
        DeclareLaunchArgument('usb_port', default_value='/dev/ttyACM0',
                              description='Connected USB port with OpenCR'),
        DeclareLaunchArgument('warn_voltage', default_value='11.0',
                              description='Battery voltage [V] below which the tmux status turns yellow'),
        DeclareLaunchArgument('critical_voltage', default_value='10.5',
                              description='Battery voltage [V] below which the tmux status turns red'),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, 'launch', 'robot.launch.py')),
            launch_arguments={'usb_port': LaunchConfiguration('usb_port'),
                              **lidar_launch_arguments}.items()),

        ExecuteProcess(
            cmd=['python3', os.path.join(ROBOT_DIR, 'battery_status.py'), '--ros-args',
                 '-p', ['warn_voltage:=', LaunchConfiguration('warn_voltage')],
                 '-p', ['critical_voltage:=', LaunchConfiguration('critical_voltage')]],
            output='screen'),
    ])
