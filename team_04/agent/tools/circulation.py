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

        # Legacy fields mirror the public entrance (or first available).
        legacy = public_ent or (entrances[0] if entrances else None)
        results.append({
            "building_id": bld_id,
            "entrances": entrances,
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
