"""
Building Transparency (EC3) API client — North America & global EPD database.

Requires a free API key from https://buildingtransparency.org
Set environment variable BT_API_KEY before launching Streamlit.

  Windows PowerShell:  $env:BT_API_KEY = "your_token_here"
  bash / macOS:        export BT_API_KEY="your_token_here"
"""
from __future__ import annotations
import os
import pathlib
import requests
from typing import Optional

# Auto-load .env from repo root so BT_API_KEY works without manual export.
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # python-dotenv if installed
        for candidate in [
            pathlib.Path(__file__).parents[3] / ".env",
            pathlib.Path(__file__).parents[2] / ".env",
            pathlib.Path(".env"),
        ]:
            if candidate.exists():
                load_dotenv(candidate, override=False)
                return
    except ImportError:
        # Fallback: minimal .env parser (no dependency needed)
        for candidate in [
            pathlib.Path(__file__).parents[3] / ".env",
            pathlib.Path(__file__).parents[2] / ".env",
            pathlib.Path(".env"),
        ]:
            if not candidate.exists():
                continue
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
            return

_load_dotenv()

_BASE = "https://api.buildingtransparency.org"

# Maps our material keys to English EC3 search terms.
_SEARCH_MAP: dict[str, str] = {
    # Structural slabs
    "rc_solid":                  "ready mix concrete",
    "rc_waffle":                 "ready mix concrete",
    "rc_ribbed":                 "ready mix concrete",
    "post_tensioned":            "ready mix concrete",
    "hollow_core":               "precast concrete",
    "composite_steel":           "structural steel",
    "precast":                   "precast concrete",
    "timber_joist":              "dimensional lumber",
    # Floor finishes
    "porcelain_tile":            "porcelain tile",
    "ceramic_tile":              "ceramic tile",
    "marble":                    "marble",
    "granite":                   "granite",
    "natural_stone":             "natural stone",
    "engineered_wood":           "engineered wood flooring",
    "solid_wood":                "hardwood flooring",
    "laminate":                  "laminate flooring",
    "vinyl":                     "vinyl flooring",
    "epoxy":                     "epoxy coating",
    "polished_concrete":         "polished concrete",
    "carpet":                    "carpet",
    "terrazzo":                  "terrazzo",
    # Wall finishes
    "paint":                     "interior paint",
    "emulsion_paint":            "interior paint",
    "gypsum_paint":              "gypsum plaster",
    "wallpaper":                 "wallpaper",
    "wood_panel":                "wood panel",
    "veneer":                    "wood veneer",
    "exposed_concrete":          "concrete",
    "stucco":                    "stucco",
    "cladding":                  "cladding panel",
    # Ceiling
    "gypsum_board":              "gypsum board",
    "gypsum_painted":            "gypsum board",
    "suspended_gypsum":          "gypsum board",
    "acoustic_tile":             "acoustic ceiling tile",
    "metal_panel":               "aluminum panel",
    "wood_slat":                 "wood",
    "paint_on_slab":             "interior paint",
    "stretch_ceiling":           "PVC",
    # Doors
    "mdf_painted":               "MDF",
    "mdf_veneer":                "MDF",
    "hdf_laminate":              "HDF",
    "flush_hollow_core":         "hollow core door",
    "steel":                     "structural steel",
    "aluminum":                  "aluminum",
    "upvc":                      "PVC window",
    "glass_frameless":           "flat glass",
    "fire_rated_60":             "fire door",
    "fire_rated_120":            "fire door",
    "wood":                      "dimensional lumber",
    "hardwood":                  "hardwood",
    # Windows
    "aluminum_single":           "aluminum window",
    "aluminum_double":           "aluminum window",
    "thermal_aluminum_double":   "aluminum window",
    "thermal_aluminum_low_e":    "aluminum window",
    "upvc_double":               "PVC window",
    "upvc_double_low_e":         "PVC window",
    "wood_double":               "wood window",
    "wood_clad_aluminum":        "aluminum window",
    "steel_single":              "steel window",
    "steel_double":              "steel window",
    "curtain_wall":              "curtain wall",
    # Column finishes
    "plaster_paint":             "gypsum plaster",
    "fair_face_concrete":        "concrete",
    "marble_clad":               "marble",
    "metal_clad":                "structural steel",
    "grc_clad":                  "concrete",
    "wood_clad":                 "wood panel",
}

# Session cache: "{material_key}|{jurisdiction}" → GWP value
_cache: dict[str, Optional[float]] = {}


def has_api_key() -> bool:
    """Return True if BT_API_KEY is set in the environment."""
    return bool(os.environ.get("BT_API_KEY"))


def _normalise(s: str) -> str:
    return s.lower().replace(" ", "_").replace("-", "_")


def _fetch_gwp(term: str, jurisdiction: Optional[str], api_key: str) -> Optional[float]:
    """Call EC3 /api/epds/ and return the first A1-A3 GWP found."""
    headers = {"Authorization": f"Bearer {api_key}"}
    params: dict = {"q": term, "page_size": 5}
    if jurisdiction:
        params["jurisdiction__in"] = jurisdiction
    try:
        r = requests.get(
            f"{_BASE}/api/epds/",
            headers=headers,
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        results = body.get("results", []) if isinstance(body, dict) else body
        if not isinstance(results, list):
            return None
        for epd in results:
            gwp = _parse_gwp(epd)
            if gwp is not None:
                return gwp
        return None
    except Exception:
        return None


def _parse_gwp(epd: dict) -> Optional[float]:
    """Try multiple field paths to extract A1-A3 GWP from an EC3 EPD object."""
    try:
        # Primary: top-level gwp / gwp_total field
        for field in ("gwp", "gwp_total", "global_warming_potential"):
            raw = epd.get(field)
            if raw is None:
                continue
            if isinstance(raw, (int, float)):
                return round(float(raw), 2)
            if isinstance(raw, dict):
                for key in ("A1A3", "A1-A3", "a1a3", "a1-a3", "declared"):
                    v = raw.get(key)
                    if v is not None:
                        try:
                            return round(float(v), 2)
                        except (TypeError, ValueError):
                            pass

        # Secondary: impacts list
        for impact in epd.get("impacts", []):
            name = (impact.get("name") or "").upper()
            if "GWP" not in name and "WARMING" not in name:
                continue
            for key in ("A1A3", "A1-A3", "declared"):
                v = impact.get(key)
                if v is not None:
                    try:
                        return round(float(v), 2)
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass
    return None


def get_gwp(material_key: str, jurisdiction: Optional[str] = None) -> Optional[float]:
    """Return GWP A1-A3 (kgCO2e) from EC3 Building Transparency.

    jurisdiction: ISO 3166-1 alpha-2 code, e.g. 'US', 'CA', 'AU', 'NZ'.
                  Pass None to search globally across all jurisdictions.
    Returns None if BT_API_KEY is missing, material unmapped, or API call fails.
    """
    key = _normalise(material_key)
    cache_key = f"{key}|{jurisdiction or ''}"

    if cache_key in _cache:
        return _cache[cache_key]

    api_key = os.environ.get("BT_API_KEY")
    if not api_key:
        _cache[cache_key] = None
        return None

    parts = key.split("_")
    reversed_key = "_".join(reversed(parts)) if len(parts) > 1 else key
    term = _SEARCH_MAP.get(key) or _SEARCH_MAP.get(reversed_key)
    if not term:
        _cache[cache_key] = None
        return None

    gwp = _fetch_gwp(term, jurisdiction, api_key)
    status = f"{gwp} kgCO2e" if gwp is not None else "not found"
    print(f"[ec3_bt] '{material_key}' ({term}, {jurisdiction or 'global'}): {status}")
    _cache[cache_key] = gwp
    return gwp
