"""TurtleBot3 bring-up with the EKF odometry and the battery monitor for the tmux status bar. Run on the ROBOT.

    ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py

ekf:=true (default) switches off the odom -> base_footprint transform of turtlebot3_node and starts the
covariance fixer and robot_localization's ekf_node, which publish it instead (docs/ekf.md).
ekf:=false is the plain bring-up. Never run two bring-ups at once.

With the LDS-01 the LiDAR runs on the robust driver (lidar_driver:=stock for the stock one).
With the RPLiDAR A1M8 (LDS_MODEL=RPLIDAR-A1) it runs on rplidar_ros.
gamepad:=true also starts the gamepad teleop (gamepad.launch.py).
"""

import os
import sys

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot_common import gamepad_actions, lidar_arguments, robot_actions  # noqa: E402

ROBOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_launch_description():
    lidar_declarations, lidar_launch_arguments = lidar_arguments()

    return LaunchDescription([
        *lidar_declarations,
        *gamepad_actions(),
        DeclareLaunchArgument('ekf', default_value='true',
                              description='true: odometry filtered by the EKF (wheels + gyro); false: plain'),
        DeclareLaunchArgument('usb_port', default_value='/dev/ttyACM0',
                              description='Connected USB port with OpenCR'),
        DeclareLaunchArgument('warn_voltage', default_value='11.0',
                              description='Battery voltage [V] below which the tmux status turns yellow'),
        DeclareLaunchArgument('critical_voltage', default_value='10.5',
                              description='Battery voltage [V] below which the tmux status turns red'),

        OpaqueFunction(function=robot_actions, args=[lidar_launch_arguments]),

        ExecuteProcess(
            cmd=['python3', os.path.join(ROBOT_DIR, 'battery_status.py'), '--ros-args',
                 '-p', ['warn_voltage:=', LaunchConfiguration('warn_voltage')],
                 '-p', ['critical_voltage:=', LaunchConfiguration('critical_voltage')]],
            output='screen'),
    ])
