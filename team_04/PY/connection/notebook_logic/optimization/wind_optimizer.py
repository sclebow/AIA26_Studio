"""Wind/ventilation scorer.

Two modes, selected automatically per call:
  * GEOMETRY (legacy, always available): cross-ventilation from plate depth,
    courtyard airflow, wind-tunnel risk from aspect ratio. Unchanged from before.
  * ENVIRONMENTAL (when real wind data is in ctx): scores the building's actual
    ORIENTATION + facade exposure + courtyard alignment against the site's REAL
    prevailing wind direction & speed (NASA POWER, via env_data + ctx["wind"]).

The environmental path is used ONLY when ctx carries a "wind" record (which only
happens with Environmental Mode ON and a successful fetch). Otherwise it falls back
to the geometry proxy — so the legacy workflow is byte-for-byte unchanged.

The result always carries BOTH scores (proxy_score + env_score when available) and a
`mode` flag, so the dashboard can show the comparison.
"""
from __future__ import annotations

import math
from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}

    proxy = _geometry_score(candidate)
    wind = ctx.get("wind")  # real wind record (only present in Environmental Mode)

    if not wind or wind.get("prevailing_dir") is None:
        # Legacy geometry mode — identical behaviour to before.
        return {
            "score": proxy["score"],
            "metrics": {**proxy["metrics"], "mode": "geometry"},
            "reason": proxy["reason"],
        }

    env = _environmental_score(candidate, wind, proxy)
    return {
        "score": env["score"],
        "metrics": {
            **proxy["metrics"],
            **env["metrics"],
            "mode": "environmental",
            "proxy_score": proxy["score"],   # geometry score, for dashboard comparison
            "env_score": env["score"],
        },
        "reason": env["reason"],
    }


# ---------------------------------------------------------------------------
# GEOMETRY proxy (legacy) — kept exactly as the original scorer.
# ---------------------------------------------------------------------------

def _geometry_score(candidate: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    w, h, *_ = _geom.extent(b)
    depth = min(w, h)
    cross = _geom.clamp01((20.0 - depth) / 16.0) if depth else 0.5
    court = 0.15 if candidate.get("holes") else 0.0
    aspect = (max(w, h) / max(1.0, min(w, h)))
    tunnel_risk = _geom.clamp01((aspect - 2.0) / 3.0) * (1.0 if (candidate.get("floors") or 1) > 12 else 0.5)
    s = _geom.clamp01(0.7 * cross + court + 0.3 * (1.0 - tunnel_risk))
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "ventilation_potential": round(cross * 100),
            "wind_comfort_index": round((1.0 - tunnel_risk) * 100),
            "courtyard_airflow": bool(candidate.get("holes")),
        },
        "reason": f"ventilation {round(cross*100)}, wind comfort {round((1-tunnel_risk)*100)}",
    }


# ---------------------------------------------------------------------------
# ENVIRONMENTAL — score against the REAL prevailing wind.
# ---------------------------------------------------------------------------

def _environmental_score(candidate: dict[str, Any], wind: dict[str, Any],
                         proxy: dict[str, Any]) -> dict[str, Any]:
    """Natural-ventilation potential vs the site's actual wind:
      * Facade exposure — how broadly the building presents a facade TO the incoming
        wind (a long facade facing the wind catches more breeze for cross-ventilation).
      * Wind-tunnel penalty — a long facade EXACTLY perpendicular to a STRONG wind, on a
        tall mass, over-channels it (pedestrian discomfort).
      * Courtyard alignment — a courtyard helps most when the form can funnel wind
        through it (open toward the prevailing direction).
    All driven by the candidate's real orientation relative to wind['prevailing_dir'].
    """
    b = candidate.get("boundary") or []
    prevailing = float(wind["prevailing_dir"])      # degrees the wind comes FROM
    speed = float(wind.get("prevailing_speed") or 3.0)
    wind_to = (prevailing + 180.0) % 360.0          # direction wind travels TOWARD

    # Longest facade direction (the building's main orientation axis).
    facade_dir, facade_len = _longest_edge_bearing(b)
    perim = _geom.perimeter(b) or 1.0

    # Exposure: fraction of facade that faces INTO the wind (catches it for ventilation).
    exposure = _facade_exposure_to_wind(b, wind_to)

    # How square-on the longest facade is to the wind (0 = parallel, 1 = perpendicular).
    perpendicularity = abs(math.cos(math.radians(_angle_between(facade_dir, prevailing))))

    # Cross-ventilation potential: good exposure + a shallow-enough plate to let air
    # pass through. Reuse the geometry depth term so a deep block still scores low.
    w, h, *_ = _geom.extent(b)
    depth = min(w, h)
    through_depth = _geom.clamp01((22.0 - depth) / 18.0) if depth else 0.5
    vent_potential = _geom.clamp01(0.55 * exposure + 0.45 * through_depth)

    # Wind-tunnel risk: a long facade perpendicular to a STRONG wind on a tall mass.
    long_frac = facade_len / perim
    strong = _geom.clamp01((speed - 3.0) / 5.0)     # ramps in above ~3 m/s
    tall = 1.0 if (candidate.get("floors") or 1) > 12 else 0.5
    tunnel_risk = _geom.clamp01(perpendicularity * long_frac * strong * (0.6 + 0.4 * tall))

    # Courtyard alignment bonus — a void aligned to let wind through the core.
    court_bonus = 0.0
    if candidate.get("holes"):
        court_bonus = 0.12 * (0.5 + 0.5 * exposure)

    s = _geom.clamp01(0.7 * vent_potential + court_bonus + 0.3 * (1.0 - tunnel_risk))
    score_100 = round(s * 100, 1)
    return {
        "score": score_100,
        "metrics": {
            "prevailing_wind": f"{wind.get('compass', '?')} ({round(prevailing)}°)",
            "wind_speed_ms": round(speed, 2),
            "facade_exposure_pct": round(exposure * 100),
            "ventilation_potential": round(vent_potential * 100),
            "wind_tunnel_risk": round(tunnel_risk * 100),
        },
        "reason": (f"oriented to {wind.get('compass','?')} wind "
                   f"({round(speed,1)} m/s): exposure {round(exposure*100)}%, "
                   f"vent {round(vent_potential*100)}, tunnel risk {round(tunnel_risk*100)}"),
    }


# ---- geometry helpers (orientation vs wind) ----

def _edge_bearing(ax, ay, bx, by) -> float:
    """Bearing of an edge as a 0-360 angle (atan2(dy,dx) convention, x=east y=north)."""
    return (math.degrees(math.atan2(by - ay, bx - ax)) + 360) % 360


def _longest_edge_bearing(b: list[list[float]]) -> tuple[float, float]:
    best_len, best_dir = 0.0, 0.0
    n = len(b)
    for i in range(n):
        ax, ay = b[i][0], b[i][1]
        bx, by = b[(i + 1) % n][0], b[(i + 1) % n][1]
        d = math.hypot(bx - ax, by - ay)
        if d > best_len:
            best_len, best_dir = d, _edge_bearing(ax, ay, bx, by)
    return best_dir, best_len


def _angle_between(a: float, b: float) -> float:
    """Smallest difference between two bearings, 0-90 (treats a facade as bidirectional)."""
    d = abs((a - b) % 180)
    return min(d, 180 - d)


def _facade_exposure_to_wind(b: list[list[float]], wind_to_deg: float) -> float:
    """Fraction of the perimeter whose OUTWARD normal faces into the incoming wind
    (i.e. windward facades that catch the breeze). 0..1, length-weighted."""
    n = len(b)
    cx = sum(p[0] for p in b) / n
    cy = sum(p[1] for p in b) / n
    # unit vector the wind is blowing TOWARD
    wx, wy = math.cos(math.radians(wind_to_deg)), math.sin(math.radians(wind_to_deg))
    windward, total = 0.0, 0.0
    for i in range(n):
        ax, ay = b[i][0], b[i][1]
        bx, by = b[(i + 1) % n][0], b[(i + 1) % n][1]
        seg = math.hypot(bx - ax, by - ay)
        if seg < 1e-6:
            continue
        total += seg
        mx, my = (ax + bx) / 2, (ay + by) / 2
        nx, ny = mx - cx, my - cy            # outward normal (midpoint - centroid)
        nlen = math.hypot(nx, ny) or 1.0
        # facade is windward if its outward normal opposes the wind-travel vector
        facing = -(nx / nlen * wx + ny / nlen * wy)
        if facing > 0:
            windward += seg * facing
    return _geom.clamp01(windward / total) if total else 0.0
