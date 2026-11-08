"""Frontier explorer: drives to the nearest unexplored edge of the SLAM map until none are left."""

import math
import os
import subprocess

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Point, PointStamped, PoseStamped
from nav2_msgs.action import NavigateToPose, Spin
from nav2_msgs.msg import CostmapFilterInfo
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Empty
import tf2_ros
from visualization_msgs.msg import Marker, MarkerArray

from auto_mapper import geofence as fence
from auto_mapper.frontiers import (
    choose_frontier, downsample, find_frontiers, frontier_near, Grid)

KEEPOUT_MASK_TOPIC = '/keepout_filter_mask'
KEEPOUT_INFO_TOPIC = '/costmap_filter_info'
KEEPOUT_FILTER_TYPE = 0     # CostmapFilterInfo.type of the keepout filter


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
        self.map_save_timeout = self.declare_parameter('map_save_timeout', 10.0).value
        self.analysis_resolution = self.declare_parameter('analysis_resolution', 0.05).value
        self.clearance = self.declare_parameter('clearance', 0.15).value
        self.min_goal_distance = self.declare_parameter('min_goal_distance', 0.35).value
        self.goal_radius = self.declare_parameter('goal_frontier_radius', 0.25).value
        self.settle_time = self.declare_parameter('settle_time', 3.0).value
        self.reject_backoff = self.declare_parameter('reject_backoff', 2.0).value
        self.blacklist_retries = self.declare_parameter('blacklist_retries', 1).value
        self.blacklist_retries_max = self.blacklist_retries
        self.spin_pending = self.declare_parameter('initial_spin', True).value
        self.max_offmap_spins = self.declare_parameter('max_offmap_spins', 3).value
        period = self.declare_parameter('period', 1.0).value
        self.require_geofence = self.declare_parameter('require_geofence', True).value
        self.geofence_margin = self.declare_parameter('geofence_margin', 0.15).value
        self.close_radius = self.declare_parameter('geofence_close_radius', 0.3).value
        self.keepout_resolution = self.declare_parameter('keepout_resolution', 0.05).value
        self.keepout_extra = self.declare_parameter('keepout_extra', 10.0).value
        self.keepout_ramp = self.declare_parameter('keepout_ramp', 0.3).value
        preset = self.declare_parameter('geofence', Parameter.Type.DOUBLE_ARRAY).value

        self.geofence = None        # the accepted polygon, [(x, y), ...] in the map frame
        self.drawing = []           # vertices clicked so far
        self.pending_polygon = None  # from the parameter, accepted once the robot position is known
        self.keepout = None         # Grid of the mask last sent to Nav2
        self.allowed = None         # cells inside the geofence, for the grid with allowed_key
        self.allowed_key = None
        if preset:
            if len(preset) % 2 == 0:
                self.pending_polygon = list(zip(preset[0::2], preset[1::2]))
            else:
                self.get_logger().error('Parameter geofence needs x, y pairs, ignoring its odd length')

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
        # For RViz: frontier targets (yellow, size by length) and the current goal (magenta).
        self.markers = self.create_publisher(MarkerArray, '~/frontiers', 1)
        self.frontiers = []
        # The geofence: drawn in RViz with "Publish Point", shown as markers, and sent to the Nav2 keepout
        # filter as a mask, so Nav2 does not plan through the outside either. Latched like /map.
        self.geofence_markers = self.create_publisher(MarkerArray, '~/geofence', 1)
        self.mask_pub = self.create_publisher(OccupancyGrid, KEEPOUT_MASK_TOPIC, qos)
        self.info_pub = self.create_publisher(CostmapFilterInfo, KEEPOUT_INFO_TOPIC, qos)
        self.create_subscription(PointStamped, 'clicked_point', self.on_clicked_point, 10)
        self.create_service(Empty, '~/clear_geofence', self.on_clear_geofence)
        self.create_timer(1.0, self.publish_geofence_markers)
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
        if self.pending_polygon is not None:
            self.set_geofence(self.pending_polygon)
            self.pending_polygon = None
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
        if self.require_geofence and self.geofence is None:
            self.get_logger().info(
                'Waiting for the geofence: click its vertices in RViz with "Publish Point" and close it '
                'by clicking the first vertex again', throttle_duration_sec=10.0)
            return

        frontiers = find_frontiers(self.grid, robot, self.min_frontier_size, self.free_threshold,
                                   self.blacklist, self.blacklist_radius,
                                   self.clearance, self.min_goal_distance, self.allowed_mask())
        target = choose_frontier(frontiers, self.size_weight, self.grid.resolution)
        self.frontiers = frontiers
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

    def allowed_mask(self):
        """Cells of the current grid inside the geofence (None without one); recomputed when the map grows."""
        if self.geofence is None:
            return None
        key = (self.grid.data.shape, self.grid.origin_x, self.grid.origin_y, self.grid.resolution)
        if key != self.allowed_key:
            self.allowed = fence.allowed_mask(self.grid, self.geofence, self.geofence_margin)
            self.allowed_key = key
        return self.allowed

    def on_clicked_point(self, msg):
        if msg.header.frame_id != self.map_frame:
            self.get_logger().warn(f'The clicked point is in frame "{msg.header.frame_id}", set the fixed '
                                   f'frame of RViz to "{self.map_frame}" to draw the geofence')
            return
        point = (msg.point.x, msg.point.y)
        if fence.closes_polygon(self.drawing, point, self.close_radius):
            polygon, self.drawing = self.drawing, []
            self.set_geofence(polygon)
        else:
            if not self.drawing and self.geofence is not None:
                self.get_logger().info(
                    'Drawing a new geofence; the current one stays in force until the new one is closed. '
                    'Cancel the drawing with: ros2 service call /explorer/clear_geofence std_srvs/srv/Empty')
            self.drawing.append(point)
            hint = '; click the first vertex to close it' if len(self.drawing) >= 3 else ''
            self.get_logger().info(
                f'Geofence vertex {len(self.drawing)} at ({point[0]:.2f}, {point[1]:.2f}){hint}')
        self.publish_geofence_markers()

    def set_geofence(self, polygon):
        """Accept the polygon if it is a simple one with the robot inside, and hand it to Nav2 as a mask.

        It also replaces a geofence that is set; a rejected polygon leaves that one in force.
        """
        problem = fence.validate(polygon)
        if problem is None:
            robot = self.robot_xy()
            if robot is None:
                problem = 'the robot position is not known yet (no TF)'
            elif not fence.contains(polygon, robot):
                problem = f'the robot at ({robot[0]:.2f}, {robot[1]:.2f}) is not inside'
        self.drawing = []
        if problem:
            self.get_logger().warn(f'Geofence rejected, {problem}. '
                                   + ('The previous one stays in force.' if self.geofence else 'Draw it again.'))
        else:
            changed = self.geofence is not None
            self.geofence = list(polygon)
            self.allowed_key = None
            self.publish_keepout(fence.keepout_mask(self.geofence, self.keepout_resolution,
                                                       self.keepout_extra, self.keepout_ramp))
            self.get_logger().info(
                f'Geofence {"changed" if changed else "set"}: {len(polygon)} vertices, '
                f'{fence.polygon_area(polygon):.1f} m2. The explorer stays inside and Nav2 treats the '
                'outside as a keepout zone.')
            if self.goal_handle and self.goal_xy and not fence.contains(
                    self.geofence, self.goal_xy, self.geofence_margin):
                self.get_logger().info('The running goal is outside the new geofence, cancelling it')
                self.goal_cleared = True
                self.goal_handle.cancel_goal_async()
                self.goal_handle = None
            if self.done:
                # A bigger fence can open frontiers that were out of reach; the map is saved again at the end.
                self.get_logger().info('The map was saved already; exploring again inside the new geofence')
                self.done = False
                self.empty_ticks = 0
                self.blacklist.clear()
                self.blacklist_retries = self.blacklist_retries_max
        self.publish_geofence_markers()

    def on_clear_geofence(self, request, response):
        if self.drawing:
            # Only the unfinished drawing goes, a geofence that is set stays.
            self.drawing = []
            self.get_logger().info('Drawing cancelled' + (', the current geofence stays in force'
                                                          if self.geofence else ''))
        elif self.geofence is not None:
            self.geofence = None
            self.allowed = self.allowed_key = None
            # The costmap filter keeps its last mask, so overwrite it with one that forbids nothing.
            self.publish_keepout(Grid(np.zeros_like(self.keepout.data), self.keepout.resolution,
                                      self.keepout.origin_x, self.keepout.origin_y))
            if self.goal_handle:
                self.goal_cleared = True
                self.goal_handle.cancel_goal_async()
                self.goal_handle = None
            self.get_logger().info('Geofence removed' + (', waiting for a new one' if self.require_geofence else ''))
        self.publish_geofence_markers()
        return response

    def publish_keepout(self, mask):
        """Send the keepout mask and its CostmapFilterInfo to the filter in the Nav2 costmaps."""
        self.keepout = mask
        stamp = self.get_clock().now().to_msg()
        msg = OccupancyGrid()
        msg.header.frame_id = self.map_frame
        msg.header.stamp = stamp
        msg.info.resolution = float(mask.resolution)
        msg.info.height, msg.info.width = mask.data.shape
        msg.info.origin.position.x = float(mask.origin_x)
        msg.info.origin.position.y = float(mask.origin_y)
        msg.info.origin.orientation.w = 1.0
        msg.data = mask.data.ravel().tolist()
        info = CostmapFilterInfo()
        info.header = msg.header
        info.type = KEEPOUT_FILTER_TYPE
        info.filter_mask_topic = KEEPOUT_MASK_TOPIC
        info.base = 0.0
        info.multiplier = 1.0
        self.mask_pub.publish(msg)
        self.info_pub.publish(info)

    def polygon_markers(self, first_id, polygon, closed, rgba):
        """An outline (LINE_STRIP, closed or not) and its vertices (SPHERE_LIST); DELETE for an empty polygon."""
        line = Marker()
        vertices = Marker()
        for marker_id, marker, kind, size in ((first_id, line, Marker.LINE_STRIP, 0.06),
                                              (first_id + 1, vertices, Marker.SPHERE_LIST, 0.15)):
            marker.header.frame_id = self.map_frame
            marker.ns, marker.id, marker.type = 'geofence', marker_id, kind
            marker.pose.orientation.w = 1.0
            marker.scale.x = marker.scale.y = marker.scale.z = size
            marker.color.r, marker.color.g, marker.color.b, marker.color.a = rgba
            if not polygon:
                marker.action = Marker.DELETE
            marker.points = [Point(x=x, y=y) for x, y in polygon]
        if closed and polygon:
            line.points.append(Point(x=polygon[0][0], y=polygon[0][1]))
        return [line, vertices]

    def publish_geofence_markers(self):
        """The geofence in force (red) and, while a new one is being drawn, that drawing (orange)."""
        markers = (self.polygon_markers(0, self.geofence or [], True, (1.0, 0.1, 0.1, 0.9))
                   + self.polygon_markers(2, self.drawing, False, (1.0, 0.55, 0.0, 0.9)))
        self.geofence_markers.publish(MarkerArray(markers=markers))

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
        self.publish_markers()

    def publish_markers(self):
        """Frontier targets and the current goal. Stamp 0: RViz draws them with the newest transform."""
        def marker(ns, kind, size, rgba):
            m = Marker()
            m.header.frame_id = self.map_frame
            m.ns, m.id, m.type = ns, 0, kind
            m.pose.orientation.w = 1.0
            m.scale.x = m.scale.y = m.scale.z = size
            m.color.r, m.color.g, m.color.b, m.color.a = rgba
            return m

        frontiers = marker('frontiers', Marker.SPHERE_LIST, 0.08, (1.0, 0.85, 0.0, 0.9))
        frontiers.points = [Point(x=f.x, y=f.y) for f in self.frontiers]
        goal = marker('goal', Marker.SPHERE, 0.2, (1.0, 0.0, 1.0, 0.9))
        if self.busy and self.goal_xy:
            goal.pose.position.x, goal.pose.position.y = self.goal_xy
        else:
            goal.action = Marker.DELETE
        self.markers.publish(MarkerArray(markers=[frontiers, goal]))

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
        self.publish_markers()
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
                # map_saver_cli waits only 2 s for a map by default, which is shorter than the interval
                # of the slam_toolbox updates; it failed with "Failed to spin map subscription" in 2 of 5
                # simulation runs.
                returncode = subprocess.run(
                    ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', path, '--ros-args',
                     '-p', f'save_map_timeout:={self.map_save_timeout}'],
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
        # With a geofence the node stays up after the map is saved: Nav2 asks for the latched keepout mask
        # again whenever it resets a costmap, and only this node can send it.
        while rclpy.ok() and not (node.done and node.geofence is None):
            rclpy.spin_once(node, timeout_sec=0.2)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
