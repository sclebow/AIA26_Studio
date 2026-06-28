"""Shared confirmed-site state — the single source of truth for the site boundary.

When the user confirms a boundary on the map, the frontend posts it here (via
connection/routes/site_routes.py). It is persisted to connection/data/confirmed_site.json
and every other runtime module loads it when no explicit boundary is supplied, so
geometry generation, optimization, the decision graph, and the agent workflow all
operate on the same site.

Units: the agent's geometry tools work in METERS, but the map draws in geographic
DEGREES (lng/lat). `project_ring_to_meters` converts a lng/lat ring to a local
metric frame (equirectangular about its centroid, sub-meter accurate at site
scale). `save_confirmed_site` accepts either; pass project=True for raw lng/lat.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any

# connection/data/confirmed_site.json  (this file is connection/notebook_logic/site_state.py)
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_SITE_PATH = os.path.join(_DATA_DIR, "confirmed_site.json")

_EARTH_RADIUS_M = 6378137.0  # WGS84 equatorial radius


# --------------------------------------------------------------------------- #
# Projection (lng/lat degrees -> local meters). Mirrors the frontend helper so
# both sides agree; the canonical version lives here.
# --------------------------------------------------------------------------- #
def project_ring_to_meters(ring: list[list[float]]) -> tuple[list[list[float]], dict[str, float] | None]:
    """Project a [[lng, lat], ...] ring to a local metric frame about its centroid.

    Returns (projected_ring, origin) where origin = {"lng", "lat"} is the frame's
    geographic center (so the result can be unprojected later). A ring with fewer
    than 3 points is returned unchanged with origin=None.
    """
    if not ring or len(ring) < 3:
        return ring, None
    lngs = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    lng0 = sum(lngs) / len(lngs)
    lat0 = sum(lats) / len(lats)
    cos_lat = math.cos(math.radians(lat0))
    projected = [
        [
            math.radians(float(p[0]) - lng0) * _EARTH_RADIUS_M * cos_lat,
            math.radians(float(p[1]) - lat0) * _EARTH_RADIUS_M,
        ]
        for p in ring
    ]
    return projected, {"lng": lng0, "lat": lat0}


def polygon_area_sqm(ring: list[list[float]]) -> float:
    """Shoelace area of a planar (metric) ring."""
    if not ring or len(ring) < 3:
        return 0.0
    pts = [(float(p[0]), float(p[1])) for p in ring]
    area = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def _normalize_ring(ring: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for p in ring or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            out.append([float(p[0]), float(p[1])] + ([float(p[2])] if len(p) > 2 else []))
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def save_confirmed_site(
    boundary: list[list[float]],
    *,
    project: bool = False,
    location_name: str | None = None,
    origin: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a confirmed site boundary as the single source of truth.

    boundary: ring of [x, y] (meters) or [lng, lat] (degrees, when project=True).
    project:  if True, treat boundary as lng/lat and project to meters here.
    Returns the stored record.
    """
    ring = _normalize_ring(boundary)
    if len(ring) < 3:
        raise ValueError("Boundary needs at least 3 points")

    if project:
        metric_ring, derived_origin = project_ring_to_meters(ring)
        ring = metric_ring
        origin = origin or derived_origin

    record: dict[str, Any] = {
        "boundary": ring,
        "origin": origin,
        "area_sqm": round(polygon_area_sqm(ring), 2),
        "location_name": location_name,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        record.update(extra)

    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SITE_PATH, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    return record


def load_confirmed_site() -> dict[str, Any] | None:
    """Return the stored site record, or None if none has been confirmed."""
    if not os.path.exists(_SITE_PATH):
        return None
    try:
        with open(_SITE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) and data.get("boundary") else None


def load_confirmed_boundary() -> list[list[float]] | None:
    """Convenience: just the metric boundary ring of the confirmed site, or None."""
    record = load_confirmed_site()
    return record.get("boundary") if record else None


def has_confirmed_site() -> bool:
    return load_confirmed_site() is not None


def clear_confirmed_site() -> bool:
    """Remove the confirmed site. Returns True if a file was deleted."""
    if os.path.exists(_SITE_PATH):
        os.remove(_SITE_PATH)
        return True
    return False
