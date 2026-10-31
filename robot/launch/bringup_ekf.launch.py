"""TurtleBot3 bring-up with an EKF. Run on the ROBOT instead of turtlebot3_bringup robot.launch.py.

    ros2 launch ~/turtlebot3-setup/robot/launch/bringup_ekf.launch.py

It starts the normal bring-up with the odom -> base_footprint transform of turtlebot3_node switched off
(the EKF publishes it instead), the covariance fixer and robot_localization's ekf_node.
"""

import os
import re
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
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


def generate_launch_description():
    model = os.environ.get('TURTLEBOT3_MODEL', 'burger')
    bringup = get_package_share_directory('turtlebot3_bringup')

    return LaunchDescription([
        DeclareLaunchArgument('usb_port', default_value='/dev/ttyACM0',
                              description='Connected USB port with OpenCR'),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, 'launch', 'robot.launch.py')),
            launch_arguments={'tb3_param_dir': params_without_odom_tf(model),
                              'usb_port': LaunchConfiguration('usb_port')}.items()),

        ExecuteProcess(cmd=['python3', os.path.join(ROBOT_DIR, 'covariance_fixer.py')], output='screen'),

        Node(package='robot_localization', executable='ekf_node', name='ekf_filter_node',
             output='screen', parameters=[os.path.join(ROBOT_DIR, 'config', 'ekf.yaml')]),
    ])
