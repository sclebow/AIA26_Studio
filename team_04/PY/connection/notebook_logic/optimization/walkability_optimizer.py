"""Walkability scorer — transit/retail/public-space proximity, pedestrian routes."""
from __future__ import annotations

from typing import Any


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    cs = ctx.get("context_scores") or {}
    walk = _n(cs.get("walkability"))
    transit = _n(cs.get("transit") or cs.get("accessibility"))
    retail = _n(cs.get("retail"))
    s = 0.45 * walk + 0.35 * transit + 0.20 * retail
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "walkability_score": round(walk * 100),
            "transit_access_score": round(transit * 100),
            "retail_proximity_score": round(retail * 100),
        },
        "reason": f"walkability {round(walk*100)}, transit {round(transit*100)}",
    }


def _n(v):
    try:
        return max(0.0, min(1.0, float(v) / 100.0)) if v is not None else 0.5
    except (TypeError, ValueError):
        return 0.5
