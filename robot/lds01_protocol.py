"""The LDS-01 serial protocol. Pure Python, no ROS and no pyserial, so it can be tested anywhere.

The sensor streams 42-byte packets at 230400 baud: 0xFA, 0xA0 + index (0..59), speed (2 bytes,
rpm * 10), six readings of 6 bytes (intensity, range in mm, 2 reserved) and 2 checksum bytes. The 60
packets of one revolution give 360 readings.

The stock hls_lfcd_lds_driver cuts a revolution out of the stream at fixed 42-byte positions, so a
single lost byte spoils the whole revolution. Here every packet is recognised on its own and placed
by its index, which keeps whatever arrives.
"""

PACKET = 42
PACKETS_PER_REV = 60
READINGS_PER_PACKET = 6
RANGE_MIN_MM = 120
RANGE_MAX_MM = 3500
RPM_MIN = 200.0   # speeds outside this window come from corrupted packets
RPM_MAX = 400.0


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


class Revolution:
    """The packets of one turn of the sensor, by packet index."""

    def __init__(self, packets, rpm):
        self.packets = packets
        self.rpm = rpm

    @property
    def packet_count(self):
        return len(self.packets)

    @property
    def valid_count(self):
        return sum(1 for rs in self.packets.values() for r, _ in rs if RANGE_MIN_MM <= r <= RANGE_MAX_MM)


class Revolutions:
    """Collects packets into revolutions; a new one starts when the packet index does not increase."""

    def __init__(self):
        self.last_index = -1
        self.packets = {}
        self.rpms = []
        self.finished = []
        self.rejected = 0   # packets with an impossible speed (corrupted)

    def add(self, index, rpm, readings):
        """Add a packet. Returns the finished Revolution when this packet starts the next one, else None."""
        if not RPM_MIN <= rpm <= RPM_MAX:
            self.rejected += 1
            return None
        done = self._close() if index <= self.last_index else None
        self.last_index = index
        self.packets[index] = readings
        self.rpms.append(rpm)
        return done

    def _close(self):
        rpm = sum(self.rpms) / len(self.rpms) if self.rpms else 0.0
        rev = Revolution(self.packets, rpm)
        self.finished.append(rev)
        self.packets = {}
        self.rpms = []
        return rev


def revolution_to_scan(rev, range_min_m=RANGE_MIN_MM / 1000, range_max_m=RANGE_MAX_MM / 1000):
    """Return (ranges, intensities), 360 values each, in the order of sensor_msgs/LaserScan.

    Readings that did not arrive or are out of range are 0.0, like in the stock driver. The sensor
    turns clockwise, so reading n goes to position 359 - n.
    """
    ranges = [0.0] * 360
    intensities = [0.0] * 360
    for index, readings in rev.packets.items():
        for k, (range_mm, intensity) in enumerate(readings):
            position = 359 - (READINGS_PER_PACKET * index + k)
            metres = range_mm / 1000.0
            if range_min_m <= metres <= range_max_m:
                ranges[position] = metres
            intensities[position] = float(intensity)
    return ranges, intensities
