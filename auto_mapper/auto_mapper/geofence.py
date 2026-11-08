"""Geofence polygon geometry. Pure numpy, no ROS imports, so it can be unit-tested."""

import json
import math
import os

import numpy as np

from auto_mapper.frontiers import Grid

FREE = 0
OCCUPIED = 100
MAX_COST = 98     # the Nav2 costmap turns mask values below 100 into costs; 99 and more is nearly inscribed


def polygon_area(polygon):
    """Absolute area by the shoelace formula."""
    total = 0.0
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _cross(a, b, c, d):
    """Do the segments a-b and c-d cross in a single interior point?"""
    return _orient(a, b, c) * _orient(a, b, d) < 0 and _orient(c, d, a) * _orient(c, d, b) < 0


def validate(polygon, min_area=0.05):
    """None for a usable polygon, else a sentence saying what is wrong with it."""
    n = len(polygon)
    if n < 3:
        return f'it needs at least 3 vertices, it has {n}'
    # Crossing first: the signed areas of a bow tie cancel out, so its area would look too small.
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue    # neighbouring edges meet in a vertex
            if _cross(polygon[i], polygon[(i + 1) % n], polygon[j], polygon[(j + 1) % n]):
                return 'its edges cross each other'
    if polygon_area(polygon) < min_area:
        return f'its area is under {min_area} m2'
    return None


def closes_polygon(vertices, point, radius):
    """A click within radius metres of the first of at least 3 vertices closes the polygon."""
    return len(vertices) >= 3 and math.hypot(point[0] - vertices[0][0], point[1] - vertices[0][1]) < radius


def points_inside(xs, ys, polygon):
    """Boolean array: is each point (xs[i], ys[i]) inside the polygon? Ray casting, any array shape."""
    xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    inside = np.zeros(xs.shape, dtype=bool)
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        if y1 == y2:
            continue
        crosses = (y1 > ys) != (y2 > ys)
        x_at = x1 + (ys - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (xs < x_at)
    return inside


def contains(polygon, point, margin=0.0):
    """Is the point inside the polygon, and at least margin metres from its edge?"""
    x, y = np.array([point[0]]), np.array([point[1]])
    return bool(points_inside(x, y, polygon)[0] and distance_to_edges(x, y, polygon)[0] >= margin)


def distance_to_edges(xs, ys, polygon):
    """Distance of each point to the nearest polygon edge, in metres."""
    xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    nearest = np.full(xs.shape, np.inf)
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else np.clip(((xs - x1) * dx + (ys - y1) * dy) / length2, 0.0, 1.0)
        nearest = np.minimum(nearest, np.hypot(xs - (x1 + t * dx), ys - (y1 + t * dy)))
    return nearest


def _cell_centres(rows, cols, resolution, origin_x, origin_y):
    xs = origin_x + (np.arange(cols) + 0.5) * resolution
    ys = origin_y + (np.arange(rows) + 0.5) * resolution
    return np.meshgrid(xs, ys)


def allowed_mask(grid, polygon, margin):
    """Cells of the grid the robot may use: inside the polygon and at least margin metres from its edge."""
    xs, ys = _cell_centres(*grid.data.shape, grid.resolution, grid.origin_x, grid.origin_y)
    return points_inside(xs, ys, polygon) & (distance_to_edges(xs, ys, polygon) >= margin)


def keepout_mask(polygon, resolution, extra, ramp=0.0):
    """Mask for the Nav2 keepout filter as a Grid: 100 (lethal) outside the polygon, a cost inside.

    The filter does not inflate. Without a ramp the planner and the controller would take the centre of
    the robot right up to the edge, with its body across the line. Inside, the value therefore grows from
    0 at ramp metres from the edge to MAX_COST at the edge, which the filter turns into a costmap cost.
    MAX_COST stays below the inscribed cost, so a robot that ends up at the edge can still drive off; a
    lethal strip inside the edge trapped it ("No valid trajectories").

    The filter changes only the costmap cells the mask covers, so the mask reaches extra metres past the
    polygon on every side. Beyond that the costmap is not filtered.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    origin_x, origin_y = min(xs) - extra, min(ys) - extra
    cols = int(math.ceil((max(xs) + extra - origin_x) / resolution))
    rows = int(math.ceil((max(ys) + extra - origin_y) / resolution))
    cx, cy = _cell_centres(rows, cols, resolution, origin_x, origin_y)
    inside = points_inside(cx, cy, polygon)
    data = np.full((rows, cols), OCCUPIED, dtype=np.int8)
    if ramp > 0:
        depth = distance_to_edges(cx, cy, polygon)
        cost = np.rint(MAX_COST * np.clip(1.0 - depth / ramp, 0.0, 1.0)).astype(np.int8)
        data[inside] = cost[inside]
    else:
        data[inside] = FREE
    return Grid(data, resolution, origin_x, origin_y)


def save_polygon(path, polygon):
    """Write the polygon as JSON, so a restarted explorer can use it again."""
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'polygon': [[float(x), float(y)] for x, y in polygon]}, f)


def load_polygon(path):
    """The polygon saved by save_polygon as [(x, y), ...]; None if the file is missing or not usable."""
    try:
        with open(os.path.expanduser(path), encoding='utf-8') as f:
            polygon = [(float(x), float(y)) for x, y in json.load(f)['polygon']]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return polygon or None


def remove_polygon(path):
    try:
        os.remove(os.path.expanduser(path))
    except OSError:
        pass
