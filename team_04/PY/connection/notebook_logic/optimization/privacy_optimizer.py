"""Privacy scorer — window-to-window distance, overlooking risk, residential privacy."""
from __future__ import annotations

import math
from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    cx, cy = _geom.centroid(b)
    # Distance to the nearest neighbouring building drives overlooking. Two sources:
    #   1. obstacles — other buildings placed in THIS session (footprint rings)
    #   2. neighbor_buildings — the REAL surrounding OSM buildings (each {height, cx, cy})
    # Use whichever is present; the OSM neighbours make this a real, site-aware score
    # instead of N/A on a single-building site.
    nearest = float("inf")
    source = None
    for ob in (ctx.get("obstacles") or []):
        if not ob or len(ob) < 3:
            continue
        ox, oy = _geom.centroid(ob)
        nearest = min(nearest, math.hypot(ox - cx, oy - cy))
        source = "placed buildings"
    for nb in (ctx.get("neighbor_buildings") or []):
        ox, oy = nb.get("cx"), nb.get("cy")
        if ox is None or oy is None:
            continue
        nearest = min(nearest, math.hypot(float(ox) - cx, float(oy) - cy))
        source = "OSM neighbours"
    if nearest == float("inf"):
        nearest = 60.0  # open site — good privacy
    # >=18m window-to-window is a common residential privacy benchmark.
    privacy = _geom.clamp01((nearest - 8.0) / 22.0)
    overlooking = round((1.0 - privacy) * 100)
    return {
        "score": round(privacy * 100, 1),
        "metrics": {
            "privacy_index": round(privacy * 100),
            "overlooking_risk": overlooking,
            "nearest_neighbour_m": round(nearest),
        },
        "reason": (f"{round(nearest)}m to nearest neighbour "
                   f"({source or 'open site'}), overlooking risk {overlooking}"),
    }
