"""Context response scorer — tall-neighbour response, transit, park frontage, edge activation."""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    cx, cy = _geom.centroid(b)
    scores_ctx = ctx.get("context_scores") or {}
    # Reuse the already-computed urban-context scores where available (0-100).
    transit = _norm(scores_ctx.get("transit") or scores_ctx.get("accessibility"))
    walk = _norm(scores_ctx.get("walkability"))
    green = _norm(scores_ctx.get("greenSpace") or scores_ctx.get("green_space"))
    # Street-edge activation: building near a site edge activates the street.
    site = ctx.get("site_boundary") or []
    edge_d = _geom.dist_point_to_poly(cx, cy, site) if site else 30.0
    activation = _geom.clamp01(1.0 - edge_d / 60.0)
    integ = 0.35 * transit + 0.25 * walk + 0.2 * green + 0.2 * activation
    return {
        "score": round(integ * 100, 1),
        "metrics": {
            "context_compatibility": round((transit + green) / 2 * 100),
            "urban_integration_score": round(integ * 100),
            "street_edge_activation": round(activation * 100),
        },
        "reason": f"urban integration {round(integ*100)}, edge activation {round(activation*100)}",
    }


def _norm(v):
    try:
        return max(0.0, min(1.0, float(v) / 100.0)) if v is not None else 0.5
    except (TypeError, ValueError):
        return 0.5
