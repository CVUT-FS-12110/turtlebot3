"""Shared by bringup.launch.py and bringup_ekf.launch.py."""

import os

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression

ROBOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lidar_arguments():
    """Return (launch arguments to declare, extra launch_arguments for robot.launch.py).

    With the LDS-01 the robust driver replaces hlds_laser_publisher: robot.launch.py includes
    <lidar_pkg_dir>/hlds_laser.launch.py, and lidar_pkg_dir is pointed at robot/launch/lidar.
    `lidar_driver:=stock` brings the stock driver back. Other LiDAR models are left alone.
    """
    declare = DeclareLaunchArgument(
        'lidar_driver', default_value='robust',
        description="LDS-01 driver: 'robust' (survives lost bytes) or 'stock' (hls_lfcd_lds_driver)")
    if os.environ.get('LDS_MODEL', 'LDS-01') != 'LDS-01':
        return [declare], {}
    try:
        stock = os.path.join(get_package_share_directory('hls_lfcd_lds_driver'), 'launch')
    except PackageNotFoundError:
        return [declare], {}
    robust = os.path.join(ROBOT_DIR, 'launch', 'lidar')
    chosen = PythonExpression(["'", robust, "' if '", LaunchConfiguration('lidar_driver'),
                               "' == 'robust' else '", stock, "'"])
    return [declare], {'lidar_pkg_dir': chosen}
