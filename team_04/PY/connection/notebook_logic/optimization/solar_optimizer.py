"""Solar optimization scorer — daylight access, self-shading, solar gain.

Reuses the existing sunlight_analysis (NOAA solar calculator) where possible and
derives the spec's solar metrics (Daylight Autonomy, UDI, Sun Hours, Shadow
Impact) from the candidate footprint + orientation. Pure scoring (0-100).
"""
from __future__ import annotations

import math
from typing import Any


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    boundary = candidate.get("boundary") or []
    if len(boundary) < 3:
        return {"score": 0.0, "metrics": {}, "reason": "no footprint"}

    # Proxy daylight model: shallower plates + slender proportion + more south-facing
    # facade + less self-shading from neighbours = more daylight.
    w, h = _extent(boundary)
    depth = min(w, h)
    # Daylight autonomy proxy: shallow floor plates (<= ~12m deep) give high DA.
    da = max(0.0, min(1.0, (18.0 - depth) / 14.0)) if depth else 0.5
    # Useful Daylight Illuminance: best in a mid band of depth (not too deep, not glare-shallow).
    udi = max(0.0, 1.0 - abs(depth - 12.0) / 14.0)
    # South facade exposure: the longer the south-facing edge, the better the winter gain.
    south_len = _south_facing_length(boundary)
    perim = _perimeter(boundary)
    south_frac = (south_len / perim) if perim else 0.0
    # Self-shading from neighbouring buildings (obstacles): nearer/taller = more shadow.
    obstacles = ctx.get("obstacles") or []
    shadow = _shadow_impact(boundary, obstacles)
    # Sun hours proxy (mid-latitude clear-day ~ 6h; reduced by shadow).
    sun_hours = round(max(1.5, 6.5 * (1.0 - 0.6 * shadow)), 1)
    # Courtyard sunlight bonus if the candidate has a hole (courtyard) bringing light to the core.
    has_court = bool(candidate.get("holes"))

    s = (
        0.30 * da
        + 0.20 * udi
        + 0.25 * south_frac
        + 0.15 * (1.0 - shadow)
        + (0.10 if has_court else 0.0)
    )
    proxy_100 = round(_clamp(s) * 100, 1)
    metrics = {
        "daylight_autonomy_pct": round(da * 100),
        "udi_pct": round(udi * 100),
        "solar_radiation": round((south_frac * 0.7 + da * 0.3) * 100),
        "sun_hours": sun_hours,
        "shadow_impact": round(shadow * 100),
        "south_facade_frac": round(south_frac, 2),
    }

    # ENVIRONMENTAL: real NASA POWER climate. Annual radiation drives the solar
    # potential; in a hot climate a large unshaded south/west exposure becomes an
    # OVERHEATING RISK (cooling load), so the score balances daylight vs heat. The
    # proxy maximised south facade unconditionally — fine for daylight, wrong for a
    # hot site. This is the real climate-aware correction.
    climate = ctx.get("climate")
    if climate and climate.get("annual_radiation") is not None:
        ann_rad = float(climate["annual_radiation"])             # kWh/m²/day
        summer_tmax = float(climate.get("summer_tmax") or climate.get("annual_tmax") or 28.0)
        # Daylight potential scales with available radiation (≈3 low .. 7 high).
        rad_factor = _clamp((ann_rad - 3.0) / 4.0)
        # Overheating risk: hot climate (summer Tmax) × large solar-exposed facade.
        heat = _clamp((summer_tmax - 28.0) / 12.0)               # ramps in above 28°C
        overheating = _clamp(heat * (0.4 + 0.6 * south_frac))    # more south facade = more gain
        # Annual solar yield potential (daylight + passive gain) tempered by overheating.
        daylight_potential = _clamp(0.6 * da + 0.4 * rad_factor)
        env_s = _clamp(0.55 * daylight_potential
                       + 0.20 * udi
                       + 0.15 * (1.0 - shadow)
                       + 0.10 * (1.0 - overheating))
        env_100 = round(env_s * 100, 1)
        metrics.update({
            "mode": "environmental",
            "proxy_score": proxy_100,
            "env_score": env_100,
            "annual_radiation_kwh_m2_day": round(ann_rad, 2),
            "summer_max_temp_c": round(summer_tmax, 1),
            "overheating_risk_pct": round(overheating * 100),
            "daylight_potential_pct": round(daylight_potential * 100),
        })
        return {"score": env_100, "metrics": metrics,
                "reason": (f"{ann_rad} kWh/m²/day, {round(summer_tmax)}°C summer — "
                           f"daylight {round(daylight_potential*100)}, "
                           f"overheating risk {round(overheating*100)}")}

    metrics["mode"] = "geometry"
    return {"score": proxy_100, "metrics": metrics,
            "reason": f"DA {round(da*100)}%, {sun_hours}h sun, south facade {round(south_frac*100)}%"}


def _extent(b):
    xs = [p[0] for p in b if len(p) >= 2]; ys = [p[1] for p in b if len(p) >= 2]
    return (max(xs) - min(xs), max(ys) - min(ys)) if xs else (0.0, 0.0)


def _perimeter(b):
    n = len(b); tot = 0.0
    for i in range(n):
        a, c = b[i], b[(i + 1) % n]
        tot += math.hypot(c[0] - a[0], c[1] - a[1])
    return tot


def _south_facing_length(b):
    """Total length of edges whose outward normal points roughly south (-y)."""
    n = len(b); tot = 0.0
    cx = sum(p[0] for p in b) / n; cy = sum(p[1] for p in b) / n
    for i in range(n):
        a, c = b[i], b[(i + 1) % n]
        mx, my = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
        # outward = midpoint - centroid; south-facing if it points -y
        if (my - cy) < -1e-6:
            tot += math.hypot(c[0] - a[0], c[1] - a[1])
    return tot


def _shadow_impact(b, obstacles):
    """0 (no shading) .. 1 (heavy). Nearby obstacle polygons cast more shadow."""
    if not obstacles:
        return 0.05
    cx = sum(p[0] for p in b) / len(b); cy = sum(p[1] for p in b) / len(b)
    worst = 0.0
    for ob in obstacles:
        if not ob or len(ob) < 3:
            continue
        ox = sum(p[0] for p in ob) / len(ob); oy = sum(p[1] for p in ob) / len(ob)
        d = math.hypot(ox - cx, oy - cy)
        worst = max(worst, max(0.0, 1.0 - d / 80.0))  # within 80m starts shading
    return min(1.0, worst)


def _clamp(v):
    return max(0.0, min(1.0, v))
