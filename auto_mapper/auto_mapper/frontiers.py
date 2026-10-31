"""Frontier detection on an occupancy grid. Pure numpy, no ROS imports, so it can be unit-tested."""

from collections import deque
from dataclasses import dataclass
import math

import numpy as np

UNKNOWN = -1

_NEIGHBORS_4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
_NEIGHBORS_8 = _NEIGHBORS_4 + ((-1, -1), (-1, 1), (1, -1), (1, 1))


@dataclass(frozen=True)
class Grid:
    """Occupancy grid in the layout of nav_msgs/OccupancyGrid: data[row, col], row 0 at origin_y."""

    data: np.ndarray
    resolution: float
    origin_x: float
    origin_y: float

    def world_to_cell(self, x, y):
        return (int(math.floor((y - self.origin_y) / self.resolution)),
                int(math.floor((x - self.origin_x) / self.resolution)))

    def cell_to_world(self, row, col):
        return (self.origin_x + (col + 0.5) * self.resolution,
                self.origin_y + (row + 0.5) * self.resolution)

    def in_bounds(self, row, col):
        return 0 <= row < self.data.shape[0] and 0 <= col < self.data.shape[1]


@dataclass(frozen=True)
class Frontier:
    x: float
    y: float
    size: int
    distance: float


def frontier_mask(data, free_threshold):
    """Free cells that touch an unknown cell (4-neighbourhood)."""
    free = (data >= 0) & (data < free_threshold)
    unknown = data == UNKNOWN
    near_unknown = np.zeros_like(unknown)
    near_unknown[1:, :] |= unknown[:-1, :]
    near_unknown[:-1, :] |= unknown[1:, :]
    near_unknown[:, 1:] |= unknown[:, :-1]
    near_unknown[:, :-1] |= unknown[:, 1:]
    return free & near_unknown


def is_frontier_cell(data, row, col, free_threshold):
    if not (0 <= row < data.shape[0] and 0 <= col < data.shape[1]):
        return False
    if not 0 <= data[row, col] < free_threshold:
        return False
    for dr, dc in _NEIGHBORS_4:
        r, c = row + dr, col + dc
        if 0 <= r < data.shape[0] and 0 <= c < data.shape[1] and data[r, c] == UNKNOWN:
            return True
    return False


def cluster_cells(mask):
    """Group True cells into 8-connected clusters; returns a list of lists of (row, col)."""
    visited = np.zeros_like(mask, dtype=bool)
    clusters = []
    for start in zip(*np.nonzero(mask)):
        start = (int(start[0]), int(start[1]))
        if visited[start]:
            continue
        visited[start] = True
        queue = deque([start])
        cells = []
        while queue:
            row, col = queue.popleft()
            cells.append((row, col))
            for dr, dc in _NEIGHBORS_8:
                r, c = row + dr, col + dc
                if (0 <= r < mask.shape[0] and 0 <= c < mask.shape[1]
                        and mask[r, c] and not visited[r, c]):
                    visited[r, c] = True
                    queue.append((r, c))
        clusters.append(cells)
    return clusters


def reachable_distances(data, start, free_threshold):
    """BFS over free cells from start (4-neighbourhood); returns path length in cells, inf if unreachable."""
    dist = np.full(data.shape, np.inf)
    if not (0 <= start[0] < data.shape[0] and 0 <= start[1] < data.shape[1]):
        return dist
    passable = (data >= 0) & (data < free_threshold)
    dist[start] = 0
    queue = deque([start])
    while queue:
        row, col = queue.popleft()
        d = dist[row, col] + 1
        for dr, dc in _NEIGHBORS_4:
            r, c = row + dr, col + dc
            if (0 <= r < data.shape[0] and 0 <= c < data.shape[1]
                    and passable[r, c] and d < dist[r, c]):
                dist[r, c] = d
                queue.append((r, c))
    return dist


def find_frontiers(grid, robot_xy, min_size, free_threshold, blacklist=(), blacklist_radius=0.5):
    """Reachable frontier clusters of at least min_size cells, away from blacklisted points.

    The target of a cluster is its reachable cell closest to the cluster centroid.
    """
    data = grid.data
    start = grid.world_to_cell(*robot_xy)
    dist = reachable_distances(data, start, free_threshold)
    frontiers = []
    for cells in cluster_cells(frontier_mask(data, free_threshold)):
        if len(cells) < min_size:
            continue
        reachable = [cell for cell in cells if np.isfinite(dist[cell])]
        if not reachable:
            continue
        centroid = np.mean(reachable, axis=0)
        row, col = min(reachable, key=lambda cell: (cell[0] - centroid[0]) ** 2 + (cell[1] - centroid[1]) ** 2)
        x, y = grid.cell_to_world(row, col)
        if any(math.hypot(x - bx, y - by) < blacklist_radius for bx, by in blacklist):
            continue
        frontiers.append(Frontier(x, y, len(cells), float(dist[row, col]) * grid.resolution))
    return frontiers


def choose_frontier(frontiers, size_weight, resolution):
    """Cheapest frontier: path length minus a bonus for the frontier length (both in metres)."""
    if not frontiers:
        return None
    return min(frontiers, key=lambda f: f.distance - size_weight * f.size * resolution)
