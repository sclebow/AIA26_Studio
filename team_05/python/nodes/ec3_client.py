from __future__ import annotations
import requests
from typing import Optional

# Ökobaudat — German Federal Ministry public EPD database, no auth required.
# Two-step query: search by name to get UUID, then fetch process detail for GWP.
_BASE = "https://oekobaudat.de/OEKOBAU.DAT/resource"

# Maps our material keys to Ökobaudat search terms.
# German terms give better results since it is a German database.
_SEARCH_MAP: dict[str, str] = {
    # Structural slabs
    "rc_solid":         "concrete",
    "rc_waffle":        "concrete",
    "rc_ribbed":        "concrete",
    "post_tensioned":   "concrete",
    "hollow_core":      "concrete",
    "composite_steel":  "Stahl",
    "precast":          "concrete",
    "timber_joist":     "Vollholz",
    # Floor finishes
    "porcelain_tile":   "Keramik",
    "ceramic_tile":     "Keramik",
    "marble":           "Marmor",
    "granite":          "Granit",
    "natural_stone":    "Naturstein",
    "engineered_wood":  "Holzwerkstoff",
    "solid_wood":       "Vollholz",
    "laminate":         "Laminat",
    "vinyl":            "Vinyl",
    "epoxy":            "Epoxidharz",
    "polished_concrete":"Sichtbeton",
    "carpet":           "Teppich",
    "terrazzo":         "Terrazzo",
    # Wall finishes
    "paint":            "Dispersionsfarbe",
    "emulsion_paint":   "Dispersionsfarbe",
    "gypsum_paint":     "Gipsputz",
    "wallpaper":        "Tapete",
    "wood_panel":       "Holzwerkstoff",
    "veneer":           "Furnier",
    "exposed_concrete": "Sichtbeton",
    "stucco":           "Gipsputz",
    "cladding":         "Fassadenverkleidung",
    # Ceiling
    "gypsum_board":     "Gipskartonplatte",
    "gypsum_painted":   "Gipskartonplatte",
    "suspended_gypsum": "Gipskartonplatte",
    "acoustic_tile":    "Mineralwolle",
    "metal_panel":      "Aluminiumblech",
    "wood_slat":        "Holz",
    "paint_on_slab":    "Dispersionsfarbe",
    "stretch_ceiling":  "PVC",
    # Doors
    "mdf_painted":      "MDF",
    "mdf_veneer":       "MDF",
    "hdf_laminate":     "HDF",
    "flush_hollow_core":"Holz",
    "steel":            "Stahl",
    "aluminum":         "Aluminium",
    "upvc":             "PVC",
    "glass_frameless":  "Flachglas",
    "fire_rated_60":    "Stahl",
    "fire_rated_120":   "Stahl",
    "wood":             "Vollholz",
    "hardwood":         "Laubholz",
    # Windows
    "aluminum_single":          "Aluminium",
    "aluminum_double":          "Aluminium",
    "thermal_aluminum_double":  "Aluminium",
    "thermal_aluminum_low_e":   "Aluminium",
    "upvc_double":              "PVC",
    "upvc_double_low_e":        "PVC",
    "wood_double":              "Vollholz",
    "wood_clad_aluminum":       "Aluminium",
    "steel_single":             "Stahl",
    "steel_double":             "Stahl",
    "curtain_wall":             "Flachglas",
    # Column finishes
    "plaster_paint":    "Gipsputz",
    "fair_face_concrete":"Sichtbeton",
    "marble_clad":      "Marmor",
    "metal_clad":       "Stahl",
    "grc_clad":         "Beton",
    "wood_clad":        "Holzwerkstoff",
}

# Session cache: material_key → GWP value (avoids repeated API calls)
_cache: dict[str, Optional[float]] = {}


def _normalise(s: str) -> str:
    return s.lower().replace(" ", "_").replace("-", "_")


def _search_uuid(term: str) -> Optional[str]:
    """Return the UUID of the first matching Ökobaudat process."""
    try:
        r = requests.get(
            f"{_BASE}/processes",
            params={"search": "true", "name": term, "format": "json", "pageSize": 5},
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()

        # Response may be {"data": [...]} or a list directly
        entries = body.get("data", body) if isinstance(body, dict) else body
        if not entries:
            return None

        first = entries[0] if isinstance(entries, list) else None
        if not first:
            return None

        # UUID may be at top level or nested
        return first.get("uuid") or first.get("sapi:uuid")
    except Exception:
        return None


def _fetch_gwp(uuid: str) -> Optional[float]:
    """Fetch process detail and extract GWP-total for module A1-A3."""
    try:
        r = requests.get(
            f"{_BASE}/processes/{uuid}",
            params={"format": "json"},
            timeout=10,
        )
        r.raise_for_status()
        return _parse_gwp(r.json())
    except Exception:
        return None


def _parse_gwp(data: dict) -> Optional[float]:
    """Walk the ILCD+EPD JSON structure to find GWP-total for A1-A3.

    Actual anies structure: [{"value": "-681.48", "module": "A1-A3"}, ...]
    Each item carries its module as a direct key alongside "value".
    """
    try:
        # LCIAResults sits at root level (not wrapped in processDataSet)
        root = data.get("processDataSet", data)
        lcia_list = root.get("LCIAResults", {}).get("LCIAResult", [])
        if isinstance(lcia_list, dict):
            lcia_list = [lcia_list]

        for result in lcia_list:
            # Check indicator name contains "GWP" and "total"
            descriptions = (
                result.get("referenceToLCIAMethodDataSet", {})
                      .get("shortDescription", [])
            )
            if isinstance(descriptions, dict):
                descriptions = [descriptions]
            name = " ".join(d.get("value", "") for d in descriptions).upper()
            # Older EPDs (EN 15804+A1) use "Global warming potential (GWP)" without "total".
            # Accept any GWP indicator — prefer total, but fall back to generic.
            if "GWP" not in name and "WARMING" not in name:
                continue

            # Each anies item has {"value": "...", "module": "A1-A3"}
            for item in result.get("other", {}).get("anies", []):
                if item.get("module") in ("A1-A3", "A1A2A3", "A1-A2-A3"):
                    try:
                        return round(float(item["value"]), 2)
                    except (TypeError, ValueError, KeyError):
                        pass
    except Exception:
        pass
    return None


def get_gwp(material_key: str) -> Optional[float]:
    """Return GWP-total A1-A3 (kgCO2e) from Ökobaudat for a material key.

    Returns None if the material is unmapped or the API call fails —
    the caller should use the static fallback value.
    """
    key = _normalise(material_key)

    if key in _cache:
        return _cache[key]

    # Try word-reversed key as fallback (e.g. 'wood_solid' -> 'solid_wood')
    parts = key.split("_")
    reversed_key = "_".join(reversed(parts)) if len(parts) > 1 else key

    term = _SEARCH_MAP.get(key) or _SEARCH_MAP.get(reversed_key)
    if not term:
        _cache[key] = None
        return None

    uuid = _search_uuid(term)
    if not uuid:
        print(f"[oekobaudat] No results for '{term}' (material: {material_key})")
        _cache[key] = None
        return None

    gwp = _fetch_gwp(uuid)
    print(f"[oekobaudat] GWP for '{material_key}' ({term}): {gwp} kgCO2e")
    _cache[key] = gwp
    return gwp
