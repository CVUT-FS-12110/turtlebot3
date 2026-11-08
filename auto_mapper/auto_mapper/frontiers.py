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


def downsample(grid, factor, free_threshold):
    """Merge factor x factor blocks: occupied if any cell is, else free if any cell is, else unknown.

    Single unknown cells between the rays of a scan vanish, so they do not count as frontiers.
    """
    if factor <= 1:
        return grid
    height, width = grid.data.shape
    rows, cols = -(-height // factor), -(-width // factor)
    padded = np.full((rows * factor, cols * factor), UNKNOWN, dtype=grid.data.dtype)
    padded[:height, :width] = grid.data
    blocks = padded.reshape(rows, factor, cols, factor)
    known = blocks >= 0
    occupied = (blocks >= free_threshold).any(axis=(1, 3))
    free = (known & (blocks < free_threshold)).any(axis=(1, 3))
    data = np.full((rows, cols), UNKNOWN, dtype=grid.data.dtype)
    data[free] = 0
    data[occupied] = 100
    return Grid(data, grid.resolution * factor, grid.origin_x, grid.origin_y)


def _disk(radius):
    return [(dr, dc) for dr in range(-radius, radius + 1) for dc in range(-radius, radius + 1)
            if dr * dr + dc * dc <= radius * radius]


def near_occupied(data, free_threshold, radius):
    """Cells within radius cells of an occupied cell."""
    occupied = data >= free_threshold
    near = occupied.copy()
    height, width = data.shape
    for dr, dc in _disk(radius):
        near[max(dr, 0):height + min(dr, 0), max(dc, 0):width + min(dc, 0)] |=             occupied[max(-dr, 0):height + min(-dr, 0), max(-dc, 0):width + min(-dc, 0)]
    return near


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


def frontier_near(data, row, col, free_threshold, radius):
    """Is there a frontier cell within radius cells (a square) of the given cell?

    Checking only the cell itself is too strict: frontier edges shift a little with every map update.
    """
    window = frontier_mask(data, free_threshold)[max(row - radius, 0):max(row + radius + 1, 0),
                                                 max(col - radius, 0):max(col + radius + 1, 0)]
    return bool(window.any())


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


def reachable_distances(data, start, free_threshold, clearance_cells=0):
    """BFS over free cells from start (4-neighbourhood); returns path length in cells, inf if unreachable.

    Cells closer than clearance_cells to an obstacle are not passable, except around the start, so a
    robot standing next to a wall can still leave.
    """
    dist = np.full(data.shape, np.inf)
    if not (0 <= start[0] < data.shape[0] and 0 <= start[1] < data.shape[1]):
        return dist
    free = (data >= 0) & (data < free_threshold)
    passable = free
    if clearance_cells > 0:
        passable = free & ~near_occupied(data, free_threshold, clearance_cells)
        for dr, dc in _disk(clearance_cells + 1):
            r, c = start[0] + dr, start[1] + dc
            if 0 <= r < data.shape[0] and 0 <= c < data.shape[1]:
                passable[r, c] = free[r, c]
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


def find_frontiers(grid, robot_xy, min_size, free_threshold, blacklist=(), blacklist_radius=0.5,
                   clearance=0.0, min_distance=0.0):
    """Reachable frontier clusters of at least min_size cells.

    The target of a cluster is the usable cell closest to the centroid of the usable cells. A cell is
    usable if the robot fits there (clearance, metres), it is not within min_distance metres of the
    robot (Nav2 would report such a goal as reached without moving) and not near a blacklisted point.
    A cluster without a usable cell is left out.
    """
    data = grid.data
    start = grid.world_to_cell(*robot_xy)
    clearance_cells = int(math.ceil(clearance / grid.resolution))
    dist = reachable_distances(data, start, free_threshold, clearance_cells)
    frontiers = []
    for cells in cluster_cells(frontier_mask(data, free_threshold)):
        if len(cells) < min_size:
            continue
        usable = []
        for cell in cells:
            if not np.isfinite(dist[cell]):
                continue
            x, y = grid.cell_to_world(*cell)
            if math.hypot(x - robot_xy[0], y - robot_xy[1]) < min_distance:
                continue
            if any(math.hypot(x - bx, y - by) < blacklist_radius for bx, by in blacklist):
                continue
            usable.append(cell)
        if not usable:
            continue
        centroid = np.mean(usable, axis=0)
        row, col = min(usable, key=lambda cell: (cell[0] - centroid[0]) ** 2 + (cell[1] - centroid[1]) ** 2)
        x, y = grid.cell_to_world(row, col)
        frontiers.append(Frontier(x, y, len(cells), float(dist[row, col]) * grid.resolution))
    return frontiers


def choose_frontier(frontiers, size_weight, resolution):
    """Cheapest frontier: path length minus a bonus for the frontier length (both in metres)."""
    if not frontiers:
        return None
    return min(frontiers, key=lambda f: f.distance - size_weight * f.size * resolution)
