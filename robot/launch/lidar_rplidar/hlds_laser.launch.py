"""Stand-in for hls_lfcd_lds_driver's hlds_laser.launch.py that starts the RPLiDAR A1M8 (rplidar_ros).

turtlebot3_bringup's robot.launch.py includes <lidar_pkg_dir>/hlds_laser.launch.py with the arguments
port, frame_id and namespace. robot_common.py points lidar_pkg_dir at this directory when
LDS_MODEL=RPLIDAR-A1. The file keeps the name hlds_laser.launch.py because that is the one
robot.launch.py asks for.

The A1M8 talks 115200 baud (A2M7, A3 and S1 use 256000). The scan is published on /scan.
"""

import os

from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def driver_executable():
    """The same node is installed as rplidar_node (upstream 2.1.4) or only as rplidar_composition
    (older binary builds); use whichever the installed package has."""
    libexec = os.path.join(get_package_prefix('rplidar_ros'), 'lib', 'rplidar_ros')
    for name in ('rplidar_node', 'rplidar_composition'):
        if os.path.exists(os.path.join(libexec, name)):
            return name
    return 'rplidar_node'


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('frame_id', default_value='base_scan'),
        DeclareLaunchArgument('namespace', default_value='', description='accepted and ignored'),

        Node(package='rplidar_ros', executable=driver_executable(), name='rplidar_node', output='screen',
             parameters=[{'channel_type': 'serial',
                          'serial_port': LaunchConfiguration('port'),
                          'serial_baudrate': 115200,
                          'frame_id': LaunchConfiguration('frame_id'),
                          'inverted': False,
                          'angle_compensate': True}]),
    ])
