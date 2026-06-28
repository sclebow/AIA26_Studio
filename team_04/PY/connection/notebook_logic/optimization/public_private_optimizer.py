"""Public / semi-private / private spatial zoning analysis.

Evaluates the privacy gradient: public frontage at the street edge, semi-private
courtyards, private interior/rear zones, and use-conflict (public crowding into
private). Returns the spec's four metrics plus a blended score.
"""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    cx, cy = _geom.centroid(b)
    site = ctx.get("site_boundary") or []
    site_area = ctx.get("site_area") or _geom.area(site)

    # Public access: building near a street edge gives an active public frontage.
    edge_d = _geom.dist_point_to_poly(cx, cy, site) if site else 30.0
    public = _geom.clamp01(1.0 - edge_d / 60.0)

    # Semi-private quality: a courtyard provides a protected shared realm.
    court_area = sum(_geom.area(h) for h in (candidate.get("holes") or []))
    semi = _geom.clamp01(court_area / max(1.0, site_area) * 6) if court_area else 0.25

    # Privacy gradient: a clear public(front) -> semi(court) -> private(rear) sequence.
    gradient = _geom.clamp01(0.4 + 0.3 * (1.0 if court_area else 0.0) + 0.3 * public)

    # Use conflict: public frontage AND a courtyard means public/private overlap risk
    # if there's no separation — low conflict is good, so invert.
    conflict = _geom.clamp01(public * semi * 0.6)
    use_conflict_score = round((1.0 - conflict) * 100)

    blended = 0.3 * public + 0.25 * semi + 0.25 * gradient + 0.2 * (1.0 - conflict)
    return {
        "score": round(blended * 100, 1),
        "metrics": {
            "public_access_score": round(public * 100),
            "semi_private_quality_score": round(semi * 100),
            "privacy_gradient_score": round(gradient * 100),
            "use_conflict_score": use_conflict_score,
        },
        "reason": f"public {round(public*100)}, semi-private {round(semi*100)}, gradient {round(gradient*100)}",
    }
