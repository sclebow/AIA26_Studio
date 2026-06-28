"""Parking demand estimation and site allocation (Phase 4 — BACKEND_PLAN.md).

Three public functions form the full Phase 4 pipeline:

    estimate_apartments(footprint_area_sqm, storeys, ...)
        Dwelling count derived from gross floor area × efficiency ratio.

    parking_demand(apartments, ratio=1.0)
        Required stalls and area summary from apartment count.

    allocate_parking_zones(site_model, buildings, demand_by_building, ...)
        Rectangular parking strips placed in available site area,
        preferring the main-road side (Phase 2), clear of buildings.
        Returns zone polygons, stall counts, and a shortfall flag.

Helper:
    compute_building_demand(buildings, parking_ratio=1.0)
        Convenience wrapper that calls estimate_apartments + parking_demand
        for each placed building in a single pass.

Pure geometry (Shapely in / dict out), deterministic, no LLM or MCP.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union


# ---------------------------------------------------------------------------
# Constants (centralized, documented — override via kwargs not by editing here)
# ---------------------------------------------------------------------------

EFFICIENCY: float = 0.80
"""Net-to-gross ratio: fraction of GFA that is lettable living area."""

AVG_APARTMENT_SQM: float = 70.0
"""Assumed average net apartment area (m²)."""

DEFAULT_PARKING_RATIO: float = 1.0
"""Stalls per apartment when the brief does not specify."""

STALL_WIDTH_M: float = 2.5
"""Width of a single parking stall perpendicular to the aisle (m)."""

STALL_DEPTH_M: float = 5.0
"""Depth of a parking stall from the aisle face to the stop kerb (m)."""

AISLE_WIDTH_M: float = 6.0
"""Two-way manoeuvring aisle width shared between two stall rows (m)."""

BAY_DEPTH_M: float = STALL_DEPTH_M + AISLE_WIDTH_M
"""Depth of one parking bay: single row of stalls + full aisle = 11 m."""

M2_PER_STALL: float = STALL_WIDTH_M * BAY_DEPTH_M
"""Ground-area budget per stall including aisle share (2.5 × 11 = 27.5 m²)."""

STRIP_INSET_M: float = 0.3
"""Gap between the site boundary and the near edge of the parking strip."""

MIN_STRIP_STALLS: int = 2
"""Minimum useful strip: at least this many stalls, else skip the edge."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_apartments(
    footprint_area_sqm: float,
    storeys: int,
    *,
    efficiency: float = EFFICIENCY,
    avg_apartment_sqm: float = AVG_APARTMENT_SQM,
) -> int:
    """Return the estimated dwelling count for a building.

    Args:
        footprint_area_sqm: Ground-floor footprint area (m²).
        storeys:            Number of above-ground storeys (≥ 1).
        efficiency:         Net / gross area ratio (default 0.80).
        avg_apartment_sqm:  Average net apartment area (default 70 m²).

    Returns:
        Integer dwelling count (≥ 0).
    """
    if footprint_area_sqm <= 0 or storeys <= 0 or avg_apartment_sqm <= 0:
        return 0
    gfa = footprint_area_sqm * storeys
    net_area = gfa * max(0.0, min(1.0, float(efficiency)))
    return max(0, int(net_area / float(avg_apartment_sqm)))


def parking_demand(
    apartments: int,
    *,
    parking_ratio: float = DEFAULT_PARKING_RATIO,
) -> dict[str, Any]:
    """Return the parking demand summary for a number of apartments.

    Args:
        apartments:     Number of dwelling units.
        parking_ratio:  Stalls per apartment (default 1.0).

    Returns:
        dict with keys:
            stalls_required   — integer stalls needed
            area_sqm_required — approximate land area needed (m²)
            stall_width_m, stall_depth_m, aisle_width_m, bay_depth_m,
            m2_per_stall      — constants used (informational)
    """
    stalls = max(0, int(math.ceil(apartments * max(0.0, float(parking_ratio)))))
    return {
        "stalls_required": stalls,
        "area_sqm_required": round(stalls * M2_PER_STALL, 1),
        "stall_width_m": STALL_WIDTH_M,
        "stall_depth_m": STALL_DEPTH_M,
        "aisle_width_m": AISLE_WIDTH_M,
        "bay_depth_m": BAY_DEPTH_M,
        "m2_per_stall": M2_PER_STALL,
    }


def compute_building_demand(
    buildings: list[dict[str, Any]],
    *,
    parking_ratio: float = DEFAULT_PARKING_RATIO,
    efficiency: float = EFFICIENCY,
    avg_apartment_sqm: float = AVG_APARTMENT_SQM,
) -> list[dict[str, Any]]:
    """Compute parking demand for each placed building in one pass.

    Args:
        buildings:      List of placed-building dicts (each must have
                        ``boundary`` and optionally ``storeys`` / ``height_m``).
        parking_ratio:  Stalls per apartment.
        efficiency:     Net / gross GFA ratio.
        avg_apartment_sqm: Average net apartment area.

    Returns:
        List of demand dicts, one per building, each containing:
            building_id, apartments, stalls_required, area_sqm_required,
            + the stall-dimension constants from parking_demand().
    """
    result: list[dict[str, Any]] = []
    for bld in buildings:
        bld_id = str(bld.get("building_id") or bld.get("geometry_id") or id(bld))
        boundary = bld.get("boundary") or bld.get("building_boundary", [])
        footprint = _poly_area(boundary)

        # Prefer explicit storeys; fall back to height / 3 m/floor
        storeys_raw = bld.get("storeys") or bld.get("height_m")
        if isinstance(storeys_raw, (int, float)) and storeys_raw > 0:
            storeys = max(1, int(storeys_raw if storeys_raw <= 50 else storeys_raw / 3.0))
        else:
            storeys = 3  # conservative default

        apts = estimate_apartments(
            footprint, storeys, efficiency=efficiency, avg_apartment_sqm=avg_apartment_sqm
        )
        demand = parking_demand(apts, parking_ratio=parking_ratio)
        result.append({"building_id": bld_id, "apartments": apts, **demand})
    return result


def allocate_parking_zones(
    site_model: dict[str, Any],
    buildings: list[dict[str, Any]],
    demand_by_building: list[dict[str, Any]],
    *,
    default_setback: float = 5.0,
    prefer_road_side: bool = True,
) -> dict[str, Any]:
    """Allocate rectangular parking zones on the site.

    Parking strips are placed inside the site, parallel to each boundary edge
    and ``BAY_DEPTH_M`` (11 m) deep, preferring the main-road side (from Phase 2
    road analysis).  Strips are intersected with the available area (site minus
    building footprints) so they never overlap placed buildings.

    Args:
        site_model:         Canonical SiteModel dict (output of build_site_model).
                            Must contain at least ``boundary`` and (optionally)
                            ``sides`` and ``roads``.
        buildings:          List of placed-building dicts with a ``boundary`` key.
        demand_by_building: List of ``{building_id, stalls_required}`` dicts.
        default_setback:    Fallback edge setback when site_model has none (m).
        prefer_road_side:   When True, try the main-road edge first.

    Returns:
        dict with:
            zones            — list of zone dicts (see below)
            total_stalls_allocated
            stalls_required
            shortfall        — stalls_required − total_stalls_allocated (≥ 0)
            feasible         — True when shortfall == 0
            summary          — human-readable one-liner
            building_demand  — echoes the demand_by_building input

        Each zone dict:
            zone_id                — "parking_zone_0", "parking_zone_1", …
            boundary               — closed polygon [[x, y, 0], …]
            stalls_allocated       — stalls this zone accounts for
            area_sqm               — zone footprint area
            side_index             — which site edge this zone fronts
            is_main_road_side      — True when this is the main-road edge
    """
    # ── Coerce site model ────────────────────────────────────────────────────
    boundary = (
        site_model.get("boundary")
        or site_model.get("site_boundary")
        or []
    )
    sides: list[dict] = site_model.get("sides") or []
    roads_result: dict = site_model.get("roads") or {}
    main_road_side: int | None = roads_result.get("main_road_side_index")

    if not boundary or len(boundary) < 3:
        return _empty_result(demand_by_building, "no valid site boundary")

    site_poly = _to_shapely(boundary)
    if site_poly.is_empty or site_poly.area < 1.0:
        return _empty_result(demand_by_building, "site polygon is degenerate")

    # ── Build sides from boundary when site_model has none ───────────────────
    if not sides:
        coords = list(site_poly.exterior.coords)[:-1]
        sides = [
            {
                "side_index": i,
                "start": [coords[i][0], coords[i][1], 0.0],
                "end": [coords[(i + 1) % len(coords)][0], coords[(i + 1) % len(coords)][1], 0.0],
            }
            for i in range(len(coords))
        ]

    # ── Building footprints as obstacles ─────────────────────────────────────
    bld_polys: list[Polygon] = []
    for bld in buildings:
        bnd = bld.get("boundary") or bld.get("building_boundary", [])
        if bnd and len(bnd) >= 3:
            try:
                p = _to_shapely(bnd).buffer(0.15)  # small guard clearance
                if not p.is_empty:
                    bld_polys.append(p)
            except Exception:
                pass
    obstacles = unary_union(bld_polys) if bld_polys else Polygon()
    available = site_poly.difference(obstacles)
    if available.is_empty:
        return _empty_result(demand_by_building, "no space remains after building placement")

    # ── Total stall demand ───────────────────────────────────────────────────
    stalls_required = sum(
        max(0, int(d.get("stalls_required", 0)))
        for d in demand_by_building
        if isinstance(d, dict)
    )
    stalls_remaining = stalls_required

    # ── Edge ordering: main-road first, then longest side desc ───────────────
    side_indices = list(range(len(sides)))
    if prefer_road_side and main_road_side is not None:
        others = sorted(
            [i for i in side_indices if i != main_road_side],
            key=lambda i: _side_length(sides[i]),
            reverse=True,
        )
        side_indices = [main_road_side] + others
    else:
        side_indices = sorted(
            side_indices,
            key=lambda i: _side_length(sides[i]),
            reverse=True,
        )

    # ── Place parking strips ──────────────────────────────────────────────────
    zones: list[dict[str, Any]] = []
    placed_zone_polys: list[Polygon] = []

    for side_idx in side_indices:
        if stalls_remaining <= 0:
            break

        side = sides[side_idx]
        strip, edge_vec = _make_strip(side, site_poly)
        if strip is None or strip.is_empty:
            continue

        # Remove buildings + already-placed zones from this strip
        extra_obstacles = unary_union(placed_zone_polys) if placed_zone_polys else Polygon()
        combined_obstacles = obstacles.union(extra_obstacles)
        free = strip.intersection(available).difference(combined_obstacles)
        if free.is_empty or free.area < M2_PER_STALL * MIN_STRIP_STALLS:
            continue

        # How many stalls fit by area?
        stalls_here = int(free.area / M2_PER_STALL)
        if stalls_here < MIN_STRIP_STALLS:
            continue

        stalls_to_place = min(stalls_here, stalls_remaining)

        # Trim the zone polygon along the edge direction if we don't need all
        zone_poly = (
            _trim_strip(free, edge_vec, stalls_to_place)
            if stalls_to_place < stalls_here
            else free
        )
        if zone_poly is None or zone_poly.is_empty:
            zone_poly = free

        # Normalize to a simple Polygon (take largest piece if multi-polygon)
        if not isinstance(zone_poly, Polygon):
            geoms = list(getattr(zone_poly, "geoms", [zone_poly]))
            zone_poly = max(geoms, key=lambda g: g.area)

        zone_id = f"parking_zone_{len(zones)}"
        zones.append({
            "zone_id": zone_id,
            "boundary": _poly_to_list(zone_poly),
            "stalls_allocated": stalls_to_place,
            "area_sqm": round(float(zone_poly.area), 1),
            "side_index": int(side_idx),
            "is_main_road_side": side_idx == main_road_side,
        })
        placed_zone_polys.append(zone_poly)
        stalls_remaining -= stalls_to_place

    total_allocated = stalls_required - stalls_remaining
    shortfall = max(0, stalls_remaining)
    feasible = shortfall == 0

    parts = [f"{stalls_required} stall(s) required"]
    parts.append(f"{total_allocated} allocated in {len(zones)} zone(s)")
    if shortfall:
        parts.append(f"{shortfall} stall(s) unplaced — site too constrained")

    return {
        "zones": zones,
        "total_stalls_allocated": total_allocated,
        "stalls_required": stalls_required,
        "shortfall": shortfall,
        "feasible": feasible,
        "summary": "; ".join(parts),
        "building_demand": demand_by_building,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_shapely(boundary: list) -> Polygon:
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    poly = Polygon(pts)
    return poly.buffer(0) if not poly.is_valid else poly


def _poly_area(boundary: list) -> float:
    if not boundary or len(boundary) < 3:
        return 0.0
    pts = [(float(p[0]), float(p[1])) for p in boundary]
    n = len(pts)
    area = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )
    return abs(area) / 2.0


def _side_length(side: dict) -> float:
    s = side.get("start", [0, 0])
    e = side.get("end", [0, 0])
    return math.hypot(float(e[0]) - float(s[0]), float(e[1]) - float(s[1]))


def _make_strip(
    side: dict,
    site_poly: Polygon,
) -> tuple[Polygon | None, tuple[float, float]]:
    """Build a strip polygon BAY_DEPTH_M deep inside the site along this edge."""
    start = side.get("start", [0, 0])
    end = side.get("end", [0, 0])
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length < STALL_WIDTH_M * MIN_STRIP_STALLS:
        return None, (0.0, 0.0)

    ux, uy = dx / length, dy / length  # unit edge direction

    # Inward normal: rotate 90° CCW and confirm it points toward site centroid
    nx, ny = -uy, ux
    mid_x, mid_y = (sx + ex) / 2.0, (sy + ey) / 2.0
    cx, cy = site_poly.centroid.x, site_poly.centroid.y
    if (cx - mid_x) * nx + (cy - mid_y) * ny < 0:
        nx, ny = -nx, -ny  # flip outward normal inward

    inset = STRIP_INSET_M
    depth = BAY_DEPTH_M

    # Four corners of the strip rectangle
    p1 = (sx + nx * inset,         sy + ny * inset)
    p2 = (ex + nx * inset,         ey + ny * inset)
    p3 = (ex + nx * (inset + depth), ey + ny * (inset + depth))
    p4 = (sx + nx * (inset + depth), sy + ny * (inset + depth))

    strip = Polygon([p1, p2, p3, p4]).intersection(site_poly)
    if strip.is_empty or strip.area < M2_PER_STALL:
        return None, (ux, uy)
    return strip, (ux, uy)


def _trim_strip(
    poly: Polygon,
    edge_vec: tuple[float, float],
    stalls: int,
) -> Polygon:
    """Clip poly along the edge direction to account for only `stalls` stalls."""
    # The free strip can be a MultiPolygon on a concave site — clip the largest piece.
    if not isinstance(poly, Polygon):
        geoms = list(getattr(poly, "geoms", [poly]))
        poly = max(geoms, key=lambda g: g.area)
    target_span = stalls * STALL_WIDTH_M
    ux, uy = edge_vec
    coords = list(poly.exterior.coords)
    projections = [float(x) * ux + float(y) * uy for x, y in coords]
    p_min = min(projections)
    p_max = max(projections)

    if target_span >= p_max - p_min:
        return poly  # no trimming needed

    p_cut = p_min + target_span

    # Point on the clip line: shift centroid to projection p_cut
    cx, cy = poly.centroid.x, poly.centroid.y
    c_proj = cx * ux + cy * uy
    clip_x = cx + (p_cut - c_proj) * ux
    clip_y = cy + (p_cut - c_proj) * uy

    # Perpendicular to edge direction
    perp_x, perp_y = -uy, ux
    far = (abs(p_max - p_min) + 200.0)

    # Half-plane that removes everything with projection > p_cut
    cut = Polygon([
        (clip_x + perp_x * far,          clip_y + perp_y * far),
        (clip_x - perp_x * far,          clip_y - perp_y * far),
        (clip_x + ux * far - perp_x * far, clip_y + uy * far - perp_y * far),
        (clip_x + ux * far + perp_x * far, clip_y + uy * far + perp_y * far),
    ])
    result = poly.difference(cut)
    if result.is_empty:
        return poly
    if not isinstance(result, Polygon):
        geoms = list(getattr(result, "geoms", [result]))
        result = max(geoms, key=lambda g: g.area)
    return result


def _poly_to_list(poly: Polygon) -> list[list[float]]:
    return [
        [round(float(x), 4), round(float(y), 4), 0.0]
        for x, y in poly.exterior.coords
    ]


def _empty_result(demand: list[dict], reason: str) -> dict[str, Any]:
    stalls = sum(max(0, int(d.get("stalls_required", 0))) for d in demand if isinstance(d, dict))
    return {
        "zones": [],
        "total_stalls_allocated": 0,
        "stalls_required": stalls,
        "shortfall": stalls,
        "feasible": stalls == 0,
        "summary": f"Parking allocation skipped: {reason}",
        "building_demand": demand,
    }
