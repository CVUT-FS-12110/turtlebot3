import unittest

import numpy as np

from auto_mapper.frontiers import find_frontiers, Grid
from auto_mapper.geofence import (
    allowed_mask, closes_polygon, contains, distance_to_edges, keepout_mask, points_inside,
    polygon_area, validate)

FREE = 25
SQUARE = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
L_SHAPE = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)]


class PolygonTest(unittest.TestCase):

    def test_area(self):
        self.assertAlmostEqual(polygon_area(SQUARE), 16.0)
        self.assertAlmostEqual(polygon_area(SQUARE[::-1]), 16.0)    # orientation does not matter
        self.assertAlmostEqual(polygon_area(L_SHAPE), 12.0)

    def test_inside_outside(self):
        self.assertTrue(contains(SQUARE, (2.0, 2.0)))
        self.assertFalse(contains(SQUARE, (5.0, 2.0)))
        self.assertFalse(contains(SQUARE, (-0.1, 2.0)))
        self.assertFalse(contains(SQUARE, (2.0, 4.1)))

    def test_concave_polygon(self):
        self.assertTrue(contains(L_SHAPE, (1.0, 3.0)))
        self.assertTrue(contains(L_SHAPE, (3.0, 1.0)))
        self.assertFalse(contains(L_SHAPE, (3.0, 3.0)))     # the notch

    def test_points_inside_works_on_arrays(self):
        xs, ys = np.meshgrid([1.0, 5.0], [1.0, 3.0])
        self.assertEqual(points_inside(xs, ys, SQUARE).tolist(), [[True, False], [True, False]])

    def test_distance_to_edges(self):
        d = distance_to_edges(np.array([2.0, 1.0, 6.0]), np.array([2.0, 0.5, 2.0]), SQUARE)
        self.assertAlmostEqual(d[0], 2.0)
        self.assertAlmostEqual(d[1], 0.5)
        self.assertAlmostEqual(d[2], 2.0)

    def test_valid_polygons(self):
        self.assertIsNone(validate(SQUARE))
        self.assertIsNone(validate(L_SHAPE))
        self.assertIsNone(validate(SQUARE[::-1]))

    def test_invalid_polygons(self):
        self.assertIn('3 vertices', validate([(0.0, 0.0), (1.0, 0.0)]))
        self.assertIn('area', validate([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]))
        bow_tie = [(0.0, 0.0), (4.0, 4.0), (4.0, 0.0), (0.0, 4.0)]
        self.assertIn('cross', validate(bow_tie))

    def test_click_near_the_first_vertex_closes(self):
        self.assertFalse(closes_polygon([], (0.0, 0.0), 0.3))
        self.assertFalse(closes_polygon(SQUARE[:2], (0.0, 0.1), 0.3))   # too few vertices
        self.assertTrue(closes_polygon(SQUARE, (0.1, 0.1), 0.3))
        self.assertFalse(closes_polygon(SQUARE, (0.5, 0.5), 0.3))


class MaskTest(unittest.TestCase):

    def test_allowed_mask_keeps_a_margin_from_the_edge(self):
        grid = Grid(np.zeros((6, 6), dtype=np.int8), resolution=1.0, origin_x=-1.0, origin_y=-1.0)
        allowed = allowed_mask(grid, SQUARE, margin=1.0)
        # Cell centres are at -0.5 .. 4.5; only the ones 1 m or more inside remain.
        self.assertEqual(int(allowed.sum()), 4)
        self.assertTrue(allowed[2:4, 2:4].all())
        self.assertFalse(allowed[0, :].any() or allowed[:, 0].any())

    def test_keepout_mask_is_free_inside_and_occupied_outside(self):
        mask = keepout_mask(SQUARE, resolution=0.5, extra=2.0)
        self.assertEqual(mask.data.shape, (16, 16))
        self.assertEqual((mask.origin_x, mask.origin_y), (-2.0, -2.0))
        self.assertEqual(mask.data.dtype, np.int8)
        row, col = mask.world_to_cell(2.0, 2.0)
        self.assertEqual(mask.data[row, col], 0)
        row, col = mask.world_to_cell(-1.0, 2.0)
        self.assertEqual(mask.data[row, col], 100)
        self.assertEqual(set(np.unique(mask.data)), {0, 100})

    def test_keepout_mask_ramps_up_towards_the_edge(self):
        mask = keepout_mask(SQUARE, resolution=0.5, extra=2.0, ramp=1.0)
        value = lambda x, y: mask.data[mask.world_to_cell(x, y)]
        self.assertEqual(value(2.0, 2.0), 0)        # deeper than the ramp
        self.assertEqual(value(1.25, 2.0), 0)       # 1.25 m from the edge
        self.assertAlmostEqual(int(value(0.75, 2.0)), 24.5, delta=1)    # 0.75 m: a quarter of the way up
        self.assertAlmostEqual(int(value(0.25, 2.0)), 73.5, delta=1)    # 0.25 m: three quarters
        self.assertEqual(value(-1.0, 2.0), 100)     # outside stays lethal
        self.assertLess(mask.data[mask.data < 100].max(), 99)   # inside never reaches the inscribed cost

    def test_contains_with_a_margin(self):
        self.assertTrue(contains(SQUARE, (0.3, 2.0)))
        self.assertTrue(contains(SQUARE, (0.3, 2.0), 0.2))
        self.assertFalse(contains(SQUARE, (0.3, 2.0), 0.5))
        self.assertFalse(contains(SQUARE, (-0.3, 2.0), 0.0))

    def test_explorer_stays_inside_the_geofence(self):
        # A corridor with unknown space at both ends; the fence covers only the left half.
        grid = Grid(np.array([[-1] + [0] * 8 + [-1]], dtype=np.int8), 1.0, 0.0, 0.0)
        robot = (4.5, 0.5)
        self.assertEqual(len(find_frontiers(grid, robot, 1, FREE)), 2)
        fence = [(-1.0, -1.0), (5.0, -1.0), (5.0, 2.0), (-1.0, 2.0)]
        allowed = allowed_mask(grid, fence, margin=0.0)
        found = find_frontiers(grid, robot, 1, FREE, allowed=allowed)
        self.assertEqual(len(found), 1)
        self.assertLess(found[0].x, 2.0)

    def test_geofence_blocks_the_way_to_a_frontier(self):
        # The frontier in the top right corner is inside the fence, but the way there leads through
        # the band that is outside. The cells next to the robot are exempt, so the band is 3 cells wide.
        rows = np.zeros((7, 5), dtype=np.int8)
        rows[6, 4] = -1
        grid = Grid(rows, 1.0, 0.0, 0.0)
        robot = (0.5, 0.5)
        self.assertEqual(len(find_frontiers(grid, robot, 1, FREE)), 1)
        allowed = np.ones(grid.data.shape, dtype=bool)
        allowed[2:5, :] = False
        self.assertEqual(find_frontiers(grid, robot, 1, FREE, allowed=allowed), [])

    def test_robot_at_the_fence_can_still_leave(self):
        grid = Grid(np.array([[0, 0, 0, 0, -1]], dtype=np.int8), 1.0, 0.0, 0.0)
        allowed = np.array([[False, False, True, True, True]])   # the robot (cell 0) is in the margin
        found = find_frontiers(grid, (0.5, 0.5), 1, FREE, allowed=allowed)
        self.assertEqual(len(found), 1)


if __name__ == '__main__':
    unittest.main()
