#!/usr/bin/env python3
"""Write the battery voltage from /battery_state to a file for the tmux status bar.

The file holds one line with tmux style codes, for example "bat 11.8 V 87 %" in green, yellow or red.
tmux shows it with #(cat /tmp/tb3_battery). One small subscriber costs far less on a Raspberry Pi 3B+
than calling `ros2 topic echo` every few seconds.
"""

import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import BatteryState


def format_status(voltage, percentage, warn_voltage, critical_voltage):
    """One tmux status line for a battery reading; percentage is 0-1 as in sensor_msgs/BatteryState."""
    # Foreground and background are always set: the default tmux status bar is green, so a plain
    # green text on it would be invisible.
    if voltage < critical_voltage:
        style, label = 'fg=white,bg=red,bold', 'BAT LOW'
    elif voltage < warn_voltage:
        style, label = 'fg=black,bg=yellow', 'bat'
    else:
        style, label = 'fg=black,bg=colour120', 'bat'
    percent = percentage * 100 if percentage <= 1.0 else percentage
    return f'#[{style}]{label} {voltage:.1f} V {percent:.0f} %#[default]'


def format_stale(age):
    return f'#[fg=white,bg=colour240]bat no data ({age:.0f} s)#[default]'


class BatteryStatus(Node):

    def __init__(self):
        super().__init__('battery_status')
        self.path = self.declare_parameter('output_file', '/tmp/tb3_battery').value
        self.warn_voltage = self.declare_parameter('warn_voltage', 11.0).value
        self.critical_voltage = self.declare_parameter('critical_voltage', 10.5).value
        self.stale_after = self.declare_parameter('stale_after', 5.0).value

        self.last_line = None
        self.last_time = time.monotonic()
        # Best effort receives from both reliable and best-effort publishers.
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(BatteryState, 'battery_state', self.on_battery, qos)
        self.create_timer(2.0, self.refresh)
        self.write(format_stale(0.0))

    def on_battery(self, msg):
        self.last_time = time.monotonic()
        self.last_line = format_status(msg.voltage, msg.percentage,
                                       self.warn_voltage, self.critical_voltage)

    def refresh(self):
        age = time.monotonic() - self.last_time
        if self.last_line is None or age > self.stale_after:
            self.write(format_stale(age))
        else:
            self.write(self.last_line)

    def write(self, line):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(line)
        os.replace(tmp, self.path)   # tmux never reads a half-written file


def main():
    rclpy.init()
    node = BatteryStatus()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        try:
            os.remove(node.path)   # a stale file would show an old voltage in tmux
        except OSError:
            pass
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
