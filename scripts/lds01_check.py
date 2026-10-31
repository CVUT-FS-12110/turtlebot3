#!/usr/bin/env python3
"""Read an LDS-01 LiDAR directly from its serial port, without ROS.

Shows, per revolution, the rotation speed, how many of the 60 packets arrived and how many of the
360 readings are valid. It tells a faulty sensor from a bad link (cable, adapter, Pi) and from a
slow driver: a healthy LDS-01 gives about 300 rpm, 60 of 60 packets and 5 revolutions per second.

    python3 lds01_check.py /dev/ttyUSB0          # Linux, Raspberry Pi (stop the bring-up first)
    py lds01_check.py COM3                       # Windows (pip install pyserial)

The packet format follows the hls_lfcd_lds_driver: 42 bytes = 0xFA, 0xA0 + index (0..59), speed
(2 bytes, rpm * 10), six readings of 6 bytes (intensity, range in mm, 2 reserved), 2 checksum bytes.
"""

import argparse
import sys
import time

PACKET = 42
PACKETS_PER_REV = 60
RANGE_MIN_MM = 120
RANGE_MAX_MM = 3500


def parse_packet(p):
    """Return (index, rpm, [(range_mm, intensity) x 6]) for a 42-byte packet, or None if the header is bad."""
    if len(p) != PACKET or p[0] != 0xFA or not 0xA0 <= p[1] < 0xA0 + PACKETS_PER_REV:
        return None
    rpm = (p[3] << 8 | p[2]) / 10
    readings = []
    for j in range(4, 40, 6):
        intensity = p[j + 1] << 8 | p[j]
        range_mm = p[j + 3] << 8 | p[j + 2]
        readings.append((range_mm, intensity))
    return p[1] - 0xA0, rpm, readings


class PacketStream:
    """Cuts packets out of the byte stream and counts what it had to throw away."""

    def __init__(self):
        self.buf = bytearray()
        self.received = 0
        self.discarded = 0

    def feed(self, data):
        """Add bytes and yield the parsed packets; resynchronises on 0xFA."""
        self.received += len(data)
        buf = self.buf
        buf += data
        while len(buf) >= PACKET + 1:
            if buf[0] != 0xFA:
                del buf[0]
                self.discarded += 1
                continue
            parsed = parse_packet(bytes(buf[:PACKET]))
            # A real packet is followed by the next 0xFA; otherwise this 0xFA was only a data byte.
            if parsed is None or buf[PACKET] != 0xFA:
                del buf[0]
                self.discarded += 1
                continue
            del buf[:PACKET]
            yield parsed


class Revolutions:
    """Collects packets into revolutions; a new one starts when the packet index does not increase."""

    def __init__(self):
        self.last_index = -1
        self.packets = {}
        self.rpms = []
        self.finished = []

    def add(self, index, rpm, readings):
        if index <= self.last_index:
            self._close()
        self.last_index = index
        self.packets[index] = readings
        self.rpms.append(rpm)

    def _close(self):
        valid = sum(1 for rs in self.packets.values() for r, _ in rs if RANGE_MIN_MM <= r <= RANGE_MAX_MM)
        rpm = sum(self.rpms) / len(self.rpms) if self.rpms else 0.0
        self.finished.append((len(self.packets), valid, rpm))
        self.packets = {}
        self.rpms = []
        return self.finished[-1]


def summarize(revolutions, seconds, stream=None):
    if not revolutions:
        return 'No complete revolution received.'
    n = len(revolutions)
    text = (f'{n} revolutions in {seconds:.1f} s = {n / seconds:.2f} per second (healthy: about 5). '
            f'Mean: {sum(r[0] for r in revolutions) / n:.1f} of {PACKETS_PER_REV} packets, '
            f'{sum(r[1] for r in revolutions) / n:.0f} of 360 valid readings, '
            f'{sum(r[2] for r in revolutions) / n:.0f} rpm (healthy: about 300).')
    if stream is not None and stream.received:
        text += ('\n' + f'Bytes: {stream.received / seconds:.0f} per second (healthy: about 12600), '
                 f'{100 * stream.discarded / stream.received:.1f} % discarded as unusable (healthy: about 0).')
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
                    packets, valid, rpm = revs.finished[shown]
                    print(f'revolution {shown + 1}: {packets}/{PACKETS_PER_REV} packets, '
                          f'{valid}/360 valid, {rpm:.0f} rpm')
                    shown += 1
        finally:
            port.write(b'e')   # stops the motor
    # The first revolution starts at a random packet, so it is partial and left out of the summary.
    print(summarize(revs.finished[1:], time.monotonic() - start, stream))


if __name__ == '__main__':
    main()
