"""Stand-in for hls_lfcd_lds_driver's hlds_laser.launch.py that starts the robust LDS-01 driver.

turtlebot3_bringup's robot.launch.py includes <lidar_pkg_dir>/hlds_laser.launch.py with the arguments
port, frame_id and namespace. bringup.launch.py points lidar_pkg_dir at this directory.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration

DRIVER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      'lds01_driver.py')


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('frame_id', default_value='base_scan'),
        DeclareLaunchArgument('namespace', default_value='', description='accepted and ignored'),
        ExecuteProcess(
            cmd=['python3', '-u', DRIVER, '--ros-args',
                 '-p', ['port:=', LaunchConfiguration('port')],
                 '-p', ['frame_id:=', LaunchConfiguration('frame_id')]],
            output='screen'),
    ])
