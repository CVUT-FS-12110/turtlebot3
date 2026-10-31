"""Frontier explorer: drives to the nearest unexplored edge of the SLAM map until none are left."""

import math
import os
import subprocess
import time

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
import tf2_ros

from auto_mapper.frontiers import choose_frontier, find_frontiers, Grid, is_frontier_cell


class Explorer(Node):

    def __init__(self):
        super().__init__('explorer')
        self.map_frame = self.declare_parameter('map_frame', 'map').value
        self.robot_frame = self.declare_parameter('robot_frame', 'base_footprint').value
        self.free_threshold = self.declare_parameter('free_threshold', 25).value
        self.min_frontier_size = self.declare_parameter('min_frontier_size', 5).value
        self.size_weight = self.declare_parameter('size_weight', 0.5).value
        self.blacklist_radius = self.declare_parameter('blacklist_radius', 0.5).value
        self.goal_timeout = self.declare_parameter('goal_timeout', 90.0).value
        self.finish_after = self.declare_parameter('finish_after_empty_ticks', 5).value
        self.save_map = self.declare_parameter('save_map', True).value
        self.map_path = self.declare_parameter('map_path', '~/maps/auto_map').value
        period = self.declare_parameter('period', 1.0).value

        self.grid = None
        self.blacklist = []
        self.busy = False
        self.done = False
        self.empty_ticks = 0
        self.goal_xy = None
        self.goal_time = 0.0
        self.goal_handle = None

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.nav = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        # slam_toolbox publishes /map latched, so a late start still gets the last map.
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, 'map', self.on_map, qos)
        self.create_timer(period, self.tick)
        self.get_logger().info('Waiting for /map, TF and the navigate_to_pose action server...')

    def on_map(self, msg):
        data = np.asarray(msg.data, dtype=np.int8).reshape(msg.info.height, msg.info.width)
        self.grid = Grid(data, msg.info.resolution,
                         msg.info.origin.position.x, msg.info.origin.position.y)

    def robot_xy(self):
        try:
            t = self.tf_buffer.lookup_transform(self.map_frame, self.robot_frame, rclpy.time.Time())
        except tf2_ros.TransformException:
            return None
        return t.transform.translation.x, t.transform.translation.y

    def tick(self):
        if self.done or self.grid is None:
            return
        robot = self.robot_xy()
        if robot is None:
            return
        if self.busy:
            if time.monotonic() - self.goal_time > self.goal_timeout and self.goal_handle:
                self.get_logger().warn('Goal timed out, cancelling it')
                self.goal_handle.cancel_goal_async()
                self.goal_handle = None
            elif self.goal_handle and not self.goal_is_frontier():
                self.get_logger().info('Goal area is explored already, cancelling it')
                self.goal_handle.cancel_goal_async()
                self.goal_handle = None
            return
        if not self.nav.server_is_ready():
            return

        frontiers = find_frontiers(self.grid, robot, self.min_frontier_size, self.free_threshold,
                                   self.blacklist, self.blacklist_radius)
        target = choose_frontier(frontiers, self.size_weight, self.grid.resolution)
        if target is None:
            self.empty_ticks += 1
            if self.empty_ticks >= self.finish_after:
                self.finish()
            return
        self.empty_ticks = 0
        self.send_goal(target, robot)

    def goal_is_frontier(self):
        row, col = self.grid.world_to_cell(*self.goal_xy)
        return is_frontier_cell(self.grid.data, row, col, self.free_threshold)

    def send_goal(self, target, robot):
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = self.map_frame
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = target.x
        goal.pose.pose.position.y = target.y
        yaw = math.atan2(target.y - robot[1], target.x - robot[0])
        goal.pose.pose.orientation.z = math.sin(yaw / 2)
        goal.pose.pose.orientation.w = math.cos(yaw / 2)

        self.get_logger().info(
            f'Going to frontier ({target.x:.2f}, {target.y:.2f}), '
            f'{target.size} cells, {target.distance:.1f} m away')
        self.busy = True
        self.goal_xy = (target.x, target.y)
        self.goal_time = time.monotonic()
        self.nav.send_goal_async(goal).add_done_callback(self.on_goal_response)

    def on_goal_response(self, future):
        self.goal_handle = future.result()
        if not self.goal_handle.accepted:
            self.get_logger().warn('Nav2 rejected the goal')
            self.end_goal()
            return
        self.goal_handle.get_result_async().add_done_callback(self.on_result)

    def on_result(self, future):
        status = future.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info(f'Goal ended with status {status}')
        self.end_goal()

    def end_goal(self):
        """A goal that did not clear its frontier (failed, timed out, reached but unseen) is blacklisted."""
        if self.grid is not None and self.goal_is_frontier():
            self.blacklist.append(self.goal_xy)
            self.get_logger().info(f'Blacklisted ({self.goal_xy[0]:.2f}, {self.goal_xy[1]:.2f}), '
                                   f'{len(self.blacklist)} in total')
        self.goal_handle = None
        self.busy = False

    def finish(self):
        self.get_logger().info('No reachable frontiers left, exploration is complete')
        if self.save_map:
            path = os.path.expanduser(self.map_path)
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            result = subprocess.run(
                ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', path],
                check=False, timeout=60)
            if result.returncode == 0:
                self.get_logger().info(f'Map saved to {path}.yaml / {path}.pgm')
            else:
                self.get_logger().error('map_saver_cli failed, the map was not saved')
        self.done = True


def main():
    rclpy.init()
    node = Explorer()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
