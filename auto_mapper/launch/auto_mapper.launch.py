"""SLAM + Nav2 + frontier explorer. Run on the PC; the robot (or Gazebo) provides /scan, /odom and TF."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    model = os.environ.get('TURTLEBOT3_MODEL', 'burger')

    mapper = get_package_share_directory('auto_mapper')
    slam = get_package_share_directory('slam_toolbox')
    nav2 = get_package_share_directory('nav2_bringup')
    tb3_nav = get_package_share_directory('turtlebot3_navigation2')

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false',
                              description='true when running against Gazebo'),
        DeclareLaunchArgument('explorer_params',
                              default_value=os.path.join(mapper, 'config', 'explorer.yaml')),
        DeclareLaunchArgument('slam_params',
                              default_value=os.path.join(mapper, 'config', 'slam_toolbox.yaml')),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(slam, 'launch', 'online_async_launch.py')),
            launch_arguments={'use_sim_time': use_sim_time,
                              'slam_params_file': LaunchConfiguration('slam_params')}.items()),

        # Nav2 without AMCL and map_server: the map comes from slam_toolbox.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(nav2, 'launch', 'navigation_launch.py')),
            launch_arguments={'use_sim_time': use_sim_time,
                              'params_file': os.path.join(tb3_nav, 'param', f'{model}.yaml')}.items()),

        Node(package='auto_mapper', executable='explorer', name='explorer', output='screen',
             parameters=[LaunchConfiguration('explorer_params'), {'use_sim_time': use_sim_time}]),
    ])
