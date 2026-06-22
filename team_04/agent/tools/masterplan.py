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
"""Weights for the five sub-scores (sum to 1)."""


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
# Orchestrator — the full circulation-first pipeline (steps 1-10)
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
    """Generate a masterplan circulation-first and score it.

    Runs steps 1–10 in order: reserve margins → access structure → spine →
    place buildings → entrances → drop-offs → parking → pedestrian network →
    fire validation → score. Returns one report with every artifact and a
    per-element ``reasoning`` log, plus the accept/reject ``score``.

    Args:
        site_model:      Canonical SiteModel (``boundary``/``sides``/``roads``).
        program:         Buildings to place: ``{building_id, label, type, area,
                         storeys, depth?, ratio?}`` (``type`` ∈ I/L/T/U/H/X/Y/O).
        default_setback: Fallback edge setback (m).
        spine_width:     Vehicular spine width (m).
        separation:      Minimum building-to-building gap (m).
        parking_ratio:   Stalls per apartment for demand.
        score_threshold: Reject layouts scoring below this.

    Returns:
        dict with ``margins``, ``access``, ``spine``, ``placement``, ``buildings``,
        ``entrances``, ``dropoffs``, ``parking``, ``vehicular_circulation``,
        ``pedestrian_circulation``, ``site_access``, ``parking_integration``,
        ``fire_safety_egress``, ``conflicts``, ``audit``, ``score``, ``reasoning``,
        ``summary``.
    """
    reasoning: list[str] = []

    # 1 — margins
    margins = reserve_site_margins(site_model, default_setback=default_setback)
    buildable = margins["buildable_polygon"]
    reasoning.append(f"[1] {margins['reason']}")

    # 2 — access structure
    access = plan_access_structure(site_model)
    entries = access["entries"]
    reasoning.append(f"[2] {access['summary']}")

    # 3 — spine
    spine = generate_movement_spine(buildable, entries, spine_width=spine_width)
    reasoning.append(f"[3] {spine['reason']}")

    # 4 — place buildings on the spine
    placement = place_buildings_along_spine(buildable, spine, program, separation=separation)
    buildings = placement["buildings"]
    for b in buildings:
        reasoning.append(f"[4] {b['building_id']}: {b['placement_reason']}")
    if placement["unplaced"]:
        reasoning.append(f"[4] unplaced (no valid slot): {', '.join(placement['unplaced'])}")

    site_poly = _to_polygon(site_model.get("boundary") or [])

    # 7 — parking (computed now so vehicular routing can serve it)
    demand = compute_building_demand(buildings, parking_ratio=parking_ratio) if buildings else []
    parking = allocate_parking_zones(site_model, buildings, demand) if buildings else {"zones": []}

    # 5 — entrances (prelim → final once the network exists)
    orient0 = building_entrance_orientation(buildings, entries, None)
    vehicular = route_internal_circulation(
        site_model, entries, buildings, parking, path_width_m=spine_width,
        entrances_by_building=orient0,
    )
    _overlay_framework(vehicular, spine, site_poly)
    orientation = building_entrance_orientation(buildings, entries, vehicular)
    reasoning.append(f"[5] entrances: {orientation['summary']}")

    # 6 — drop-offs from entrances
    dropoffs = generate_dropoffs(orientation, vehicular)
    for d in dropoffs["dropoffs"]:
        reasoning.append(f"[6] {d['drop_id']}: {d['reason']}")
    reasoning.append(f"[7] parking: {parking.get('summary', 'n/a')}")

    # 8 — pedestrian network
    pedestrian = route_pedestrian_network(site_model, entries, buildings, parking, orientation)
    reasoning.append(f"[8] pedestrian: {pedestrian['summary']}")

    # 9 — fire validation
    fire = check_fire_access(buildings, vehicular, strict=True)
    egress = analyze_egress(buildings, vehicular)
    reasoning.append(f"[9] fire: {fire['summary']} | {egress['summary']}")

    arrival = analyze_site_arrival(site_model, entries, orientation)
    parking_access = analyze_parking_access(buildings, parking, orientation, pedestrian)
    conflicts = detect_circulation_conflicts(vehicular, pedestrian, parking, fire)
    audit = audit_circulation(entries, orientation, vehicular, pedestrian,
                              parking_access, egress, fire, conflicts)

    # 10 — score
    score = score_masterplan(buildable, buildings, spine, vehicular, pedestrian,
                             parking_access, orientation, fire, egress, conflicts,
                             threshold=score_threshold)
    reasoning.append(f"[10] {score['summary']} sub-scores={score['sub_scores']}")

    return {
        "margins": margins,
        "access": access,
        "spine": spine,
        "placement": placement,
        "buildings": buildings,
        "entrances": orientation,
        "dropoffs": dropoffs,
        "parking": parking,
        "vehicular_circulation": vehicular,
        "pedestrian_circulation": pedestrian,
        "site_access": arrival,
        "parking_integration": parking_access,
        "fire_safety_egress": {"fire_access": fire, "egress": egress},
        "conflicts": conflicts,
        "audit": audit,
        "score": score,
        "reasoning": reasoning,
        "summary": (f"{placement['summary']} | {score['summary']} | "
                    f"{audit['summary']} | {conflicts['summary']}"),
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
