"""Context enrichment — turn the stored Urban Context into the ctx data the
objective scorers need, so objectives (noise / view / road access / privacy)
actually RESPOND to where a candidate sits instead of flat-lining to a default.

The Urban Context stage already captures real OSM data per edge:
  edge = {direction, a:[x,y], b:[x,y], mid:[x,y], nearest:{Feature: distance_m},
          edge_context:[{label, distance, reason}]}

We derive, from those edges (no new data fetched, no fabrication):
  * roads          — polylines for edges fronting a road (noise + access scorers)
  * noise_sources  — point sources at noisy edges (primary road / highway / rail)
  * view_attractors— points at amenity edges (park / water / landmark)

If the context has none of a given feature, that key stays empty and the
dependent objective is reported UNAVAILABLE downstream (never scored from a
default) — honouring the context-availability rule.
"""
from __future__ import annotations

from typing import Any

# Feature-name fragments → category. Matched case-insensitively against the edge's
# nearest-feature labels.
_ROAD_WORDS = ("road", "street", "highway", "avenue", "drive", "lane", "motorway")
_NOISE_WORDS = ("highway", "motorway", "primary road", "railway", "rail", "industrial", "freeway")
_VIEW_WORDS = ("park", "water", "river", "lake", "garden", "green", "landmark", "plaza", "waterfront", "sea", "coast")
# Features that make a BAD view (penalise) — for the View scorer's detractors.
_VIEW_DETRACTOR_WORDS = ("highway", "motorway", "freeway", "industrial", "factory",
                         "warehouse", "parking", "service", "railway", "substation",
                         "landfill", "treatment")
# Road-class → relative noise emission (0..1). Real OSM classification: motorway/
# trunk/primary are far louder than residential/local. Used for road-class-weighted
# noise so a primary road scores worse than a quiet lane at the same distance.
_ROAD_CLASS_NOISE = {
    "motorway": 1.0, "freeway": 1.0, "trunk": 0.95, "highway": 0.95,
    "primary": 0.85, "primary road": 0.85, "railway": 0.9, "rail": 0.9,
    "secondary": 0.6, "tertiary": 0.45,
    "residential": 0.3, "local": 0.3, "street": 0.35, "service": 0.25,
    "industrial": 0.7,
}


def _road_noise_level(label: str) -> float:
    """Relative noise emission for a road/feature label, by OSM class."""
    low = label.lower()
    best = 0.0
    for word, lvl in _ROAD_CLASS_NOISE.items():
        if word in low:
            best = max(best, lvl)
    return best or 0.5


def _edge_points(edge: dict[str, Any]) -> list[list[float]] | None:
    a, b = edge.get("a"), edge.get("b")
    if a and b and len(a) >= 2 and len(b) >= 2:
        return [[float(a[0]), float(a[1])], [float(b[0]), float(b[1])]]
    mid = edge.get("mid")
    if mid and len(mid) >= 2:
        return [[float(mid[0]), float(mid[1])]]
    return None


def _nearest_items(edge: dict[str, Any]) -> list[tuple[str, float]]:
    """[(label, distance_m)] from an edge's nearest map + edge_context list."""
    items: list[tuple[str, float]] = []
    for label, dist in (edge.get("nearest") or {}).items():
        try:
            items.append((str(label), float(dist)))
        except (TypeError, ValueError):
            continue
    for ec in edge.get("edge_context") or []:
        if isinstance(ec, dict) and ec.get("label") is not None:
            try:
                items.append((str(ec["label"]), float(ec.get("distance", 9999))))
            except (TypeError, ValueError):
                continue
    return items


def _matches(label: str, words: tuple[str, ...]) -> bool:
    low = label.lower()
    return any(w in low for w in words)


def enrich_ctx(base_ctx: dict[str, Any], urban_context: dict[str, Any] | None) -> dict[str, Any]:
    """Return base_ctx augmented with roads / noise_sources / view_attractors derived
    from the urban context edges. Non-destructive: only fills keys that are empty."""
    ctx = dict(base_ctx)
    uc = urban_context or {}
    edges = uc.get("edges") or []
    if not edges:
        return ctx

    roads: list[dict[str, Any]] = list(ctx.get("roads") or [])
    noise_sources: list[dict[str, Any]] = list(ctx.get("noise_sources") or [])
    view_attractors: list[dict[str, Any]] = list(ctx.get("view_attractors") or [])
    view_detractors: list[dict[str, Any]] = list(ctx.get("view_detractors") or [])

    for edge in edges:
        pts = _edge_points(edge)
        if not pts:
            continue
        mid = edge.get("mid") or pts[0]
        mx, my = float(mid[0]), float(mid[1])
        items = _nearest_items(edge)

        for label, dist in items:
            if _matches(label, _ROAD_WORDS):
                # The edge itself is the road front — use its polyline for distance calcs.
                roads.append({"path": pts, "label": label, "distance": dist,
                              "noise_class": round(_road_noise_level(label), 2)})
            if _matches(label, _NOISE_WORDS):
                # Real noise = road-class emission × proximity falloff. A primary road
                # (class ~0.85) is far louder than a local lane (~0.3) at the same range.
                emission = _road_noise_level(label)
                proximity = max(0.2, min(1.0, 1.0 - dist / 200.0)) if dist else 0.85
                level = round(emission * proximity, 2)
                noise_sources.append({"x": mx, "y": my, "level": level, "label": label,
                                      "road_class": round(emission, 2), "distance": dist})
            if _matches(label, _VIEW_WORDS) and not _matches(label, _VIEW_DETRACTOR_WORDS):
                weight = max(0.3, min(1.0, 1.0 - dist / 400.0)) if dist else 0.7
                view_attractors.append({"x": mx, "y": my, "weight": round(weight, 2),
                                        "type": "amenity", "label": label,
                                        "geometry": [[mx, my, 0.0]]})
            if _matches(label, _VIEW_DETRACTOR_WORDS):
                # Negative view: highways / industrial / service yards penalise the view.
                weight = max(0.3, min(1.0, 1.0 - dist / 300.0)) if dist else 0.6
                view_detractors.append({"x": mx, "y": my, "weight": round(weight, 2),
                                        "type": "detractor", "label": label})

    # De-duplicate noise/view points that landed on the same edge midpoint.
    def _dedup_pts(seq):
        seen, out = set(), []
        for s in seq:
            k = (round(s.get("x", 0), 1), round(s.get("y", 0), 1), s.get("label"))
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
        return out

    if roads:
        ctx["roads"] = roads
    if noise_sources:
        ctx["noise_sources"] = _dedup_pts(noise_sources)
    if view_attractors:
        ctx["view_attractors"] = _dedup_pts(view_attractors)
    if view_detractors:
        ctx["view_detractors"] = _dedup_pts(view_detractors)
    return ctx


def availability_summary(ctx: dict[str, Any]) -> dict[str, bool]:
    """Quick report of which context-derived feature groups are present, for
    transparency in the optimize response."""
    return {
        "roads": bool(ctx.get("roads")),
        "noise_sources": bool(ctx.get("noise_sources")),
        "view_attractors": bool(ctx.get("view_attractors")),
        "obstacles": bool(ctx.get("obstacles")),
        "context_scores": bool(ctx.get("context_scores")),
    }
