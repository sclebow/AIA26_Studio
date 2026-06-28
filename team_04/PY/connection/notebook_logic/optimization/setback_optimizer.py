"""Setback compliance scorer — reuses the existing setback_rules / buildable area."""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    site = ctx.get("site_boundary") or []
    if len(b) < 3 or len(site) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "insufficient geometry"}
    rules = ctx.get("setback_rules")
    buildable = ctx.get("buildable_area")
    try:
        from .. import setback_rules as sr

        if rules is None:
            rules = sr.get_setback_rules(ctx.get("building_use") or "residential")
        if buildable is None:
            poly = sr.create_buildable_area(site, rules)
            buildable = [[float(x), float(y)] for x, y in poly.exterior.coords] if poly else site
    except Exception:  # noqa: BLE001
        buildable = site

    inside = _fraction_inside(b, buildable)
    # Buildable-envelope utilization: how much of the allowed footprint is used.
    util = _geom.clamp01(_geom.area(b) / max(1.0, _geom.area(buildable)))
    compliance = inside  # 1.0 = fully within setback zone
    s = 0.75 * compliance + 0.25 * min(1.0, util * 1.4)
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "compliance_pct": round(compliance * 100),
            "buildable_envelope_utilization_pct": round(util * 100),
            "setback_distance_m": getattr(rules, "min_setback", None) if rules else None,
        },
        "reason": f"{round(compliance*100)}% within setback, {round(util*100)}% envelope used",
    }


def _fraction_inside(b, container):
    """Fraction of b's area that lies inside the container polygon (shapely)."""
    try:
        from shapely.geometry import Polygon

        bp = Polygon([(p[0], p[1]) for p in b])
        cp = Polygon([(p[0], p[1]) for p in container])
        if not bp.is_valid:
            bp = bp.buffer(0)
        if not cp.is_valid:
            cp = cp.buffer(0)
        if bp.area <= 0:
            return 0.0
        return max(0.0, min(1.0, bp.intersection(cp).area / bp.area))
    except Exception:  # noqa: BLE001
        return 1.0
