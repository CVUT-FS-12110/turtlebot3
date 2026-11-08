"""Shared by bringup.launch.py and bringup_ekf.launch.py."""

import os
import re
import tempfile

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

ROBOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def params_without_odom_tf(model):
    """Copy the installed bring-up parameters with odometry.publish_tf turned off."""
    source = os.path.join(get_package_share_directory('turtlebot3_bringup'), 'param', f'{model}.yaml')
    with open(source, encoding='utf-8') as f:
        text, count = re.subn(r'publish_tf:\s*true', 'publish_tf: false', f.read())
    if count == 0:
        raise RuntimeError(f'{source} has no "publish_tf: true" to switch off; was it changed upstream?')
    target = os.path.join(tempfile.mkdtemp(prefix='tb3_ekf_'), f'{model}.yaml')
    with open(target, 'w', encoding='utf-8') as f:
        f.write(text)
    return target


def robot_actions(context, lidar_launch_arguments):
    """turtlebot3_bringup robot.launch.py; with ekf:=true without its odom TF, plus the EKF that publishes it."""
    bringup = get_package_share_directory('turtlebot3_bringup')
    arguments = {'usb_port': LaunchConfiguration('usb_port'), **lidar_launch_arguments}
    ekf = LaunchConfiguration('ekf').perform(context).lower() in ('true', '1', 'yes')
    if ekf:
        arguments['tb3_param_dir'] = params_without_odom_tf(os.environ.get('TURTLEBOT3_MODEL', 'burger'))
    actions = [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup, 'launch', 'robot.launch.py')),
        launch_arguments=arguments.items())]
    if ekf:
        actions += [
            ExecuteProcess(cmd=['python3', os.path.join(ROBOT_DIR, 'covariance_fixer.py')], output='screen'),
            Node(package='robot_localization', executable='ekf_node', name='ekf_filter_node',
                 output='screen', parameters=[os.path.join(ROBOT_DIR, 'config', 'ekf.yaml')]),
        ]
    return actions


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
