"""Shared by bringup.launch.py and bringup_ekf.launch.py."""

import os

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression

ROBOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gamepad_actions():
    """`gamepad:=true` also starts gamepad.launch.py (its own arguments, such as enable_button:=4, can
    be given on the same command line)."""
    return [
        DeclareLaunchArgument('gamepad', default_value='false',
                              description='true: also start the gamepad teleop (see gamepad.launch.py)'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(ROBOT_DIR, 'launch', 'gamepad.launch.py')),
            condition=IfCondition(LaunchConfiguration('gamepad'))),
    ]


def lidar_arguments():
    """Return (launch arguments to declare, extra launch_arguments for robot.launch.py).

    robot.launch.py includes <lidar_pkg_dir>/hlds_laser.launch.py, so lidar_pkg_dir is pointed at a
    folder of this repository:
      - LDS_MODEL=RPLIDAR-A1: robot/launch/lidar_rplidar (rplidar_ros). robot.launch.py does not know
        this model and would start the LDS-01 driver on the same port.
      - LDS-01: robot/launch/lidar, the robust driver instead of hlds_laser_publisher;
        `lidar_driver:=stock` brings the stock driver back.
    Other LiDAR models are left alone.
    """
    declare = DeclareLaunchArgument(
        'lidar_driver', default_value='robust',
        description="LDS-01 driver: 'robust' (survives lost bytes) or 'stock' (hls_lfcd_lds_driver); "
                    "ignored with other LiDARs")
    model = os.environ.get('LDS_MODEL', 'LDS-01')
    if model == 'RPLIDAR-A1':
        return [declare], {'lidar_pkg_dir': os.path.join(ROBOT_DIR, 'launch', 'lidar_rplidar')}
    if model != 'LDS-01':
        return [declare], {}
    try:
        stock = os.path.join(get_package_share_directory('hls_lfcd_lds_driver'), 'launch')
    except PackageNotFoundError:
        return [declare], {}
    robust = os.path.join(ROBOT_DIR, 'launch', 'lidar')
    chosen = PythonExpression(["'", robust, "' if '", LaunchConfiguration('lidar_driver'),
                               "' == 'robust' else '", stock, "'"])
    return [declare], {'lidar_pkg_dir': chosen}
