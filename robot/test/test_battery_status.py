"""Run on a machine with ROS 2: python3 -m unittest discover -s robot/test"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from battery_status import format_stale, format_status  # noqa: E402

WARN, CRIT = 11.0, 10.5


class FormatTest(unittest.TestCase):

    def test_full_battery_is_green(self):
        line = format_status(12.4, 0.95, WARN, CRIT)
        self.assertIn('fg=green', line)
        self.assertIn('12.4 V 95 %', line)

    def test_below_warning_is_yellow(self):
        self.assertIn('bg=yellow', format_status(10.9, 0.30, WARN, CRIT))

    def test_below_critical_is_red_and_says_low(self):
        line = format_status(10.2, 0.05, WARN, CRIT)
        self.assertIn('bg=red', line)
        self.assertIn('BAT LOW', line)

    def test_limits_belong_to_the_better_state(self):
        self.assertIn('fg=green', format_status(11.0, 0.5, WARN, CRIT))
        self.assertIn('bg=yellow', format_status(10.5, 0.5, WARN, CRIT))

    def test_percentage_given_in_percent_is_kept(self):
        self.assertIn('87 %', format_status(11.8, 87.0, WARN, CRIT))

    def test_stale_line(self):
        self.assertIn('no data (12 s)', format_stale(12.3))


if __name__ == '__main__':
    unittest.main()
