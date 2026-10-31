#!/usr/bin/env python3
"""LDS-01 driver that survives lost bytes. Drop-in for hlds_laser_publisher: publishes /scan.

On some robots the serial link of the LiDAR loses or corrupts about a third of the bytes. The stock
driver cuts a revolution out of the stream at fixed positions, so one lost byte spoils the rest of
the revolution and it keeps only a handful of readings. This driver recognises every packet on its
own and places its six readings by the packet index; what is lost stays empty (0.0), the rest is kept.

Started by launch/lidar/hlds_laser.launch.py, which robot.launch.py picks instead of the stock one.
Needs pyserial (sudo apt install python3-serial).
"""

import math
import os
import sys
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lds01_protocol import (PACKETS_PER_REV, PacketStream, RANGE_MAX_MM, RANGE_MIN_MM,  # noqa: E402
                            Revolutions, revolution_to_scan)


class Lds01Driver(Node):

    def __init__(self):
        super().__init__('hlds_laser_publisher')
        self.port_name = self.declare_parameter('port', '/dev/ttyUSB0').value
        self.baud = self.declare_parameter('baud', 230400).value
        self.frame_id = self.declare_parameter('frame_id', 'base_scan').value
        # Revolutions with fewer packets than this are garbage and not published.
        self.min_packets = self.declare_parameter('min_packets', 20).value
        self.log_every = self.declare_parameter('log_every', 10.0).value

        self.serial = None
        self.next_open = 0.0
        self.stream = PacketStream()
        self.revs = Revolutions()
        self.published = 0
        self.dropped = 0
        self.packet_sum = 0
        self.last_log = time.monotonic()

        self.pub = self.create_publisher(LaserScan, 'scan', qos_profile_sensor_data)
        self.create_timer(0.02, self.read)

    def open_port(self):
        import serial   # imported here so a missing pyserial is reported by the node
        try:
            self.serial = serial.Serial(self.port_name, self.baud, timeout=0)
            self.serial.write(b'b')   # starts the motor
            self.stream = PacketStream()
            self.revs = Revolutions()
            self.get_logger().info(f'Reading the LDS-01 on {self.port_name}')
        except (OSError, serial.SerialException) as err:
            self.serial = None
            self.next_open = time.monotonic() + 2.0
            self.get_logger().error(f'Cannot open {self.port_name}: {err}; retrying in 2 s')

    def read(self):
        if self.serial is None:
            if time.monotonic() >= self.next_open:
                self.open_port()
            return
        try:
            data = self.serial.read(self.serial.in_waiting)
        except OSError as err:
            self.get_logger().error(f'Serial read failed: {err}; reopening')
            self.serial = None
            self.next_open = time.monotonic() + 2.0
            return
        for index, rpm, readings in self.stream.feed(data):
            rev = self.revs.add(index, rpm, readings)
            if rev is not None:
                self.publish(rev)
        self.log_stats()

    def publish(self, rev):
        if rev.packet_count < self.min_packets:
            self.dropped += 1
            return
        ranges, intensities = revolution_to_scan(rev, RANGE_MIN_MM / 1000, RANGE_MAX_MM / 1000)
        scan_time = 60.0 / rev.rpm
        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.angle_min = 0.0
        msg.angle_max = 2.0 * math.pi
        msg.angle_increment = 2.0 * math.pi / 360.0
        msg.scan_time = scan_time
        msg.time_increment = scan_time / 360.0
        msg.range_min = RANGE_MIN_MM / 1000
        msg.range_max = RANGE_MAX_MM / 1000
        msg.ranges = ranges
        msg.intensities = intensities
        self.pub.publish(msg)
        self.published += 1
        self.packet_sum += rev.packet_count

    def log_stats(self):
        now = time.monotonic()
        if now - self.last_log < self.log_every:
            return
        seconds = now - self.last_log
        mean = self.packet_sum / self.published if self.published else 0.0
        discarded = 100.0 * self.stream.discarded / self.stream.received if self.stream.received else 0.0
        self.get_logger().info(
            f'{self.published / seconds:.1f} scans/s, {mean:.0f} of {PACKETS_PER_REV} packets per scan, '
            f'{self.dropped} revolutions dropped, {discarded:.0f} % of the bytes unusable')
        self.published = self.dropped = self.packet_sum = 0
        self.stream.received = self.stream.discarded = 0
        self.last_log = now

    def stop(self):
        if self.serial is not None:
            try:
                self.serial.write(b'e')   # stops the motor
                self.serial.close()
            except OSError:
                pass


def main():
    rclpy.init()
    node = Lds01Driver()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.stop()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
