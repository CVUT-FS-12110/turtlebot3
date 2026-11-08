"""SLAM + Nav2 + frontier explorer. Run on the PC; the robot (or Gazebo) provides /scan, /odom and TF.

With slam:=false only Nav2 and the explorer start and continue the map of a slam_toolbox that already
runs, for example after mapping part of a room by hand (mapping.sh explore).
"""

import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml
import yaml


def with_keepout_filter(source_file):
    """Copy of the Nav2 parameters with the keepout filter in both costmaps; returns the path.

    The explorer publishes the mask and /costmap_filter_info once a geofence is set. Until then the filter
    waits for them and changes nothing. RewrittenYaml cannot do this, it only sets single string values.
    """
    with open(source_file, encoding='utf-8') as f:
        params = yaml.safe_load(f)
    for name in ('global_costmap', 'local_costmap'):
        costmap = params[name][name]['ros__parameters']
        costmap['filters'] = ['keepout_filter']
        costmap['keepout_filter'] = {
            'plugin': 'nav2_costmap_2d::KeepoutFilter',
            'enabled': True,
            'filter_info_topic': '/costmap_filter_info',
        }
    with tempfile.NamedTemporaryFile('w', suffix='_nav2_keepout.yaml', delete=False, encoding='utf-8') as f:
        yaml.safe_dump(params, f)
    return f.name


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    max_speed = LaunchConfiguration('max_speed')
    model = os.environ.get('TURTLEBOT3_MODEL', 'burger')

    mapper = get_package_share_directory('auto_mapper')
    slam = get_package_share_directory('slam_toolbox')
    nav2 = get_package_share_directory('nav2_bringup')
    tb3_nav = get_package_share_directory('turtlebot3_navigation2')

    # The ROBOTIS parameters with what does not fit this robot changed:
    # - collision_monitor stops the robot when the newest scan is older than source_timeout. The default
    #   0.2 s is barely longer than the scan period (0.14 s at 7 Hz), so Wi-Fi jitter would stop it all the time.
    # - The default top speed of 0.3 m/s is above the 0.22 m/s the Burger can do.
    # - The costmaps have the 2.5 cm cells of the SLAM map instead of 5 cm, so they look as fine in RViz.
    # - The costmaps get the keepout filter that enforces the geofence.
    nav2_params = RewrittenYaml(
        source_file=with_keepout_filter(os.path.join(tb3_nav, 'param', f'{model}.yaml')),
        param_rewrites={
            'collision_monitor.ros__parameters.scan.source_timeout': '1.0',
            'global_costmap.global_costmap.ros__parameters.resolution': '0.025',
            'local_costmap.local_costmap.ros__parameters.resolution': '0.025',
            'controller_server.ros__parameters.FollowPath.max_vel_x': max_speed,
            'controller_server.ros__parameters.FollowPath.max_speed_xy': max_speed,
        },
        convert_types=True)

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false',
                              description='true when running against Gazebo'),
        DeclareLaunchArgument('max_speed', default_value='0.18',
                              description='Top speed [m/s]; the Burger reaches 0.22, slower gives SLAM a better map'),
        DeclareLaunchArgument('slam', default_value='true',
                              description='false: use a slam_toolbox that already runs (keeps its map)'),
        DeclareLaunchArgument('explorer_params',
                              default_value=os.path.join(mapper, 'config', 'explorer.yaml')),
        DeclareLaunchArgument('slam_params',
                              default_value=os.path.join(mapper, 'config', 'slam_toolbox.yaml')),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(slam, 'launch', 'online_async_launch.py')),
            condition=IfCondition(LaunchConfiguration('slam')),
            launch_arguments={'use_sim_time': use_sim_time,
                              'slam_params_file': LaunchConfiguration('slam_params')}.items()),

        # Nav2 without AMCL and map_server: the map comes from slam_toolbox.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(nav2, 'launch', 'navigation_launch.py')),
            launch_arguments={'use_sim_time': use_sim_time,
                              'params_file': nav2_params}.items()),

        Node(package='auto_mapper', executable='explorer', name='explorer', output='screen',
             parameters=[LaunchConfiguration('explorer_params'), {'use_sim_time': use_sim_time}]),
    ])
