#!/usr/bin/env python3
"""Read an LDS-01 LiDAR directly from its serial port, without ROS.

Shows, per revolution, the rotation speed, how many of the 60 packets arrived and how many of the
360 readings are valid. It tells a faulty sensor from a bad link (cable, adapter, Pi) and from a
slow driver: a healthy LDS-01 gives about 300 rpm, 60 of 60 packets and 5 revolutions per second.

    python3 lds01_check.py /dev/ttyUSB0          # Linux, Raspberry Pi (stop the bring-up first)
    py lds01_check.py COM3                       # Windows (pip install pyserial)

The packet format and its parser are in robot/lds01_protocol.py, shared with the ROS driver.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'robot'))

from lds01_protocol import PACKETS_PER_REV, PacketStream, Revolutions  # noqa: E402


def summarize(revolutions, seconds, stream=None, rejected=0):
    if not revolutions:
        return 'No complete revolution received.'
    n = len(revolutions)
    text = (f'{n} revolutions in {seconds:.1f} s = {n / seconds:.2f} per second (healthy: about 5). '
            f'Mean: {sum(r.packet_count for r in revolutions) / n:.1f} of {PACKETS_PER_REV} packets, '
            f'{sum(r.valid_count for r in revolutions) / n:.0f} of 360 valid readings, '
            f'{sum(r.rpm for r in revolutions) / n:.0f} rpm (healthy: about 300).')
    if stream is not None and stream.received:
        text += ('\n' + f'Bytes: {stream.received / seconds:.0f} per second (healthy: about 12600), '
                 f'{100 * stream.discarded / stream.received:.1f} % discarded as unusable (healthy: about 0), '
                 f'{rejected} packets with an impossible speed.')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('port', help='serial port, for example /dev/ttyUSB0 or COM3')
    parser.add_argument('--seconds', type=float, default=10.0, help='how long to read (default 10)')
    parser.add_argument('--baud', type=int, default=230400)
    args = parser.parse_args()

    try:
        import serial
    except ImportError:
        sys.exit('pyserial is missing: pip install pyserial (Ubuntu: sudo apt install python3-serial)')

    revs = Revolutions()
    stream = PacketStream()
    with serial.Serial(args.port, args.baud, timeout=0.2) as port:
        port.write(b'b')   # starts the motor, like the ROS driver does
        start = time.monotonic()
        shown = 0
        try:
            while time.monotonic() - start < args.seconds:
                for index, rpm, readings in stream.feed(port.read(max(port.in_waiting, 1))):
                    revs.add(index, rpm, readings)
                while shown < len(revs.finished):
                    rev = revs.finished[shown]
                    print(f'revolution {shown + 1}: {rev.packet_count}/{PACKETS_PER_REV} packets, '
                          f'{rev.valid_count}/360 valid, {rev.rpm:.0f} rpm')
                    shown += 1
        finally:
            port.write(b'e')   # stops the motor
    # The first revolution starts at a random packet, so it is partial and left out of the summary.
    print(summarize(revs.finished[1:], time.monotonic() - start, stream, revs.rejected))


if __name__ == '__main__':
    main()
