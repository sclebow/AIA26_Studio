"""View optimization scorer — WRAPS the existing view optimization logic.

Per the spec, the existing view optimizer is NOT rewritten. This module reuses
the candidate's view scores already produced by view_optimization_runtime /
agent.tools.view_optimizer (unblocked_view, attractor_view, sky_exposure) when
present, and adds the spec's view-quality framing (parks/water/skyline/landmarks
positive; industrial/blank-wall negative) + metrics.
"""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    # Prefer the REAL view scores already computed by the existing view optimizer.
    unblocked = _num(candidate.get("unblocked_view_score") or candidate.get("view_score"))
    attractor = _num(candidate.get("attractor_view_score"))
    sky = _num(candidate.get("sky_exposure_score") or candidate.get("sky_exposure"))

    # If the candidate has no precomputed view score, derive a light proxy from
    # proximity to positive attractors (parks/water) minus negative ones.
    if unblocked is None and attractor is None:
        proxy = _view_proxy(candidate, ctx)
        unblocked = proxy
        attractor = proxy

    unblocked = unblocked if unblocked is not None else 0.5
    attractor = attractor if attractor is not None else unblocked
    sky = sky if sky is not None else unblocked

    # Premium view area = fraction of facade with attractor exposure.
    premium = round(attractor * 0.9, 2)
    quality = 0.5 * unblocked + 0.35 * attractor + 0.15 * sky
    proxy_quality = quality  # before any environmental detractor penalty
    # Environmental Mode when real view features are present: rewards parks/water,
    # penalises highways/industrial detractors (both from context_enrichment).
    pos = ctx.get("view_attractors") or []
    neg = ctx.get("view_detractors") or []
    env_mode = bool(pos or neg)
    if env_mode and neg:
        # Apply the real detractor penalty even when a precomputed view score was used —
        # a great unblocked view that LOOKS AT a highway/industrial yard is still degraded.
        cx, cy = _geom.centroid(candidate.get("boundary") or [[0, 0], [1, 0], [0, 1]])
        neg_near = _nearness_bonus(cx, cy, neg)
        pos_near = _nearness_bonus(cx, cy, pos)
        quality = _geom.clamp01(quality * (1.0 - 0.35 * neg_near) + 0.1 * pos_near)
    score_100 = round(_geom.clamp01(quality) * 100, 1)
    metrics = {
        "view_quality_score": round(quality * 100),
        "view_coverage_pct": round(unblocked * 100),
        "premium_view_area_pct": round(premium * 100),
    }
    if env_mode:
        # proxy = view quality WITHOUT the environmental detractor penalty (for comparison).
        metrics.update({
            "mode": "environmental",
            "proxy_score": round(_geom.clamp01(proxy_quality) * 100, 1),
            "env_score": score_100,
            "positive_features": len(pos),
            "negative_features": len(neg),
        })
    else:
        metrics["mode"] = "geometry"
    return {
        "score": score_100,
        "metrics": metrics,
        "reason": (f"view quality {round(quality*100)}"
                   + (f", {len(pos)} good / {len(neg)} bad features" if env_mode else "")),
    }


def _view_proxy(candidate, ctx) -> float:
    """0..1 proxy: closer to positive attractors (park/water) is better; closer to
    negative features (industrial/blank) is worse."""
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return 0.5
    cx, cy = _geom.centroid(b)
    positive = ctx.get("view_attractors") or []   # [{x,y}] parks/water/landmarks
    negative = ctx.get("view_detractors") or []   # [{x,y}] industrial/service/blank
    pos = _nearness_bonus(cx, cy, positive)
    neg = _nearness_bonus(cx, cy, negative)
    return _geom.clamp01(0.5 + 0.5 * pos - 0.4 * neg)


def _nearness_bonus(cx, cy, pts) -> float:
    if not pts:
        return 0.0
    best = 0.0
    for p in pts:
        px = p.get("x", p[0] if isinstance(p, (list, tuple)) else None)
        py = p.get("y", p[1] if isinstance(p, (list, tuple)) else None)
        if px is None or py is None:
            continue
        d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
        best = max(best, max(0.0, 1.0 - d / 300.0))  # within 300m counts
    return best


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
