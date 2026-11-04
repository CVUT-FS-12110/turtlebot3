"""Stand-in for hls_lfcd_lds_driver's hlds_laser.launch.py that starts the RPLiDAR A1M8 (rplidar_ros).

turtlebot3_bringup's robot.launch.py includes <lidar_pkg_dir>/hlds_laser.launch.py with the arguments
port, frame_id and namespace. robot_common.py points lidar_pkg_dir at this directory when
LDS_MODEL=RPLIDAR-A1. The file keeps the name hlds_laser.launch.py because that is the one
robot.launch.py asks for.

The A1M8 talks 115200 baud (A2M7, A3 and S1 use 256000). The scan is published on /scan.

Mounting: the sensor's zero angle is along the arrow on its body. On this robot the sensor sits turned
by 180 degrees (arrow pointing backwards), so the scan is published in a frame <frame_id>_rplidar that
is turned by lidar_yaw radians (default pi) against base_scan. With a wrong angle, SLAM sees the walls
move with the robot. If the arrow points forward, use lidar_yaw:=0.
"""

import os

from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def driver_executable():
    """The same node is installed as rplidar_node (upstream 2.1.4) or only as rplidar_composition
    (older binary builds, as on the robot); use whichever the installed package has."""
    libexec = os.path.join(get_package_prefix('rplidar_ros'), 'lib', 'rplidar_ros')
    for name in ('rplidar_node', 'rplidar_composition'):
        if os.path.exists(os.path.join(libexec, name)):
            return name
    return 'rplidar_node'


def generate_launch_description():
    frame = LaunchConfiguration('frame_id')
    scan_frame = [frame, '_rplidar']

    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('frame_id', default_value='base_scan'),
        DeclareLaunchArgument('namespace', default_value='', description='accepted and ignored'),
        DeclareLaunchArgument('lidar_yaw', default_value='3.14159265',
                              description='Rotation of the sensor against base_scan [rad]: '
                                          '3.14159265 = arrow pointing backwards, 0 = forwards'),

        Node(package='tf2_ros', executable='static_transform_publisher', name='rplidar_mount_tf',
             arguments=['--yaw', LaunchConfiguration('lidar_yaw'),
                        '--frame-id', frame, '--child-frame-id', scan_frame]),

        Node(package='rplidar_ros', executable=driver_executable(), name='rplidar_node', output='screen',
             parameters=[{'channel_type': 'serial',
                          'serial_port': LaunchConfiguration('port'),
                          'serial_baudrate': 115200,
                          'frame_id': ParameterValue(scan_frame, value_type=str),
                          'inverted': False,
                          'angle_compensate': True}]),
    ])
