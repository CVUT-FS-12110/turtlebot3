"""Pure Python, runs anywhere: python3 -m unittest discover -s robot/test"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lds01_protocol as P  # noqa: E402


def packet(index, rpm10=3000, range_mm=1500, valid=6):
    p = bytearray(P.PACKET)
    p[0] = 0xFA
    p[1] = 0xA0 + index
    p[2] = rpm10 & 0xFF
    p[3] = rpm10 >> 8
    for k in range(6):
        j = 4 + 6 * k
        r = range_mm + 10 * k if k < valid else 0
        p[j] = 100
        p[j + 2] = r & 0xFF
        p[j + 3] = r >> 8
    return bytes(p)


def revolution(skip=(), **kw):
    return b''.join(packet(i, **kw) for i in range(60) if i not in skip)


def run(data, chunk=None):
    """Feed bytes through PacketStream and Revolutions; returns (stream, revs, finished list)."""
    stream, revs, done = P.PacketStream(), P.Revolutions(), []
    pos = 0
    while pos < len(data):
        n = chunk or len(data)
        for idx, rpm, rd in stream.feed(data[pos:pos + n]):
            rev = revs.add(idx, rpm, rd)
            if rev:
                done.append(rev)
        pos += n
    return stream, revs, done


class ParsePacketTest(unittest.TestCase):

    def test_good_packet(self):
        index, rpm, readings = P.parse_packet(packet(7))
        self.assertEqual(index, 7)
        self.assertEqual(rpm, 300.0)
        self.assertEqual(readings[0], (1500, 100))
        self.assertEqual(len(readings), 6)

    def test_bad_header_or_length(self):
        self.assertIsNone(P.parse_packet(b'\x00' * 42))
        self.assertIsNone(P.parse_packet(packet(3)[:41]))
        bad_index = bytearray(packet(3))
        bad_index[1] = 0xA0 + 60
        self.assertIsNone(P.parse_packet(bytes(bad_index)))


class StreamTest(unittest.TestCase):

    def test_garbage_before_the_stream_is_skipped_and_counted(self):
        garbage = b'\x12\xFA\x00junk\xFA\xA5'
        stream, _, done = run(garbage + revolution() * 3, chunk=37)
        self.assertEqual(stream.discarded, len(garbage))
        self.assertEqual([r.packet_count for r in done], [60, 60])

    def test_lost_packets_do_not_spoil_the_others(self):
        _, _, done = run(revolution() + revolution(skip=range(0, 60, 6)) + revolution() * 2)
        self.assertEqual([r.packet_count for r in done], [60, 50, 60])

    def test_truncated_packet_is_discarded_and_the_stream_recovers(self):
        broken = packet(10)[:30]          # 12 bytes lost in the middle of a packet
        data = revolution() + packet(0) + packet(1) + packet(2) + broken + b''.join(packet(i) for i in range(11, 60)) + revolution() * 2
        stream, _, done = run(data, chunk=100)
        self.assertGreater(stream.discarded, 0)
        self.assertEqual(done[1].packet_count, 3 + 49)   # packets 0-2 and 11-59; 10 is lost


class RevolutionsTest(unittest.TestCase):

    def test_impossible_speed_is_rejected(self):
        revs = P.Revolutions()
        self.assertIsNone(revs.add(0, 1138.0, [(1000, 1)] * 6))
        self.assertEqual(revs.rejected, 1)
        self.assertEqual(revs.packets, {})

    def test_valid_count_uses_the_range_window(self):
        revs = P.Revolutions()
        revs.add(0, 300.0, [(1000, 1), (50, 1), (3600, 1), (0, 1), (3500, 1), (120, 1)])
        rev = revs.add(0, 300.0, [(1000, 1)] * 6)
        self.assertEqual(rev.valid_count, 3)   # 1000, 3500 and 120 are inside 120..3500 mm


class ScanTest(unittest.TestCase):

    def test_positions_follow_the_stock_driver(self):
        revs = P.Revolutions()
        revs.add(0, 300.0, [(1000 + 100 * k, 5) for k in range(6)])
        revs.add(59, 300.0, [(2000, 7)] * 6)
        rev = revs.add(0, 300.0, [(1000, 1)] * 6)
        ranges, intensities = P.revolution_to_scan(rev)
        self.assertEqual(len(ranges), 360)
        self.assertAlmostEqual(ranges[359], 1.0)      # reading 0 -> position 359
        self.assertAlmostEqual(ranges[354], 1.5)      # reading 5 -> position 354
        self.assertAlmostEqual(ranges[0], 2.0)        # packet 59, reading 5 -> position 0
        self.assertEqual(intensities[359], 5.0)
        self.assertEqual(ranges[200], 0.0)            # missing packet -> 0.0

    def test_out_of_range_readings_become_zero(self):
        revs = P.Revolutions()
        revs.add(0, 300.0, [(50, 1), (4000, 1), (0, 1), (500, 1), (60000, 1), (120, 1)])
        ranges, _ = P.revolution_to_scan(revs.add(0, 300.0, [(1, 1)] * 6))
        self.assertEqual([ranges[359 - k] for k in range(6)], [0.0, 0.0, 0.0, 0.5, 0.0, 0.12])


class LossyStreamTest(unittest.TestCase):

    def test_robust_reading_keeps_most_of_a_lossy_stream(self):
        random.seed(3)
        data = bytearray()
        for _ in range(20):
            for i in range(60):
                p = bytearray(packet(i))
                roll = random.random()
                if roll < 0.15:
                    continue                      # packet lost
                if roll < 0.30:
                    del p[random.randrange(2, 40)]  # one byte lost inside the packet
                data += p
        stream, revs, done = run(bytes(data), chunk=173)
        kept = sum(r.packet_count for r in done) / (60 * len(done))
        self.assertGreater(kept, 0.6)             # about 70 % of the packets are intact
        self.assertGreater(len(done), 15)         # and nearly every revolution is still published


if __name__ == '__main__':
    unittest.main()
