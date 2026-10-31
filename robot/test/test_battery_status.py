"""Run on a machine with ROS 2: python3 -m unittest discover -s robot/test"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from battery_status import format_stale, format_status  # noqa: E402

WARN, CRIT = 11.0, 10.5


class FormatTest(unittest.TestCase):

    def test_full_battery_is_plain_black_on_the_bar_background(self):
        line = format_status(12.4, 0.95, WARN, CRIT)
        self.assertTrue(line.startswith('#[fg=colour16]'))
        self.assertNotIn('bg=', line)
        self.assertNotIn('bold', line)   # bold black turns grey in many terminals
        self.assertIn('Battery: 12.4 V 95 %', line)

    def test_colour_styles_set_foreground_and_background(self):
        # The default tmux status bar is green; text with only a foreground colour can vanish on it.
        for line in (format_status(10.9, 0.3, WARN, CRIT), format_status(10.2, 0.0, WARN, CRIT),
                     format_stale(7)):
            style = line[line.index('#[') + 2:line.index(']')]
            self.assertIn('fg=', style)
            self.assertIn('bg=', style)

    def test_below_warning_is_yellow(self):
        self.assertIn('bg=yellow', format_status(10.9, 0.30, WARN, CRIT))

    def test_below_critical_is_red_and_says_low(self):
        line = format_status(10.2, 0.05, WARN, CRIT)
        self.assertIn('bg=red', line)
        self.assertIn('Battery LOW: 10.2 V', line)

    def test_limits_belong_to_the_better_state(self):
        self.assertTrue(format_status(11.0, 0.5, WARN, CRIT).startswith('#[fg=colour16]'))
        self.assertIn('bg=yellow', format_status(10.5, 0.5, WARN, CRIT))

    def test_percentage_given_in_percent_is_kept(self):
        self.assertIn('87 %', format_status(11.8, 87.0, WARN, CRIT))

    def test_stale_line(self):
        self.assertIn('no data (12 s)', format_stale(12.3))


if __name__ == '__main__':
    unittest.main()
