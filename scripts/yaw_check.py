#!/usr/bin/env python3
"""Compare the heading (yaw) the robot reports from its different sources. Needs ROS 2.

    python3 yaw_check.py [seconds]          # default 60

Sources:
  /odom yaw         the wheel odometry; turtlebot3_node takes its heading from the IMU orientation
  /imu orientation  the quaternion computed by the OpenCR firmware
  gyro integral     angular_velocity.z of /imu integrated over time (rate only, no reference)
  EKF yaw           /odometry/filtered, if the EKF bring-up is running

Run it twice:
  1. Robot standing still: every source should stay within about a degree. A source that drifts,
     or an orientation that moves while the gyro integral stays put, is an unreliable heading.
  2. Drive one full turn slowly (teleop, 0.3 rad/s) and bring the robot back to its starting direction:
     a good source ends near 360 degrees. Sources that disagree with each other show who is wrong.

Also prints the largest single jump of each yaw between two messages; a heading jump is what makes
the map suddenly rotate.
"""

import math
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Track:
    """An unwrapped yaw in degrees with its total change and its largest jump between messages."""

    def __init__(self, name):
        self.name = name
        self.count = 0
        self.first = None
        self.last = None
        self.total = 0.0
        self.max_jump = 0.0
        self.big_jumps = 0

    def add(self, yaw_rad):
        if self.last is not None:
            step = math.degrees(math.remainder(yaw_rad - self.last, 2 * math.pi))
            self.total += step
            if abs(step) > abs(self.max_jump):
                self.max_jump = step
            if abs(step) > 3.0:
                self.big_jumps += 1
        self.count += 1
        self.last = yaw_rad

    def line(self, seconds):
        if self.count < 2:
            return f'{self.name:<18} no data'
        return (f'{self.name:<18} change {self.total:8.1f} deg  ({self.total / seconds * 60:7.1f} deg/min)'
                f'   largest step {self.max_jump:6.1f} deg   steps over 3 deg: {self.big_jumps}')


class YawCheck(Node):

    def __init__(self):
        super().__init__('yaw_check')
        self.odom = Track('/odom yaw')
        self.imu = Track('/imu orientation')
        self.ekf = Track('EKF yaw')
        self.gyro_total = 0.0
        self.gyro_sum = 0.0
        self.gyro_count = 0
        self.last_gyro_time = None
        self.create_subscription(Odometry, 'odom', lambda m: self.odom.add(yaw_of(m.pose.pose.orientation)), 10)
        self.create_subscription(Odometry, 'odometry/filtered',
                                 lambda m: self.ekf.add(yaw_of(m.pose.pose.orientation)), 10)
        self.create_subscription(Imu, 'imu', self.on_imu, qos_profile_sensor_data)

    def on_imu(self, m):
        self.imu.add(yaw_of(m.orientation))
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        if self.last_gyro_time is not None and 0 < t - self.last_gyro_time < 1.0:
            self.gyro_total += math.degrees(m.angular_velocity.z) * (t - self.last_gyro_time)
        self.gyro_sum += m.angular_velocity.z
        self.gyro_count += 1
        self.last_gyro_time = t


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    rclpy.init()
    node = YawCheck()
    print(f'Measuring for {seconds:g} s ...', flush=True)
    end = node.get_clock().now().nanoseconds + int(seconds * 1e9)
    while node.get_clock().now().nanoseconds < end:
        rclpy.spin_once(node, timeout_sec=0.2)
    print()
    print(node.odom.line(seconds))
    print(node.imu.line(seconds))
    print(f'{"gyro integral":<18} change {node.gyro_total:8.1f} deg  ({node.gyro_total / seconds * 60:7.1f} deg/min)')
    print(node.ekf.line(seconds))
    if node.gyro_count:
        bias = math.degrees(node.gyro_sum / node.gyro_count)
        print(f'mean gyro z: {bias:.3f} deg/s (about 0 when standing still; a larger value is a gyro bias)')
    print('messages:', f'/odom {node.odom.count}, /imu {node.imu.count}, EKF {node.ekf.count}')
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
