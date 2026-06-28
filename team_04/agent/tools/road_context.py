"""Road and transportation context (Phase 2 of BACKEND_PLAN.md).

The agent must know its surroundings — at minimum the biggest road near the site.
This module analyses road objects supplied with the site and tags each site side
with the nearest road, identifying the *main road* (highest hierarchy, then
widest, then most frontage) so downstream tools — the grid alignment and the
setback derivation — can anchor to the actual street instead of guessing.

Input road schema
-----------------
::

    {
        "type":       "road",
        "centerline": [[x, y], ...],   # or [[x, y, z], ...]
        "width_m":    float,
        "hierarchy":  "main" | "secondary" | "path",
        "name":       str   # optional
    }

When no road data is provided the function records an ambiguity — the caller
should surface it so the user or the brief system can fill the gap, rather than
the agent inventing a road.

Pure geometry (Shapely in / dict out), deterministic, no LLM or MCP.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString

from .view_analysis import _coerce_polygon_2d


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Hierarchy ordering — higher rank = more important road.
HIERARCHY_RANK: dict[str, int] = {"main": 3, "secondary": 2, "path": 1}

#: Default road width when the input omits ``width_m`` (metres).
DEFAULT_ROAD_WIDTH_M: float = 6.0

#: A road is "adjacent" to a site side when the centreline is closer than
#: its half-width plus this margin.  Keeps distant parallel roads from
#: accidentally tagging a side they don't front.
ADJACENCY_MARGIN_M: float = 20.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_road(road: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a raw road dict, returning a clean copy.

    Raises ``ValueError`` for fatally malformed input (missing centreline,
    fewer than 2 points).  Silently fixes unknown hierarchy to ``"secondary"``
    and non-positive width to ``DEFAULT_ROAD_WIDTH_M``.
    """
    if not isinstance(road, dict):
        raise ValueError(f"road must be a dict, got {type(road).__name__}")

    cl_raw = road.get("centerline")
    if not cl_raw or len(cl_raw) < 2:
        raise ValueError("road.centerline must have at least 2 points")

    hierarchy = road.get("hierarchy", "secondary")
    if hierarchy not in HIERARCHY_RANK:
        hierarchy = "secondary"

    width_m = road.get("width_m", DEFAULT_ROAD_WIDTH_M)
    try:
        width_m = float(width_m)
    except (TypeError, ValueError):
        width_m = DEFAULT_ROAD_WIDTH_M
    if width_m <= 0.0:
        width_m = DEFAULT_ROAD_WIDTH_M

    return {
        "type": "road",
        "centerline": [[float(p[0]), float(p[1])] for p in cl_raw],
        "width_m": width_m,
        "hierarchy": hierarchy,
        "name": road.get("name"),
    }


def analyze_roads(
    site_model: dict[str, Any],
    roads: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Analyse road objects relative to the site and tag site sides.

    For each road the function computes:
      - ``nearest_side_index`` — which site boundary edge is closest.
      - ``distance_m``         — shortest distance from centreline to that edge.
      - ``frontage_m``         — portion of the edge inside the road's width
                                 buffer (the "street frontage" length).

    The *main road* is the one with:
      1. Highest ``hierarchy`` (main > secondary > path).
      2. Among ties: greatest ``width_m``.
      3. Among remaining ties: greatest ``frontage_m``.

    ``edge_road_widths`` maps ``{side_index: width_m}`` for every side that has
    an adjacent road within ``ADJACENCY_MARGIN_M`` of the centreline — this dict
    is fed directly into ``site_setback.compute_buildable_zone``.

    ``updated_sides`` is a copy of ``site_model["sides"]`` with each side's
    ``adjacent_road`` slot filled from the nearest road (or ``None`` when no
    road is close enough to be considered adjacent).

    Parameters
    ----------
    site_model:
        Canonical SiteModel from ``build_site_model``.  Must contain
        ``boundary`` and ideally ``sides`` (list of edge dicts with
        ``adjacent_road`` slots).
    roads:
        List of raw road dicts.  Pass ``None`` or ``[]`` to receive an
        ambiguity record with ``available=False`` rather than an error.

    Returns
    -------
    dict with keys:
        ``available``            — True when at least one valid road was found.
        ``roads``                — per-road analysis dicts.
        ``main_road``            — the highest-priority road dict (or None).
        ``main_road_side_index`` — site side index that fronts the main road.
        ``edge_road_widths``     — {side_index: width_m} for the setback tool.
        ``updated_sides``        — site sides with ``adjacent_road`` tagged.
        ``ambiguity``            — ``"no_road_data"``, ``"no_valid_roads"``,
                                   ``"no_site_boundary"``, or ``None``.
        ``ambiguity_message``    — human-readable explanation (when ambiguous).
    """
    # --- Guard: no roads supplied -------------------------------------------
    if not roads:
        return _ambiguity_result(
            "no_road_data",
            "No road data provided. The grid defaults to the longest site side; "
            "parking has no road-frontage preference. "
            "Supply site_objects with type='road' to enable road-aware placement.",
            site_model,
        )

    # --- Guard: unusable site model -----------------------------------------
    boundary = site_model.get("boundary", [])
    if not boundary or len(boundary) < 3:
        return _ambiguity_result("no_site_boundary", "Site boundary is missing.", site_model)

    # --- Validate roads -------------------------------------------------------
    valid_roads: list[dict[str, Any]] = []
    for r in roads:
        try:
            valid_roads.append(validate_road(r))
        except (ValueError, TypeError, IndexError, KeyError):
            continue

    if not valid_roads:
        return _ambiguity_result(
            "no_valid_roads",
            "All supplied roads failed validation (missing centerline or < 2 points).",
            site_model,
        )

    # --- Build site-side segments -------------------------------------------
    sides = list(site_model.get("sides") or [])
    side_segments = _side_segments(boundary)

    # --- Per-road geometry --------------------------------------------------
    road_analyses: list[dict[str, Any]] = []
    for road in valid_roads:
        cl = LineString(road["centerline"])

        best_idx: int | None = None
        best_dist = math.inf
        best_frontage = 0.0

        for i, (p1, p2) in enumerate(side_segments):
            seg = LineString([p1, p2])
            d = float(cl.distance(seg))
            frontage = _frontage_projected(seg, cl)
            # Pick the nearest side; break ties by projected frontage so a road
            # running parallel to a side wins over one that merely ends near it.
            if d < best_dist - 1e-6 or (d < best_dist + 1e-6 and frontage > best_frontage):
                best_idx = i
                best_dist = d
                best_frontage = frontage

        road_analyses.append({
            **road,
            "nearest_side_index": best_idx,
            "distance_m": round(best_dist, 3),
            "frontage_m": round(best_frontage, 3),
            "_rank": (HIERARCHY_RANK.get(road["hierarchy"], 1), road["width_m"], best_frontage),
        })

    # --- Sort: highest hierarchy → widest → most frontage ------------------
    road_analyses.sort(key=lambda r: r["_rank"], reverse=True)
    main = road_analyses[0]

    # --- edge_road_widths: widest adjacent road per side -------------------
    edge_road_widths: dict[int, float] = {}
    for r in road_analyses:
        si = r["nearest_side_index"]
        if si is None:
            continue
        threshold = r["width_m"] / 2.0 + ADJACENCY_MARGIN_M
        if r["distance_m"] <= threshold:
            if si not in edge_road_widths or r["width_m"] > edge_road_widths[si]:
                edge_road_widths[si] = r["width_m"]

    # --- Tag site sides with their nearest adjacent road -------------------
    updated_sides: list[dict[str, Any]] = []
    for i, side in enumerate(sides):
        nearest_road = None
        nearest_d = math.inf
        for r in road_analyses:
            if r["nearest_side_index"] == i:
                threshold = r["width_m"] / 2.0 + ADJACENCY_MARGIN_M
                if r["distance_m"] < nearest_d and r["distance_m"] <= threshold:
                    nearest_d = r["distance_m"]
                    nearest_road = r
        if nearest_road is not None:
            adjacent = {
                "name": nearest_road.get("name"),
                "hierarchy": nearest_road["hierarchy"],
                "width_m": nearest_road["width_m"],
                "distance_m": nearest_road["distance_m"],
                "frontage_m": nearest_road["frontage_m"],
            }
        else:
            adjacent = None
        updated_sides.append({**side, "adjacent_road": adjacent})

    # --- Strip internal rank key before returning ---------------------------
    clean_roads = [{k: v for k, v in r.items() if k != "_rank"} for r in road_analyses]

    return {
        "available": True,
        "roads": clean_roads,
        "main_road": {k: v for k, v in main.items() if k != "_rank"},
        "main_road_side_index": main["nearest_side_index"],
        "edge_road_widths": edge_road_widths,
        "updated_sides": updated_sides,
        "ambiguity": None,
        "ambiguity_message": None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _side_segments(
    boundary: list[list[float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Return ``(p1, p2)`` tuples for each boundary edge in order."""
    pts = [(float(p[0]), float(p[1])) for p in boundary]
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def _frontage_projected(side_seg: LineString, road_cl: LineString) -> float:
    """Return the frontage as the overlap of road and side projected onto the side direction.

    Projects both the road centreline and the site side onto the *side's own
    direction vector*, then returns the length of their 1-D overlap. This is
    the natural planning notion of "how much of this side does the road serve"
    and is independent of whether the road happens to be within the road-width
    buffer of the side (which can be zero when the road runs just outside the
    buffer even though it is clearly the nearest parallel road).
    """
    sc = list(side_seg.coords)
    rc = list(road_cl.coords)
    if len(sc) < 2 or len(rc) < 2:
        return 0.0
    dx = sc[1][0] - sc[0][0]
    dy = sc[1][1] - sc[0][1]
    side_len = math.hypot(dx, dy)
    if side_len < 1e-9:
        return 0.0
    ux, uy = dx / side_len, dy / side_len
    s_projs = [p[0] * ux + p[1] * uy for p in sc]
    r_projs = [p[0] * ux + p[1] * uy for p in rc]
    overlap = max(0.0, min(max(r_projs), max(s_projs)) - max(min(r_projs), min(s_projs)))
    return overlap


def _ambiguity_result(
    code: str,
    message: str,
    site_model: dict[str, Any],
) -> dict[str, Any]:
    return {
        "available": False,
        "roads": [],
        "main_road": None,
        "main_road_side_index": None,
        "edge_road_widths": {},
        "updated_sides": list(site_model.get("sides") or []),
        "ambiguity": code,
        "ambiguity_message": message,
    }
