"""Circulation-first generative masterplanning (Phase 6).

The earlier tools placed buildings, then connected paths. Real masterplans are
built the other way round: you reserve the site margins, decide where people and
vehicles get on and off the site, lay a movement **skeleton**, and only then hang
buildings off it — so circulation is never an afterthought routed around an
already-packed site.

This module implements that order as one pipeline:

    1. reserve_site_margins        — setbacks → buildable envelope (the no-build zone
                                     is kept for fire access / footways / landscape).
    2. plan_access_structure       — main / secondary / service / emergency entries.
    3. generate_movement_spine     — a vehicular spine + fire loop + pedestrian spine
                                     laid in the *empty* buildable zone first.
    4. place_buildings_along_spine — footprints attach to the spine, inside the
                                     envelope, clear of it and of each other; bad
                                     placements are rejected, each good one explained.
    5. building entrances          — public faces the spine, service the quiet side
                                     (reuses circulation.building_entrance_orientation).
    6. generate_dropoffs           — a drop-off per public entrance, on the nearest
                                     road, never random and never blocking a corridor.
    7. parking                     — allocated to serve destinations (reuses parking).
    8. pedestrian network          — desire lines that avoid parking / fire lanes.
    9. fire validation             — reach + multi-direction egress (reuses circulation).
   10. score_masterplan            — five weighted sub-scores gate the layout.

The single entry point is ``generate_masterplan(site_model, program)``. Every
placement decision carries a human ``reason``. Pure geometry; deterministic; no
LLM, MCP, or solver dependency (greedy placement, not pymoo).
"""
from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

from .building_shape_graph import build_shape_model
from .parking import allocate_parking_zones, compute_building_demand
from .site_setback import compute_buildable_zone, setback_summary
from .circulation import (
    MAX_FIRE_DISTANCE_M,
    analyze_egress,
    analyze_parking_access,
    analyze_site_arrival,
    audit_circulation,
    building_entrance_orientation,
    check_fire_access,
    detect_circulation_conflicts,
    propose_site_entries,
    route_internal_circulation,
    route_pedestrian_network,
    _coerce_entries,
    _largest_polygon,
    _network_from_circulation,
    _poly_to_list,
    _public_entrance_index,
    _to_polygon,
)


# ---------------------------------------------------------------------------
# Constants (override via kwargs, not by editing)
# ---------------------------------------------------------------------------

DEFAULT_SPINE_WIDTH_M: float = 6.0
"""Width of the vehicular movement spine (m)."""

MIN_BUILDING_SEPARATION_M: float = 6.0
"""Minimum gap between two building footprints (m)."""

SPINE_CLEARANCE_M: float = 2.0
"""Gap kept between a building and the edge of the spine corridor (m)."""

ACCESS_MAX_M: float = 45.0
"""A building is "well served" when its footprint is within this of the spine (m)."""

DROPOFF_MAX_WALK_M: float = 35.0
"""A drop-off must sit within this walking distance of its public entrance (m)."""

PLACEMENT_MARCH_STEP_M: float = 2.0
"""Step used when marching a building along the spine looking for a free slot (m)."""

SCORE_THRESHOLD: float = 0.6
"""Layouts scoring below this overall are rejected."""

SCORE_WEIGHTS: dict[str, float] = {
    "building_placement": 0.25,
    "vehicular_network": 0.20,
    "pedestrian_network": 0.20,
    "entrance_quality": 0.15,
    "fire_safety": 0.20,
}
"""Weights for the five core sub-scores (sum to 1). ``evaluate_urban_design``
re-weights these together with completeness + public realm (``URBAN_DESIGN_WEIGHTS``)."""

# --- 17-step pipeline tuning ----------------------------------------------

IMPORTANCE_TYPE_WEIGHT: dict[str, float] = {
    "O": 1.20, "U": 1.15, "H": 1.10, "X": 1.10, "Y": 1.05,
    "T": 1.00, "L": 1.00, "I": 0.95,
}
"""Civic-prominence multiplier by typology — a courtyard / winged block reads as
more of a landmark than a plain bar of the same floor area."""

TIER_ORDER: tuple[str, ...] = ("landmark", "primary", "secondary", "background")
"""Building-importance tiers, most prominent first."""

ARRIVAL_DEPTH_BY_TIER: dict[str, float] = {
    "landmark": 14.0, "primary": 10.0, "secondary": 6.0, "background": 0.0,
}
"""Forecourt depth (m) reserved in front of a building's public entrance, by
tier. ``background`` buildings get no dedicated arrival space."""

PROGRAM_COMPLETENESS_GATE: float = 0.8
"""A layout is rejected outright if fewer than this fraction of the program is
placed — so dropping buildings can never *raise* the score."""

URBAN_DESIGN_WEIGHTS: dict[str, float] = {
    "program_completeness": 0.18,
    "building_placement": 0.18,
    "vehicular_network": 0.14,
    "pedestrian_network": 0.14,
    "entrance_quality": 0.12,
    "fire_safety": 0.16,
    "public_realm": 0.08,
}
"""Weights for the seven urban-design sub-scores (sum to 1)."""


# ===========================================================================
# Step 1 — reserve site margins
# ===========================================================================

def reserve_site_margins(
    site_model: dict[str, Any],
    *,
    default_setback: float = 5.0,
) -> dict[str, Any]:
    """Reserve setbacks and return the buildable envelope.

    Front/side/rear setbacks are derived from each edge's road width (wider road →
    deeper setback) via ``site_setback``. The reserved ring stays available for
    fire access, footways, landscape and service — buildings may only be generated
    inside the returned ``buildable_boundary``.
    """
    boundary = site_model.get("boundary") or site_model.get("site_boundary") or []
    edge_road_widths = _edge_road_widths(site_model)
    summary = setback_summary(boundary, default_setback=default_setback,
                              edge_road_widths=edge_road_widths or None)
    buildable = compute_buildable_zone(boundary, default_setback=default_setback,
                                       edge_road_widths=edge_road_widths or None)
    return {
        "buildable_boundary": summary["buildable_boundary"],
        "buildable_polygon": buildable,
        "site_area_sqm": summary["site_area_sqm"],
        "buildable_area_sqm": summary["buildable_area_sqm"],
        "buildable_fraction": summary["buildable_fraction"],
        "edges": summary["edges"],
        "reason": (f"Reserved {summary['setback_area_sqm']} m² of margin "
                   f"({round((1 - summary['buildable_fraction']) * 100)}% of the site) for fire "
                   f"access, footways and landscape; buildings may only sit in the inner "
                   f"{summary['buildable_area_sqm']} m² envelope."),
        "summary": (f"Buildable envelope = {summary['buildable_area_sqm']} m² "
                    f"({round(summary['buildable_fraction'] * 100)}% of site) after setbacks."),
    }


def _edge_road_widths(site_model: dict[str, Any]) -> dict[int, float]:
    out: dict[int, float] = {}
    for s in site_model.get("sides") or []:
        ar = s.get("adjacent_road")
        if isinstance(ar, dict) and isinstance(ar.get("width_m"), (int, float)):
            out[int(s.get("side_index", -1))] = float(ar["width_m"])
    return out


# ===========================================================================
# Step 2 — access structure
# ===========================================================================

def plan_access_structure(site_model: dict[str, Any]) -> dict[str, Any]:
    """Classify entries into main / secondary / service / emergency roles.

    Wraps ``propose_site_entries`` and labels each entry by the hierarchy of the
    road it sits on, so downstream steps know which gate is the public arrival and
    which is for servicing / emergency vehicles.
    """
    entries = propose_site_entries(site_model)
    sides = site_model.get("sides") or []

    def hier(side_index: int) -> str | None:
        if 0 <= side_index < len(sides):
            ar = sides[side_index].get("adjacent_road")
            if isinstance(ar, dict):
                return ar.get("hierarchy")
        return None

    roles: list[dict[str, Any]] = []
    for e in entries["entries"]:
        h = hier(int(e.get("side_index", -1)))
        if e["type"] == "public":
            role = "main"
        elif h in ("secondary",):
            role = "service"
        else:
            role = "secondary"
        roles.append({
            "entry_id": e["entry_id"], "point": e["point"], "type": e["type"],
            "road_name": e.get("road_name"), "road_hierarchy": h, "role": role,
            "emergency_access": True,  # every drivable entry doubles as appliance access
            "reason": (f"{role} access off {e.get('road_name') or 'the boundary'} "
                       f"({h or 'no road data'})."),
        })
    return {
        "entries": entries,
        "roles": roles,
        "main": next((r for r in roles if r["role"] == "main"), None),
        "summary": (f"{sum(1 for r in roles if r['role'] == 'main')} main, "
                    f"{sum(1 for r in roles if r['role'] == 'service')} service, "
                    f"{sum(1 for r in roles if r['role'] == 'secondary')} secondary entry(ies); "
                    f"all drivable entries usable as emergency access."),
    }


# ===========================================================================
# Step 3 — movement spine (laid before any building)
# ===========================================================================

def generate_movement_spine(
    buildable: Polygon,
    entries: Any,
    *,
    spine_width: float = DEFAULT_SPINE_WIDTH_M,
) -> dict[str, Any]:
    """Lay the circulation skeleton in the empty buildable zone.

    Produces a **vehicular spine** along the envelope's long axis (anchored at the
    public entry), a **fire loop** just inside the envelope so an appliance can
    reach every edge, and a **pedestrian spine** aligned with the vehicular one.
    Buildings are attached to this afterwards; circulation is never bent around
    them.
    """
    mrr = buildable.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]
    edges = [(coords[i], coords[(i + 1) % 4]) for i in range(4)]
    lengths = [math.dist(a, b) for a, b in edges]
    (ax, ay), (bx, by) = edges[max(range(4), key=lambda i: lengths[i])]
    u_ang = math.degrees(math.atan2(by - ay, bx - ax))
    ux, uy = math.cos(math.radians(u_ang)), math.sin(math.radians(u_ang))

    c = buildable.centroid
    reach = max(lengths) * 1.5
    raw = LineString([(c.x - ux * reach, c.y - uy * reach), (c.x + ux * reach, c.y + uy * reach)])
    main_geom = _longest_line(raw.intersection(buildable))
    sline = [list(p) for p in main_geom.coords] if main_geom is not None else [[c.x, c.y], [c.x + 1, c.y]]

    # The main spine is the straight long axis (buildings pack along THIS). The public
    # entry connects to it via a short perpendicular stub — a clean T, not a diagonal.
    main_line = LineString(sline)
    main = [[round(x, 3), round(y, 3), 0.0] for x, y in sline]

    entry_stub: list[list[float]] = []
    drivable = list(main)
    pub = next((e for e in _coerce_entries(entries) if e.get("type") == "public"), None)
    if pub:
        ep = Point(float(pub["point"][0]), float(pub["point"][1]))
        proj = main_line.interpolate(main_line.project(ep))
        entry_stub = [[round(ep.x, 3), round(ep.y, 3), 0.0], [round(proj.x, 3), round(proj.y, 3), 0.0]]
        # Drivable spine = stub from the entry, then along the full main axis.
        if proj.distance(Point(sline[0])) > proj.distance(Point(sline[-1])):
            drivable = entry_stub + main[::-1]
        else:
            drivable = entry_stub + main

    ring = buildable.buffer(-spine_width)
    ring = _largest_polygon(ring) if ring and not ring.is_empty else None
    fire_loop = (_poly_to_list(ring) if ring is not None and not ring.is_empty else [])

    return {
        "vehicular_spine": main,            # straight long axis — placement marches this
        "entry_stub": entry_stub,           # short connector from the public entry
        "drivable_spine": drivable,         # stub + main, for the framework overlay
        "fire_loop": fire_loop,
        "pedestrian_spine": main,           # aligned; pedestrian routing adds the detail
        "axis_angle_deg": round(u_ang, 2),
        "spine_width_m": spine_width,
        "reason": ("Spine laid straight along the envelope's long axis; the public entry joins it "
                   "with a short stub (a T-junction); a fire loop set one corridor-width inside the "
                   "envelope reaches every edge."),
        "summary": f"Vehicular spine {round(main_line.length, 1)} m + entry stub + fire loop; "
                   f"buildings attach to this skeleton.",
    }


def _longest_line(geom: Any) -> LineString | None:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, LineString):
        return geom
    lines = [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]
    return max(lines, key=lambda g: g.length) if lines else None


# ===========================================================================
# Step 4 — access-driven building placement
# ===========================================================================

def place_buildings_along_spine(
    buildable: Polygon,
    spine: dict[str, Any],
    program: list[dict[str, Any]],
    *,
    separation: float = MIN_BUILDING_SEPARATION_M,
    spine_clearance: float = SPINE_CLEARANCE_M,
) -> dict[str, Any]:
    """Attach each programmed building to the spine inside the envelope.

    For every building (footprint generated by the wing model / a courtyard ring)
    we march along the spine, alternating sides, and take the first slot where the
    footprint sits **inside the buildable envelope**, **clear of the spine
    corridor**, and **far enough from every other building**. Placements that
    cannot satisfy this are reported as ``unplaced`` rather than forced.

    Args:
        buildable:  Buildable envelope polygon (Step 1).
        spine:      ``generate_movement_spine`` result.
        program:    List of ``{building_id, label, type, area, storeys, depth?, ratio?}``.
        separation: Minimum building-to-building gap (m).
        spine_clearance: Gap kept from the spine corridor edge (m).

    Returns:
        dict with ``buildings`` (placed dicts, each with ``placement_reason``),
        ``unplaced`` (ids), ``summary``.
    """
    corridor_half = spine["spine_width_m"] / 2.0 + spine_clearance
    # Frontages buildings can line: the central spine first, then the perimeter
    # fire loop (perimeter-block urbanism) — so a layout packs like a real
    # masterplan instead of a single double-loaded row.
    spine_line = LineString([(x, y) for x, y, *_ in spine["vehicular_spine"]])
    frontages: list[tuple[str, LineString]] = [("central spine", spine_line)]
    if spine.get("fire_loop") and len(spine["fire_loop"]) >= 2:
        frontages.append(("perimeter loop", LineString([(x, y) for x, y, *_ in spine["fire_loop"]])))

    # Place the biggest footprints first (they need the prime slots); smaller ones
    # then fill the gaps. Each building scans every frontage on both sides and takes
    # the first slot that is valid AND clear of everything already placed.
    order = sorted(range(len(program)), key=lambda i: -float(program[i].get("area", 0.0)))

    placed: list[dict[str, Any]] = []
    placed_polys: list[Polygon] = []
    unplaced: list[str] = []

    for idx in order:
        item = program[idx]
        base = _make_footprint(item)
        principal = _principal_angle(base)
        best: tuple[Polygon, float, int, str] | None = None

        for fname, line in frontages:
            if best is not None:
                break
            total_len = line.length
            d = 0.0
            while d <= total_len and best is None:
                for side in (1, -1):
                    pt = line.interpolate(d)
                    tang = _tangent_angle(line, d, total_len)
                    cand = affinity.rotate(base, tang - principal, origin=(0.0, 0.0))
                    _, dv = _frame_extents(cand, tang)
                    vx = math.cos(math.radians(tang + 90.0))
                    vy = math.sin(math.radians(tang + 90.0))
                    offset = corridor_half + dv / 2.0 + 0.5
                    fp = affinity.translate(cand, xoff=pt.x + vx * side * offset,
                                            yoff=pt.y + vy * side * offset)
                    if _valid_placement(fp, buildable, spine_line, corridor_half, placed_polys, separation):
                        best = (fp, d, side, fname)
                        break
                d += PLACEMENT_MARCH_STEP_M

        if best is None:
            unplaced.append(str(item.get("building_id") or f"building_{idx}"))
            continue
        fp, d_at, side, fname = best
        gap = _nearest_gap(fp, placed_polys)
        bdict = _poly_to_building(fp, item)
        bdict["placement_reason"] = (
            f"Attached to the {fname} at ~{round(d_at)} m, "
            f"{'left' if side > 0 else 'right'} side, long facade to circulation so the public "
            f"entrance faces arrival; "
            f"{'clear of all neighbours' if gap is None else f'{round(gap, 1)} m to nearest building'}, "
            f"fully inside the buildable envelope, clear of the corridor."
        )
        placed.append(bdict)
        placed_polys.append(fp)

    # Restore program order for a stable, readable result.
    placed.sort(key=lambda b: next((i for i, it in enumerate(program)
                                    if str(it.get("building_id")) == b["building_id"]), 0))
    return {
        "buildings": placed,
        "unplaced": unplaced,
        "summary": (f"{len(placed)}/{len(program)} building(s) placed along the spine"
                    + (f"; {len(unplaced)} could not fit ({', '.join(unplaced)})" if unplaced else ".")),
    }


def _make_footprint(item: dict[str, Any]) -> Polygon:
    """Footprint polygon (centred at origin) for a program item."""
    t = str(item.get("type", "I")).upper()
    area = float(item.get("area", 1200.0))
    depth = float(item.get("depth", 12.0))
    ratio = float(item.get("ratio", 0.5))
    if t in ("O", "COURTYARD", "RING"):
        # Square ring whose net (ring) area ≈ area, with a central courtyard hole.
        side = math.sqrt(area / 0.7975)        # outer side; hole = 0.45·side
        h = 0.45 * side
        shell = box(-side / 2, -side / 2, side / 2, side / 2)
        hole = box(-h / 2, -h / 2, h / 2, h / 2)
        poly = shell.difference(hole)
        return poly if poly.is_valid else poly.buffer(0)
    model = build_shape_model(area=area, building_type=t, building_depth=depth, shape_ratio=ratio)
    poly = model.polygon
    return poly if poly.is_valid else poly.buffer(0)


def _poly_to_building(poly: Polygon, item: dict[str, Any]) -> dict[str, Any]:
    bdict: dict[str, Any] = {
        "building_id": str(item.get("building_id") or item.get("label") or "building"),
        "label": item.get("label", item.get("building_id", "building")),
        "type": str(item.get("type", "I")).upper(),
        "storeys": int(item.get("storeys", 5)),
        "boundary": [[round(float(x), 3), round(float(y), 3), 0.0] for x, y in poly.exterior.coords],
    }
    holes = [[[round(float(x), 3), round(float(y), 3)] for x, y in ring.coords] for ring in poly.interiors]
    if holes:
        bdict["holes"] = holes
    return bdict


def _principal_angle(poly: Polygon) -> float:
    mrr = poly.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]
    edges = [(coords[i], coords[(i + 1) % 4]) for i in range(4)]
    (ax, ay), (bx, by) = max(edges, key=lambda e: math.dist(*e))
    return math.degrees(math.atan2(by - ay, bx - ax))


def _tangent_angle(line: LineString, d: float, total: float) -> float:
    d0 = min(max(d, 0.0), max(total - 0.5, 0.0))
    p1 = line.interpolate(d0)
    p2 = line.interpolate(min(d0 + 1.0, total))
    if p1.distance(p2) < 1e-9 and d0 > 1.0:
        p1 = line.interpolate(d0 - 1.0)
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))


def _frame_extents(poly: Polygon, angle_deg: float) -> tuple[float, float]:
    """Footprint extent along (u) and across (v) a frame rotated by ``angle_deg``."""
    aligned = affinity.rotate(poly, -angle_deg, origin=(0.0, 0.0))
    minx, miny, maxx, maxy = aligned.bounds
    return maxx - minx, maxy - miny


def _valid_placement(
    fp: Polygon,
    buildable: Polygon,
    spine_line: LineString,
    corridor_half: float,
    placed: list[Polygon],
    separation: float,
) -> bool:
    if not buildable.buffer(1e-6).contains(fp):
        return False
    if fp.distance(spine_line) < corridor_half - 1e-6:
        return False
    for q in placed:
        if fp.distance(q) < separation - 1e-6:
            return False
    return True


def _nearest_gap(fp: Polygon, placed: list[Polygon]) -> float | None:
    if not placed:
        return None
    return min(fp.distance(q) for q in placed)


# ===========================================================================
# Step 6 — drop-offs (a consequence of entrances)
# ===========================================================================

def generate_dropoffs(
    orientation: dict[str, Any],
    vehicular: dict[str, Any],
    *,
    max_walk: float = DROPOFF_MAX_WALK_M,
) -> dict[str, Any]:
    """Place one drop-off per public entrance on the nearest road segment.

    A drop-off is generated **from** an entrance — it lands on the closest point of
    the vehicular network within ``max_walk`` of that entrance, so it is always
    attached to both a building and a road and never sits in open space. Entrances
    with no road within reach are reported as rejected (a real placement gap).
    """
    ent_pts = _public_entrance_index(orientation)
    net = _network_from_circulation(vehicular)
    drops: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for bid, (ex, ey) in ent_pts.items():
        ent = Point(ex, ey)
        if net is None:
            rejected.append({"building_id": bid, "reason": "no vehicular network"})
            continue
        on_road = nearest_points(ent, net)[1]
        d = float(ent.distance(on_road))
        if d > max_walk:
            rejected.append({"building_id": bid, "reason": f"nearest road {round(d, 1)} m away (> {max_walk} m)"})
            continue
        drops.append({
            "drop_id": f"{bid}_dropoff",
            "building_id": bid,
            "point": [round(on_road.x, 3), round(on_road.y, 3), 0.0],
            "entrance_point": [round(ex, 3), round(ey, 3), 0.0],
            "walk_distance_m": round(d, 2),
            "reason": (f"On the road {round(d, 1)} m from the {bid} public entrance — "
                       f"adjacent, within walking distance, not blocking the corridor."),
        })

    return {
        "dropoffs": drops,
        "rejected": rejected,
        "summary": (f"{len(drops)} drop-off(s) placed"
                    + (f", {len(rejected)} entrance(s) had no road within {max_walk} m" if rejected else ".")),
    }


# ===========================================================================
# Step 10 — planning quality scoring
# ===========================================================================

def score_masterplan(
    buildable: Polygon,
    buildings: list[dict[str, Any]],
    spine: dict[str, Any],
    vehicular: dict[str, Any],
    pedestrian: dict[str, Any],
    parking_access: dict[str, Any],
    orientation: dict[str, Any],
    fire: dict[str, Any],
    egress: dict[str, Any],
    conflicts: dict[str, Any],
    *,
    threshold: float = SCORE_THRESHOLD,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Score the layout on five dimensions and accept / reject it.

    Sub-scores (0–1): building placement (setback + spacing + access), vehicular
    network (connectivity + hierarchy), pedestrian network (directness + safety +
    accessibility), entrance quality (public doors facing arrival), fire safety
    (reach coverage + evacuation compliance). A layout is **rejected** when the
    weighted overall falls below ``threshold`` or a hard constraint fails (any
    building outside the envelope, or any building unreachable by an appliance).
    """
    weights = weights or SCORE_WEIGHTS
    if not buildings:
        return {"sub_scores": {k: 0.0 for k in (weights or SCORE_WEIGHTS)}, "overall": 0.0,
                "threshold": threshold, "accepted": False, "hard_constraints_ok": False,
                "summary": "REJECTED — no buildings were placed."}
    bpolys = [_to_polygon(b["boundary"]) for b in buildings]
    n = len(bpolys) or 1

    # building placement
    inside = sum(1 for p in bpolys if buildable.buffer(0.05).contains(p)) / n
    pairs = [(i, j) for i in range(len(bpolys)) for j in range(i + 1, len(bpolys))]
    spacing = (sum(1 for i, j in pairs if bpolys[i].distance(bpolys[j]) >= MIN_BUILDING_SEPARATION_M - 1e-6)
               / len(pairs)) if pairs else 1.0
    spine_line = LineString([(x, y) for x, y, *_ in spine["vehicular_spine"]])
    access = sum(1 for p in bpolys if p.distance(spine_line) <= ACCESS_MAX_M) / n
    placement_score = _mean([inside, spacing, access])

    # vehicular
    veh_net = _network_from_circulation(vehicular)
    reach = (sum(1 for p in bpolys if veh_net is not None and veh_net.distance(p) <= MAX_FIRE_DISTANCE_M) / n)
    has_spine = any(p.get("hierarchy") == "primary_spine" for p in vehicular.get("paths", []))
    has_loop = any(p.get("hierarchy") == "fire_loop" for p in vehicular.get("paths", []))
    hierarchy = 0.5 + 0.25 * has_spine + 0.25 * has_loop
    veh_score = _mean([reach, hierarchy])

    # pedestrian
    direct = []
    for p in pedestrian.get("paths", []):
        pl = p.get("polyline") or []
        if len(pl) >= 2 and p.get("length_m", 0) > 1e-6:
            straight = math.dist(pl[0][:2], pl[-1][:2])
            direct.append(min(1.0, straight / p["length_m"]))
    directness = _mean(direct) if direct else 0.6
    crossings = (conflicts.get("counts", {}) or {}).get("pedestrian_vehicle_crossing", 0)
    safety = max(0.0, 1.0 - 0.1 * crossings)
    pz = parking_access.get("zones") or []
    accessibility = (sum(1 for z in pz if z.get("accessible_parking_ok")) / len(pz)) if pz else 1.0
    pedestrian_score = _mean([directness, safety, accessibility])

    # entrance quality
    obs = orientation.get("buildings") or []
    ent_ok = (sum(1 for b in obs if any(e.get("role") == "public" and e.get("faces") in ("circulation", "public_entry")
                                        for e in b.get("entrances", []))) / len(obs)) if obs else 0.0
    entrance_score = ent_ok

    # fire safety
    fb = fire.get("buildings") or []
    coverage = (sum(1 for b in fb if b.get("within_reach")) / len(fb)) if fb else 0.0
    eg = egress.get("buildings") or []
    evacuation = (sum(1 for r in eg if r.get("compliant")) / len(eg)) if eg else 0.0
    fire_score = _mean([coverage, evacuation])

    subs = {
        "building_placement": round(placement_score, 3),
        "vehicular_network": round(veh_score, 3),
        "pedestrian_network": round(pedestrian_score, 3),
        "entrance_quality": round(entrance_score, 3),
        "fire_safety": round(fire_score, 3),
    }
    overall = round(sum(subs[k] * weights[k] for k in subs), 3)
    hard_ok = inside >= 0.999 and coverage >= 0.999
    accepted = bool(overall >= threshold and hard_ok)

    reasons = []
    if inside < 0.999:
        reasons.append("a building falls outside the buildable envelope")
    if coverage < 0.999:
        reasons.append("a building is not reachable by a fire appliance")
    if overall < threshold:
        reasons.append(f"overall {overall} below threshold {threshold}")
    verdict = "ACCEPTED" if accepted else "REJECTED — " + "; ".join(reasons or ["below threshold"])

    return {
        "sub_scores": subs,
        "overall": overall,
        "threshold": threshold,
        "accepted": accepted,
        "hard_constraints_ok": bool(hard_ok),
        "summary": f"{verdict} (overall {overall}/1.0).",
    }


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


# ===========================================================================
# DEEP 17-STEP PIPELINE
#
# Conceptual flow (what the agent now "thinks"):
#   Site → Public Realm Structure → Arrival Hierarchy → Building Hierarchy →
#   Frontages → Entrances → Circulation → Fire & Service → Optimization
#
# Buildings address an abstract **spatial armature** (primary axis + frontage
# lines + open-space tiers) laid in step 3; the drivable streets are then
# engineered onto that same armature in step 11 — the urban-design "framework →
# blocks → streets" order, not "buildings then paths".
# ===========================================================================

# ---------------------------------------------------------------------------
# Step 1 — Read Site
# ---------------------------------------------------------------------------

def read_site(site_model: dict[str, Any]) -> dict[str, Any]:
    """Parse the site into geometry the rest of the pipeline reasons over.

    Returns the site polygon, its edges (from the model or synthesised from the
    boundary), area, centroid and long-axis bearing — the raw reading every later
    step builds on.
    """
    boundary = site_model.get("boundary") or site_model.get("site_boundary") or []
    poly = _to_polygon(boundary)
    sides = _site_sides(site_model, poly)
    c = poly.centroid
    mrr = poly.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]
    pairs = [(coords[i], coords[(i + 1) % 4]) for i in range(len(coords))]
    (ax, ay), (bx, by) = max(pairs, key=lambda e: math.dist(*e)) if pairs else ((0, 0), (1, 0))
    axis = round(math.degrees(math.atan2(by - ay, bx - ax)), 2)
    return {
        "boundary": boundary,
        "polygon": poly,
        "sides": sides,
        "area_sqm": round(float(poly.area), 2),
        "centroid": [round(c.x, 3), round(c.y, 3)],
        "long_axis_deg": axis,
        "n_sides": len(sides),
        "reason": (f"Read a {round(poly.area)} m² site with {len(sides)} edge(s); "
                   f"long axis bears {axis}°."),
        "summary": f"Site {round(poly.area)} m², {len(sides)} edge(s), long axis {axis}°.",
    }


def _site_sides(site_model: dict[str, Any], poly: Polygon) -> list[dict[str, Any]]:
    sides = list(site_model.get("sides") or [])
    if sides:
        return sides
    coords = list(poly.exterior.coords)[:-1]
    n = len(coords)
    return [{"side_index": i, "start": [coords[i][0], coords[i][1], 0.0],
             "end": [coords[(i + 1) % n][0], coords[(i + 1) % n][1], 0.0],
             "adjacent_road": None} for i in range(n)]


def _seg_len(side: dict[str, Any]) -> float:
    s = side.get("start", [0, 0]); e = side.get("end", [0, 0])
    return math.hypot(float(e[0]) - float(s[0]), float(e[1]) - float(s[1]))


def _edge_mid_normal(side: dict[str, Any], poly: Polygon) -> tuple[tuple[float, float], tuple[float, float]]:
    s = side.get("start", [0, 0]); e = side.get("end", [0, 0])
    sx, sy, ex, ey = float(s[0]), float(s[1]), float(e[0]), float(e[1])
    mid = ((sx + ex) / 2.0, (sy + ey) / 2.0)
    dx, dy = ex - sx, ey - sy
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    c = poly.centroid
    if (c.x - mid[0]) * nx + (c.y - mid[1]) * ny < 0:
        nx, ny = -nx, -ny
    return mid, (nx, ny)


# ---------------------------------------------------------------------------
# Step 2 — Determine Public / Private / Service Edges
# ---------------------------------------------------------------------------

_PUBLIC_EDGE_HIER: tuple[str, ...] = ("main", "primary")
_SERVICE_EDGE_HIER: tuple[str, ...] = ("secondary",)


def classify_site_edges(site_model: dict[str, Any], site: dict[str, Any] | None = None) -> dict[str, Any]:
    """Label every site edge **public / service / private**.

    The edge a building fronts dictates its character: a *public* edge (main road)
    is the address and arrival face; a *service* edge (secondary road) takes
    loading and back-of-house; a *private* edge (pedestrian path or no road) is the
    quiet, green side. This is the structuring decision the whole layout hangs on.
    """
    site = site or read_site(site_model)
    poly = site["polygon"]
    out: list[dict[str, Any]] = []
    for s in site["sides"]:
        ar = s.get("adjacent_road")
        h = ar.get("hierarchy") if isinstance(ar, dict) else None
        if h in _PUBLIC_EDGE_HIER:
            role = "public"
        elif h in _SERVICE_EDGE_HIER:
            role = "service"
        else:
            role = "private"
        mid, nrm = _edge_mid_normal(s, poly)
        name = ar.get("name") if isinstance(ar, dict) else None
        out.append({
            "side_index": int(s.get("side_index", len(out))),
            "role": role,
            "road_name": name,
            "hierarchy": h,
            "length_m": round(_seg_len(s), 2),
            "midpoint": [round(mid[0], 3), round(mid[1], 3), 0.0],
            "inward_normal": [round(nrm[0], 6), round(nrm[1], 6)],
            "reason": (f"{role} edge"
                       + (f" on {name} ({h})" if name else f" ({h or 'no adjacent road'})")),
        })
    npub = sum(1 for r in out if r["role"] == "public")
    nsvc = sum(1 for r in out if r["role"] == "service")
    npriv = sum(1 for r in out if r["role"] == "private")
    return {
        "edges": out,
        "public": [r for r in out if r["role"] == "public"],
        "service": [r for r in out if r["role"] == "service"],
        "private": [r for r in out if r["role"] == "private"],
        "summary": f"{npub} public, {nsvc} service, {npriv} private edge(s).",
    }


# ---------------------------------------------------------------------------
# Step 3 — Create Spatial Hierarchy (the public-realm structure / armature)
# ---------------------------------------------------------------------------

def build_public_realm_structure(
    site_model: dict[str, Any],
    edges: dict[str, Any] | None = None,
    *,
    default_setback: float = 5.0,
    spine_width: float = DEFAULT_SPINE_WIDTH_M,
) -> dict[str, Any]:
    """Lay the public-realm structure in the *empty* site.

    Reserves the buildable envelope (setbacks), anchors a **primary movement axis**
    at the public entry, derives a **fire loop** just inside the envelope, and
    tiers the open space (forecourt band at the public edge → central spine →
    green buffer at the private edge). Buildings will address the *frontage lines*
    of this armature; the drivable streets are engineered onto it later.
    """
    site = read_site(site_model)
    edges = edges or classify_site_edges(site_model, site)
    margins = reserve_site_margins(site_model, default_setback=default_setback)
    buildable = margins["buildable_polygon"]
    access = plan_access_structure(site_model)
    armature = generate_movement_spine(buildable, access["entries"], spine_width=spine_width)
    open_space = _open_space_tiers(buildable, edges, armature, site["polygon"], spine_width)
    frontage_lines = {
        "primary": armature["vehicular_spine"],          # the boulevard buildings address
        "secondary": armature.get("fire_loop") or [],    # the perimeter / fire-loop frontage
    }
    return {
        "margins": margins,
        "access": access,
        "entries": access["entries"],
        "buildable_polygon": buildable,
        "buildable_boundary": margins["buildable_boundary"],
        "armature": armature,
        "frontage_lines": frontage_lines,
        "open_space": open_space,
        "reason": ("Reserved the buildable envelope, anchored a primary movement axis at the "
                   "public entry, added a perimeter fire loop, and tiered the open space "
                   "(forecourt → central spine → green buffer)."),
        "summary": (f"Public-realm structure: envelope {margins['buildable_area_sqm']} m², "
                    f"primary axis + fire loop, {len(open_space)} open-space tier(s)."),
    }


def _open_space_tiers(
    buildable: Polygon,
    edges: dict[str, Any],
    armature: dict[str, Any],
    site_poly: Polygon,
    spine_width: float,
) -> dict[str, Any]:
    """Forecourt / central / green open-space bands (geometry for visualisation)."""
    tiers: dict[str, Any] = {}
    try:
        # Forecourt: the strip of envelope nearest the public edges.
        pub = [e for e in edges.get("edges", []) if e["role"] == "public"]
        if pub:
            bands = []
            for e in pub:
                mx, my, _ = e["midpoint"]
                nx, ny = e["inward_normal"]
                strip = LineString([(mx - ny * 200, my + nx * 200), (mx + ny * 200, my - nx * 200)])
                bands.append(strip.buffer(spine_width * 1.5))
            fc = unary_union(bands).intersection(buildable)
            fc = _largest_polygon(fc)
            if fc is not None and not fc.is_empty:
                tiers["forecourt"] = _poly_to_list(fc)
        # Central: a band around the primary spine.
        sp = armature.get("vehicular_spine") or []
        if len(sp) >= 2:
            cl = LineString([(x, y) for x, y, *_ in sp]).buffer(spine_width * 1.2).intersection(buildable)
            cl = _largest_polygon(cl)
            if cl is not None and not cl.is_empty:
                tiers["central"] = _poly_to_list(cl)
        # Green: envelope strip nearest the private edges.
        priv = [e for e in edges.get("edges", []) if e["role"] == "private"]
        if priv:
            bands = []
            for e in priv:
                mx, my, _ = e["midpoint"]
                nx, ny = e["inward_normal"]
                strip = LineString([(mx - ny * 200, my + nx * 200), (mx + ny * 200, my - nx * 200)])
                bands.append(strip.buffer(spine_width))
            gr = unary_union(bands).intersection(buildable)
            gr = _largest_polygon(gr)
            if gr is not None and not gr.is_empty:
                tiers["green"] = _poly_to_list(gr)
    except Exception:
        pass
    return tiers


# ---------------------------------------------------------------------------
# Step 4 — Assign Building Importance
# ---------------------------------------------------------------------------

def assign_building_importance(program: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank the program by civic prominence and assign a tier.

    Importance = floor area × storeys (a GFA proxy) × a typology weight, unless the
    item carries an explicit ``importance``. The ranking drives *which* frontage a
    building gets (prominent buildings address the primary axis) and the *order* in
    which buildings claim slots.
    """
    scored: list[tuple[int, float]] = []
    for i, it in enumerate(program or []):
        area = float(it.get("area", 1000.0))
        storeys = max(int(it.get("storeys", 5)), 1)
        t = str(it.get("type", "I")).upper()
        base = float(it["importance"]) if it.get("importance") is not None else area * storeys
        scored.append((i, base * IMPORTANCE_TYPE_WEIGHT.get(t, 1.0)))

    order = sorted(range(len(scored)), key=lambda k: -scored[k][1])
    n = len(scored) or 1
    ranked: list[dict[str, Any]] = []
    for rank, k in enumerate(order):
        idx, score = scored[k]
        frac = rank / n
        if rank == 0 and n >= 3:
            tier = "landmark"
        elif frac < 0.34:
            tier = "primary"
        elif frac < 0.67:
            tier = "secondary"
        else:
            tier = "background"
        d = dict(program[idx])
        d["building_id"] = str(d.get("building_id") or d.get("label") or f"b{idx}")
        d["importance_score"] = round(score, 1)
        d["importance_rank"] = rank + 1
        d["tier"] = tier
        d["importance_reason"] = (
            f"Rank {rank + 1}/{n} (prominence {round(score)}) → {tier}: "
            f"{'takes a prime central frontage' if tier in ('landmark', 'primary') else 'lines a secondary frontage'}."
        )
        ranked.append(d)
    return {
        "buildings": ranked,
        "order": [ranked[i]["building_id"] for i in range(len(ranked))],
        "summary": ("Ranked " + str(n) + " building(s) by prominence: "
                    + ", ".join(f"{b['building_id']}={b['tier']}" for b in ranked)),
    }


# ---------------------------------------------------------------------------
# Step 5 — Determine Building Frontages
# ---------------------------------------------------------------------------

def determine_building_frontages(
    ranked_buildings: list[dict[str, Any]],
    realm: dict[str, Any],
) -> dict[str, Any]:
    """Decide which frontage line each building addresses, from its tier.

    Landmark / primary buildings front the **primary axis** (the most visible,
    arrival-facing frontage); secondary / background buildings line the
    **secondary** perimeter frontage. With no secondary frontage available every
    building addresses the primary axis.
    """
    has_secondary = bool(realm["frontage_lines"]["secondary"])
    out: list[dict[str, Any]] = []
    for b in ranked_buildings:
        tier = b.get("tier", "secondary")
        if tier in ("landmark", "primary") or not has_secondary:
            front, reason = "primary", "Prominent building → addresses the primary movement axis (the boulevard)."
        else:
            front, reason = "secondary", "Secondary building → lines the perimeter / fire-loop frontage."
        out.append({"building_id": b["building_id"], "frontage": front, "tier": tier, "reason": reason})
    n_pri = sum(1 for f in out if f["frontage"] == "primary")
    return {
        "frontages": out,
        "summary": f"{n_pri} primary-frontage, {len(out) - n_pri} secondary-frontage building(s).",
    }


# ---------------------------------------------------------------------------
# Step 6 — Place Buildings (importance-first, frontage-driven, slot-scored)
# ---------------------------------------------------------------------------

def place_buildings_by_frontage(
    buildable: Polygon,
    realm: dict[str, Any],
    ranked_buildings: list[dict[str, Any]],
    frontages: dict[str, Any],
    *,
    separation: float = MIN_BUILDING_SEPARATION_M,
    spine_clearance: float = SPINE_CLEARANCE_M,
    strict_frontage: bool = True,
) -> dict[str, Any]:
    """Attach buildings to their assigned frontage line, most important first.

    Each building marches along its assigned frontage (falling back to the other
    frontage if its own is full); at the first workable station it picks the *side*
    whose footprint best **addresses the primary axis** — so frontage is an
    intentional design move, not a first-fit accident. Footprints stay inside the
    envelope, clear of the corridor, and separated from every neighbour, else they
    are reported ``unplaced`` rather than forced.

    With ``strict_frontage=False`` every building tries the **primary** axis first
    (still in importance order, so prominent buildings get first pick) before the
    perimeter — a more compact packing the optimiser uses to recover completeness
    on tight sites.
    """
    arm = realm["armature"]
    corridor_half = arm["spine_width_m"] / 2.0 + spine_clearance
    primary_line = LineString([(x, y) for x, y, *_ in arm["vehicular_spine"]])
    lines: dict[str, LineString] = {"primary": primary_line}
    if arm.get("fire_loop") and len(arm["fire_loop"]) >= 2:
        lines["secondary"] = LineString([(x, y) for x, y, *_ in arm["fire_loop"]])
    fr_by = {f["building_id"]: f["frontage"] for f in frontages["frontages"]}

    placed: list[dict[str, Any]] = []
    placed_polys: list[Polygon] = []
    unplaced: list[str] = []

    for item in ranked_buildings:  # already in importance order
        base = _make_footprint(item)
        principal = _principal_angle(base)
        assigned = fr_by.get(item["building_id"], "primary")
        if strict_frontage:
            try_order = [assigned] + [k for k in lines if k != assigned]
        else:
            # Compact packing: everyone addresses the primary axis first.
            try_order = ["primary"] + [k for k in lines if k != "primary"]
        best: tuple[Polygon, float, int, str] | None = None

        for fname in try_order:
            if best is not None:
                break
            line = lines.get(fname)
            if line is None:
                continue
            total_len = line.length
            d = 0.0
            while d <= total_len and best is None:
                cands: list[tuple[Polygon, int]] = []
                for side in (1, -1):
                    pt = line.interpolate(d)
                    tang = _tangent_angle(line, d, total_len)
                    cand = affinity.rotate(base, tang - principal, origin=(0.0, 0.0))
                    _, dv = _frame_extents(cand, tang)
                    vx = math.cos(math.radians(tang + 90.0))
                    vy = math.sin(math.radians(tang + 90.0))
                    offset = corridor_half + dv / 2.0 + 0.5
                    fp = affinity.translate(cand, xoff=pt.x + vx * side * offset,
                                            yoff=pt.y + vy * side * offset)
                    if _valid_placement(fp, buildable, line, corridor_half, placed_polys, separation):
                        cands.append((fp, side))
                if cands:
                    if len(cands) == 1:
                        fp, side = cands[0]
                    elif fname == "secondary":
                        # On the perimeter, face the building inward toward the boulevard.
                        fp, side = min(cands, key=lambda c: c[0].distance(primary_line))
                    else:
                        # On the primary axis keep the deterministic side order so the
                        # packing stays as dense as the proven spine placement.
                        fp, side = cands[0]
                    best = (fp, d, side, fname)
                d += PLACEMENT_MARCH_STEP_M

        if best is None:
            unplaced.append(str(item.get("building_id")))
            continue
        fp, d_at, side, fname = best
        gap = _nearest_gap(fp, placed_polys)
        bdict = _poly_to_building(fp, item)
        bdict["tier"] = item.get("tier")
        bdict["importance_rank"] = item.get("importance_rank")
        bdict["frontage"] = fname
        bdict["placement_reason"] = (
            f"{str(item.get('tier', 'secondary')).title()} building on the {fname} frontage at "
            f"~{round(d_at)} m, {'left' if side > 0 else 'right'} side, addressing the boulevard; "
            f"{'clear of all neighbours' if gap is None else f'{round(gap, 1)} m to nearest building'}, "
            f"inside the envelope, clear of the corridor."
        )
        placed.append(bdict)
        placed_polys.append(fp)

    placed.sort(key=lambda b: b.get("importance_rank") or 99)
    return {
        "buildings": placed,
        "unplaced": unplaced,
        "summary": (f"{len(placed)}/{len(ranked_buildings)} building(s) placed on their frontages"
                    + (f"; {len(unplaced)} could not fit ({', '.join(unplaced)})" if unplaced else ".")),
    }


# ---------------------------------------------------------------------------
# Step 8 — Generate Arrival Spaces (forecourts scaled by prominence)
# ---------------------------------------------------------------------------

def generate_arrival_spaces(
    orientation: dict[str, Any],
    buildings: list[dict[str, Any]],
    ranked_buildings: list[dict[str, Any]],
    buildable: Polygon,
) -> dict[str, Any]:
    """Carve a forecourt in front of each prominent building's public entrance.

    The arrival space is a rectangle projected out from the public door along its
    facing direction, sized by tier (``ARRIVAL_DEPTH_BY_TIER``), clipped to the
    envelope and cut clear of all footprints. Background buildings get none — the
    hierarchy of arrival mirrors the hierarchy of buildings.
    """
    tier_by = {b["building_id"]: b.get("tier", "secondary") for b in ranked_buildings}
    bpolys = [_to_polygon(b["boundary"]) for b in (buildings or [])]
    union = unary_union(bpolys) if bpolys else None

    ent_pt = _public_entrance_index(orientation)
    ent_dir: dict[str, list[float]] = {}
    for b in orientation.get("buildings", []):
        for e in b.get("entrances", []):
            if e.get("role") == "public":
                ent_dir[b["building_id"]] = e.get("direction") or [0.0, 1.0]
                break

    spaces: list[dict[str, Any]] = []
    for bid, (ex, ey) in ent_pt.items():
        tier = tier_by.get(bid, "secondary")
        depth = ARRIVAL_DEPTH_BY_TIER.get(tier, 0.0)
        if depth <= 0:
            continue
        ux, uy = ent_dir.get(bid, [0.0, 1.0])
        px, py = -uy, ux
        w = max(8.0, 1.4 * depth)
        p1 = (ex + px * w / 2, ey + py * w / 2)
        p2 = (ex - px * w / 2, ey - py * w / 2)
        p3 = (p2[0] + ux * depth, p2[1] + uy * depth)
        p4 = (p1[0] + ux * depth, p1[1] + uy * depth)
        fc: Any = Polygon([p1, p2, p3, p4])
        if not fc.is_valid:
            fc = fc.buffer(0)
        if buildable is not None:
            fc = fc.intersection(buildable.buffer(2.0))
        if union is not None:
            fc = fc.difference(union)
        fc = _largest_polygon(fc)
        if fc is None or fc.is_empty or fc.area < 4.0:
            continue
        spaces.append({
            "building_id": bid,
            "tier": tier,
            "boundary": _poly_to_list(fc),
            "area_sqm": round(float(fc.area), 1),
            "reason": (f"{tier.title()} arrival forecourt (~{round(fc.area)} m²) in front of the "
                       f"{bid} public entrance, scaled to its prominence."),
        })
    return {
        "arrival_spaces": spaces,
        "summary": f"{len(spaces)} arrival space(s) for the more prominent building(s).",
    }


# ---------------------------------------------------------------------------
# Step 13 — Generate Fire Access (appliance reach + provisions)
# ---------------------------------------------------------------------------

def generate_fire_access(
    buildings: list[dict[str, Any]],
    vehicular: dict[str, Any],
    armature: dict[str, Any],
    *,
    max_distance: float = MAX_FIRE_DISTANCE_M,
) -> dict[str, Any]:
    """Resolve fire-appliance access from the drivable network + fire loop.

    For each building it finds the nearest appliance standing point on the network,
    its reach distance, and whether that is within ``max_distance``. Any building
    beyond reach yields a **provision** (extend a fire lane / hammerhead toward it)
    — fire access is *generated*, not only checked.
    """
    net = _network_from_circulation(vehicular)
    loop = armature.get("fire_loop") or []
    points: list[dict[str, Any]] = []
    beyond: list[str] = []
    for i, b in enumerate(buildings or []):
        poly = _to_polygon(b["boundary"])
        bid = str(b.get("building_id") or f"b{i}")
        if net is None:
            points.append({"building_id": bid, "point": None, "distance_m": None, "within_reach": False})
            beyond.append(bid)
            continue
        on = nearest_points(poly, net)[1]
        d = float(poly.distance(net))
        ok = d <= max_distance + 1e-6
        points.append({"building_id": bid, "point": [round(on.x, 3), round(on.y, 3), 0.0],
                       "distance_m": round(d, 2), "within_reach": ok})
        if not ok:
            beyond.append(bid)
    provisions = [{"type": "fire_lane_or_hammerhead", "building_id": b,
                   "reason": (f"{b} sits beyond {max_distance} m of the appliance network — "
                              f"extend a fire lane / add a hammerhead within reach.")}
                  for b in beyond]
    n_ok = len(points) - len(beyond)
    return {
        "fire_loop": loop,
        "appliance_points": points,
        "beyond_reach": beyond,
        "provisions": provisions,
        "summary": (f"Appliance can stand within {max_distance} m of {n_ok}/{len(points)} building(s)"
                    + (f"; {len(beyond)} need a fire-lane extension." if beyond else ".")),
    }


# ---------------------------------------------------------------------------
# Step 15 — Evaluate Urban Design Quality (score that penalises dropped program)
# ---------------------------------------------------------------------------

def evaluate_urban_design(
    buildable: Polygon,
    buildings: list[dict[str, Any]],
    spine: dict[str, Any],
    vehicular: dict[str, Any],
    pedestrian: dict[str, Any],
    parking_access: dict[str, Any],
    orientation: dict[str, Any],
    fire: dict[str, Any],
    egress: dict[str, Any],
    conflicts: dict[str, Any],
    arrival_spaces: list[dict[str, Any]],
    total_program: int,
    *,
    threshold: float = SCORE_THRESHOLD,
) -> dict[str, Any]:
    """Score the layout on seven axes and accept / reject it.

    Wraps the five core sub-scores from :func:`score_masterplan` and adds two:
    ``program_completeness`` (placed / total — so dropping buildings can never
    raise the score) and ``public_realm`` (arrival provision for the prominent
    buildings). A layout is rejected when the weighted overall is below
    ``threshold``, a hard constraint fails, **or** completeness is below
    ``PROGRAM_COMPLETENESS_GATE``.
    """
    base = score_masterplan(buildable, buildings, spine, vehicular, pedestrian,
                            parking_access, orientation, fire, egress, conflicts,
                            threshold=threshold)
    subs = dict(base["sub_scores"])
    placed = len(buildings)
    total = max(int(total_program), 1)
    completeness = placed / total
    pr = (len(arrival_spaces) / placed) if placed else 0.0
    subs["program_completeness"] = round(completeness, 3)
    subs["public_realm"] = round(min(1.0, 0.5 + pr), 3)

    overall = round(sum(subs.get(k, 0.0) * w for k, w in URBAN_DESIGN_WEIGHTS.items()), 3)
    hard_ok = bool(base.get("hard_constraints_ok", False)) and completeness >= PROGRAM_COMPLETENESS_GATE
    accepted = bool(overall >= threshold and hard_ok)

    reasons: list[str] = []
    if completeness < PROGRAM_COMPLETENESS_GATE:
        reasons.append(f"only {placed}/{total} of the program placed")
    if not base.get("hard_constraints_ok", False):
        reasons.append("a building is outside the envelope or unreachable by a fire appliance")
    if overall < threshold:
        reasons.append(f"overall {overall} below threshold {threshold}")
    verdict = "ACCEPTED" if accepted else "REJECTED — " + "; ".join(reasons or ["below threshold"])

    return {
        "sub_scores": subs,
        "overall": overall,
        "threshold": threshold,
        "accepted": accepted,
        "hard_constraints_ok": bool(hard_ok),
        "program_completeness": round(completeness, 3),
        "summary": f"{verdict} (overall {overall}/1.0).",
    }


# ---------------------------------------------------------------------------
# Step 16 — Optimize Layout (compose → evaluate → keep best over variants)
# ---------------------------------------------------------------------------

def _enrich_placement(placement: dict[str, Any], ranked_buildings: list[dict[str, Any]]) -> None:
    """Stamp tier / rank / frontage onto buildings placed by the spine packer."""
    meta = {b["building_id"]: b for b in ranked_buildings}
    for b in placement.get("buildings", []):
        m = meta.get(b["building_id"], {})
        b["tier"] = m.get("tier")
        b["importance_rank"] = m.get("importance_rank")
        b["frontage"] = "secondary" if "perimeter" in b.get("placement_reason", "") else "primary"


def _compose_layout(
    site_model: dict[str, Any],
    realm: dict[str, Any],
    ranked_buildings: list[dict[str, Any]],
    *,
    separation: float,
    spine_width: float,
    parking_ratio: float,
    score_threshold: float,
    total_program: int,
    strict_frontage: bool = True,
) -> dict[str, Any]:
    """Run steps 5–15 once for a given placement separation; return the full layout."""
    buildable = realm["buildable_polygon"]
    entries = realm["entries"]
    armature = realm["armature"]
    site_poly = _to_polygon(site_model.get("boundary") or [])

    frontages = determine_building_frontages(ranked_buildings, realm)                       # 5
    if strict_frontage:
        placement = place_buildings_by_frontage(buildable, realm, ranked_buildings,         # 6
                                                frontages, separation=separation, strict_frontage=True)
    else:
        # Compact packing: the proven spine placement, fed in importance order, so the
        # most prominent buildings still claim the prime slots first.
        placement = place_buildings_along_spine(buildable, armature, ranked_buildings, separation=separation)
        _enrich_placement(placement, ranked_buildings)
    buildings = placement["buildings"]

    # 10 — parking first so the vehicular network can serve it
    demand = compute_building_demand(buildings, parking_ratio=parking_ratio) if buildings else []
    parking = allocate_parking_zones(site_model, buildings, demand) if buildings else {"zones": []}

    # 7 — entrances (prelim → final once the network exists)
    orient0 = building_entrance_orientation(buildings, entries, None)
    vehicular = route_internal_circulation(site_model, entries, buildings, parking,          # 11
                                           path_width_m=spine_width, entrances_by_building=orient0)
    _overlay_framework(vehicular, armature, site_poly)
    orientation = building_entrance_orientation(buildings, entries, vehicular)

    arrival = generate_arrival_spaces(orientation, buildings, ranked_buildings, buildable)   # 8
    dropoffs = generate_dropoffs(orientation, vehicular)                                      # 9
    pedestrian = route_pedestrian_network(site_model, entries, buildings, parking, orientation)  # 12

    fire_access = generate_fire_access(buildings, vehicular, armature)                        # 13
    fire = check_fire_access(buildings, vehicular, strict=True)                               # 14
    egress = analyze_egress(buildings, vehicular)

    site_arrival = analyze_site_arrival(site_model, entries, orientation)
    parking_access = analyze_parking_access(buildings, parking, orientation, pedestrian)
    conflicts = detect_circulation_conflicts(vehicular, pedestrian, parking, fire)
    audit = audit_circulation(entries, orientation, vehicular, pedestrian,
                              parking_access, egress, fire, conflicts)
    score = evaluate_urban_design(buildable, buildings, armature, vehicular, pedestrian,     # 15
                                  parking_access, orientation, fire, egress, conflicts,
                                  arrival["arrival_spaces"], total_program, threshold=score_threshold)

    return {
        "frontages": frontages, "placement": placement, "buildings": buildings,
        "parking": parking, "entrances": orientation, "arrival": arrival,
        "dropoffs": dropoffs, "pedestrian": pedestrian, "vehicular": vehicular,
        "fire_access": fire_access, "fire": fire, "egress": egress,
        "site_access": site_arrival, "parking_access": parking_access,
        "conflicts": conflicts, "audit": audit, "score": score,
        "placed_count": len(buildings), "total": total_program, "separation_m": separation,
    }


def optimize_layout(
    site_model: dict[str, Any],
    realm: dict[str, Any],
    ranked_buildings: list[dict[str, Any]],
    *,
    spine_width: float = DEFAULT_SPINE_WIDTH_M,
    parking_ratio: float = 0.6,
    score_threshold: float = SCORE_THRESHOLD,
    base_separation: float = MIN_BUILDING_SEPARATION_M,
) -> dict[str, Any]:
    """Generate → evaluate → keep-best across a few placement variants.

    Re-runs the compose pass at several building separations and keeps the layout
    that places the **most** of the program and then scores highest — a real
    optimisation loop, not a single forward pass that reports failure.
    """
    total = len(ranked_buildings)
    # (name, separation, strict_frontage). Strict variants honour the tiered
    # frontages; the compact variant packs everyone onto the primary axis first to
    # recover completeness when a tight site can't host the perimeter frontage.
    variants = [
        ("strict", base_separation, True),
        ("compact", base_separation, False),
        ("compact-tight", max(3.0, base_separation - 2.0), False),
    ]
    trials: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    best_key: tuple[int, float] | None = None
    best_name = variants[0][0]
    for name, sep, strict in variants:
        layout = _compose_layout(site_model, realm, ranked_buildings, separation=sep,
                                 spine_width=spine_width, parking_ratio=parking_ratio,
                                 score_threshold=score_threshold, total_program=total,
                                 strict_frontage=strict)
        key = (layout["placed_count"], layout["score"]["overall"])
        trials.append({"variant": name, "separation_m": sep, "strict_frontage": strict,
                       "placed": layout["placed_count"], "overall": layout["score"]["overall"],
                       "accepted": layout["score"]["accepted"]})
        if best is None or key > best_key:  # type: ignore[operator]
            best, best_key, best_name = layout, key, name

    return {
        "best_layout": best,
        "best_variant": best_name,
        "trials": trials,
        "summary": (f"Optimised over {len(variants)} variant(s); kept '{best_name}' "
                    f"({best['placed_count']}/{total} placed, score {best['score']['overall']})."
                    if best else "No layout composed."),
    }


# ===========================================================================
# Orchestrator — the deep 17-step pipeline (Site → … → Output)
# ===========================================================================

def generate_masterplan(
    site_model: dict[str, Any],
    program: list[dict[str, Any]],
    *,
    default_setback: float = 5.0,
    spine_width: float = DEFAULT_SPINE_WIDTH_M,
    separation: float = MIN_BUILDING_SEPARATION_M,
    parking_ratio: float = 0.6,
    score_threshold: float = SCORE_THRESHOLD,
) -> dict[str, Any]:
    """Generate a masterplan with the deep **17-step** pipeline and score it.

    Conceptual flow — *Site → Public Realm Structure → Arrival Hierarchy →
    Building Hierarchy → Frontages → Entrances → Circulation → Fire & Service →
    Optimization* — run as 17 explicit steps:

        1  Read site                     10  Generate parking
        2  Classify public/private/      11  Vehicular network
           service edges                 12  Pedestrian desire lines
        3  Create spatial hierarchy      13  Generate fire access
        4  Assign building importance    14  Run fire constraints
        5  Determine building frontages  15  Evaluate urban-design quality
        6  Place buildings               16  Optimize layout
        7  Generate entrances            17  Output
        8  Generate arrival spaces
        9  Generate drop-offs

    Buildings address an abstract spatial **armature** (step 3); the drivable
    streets are engineered onto it (step 11). The quality gate (step 15) penalises
    dropped program, and the optimiser (step 16) keeps the best of several
    variants. Every step carries a human ``reason`` in the ``reasoning`` log and a
    structured entry in ``steps``.

    Returns one report with the new structured keys (``site``, ``edges``,
    ``public_realm``, ``importance``, ``frontages``, ``arrival_spaces``,
    ``fire_access``, ``optimization``, ``urban_design``, ``steps``) **and** the
    legacy keys (``margins``, ``access``, ``spine``, ``placement``, ``buildings``,
    ``entrances``, ``dropoffs``, ``parking``, ``vehicular_circulation``,
    ``pedestrian_circulation``, ``site_access``, ``parking_integration``,
    ``fire_safety_egress``, ``conflicts``, ``audit``, ``score``, ``reasoning``,
    ``summary``) for backward compatibility.
    """
    reasoning: list[str] = []
    steps: list[dict[str, Any]] = []

    def step(n: int, phase: str, title: str, summary: str, reason: str = "") -> None:
        steps.append({"n": n, "phase": phase, "title": title, "summary": summary, "reason": reason})
        reasoning.append(f"[{n}] {summary}")

    # ── Phase: Site ──────────────────────────────────────────────────────────
    site = read_site(site_model)                                                  # 1
    step(1, "Site", "Read site", site["summary"], site["reason"])

    # ── Phase: Public Realm Structure ────────────────────────────────────────
    edges = classify_site_edges(site_model, site)                                 # 2
    step(2, "Public Realm Structure", "Determine public/private/service edges", edges["summary"])
    realm = build_public_realm_structure(site_model, edges,                       # 3
                                         default_setback=default_setback, spine_width=spine_width)
    step(3, "Public Realm Structure", "Create spatial hierarchy", realm["summary"], realm["reason"])

    # ── Phase: Building Hierarchy ────────────────────────────────────────────
    importance = assign_building_importance(program)                              # 4
    ranked = importance["buildings"]
    step(4, "Building Hierarchy", "Assign building importance", importance["summary"])

    # ── Phase: Optimization wraps steps 5–15 (compose → evaluate → keep best) ─
    opt = optimize_layout(site_model, realm, ranked, spine_width=spine_width,     # 16
                          parking_ratio=parking_ratio, score_threshold=score_threshold,
                          base_separation=separation)
    L = opt["best_layout"] or _compose_layout(
        site_model, realm, ranked, separation=separation, spine_width=spine_width,
        parking_ratio=parking_ratio, score_threshold=score_threshold, total_program=len(ranked))

    # narrate steps 5–15 from the chosen layout
    step(5, "Frontages", "Determine building frontages", L["frontages"]["summary"])
    step(6, "Frontages", "Place buildings", L["placement"]["summary"])
    for b in L["buildings"]:
        reasoning.append(f"[6] {b['building_id']}: {b['placement_reason']}")
    if L["placement"]["unplaced"]:
        reasoning.append(f"[6] unplaced (no valid slot): {', '.join(L['placement']['unplaced'])}")
    step(7, "Entrances", "Generate entrances", L["entrances"]["summary"])
    step(8, "Arrival Hierarchy", "Generate arrival spaces", L["arrival"]["summary"])
    step(9, "Arrival Hierarchy", "Generate drop-offs", L["dropoffs"]["summary"])
    step(10, "Arrival Hierarchy", "Generate parking", L["parking"].get("summary", "n/a"))
    step(11, "Circulation", "Generate vehicular network", L["vehicular"]["summary"])
    step(12, "Circulation", "Generate pedestrian desire lines", L["pedestrian"]["summary"])
    step(13, "Fire & Service", "Generate fire access", L["fire_access"]["summary"])
    step(14, "Fire & Service", "Run fire constraints", f"{L['fire']['summary']} | {L['egress']['summary']}")
    step(15, "Optimization", "Evaluate urban-design quality", L["score"]["summary"])
    step(16, "Optimization", "Optimize layout", opt["summary"])
    step(17, "Optimization", "Output",
         "Assembled the masterplan report with all artifacts, a per-step reasoning log and the score.")

    return {
        # ---- new structured 17-step keys ----
        "site": site,
        "edges": edges,
        "public_realm": realm,
        "importance": importance,
        "frontages": L["frontages"],
        "arrival_spaces": L["arrival"],
        "fire_access": L["fire_access"],
        "optimization": opt,
        "urban_design": L["score"],
        "steps": steps,
        # ---- legacy keys (backward compatible) ----
        "margins": realm["margins"],
        "access": realm["access"],
        "spine": realm["armature"],
        "placement": L["placement"],
        "buildings": L["buildings"],
        "entrances": L["entrances"],
        "dropoffs": L["dropoffs"],
        "parking": L["parking"],
        "vehicular_circulation": L["vehicular"],
        "pedestrian_circulation": L["pedestrian"],
        "site_access": L["site_access"],
        "parking_integration": L["parking_access"],
        "fire_safety_egress": {"fire_access": L["fire"], "egress": L["egress"]},
        "conflicts": L["conflicts"],
        "audit": L["audit"],
        "score": L["score"],
        "reasoning": reasoning,
        "summary": (f"{L['placement']['summary']} | {L['score']['summary']} | "
                    f"{L['audit']['summary']} | {L['conflicts']['summary']}"),
    }


def _overlay_framework(vehicular: dict[str, Any], spine: dict[str, Any], site_poly: Polygon) -> None:
    """Tag connection corridors and append the spine + fire loop as framework paths."""
    for p in vehicular.get("paths", []):
        p["mode"] = "vehicular"
        p["hierarchy"] = "primary" if p.get("target_type") == "building" else "parking_access"

    half = spine["spine_width_m"] / 2.0

    def framework(pid: str, polyline: list, hierarchy: str) -> dict[str, Any]:
        line = LineString([(x, y) for x, y, *_ in polyline])
        buf = line.buffer(half, cap_style=2, join_style=2).intersection(site_poly)
        buf = _largest_polygon(buf)
        return {
            "path_id": pid, "polyline": polyline,
            "buffered_boundary": _poly_to_list(buf) if buf is not None and not buf.is_empty else [],
            "width_m": spine["spine_width_m"], "length_m": round(line.length, 2),
            "serves": "site", "target_type": "framework", "mode": "vehicular",
            "hierarchy": hierarchy, "routed_around": 0,
        }

    if spine.get("drivable_spine"):
        vehicular["paths"].append(framework("veh_spine", spine["drivable_spine"], "primary_spine"))
    if spine.get("fire_loop"):
        vehicular["paths"].append(framework("fire_loop", spine["fire_loop"], "fire_loop"))


# ===========================================================================
# Agent tool wrapper — exposes generate_masterplan to the reactive agent
#
# The reactive LangGraph agent discovers tools by an MCP-style definition and
# calls them with a flat argument dict, expecting a ``{success, data, metadata}``
# envelope. ``run_masterplan_tool`` adapts ``generate_masterplan`` to that shape:
# it builds a site_model from whatever the agent has (a site boundary is enough —
# the pipeline synthesises edges + a public frontage when roads are absent),
# derives a building program from the design brief, and returns a trimmed report
# plus ``placed_buildings`` in the agent's placed-building format.
# ===========================================================================

MASTERPLAN_TOOL_DEFINITION: dict[str, Any] = {
    "name": "generate_masterplan",
    "description": (
        "Generate a whole-site masterplan circulation-first (deep 17-step pipeline): "
        "classify public/service/private edges, build the public-realm armature, rank "
        "buildings by prominence, place them on their frontages, add entrances / arrival "
        "spaces / drop-offs / parking, route the vehicular + pedestrian networks, generate "
        "and validate fire access, then score on seven axes and optimise. Use for "
        "site-wide layout, circulation, or fire-access requests — not single-building "
        "placement."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_boundary": {"type": "array", "description": "Closed site polygon [[x,y,z?], ...]."},
            "program": {"type": "array", "description": "Optional explicit buildings: [{building_id,type,area,storeys}]."},
            "target_building_count": {"type": "integer", "description": "How many buildings to lay out when no explicit program is given."},
            "main_road_side_index": {"type": "integer", "description": "Optional index of the main-road site side (the public front)."},
            "default_setback": {"type": "number", "default": 5.0},
            "spine_width": {"type": "number", "default": 6.0},
            "separation": {"type": "number", "default": 6.0},
            "parking_ratio": {"type": "number", "default": 0.6},
            "score_threshold": {"type": "number", "default": 0.6},
        },
        "required": ["site_boundary"],
    },
}


_AUTO_PROGRAM_TYPES: tuple[str, ...] = ("H", "U", "L", "O", "T", "I", "X", "Y")
_VALID_TYPES: frozenset[str] = frozenset({"I", "L", "T", "U", "H", "X", "Y", "O"})


def program_from_brief(
    design_brief: Any = None,
    target_building_count: int | None = None,
) -> list[dict[str, Any]]:
    """Build a masterplan program from a DesignBrief dict (or a sensible default).

    Each brief building spec (``shape_preference``, ``footprint_area_sqm``,
    ``storeys``) becomes a program item. ``auto``/unknown shapes cycle through the
    typology palette so a mixed, legible layout results. With no brief, ``target_
    building_count`` generic buildings are produced.
    """
    items: list[dict[str, Any]] = []
    specs = design_brief.get("buildings") if isinstance(design_brief, dict) else None
    for i, spec in enumerate(specs or []):
        if not isinstance(spec, dict):
            continue
        shape = str(spec.get("shape_preference") or "auto").upper()
        if shape not in _VALID_TYPES:
            shape = _AUTO_PROGRAM_TYPES[i % len(_AUTO_PROGRAM_TYPES)]
        area = spec.get("footprint_area_sqm")
        storeys = spec.get("storeys")
        items.append({
            "building_id": f"B{i + 1}",
            "label": f"B{i + 1}",
            "type": shape,
            "area": float(area) if isinstance(area, (int, float)) and area > 0 else 1200.0,
            "storeys": int(storeys) if isinstance(storeys, (int, float)) and storeys else 5,
        })
    if not items:
        n = max(1, int(target_building_count or 1))
        for i in range(n):
            items.append({
                "building_id": f"B{i + 1}", "label": f"B{i + 1}",
                "type": _AUTO_PROGRAM_TYPES[i % len(_AUTO_PROGRAM_TYPES)],
                "area": 1200.0, "storeys": 5,
            })
    return items


def _masterplan_placed_buildings(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a masterplan report's buildings into the agent's placed-building format."""
    placed: list[dict[str, Any]] = []
    for b in report.get("buildings", []) or []:
        bnd = b.get("boundary") or []
        if not bnd:
            continue
        xs = [p[0] for p in bnd]
        ys = [p[1] for p in bnd]
        placed.append({
            "geometry_id": f"masterplan_{b.get('building_id')}",
            "building_id": b.get("building_id"),
            "label": b.get("label", b.get("building_id")),
            "shape_type": b.get("type"),
            "building_type": b.get("type"),  # explorer panel reads this key
            "tier": b.get("tier"),
            "boundary": bnd,
            "holes": b.get("holes", []),
            "centroid": [round(sum(xs) / len(xs), 3), round(sum(ys) / len(ys), 3)],
            "placement": {"reason": b.get("placement_reason", ""), "frontage": b.get("frontage")},
        })
    return placed


def run_masterplan_tool(
    site_boundary: list[list[float]] | None = None,
    *,
    program: list[dict[str, Any]] | None = None,
    design_brief: dict[str, Any] | None = None,
    target_building_count: int | None = None,
    sides: list[dict[str, Any]] | None = None,
    roads: dict[str, Any] | None = None,
    main_road_side_index: int | None = None,
    site_model: dict[str, Any] | None = None,
    default_setback: float = 5.0,
    spine_width: float = DEFAULT_SPINE_WIDTH_M,
    separation: float = MIN_BUILDING_SEPARATION_M,
    parking_ratio: float = 0.6,
    score_threshold: float = SCORE_THRESHOLD,
    layout_json: Any = None,  # accepted + ignored (the graph may inject it)
) -> dict[str, Any]:
    """Agent-facing wrapper around :func:`generate_masterplan`.

    Returns the standard ``{success, data, metadata}`` envelope. ``data`` carries a
    trimmed report (summary, score, steps, reasoning, edges) plus
    ``placed_buildings`` in the agent's placed-building format, so the explorer and
    the final report can read the result without parsing the full geometry payload.
    A site **boundary is enough**: missing sides/roads are synthesised by the
    pipeline (all-private edges, public frontage on the longest side).
    """
    model: dict[str, Any] = {}
    if isinstance(site_model, dict) and (site_model.get("boundary") or site_model.get("site_boundary")):
        model = dict(site_model)
    boundary = site_boundary or model.get("boundary") or model.get("site_boundary")
    if not isinstance(boundary, list) or len(boundary) < 3:
        return {"success": False, "data": {}, "error": "site_boundary missing or has fewer than 3 points",
                "metadata": {"tool_name": "generate_masterplan", "source": "python"}}
    model["boundary"] = boundary
    if sides is not None:
        model["sides"] = sides
    if isinstance(roads, dict):
        model["roads"] = roads
    elif main_road_side_index is not None:
        model["roads"] = {"main_road_side_index": int(main_road_side_index)}

    prog = program or program_from_brief(design_brief, target_building_count)
    try:
        report = generate_masterplan(
            model, prog,
            default_setback=default_setback, spine_width=spine_width,
            separation=separation, parking_ratio=parking_ratio, score_threshold=score_threshold,
        )
    except Exception as exc:  # never crash the agent loop — report the failure
        return {"success": False, "data": {}, "error": f"masterplan failed: {exc}",
                "metadata": {"tool_name": "generate_masterplan", "source": "python"}}

    placed = _masterplan_placed_buildings(report)
    score = report.get("score", {}) or {}
    data = {
        "summary": report.get("summary"),
        "accepted": score.get("accepted"),
        "overall_score": score.get("overall"),
        "sub_scores": score.get("sub_scores"),
        "program_completeness": score.get("program_completeness"),
        "placed_count": len(placed),
        "unplaced": (report.get("placement", {}) or {}).get("unplaced", []),
        "edges": (report.get("edges", {}) or {}).get("summary"),
        "optimization": (report.get("optimization", {}) or {}).get("summary"),
        "parking_zone_count": len((report.get("parking", {}) or {}).get("zones", []) or []),
        "parking_zones": (report.get("parking", {}) or {}).get("zones", []) or [],
        "steps": report.get("steps", []),
        "reasoning": report.get("reasoning", []),
        "placed_buildings": placed,
    }
    return {"success": True, "data": data,
            "metadata": {"tool_name": "generate_masterplan", "source": "python",
                         "buildings_placed": len(placed)}}
