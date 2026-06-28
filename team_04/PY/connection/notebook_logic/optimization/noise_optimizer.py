"""Noise scorer — environmental noise exposure.

Two modes (same pattern as wind_optimizer):
  * GEOMETRY/PROXY (always available): exposure from plain distance to the nearest
    road, no class weighting. The original behaviour.
  * ENVIRONMENTAL (when ctx carries classified noise_sources): road-CLASS-weighted
    exposure — a motorway/primary road is far louder than a residential lane at the
    same distance — plus a day/night estimate (night penalises proximity to arterial
    roads more, as quiet hours make traffic noise more intrusive).

The environmental path activates whenever ctx["noise_sources"] entries carry a
'road_class' (produced by context_enrichment in Environmental Mode). Otherwise it
falls back to the proxy. Result carries proxy_score + env_score + mode for the
dashboard comparison.
"""
from __future__ import annotations

import math
from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    cx, cy = _geom.centroid(b)

    proxy = _proxy_score(cx, cy, ctx)
    sources = ctx.get("noise_sources") or []
    has_class = any("road_class" in s for s in sources)

    if not has_class:
        return {
            "score": proxy["score"],
            "metrics": {**proxy["metrics"], "mode": "geometry"},
            "reason": proxy["reason"],
        }

    env = _environmental_score(cx, cy, sources, proxy)
    return {
        "score": env["score"],
        "metrics": {
            **proxy["metrics"], **env["metrics"], "mode": "environmental",
            "proxy_score": proxy["score"], "env_score": env["score"],
        },
        "reason": env["reason"],
    }


def _proxy_score(cx: float, cy: float, ctx: dict[str, Any]) -> dict[str, Any]:
    sources = ctx.get("noise_sources") or []
    if not sources:
        roads = ctx.get("roads") or []
        nearest = min((_geom.dist_point_to_poly(cx, cy, _path(r)) for r in roads), default=120.0)
        exposure = _geom.clamp01(1.0 - nearest / 120.0)
    else:
        worst = 0.0
        for s in sources:
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None:
                continue
            d = math.hypot(sx - cx, sy - cy)
            worst = max(worst, float(s.get("level", 1.0)) * max(0.0, 1.0 - d / 250.0))
        exposure = _geom.clamp01(worst)
    quiet = 1.0 - exposure
    return {
        "score": round(quiet * 100, 1),
        "metrics": {"noise_exposure_score": round(exposure * 100),
                    "quiet_zone_score": round(quiet * 100)},
        "reason": f"quiet zone {round(quiet*100)}, exposure {round(exposure*100)}",
    }


def _environmental_score(cx: float, cy: float, sources: list[dict[str, Any]],
                         proxy: dict[str, Any]) -> dict[str, Any]:
    """Road-class-weighted exposure + day/night. Distance falloff ~ 1 - d/300 (noise
    carries further from busy roads). Night exposure weights arterial roads higher."""
    day_worst, night_worst, loudest = 0.0, 0.0, None
    for s in sources:
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None:
            continue
        d = math.hypot(sx - cx, sy - cy)
        falloff = max(0.0, 1.0 - d / 300.0)
        rc = float(s.get("road_class", s.get("level", 0.5)))
        day = rc * falloff
        # at night, arterial roads (high class) feel louder relative to ambient quiet
        night = min(1.0, rc * (0.7 + 0.5 * rc)) * falloff
        if day > day_worst:
            day_worst, loudest = day, s.get("label")
        night_worst = max(night_worst, night)

    day_exp = _geom.clamp01(day_worst)
    night_exp = _geom.clamp01(night_worst)
    # Overall exposure leans on the worse of day/night.
    exposure = _geom.clamp01(0.5 * day_exp + 0.5 * night_exp)
    quiet = 1.0 - exposure
    # crude dB estimate for display (≈ 45 dB quiet .. 75 dB at a busy road front)
    day_db = round(45 + 30 * day_exp)
    night_db = round(40 + 30 * night_exp)
    return {
        "score": round(quiet * 100, 1),
        "metrics": {
            "noise_exposure_score": round(exposure * 100),
            "quiet_zone_score": round(quiet * 100),
            "day_noise_db": day_db,
            "night_noise_db": night_db,
            "loudest_source": loudest or "—",
        },
        "reason": (f"road-class noise: day ~{day_db}dB, night ~{night_db}dB "
                   f"(loudest: {loudest or 'road'}), quiet {round(quiet*100)}"),
    }


def _path(r):
    return r.get("path") or r.get("boundary") or [] if isinstance(r, dict) else r
