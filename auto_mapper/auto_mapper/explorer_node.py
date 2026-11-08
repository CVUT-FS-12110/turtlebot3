"""Frontier explorer: drives to the nearest unexplored edge of the SLAM map until none are left."""

import math
import os
import subprocess

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose, Spin
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
import tf2_ros

from auto_mapper.frontiers import (
    choose_frontier, downsample, find_frontiers, frontier_near, Grid)


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
        self.analysis_resolution = self.declare_parameter('analysis_resolution', 0.05).value
        self.clearance = self.declare_parameter('clearance', 0.15).value
        self.min_goal_distance = self.declare_parameter('min_goal_distance', 0.35).value
        self.goal_radius = self.declare_parameter('goal_frontier_radius', 0.25).value
        self.settle_time = self.declare_parameter('settle_time', 3.0).value
        self.reject_backoff = self.declare_parameter('reject_backoff', 2.0).value
        self.blacklist_retries = self.declare_parameter('blacklist_retries', 1).value
        self.spin_pending = self.declare_parameter('initial_spin', True).value
        self.max_offmap_spins = self.declare_parameter('max_offmap_spins', 3).value
        period = self.declare_parameter('period', 1.0).value

        self.grid = None
        self.blacklist = []
        self.busy = False
        self.done = False
        self.empty_ticks = 0
        self.goal_xy = None
        self.goal_time = 0.0
        self.goal_handle = None
        self.spinning = False
        self.offmap_spins = 0
        self.wait_until = 0.0      # no new goal before this time
        self.check_goal = False     # after settling: blacklist the last goal if it is still a frontier
        self.goal_cleared = False   # the running goal was cancelled because its area got explored

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.nav = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.spin = ActionClient(self, Spin, 'spin')
        # slam_toolbox publishes /map latched, so a late start still gets the last map.
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, 'map', self.on_map, qos)
        self.create_timer(period, self.tick)
        self.get_logger().info('Waiting for /map, TF and the navigate_to_pose action server...')

    def on_map(self, msg):
        data = np.asarray(msg.data, dtype=np.int8).reshape(msg.info.height, msg.info.width)
        grid = Grid(data, msg.info.resolution,
                    msg.info.origin.position.x, msg.info.origin.position.y)
        factor = int(round(self.analysis_resolution / msg.info.resolution))
        self.grid = downsample(grid, factor, self.free_threshold)

    def now(self):
        """Node time in seconds: follows the Gazebo clock, so timeouts hold in a slow simulation too."""
        return self.get_clock().now().nanoseconds * 1e-9

    def robot_on_map(self, robot):
        row, col = self.grid.world_to_cell(*robot)
        return self.grid.in_bounds(row, col) and self.grid.data[row, col] >= 0

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
        if self.spinning:
            return
        if self.busy:
            if self.now() - self.goal_time > self.goal_timeout and self.goal_handle:
                self.get_logger().warn('Goal timed out, cancelling it')
                self.goal_handle.cancel_goal_async()
                self.goal_handle = None
            elif self.goal_handle and not self.goal_is_frontier():
                self.get_logger().info('Goal area is explored already, cancelling it')
                self.goal_cleared = True
                self.goal_handle.cancel_goal_async()
                self.goal_handle = None
            return
        if not self.nav.server_is_ready() or self.now() < self.wait_until:
            return
        # Nav2 cannot plan from outside the map and no frontier would be reachable, which must not look
        # like a finished map. slam_toolbox adds a scan only after a move or turn, so turn to grow the map.
        if self.robot_on_map(robot):
            self.offmap_spins = 0
        elif self.offmap_spins >= self.max_offmap_spins:
            self.get_logger().error(
                f'The robot is still outside the map after {self.offmap_spins} turns; SLAM does not seem '
                'to add scans (check /scan and TF). Stopping and saving what there is.')
            self.finish()
            return
        else:
            self.offmap_spins += 1
            self.spin_pending = True
        if self.spin_pending:
            self.send_spin()
            return
        if self.check_goal:
            self.check_goal = False
            self.blacklist_goal_if_unexplored()

        frontiers = find_frontiers(self.grid, robot, self.min_frontier_size, self.free_threshold,
                                   self.blacklist, self.blacklist_radius,
                                   self.clearance, self.min_goal_distance)
        target = choose_frontier(frontiers, self.size_weight, self.grid.resolution)
        if target is None:
            self.empty_ticks += 1
            if self.empty_ticks >= self.finish_after:
                if self.blacklist and self.blacklist_retries > 0:
                    # A goal can fail for a passing reason, so give them another chance before finishing.
                    self.blacklist_retries -= 1
                    self.get_logger().info(f'Retrying {len(self.blacklist)} blacklisted goals before finishing')
                    self.blacklist.clear()
                    self.empty_ticks = 0
                else:
                    self.finish()
            return
        self.empty_ticks = 0
        self.send_goal(target, robot)

    def goal_is_frontier(self):
        row, col = self.grid.world_to_cell(*self.goal_xy)
        radius = int(round(self.goal_radius / self.grid.resolution))
        return frontier_near(self.grid.data, row, col, self.free_threshold, radius)

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
        self.goal_time = self.now()
        self.nav.send_goal_async(goal).add_done_callback(self.on_goal_response)

    def on_goal_response(self, future):
        self.goal_handle = future.result()
        if not self.goal_handle.accepted:
            # Says nothing about the goal: bt_navigator rejects everything until Nav2 is active.
            self.get_logger().info('Nav2 is not accepting goals yet, trying again shortly')
            self.goal_handle = None
            self.busy = False
            self.wait_until = self.now() + self.reject_backoff
            return
        self.goal_handle.get_result_async().add_done_callback(self.on_result)

    def on_result(self, future):
        status = future.result().status
        self.goal_handle = None
        self.busy = False
        if self.goal_cleared:
            self.goal_cleared = False   # nothing to judge, go straight to the next frontier
            return
        if status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info(f'Goal ended with status {status}')
        # The map lags behind the robot (map_update_interval), so judge the goal after the next update.
        self.check_goal = True
        self.wait_until = self.now() + self.settle_time

    def send_spin(self):
        if not self.spin.server_is_ready():
            return
        self.get_logger().info('Turning around to scan the surroundings')
        goal = Spin.Goal()
        goal.target_yaw = 2 * math.pi
        goal.time_allowance.sec = 60
        self.spinning = True
        self.spin.send_goal_async(goal).add_done_callback(self.on_spin_response)

    def on_spin_response(self, future):
        handle = future.result()
        if not handle.accepted:
            self.spinning = False
            self.wait_until = self.now() + self.reject_backoff
            return
        handle.get_result_async().add_done_callback(self.on_spin_result)

    def on_spin_result(self, future):
        status = future.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().warn(f'Turning around ended with status {status}')
        self.spinning = False
        self.spin_pending = False
        self.wait_until = self.now() + self.settle_time

    def blacklist_goal_if_unexplored(self):
        """A goal that did not clear its frontier (failed, timed out, reached but unseen) is blacklisted."""
        if self.goal_is_frontier():
            self.blacklist.append(self.goal_xy)
            self.get_logger().info(f'Blacklisted ({self.goal_xy[0]:.2f}, {self.goal_xy[1]:.2f}), '
                                   f'{len(self.blacklist)} in total')

    def finish(self):
        self.get_logger().info('No reachable frontiers left, exploration is complete')
        if self.save_map:
            path = os.path.expanduser(self.map_path)
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            try:
                returncode = subprocess.run(
                    ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', path],
                    check=False, timeout=60).returncode
            except subprocess.TimeoutExpired:
                returncode = -1
            if returncode == 0:
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
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
