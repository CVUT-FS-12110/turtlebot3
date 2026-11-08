import unittest

import numpy as np

from auto_mapper.frontiers import (
    choose_frontier, cluster_cells, downsample, find_frontiers, Frontier, frontier_mask,
    frontier_near, frontiers_near, Grid, nearest_reachable, reachable_distances)

FREE = 25


def make_grid(rows):
    """'.' free, '#' occupied, '?' unknown; first string is the top row (highest y)."""
    codes = {'.': 0, '#': 100, '?': -1}
    data = np.array([[codes[ch] for ch in row] for row in reversed(rows)], dtype=np.int8)
    return Grid(data, resolution=1.0, origin_x=0.0, origin_y=0.0)


class FrontierTest(unittest.TestCase):

    def test_mask_marks_free_cells_next_to_unknown(self):
        grid = make_grid(['??????',
                          '?....?',
                          '?....?',
                          '######'])
        mask = frontier_mask(grid.data, FREE)
        self.assertTrue(mask[1, 1] and mask[2, 4] and mask[2, 2])  # edge of the known area
        self.assertFalse(mask[1, 2])                                # surrounded by free cells
        self.assertFalse(mask[0, 2])                                # wall, not free
        self.assertFalse(mask[3, 0])                                # unknown is not a frontier

    def test_occupied_cells_are_not_frontiers(self):
        grid = make_grid(['?#?',
                          '?#?'])
        self.assertFalse(frontier_mask(grid.data, FREE).any())

    def test_clusters_are_8_connected(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[0, 0] = mask[1, 1] = True      # diagonal -> one cluster
        mask[3, 3] = True                   # separate
        sizes = sorted(len(c) for c in cluster_cells(mask))
        self.assertEqual(sizes, [1, 2])

    def test_unreachable_cells_are_infinite(self):
        grid = make_grid(['..#..',
                          '..#..'])
        dist = reachable_distances(grid.data, (0, 0), FREE)
        self.assertEqual(dist[0, 1], 1)
        self.assertTrue(np.isinf(dist[0, 3]))

    def test_frontier_behind_a_wall_is_ignored(self):
        grid = make_grid(['?..#..?',
                          '?..#..?'])
        found = find_frontiers(grid, (1.5, 0.5), min_size=1, free_threshold=FREE)
        self.assertEqual(len(found), 1)
        self.assertLess(found[0].x, 3.0)

    def test_small_frontiers_are_filtered(self):
        grid = make_grid(['#?#',
                          '#.#'])  # a single frontier cell
        self.assertEqual(find_frontiers(grid, (1.5, 0.5), min_size=2, free_threshold=FREE), [])
        self.assertEqual(len(find_frontiers(grid, (1.5, 0.5), min_size=1, free_threshold=FREE)), 1)

    def test_blacklist_removes_frontier(self):
        grid = make_grid(['?....',
                          '?....'])
        found = find_frontiers(grid, (3.5, 0.5), min_size=1, free_threshold=FREE)
        self.assertEqual(len(found), 1)
        again = find_frontiers(grid, (3.5, 0.5), min_size=1, free_threshold=FREE,
                               blacklist=[(found[0].x, found[0].y)], blacklist_radius=1.5)
        self.assertEqual(again, [])

    def test_blacklist_keeps_the_rest_of_a_long_frontier(self):
        grid = make_grid(['?.'] * 10)
        found = find_frontiers(grid, (1.5, 0.5), min_size=1, free_threshold=FREE,
                               blacklist=[(1.5, 0.5)], blacklist_radius=2.0)
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0].y, 2.0)

    def test_downsample_removes_gaps_between_scan_rays(self):
        grid = make_grid(['.?..',
                          '....',
                          '..#.',
                          '....'])
        small = downsample(grid, 2, FREE)
        self.assertEqual(small.resolution, 2.0)
        self.assertEqual(small.data.shape, (2, 2))
        self.assertFalse((small.data == -1).any())
        self.assertEqual(small.data[0, 1], 100)   # one occupied cell makes the block occupied
        self.assertEqual(small.data[1, 0], 0)     # one unknown cell does not make it unknown

    def test_downsample_pads_with_unknown(self):
        small = downsample(make_grid(['...']), 2, FREE)
        self.assertEqual(small.data.shape, (1, 2))
        self.assertEqual(small.data[0, 1], 0)

    def test_gap_narrower_than_the_robot_is_not_reachable(self):
        grid = make_grid(['#########',
                          '....#...?',
                          '.........',
                          '....#...?',
                          '#########'])
        self.assertEqual(len(find_frontiers(grid, (1.5, 2.5), 1, FREE)), 1)
        self.assertEqual(find_frontiers(grid, (1.5, 2.5), 1, FREE, clearance=1.0), [])

    def test_robot_next_to_a_wall_can_still_leave(self):
        grid = make_grid(['########',
                          '.......?',
                          '.......?',
                          '.......?',
                          '.......?',
                          '.......?',
                          '########'])
        found = find_frontiers(grid, (1.5, 5.5), 1, FREE, clearance=1.0)
        self.assertEqual(len(found), 1)

    def test_cells_under_the_robot_are_not_goals(self):
        grid = make_grid(['?????',
                          '?...?',
                          '?...?',
                          '?...?',
                          '?????'])
        robot = (2.5, 2.5)
        self.assertEqual(len(find_frontiers(grid, robot, 1, FREE)), 1)
        self.assertEqual(find_frontiers(grid, robot, 1, FREE, min_distance=2.0), [])

    def test_fully_explored_map_has_no_frontiers(self):
        grid = make_grid(['#####',
                          '#...#',
                          '#####'])
        self.assertEqual(find_frontiers(grid, (2.5, 1.5), min_size=1, free_threshold=FREE), [])

    def test_frontier_near(self):
        grid = make_grid(['?....#'])
        self.assertTrue(frontier_near(grid.data, 0, 1, FREE, 0))
        self.assertFalse(frontier_near(grid.data, 0, 3, FREE, 0))
        self.assertTrue(frontier_near(grid.data, 0, 3, FREE, 2))
        self.assertFalse(frontier_near(grid.data, 5, 5, FREE, 2))
        self.assertFalse(frontier_near(grid.data, -9, -9, FREE, 2))

    def test_choose_prefers_near_and_long(self):
        near_short = Frontier(0, 0, size=2, distance=1.0)
        far_long = Frontier(0, 0, size=40, distance=5.0)
        self.assertIs(choose_frontier([near_short, far_long], 0.0, 1.0), near_short)
        self.assertIs(choose_frontier([near_short, far_long], 0.5, 1.0), far_long)
        self.assertIsNone(choose_frontier([], 0.5, 1.0))

    def test_focus_pulls_the_choice_towards_a_point(self):
        near_robot = Frontier(0.0, 0.0, size=5, distance=1.0)
        near_focus = Frontier(6.0, 0.0, size=5, distance=4.0)
        self.assertIs(choose_frontier([near_robot, near_focus], 0.0, 1.0), near_robot)
        self.assertIs(choose_frontier([near_robot, near_focus], 0.0, 1.0, focus=(6.0, 0.0), focus_weight=1.0),
                      near_focus)
        # With no weight the focus changes nothing.
        self.assertIs(choose_frontier([near_robot, near_focus], 0.0, 1.0, focus=(6.0, 0.0), focus_weight=0.0),
                      near_robot)

    def test_frontiers_near_a_point(self):
        a, b = Frontier(0.0, 0.0, 5, 1.0), Frontier(3.0, 4.0, 5, 1.0)
        self.assertEqual(frontiers_near([a, b], (0.0, 0.0), 1.0), [a])
        self.assertEqual(frontiers_near([a, b], (0.0, 0.0), 5.0), [a, b])
        self.assertEqual(frontiers_near([], (0.0, 0.0), 5.0), [])

    def test_nearest_reachable_cell(self):
        grid = make_grid(['..#..',
                          '..#..'])
        dist = reachable_distances(grid.data, (0, 0), FREE)
        self.assertEqual(nearest_reachable(dist, (0, 1), 2), (0, 1))     # reachable itself
        self.assertEqual(nearest_reachable(dist, (0, 2), 2), (0, 1))     # the wall: the nearest free cell
        self.assertIsNone(nearest_reachable(dist, (0, 4), 1))            # only the cut-off side near
        self.assertIsNone(nearest_reachable(dist, (9, 9), 2))            # outside the grid


if __name__ == '__main__':
    unittest.main()
