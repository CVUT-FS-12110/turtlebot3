#!/usr/bin/env python3
"""Republish /odom and /imu with real covariances for the EKF.

turtlebot3_node leaves every covariance at zero, which robot_localization reads as a perfect
measurement, so the filter would just copy its inputs. The variances below set how much it trusts
the wheel speed and the gyro; tune them with ros2 param set if the result is too jumpy or too laggy.
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu


class CovarianceFixer(Node):

    def __init__(self):
        super().__init__('covariance_fixer')
        self.vx_var = self.declare_parameter('odom_vx_variance', 4.0e-4).value      # (0.02 m/s)^2
        self.gyro_var = self.declare_parameter('imu_gyro_variance', 1.0e-4).value   # (0.01 rad/s)^2

        # Best effort receives from both reliable and best-effort publishers.
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.odom_pub = self.create_publisher(Odometry, 'odom_cov', 10)
        self.imu_pub = self.create_publisher(Imu, 'imu_cov', 10)
        self.create_subscription(Odometry, 'odom', self.on_odom, qos)
        self.create_subscription(Imu, 'imu', self.on_imu, qos)

    def on_odom(self, msg):
        msg.twist.covariance[0] = self.vx_var     # vx
        msg.twist.covariance[7] = 1.0e-3          # vy (not fused)
        msg.twist.covariance[35] = 1.0e-3         # vyaw (not fused, the gyro is used instead)
        self.odom_pub.publish(msg)

    def on_imu(self, msg):
        for i in (0, 4, 8):
            msg.angular_velocity_covariance[i] = self.gyro_var
        self.imu_pub.publish(msg)


def main():
    rclpy.init()
    node = CovarianceFixer()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
