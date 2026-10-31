#!/usr/bin/env python3
"""Count the valid readings in the /scan messages that arrive. Needs ROS 2 (run it on the PC or the robot).

    python3 scan_stats.py [seconds]

Prints how many scans arrived (a healthy LDS-01 gives 5 per second) and, for a few of them, how many of
the 360 rays are valid and where the nearest and farthest readings are. With a robot standing in the
middle of a room with matte walls a good scan has hundreds of valid rays; a handful means the LiDAR
link loses data or the surfaces return no light (see docs/troubleshooting.md).
"""

import math
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    rclpy.init()
    node = Node('scan_stats')
    scans = []
    node.create_subscription(LaserScan, 'scan', scans.append, qos_profile_sensor_data)
    end = node.get_clock().now().nanoseconds + int(seconds * 1e9)
    while node.get_clock().now().nanoseconds < end:
        rclpy.spin_once(node, timeout_sec=0.2)
    print(f'scans in {seconds:g} s: {len(scans)} ({len(scans) / seconds:.1f} per second, healthy: about 5)')
    valid_counts = []
    for m in scans:
        valid_counts.append(sum(1 for x in m.ranges if math.isfinite(x) and m.range_min <= x <= m.range_max))
    if scans:
        print(f'valid rays per scan: mean {sum(valid_counts) / len(scans):.0f}, '
              f'min {min(valid_counts)}, max {max(valid_counts)} (of {len(scans[0].ranges)})')
        m = scans[len(scans) // 2]
        ok = [x for x in m.ranges if math.isfinite(x) and m.range_min <= x <= m.range_max]
        print(f'a middle scan: nearest {min(ok, default=0):.2f} m, farthest {max(ok, default=0):.2f} m, '
              f'limits {m.range_min:.2f}-{m.range_max:.2f} m, scan_time {m.scan_time:.2f} s')
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
