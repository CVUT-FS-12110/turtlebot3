"""Drive the robot with the Evolveo Fighter F1 gamepad plugged into the Pi. Run on the ROBOT.

    ros2 launch ~/turtlebot3-setup/robot/launch/gamepad.launch.py

or together with the bring-up: bringup.launch.py gamepad:=true. It starts joy_node (reads /dev/input/js0)
and teleop_twist_joy, which turns the left stick into /cmd_vel while the enable button is held:
stick up/down = forward/back, left/right = turn. Releasing the enable button stops the robot.

Measured on the pad in D-input mode (0079:181c): left stick = axes 0 (left/right) and 1 (up/down),
L1 = button 6. In X-input mode (045e:028e, LED1 + LED2) the left stick is the same, but L1 (LB) is
button 4: pass enable_button:=4. See docs/gamepad.md.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('enable_button', default_value='6',
                              description='Button held to drive: 6 = L1 in D-input mode, 4 = LB in X-input mode'),
        DeclareLaunchArgument('scale_linear', default_value='0.15',
                              description='Forward speed [m/s] at full stick (Burger maximum is 0.22)'),
        DeclareLaunchArgument('scale_angular', default_value='1.0',
                              description='Turning speed [rad/s] at full stick (Burger maximum is 2.84)'),
        DeclareLaunchArgument('stamped', default_value='true',
                              description='true: /cmd_vel is geometry_msgs/TwistStamped, which turtlebot3_node '
                                          'expects in Jazzy (checked on the robot with ros2 topic info /cmd_vel -v)'),

        Node(package='joy', executable='joy_node', name='joy_node', output='screen',
             parameters=[{'autorepeat_rate': 20.0}]),

        Node(package='teleop_twist_joy', executable='teleop_node', name='teleop_twist_joy_node',
             output='screen',
             parameters=[{
                 'enable_button': ParameterValue(LaunchConfiguration('enable_button'), value_type=int),
                 'axis_linear.x': 1,
                 'axis_angular.yaw': 0,
                 'scale_linear.x': ParameterValue(LaunchConfiguration('scale_linear'), value_type=float),
                 'scale_angular.yaw': ParameterValue(LaunchConfiguration('scale_angular'), value_type=float),
                 'publish_stamped_twist': ParameterValue(LaunchConfiguration('stamped'), value_type=bool),
             }]),
    ])
