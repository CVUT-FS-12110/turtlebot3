import unittest

import numpy as np

from auto_mapper.frontiers import (
    choose_frontier, cluster_cells, find_frontiers, Frontier, frontier_mask, Grid,
    is_frontier_cell, reachable_distances)

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
                               blacklist=[(found[0].x, found[0].y)], blacklist_radius=0.5)
        self.assertEqual(again, [])

    def test_fully_explored_map_has_no_frontiers(self):
        grid = make_grid(['#####',
                          '#...#',
                          '#####'])
        self.assertEqual(find_frontiers(grid, (2.5, 1.5), min_size=1, free_threshold=FREE), [])

    def test_is_frontier_cell(self):
        grid = make_grid(['?..#'])
        self.assertTrue(is_frontier_cell(grid.data, 0, 1, FREE))
        self.assertFalse(is_frontier_cell(grid.data, 0, 2, FREE))
        self.assertFalse(is_frontier_cell(grid.data, 5, 5, FREE))

    def test_choose_prefers_near_and_long(self):
        near_short = Frontier(0, 0, size=2, distance=1.0)
        far_long = Frontier(0, 0, size=40, distance=5.0)
        self.assertIs(choose_frontier([near_short, far_long], 0.0, 1.0), near_short)
        self.assertIs(choose_frontier([near_short, far_long], 0.5, 1.0), far_long)
        self.assertIsNone(choose_frontier([], 0.5, 1.0))


if __name__ == '__main__':
    unittest.main()
