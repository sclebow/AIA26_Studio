"""Open space scorer — public open space, green, plazas, courtyard usability."""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    site_area = ctx.get("site_area") or _geom.area(ctx.get("site_boundary") or [])
    if len(b) < 3 or site_area <= 0:
        return {"score": 0.0, "metrics": {}, "reason": "no footprint/site"}
    fp = _geom.area(b)
    open_ratio = _geom.clamp01(1.0 - fp / site_area)        # site not covered by building
    # Courtyard usability: interior voids count as semi-public usable open space.
    court_area = sum(_geom.area(h) for h in (candidate.get("holes") or []))
    court_ratio = _geom.clamp01(court_area / site_area)
    # Public realm: open ground that is generous (>=35%) reads as real public space.
    public = _geom.clamp01((open_ratio - 0.2) / 0.6)
    s = 0.55 * open_ratio + 0.25 * public + 0.20 * min(1.0, court_ratio * 6)
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "open_space_ratio_pct": round(open_ratio * 100),
            "green_coverage_pct": round(open_ratio * 70),     # assume ~70% of open is landscaped
            "public_realm_score": round(public * 100),
            "courtyard_open_pct": round(court_ratio * 100),
        },
        "reason": f"{round(open_ratio*100)}% open, public realm {round(public*100)}",
    }
