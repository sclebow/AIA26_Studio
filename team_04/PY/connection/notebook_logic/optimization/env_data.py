"""Environmental data retrieval + per-site cache — the foundation for real,
site-aware environmental analysis (vs geometry proxies).

Design goals (so it NEVER disrupts the working geometry path):
  * Fetch real datasets ONCE per site (keyed by rounded lat/long), cache in-process.
  * Every fetch is wrapped: a network failure / timeout / bad response returns None,
    so the calling scorer transparently falls back to its geometry proxy.
  * No fetch happens at all unless the ENVIRONMENTAL feature flag is ON (see flags()).
  * Optimization scores ~200 candidates per run — this module is called PER SITE
    (once, cached), NEVER per candidate, so it adds no per-candidate latency.

Currently implemented: WIND (NASA POWER prevailing direction + seasonal speeds).
The same get_site_env(lat, lng) cache is the plug point for future scorers
(noise / view / density / accessibility / advanced solar) — each adds a fetch_* fn
and a key in the returned record; nothing else changes.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Feature flag — the master switch between Legacy Geometry Mode and Environmental
# Mode. OFF by default so the live workflow is byte-for-byte unchanged.
# ---------------------------------------------------------------------------

def env_mode_enabled() -> bool:
    """True when Environmental Mode is ON. DEFAULT = ON (real site-aware analysis), so it
    survives restarts without toggling. Precedence:
      1. runtime override via set_env_mode() / POST /env/mode (highest)
      2. env var TERRAPILOT_ENV_MODE (set '0'/'off'/'false' to force OFF)
      3. default → ON
    """
    if _RUNTIME_OVERRIDE["value"] is not None:
        return bool(_RUNTIME_OVERRIDE["value"])
    raw = (os.environ.get("TERRAPILOT_ENV_MODE") or "").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return False
    if raw in ("1", "on", "true", "yes"):
        return True
    return True  # default ON


_RUNTIME_OVERRIDE: dict[str, Any] = {"value": None}


def set_env_mode(on: bool | None) -> None:
    """Runtime override of the flag (None = defer to the env var). Lets the UI/tests
    flip modes without a restart."""
    _RUNTIME_OVERRIDE["value"] = on


# ---------------------------------------------------------------------------
# Per-site cache — keyed by rounded lat/long (~100 m). Thread-safe. In-process;
# a process restart re-fetches (fine — data is climatological, changes slowly).
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_HTTP_TIMEOUT = float(os.environ.get("TERRAPILOT_ENV_TIMEOUT", "12"))


def _site_key(lat: float, lng: float) -> str:
    return f"{round(float(lat), 3)},{round(float(lng), 3)}"


def resolve_site_coords(state: dict[str, Any]) -> tuple[float | None, float | None]:
    """Find the site's lat/lng from wherever the app stored it. The location is set at
    different stages under different keys, so we check them in order. Returns
    (lat, lng) or (None, None)."""
    # 1) explicit site_latitude / site_longitude
    lat = state.get("site_latitude")
    lng = state.get("site_longitude")
    if lat is not None and lng is not None:
        return float(lat), float(lng)
    # 2) site_context.center {lat, lng} (set during context analysis)
    for key in ("site_context", "urban_context"):
        c = (state.get(key) or {}).get("center") if isinstance(state.get(key), dict) else None
        if isinstance(c, dict) and c.get("lat") is not None and c.get("lng") is not None:
            return float(c["lat"]), float(c["lng"])
    # 3) a stored location object {lat, lng}
    loc = state.get("location") or {}
    if isinstance(loc, dict) and loc.get("lat") is not None and loc.get("lng") is not None:
        return float(loc["lat"]), float(loc["lng"])
    return None, None


def get_site_env(lat: float | None, lng: float | None) -> dict[str, Any] | None:
    """Return the cached environmental record for a site, fetching it once if needed.
    Returns None when Environmental Mode is OFF or no coordinates are available — the
    caller then uses its geometry proxy. Never raises."""
    if not env_mode_enabled():
        return None
    if lat is None or lng is None:
        return None
    try:
        key = _site_key(lat, lng)
    except (TypeError, ValueError):
        return None

    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    record = _build_site_env(float(lat), float(lng))
    with _CACHE_LOCK:
        _CACHE[key] = record
    return record


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _build_site_env(lat: float, lng: float) -> dict[str, Any]:
    """Assemble the env record for a site. Each dataset is independent + optional;
    a failed fetch simply leaves that key absent (scorer falls back)."""
    record: dict[str, Any] = {
        "lat": lat, "lng": lng,
        "fetched_at": time.time(),
        "sources": {},  # per-dataset {available, source, note}
    }
    wind = fetch_wind(lat, lng)
    if wind:
        record["wind"] = wind
        record["sources"]["wind"] = {"available": True, "source": wind.get("source")}
    else:
        record["sources"]["wind"] = {"available": False, "source": "NASA POWER", "note": "fetch failed"}
    climate = fetch_climate(lat, lng)
    if climate:
        record["climate"] = climate
        record["sources"]["climate"] = {"available": True, "source": climate.get("source")}
    else:
        record["sources"]["climate"] = {"available": False, "source": "NASA POWER", "note": "fetch failed"}
    return record


# ---------------------------------------------------------------------------
# WIND — NASA POWER climatology (free, no API key). Monthly + annual prevailing
# direction (deg, meteorological: direction wind comes FROM) and speed (m/s).
# ---------------------------------------------------------------------------

_NASA_POWER_URL = (
    "https://power.larc.nasa.gov/api/temporal/climatology/point"
    "?parameters=WS10M,WD10M&community=RE&longitude={lng}&latitude={lat}&format=JSON"
)
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def fetch_wind(lat: float, lng: float) -> dict[str, Any] | None:
    """Real prevailing wind for the site from NASA POWER. Returns a wind record or
    None on any failure. The 'prevailing_dir' is meteorological (FROM), in degrees."""
    url = _NASA_POWER_URL.format(lat=lat, lng=lng)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TerraPilot/1.0"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except Exception:  # noqa: BLE001 — any failure → None → geometry fallback
        return None

    try:
        params = data["properties"]["parameter"]
        wd = params.get("WD10M", {})
        ws = params.get("WS10M", {})
        ann_dir = wd.get("ANN")
        ann_spd = ws.get("ANN")
        if ann_dir is None or ann_spd is None:
            # Derive annual from the monthly mean if ANN missing.
            mdirs = [wd[m] for m in _MONTHS if m in wd]
            mspds = [ws[m] for m in _MONTHS if m in ws]
            if not mdirs or not mspds:
                return None
            ann_dir = _circular_mean(mdirs)
            ann_spd = sum(mspds) / len(mspds)
        monthly = {m: {"dir": wd.get(m), "speed": ws.get(m)} for m in _MONTHS if m in wd and m in ws}
        # Seasonal split (meteorological seasons, N. hemisphere oriented but fine as
        # a generic 3-month grouping for the wind rose).
        seasons = {
            "winter": _season_dir(wd, ws, ["DEC", "JAN", "FEB"]),
            "spring": _season_dir(wd, ws, ["MAR", "APR", "MAY"]),
            "summer": _season_dir(wd, ws, ["JUN", "JUL", "AUG"]),
            "autumn": _season_dir(wd, ws, ["SEP", "OCT", "NOV"]),
        }
        return {
            "source": "NASA POWER",
            "prevailing_dir": round(float(ann_dir), 1),   # degrees FROM (met. convention)
            "prevailing_speed": round(float(ann_spd), 2),  # m/s
            "monthly": monthly,
            "seasons": seasons,
            "compass": _deg_to_compass(float(ann_dir)),
        }
    except Exception:  # noqa: BLE001
        return None


def _season_dir(wd: dict, ws: dict, months: list[str]) -> dict[str, Any] | None:
    dirs = [wd[m] for m in months if m in wd]
    spds = [ws[m] for m in months if m in ws]
    if not dirs or not spds:
        return None
    return {"dir": round(_circular_mean(dirs), 1),
            "speed": round(sum(spds) / len(spds), 2),
            "compass": _deg_to_compass(_circular_mean(dirs))}


def _circular_mean(degs: list[float]) -> float:
    """Mean of angles (degrees) handling the 360/0 wrap."""
    s = sum(math.sin(math.radians(d)) for d in degs)
    c = sum(math.cos(math.radians(d)) for d in degs)
    return (math.degrees(math.atan2(s, c)) + 360) % 360


def _deg_to_compass(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg % 360) / 22.5 + 0.5) % 16]


# ---------------------------------------------------------------------------
# CLIMATE — NASA POWER annual + seasonal solar radiation and max temperature, for
# advanced solar (annual radiation, overheating risk, daylight potential).
# ---------------------------------------------------------------------------

_NASA_CLIMATE_URL = (
    "https://power.larc.nasa.gov/api/temporal/climatology/point"
    "?parameters=ALLSKY_SFC_SW_DWN,T2M_MAX,T2M&community=RE"
    "&longitude={lng}&latitude={lat}&format=JSON"
)


def fetch_climate(lat: float, lng: float) -> dict[str, Any] | None:
    """Annual + summer solar radiation (kWh/m²/day) and max temperature (°C) from NASA
    POWER. Used for overheating risk + annual solar yield. None on any failure."""
    url = _NASA_CLIMATE_URL.format(lat=lat, lng=lng)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TerraPilot/1.0"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read())
        p = data["properties"]["parameter"]
        rad = p.get("ALLSKY_SFC_SW_DWN", {})
        tmax = p.get("T2M_MAX", {})
        tmean = p.get("T2M", {})
        ann_rad = rad.get("ANN")
        if ann_rad is None:
            vals = [rad[m] for m in _MONTHS if m in rad]
            ann_rad = sum(vals) / len(vals) if vals else None
        if ann_rad is None:
            return None
        summer_rad = _avg([rad.get(m) for m in ["MAR", "APR", "MAY"]])  # hot season here
        summer_tmax = _avg([tmax.get(m) for m in ["MAR", "APR", "MAY"]])
        return {
            "source": "NASA POWER",
            "annual_radiation": round(float(ann_rad), 2),          # kWh/m²/day
            "summer_radiation": round(summer_rad, 2) if summer_rad else None,
            "annual_tmax": round(float(tmax.get("ANN")), 1) if tmax.get("ANN") is not None else None,
            "summer_tmax": round(summer_tmax, 1) if summer_tmax else None,
            "annual_tmean": round(float(tmean.get("ANN")), 1) if tmean.get("ANN") is not None else None,
        }
    except Exception:  # noqa: BLE001
        return None


def _avg(vals):
    nums = [v for v in vals if v is not None]
    return sum(nums) / len(nums) if nums else None
