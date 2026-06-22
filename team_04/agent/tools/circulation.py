"""Circulation, access, and fire safety (Phase 5 — BACKEND_PLAN.md).

Access placement should explain *why* a building sits where it sits: people and
vehicles enter from the street, drive along internal corridors to each building
and to parking, and fire appliances must be able to reach every building.

Four public functions form the Phase 5 pipeline:

    propose_site_entries(site_model)
        Public entry on the main-road side, optional private/service entry on a
        secondary side. Each entry is a point on the boundary + a type.

    route_internal_circulation(site_model, entries, buildings, parking)
        A drivable internal path network — straight / L-shaped corridors of
        ``DEFAULT_PATH_WIDTH_M`` from the entry to each building's entrance side
        and to each parking zone. Returned as polylines + buffered polygons.
        The buffered polygons join parking as occupied obstacles for placement.

    building_entrance_orientation(buildings, entries, circulation)
        Heuristic: each building's entrance facade faces the nearest circulation
        path / public entry; the private/quiet facade faces away.

    check_fire_access(buildings, circulation, max_distance=50, min_path_width=4)
        Per building: distance from the drivable network, reachable perimeter
        ratio, pass/fail. ``constraint_value = distance - max_distance`` (≤ 0
        feasible) is the hard fire-access constraint G for the optimizer.

Pure geometry (Shapely in / dict out), deterministic, no LLM or MCP.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from .view_analysis import divide_boundary_into_test_points


# ---------------------------------------------------------------------------
# Constants (centralized, documented — override via kwargs not by editing here)
# ---------------------------------------------------------------------------

DEFAULT_PATH_WIDTH_M: float = 6.0
"""Width of a two-way drivable internal corridor (m)."""

MIN_PATH_WIDTH_M: float = 4.0
"""Minimum width that still counts as fire-appliance access (m)."""

MAX_FIRE_DISTANCE_M: float = 50.0
"""Max hose/appliance reach: every building must be within this of a drivable
path (m). Default reflects a common code distance for unsprinklered buildings."""

REACHABLE_RATIO_PASS: float = 0.0
"""Minimum fraction of a building's perimeter that must be within reach for the
soft perimeter check. The hard pass/fail is governed by distance alone (the
nearest-point distance), this only enriches the report; set > 0 to require
a serviceable frontage as well."""

PERIMETER_PIECE_LENGTH_M: float = 2.0
"""Spacing of boundary test points used for the reachable-perimeter ratio (m)."""

SECONDARY_HIERARCHY: tuple[str, ...] = ("secondary", "path")
"""Road hierarchies eligible to host a private / service entry."""


# ---------------------------------------------------------------------------
# Public API — 1. Site entries
# ---------------------------------------------------------------------------

def propose_site_entries(site_model: dict[str, Any]) -> dict[str, Any]:
    """Propose access entry points on the site boundary.

    A single **public** entry is placed at the midpoint of the main-road side
    (from Phase 2 road analysis). When no road is known the longest side is used
    and an ambiguity is reported. An optional **private** / service entry is
    placed on a different side that carries a secondary/path road, if any.

    Args:
        site_model: Canonical SiteModel dict (``boundary``, ``sides``, ``roads``).

    Returns:
        dict with:
            entries        — list of entry dicts (see below)
            public_count   — number of public entries
            private_count  — number of private entries
            main_road_side_index — echoed from road analysis (or None)
            ambiguity      — "no_road_data" when the public side was guessed
            summary        — human-readable one-liner

        Each entry dict:
            entry_id       — "entry_public_0", "entry_private_0", …
            point          — [x, y, 0] on the boundary
            type           — "public" | "private"
            side_index     — which site edge it sits on
            inward_normal  — unit vector pointing into the site [nx, ny]
            road_name      — adjacent road name (or None)
    """
    boundary = site_model.get("boundary") or site_model.get("site_boundary") or []
    if not boundary or len(boundary) < 3:
        return {
            "entries": [],
            "public_count": 0,
            "private_count": 0,
            "main_road_side_index": None,
            "ambiguity": "no_site_boundary",
            "summary": "No entries proposed: site boundary is missing.",
        }

    site_poly = _to_polygon(boundary)
    sides = _sides_from_model(site_model, site_poly)
    roads_result: dict = site_model.get("roads") or {}
    main_road_side = roads_result.get("main_road_side_index")

    ambiguity: str | None = None
    if main_road_side is None or not (0 <= int(main_road_side) < len(sides)):
        # No road context — fall back to the longest side as the public frontage.
        main_road_side = max(range(len(sides)), key=lambda i: _side_length(sides[i]))
        ambiguity = "no_road_data"

    entries: list[dict[str, Any]] = []

    # ── Public entry on the main-road side ───────────────────────────────────
    pub_point, pub_normal = _midpoint_and_inward_normal(sides[main_road_side], site_poly)
    entries.append({
        "entry_id": "entry_public_0",
        "point": [round(pub_point[0], 4), round(pub_point[1], 4), 0.0],
        "type": "public",
        "side_index": int(main_road_side),
        "inward_normal": [round(pub_normal[0], 6), round(pub_normal[1], 6)],
        "road_name": _side_road_name(sides[main_road_side]),
    })

    # ── Optional private / service entry on a secondary-road side ────────────
    private_side = _pick_private_side(sides, main_road_side)
    if private_side is not None:
        pv_point, pv_normal = _midpoint_and_inward_normal(sides[private_side], site_poly)
        entries.append({
            "entry_id": "entry_private_0",
            "point": [round(pv_point[0], 4), round(pv_point[1], 4), 0.0],
            "type": "private",
            "side_index": int(private_side),
            "inward_normal": [round(pv_normal[0], 6), round(pv_normal[1], 6)],
            "road_name": _side_road_name(sides[private_side]),
        })

    public_count = sum(1 for e in entries if e["type"] == "public")
    private_count = sum(1 for e in entries if e["type"] == "private")

    parts = [f"{public_count} public entry on side {main_road_side}"]
    if private_count:
        parts.append(f"{private_count} private/service entry on side {private_side}")
    if ambiguity:
        parts.append("(public side guessed from longest edge — no road data)")

    return {
        "entries": entries,
        "public_count": public_count,
        "private_count": private_count,
        "main_road_side_index": int(main_road_side),
        "ambiguity": ambiguity,
        "summary": "; ".join(parts),
    }


# ---------------------------------------------------------------------------
# Public API — 2. Internal circulation network
# ---------------------------------------------------------------------------

def route_internal_circulation(
    site_model: dict[str, Any],
    entries: list[dict[str, Any]],
    buildings: list[dict[str, Any]],
    parking: dict[str, Any] | list[dict[str, Any]] | None = None,
    *,
    path_width_m: float = DEFAULT_PATH_WIDTH_M,
) -> dict[str, Any]:
    """Route a drivable internal path network from entries to targets.

    Starting from the public entry, the network grows as a tree: each target
    (building entrance point, then each parking zone) is connected to the
    *nearest point on the network so far* with a straight or L-shaped corridor,
    keeping the corner inside the site where possible. Each corridor is a
    centreline polyline plus a buffered polygon ``path_width_m`` wide.

    Args:
        site_model:   Canonical SiteModel dict (for the site polygon clip).
        entries:      Output of ``propose_site_entries`` — its ``entries`` list,
                      or the whole dict (the ``entries`` key is read).
        buildings:    Placed-building dicts, each with a ``boundary`` key.
        parking:      ``allocate_parking_zones`` result dict (``zones`` read) or
                      a raw list of zone dicts. Optional.
        path_width_m: Corridor width (m).

    Returns:
        dict with:
            paths            — list of path dicts (see below)
            network_polyline — merged centrelines as a list of polylines
            occupied_polygons — buffered corridor polygons (obstacles for placement)
            total_length_m   — summed centreline length
            path_width_m     — echoed width
            summary          — human-readable one-liner

        Each path dict:
            path_id          — "path_0", "path_1", …
            polyline         — [[x, y, 0], …] centreline
            buffered_boundary— [[x, y, 0], …] corridor polygon
            width_m          — corridor width
            length_m         — centreline length
            serves           — building_id / zone_id the path reaches
            target_type      — "building" | "parking"
    """
    entry_list = _coerce_entries(entries)
    boundary = site_model.get("boundary") or site_model.get("site_boundary") or []

    if not entry_list:
        return _empty_circulation(path_width_m, "no entries supplied")
    if not boundary or len(boundary) < 3:
        return _empty_circulation(path_width_m, "no valid site boundary")

    site_poly = _to_polygon(boundary)
    half_w = max(MIN_PATH_WIDTH_M, float(path_width_m)) / 2.0

    # Anchor the network at the public entry (fallback: first entry).
    anchor = next((e for e in entry_list if e.get("type") == "public"), entry_list[0])
    anchor_pt = Point(float(anchor["point"][0]), float(anchor["point"][1]))

    # ── Targets: building entrance points, then parking zone centroids ───────
    targets: list[dict[str, Any]] = []
    for bld in buildings or []:
        bnd = bld.get("boundary") or bld.get("building_boundary") or []
        if not bnd or len(bnd) < 3:
            continue
        bld_poly = _to_polygon(bnd)
        bld_id = str(bld.get("building_id") or bld.get("geometry_id") or f"building_{len(targets)}")
        targets.append({"geom": bld_poly, "serves": bld_id, "target_type": "building"})

    for zone in _coerce_zones(parking):
        zbnd = zone.get("boundary") or []
        if not zbnd or len(zbnd) < 3:
            continue
        zpoly = _to_polygon(zbnd)
        zid = str(zone.get("zone_id") or f"parking_zone_{len(targets)}")
        targets.append({"geom": zpoly, "serves": zid, "target_type": "parking"})

    if not targets:
        return _empty_circulation(path_width_m, "no buildings or parking to serve")

    # Connect nearest targets first so the tree stays short and connected.
    targets.sort(key=lambda t: t["geom"].distance(anchor_pt))

    paths: list[dict[str, Any]] = []
    centrelines: list[LineString] = []
    network_geom: Any = anchor_pt  # grows as lines are added

    for tgt in targets:
        # Connect from the nearest point on the network so far.
        from_geom, _ = nearest_points(network_geom, tgt["geom"])
        # Target the boundary point of the building/zone nearest that network point.
        _, to_geom = nearest_points(from_geom, tgt["geom"])
        a = (from_geom.x, from_geom.y)
        b = (to_geom.x, to_geom.y)

        polyline = _l_polyline(a, b, site_poly)
        line = LineString(polyline)
        if line.length < 1e-6:
            continue

        buffered = line.buffer(half_w, cap_style=2, join_style=2).intersection(site_poly)
        buffered = _largest_polygon(buffered)

        paths.append({
            "path_id": f"path_{len(paths)}",
            "polyline": [[round(x, 4), round(y, 4), 0.0] for x, y in polyline],
            "buffered_boundary": _poly_to_list(buffered) if buffered and not buffered.is_empty else [],
            "width_m": round(float(path_width_m), 2),
            "length_m": round(float(line.length), 2),
            "serves": tgt["serves"],
            "target_type": tgt["target_type"],
        })
        centrelines.append(line)
        network_geom = unary_union([network_geom, line])

    total_length = round(sum(c.length for c in centrelines), 2)
    occupied = [p["buffered_boundary"] for p in paths if p["buffered_boundary"]]

    n_bld = sum(1 for p in paths if p["target_type"] == "building")
    n_park = sum(1 for p in paths if p["target_type"] == "parking")
    summary = (
        f"{len(paths)} corridor(s), {total_length} m total "
        f"({n_bld} to buildings, {n_park} to parking), {path_width_m} m wide"
    )

    return {
        "paths": paths,
        "network_polyline": [p["polyline"] for p in paths],
        "occupied_polygons": occupied,
        "total_length_m": total_length,
        "path_width_m": round(float(path_width_m), 2),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Public API — 3. Building entrance orientation
# ---------------------------------------------------------------------------

def building_entrance_orientation(
    buildings: list[dict[str, Any]],
    entries: list[dict[str, Any]] | dict[str, Any],
    circulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Heuristic entrance orientation per building.

    Each building's entrance faces the nearest circulation path (or, when no
    paths exist, the nearest public entry). The private / quiet facade faces the
    opposite direction. Returns the entrance point on the building boundary, the
    outward direction it faces, and the distance to whatever it faces.

    Args:
        buildings:   Placed-building dicts with a ``boundary`` key.
        entries:     ``propose_site_entries`` result or its ``entries`` list.
        circulation: ``route_internal_circulation`` result (optional). When
                     present, paths take precedence over entries.

    Returns:
        dict with:
            buildings — list of per-building dicts:
                building_id, entrance_point [x,y,0], entrance_direction [nx,ny]
                (outward, toward the access), private_direction [nx,ny]
                (opposite), faces ("circulation" | "public_entry" | "none"),
                distance_m
            summary
    """
    entry_list = _coerce_entries(entries)
    public_entries = [e for e in entry_list if e.get("type") == "public"] or entry_list

    # Build the access geometry the entrance should face.
    centrelines: list[LineString] = []
    if circulation:
        for p in circulation.get("paths", []):
            pl = p.get("polyline") or []
            if len(pl) >= 2:
                centrelines.append(LineString([(pt[0], pt[1]) for pt in pl]))
    access_geom = unary_union(centrelines) if centrelines else None
    faces_kind = "circulation" if access_geom is not None else (
        "public_entry" if public_entries else "none"
    )

    entry_points = [Point(e["point"][0], e["point"][1]) for e in public_entries]

    results: list[dict[str, Any]] = []
    for i, bld in enumerate(buildings or []):
        bnd = bld.get("boundary") or bld.get("building_boundary") or []
        bld_id = str(bld.get("building_id") or bld.get("geometry_id") or f"building_{i}")
        if not bnd or len(bnd) < 3:
            continue
        bld_poly = _to_polygon(bnd)

        if access_geom is not None:
            near_on_bld, near_on_access = nearest_points(bld_poly.exterior, access_geom)
            target = near_on_access
        elif entry_points:
            target = min(entry_points, key=lambda ep: bld_poly.distance(ep))
            near_on_bld, _ = nearest_points(bld_poly.exterior, target)
        else:
            results.append({
                "building_id": bld_id,
                "entrance_point": None,
                "entrance_direction": None,
                "private_direction": None,
                "faces": "none",
                "distance_m": None,
            })
            continue

        ex, ey = near_on_bld.x, near_on_bld.y
        dx, dy = target.x - ex, target.y - ey
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            # Entrance sits on the access; face outward from building centroid.
            c = bld_poly.centroid
            dx, dy = ex - c.x, ey - c.y
            dist0 = math.hypot(dx, dy) or 1.0
            ndir = (dx / dist0, dy / dist0)
        else:
            ndir = (dx / dist, dy / dist)

        results.append({
            "building_id": bld_id,
            "entrance_point": [round(ex, 4), round(ey, 4), 0.0],
            "entrance_direction": [round(ndir[0], 6), round(ndir[1], 6)],
            "private_direction": [round(-ndir[0], 6), round(-ndir[1], 6)],
            "faces": faces_kind,
            "distance_m": round(float(dist), 3),
        })

    return {
        "buildings": results,
        "summary": f"Oriented {len(results)} building entrance(s) toward {faces_kind}.",
    }


# ---------------------------------------------------------------------------
# Public API — 4. Fire access constraint
# ---------------------------------------------------------------------------

def check_fire_access(
    buildings: list[dict[str, Any]],
    circulation: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    max_distance: float = MAX_FIRE_DISTANCE_M,
    min_path_width: float = MIN_PATH_WIDTH_M,
) -> dict[str, Any]:
    """Check that every building is reachable by a drivable fire-access path.

    Only paths at least ``min_path_width`` wide count as fire access. For each
    building the nearest-point distance to the drivable network is measured; the
    building **passes** when that distance ≤ ``max_distance``. A reachable
    perimeter ratio (fraction of boundary test points within ``max_distance`` of
    the network) is reported for richer feedback.

    The hard constraint follows the optimizer's ``G ≤ 0`` convention:

        ``constraint_value = distance_m − max_distance``   (≤ 0 ⇒ feasible)

    Args:
        buildings:      Placed-building dicts with a ``boundary`` key.
        circulation:    ``route_internal_circulation`` result (``paths`` read)
                        or a raw list of path dicts.
        max_distance:   Maximum allowed building-to-path distance (m).
        min_path_width: Minimum path width that qualifies as access (m).

    Returns:
        dict with:
            buildings  — per-building dicts:
                building_id, distance_m, reachable_perimeter_ratio,
                within_reach (bool), pass (bool), constraint_value (≤0 ⇒ ok)
            all_pass            — True when every building passes
            max_constraint_value— worst (largest) constraint_value; >0 ⇒ violation
            n_pass, n_fail
            max_distance_m, min_path_width_m
            summary
    """
    # ── Drivable network from qualifying paths ───────────────────────────────
    drivable: list[LineString] = []
    for p in _coerce_paths(circulation):
        width = float(p.get("width_m", DEFAULT_PATH_WIDTH_M))
        if width + 1e-9 < float(min_path_width):
            continue
        pl = p.get("polyline") or []
        if len(pl) >= 2:
            drivable.append(LineString([(pt[0], pt[1]) for pt in pl]))
    network = unary_union(drivable) if drivable else None

    results: list[dict[str, Any]] = []
    for i, bld in enumerate(buildings or []):
        bnd = bld.get("boundary") or bld.get("building_boundary") or []
        bld_id = str(bld.get("building_id") or bld.get("geometry_id") or f"building_{i}")
        if not bnd or len(bnd) < 3:
            continue
        bld_poly = _to_polygon(bnd)

        if network is None:
            distance = math.inf
            ratio = 0.0
        else:
            distance = float(bld_poly.distance(network))
            ratio = _reachable_perimeter_ratio(bnd, network, max_distance)

        within = distance <= float(max_distance) + 1e-6
        passed = within and ratio >= REACHABLE_RATIO_PASS
        constraint = (distance - float(max_distance)) if math.isfinite(distance) else 1e9

        results.append({
            "building_id": bld_id,
            "distance_m": round(distance, 3) if math.isfinite(distance) else None,
            "reachable_perimeter_ratio": round(ratio, 3),
            "within_reach": bool(within),
            "pass": bool(passed),
            "constraint_value": round(float(constraint), 3),
        })

    n_pass = sum(1 for r in results if r["pass"])
    n_fail = len(results) - n_pass
    all_pass = n_fail == 0 and len(results) > 0
    max_constraint = max((r["constraint_value"] for r in results), default=0.0)

    if not results:
        summary = "No buildings to check for fire access."
    elif all_pass:
        summary = f"All {n_pass} building(s) within {max_distance} m of a drivable path."
    else:
        summary = (
            f"{n_fail} of {len(results)} building(s) FAIL fire access "
            f"(> {max_distance} m from a >= {min_path_width} m path)."
        )

    return {
        "buildings": results,
        "all_pass": bool(all_pass),
        "max_constraint_value": round(float(max_constraint), 3),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "max_distance_m": float(max_distance),
        "min_path_width_m": float(min_path_width),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_polygon(boundary: list) -> Polygon:
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    poly = Polygon(pts)
    return poly.buffer(0) if not poly.is_valid else poly


def _side_length(side: dict) -> float:
    s = side.get("start", [0, 0])
    e = side.get("end", [0, 0])
    return math.hypot(float(e[0]) - float(s[0]), float(e[1]) - float(s[1]))


def _sides_from_model(site_model: dict[str, Any], site_poly: Polygon) -> list[dict]:
    """Return the model's sides, or synthesise them from the boundary."""
    sides = list(site_model.get("sides") or [])
    if sides:
        return sides
    coords = list(site_poly.exterior.coords)[:-1]
    n = len(coords)
    return [
        {
            "side_index": i,
            "start": [coords[i][0], coords[i][1], 0.0],
            "end": [coords[(i + 1) % n][0], coords[(i + 1) % n][1], 0.0],
        }
        for i in range(n)
    ]


def _midpoint_and_inward_normal(
    side: dict,
    site_poly: Polygon,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Midpoint of a side and the unit normal pointing into the site."""
    s = side.get("start", [0, 0])
    e = side.get("end", [0, 0])
    sx, sy = float(s[0]), float(s[1])
    ex, ey = float(e[0]), float(e[1])
    mid = ((sx + ex) / 2.0, (sy + ey) / 2.0)

    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux  # left perpendicular
    cx, cy = site_poly.centroid.x, site_poly.centroid.y
    if (cx - mid[0]) * nx + (cy - mid[1]) * ny < 0:
        nx, ny = -nx, -ny  # flip to point inward
    return mid, (nx, ny)


def _side_road_name(side: dict) -> str | None:
    adj = side.get("adjacent_road")
    if isinstance(adj, dict):
        return adj.get("name")
    return None


def _pick_private_side(sides: list[dict], main_road_side: int) -> int | None:
    """Pick a side (≠ main road) carrying a secondary/path road for a service entry."""
    candidates: list[tuple[int, float]] = []
    for i, side in enumerate(sides):
        if i == main_road_side:
            continue
        adj = side.get("adjacent_road")
        if isinstance(adj, dict) and adj.get("hierarchy") in SECONDARY_HIERARCHY:
            candidates.append((i, _side_length(side)))
    if not candidates:
        return None
    # Longest qualifying side wins (most frontage for a service approach).
    return max(candidates, key=lambda c: c[1])[0]


def _l_polyline(
    a: tuple[float, float],
    b: tuple[float, float],
    site_poly: Polygon,
) -> list[tuple[float, float]]:
    """Straight or L-shaped polyline from a to b, keeping the corner inside the site.

    Tries both axis-aligned corners; prefers the corner that lies inside the
    site polygon. Falls back to a straight segment when neither corner helps
    (e.g. a and b already share an axis).
    """
    ax, ay = a
    bx, by = b
    if math.hypot(bx - ax, by - ay) < 1e-9:
        return [(ax, ay), (bx, by)]

    # Already axis-aligned → straight segment is fine.
    if abs(ax - bx) < 1e-6 or abs(ay - by) < 1e-6:
        return [(ax, ay), (bx, by)]

    c1 = (bx, ay)  # horizontal first, then vertical
    c2 = (ax, by)  # vertical first, then horizontal

    c1_inside = site_poly.contains(Point(c1))
    c2_inside = site_poly.contains(Point(c2))

    if c1_inside and not c2_inside:
        corner = c1
    elif c2_inside and not c1_inside:
        corner = c2
    elif c1_inside and c2_inside:
        # Both valid: pick the L whose legs stay inside the site the most.
        corner = c1 if _l_inside_length(a, c1, b, site_poly) >= _l_inside_length(a, c2, b, site_poly) else c2
    else:
        # Neither corner inside → straight segment (clipped downstream by buffer).
        return [(ax, ay), (bx, by)]

    return [(ax, ay), corner, (bx, by)]


def _l_inside_length(
    a: tuple[float, float],
    corner: tuple[float, float],
    b: tuple[float, float],
    site_poly: Polygon,
) -> float:
    """Length of an L-path's legs that fall inside the site (higher = better)."""
    line = LineString([a, corner, b])
    inside = line.intersection(site_poly)
    return float(getattr(inside, "length", 0.0))


def _reachable_perimeter_ratio(
    boundary: list,
    network: Any,
    max_distance: float,
) -> float:
    """Fraction of boundary test points within max_distance of the network."""
    try:
        test_points = divide_boundary_into_test_points(boundary, piece_length=PERIMETER_PIECE_LENGTH_M)
    except Exception:
        return 0.0
    if not test_points:
        return 0.0
    reachable = 0
    for tp in test_points:
        px, py = tp["point"][0], tp["point"][1]
        if network.distance(Point(px, py)) <= max_distance + 1e-6:
            reachable += 1
    return reachable / len(test_points)


def _largest_polygon(geom: Any) -> Polygon | None:
    """Return the largest Polygon from a geometry (handles Multi*)."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom
    geoms = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    if not geoms:
        return None
    return max(geoms, key=lambda g: g.area)


def _poly_to_list(poly: Polygon) -> list[list[float]]:
    return [[round(float(x), 4), round(float(y), 4), 0.0] for x, y in poly.exterior.coords]


def _coerce_entries(entries: Any) -> list[dict[str, Any]]:
    if isinstance(entries, dict):
        return list(entries.get("entries") or [])
    if isinstance(entries, list):
        return entries
    return []


def _coerce_zones(parking: Any) -> list[dict[str, Any]]:
    if isinstance(parking, dict):
        return list(parking.get("zones") or [])
    if isinstance(parking, list):
        return parking
    return []


def _coerce_paths(circulation: Any) -> list[dict[str, Any]]:
    if isinstance(circulation, dict):
        return list(circulation.get("paths") or [])
    if isinstance(circulation, list):
        return circulation
    return []


def _empty_circulation(path_width_m: float, reason: str) -> dict[str, Any]:
    return {
        "paths": [],
        "network_polyline": [],
        "occupied_polygons": [],
        "total_length_m": 0.0,
        "path_width_m": round(float(path_width_m), 2),
        "summary": f"Circulation routing skipped: {reason}",
    }
