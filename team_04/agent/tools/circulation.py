"""Circulation, access, and fire safety (Phase 5 — BACKEND_PLAN.md).

Access placement should explain *why* a building sits where it sits: people and
vehicles enter from the street, drive along internal corridors **around** the
buildings (never through them) to each entrance and to parking, and fire
appliances must be able to reach every part of every building — including the
interior of a courtyard.

Real sites are not rectangles and real buildings are not solid blocks, so this
module is written for concave sites and concave / courtyard footprints:

    propose_site_entries(site_model)
        Public entry on the main-road side (one, or several spaced along a long
        frontage), optional private/service entry on a secondary side.

    route_internal_circulation(site_model, entries, buildings, parking)
        A drivable internal path network. Corridors are routed with an
        **obstacle-aware visibility graph** so they bend around other buildings
        and along the free space of a non-convex site instead of cutting through
        anything. Returned as polylines + buffered polygons.

    building_entrance_orientation(buildings, entries, circulation)
        **Multiple typed entrances per building** — a public/main entrance facing
        the nearest circulation, an optional service entrance facing the private
        site entry, a quiet residential entrance, and one courtyard entrance per
        detected courtyard. The legacy single-entrance fields are still returned
        (they mirror the public entrance) for backward compatibility.

    check_fire_access(buildings, circulation, ...)
        Per building: nearest-facade distance, **deepest-interior-point reach**,
        per-facade coverage ratio, and **courtyard reachability**. The hard
        constraint ``constraint_value = distance - max_distance`` (≤ 0 feasible)
        is unchanged so the optimizer contract is preserved; ``strict=True`` folds
        coverage + courtyard reach into the pass/fail.

Courtyards are detected two ways (see ``detect_courtyards``): explicit
``building["holes"]`` rings (true enclosed O-shape courts) and automatically from
concave footprints (U / H / C shapes) via convex-hull pockets.

Pure geometry (Shapely in / dict out), deterministic, no LLM or MCP.
"""
from __future__ import annotations

import heapq
import math
from typing import Any

from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
)
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

MAX_INTERIOR_REACH_M: float = 50.0
"""Strict-mode reach for the *deepest interior point* of a footprint (m). When
``strict``, a footprint whose core sits further than this from any drivable path
fails — this is what forces a courtyard / through-block access route on deep
plans rather than only checking the nearest wall."""

REACHABLE_RATIO_PASS: float = 0.0
"""Minimum fraction of a building's perimeter that must be within reach for the
soft perimeter check. The non-strict hard pass/fail is governed by distance
alone; this only enriches the report unless ``strict`` is set."""

STRICT_COVERAGE_RATIO: float = 0.5
"""In ``strict`` mode, at least this fraction of the facade must be within reach
of a drivable path for the building to pass."""

PERIMETER_PIECE_LENGTH_M: float = 2.0
"""Spacing of boundary test points used for the reachable-perimeter ratio (m)."""

INTERIOR_SAMPLE_STEP_M: float = 4.0
"""Grid spacing used to sample interior points for the deepest-point reach (m)."""

ROUTE_CLEARANCE_M: float = 1.0
"""Extra gap kept between a corridor edge and a building it merely passes (m).
Obstacle buildings are inflated by ``half_width + ROUTE_CLEARANCE_M`` so the
buffered corridor never overlaps a building it is only driving past."""

SECONDARY_HIERARCHY: tuple[str, ...] = ("secondary", "path")
"""Road hierarchies eligible to host a private / service entry."""

COURTYARD_MIN_AREA_RATIO: float = 0.06
"""A concave pocket counts as a courtyard only if its area is at least this
fraction of the building footprint area (filters out shallow notches)."""

COURTYARD_MIN_ENCLOSURE: float = 0.55
"""A concave pocket counts as a courtyard only if at least this fraction of its
perimeter is shared with the building (i.e. it is mostly enclosed by walls)."""

MAX_PUBLIC_ENTRIES: int = 4
"""Upper bound on public entries spaced along a long main-road frontage."""


# ---------------------------------------------------------------------------
# Public API — 1. Site entries
# ---------------------------------------------------------------------------

def propose_site_entries(
    site_model: dict[str, Any],
    *,
    frontage_per_public_entry_m: float | None = None,
) -> dict[str, Any]:
    """Propose access entry points on the site boundary.

    A **public** entry is placed on the main-road side (from Phase 2 road
    analysis); when no road is known the longest side is used and an ambiguity is
    reported. By default a single public entry sits at the side midpoint. When
    ``frontage_per_public_entry_m`` is given and the main-road side is long enough
    to warrant it, several public entries are spaced evenly along that side (capped
    at ``MAX_PUBLIC_ENTRIES``) — long urban frontages rarely have just one gate.

    An optional **private** / service entry is placed on a different side that
    carries a secondary/path road, if any.

    Args:
        site_model: Canonical SiteModel dict (``boundary``, ``sides``, ``roads``).
        frontage_per_public_entry_m: If set, target one public entry per this many
            metres of main-road frontage (opt-in; default keeps one entry).

    Returns:
        dict with ``entries`` (list), ``public_count``, ``private_count``,
        ``main_road_side_index``, ``ambiguity``, ``summary``.

        Each entry dict: ``entry_id``, ``point`` [x,y,0], ``type``
        ("public"|"private"), ``side_index``, ``inward_normal`` [nx,ny],
        ``road_name``.
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

    # ── Public entry/entries on the main-road side ───────────────────────────
    main_side = sides[main_road_side]
    fractions = _public_entry_fractions(
        _side_length(main_side), frontage_per_public_entry_m
    )
    road_name = _side_road_name(main_side)
    for k, frac in enumerate(fractions):
        pub_point, pub_normal = _point_and_inward_normal(main_side, site_poly, frac)
        entries.append({
            "entry_id": f"entry_public_{k}",
            "point": [round(pub_point[0], 4), round(pub_point[1], 4), 0.0],
            "type": "public",
            "side_index": int(main_road_side),
            "inward_normal": [round(pub_normal[0], 6), round(pub_normal[1], 6)],
            "road_name": road_name,
        })

    # ── Optional private / service entry on a secondary-road side ────────────
    private_side = _pick_private_side(sides, main_road_side)
    if private_side is not None:
        pv_point, pv_normal = _point_and_inward_normal(sides[private_side], site_poly, 0.5)
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

    parts = [f"{public_count} public entry/entries on side {main_road_side}"]
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
# Public API — 2. Internal circulation network (obstacle-aware)
# ---------------------------------------------------------------------------

def route_internal_circulation(
    site_model: dict[str, Any],
    entries: list[dict[str, Any]],
    buildings: list[dict[str, Any]],
    parking: dict[str, Any] | list[dict[str, Any]] | None = None,
    *,
    path_width_m: float = DEFAULT_PATH_WIDTH_M,
    entrances_by_building: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route a drivable internal path network from entries to targets.

    Starting from the public entry, the network grows as a tree: each target
    (building, then each parking zone) is connected from the nearest point on the
    network so far. Unlike a naive axis-aligned L, each corridor is routed with an
    **obstacle-aware visibility graph** — it must stay inside the (possibly
    concave) site and must bend around every *other* building, so corridors no
    longer cut through neighbouring footprints. When a building's entrance is
    known (``entrances_by_building``) the corridor aims at that facade.

    Args:
        site_model:   Canonical SiteModel dict (for the site polygon clip).
        entries:      Output of ``propose_site_entries`` (dict or its list).
        buildings:    Placed-building dicts, each with a ``boundary`` key.
        parking:      ``allocate_parking_zones`` result (``zones``) or a raw list.
        path_width_m: Corridor width (m).
        entrances_by_building: Optional ``{building_id: [x, y]}`` (or the result of
            ``building_entrance_orientation``) used to aim each corridor at the
            real public entrance rather than the nearest wall.

    Returns:
        dict with ``paths``, ``network_polyline``, ``occupied_polygons``,
        ``total_length_m``, ``path_width_m``, ``summary``.

        Each path dict: ``path_id``, ``polyline``, ``buffered_boundary``,
        ``width_m``, ``length_m``, ``serves``, ``target_type``,
        ``routed_around`` (count of buildings the route bent around).
    """
    entry_list = _coerce_entries(entries)
    boundary = site_model.get("boundary") or site_model.get("site_boundary") or []

    if not entry_list:
        return _empty_circulation(path_width_m, "no entries supplied")
    if not boundary or len(boundary) < 3:
        return _empty_circulation(path_width_m, "no valid site boundary")

    site_poly = _to_polygon(boundary)
    half_w = max(MIN_PATH_WIDTH_M, float(path_width_m)) / 2.0
    aim_map = _coerce_entrance_points(entrances_by_building)

    # Anchor the network at the public entry (fallback: first entry).
    anchor = next((e for e in entry_list if e.get("type") == "public"), entry_list[0])
    anchor_pt = Point(float(anchor["point"][0]), float(anchor["point"][1]))

    # ── Building footprints (targets *and* obstacles) ────────────────────────
    bld_polys: list[tuple[str, Polygon]] = []
    for bld in buildings or []:
        bnd = bld.get("boundary") or bld.get("building_boundary") or []
        if not bnd or len(bnd) < 3:
            continue
        bld_id = str(bld.get("building_id") or bld.get("geometry_id") or f"building_{len(bld_polys)}")
        bld_polys.append((bld_id, _to_polygon(bnd)))

    targets: list[dict[str, Any]] = []
    for bld_id, poly in bld_polys:
        targets.append({"geom": poly, "serves": bld_id, "target_type": "building"})
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
        from_geom, _ = nearest_points(network_geom, tgt["geom"])
        start = (from_geom.x, from_geom.y)

        # Aim point: the known public entrance, else the nearest network point.
        if tgt["target_type"] == "building" and tgt["serves"] in aim_map:
            ax, ay = aim_map[tgt["serves"]]
            aim = Point(float(ax), float(ay))
        else:
            aim = from_geom
        _, goal_geom = nearest_points(aim, tgt["geom"])
        goal = (goal_geom.x, goal_geom.y)

        # Obstacles = every *other* building, inflated so the corridor keeps clear.
        inflate = half_w + ROUTE_CLEARANCE_M
        obstacles = [
            poly.buffer(inflate, join_style=2)
            for bld_id, poly in bld_polys
            if bld_id != tgt["serves"]
        ]

        route = _shortest_route(start, goal, site_poly, obstacles)
        if route is None:
            route = _l_polyline(start, goal, site_poly)  # last-resort fallback
        routed_around = max(len(route) - 2, 0)

        line = LineString(route)
        if line.length < 1e-6:
            continue

        buffered = line.buffer(half_w, cap_style=2, join_style=2).intersection(site_poly)
        buffered = _largest_polygon(buffered)

        paths.append({
            "path_id": f"path_{len(paths)}",
            "polyline": [[round(x, 4), round(y, 4), 0.0] for x, y in route],
            "buffered_boundary": _poly_to_list(buffered) if buffered and not buffered.is_empty else [],
            "width_m": round(float(path_width_m), 2),
            "length_m": round(float(line.length), 2),
            "serves": tgt["serves"],
            "target_type": tgt["target_type"],
            "routed_around": routed_around,
        })
        centrelines.append(line)
        network_geom = unary_union([network_geom, line])

    total_length = round(sum(c.length for c in centrelines), 2)
    occupied = [p["buffered_boundary"] for p in paths if p["buffered_boundary"]]

    n_bld = sum(1 for p in paths if p["target_type"] == "building")
    n_park = sum(1 for p in paths if p["target_type"] == "parking")
    n_bent = sum(1 for p in paths if p["routed_around"] > 0)
    summary = (
        f"{len(paths)} corridor(s), {total_length} m total "
        f"({n_bld} to buildings, {n_park} to parking), {path_width_m} m wide; "
        f"{n_bent} routed around obstacles"
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
# Public API — 3. Building entrance orientation (multiple typed entrances)
# ---------------------------------------------------------------------------

def building_entrance_orientation(
    buildings: list[dict[str, Any]],
    entries: list[dict[str, Any]] | dict[str, Any],
    circulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve **typed entrances** for each building.

    Per building the result carries an ``entrances`` list with up to four roles:

    * ``public``      — main entrance, on the facade facing the nearest circulation
                        path (or, with no paths, the nearest public site entry).
    * ``service``     — on the facade facing the private/service site entry, when a
                        private entry exists and lands on a different facade.
    * ``residential`` — the quiet entrance: it faces a detected courtyard when the
                        building has one, otherwise the facade opposite the public
                        entrance.
    * ``courtyard``   — one per detected courtyard, on the inner facade, facing into
                        the void (where deck-access / private cores typically sit).

    The legacy single-entrance fields (``entrance_point``, ``entrance_direction``,
    ``private_direction``, ``faces``, ``distance_m``) are still returned and mirror
    the **public** entrance, so existing callers keep working.

    Args:
        buildings:   Placed-building dicts with ``boundary`` (and optional
                     ``holes`` for enclosed courtyards).
        entries:     ``propose_site_entries`` result or its ``entries`` list.
        circulation: ``route_internal_circulation`` result (optional).

    Returns:
        dict with ``buildings`` (per-building dicts, see above) and ``summary``.
    """
    entry_list = _coerce_entries(entries)
    public_entries = [e for e in entry_list if e.get("type") == "public"]
    private_entries = [e for e in entry_list if e.get("type") == "private"]
    fallback_entries = public_entries or entry_list

    centrelines: list[LineString] = []
    if circulation:
        for p in circulation.get("paths", []):
            pl = p.get("polyline") or []
            if len(pl) >= 2:
                centrelines.append(LineString([(pt[0], pt[1]) for pt in pl]))
    access_geom = unary_union(centrelines) if centrelines else None
    public_faces_kind = "circulation" if access_geom is not None else (
        "public_entry" if fallback_entries else "none"
    )
    public_entry_pts = [Point(e["point"][0], e["point"][1]) for e in fallback_entries]
    private_entry_pts = [Point(e["point"][0], e["point"][1]) for e in private_entries]

    results: list[dict[str, Any]] = []
    n_courts_total = 0
    for i, bld in enumerate(buildings or []):
        bnd = bld.get("boundary") or bld.get("building_boundary") or []
        bld_id = str(bld.get("building_id") or bld.get("geometry_id") or f"building_{i}")
        if not bnd or len(bnd) < 3:
            continue
        bld_poly = _to_polygon(bnd)
        holes = bld.get("holes") or bld.get("courtyards")
        courts = detect_courtyards(bld_poly, holes)
        n_courts_total += len(courts)

        entrances: list[dict[str, Any]] = []

        # ── Public / main entrance — faces nearest circulation or public entry ──
        public_ent = _entrance_facing(
            bld_poly, access_geom, public_entry_pts, public_faces_kind, role="public"
        )
        if public_ent:
            entrances.append(public_ent)

        # ── Service entrance — faces the private/service site entry ─────────────
        if private_entry_pts:
            service_ent = _entrance_facing(
                bld_poly, None, private_entry_pts, "private_entry", role="service"
            )
            # Only keep it if it lands on a meaningfully different facade.
            if service_ent and _entrance_is_distinct(service_ent, entrances):
                entrances.append(service_ent)

        # ── Residential / quiet entrance — courtyard-facing, else opposite ──────
        if courts:
            biggest = max(courts, key=lambda c: c["area_sqm"])
            res_ent = _entrance_toward_point(
                bld_poly, Point(biggest["centroid"][0], biggest["centroid"][1]),
                role="residential", faces="courtyard",
            )
        elif public_ent:
            res_ent = _entrance_opposite(bld_poly, public_ent, role="residential")
        else:
            res_ent = None
        if res_ent and _entrance_is_distinct(res_ent, entrances):
            entrances.append(res_ent)

        # ── Courtyard entrances — one per court, facing inward ──────────────────
        court_records: list[dict[str, Any]] = []
        for ci, court in enumerate(courts):
            cpt = Point(court["centroid"][0], court["centroid"][1])
            court_ent = _entrance_toward_point(
                bld_poly, cpt, role="courtyard", faces="courtyard",
            )
            if court_ent:
                court_ent["courtyard_index"] = ci
                if _entrance_is_distinct(court_ent, entrances):
                    entrances.append(court_ent)
            court_records.append({
                "courtyard_index": ci,
                "type": court["type"],
                "centroid": court["centroid"],
                "area_sqm": court["area_sqm"],
                "opening_point": court.get("opening_point"),
            })

        # Attach a short human reason to each entrance (why it sits where it does).
        for e in entrances:
            e["reason"] = _entrance_reason(e["role"], e["faces"])

        # Emergency exits from the footprint geometry — multiple independent
        # directions, never dumping into an enclosed courtyard. (Reported
        # alongside the access entrances so a caller can see the full door set.)
        egress = generate_emergency_exits(bld, circulation)

        # Legacy fields mirror the public entrance (or first available).
        legacy = public_ent or (entrances[0] if entrances else None)
        results.append({
            "building_id": bld_id,
            "entrances": entrances,
            "emergency_exits": egress["exits"],
            "egress_summary": {
                "n_exits": egress["n_exits"],
                "independent_directions": egress["independent_directions"],
                "multiple_directions": egress["multiple_directions"],
                "single_point_failure": egress["single_point_failure"],
                "courtyard_only_egress_risk": egress["courtyard_only_egress_risk"],
            },
            "courtyards": court_records,
            "n_entrances": len(entrances),
            # ---- backward-compatible single-entrance fields ----
            "entrance_point": legacy["point"] if legacy else None,
            "entrance_direction": legacy["direction"] if legacy else None,
            "private_direction": [round(-legacy["direction"][0], 6), round(-legacy["direction"][1], 6)]
                if legacy else None,
            "faces": legacy["faces"] if legacy else "none",
            "distance_m": legacy.get("distance_m") if legacy else None,
        })

    total_ent = sum(r["n_entrances"] for r in results)
    summary = (
        f"Resolved {total_ent} entrance(s) across {len(results)} building(s) "
        f"({n_courts_total} courtyard(s) detected)."
    )
    return {"buildings": results, "summary": summary}


# ---------------------------------------------------------------------------
# Public API — 4. Fire access constraint (interior- and courtyard-aware)
# ---------------------------------------------------------------------------

def check_fire_access(
    buildings: list[dict[str, Any]],
    circulation: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    max_distance: float = MAX_FIRE_DISTANCE_M,
    min_path_width: float = MIN_PATH_WIDTH_M,
    max_interior_reach: float = MAX_INTERIOR_REACH_M,
    strict: bool = False,
) -> dict[str, Any]:
    """Check that every building is reachable by a drivable fire-access path.

    Only paths at least ``min_path_width`` wide count. For each building we report:

    * ``distance_m``                  — nearest-facade distance to the network.
    * ``reachable_perimeter_ratio``   — fraction of the facade within reach.
    * ``deepest_point_distance_m``    — distance from the network to the *furthest
                                        interior point* of the footprint. This is
                                        what exposes a deep core or an enclosed
                                        courtyard that the nearest-wall test misses.
    * ``courtyards``                  — per-courtyard reachability flags.

    Pass/fail and the optimizer constraint are unchanged by default:

        ``constraint_value = distance_m − max_distance``   (≤ 0 ⇒ feasible)
        ``pass = within_reach and ratio ≥ REACHABLE_RATIO_PASS``

    With ``strict=True`` the pass additionally requires the facade coverage to
    reach ``STRICT_COVERAGE_RATIO``, the deepest interior point to be within
    ``max_interior_reach``, and every courtyard to be reachable — i.e. it enforces
    that fire crews can actually service the *whole* footprint, not just its
    nearest corner.

    Args:
        buildings:        Placed-building dicts (``boundary``, optional ``holes``).
        circulation:      ``route_internal_circulation`` result or list of paths.
        max_distance:     Max building-to-path distance (m).
        min_path_width:   Min path width that qualifies as access (m).
        max_interior_reach: Strict-mode deepest-interior-point reach (m).
        strict:           Fold coverage + interior + courtyard into pass/fail.

    Returns:
        dict with ``buildings`` (per-building), ``all_pass``,
        ``max_constraint_value``, ``n_pass``, ``n_fail``, ``max_distance_m``,
        ``min_path_width_m``, ``strict``, ``summary``.
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
        holes = bld.get("holes") or bld.get("courtyards")
        courts = detect_courtyards(bld_poly, holes)

        if network is None:
            distance = math.inf
            ratio = 0.0
            deepest = math.inf
            court_reports = [_court_report(c, None, max_distance) for c in courts]
        else:
            distance = float(bld_poly.distance(network))
            ratio = _reachable_perimeter_ratio(bnd, network, max_distance)
            deepest = _deepest_interior_distance(bld_poly, network)
            court_reports = [_court_report(c, network, max_distance) for c in courts]

        within = distance <= float(max_distance) + 1e-6
        courts_ok = all(c["reachable"] for c in court_reports)
        interior_ok = math.isfinite(deepest) and deepest <= float(max_interior_reach) + 1e-6
        coverage_ok = ratio >= STRICT_COVERAGE_RATIO

        passed = within and ratio >= REACHABLE_RATIO_PASS
        if strict:
            passed = passed and coverage_ok and interior_ok and courts_ok

        constraint = (distance - float(max_distance)) if math.isfinite(distance) else 1e9

        results.append({
            "building_id": bld_id,
            "distance_m": round(distance, 3) if math.isfinite(distance) else None,
            "reachable_perimeter_ratio": round(ratio, 3),
            "deepest_point_distance_m": round(deepest, 3) if math.isfinite(deepest) else None,
            "within_reach": bool(within),
            "interior_within_reach": bool(interior_ok),
            "courtyards": court_reports,
            "courtyards_reachable": bool(courts_ok),
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
        mode = "strict " if strict else ""
        summary = f"All {n_pass} building(s) pass {mode}fire access (<= {max_distance} m)."
    else:
        summary = (
            f"{n_fail} of {len(results)} building(s) FAIL fire access "
            f"(> {max_distance} m from a >= {min_path_width} m path"
            f"{', or interior/courtyard unreachable' if strict else ''})."
        )

    return {
        "buildings": results,
        "all_pass": bool(all_pass),
        "max_constraint_value": round(float(max_constraint), 3),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "max_distance_m": float(max_distance),
        "min_path_width_m": float(min_path_width),
        "strict": bool(strict),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Courtyard detection (public — used by orientation + fire checks)
# ---------------------------------------------------------------------------

def detect_courtyards(
    building: Polygon | list,
    holes: Any = None,
) -> list[dict[str, Any]]:
    """Detect courtyards in a building footprint.

    Two sources are combined:

    1. **Explicit holes** — ``holes`` (or a ``building["holes"]`` list upstream) is
       a list of interior rings ``[[x, y], ...]``; each becomes an *enclosed*
       courtyard (true O-shape court with no driveable mouth).
    2. **Concave pockets** — the difference between the footprint's convex hull and
       the footprint yields the open notches of U / H / C shapes. A pocket counts
       as an *open* courtyard when it is large enough
       (``COURTYARD_MIN_AREA_RATIO``) and mostly enclosed by walls
       (``COURTYARD_MIN_ENCLOSURE``); its ``opening_point`` marks the mouth a fire
       lane could drive through.

    Args:
        building: Footprint as a Shapely ``Polygon`` or a coordinate list.
        holes:    Optional list of interior rings (enclosed courtyards).

    Returns:
        List of courtyard dicts: ``type`` ("enclosed"|"open"), ``centroid``
        [x,y,0], ``area_sqm``, ``enclosure`` (0..1), ``opening_point`` [x,y,0] or
        ``None``.
    """
    poly = building if isinstance(building, Polygon) else _to_polygon(building)
    if poly.is_empty or poly.area <= 0:
        return []

    courts: list[dict[str, Any]] = []

    # 1) Explicit enclosed holes.
    for ring in holes or []:
        try:
            hpoly = _to_polygon(ring)
        except Exception:
            continue
        if hpoly.is_empty or hpoly.area <= 0:
            continue
        c = hpoly.centroid
        courts.append({
            "type": "enclosed",
            "centroid": [round(c.x, 4), round(c.y, 4), 0.0],
            "area_sqm": round(float(hpoly.area), 3),
            "enclosure": 1.0,
            "opening_point": None,
        })

    # 2) Concave pockets from the convex-hull difference.
    hull = poly.convex_hull
    pocket_geom = hull.difference(poly)
    for pocket in _iter_polygons(pocket_geom):
        if pocket.area < COURTYARD_MIN_AREA_RATIO * poly.area:
            continue
        shared = pocket.exterior.intersection(poly.exterior)
        shared_len = float(getattr(shared, "length", 0.0))
        peri = float(pocket.exterior.length) or 1.0
        enclosure = shared_len / peri
        if enclosure < COURTYARD_MIN_ENCLOSURE:
            continue
        c = pocket.centroid
        # The mouth = pocket boundary not shared with the building wall.
        mouth = pocket.exterior.difference(poly.exterior.buffer(1e-6))
        opening = None
        if not mouth.is_empty and getattr(mouth, "length", 0.0) > 1e-6:
            mp = mouth.interpolate(0.5, normalized=True)
            opening = [round(mp.x, 4), round(mp.y, 4), 0.0]
        courts.append({
            "type": "open",
            "centroid": [round(c.x, 4), round(c.y, 4), 0.0],
            "area_sqm": round(float(pocket.area), 3),
            "enclosure": round(enclosure, 3),
            "opening_point": opening,
        })

    return courts


# ---------------------------------------------------------------------------
# Internal helpers — geometry primitives
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


def _point_and_inward_normal(
    side: dict,
    site_poly: Polygon,
    fraction: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """A point at ``fraction`` along a side and the unit normal pointing inward."""
    s = side.get("start", [0, 0])
    e = side.get("end", [0, 0])
    sx, sy = float(s[0]), float(s[1])
    ex, ey = float(e[0]), float(e[1])
    f = min(max(float(fraction), 0.0), 1.0)
    pt = (sx + (ex - sx) * f, sy + (ey - sy) * f)

    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux  # left perpendicular
    cx, cy = site_poly.centroid.x, site_poly.centroid.y
    if (cx - pt[0]) * nx + (cy - pt[1]) * ny < 0:
        nx, ny = -nx, -ny  # flip to point inward
    return pt, (nx, ny)


def _public_entry_fractions(
    side_length: float,
    frontage_per_entry: float | None,
) -> list[float]:
    """Fractions along the main-road side at which to place public entries."""
    if not frontage_per_entry or frontage_per_entry <= 0 or side_length <= 0:
        return [0.5]
    n = int(side_length // float(frontage_per_entry))
    n = max(1, min(MAX_PUBLIC_ENTRIES, n))
    if n == 1:
        return [0.5]
    # Evenly spaced, inset from the corners (e.g. n=2 → 1/3, 2/3).
    return [(k + 1) / (n + 1) for k in range(n)]


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
    return max(candidates, key=lambda c: c[1])[0]


# ---------------------------------------------------------------------------
# Internal helpers — obstacle-aware routing (visibility graph + Dijkstra)
# ---------------------------------------------------------------------------

def _shortest_route(
    start: tuple[float, float],
    goal: tuple[float, float],
    site_poly: Polygon,
    obstacles: list[Polygon],
) -> list[tuple[float, float]] | None:
    """Shortest obstacle-free polyline from ``start`` to ``goal``.

    Builds a visibility graph whose nodes are ``start``, ``goal`` and the corners
    of every (already-inflated) obstacle, then runs Dijkstra. An edge is usable
    only when its segment stays inside ``site_poly`` and does not pass through the
    interior of any obstacle — so the route bends around buildings and follows the
    free space of a concave site. Returns ``None`` when no route exists (caller
    falls back to a clipped straight/L segment).
    """
    nodes: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()

    def add(pt: tuple[float, float]) -> None:
        key = (round(pt[0] * 1e6), round(pt[1] * 1e6))
        if key not in seen:
            seen.add(key)
            nodes.append((float(pt[0]), float(pt[1])))

    add(start)
    add(goal)
    for ob in obstacles:
        for v in _poly_vertices(ob):
            if site_poly.covers(Point(v)):
                add(v)

    n = len(nodes)
    if n < 2:
        return None

    # Pre-shrink obstacles a hair so segments grazing a corner aren't rejected.
    shrunk = [ob.buffer(-1e-6) for ob in obstacles]
    shrunk = [g for g in shrunk if not g.is_empty]

    def blocked(p: tuple[float, float], q: tuple[float, float]) -> bool:
        seg = LineString([p, q])
        if seg.length < 1e-9:
            return False
        if seg.difference(site_poly).length > 1e-6:  # leaves the site
            return True
        for g in shrunk:
            inter = g.intersection(seg)
            if getattr(inter, "length", 0.0) > 1e-6:
                return True
        return False

    INF = float("inf")
    dist = [INF] * n
    prev = [-1] * n
    visited = [False] * n
    dist[0] = 0.0
    pq: list[tuple[float, int]] = [(0.0, 0)]

    while pq:
        d, u = heapq.heappop(pq)
        if visited[u]:
            continue
        visited[u] = True
        if u == 1:  # reached goal
            break
        pu = nodes[u]
        for v in range(n):
            if v == u or visited[v]:
                continue
            pv = nodes[v]
            w = math.hypot(pu[0] - pv[0], pu[1] - pv[1])
            if d + w < dist[v] and not blocked(pu, pv):
                dist[v] = d + w
                prev[v] = u
                heapq.heappush(pq, (dist[v], v))

    if dist[1] == INF:
        return None

    route: list[tuple[float, float]] = []
    cur = 1
    while cur != -1:
        route.append(nodes[cur])
        cur = prev[cur]
    route.reverse()
    return route


def _poly_vertices(poly: Polygon) -> list[tuple[float, float]]:
    if poly.is_empty:
        return []
    return [(float(x), float(y)) for x, y in list(poly.exterior.coords)[:-1]]


def _l_polyline(
    a: tuple[float, float],
    b: tuple[float, float],
    site_poly: Polygon,
) -> list[tuple[float, float]]:
    """Straight or L-shaped polyline from a to b, keeping the corner inside the site.

    Fallback used only when the visibility router finds no route.
    """
    ax, ay = a
    bx, by = b
    if math.hypot(bx - ax, by - ay) < 1e-9:
        return [(ax, ay), (bx, by)]
    if abs(ax - bx) < 1e-6 or abs(ay - by) < 1e-6:
        return [(ax, ay), (bx, by)]

    c1 = (bx, ay)
    c2 = (ax, by)
    c1_inside = site_poly.contains(Point(c1))
    c2_inside = site_poly.contains(Point(c2))

    if c1_inside and not c2_inside:
        corner = c1
    elif c2_inside and not c1_inside:
        corner = c2
    elif c1_inside and c2_inside:
        corner = c1 if _l_inside_length(a, c1, b, site_poly) >= _l_inside_length(a, c2, b, site_poly) else c2
    else:
        return [(ax, ay), (bx, by)]
    return [(ax, ay), corner, (bx, by)]


def _l_inside_length(
    a: tuple[float, float],
    corner: tuple[float, float],
    b: tuple[float, float],
    site_poly: Polygon,
) -> float:
    line = LineString([a, corner, b])
    inside = line.intersection(site_poly)
    return float(getattr(inside, "length", 0.0))


# ---------------------------------------------------------------------------
# Internal helpers — entrance resolution
# ---------------------------------------------------------------------------

def _entrance_facing(
    bld_poly: Polygon,
    access_geom: Any,
    entry_pts: list[Point],
    faces_kind: str,
    *,
    role: str,
) -> dict[str, Any] | None:
    """Entrance on the facade nearest a circulation network or a set of entries."""
    if access_geom is not None:
        near_on_bld, near_on_access = nearest_points(bld_poly.exterior, access_geom)
        target = near_on_access
    elif entry_pts:
        target = min(entry_pts, key=lambda ep: bld_poly.distance(ep))
        near_on_bld, _ = nearest_points(bld_poly.exterior, target)
    else:
        return None
    return _entrance_dict(bld_poly, near_on_bld, target, role=role, faces=faces_kind)


def _entrance_toward_point(
    bld_poly: Polygon,
    target: Point,
    *,
    role: str,
    faces: str,
) -> dict[str, Any] | None:
    """Entrance on the facade nearest a specific target point (e.g. a courtyard)."""
    near_on_bld, _ = nearest_points(bld_poly.exterior, target)
    return _entrance_dict(bld_poly, near_on_bld, target, role=role, faces=faces)


def _entrance_opposite(
    bld_poly: Polygon,
    public_ent: dict[str, Any],
    *,
    role: str,
) -> dict[str, Any] | None:
    """Quiet entrance on the facade opposite a given (public) entrance."""
    c = bld_poly.centroid
    pdx, pdy = public_ent["direction"]
    # Aim well outside the footprint in the opposite direction, then project back.
    span = max(bld_poly.bounds[2] - bld_poly.bounds[0], bld_poly.bounds[3] - bld_poly.bounds[1]) or 1.0
    aim = Point(c.x - pdx * span * 2.0, c.y - pdy * span * 2.0)
    near_on_bld, _ = nearest_points(bld_poly.exterior, aim)
    return _entrance_dict(bld_poly, near_on_bld, aim, role=role, faces="quiet_side")


def _entrance_dict(
    bld_poly: Polygon,
    near_on_bld: Point,
    target: Point,
    *,
    role: str,
    faces: str,
) -> dict[str, Any]:
    ex, ey = near_on_bld.x, near_on_bld.y
    dx, dy = target.x - ex, target.y - ey
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        c = bld_poly.centroid
        dx, dy = ex - c.x, ey - c.y
        d0 = math.hypot(dx, dy) or 1.0
        ndir = (dx / d0, dy / d0)
    else:
        ndir = (dx / dist, dy / dist)
    return {
        "role": role,
        "point": [round(ex, 4), round(ey, 4), 0.0],
        "direction": [round(ndir[0], 6), round(ndir[1], 6)],
        "faces": faces,
        "distance_m": round(float(dist), 3),
    }


def _entrance_is_distinct(
    candidate: dict[str, Any],
    existing: list[dict[str, Any]],
    *,
    min_separation_m: float = 3.0,
) -> bool:
    """True when the candidate entrance is far enough from all existing ones."""
    cx, cy = candidate["point"][0], candidate["point"][1]
    for e in existing:
        if math.hypot(cx - e["point"][0], cy - e["point"][1]) < min_separation_m:
            return False
    return True


# ---------------------------------------------------------------------------
# Internal helpers — fire metrics
# ---------------------------------------------------------------------------

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


def _deepest_interior_distance(poly: Polygon, network: Any) -> float:
    """Largest network distance over a grid of interior sample points (m).

    Approximates "how far is the deepest part of this footprint from a drivable
    path" — the metric that exposes a deep core or an enclosed courtyard that the
    nearest-wall distance hides.
    """
    if network is None or poly.is_empty:
        return math.inf
    minx, miny, maxx, maxy = poly.bounds
    step = INTERIOR_SAMPLE_STEP_M
    worst = 0.0
    found = False
    y = miny
    while y <= maxy + 1e-9:
        x = minx
        while x <= maxx + 1e-9:
            p = Point(x, y)
            if poly.contains(p):
                found = True
                d = network.distance(p)
                if d > worst:
                    worst = d
            x += step
        y += step
    if not found:
        # Degenerate/thin footprint — fall back to the representative point.
        return float(network.distance(poly.representative_point()))
    return worst


def _court_report(court: dict[str, Any], network: Any, max_distance: float) -> dict[str, Any]:
    """Reachability of a single courtyard from the drivable network."""
    cpt = Point(court["centroid"][0], court["centroid"][1])
    if network is None:
        reachable = False
        d = None
    else:
        d = float(network.distance(cpt))
        reachable = d <= float(max_distance) + 1e-6
    return {
        "type": court["type"],
        "centroid": court["centroid"],
        "area_sqm": court["area_sqm"],
        "distance_m": round(d, 3) if d is not None else None,
        "reachable": bool(reachable),
    }


# ---------------------------------------------------------------------------
# Internal helpers — geometry utilities & coercion
# ---------------------------------------------------------------------------

def _iter_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]


def _largest_polygon(geom: Any) -> Polygon | None:
    polys = _iter_polygons(geom)
    if not polys:
        return None
    return max(polys, key=lambda g: g.area)


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


def _coerce_entrance_points(entrances: Any) -> dict[str, list[float]]:
    """Accept a ``building_entrance_orientation`` result or a plain id→point map."""
    out: dict[str, list[float]] = {}
    if not entrances:
        return out
    if isinstance(entrances, dict) and "buildings" in entrances:
        for b in entrances.get("buildings") or []:
            bid = b.get("building_id")
            # Prefer the public entrance; fall back to the legacy single point.
            pt = None
            for e in b.get("entrances") or []:
                if e.get("role") == "public":
                    pt = e.get("point")
                    break
            if pt is None:
                pt = b.get("entrance_point")
            if bid is not None and pt:
                out[str(bid)] = [float(pt[0]), float(pt[1])]
        return out
    if isinstance(entrances, dict):
        for bid, pt in entrances.items():
            if pt and len(pt) >= 2:
                out[str(bid)] = [float(pt[0]), float(pt[1])]
    return out


def _empty_circulation(path_width_m: float, reason: str) -> dict[str, Any]:
    return {
        "paths": [],
        "network_polyline": [],
        "occupied_polygons": [],
        "total_length_m": 0.0,
        "path_width_m": round(float(path_width_m), 2),
        "summary": f"Circulation routing skipped: {reason}",
    }


# ===========================================================================
# Functional access reasoning layer (Phase 5+ rebuild)
#
# The functions above place geometry; the functions below reason about how
# people *use* it — how they arrive, which door they pick, how cars reach
# parking and people walk from it, and how everyone gets out in a fire. They
# are additive: nothing above changed signature or contract.
# ===========================================================================

# ---- additional constants -------------------------------------------------

PEDESTRIAN_PATH_WIDTH_M: float = 2.5
"""Width of a walkable pedestrian route (m)."""

COMFORT_WALK_M: float = 120.0
"""Comfortable parking-to-entrance walking distance (m). Beyond this the link
is flagged as too far."""

ACCESSIBLE_WALK_M: float = 60.0
"""Maximum barrier-free travel distance for accessible parking to an entrance
(m) — accessible bays should sit within this of a public entrance."""

FIRE_APPLIANCE_TURNING_RADIUS_M: float = 12.0
"""Outer turning radius a fire appliance needs at a dead end / hammerhead (m)."""

MIN_EMERGENCY_EXITS: int = 2
"""Minimum independent emergency exits every building must offer."""

EXIT_INDEPENDENCE_MIN_DEG: float = 60.0
"""Two exits count as *independent* escape directions only when their outward
normals differ by at least this angle (degrees)."""

FACADE_MERGE_ANGLE_DEG: float = 15.0
"""Consecutive edges whose directions differ by less than this are merged into
one facade (so a slightly faceted wall reads as a single face)."""

FACADE_PROBE_M: float = 3.0
"""Distance a facade's outward normal is probed to tell open space from a
concave courtyard pocket (m)."""


# ---- small shared helpers -------------------------------------------------

def _boundary_of(obj: Any) -> list:
    if isinstance(obj, dict):
        return obj.get("boundary") or obj.get("building_boundary") or obj.get("site_boundary") or []
    return obj or []


def _building_id_of(b: Any, idx: int = 0) -> str:
    if isinstance(b, dict):
        return str(b.get("building_id") or b.get("geometry_id") or f"building_{idx}")
    return f"building_{idx}"


def _solid_polygon(building: Any) -> Polygon | None:
    """Footprint as a Shapely polygon **with its holes** preserved."""
    if isinstance(building, Polygon):
        return building if building.is_valid else building.buffer(0)
    shell = [(float(p[0]), float(p[1])) for p in _boundary_of(building) if len(p) >= 2]
    if len(shell) < 3:
        return None
    rings: list[list[tuple[float, float]]] = []
    if isinstance(building, dict):
        for ring in building.get("holes") or []:
            r = [(float(p[0]), float(p[1])) for p in ring if len(p) >= 2]
            if len(r) >= 3:
                rings.append(r)
    poly = Polygon(shell, rings)
    return poly if poly.is_valid else poly.buffer(0)


def _unit(dx: float, dy: float) -> tuple[float, float]:
    L = math.hypot(dx, dy) or 1.0
    return dx / L, dy / L


def _angle_deg(nx: float, ny: float) -> float:
    return math.degrees(math.atan2(ny, nx))


def _ang_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _count_independent_dirs(angles: list[float], sep: float) -> int:
    reps: list[float] = []
    for a in angles:
        if all(_ang_diff(a, r) >= sep for r in reps):
            reps.append(a)
    return len(reps)


def _network_from_circulation(circulation: Any) -> Any:
    lines: list[LineString] = []
    for p in _coerce_paths(circulation):
        pl = p.get("polyline") or []
        if len(pl) >= 2:
            lines.append(LineString([(pt[0], pt[1]) for pt in pl]))
    return unary_union(lines) if lines else None


def _public_entrance_index(orientation: Any) -> dict[str, tuple[float, float]]:
    """``{building_id: (x, y)}`` for each building's public entrance."""
    out: dict[str, tuple[float, float]] = {}
    if not orientation:
        return out
    for b in orientation.get("buildings") or []:
        bid = b.get("building_id")
        pt = None
        for e in b.get("entrances") or []:
            if e.get("role") == "public":
                pt = e.get("point")
                break
        if pt is None:
            pt = b.get("entrance_point")
        if bid is not None and pt:
            out[str(bid)] = (float(pt[0]), float(pt[1]))
    return out


def _entrance_reason(role: str, faces: str) -> str:
    if role == "public":
        if faces == "circulation":
            return ("Main entrance on the facade facing the internal circulation / main "
                    "arrival route — direct and visible from where people arrive.")
        if faces == "public_entry":
            return "Main entrance on the facade closest to the public site entry on the main road."
        return "Main entrance on the most publicly visible facade toward the street."
    if role == "service":
        return ("Service / loading entrance on a quieter facade facing the secondary "
                "site entry, keeping public traffic away from servicing.")
    if role == "residential":
        if faces == "courtyard":
            return "Quiet residential entrance opening onto the building's courtyard."
        return "Quiet residential entrance on the calm facade opposite the public door."
    if role == "courtyard":
        return "Courtyard entrance on the inner facade serving the enclosed / open court."
    return ""


# ---------------------------------------------------------------------------
# Facade segmentation — the typology-aware primitive
# ---------------------------------------------------------------------------

def segment_facades(
    building: Any,
    *,
    merge_angle_deg: float = FACADE_MERGE_ANGLE_DEG,
) -> list[dict[str, Any]]:
    """Break a footprint into facades, each tagged by what it faces.

    Works for any footprint — a plain box, a winged U / H / X / Y / E, or a
    courtyard / O building — so entrance and egress logic never needs the wing
    graph. Each facade dict carries:

    * ``facade_id``, ``start``, ``end``, ``midpoint`` [x,y,0], ``length_m``
    * ``direction`` [ux,uy]      — unit vector along the facade
    * ``outward_normal`` [nx,ny] — unit normal pointing away from the solid
    * ``faces``                  — ``"open"`` (true exterior), ``"courtyard"``
                                   (a concave pocket of a U/H/E shape) or
                                   ``"enclosed_courtyard"`` (an interior hole ring)
    * ``is_exterior``            — on the outer ring *and* facing open space

    Args:
        building: Footprint as a Shapely ``Polygon`` or a building dict
                  (``boundary`` and optional ``holes``).
        merge_angle_deg: Edges closer than this in direction merge into one face.

    Returns:
        List of facade dicts (outer-ring faces first, then any hole faces).
    """
    poly = _solid_polygon(building)
    if poly is None or poly.is_empty:
        return []
    shell_hull = Polygon(poly.exterior).convex_hull

    facades: list[dict[str, Any]] = []
    facades += _ring_to_facades(list(poly.exterior.coords), poly, shell_hull, "exterior", merge_angle_deg)
    for interior in poly.interiors:
        facades += _ring_to_facades(list(interior.coords), poly, shell_hull, "hole", merge_angle_deg)
    for i, f in enumerate(facades):
        f["facade_id"] = f"facade_{i}"
    return facades


def _ring_to_facades(
    ring: list,
    solid: Polygon,
    shell_hull: Polygon,
    kind: str,
    merge_angle_deg: float,
) -> list[dict[str, Any]]:
    pts = [(float(x), float(y)) for x, y in ring[:-1]] if len(ring) > 1 else []
    n = len(pts)
    if n < 2:
        return []

    # Edge directions, then group consecutive near-collinear edges.
    edge_dirs = [_angle_deg(*_unit(pts[(i + 1) % n][0] - pts[i][0],
                                   pts[(i + 1) % n][1] - pts[i][1])) for i in range(n)]
    groups: list[list[int]] = [[0]]
    for i in range(1, n):
        if _ang_diff(edge_dirs[i], edge_dirs[i - 1]) <= merge_angle_deg:
            groups[-1].append(i)
        else:
            groups.append([i])

    facades: list[dict[str, Any]] = []
    for grp in groups:
        s = pts[grp[0]]
        e = pts[(grp[-1] + 1) % n]
        length = math.hypot(e[0] - s[0], e[1] - s[1])
        if length < 1e-6:
            continue
        mx, my = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0
        ux, uy = _unit(e[0] - s[0], e[1] - s[1])

        # Outward normal = the perpendicular whose probe leaves the solid.
        n1 = (uy, -ux)
        probe_in = Point(mx + n1[0] * 0.05, my + n1[1] * 0.05)
        nx, ny = n1 if not solid.contains(probe_in) else (-uy, ux)

        if kind == "hole":
            faces = "enclosed_courtyard"
        else:
            probe = Point(mx + nx * FACADE_PROBE_M, my + ny * FACADE_PROBE_M)
            faces = "courtyard" if (shell_hull.contains(probe) and not solid.contains(probe)) else "open"

        facades.append({
            "start": [round(s[0], 4), round(s[1], 4), 0.0],
            "end": [round(e[0], 4), round(e[1], 4), 0.0],
            "midpoint": [round(mx, 4), round(my, 4), 0.0],
            "length_m": round(length, 3),
            "direction": [round(ux, 6), round(uy, 6)],
            "outward_normal": [round(nx, 6), round(ny, 6)],
            "faces": faces,
            "is_exterior": kind == "exterior" and faces == "open",
        })
    return facades


# ---------------------------------------------------------------------------
# Emergency exits — geometry-driven, multi-direction, courtyard-avoiding
# ---------------------------------------------------------------------------

def generate_emergency_exits(
    building: Any,
    circulation: Any = None,
    *,
    min_exits: int = MIN_EMERGENCY_EXITS,
    independence_deg: float = EXIT_INDEPENDENCE_MIN_DEG,
    max_distance: float = MAX_FIRE_DISTANCE_M,
) -> dict[str, Any]:
    """Generate emergency exits for one building from its geometry.

    Exits are placed on **open exterior facades** (never into an enclosed or
    open courtyard, which would trap occupants), spread to maximise independent
    escape directions, and — for winged shapes — spread across the footprint so
    each wing has its own way out. A single-point-failure flag fires when there
    are fewer than two genuinely independent directions.

    Args:
        building:     Footprint dict or Shapely polygon.
        circulation:  Optional drivable network (to report exit→road distance).
        min_exits:    Minimum exits required (default 2).
        independence_deg: Min angle between two outward normals to count as
                      independent escape directions.
        max_distance: Reach used to flag whether an exit makes it to a road.

    Returns:
        dict with ``building_id``, ``exits`` (list), ``n_exits``,
        ``independent_directions``, ``multiple_directions``,
        ``single_point_failure``, ``courtyard_only_egress_risk``,
        ``wing_coverage``, ``summary``.
    """
    bld_id = _building_id_of(building)
    facades = segment_facades(building)
    open_f = [f for f in facades if f["faces"] == "open"]
    court_f = [f for f in facades if f["faces"] != "open"]
    network = _network_from_circulation(circulation)

    ranked = sorted(open_f, key=lambda f: -f["length_m"])
    chosen: list[dict[str, Any]] = []
    for f in ranked:
        a = _angle_deg(*f["outward_normal"])
        if all(_ang_diff(a, _angle_deg(*c["outward_normal"])) >= independence_deg for c in chosen):
            chosen.append(f)
    # Top up to min_exits with the next-longest open facades if independence was strict.
    if len(chosen) < min_exits:
        for f in ranked:
            if f not in chosen:
                chosen.append(f)
            if len(chosen) >= min_exits:
                break

    exits: list[dict[str, Any]] = []
    for k, f in enumerate(chosen):
        mid = f["midpoint"]
        d = float(network.distance(Point(mid[0], mid[1]))) if network is not None else None
        exits.append({
            "exit_id": f"{bld_id}_exit_{k}",
            "point": mid,
            "direction": f["outward_normal"],
            "faces": f["faces"],
            "facade_id": f.get("facade_id"),
            "leads_to_open": True,
            "distance_to_access_m": round(d, 3) if d is not None else None,
            "reaches_road": bool(d is not None and d <= float(max_distance) + 1e-6),
        })

    angles = [_angle_deg(*e["direction"]) for e in exits]
    independent = _count_independent_dirs(angles, independence_deg)
    courtyard_only_risk = (len(open_f) == 0 and len(court_f) > 0)
    single_point = len(exits) < min_exits or independent < 2
    wing_cov = _wing_exit_coverage(building, exits)

    notes = []
    if single_point:
        notes.append("single-point-failure risk: fewer than 2 independent escape directions")
    if courtyard_only_risk:
        notes.append("no open exterior facade — exits would discharge into a courtyard")
    if not wing_cov["covered"]:
        notes.append("exits not well spread across the footprint (possible wing without an exit)")
    summary = (f"{bld_id}: {len(exits)} exit(s), {independent} independent direction(s)"
               + (" — " + "; ".join(notes) if notes else " — OK"))

    return {
        "building_id": bld_id,
        "exits": exits,
        "n_exits": len(exits),
        "independent_directions": independent,
        "multiple_directions": independent >= 2,
        "single_point_failure": bool(single_point),
        "courtyard_only_egress_risk": bool(courtyard_only_risk),
        "wing_coverage": wing_cov,
        "summary": summary,
    }


def _wing_exit_coverage(building: Any, exits: list[dict[str, Any]]) -> dict[str, Any]:
    """Heuristic: are exits spread far enough apart to cover separate wings?"""
    poly = _solid_polygon(building)
    if poly is None or poly.is_empty or len(exits) < 2:
        return {"covered": False, "detail": "fewer than 2 exits"}
    minx, miny, maxx, maxy = poly.bounds
    diag = math.hypot(maxx - minx, maxy - miny) or 1.0
    pts = [Point(e["point"][0], e["point"][1]) for e in exits]
    max_sep = max(p.distance(q) for p in pts for q in pts)
    return {
        "covered": bool(max_sep >= 0.45 * diag),
        "max_exit_separation_m": round(max_sep, 2),
        "footprint_diagonal_m": round(diag, 2),
    }


# ---------------------------------------------------------------------------
# Site arrival — pedestrian vs vehicular, per frontage
# ---------------------------------------------------------------------------

_PEDESTRIAN_HIERARCHIES = ("path", "footpath", "pedestrian")
_VEHICULAR_HIERARCHIES = ("main", "primary", "secondary")


def analyze_site_arrival(
    site_model: dict[str, Any],
    entries: Any,
    orientation: Any = None,
) -> dict[str, Any]:
    """Reason about how users arrive from the street and which door they pick.

    For every road frontage it states whether pedestrians and/or vehicles
    arrive there; for every site entry it gives the user's mode and the
    street → site → building sequence ending at the nearest public entrance.

    Args:
        site_model:  Canonical SiteModel (``sides`` carry ``adjacent_road``).
        entries:     ``propose_site_entries`` result or its list.
        orientation: ``building_entrance_orientation`` result (for door targets).

    Returns:
        dict with ``frontages``, ``arrivals``, ``summary``.
    """
    entry_list = _coerce_entries(entries)
    sides = site_model.get("sides") or []
    ent_pts = _public_entrance_index(orientation)

    def hierarchy_of(side_index: int) -> str | None:
        if 0 <= side_index < len(sides):
            ar = sides[side_index].get("adjacent_road")
            if isinstance(ar, dict):
                return ar.get("hierarchy")
        return None

    frontages: list[dict[str, Any]] = []
    for s in sides:
        ar = s.get("adjacent_road")
        if not isinstance(ar, dict):
            continue
        h = ar.get("hierarchy")
        ped = h in _PEDESTRIAN_HIERARCHIES or h in ("main", "primary", "secondary")
        veh = h in _VEHICULAR_HIERARCHIES
        si = int(s.get("side_index", -1))
        frontages.append({
            "side_index": si,
            "road_name": ar.get("name"),
            "hierarchy": h,
            "pedestrian_arrival": bool(ped),
            "vehicular_arrival": bool(veh),
            "entry_ids": [e["entry_id"] for e in entry_list if e.get("side_index") == si],
            "note": ("vehicles + pedestrians" if veh and ped else
                     "pedestrians only" if ped else "vehicles only" if veh else "—"),
        })

    arrivals: list[dict[str, Any]] = []
    for e in entry_list:
        h = hierarchy_of(int(e.get("side_index", -1)))
        if h in _PEDESTRIAN_HIERARCHIES:
            mode = "pedestrian"
        elif e.get("type") == "public":
            mode = "both"
        else:
            mode = "vehicular"
        target = None
        if ent_pts:
            ex, ey = e["point"][0], e["point"][1]
            target = min(ent_pts, key=lambda b: math.hypot(ent_pts[b][0] - ex, ent_pts[b][1] - ey))
        road = e.get("road_name") or "street"
        seq = f"{road} → {e['type']} site entry → internal route → " + (
            f"{target} public entrance" if target else "building entrance")
        arrivals.append({
            "entry_id": e["entry_id"],
            "type": e.get("type"),
            "mode": mode,
            "point": e["point"],
            "serves_building": target,
            "sequence": seq,
        })

    n_ped = sum(1 for a in arrivals if a["mode"] in ("pedestrian", "both"))
    n_veh = sum(1 for a in arrivals if a["mode"] in ("vehicular", "both"))
    summary = (f"{len(frontages)} road frontage(s); "
               f"{n_ped} pedestrian and {n_veh} vehicular arrival point(s).")
    return {"frontages": frontages, "arrivals": arrivals, "summary": summary}


# ---------------------------------------------------------------------------
# Pedestrian network — routes that avoid walking through parking
# ---------------------------------------------------------------------------

def route_pedestrian_network(
    site_model: dict[str, Any],
    entries: Any,
    buildings: list[dict[str, Any]],
    parking: Any = None,
    orientation: Any = None,
    *,
    path_width_m: float = PEDESTRIAN_PATH_WIDTH_M,
) -> dict[str, Any]:
    """Route a pedestrian network: site entry → entrances, parking → entrances.

    Pedestrian routes are obstacle-aware (visibility graph) like the vehicular
    network, but additionally treat **parking zones as obstacles** so people are
    not routed across a parking lot when a footway around it exists.

    Returns a dict shaped like ``route_internal_circulation`` with every path
    tagged ``mode="pedestrian"`` and a ``hierarchy`` of ``"primary"`` (a public
    arrival walk) or ``"secondary"`` (a walk up from parking).
    """
    boundary = _boundary_of(site_model)
    if not boundary or len(boundary) < 3:
        return {"paths": [], "network_polyline": [], "total_length_m": 0.0,
                "path_width_m": path_width_m, "mode": "pedestrian",
                "summary": "Pedestrian routing skipped: no site boundary"}
    site_poly = _to_polygon(boundary)
    half = max(0.5, float(path_width_m)) / 2.0
    entry_list = _coerce_entries(entries)
    pub_pts = [Point(e["point"][0], e["point"][1]) for e in entry_list if e.get("type") == "public"]
    if not pub_pts and entry_list:
        pub_pts = [Point(entry_list[0]["point"][0], entry_list[0]["point"][1])]
    ent_pts = _public_entrance_index(orientation)

    bld_polys: list[tuple[str, Polygon]] = []
    for i, b in enumerate(buildings or []):
        bnd = _boundary_of(b)
        if bnd and len(bnd) >= 3:
            bld_polys.append((_building_id_of(b, i), _to_polygon(bnd)))
    park_polys: list[tuple[str, Polygon]] = []
    for z in _coerce_zones(parking):
        zb = z.get("boundary") or []
        if zb and len(zb) >= 3:
            park_polys.append((str(z.get("zone_id") or f"parking_{len(park_polys)}"), _to_polygon(zb)))

    paths: list[dict[str, Any]] = []
    network: Any = unary_union(pub_pts) if pub_pts else None

    def _emit(start, goal, serves, source, hierarchy, obstacles):
        nonlocal network
        route = _shortest_route(start, goal, site_poly, obstacles) or _l_polyline(start, goal, site_poly)
        line = LineString(route)
        if line.length < 1e-6:
            return
        paths.append({
            "path_id": f"ped_{len(paths)}",
            "polyline": [[round(x, 4), round(y, 4), 0.0] for x, y in route],
            "width_m": round(float(path_width_m), 2),
            "length_m": round(float(line.length), 2),
            "serves": serves,
            "source": source,
            "target_type": "building_entrance",
            "mode": "pedestrian",
            "hierarchy": hierarchy,
            "routed_around": max(len(route) - 2, 0),
        })
        network = unary_union([network, line]) if network is not None else line

    # 1) Public arrival walks: nearest pedestrian node → each public entrance.
    for bid, poly in bld_polys:
        goal = ent_pts.get(bid)
        goal_pt = Point(goal) if goal else nearest_points(poly.exterior, network or pub_pts[0])[1]
        goal_xy = (goal_pt.x, goal_pt.y)
        src = network if network is not None else (pub_pts[0] if pub_pts else goal_pt)
        start_geom, _ = nearest_points(src, goal_pt)
        obstacles = ([p.buffer(half + ROUTE_CLEARANCE_M, join_style=2) for oid, p in bld_polys if oid != bid]
                     + [p.buffer(half, join_style=2) for _, p in park_polys])
        _emit((start_geom.x, start_geom.y), goal_xy, bid, "site_entry", "primary", obstacles)

    # 2) Parking egress walks: each zone → its nearest public entrance.
    for zid, zpoly in park_polys:
        if not ent_pts:
            break
        bid = min(ent_pts, key=lambda b: zpoly.distance(Point(ent_pts[b])))
        goal_pt = Point(ent_pts[bid])
        start_geom, _ = nearest_points(zpoly.exterior, goal_pt)
        obstacles = ([p.buffer(half + ROUTE_CLEARANCE_M, join_style=2) for oid, p in bld_polys if oid != bid]
                     + [p.buffer(half, join_style=2) for oid, p in park_polys if oid != zid])
        _emit((start_geom.x, start_geom.y), (goal_pt.x, goal_pt.y), bid, zid, "secondary", obstacles)

    total = round(sum(p["length_m"] for p in paths), 2)
    n_pri = sum(1 for p in paths if p["hierarchy"] == "primary")
    n_sec = sum(1 for p in paths if p["hierarchy"] == "secondary")
    return {
        "paths": paths,
        "network_polyline": [p["polyline"] for p in paths],
        "total_length_m": total,
        "path_width_m": round(float(path_width_m), 2),
        "mode": "pedestrian",
        "summary": (f"{len(paths)} pedestrian route(s), {total} m "
                    f"({n_pri} arrival walk(s), {n_sec} parking walk(s)); parking treated as obstacle."),
    }


# ---------------------------------------------------------------------------
# Parking integration analysis
# ---------------------------------------------------------------------------

def analyze_parking_access(
    buildings: list[dict[str, Any]],
    parking: Any,
    orientation: Any,
    pedestrian: Any = None,
    *,
    comfort_m: float = COMFORT_WALK_M,
    accessible_m: float = ACCESSIBLE_WALK_M,
) -> dict[str, Any]:
    """Evaluate parking as part of the journey, not an isolated object.

    For each parking zone: nearest public entrance and its walking distance, a
    drop-off point on the zone edge closest to that entrance, whether the walk
    is within comfortable / accessible range, and the full
    street → site → parking → entrance sequence.

    Returns dict with ``zones`` (per-zone rows), ``all_within_comfort``,
    ``summary``.
    """
    ent_pts = _public_entrance_index(orientation)
    ped_net = _network_from_circulation(pedestrian) if pedestrian else None

    rows: list[dict[str, Any]] = []
    for z in _coerce_zones(parking):
        zb = z.get("boundary") or []
        if not zb or len(zb) < 3:
            continue
        zid = str(z.get("zone_id") or f"parking_{len(rows)}")
        zpoly = _to_polygon(zb)
        if not ent_pts:
            rows.append({"zone_id": zid, "nearest_entrance_building": None,
                         "straight_distance_m": None, "note": "no building entrances resolved"})
            continue
        bid = min(ent_pts, key=lambda b: zpoly.distance(Point(ent_pts[b])))
        ent_pt = Point(ent_pts[bid])
        straight = float(zpoly.distance(ent_pt))
        drop_geom, _ = nearest_points(zpoly.exterior, ent_pt)
        walk = None
        if ped_net is not None:
            # distance along the pedestrian network's nearest node (approx walk)
            walk = round(float(ped_net.distance(drop_geom)) + straight, 2)
        rows.append({
            "zone_id": zid,
            "nearest_entrance_building": bid,
            "straight_distance_m": round(straight, 2),
            "approx_walk_distance_m": walk,
            "drop_off_point": [round(drop_geom.x, 3), round(drop_geom.y, 3), 0.0],
            "within_comfort_walk": bool(straight <= comfort_m),
            "accessible_parking_ok": bool(straight <= accessible_m),
            "is_main_road_side": bool(z.get("is_main_road_side")),
            "sequence": f"street → site entry → {zid} → walk ~{round(straight)} m → {bid} public entrance",
        })

    all_comfort = all(r.get("within_comfort_walk") for r in rows) if rows else True
    n_acc = sum(1 for r in rows if r.get("accessible_parking_ok"))
    summary = (f"{len(rows)} parking zone(s); {n_acc} within accessible walk ({accessible_m} m); "
               + ("all within comfortable walk." if all_comfort else "some beyond comfortable walk."))
    return {"zones": rows, "all_within_comfort": bool(all_comfort), "summary": summary}


# ---------------------------------------------------------------------------
# Emergency egress + fire-appliance access (per building)
# ---------------------------------------------------------------------------

def analyze_egress(
    buildings: list[dict[str, Any]],
    circulation: Any = None,
    *,
    max_distance: float = MAX_FIRE_DISTANCE_M,
) -> dict[str, Any]:
    """Combine emergency egress and fire-appliance access into one report.

    Per building: emergency exits (multi-direction, courtyard-avoiding, wing
    coverage) plus the fire-appliance reach metrics from ``check_fire_access``
    (nearest wall, deepest interior, courtyard reachability). A building is
    ``compliant`` only when it has ≥2 independent exits, no single-point
    failure, no courtyard-only egress, and a fire appliance can reach it.

    Returns dict with ``buildings`` (rows), ``all_compliant``,
    ``turning_radius_m``, ``min_clear_width_m``, ``summary``.
    """
    fire = check_fire_access(buildings, circulation, strict=True, max_distance=max_distance)
    fire_by = {b["building_id"]: b for b in fire["buildings"]}

    rows: list[dict[str, Any]] = []
    for i, b in enumerate(buildings or []):
        bid = _building_id_of(b, i)
        ee = generate_emergency_exits(b, circulation, max_distance=max_distance)
        fb = fire_by.get(bid, {})
        appliance = {
            "distance_m": fb.get("distance_m"),
            "within_reach": fb.get("within_reach"),
            "interior_within_reach": fb.get("interior_within_reach"),
            "deepest_point_distance_m": fb.get("deepest_point_distance_m"),
            "courtyards_reachable": fb.get("courtyards_reachable"),
        }
        compliant = bool(
            ee["n_exits"] >= MIN_EMERGENCY_EXITS
            and not ee["single_point_failure"]
            and not ee["courtyard_only_egress_risk"]
            and fb.get("within_reach")
        )
        rows.append({
            "building_id": bid,
            "exits": ee["exits"],
            "n_exits": ee["n_exits"],
            "independent_directions": ee["independent_directions"],
            "multiple_directions": ee["multiple_directions"],
            "single_point_failure": ee["single_point_failure"],
            "courtyard_only_egress_risk": ee["courtyard_only_egress_risk"],
            "wing_coverage": ee["wing_coverage"],
            "fire_appliance_access": appliance,
            "compliant": compliant,
            "notes": ee["summary"],
        })

    all_ok = all(r["compliant"] for r in rows) if rows else False
    n_ok = sum(1 for r in rows if r["compliant"])
    summary = (f"{n_ok}/{len(rows)} building(s) egress-compliant "
               f"(≥{MIN_EMERGENCY_EXITS} independent exits + fire-appliance reach).")
    return {
        "buildings": rows,
        "all_compliant": bool(all_ok),
        "turning_radius_m": FIRE_APPLIANCE_TURNING_RADIUS_M,
        "min_clear_width_m": MIN_PATH_WIDTH_M,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Conflict detection (pedestrian × vehicle, parking × fire access)
# ---------------------------------------------------------------------------

def detect_circulation_conflicts(
    vehicular: Any,
    pedestrian: Any,
    parking: Any = None,
    fire: Any = None,
) -> dict[str, Any]:
    """Find pedestrian/vehicle conflicts and blocked fire access.

    * **ped × vehicle crossings** — where a pedestrian route crosses a drivable
      corridor (needs a marked / raised crossing).
    * **ped through parking** — a pedestrian route clipping a parking polygon.
    * **fire access fail** — any building the appliance network can't reach.

    Returns dict with ``conflicts`` (each ``type``, ``location``,
    ``resolution``) and ``summary``.
    """
    conflicts: list[dict[str, Any]] = []
    veh_net = _network_from_circulation(vehicular)

    ped_lines: list[tuple[str, LineString]] = []
    for p in _coerce_paths(pedestrian):
        pl = p.get("polyline") or []
        if len(pl) >= 2:
            ped_lines.append((p.get("path_id", "ped"), LineString([(pt[0], pt[1]) for pt in pl])))

    if veh_net is not None:
        seen_xy: list[tuple[float, float]] = []
        for pid, line in ped_lines:
            inter = line.intersection(veh_net)
            for pt in _iter_points(inter):
                # Dedupe crossings that land within ~2 m of one already recorded.
                if any(math.hypot(pt.x - sx, pt.y - sy) < 2.0 for sx, sy in seen_xy):
                    continue
                seen_xy.append((pt.x, pt.y))
                conflicts.append({
                    "type": "pedestrian_vehicle_crossing",
                    "path_id": pid,
                    "location": [round(pt.x, 3), round(pt.y, 3), 0.0],
                    "resolution": "provide a marked / raised pedestrian crossing with sightlines here",
                })

    park_by_id = {str(z.get("zone_id") or f"parking_{i}"): _to_polygon(z["boundary"])
                  for i, z in enumerate(_coerce_zones(parking))
                  if z.get("boundary") and len(z["boundary"]) >= 3}
    ped_source = {p.get("path_id"): p.get("source") for p in _coerce_paths(pedestrian)}
    for pid, line in ped_lines:
        src = ped_source.get(pid)
        for zid, zp in park_by_id.items():
            if zid == src:
                continue  # a walk *from* this zone necessarily starts at its edge
            if line.intersection(zp).length > 0.5:
                conflicts.append({
                    "type": "pedestrian_through_parking",
                    "path_id": pid,
                    "location": [round(line.centroid.x, 3), round(line.centroid.y, 3), 0.0],
                    "resolution": "route the footway around the parking edge or add a protected walkway",
                })
                break

    if isinstance(fire, dict):
        for b in fire.get("buildings", []):
            if not b.get("within_reach"):
                conflicts.append({
                    "type": "fire_access_unreachable",
                    "building_id": b.get("building_id"),
                    "location": None,
                    "resolution": "add a fire lane / hammerhead within 50 m of this building",
                })

    counts: dict[str, int] = {}
    for c in conflicts:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    summary = (f"{len(conflicts)} conflict(s): "
               + ", ".join(f"{k}×{v}" for k, v in counts.items())) if conflicts else "No conflicts detected."
    return {"conflicts": conflicts, "counts": counts, "summary": summary}


def _iter_points(geom: Any) -> list[Point]:
    if geom is None or getattr(geom, "is_empty", True):
        return []
    if isinstance(geom, Point):
        return [geom]
    pts: list[Point] = []
    for g in getattr(geom, "geoms", []):
        if isinstance(g, Point):
            pts.append(g)
        elif hasattr(g, "representative_point"):
            pts.append(g.representative_point())
    return pts


# ---------------------------------------------------------------------------
# Circulation audit (the validation checklist)
# ---------------------------------------------------------------------------

def audit_circulation(
    entries: Any,
    orientation: Any,
    vehicular: Any,
    pedestrian: Any,
    parking_access: Any,
    egress: Any,
    fire: Any,
    conflicts: Any,
) -> dict[str, Any]:
    """Run the pre-finalisation circulation audit.

    Verifies the user's checklist: every building has a public entrance and is
    connected to the network, parking is connected to pedestrian routes, every
    building has compliant egress and fire access, nothing is isolated, and
    pedestrian/vehicle conflicts are bounded.

    Returns dict with ``checks`` (each ``check``/``pass``/``detail``),
    ``all_pass``, ``n_pass``, ``n_fail``, ``summary``.
    """
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    blds = (orientation or {}).get("buildings") or []
    network = unary_union([g for g in (_network_from_circulation(vehicular),
                                       _network_from_circulation(pedestrian)) if g is not None]) \
        if (vehicular or pedestrian) else None

    # 1) public entrance per building
    have_pub = [b for b in blds if any(e.get("role") == "public" for e in b.get("entrances", []))]
    add("every_building_has_public_entrance", len(have_pub) == len(blds) and blds,
        f"{len(have_pub)}/{len(blds)} buildings have a public entrance")

    # 2) every entrance connected to the network
    isolated = []
    if network is not None:
        for b in blds:
            for e in b.get("entrances", []):
                p = Point(e["point"][0], e["point"][1])
                if network.distance(p) > MAX_FIRE_DISTANCE_M:
                    isolated.append((b["building_id"], e["role"]))
    add("entrances_connected_to_network", network is not None and not isolated,
        "all entrances within reach of a route" if not isolated else f"isolated: {isolated}")
    add("no_isolated_entrances", not isolated, f"{len(isolated)} isolated entrance(s)")

    # 3) parking connected to pedestrian routes
    pk = (parking_access or {}).get("zones") or []
    pk_ok = all(z.get("nearest_entrance_building") for z in pk)
    add("parking_connected_to_pedestrian_routes", pk_ok if pk else True,
        f"{sum(1 for z in pk if z.get('nearest_entrance_building'))}/{len(pk)} zones linked to an entrance")

    # 4) compliant egress per building
    eg = (egress or {}).get("buildings") or []
    add("every_building_has_compliant_egress", (egress or {}).get("all_compliant", False) and eg,
        f"{sum(1 for r in eg if r.get('compliant'))}/{len(eg)} buildings egress-compliant")

    # 5) fire vehicle access — can an appliance *reach* every building edge?
    #    (loose reachability; whole-footprint servicing is the egress check's job.)
    fb = (fire or {}).get("buildings") or []
    veh_reach = bool(fb) and all(b.get("within_reach") for b in fb)
    add("fire_vehicle_access_available", veh_reach,
        f"{sum(1 for b in fb if b.get('within_reach'))}/{len(fb)} buildings reachable by a fire appliance")

    # 6) no path without a destination (construction guarantees a target)
    veh_paths = _coerce_paths(vehicular)
    ped_paths = _coerce_paths(pedestrian)
    dangling = [p.get("path_id") for p in veh_paths + ped_paths if not p.get("serves")]
    add("no_path_without_destination", not dangling, f"{len(dangling)} dangling path(s)")

    # 7) pedestrian/vehicle conflicts minimised
    n_conf = len((conflicts or {}).get("conflicts", []))
    crossings = (conflicts or {}).get("counts", {}).get("pedestrian_vehicle_crossing", 0)
    add("pedestrian_vehicle_conflicts_minimised", crossings <= max(1, len(blds)),
        f"{crossings} ped/vehicle crossing(s), {n_conf} conflict(s) total")

    n_pass = sum(1 for c in checks if c["pass"])
    n_fail = len(checks) - n_pass
    all_pass = n_fail == 0
    summary = (f"Audit: {n_pass}/{len(checks)} checks pass"
               + ("" if all_pass else f" — {n_fail} need attention"))
    return {"checks": checks, "all_pass": bool(all_pass), "n_pass": n_pass,
            "n_fail": n_fail, "summary": summary}


# ---------------------------------------------------------------------------
# Orchestrator — the full functional-access evaluation for one layout
# ---------------------------------------------------------------------------

def evaluate_site_circulation(
    site_model: dict[str, Any],
    buildings: list[dict[str, Any]],
    parking: Any = None,
    *,
    frontage_per_public_entry_m: float | None = None,
    path_width_m: float = DEFAULT_PATH_WIDTH_M,
) -> dict[str, Any]:
    """End-to-end functional access evaluation for a placed layout.

    Runs the whole pipeline and returns one report with the sections a reviewer
    asks for: entrance reasoning, site-access strategy, the pedestrian and
    vehicular networks, parking integration, fire-safety / egress, the
    identified conflicts (with resolutions), and the validation audit.

    This is the single call the agent / a notebook makes; the individual
    functions remain available for finer-grained use.

    Args:
        site_model: Canonical SiteModel (``boundary``/``sides``/``roads``).
        buildings:  Placed-building dicts (``boundary``, optional ``holes``).
        parking:    ``allocate_parking_zones`` result or a raw zone list.
        frontage_per_public_entry_m: Opt-in multiple public gates on long frontages.
        path_width_m: Vehicular corridor width (m).

    Returns:
        dict with ``entrances``, ``site_access``, ``vehicular_circulation``,
        ``pedestrian_circulation``, ``movement_hierarchy``,
        ``parking_integration``, ``fire_safety_egress``, ``conflicts``,
        ``audit``, ``summary``.
    """
    entries = propose_site_entries(site_model, frontage_per_public_entry_m=frontage_per_public_entry_m)

    # First pass entrances (no circulation yet) so routing can aim at real doors.
    orient0 = building_entrance_orientation(buildings, entries, None)
    vehicular = route_internal_circulation(
        site_model, entries, buildings, parking,
        path_width_m=path_width_m, entrances_by_building=orient0,
    )
    # Final entrances now that corridors exist (public doors face the network).
    orientation = building_entrance_orientation(buildings, entries, vehicular)

    pedestrian = route_pedestrian_network(site_model, entries, buildings, parking, orientation)

    # Movement hierarchy: stamp vehicular paths and bucket every route.
    for p in vehicular.get("paths", []):
        p["mode"] = "vehicular"
        p["hierarchy"] = "primary"
    movement_hierarchy = {
        "primary": {
            "vehicular": [p["path_id"] for p in vehicular.get("paths", [])],
            "pedestrian": [p["path_id"] for p in pedestrian.get("paths", []) if p["hierarchy"] == "primary"],
        },
        "secondary": {
            "pedestrian_from_parking": [p["path_id"] for p in pedestrian.get("paths", [])
                                        if p["hierarchy"] == "secondary"],
            "service_courtyard": "served via the typed service/courtyard entrances",
        },
        "tertiary": {"note": "maintenance / landscape paths not generated in this pass"},
    }

    arrival = analyze_site_arrival(site_model, entries, orientation)
    parking_access = analyze_parking_access(buildings, parking, orientation, pedestrian)
    fire = check_fire_access(buildings, vehicular, strict=True)
    egress = analyze_egress(buildings, vehicular)
    conflicts = detect_circulation_conflicts(vehicular, pedestrian, parking, fire)
    audit = audit_circulation(entries, orientation, vehicular, pedestrian,
                              parking_access, egress, fire, conflicts)

    summary = (
        f"{len(buildings or [])} building(s): "
        f"{entries['summary']} | {vehicular['summary']} | {pedestrian['summary']} | "
        f"{egress['summary']} | {conflicts['summary']} | {audit['summary']}"
    )
    return {
        "entrances": orientation,
        "site_access": arrival,
        "vehicular_circulation": vehicular,
        "pedestrian_circulation": pedestrian,
        "movement_hierarchy": movement_hierarchy,
        "parking_integration": parking_access,
        "fire_safety_egress": {"fire_access": fire, "egress": egress},
        "conflicts": conflicts,
        "audit": audit,
        "summary": summary,
    }
