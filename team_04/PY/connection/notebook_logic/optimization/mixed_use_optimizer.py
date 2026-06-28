"""Mixed-use scorer — retail frontage, residential privacy, public/private stacking."""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    use = (ctx.get("building_use") or "mixed_use").lower()
    floors = int(candidate.get("floors") or 1)
    cx, cy = _geom.centroid(b)
    site = ctx.get("site_boundary") or []
    edge_d = _geom.dist_point_to_poly(cx, cy, site) if site else 30.0
    # Retail frontage potential: ground floor near a street edge.
    frontage = _geom.clamp01(1.0 - edge_d / 50.0)
    # Vertical separation potential: enough floors to stack retail/office/residential.
    stacking = _geom.clamp01((floors - 2) / 10.0)
    # Use separation: a courtyard/void helps separate public vs private circulation.
    separation = 0.8 if candidate.get("holes") else 0.4
    bonus = 0.1 if use in ("mixed_use", "mixed-use", "mixed") else 0.0
    s = _geom.clamp01(0.4 * frontage + 0.3 * stacking + 0.3 * separation + bonus)
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "functional_efficiency": round(s * 100),
            "use_separation_score": round(separation * 100),
            "retail_frontage_potential": round(frontage * 100),
        },
        "reason": f"frontage {round(frontage*100)}, use separation {round(separation*100)}",
    }
