"""Site setback and building clearance utilities.

Terminology
-----------
site_setback       — minimum distance a building must maintain from each site
                     boundary edge (e.g. 5 m from a small road, 10 m from a
                     major road).  Creates the *buildable zone* inside the site.
building_clearance — minimum centre-to-centre separation distance between the
                     footprints of two buildings.  Also called *building
                     separation* or *daylight distance*.
buildable_zone     — the polygon inside the site after applying all site
                     setbacks.  Placement optimisation uses this instead of the
                     raw site boundary.

Default road-setback heuristic
-------------------------------
  setback_i = max(min_setback, road_width_i × road_setback_ratio)

  Typical values (can be overridden):
    min_setback = 3 m          residential lane
    road_setback_ratio = 0.4   setback = 40 % of road width
    road_width = 6 m           → setback = max(3, 6×0.4) = 3 m
    road_width = 20 m          → setback = max(3, 20×0.4) = 8 m
    road_width = 40 m (arterial) → setback = 16 m
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon
from shapely.geometry.polygon import orient as _orient


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_buildable_zone(
    site_boundary: list[list[float]],
    *,
    default_setback: float = 5.0,
    edge_setbacks: dict[int, float] | None = None,
    edge_road_widths: dict[int, float] | None = None,
    road_setback_ratio: float = 0.4,
    min_setback: float = 3.0,
) -> Polygon:
    """
    Return the buildable polygon inside the site after applying per-edge setbacks.

    Priority order for each edge i:
      1. ``edge_setbacks[i]``        — explicit override
      2. road_width_i × ratio       — derived from ``edge_road_widths``
      3. ``default_setback``         — fallback

    Args:
        site_boundary:      Closed polygon [[x, y, z], …].
        default_setback:    Fallback setback for edges without explicit spec (m).
        edge_setbacks:      {edge_index: metres} — explicit per-edge overrides.
        edge_road_widths:   {edge_index: road_width_m} — auto-compute setback
                            from road width using ``road_setback_ratio``.
        road_setback_ratio: Fraction of road width used as setback (default 0.4).
        min_setback:        Floor for auto-computed setbacks (m).

    Returns:
        A Shapely Polygon (may be empty if setbacks exceed site size).
    """
    site_polygon = _to_polygon(site_boundary)
    poly = _orient(site_polygon, sign=1.0)   # ensure CCW so inward normals are correct
    coords = list(poly.exterior.coords)[:-1]
    n = len(coords)

    buildable = poly

    for i in range(n):
        s = _edge_setback(
            i,
            edge_setbacks=edge_setbacks,
            edge_road_widths=edge_road_widths,
            road_setback_ratio=road_setback_ratio,
            min_setback=min_setback,
            default_setback=default_setback,
        )
        if s <= 0.0:
            continue

        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue

        # Inward normal for CCW polygon: left-perpendicular of edge direction
        nx, ny = -dy / length, dx / length

        # Offset edge inward by s
        op1 = (p1[0] + nx * s, p1[1] + ny * s)
        op2 = (p2[0] + nx * s, p2[1] + ny * s)

        # Cutting half-plane: the outward strip between original edge and offset edge
        FAR = max(site_polygon.bounds[2] - site_polygon.bounds[0],
                  site_polygon.bounds[3] - site_polygon.bounds[1]) * 4 + 200.0
        cut = Polygon([
            op1,
            op2,
            (op2[0] - nx * FAR, op2[1] - ny * FAR),
            (op1[0] - nx * FAR, op1[1] - ny * FAR),
        ])
        buildable = buildable.difference(cut)
        if buildable.is_empty:
            break

    if buildable.is_empty or buildable.area < 1.0:
        return site_polygon.buffer(-min(default_setback, 0.5))
    if not isinstance(buildable, Polygon):
        buildable = buildable.buffer(0)
    return buildable


def setback_summary(
    site_boundary: list[list[float]],
    *,
    default_setback: float = 5.0,
    edge_setbacks: dict[int, float] | None = None,
    edge_road_widths: dict[int, float] | None = None,
    road_setback_ratio: float = 0.4,
    min_setback: float = 3.0,
) -> list[dict[str, Any]]:
    """
    Return a summary of the setback applied to each site edge.

    Useful for notebook display and LLM context.
    """
    site_polygon = _to_polygon(site_boundary)
    poly = _orient(site_polygon, sign=1.0)
    coords = list(poly.exterior.coords)[:-1]
    n = len(coords)
    rows = []

    for i in range(n):
        p1, p2 = coords[i], coords[(i + 1) % n]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        s = _edge_setback(
            i,
            edge_setbacks=edge_setbacks,
            edge_road_widths=edge_road_widths,
            road_setback_ratio=road_setback_ratio,
            min_setback=min_setback,
            default_setback=default_setback,
        )
        road_w = (edge_road_widths or {}).get(i)
        rows.append({
            "edge_index": i,
            "edge_length_m": round(length, 2),
            "setback_m": round(s, 2),
            "road_width_m": road_w,
            "midpoint": [
                round((p1[0] + p2[0]) / 2, 2),
                round((p1[1] + p2[1]) / 2, 2),
            ],
        })

    buildable = compute_buildable_zone(
        site_boundary,
        default_setback=default_setback,
        edge_setbacks=edge_setbacks,
        edge_road_widths=edge_road_widths,
        road_setback_ratio=road_setback_ratio,
        min_setback=min_setback,
    )
    area_lost = round(site_polygon.area - buildable.area, 2)
    return {
        "edges": rows,
        "site_area_sqm": round(site_polygon.area, 2),
        "buildable_area_sqm": round(buildable.area, 2),
        "setback_area_sqm": area_lost,
        "buildable_fraction": round(buildable.area / site_polygon.area, 4),
        "buildable_boundary": [
            [round(float(x), 4), round(float(y), 4), 0.0]
            for x, y in buildable.exterior.coords
        ],
    }


def clearance_constraint_value(
    bld1: Polygon,
    bld2: Polygon,
    min_separation: float,
) -> float:
    """
    Returns the constraint value for building clearance: G = min_separation - distance.
    G ≤ 0 means the constraint is satisfied (buildings are far enough apart).
    G > 0 means buildings are too close.
    """
    dist = bld1.distance(bld2)
    return min_separation - dist


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _edge_setback(
    i: int,
    *,
    edge_setbacks: dict[int, float] | None,
    edge_road_widths: dict[int, float] | None,
    road_setback_ratio: float,
    min_setback: float,
    default_setback: float,
) -> float:
    if edge_setbacks and i in edge_setbacks:
        return float(edge_setbacks[i])
    if edge_road_widths and i in edge_road_widths:
        return float(max(min_setback, edge_road_widths[i] * road_setback_ratio))
    return float(default_setback)


def _to_polygon(boundary: list[list[float]]) -> Polygon:
    pts = [(float(p[0]), float(p[1])) for p in boundary]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly
