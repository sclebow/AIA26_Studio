"""Emergency access scorer — fire-truck access, evacuation routes, service-road proximity.

Also exposes a hard MINIMUM check used by validation (a candidate with no road
within the fire-access threshold fails emergency-access minimums).
"""
from __future__ import annotations

from typing import Any

from . import _geom

FIRE_ACCESS_MAX_M = 46.0   # ~ max hose/ladder reach from a fire lane (common code basis)


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    cx, cy = _geom.centroid(b)
    roads = ctx.get("roads") or []
    if roads:
        nearest = min(_geom.dist_point_to_poly(cx, cy, _path(r)) for r in roads)
    else:
        site = ctx.get("site_boundary") or []
        nearest = _geom.dist_point_to_poly(cx, cy, site) if site else 30.0
    compliant = nearest <= FIRE_ACCESS_MAX_M
    s = _geom.clamp01(1.0 - nearest / FIRE_ACCESS_MAX_M)
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "emergency_compliance_score": round(s * 100),
            "fire_access_distance_m": round(nearest),
            "fire_access_ok": bool(compliant),
        },
        "reason": f"{round(nearest)}m to access road ({'ok' if compliant else 'exceeds fire reach'})",
    }


def meets_minimum(candidate: dict[str, Any], ctx: dict[str, Any]) -> bool:
    """Hard gate for validation: a fire lane must be within reach of the building."""
    return bool(score(candidate, ctx)["metrics"].get("fire_access_ok"))


def _path(r):
    return r.get("path") or r.get("boundary") or [] if isinstance(r, dict) else r
