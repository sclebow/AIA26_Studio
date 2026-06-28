"""Shared geometry helpers for the optimization scorers (pure, no deps beyond math)."""
from __future__ import annotations

import math
from typing import Any


def centroid(b: list[list[float]]) -> tuple[float, float]:
    pts = [p for p in b if len(p) >= 2]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def extent(b: list[list[float]]) -> tuple[float, float, float, float, float, float]:
    xs = [p[0] for p in b if len(p) >= 2]
    ys = [p[1] for p in b if len(p) >= 2]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return (max(xs) - min(xs), max(ys) - min(ys), min(xs), min(ys), max(xs), max(ys))


def area(b: list[list[float]]) -> float:
    pts = [(p[0], p[1]) for p in b if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    s = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        s += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(s) / 2.0


def perimeter(b: list[list[float]]) -> float:
    n = len(b)
    tot = 0.0
    for i in range(n):
        a, c = b[i], b[(i + 1) % n]
        tot += math.hypot(c[0] - a[0], c[1] - a[1])
    return tot


def dist_point_to_poly(px: float, py: float, poly: list[list[float]]) -> float:
    """Min distance from (px,py) to the polygon's edges (0 if inside-ish)."""
    if not poly or len(poly) < 2:
        return float("inf")
    best = float("inf")
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        best = min(best, _seg_dist(px, py, a[0], a[1], b[0], b[1]))
    return best


def _seg_dist(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))
