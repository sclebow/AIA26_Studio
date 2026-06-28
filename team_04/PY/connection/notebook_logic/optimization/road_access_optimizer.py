"""Accessibility scorer — road / service access + amenity proximity.

Two modes (same pattern as wind/noise):
  * GEOMETRY/PROXY (always): distance to the nearest road + a service/emergency
    access check. The original behaviour.
  * ENVIRONMENTAL (when ctx carries amenity distances): a 15-minute-city style
    accessibility score from REAL distances to transit, parks, schools, healthcare
    and retail (from the OSM context edges). Closer to daily-need amenities = higher.

Activates when ctx["amenities"] (label→distance_m) is present. The distances are
straight-line from OSM (a strong proxy); a true street-network routing engine is a
later upgrade — the metric is labelled accordingly so it's honest.
"""
from __future__ import annotations

from typing import Any

from . import _geom


# Amenity groups → the walk distance (m) considered "good" (≈ within a short walk).
# Matched case-insensitively against the amenity labels stored on context edges.
_AMENITY_TARGETS = {
    "transit": (("metro", "train station", "bus", "tram", "transit", "station"), 500),
    "park": (("park", "garden", "green", "playground"), 400),
    "school": (("school", "college", "university", "education"), 800),
    "healthcare": (("hospital", "clinic", "pharmacy", "healthcare", "doctor"), 1000),
    "retail": (("shop", "store", "retail", "supermarket", "market", "grocery", "mall"), 600),
}


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 0.0, "metrics": {}, "reason": "no footprint"}

    proxy = _proxy_score(candidate, ctx)
    amenities = ctx.get("amenities") or {}
    if not amenities:
        return {"score": proxy["score"],
                "metrics": {**proxy["metrics"], "mode": "geometry"},
                "reason": proxy["reason"]}

    env = _environmental_score(amenities, proxy)
    return {"score": env["score"],
            "metrics": {**proxy["metrics"], **env["metrics"], "mode": "environmental",
                        "proxy_score": proxy["score"], "env_score": env["score"]},
            "reason": env["reason"]}


def _proxy_score(candidate, ctx) -> dict[str, Any]:
    cx, cy = _geom.centroid(candidate.get("boundary") or [])
    roads = ctx.get("roads") or []
    if not roads:
        site = ctx.get("site_boundary") or []
        edge_d = _geom.dist_point_to_poly(cx, cy, site) if site else 30.0
        access = _geom.clamp01(1.0 - edge_d / 60.0)
        return {"score": round(access * 100, 1),
                "metrics": {"avg_distance_to_road_m": round(edge_d),
                            "accessibility_score": round(access * 100),
                            "service_efficiency": round(access * 100)},
                "reason": f"~{round(edge_d)}m to site edge (street access)"}
    nearest = min(_geom.dist_point_to_poly(cx, cy, _path(r)) for r in roads)
    access = _geom.clamp01(1.0 - nearest / 120.0)
    service = 1.0 if nearest <= 30 else _geom.clamp01(1.0 - (nearest - 30) / 90.0)
    s = 0.6 * access + 0.4 * service
    return {"score": round(s * 100, 1),
            "metrics": {"avg_distance_to_road_m": round(nearest),
                        "accessibility_score": round(access * 100),
                        "service_efficiency": round(service * 100)},
            "reason": f"{round(nearest)}m to nearest road"}


def _environmental_score(amenities: dict[str, float], proxy) -> dict[str, Any]:
    """15-minute-city accessibility from real amenity distances. Each group scores
    1.0 within its target walk distance, falling to 0 at ~2× the target. Overall =
    average across the available groups."""
    group_scores: dict[str, int] = {}
    reached = 0
    for group, (words, target) in _AMENITY_TARGETS.items():
        d = _nearest_amenity(amenities, words)
        if d is None:
            continue
        sc = _geom.clamp01(1.0 - max(0.0, d - target) / float(target))  # 1 within target → 0 at 2×
        group_scores[group] = round(sc * 100)
        if sc > 0.4:
            reached += 1
    if not group_scores:
        return {"score": proxy["score"], "metrics": {}, "reason": proxy["reason"]}
    overall = sum(group_scores.values()) / len(group_scores)
    return {"score": round(overall, 1),
            "metrics": {
                **{f"access_{g}": v for g, v in group_scores.items()},
                "amenities_within_walk": reached,
                "accessibility_basis": "OSM straight-line distance",
            },
            "reason": (f"15-min access: {reached}/{len(_AMENITY_TARGETS)} amenity types "
                       f"within walk (avg {round(overall)})")}


def _nearest_amenity(amenities: dict[str, float], words) -> float | None:
    best = None
    for label, dist in amenities.items():
        low = str(label).lower()
        if any(w in low for w in words):
            try:
                d = float(dist)
            except (TypeError, ValueError):
                continue
            if best is None or d < best:
                best = d
    return best


def _path(r):
    if isinstance(r, dict):
        return r.get("path") or r.get("boundary") or []
    return r
