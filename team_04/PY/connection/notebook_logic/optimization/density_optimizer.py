"""Density scorer — FAR / GFA / site coverage / buildable volume use.

Two modes (same pattern as wind/noise):
  * GEOMETRY/PROXY (always): FAR utilisation vs the allowed limit + a coverage
    penalty. The original behaviour.
  * ENVIRONMENTAL (when ctx carries neighbor_buildings): also scores CONTEXTUAL
    density — how the proposed massing (height + coverage) fits the surrounding
    urban fabric. A tower among low-rise is penalised for context-insensitivity;
    matching the prevailing height/coverage is rewarded.

Activates when ctx["neighbor_buildings"] is present (Environmental Mode + stored
OSM neighbours). Otherwise falls back to the proxy. Carries proxy/env/mode.
"""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    site_area = ctx.get("site_area") or _geom.area(ctx.get("site_boundary") or [])
    if len(b) < 3 or site_area <= 0:
        return {"score": 0.0, "metrics": {}, "reason": "no footprint/site"}

    proxy = _proxy_score(candidate, ctx, site_area)
    neighbours = ctx.get("neighbor_buildings") or []
    if not neighbours:
        return {"score": proxy["score"],
                "metrics": {**proxy["metrics"], "mode": "geometry"},
                "reason": proxy["reason"]}

    env = _environmental_score(candidate, ctx, site_area, neighbours, proxy)
    return {"score": env["score"],
            "metrics": {**proxy["metrics"], **env["metrics"], "mode": "environmental",
                        "proxy_score": proxy["score"], "env_score": env["score"]},
            "reason": env["reason"]}


def _proxy_score(candidate, ctx, site_area) -> dict[str, Any]:
    fp = _geom.area(candidate.get("boundary") or [])
    floors = int(candidate.get("floors") or 1)
    gfa = fp * floors
    far = gfa / site_area
    coverage = fp / site_area
    far_limit = float(ctx.get("far_limit") or 3.5)
    far_util = _geom.clamp01(far / far_limit)
    cover_penalty = max(0.0, coverage - 0.55) * 1.5
    s = _geom.clamp01(0.8 * far_util + 0.2 * (1.0 - cover_penalty))
    return {"score": round(s * 100, 1),
            "metrics": {"far": round(far, 2), "far_utilization_pct": round(far_util * 100),
                        "gfa_sqm": round(gfa), "site_coverage_pct": round(coverage * 100),
                        "density_efficiency": round(s * 100)},
            "reason": f"FAR {round(far,2)} ({round(far_util*100)}% of limit), coverage {round(coverage*100)}%"}


def _environmental_score(candidate, ctx, site_area, neighbours, proxy) -> dict[str, Any]:
    """Blend FAR utilisation with CONTEXT FIT: how the proposed height compares to the
    surrounding building heights. Matching the local height band = high context fit; a
    big jump above (a tower among low-rise) or far below is penalised."""
    fp = _geom.area(candidate.get("boundary") or [])
    floors = int(candidate.get("floors") or 1)
    prop_height = float(candidate.get("height_m") or floors * 3.2)

    heights = [float(n.get("height") or 0) for n in neighbours if (n.get("height") or 0) > 0]
    if not heights:
        return {"score": proxy["score"], "metrics": {}, "reason": proxy["reason"]}
    heights.sort()
    median_h = heights[len(heights) // 2]
    avg_h = sum(heights) / len(heights)
    # Context fit: 1.0 when proposed ≈ local median; falls off as it diverges. A modest
    # uplift over context (1-1.5×) is fine (intensification); a 3× jump is jarring.
    ratio = prop_height / max(4.0, median_h)
    if ratio <= 1.0:
        context_fit = _geom.clamp01(ratio)                      # below context → underuse
    else:
        context_fit = _geom.clamp01(1.0 - (ratio - 1.0) / 2.5)  # above → diminishing fit

    far = (fp * floors) / site_area
    far_util = _geom.clamp01(far / float(ctx.get("far_limit") or 3.5))
    # Environmental density = mostly FAR utilisation, weighted by how well it sits in
    # the urban fabric.
    s = _geom.clamp01(0.6 * far_util + 0.4 * context_fit)
    return {"score": round(s * 100, 1),
            "metrics": {"context_median_height_m": round(median_h, 1),
                        "context_avg_height_m": round(avg_h, 1),
                        "proposed_height_m": round(prop_height, 1),
                        "context_fit_pct": round(context_fit * 100),
                        "neighbours_considered": len(heights)},
            "reason": (f"{round(prop_height)}m vs local median {round(median_h)}m "
                       f"(context fit {round(context_fit*100)}%), FAR {round(far,2)}")}
