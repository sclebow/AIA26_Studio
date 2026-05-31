from __future__ import annotations
import csv
import json
import pathlib
from typing import Any

from nodes.ec3_client import get_gwp

# ---------------------------------------------------------------------------
# Static property database loader
# ---------------------------------------------------------------------------

_PROPS_CACHE: dict = {}

def _load_props() -> dict:
    global _PROPS_CACHE
    if _PROPS_CACHE:
        return _PROPS_CACHE

    candidates = [
        pathlib.Path(__file__).parent.parent / "material_properties.json",
        pathlib.Path("team_05/python/material_properties.json"),
        pathlib.Path("material_properties.json"),
    ]
    for p in candidates:
        if p.exists():
            _PROPS_CACHE = json.loads(p.read_text(encoding="utf-8"))
            return _PROPS_CACHE

    print("[arch_advice] WARNING: material_properties.json not found")
    return {}


def _lookup_static(material_key: str) -> dict:
    """Search all category sections of material_properties.json for material_key.

    Falls back to word-reversed key (e.g. 'wood_solid' -> 'solid_wood') to
    handle LLM inconsistencies in material name ordering.
    """
    props = _load_props()
    key = material_key.lower().replace(" ", "_").replace("-", "_")
    candidates = [key]
    parts = key.split("_")
    if len(parts) > 1:
        candidates.append("_".join(reversed(parts)))

    for candidate in candidates:
        for section_name, section in props.items():
            if section_name == "_meta" or not isinstance(section, dict):
                continue
            if candidate in section:
                return section[candidate]
    return {}

# ---------------------------------------------------------------------------
# Material extraction from layout JSON
# ---------------------------------------------------------------------------

_ROOM_FINISH_KEYS = [
    "floor_finish", "floor-finish",
    "wall_finish", "wall-finish",
    "ceiling_material", "ceiling-material", "ceiling-finish",
    "slab_material", "slab-material",
]
_OPENING_KEYS = ["leaf_material", "frame_material", "glazing", "window_material"]

# Element-type labels that are NOT materials — skip these from tool arg extraction
_ELEMENT_TYPES = {"door", "doors", "window", "windows", "room", "rooms", "column", "columns", "floor", "ceiling", "wall", "slab"}

# Informal or abbreviated names → canonical material_properties.json keys
_MATERIAL_ALIASES: dict[str, str] = {
    "wooden":           "solid_wood",
    "wood":             "solid_wood",
    "timber":           "solid_wood",
    "concrete":         "rc_solid",
    "reinforced_concrete": "rc_solid",
    "glass":            "glass_frameless",
    "glazing":          "curtain_wall",
    "tile":             "ceramic_tile",
    "tiles":            "ceramic_tile",
    "stone":            "natural_stone",
    "plaster":          "plaster_paint",
    "gypsum":           "gypsum_board",
    "carpet_tile":      "carpet",
    "hardwood_floor":   "solid_wood",
    "engineered":       "engineered_wood",
}


def _extract_materials(state: dict[str, Any]) -> list[str]:
    """Collect unique material keys from tool call history, layout JSON, and input_data."""
    materials: list[str] = []

    # Primary source: tool call arguments in the message history.
    # compute_finish_cost and compute_slab_cost always carry a "material" argument.
    for msg in state.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        try:
            body = json.loads(msg["content"])
            if body.get("action") != "tool":
                continue
            for call in body.get("tool_calls", []):
                args = call.get("arguments", {})
                # element_type is always a category (door/window/room) — never a material
                for field in ("material", "finish", "element", "subtype"):
                    raw = args.get(field)
                    if not raw:
                        continue
                    key = str(raw).lower().replace(" ", "_").replace("-", "_")
                    if key in _ELEMENT_TYPES:
                        continue
                    key = _MATERIAL_ALIASES.get(key, key)
                    materials.append(key)
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    # Secondary source: layout JSON room/opening finish fields
    layout_str = state.get("layout_json_string", "")
    if layout_str:
        try:
            layout = json.loads(layout_str)
            for room in layout.get("rooms", []):
                for k in _ROOM_FINISH_KEYS:
                    val = room.get(k)
                    if val:
                        materials.append(str(val).lower().replace(" ", "_").replace("-", "_"))
            for opening in layout.get("openings", []):
                for k in _OPENING_KEYS:
                    val = opening.get(k)
                    if val:
                        materials.append(str(val).lower().replace(" ", "_").replace("-", "_"))
        except (json.JSONDecodeError, AttributeError):
            pass

    # Tertiary source: input_data for single-material price calculation
    input_data = state.get("input_data") or {}
    for field in ("material", "element", "finish"):
        val = input_data.get(field)
        if val:
            materials.append(str(val).lower().replace(" ", "_").replace("-", "_"))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = [m for m in materials if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]
    return unique

# ---------------------------------------------------------------------------
# Advice formatter
# ---------------------------------------------------------------------------

FIRE_STANDARDS = {
    "EN 13501-1": "EN_13501",
    "ASTM E84 (USA)": "ASTM_E84",
    "BS 476 (UK)": "BS_476",
    "GB 8624 (China)": "GB_8624",
    "CAN/ULC-S102 (Canada)": "CAN_ULC",
    "AS/NZS 1530 (Australia/NZ)": "AS_NZS",
}
DEFAULT_STANDARD = "EN 13501-1"

# Region → GWP data source configuration.
# "source" is either "oekobaudat" (existing client) or "ec3" (Building Transparency).
# "jurisdiction" is an ISO 3166-1 alpha-2 code passed to the EC3 API.
GWP_REGIONS: dict[str, dict] = {
    "Europe (Ökobaudat)":        {"source": "oekobaudat"},
    "USA (EC3)":                 {"source": "ec3", "jurisdiction": "US"},
    "Canada (EC3)":              {"source": "ec3", "jurisdiction": "CA"},
    "Australia (EC3)":           {"source": "ec3", "jurisdiction": "AU"},
    "New Zealand (EC3)":         {"source": "ec3", "jurisdiction": "NZ"},
    "China (static only)":       {"source": "static"},
    "Global (static only)":      {"source": "static"},
}
DEFAULT_REGION = "Europe (Ökobaudat)"


def get_gwp_regional(material_key: str, region: str = DEFAULT_REGION) -> float | None:
    """Return GWP A1-A3 for a material using the appropriate regional database.

    Falls back to static value (None) if the chosen source is unavailable.
    """
    cfg = GWP_REGIONS.get(region, {"source": "oekobaudat"})
    source = cfg.get("source", "oekobaudat")

    if source == "oekobaudat":
        return get_gwp(material_key)

    if source == "ec3":
        from nodes.bt_client import get_gwp as bt_get_gwp
        return bt_get_gwp(material_key, cfg.get("jurisdiction"))

    # "static" — caller will use the fallback value from material_properties.json
    return None


def _resolve_fire_rating(static: dict, standard_key: str) -> str:
    """Return the fire rating string for the given standard key."""
    fire = static.get("fire_rating", "—")
    if isinstance(fire, dict):
        return fire.get(standard_key, fire.get("EN_13501", "—"))
    return str(fire) if fire else "—"


def _resolve_material_gwp(material_key: str, region: str = DEFAULT_REGION) -> float | None:
    live = get_gwp_regional(material_key, region)
    if isinstance(live, (int, float)):
        return live
    static = _lookup_static(material_key)
    if static is None:
        return None
    gwp = static.get("gwp_fallback_kgco2e")
    if isinstance(gwp, (int, float)):
        return float(gwp)
    return None


def _lookup_alternatives(material_key: str) -> list[str]:
    static = _lookup_static(material_key)
    if not isinstance(static, dict):
        return []
    alternatives = static.get("alternatives")
    if not isinstance(alternatives, list):
        return []
    normalised: list[str] = []
    for alt in alternatives:
        if not alt:
            continue
        key = str(alt).lower().replace(" ", "_").replace("-", "_")
        normalised.append(key)
    return normalised


def _choose_best_alternative(
    material_key: str,
    region: str = DEFAULT_REGION,
    standard_key: str = "EN_13501",
) -> tuple[str | None, str | None]:
    alternatives = _lookup_alternatives(material_key)
    if not alternatives:
        return None, None

    current_gwp = _resolve_material_gwp(material_key, region)
    best_alt: str | None = None
    best_gwp: float | None = None

    for alt_key in alternatives:
        alt_gwp = _resolve_material_gwp(alt_key, region)
        if alt_gwp is None:
            continue
        if best_gwp is None or alt_gwp < best_gwp:
            best_gwp = alt_gwp
            best_alt = alt_key

    if best_alt is None or best_gwp is None:
        return None, None

    if current_gwp is None:
        return best_alt, "This suggested alternative has a known lower carbon footprint."

    if best_gwp < current_gwp * 0.9:
        delta = int(round((current_gwp - best_gwp) / current_gwp * 100))
        label = material_key.replace("_", " ").title()
        return best_alt, f"Lower embodied carbon by {delta}% compared to {label}."

    return None, None


def _format_material_advice(material_key: str, live_gwp: float | None, standard_key: str = "EN_13501") -> str:
    static = _lookup_static(material_key)
    label = material_key.replace("_", " ").title()

    if not static:
        return f"**{label}**\n  • No property data found in database\n"

    fire = _resolve_fire_rating(static, standard_key)
    life = static.get("life_cycle_years", "N/A")
    gwp_fallback = static.get("gwp_fallback_kgco2e")
    gwp_unit = static.get("gwp_unit", "kgCO2e/m²")

    if live_gwp is not None:
        gwp_display = f"{live_gwp} {gwp_unit} (Okobaudat live)"
    elif gwp_fallback is not None:
        gwp_display = f"{gwp_fallback} {gwp_unit} (reference value)"
    else:
        gwp_display = "N/A"

    alt_key, alt_reason = _choose_best_alternative(material_key, DEFAULT_REGION, standard_key)
    alt_line = ""
    if alt_key:
        alt_label = alt_key.replace("_", " ").title()
        alt_line = f"  • Suggested alternative: {alt_label}\n  • Recommendation: {alt_reason}\n"

    return (
        f"**{label}**\n"
        f"  • Carbon footprint: {gwp_display}\n"
        f"  • Fire rating: {fire}\n"
        f"  • Expected lifespan: {life} years\n"
        f"{alt_line}"
    )

# ---------------------------------------------------------------------------
# Node builder
# ---------------------------------------------------------------------------

# Cap materials per call to avoid overloading context and EC3 rate limits
_MAX_MATERIALS = 8


# Materials recognisable in free-text prompts
_DETECTABLE_FINISH_MATERIALS = [
    "marble", "granite", "porcelain", "ceramic tile", "ceramic",
    "natural stone", "engineered wood", "solid wood", "laminate",
    "vinyl", "epoxy", "polished concrete", "carpet", "terrazzo",
    "paint", "wallpaper", "wood panel", "veneer", "stucco",
    "gypsum board", "acoustic tile", "metal panel", "wood slat",
    "plaster", "glass", "aluminium", "aluminum", "timber",
    "rc solid", "rc waffle", "hollow core", "precast",
]


def extract_materials_from_messages(messages: list[dict]) -> list[str]:
    """Scan user chat messages for material keyword mentions."""
    # Build a combined keyword → canonical-key lookup from both sources
    _keyword_map: dict[str, str] = {}
    for mat in _DETECTABLE_FINISH_MATERIALS:
        key = mat.lower().replace(" ", "_").replace("-", "_")
        _keyword_map[mat] = _MATERIAL_ALIASES.get(key, key)
    for alias, canonical in _MATERIAL_ALIASES.items():
        _keyword_map[alias.replace("_", " ")] = canonical

    # Sort longest keyword first so "ceramic tile" beats "ceramic"
    keywords = sorted(_keyword_map.keys(), key=len, reverse=True)

    materials: list[str] = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").lower()
        for kw in keywords:
            if kw in content:
                materials.append(_keyword_map[kw])
    seen: set[str] = set()
    return [m for m in materials if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]


def extract_materials_from_layout(layout: dict) -> list[str]:
    """Return a deduplicated list of material keys found in room/opening finish fields."""
    materials: list[str] = []
    for room in layout.get("rooms", []):
        for k in _ROOM_FINISH_KEYS:
            val = room.get(k)
            if val:
                key = str(val).lower().replace(" ", "_").replace("-", "_")
                key = _MATERIAL_ALIASES.get(key, key)
                materials.append(key)
    for opening in layout.get("openings", []):
        for k in _OPENING_KEYS:
            val = opening.get(k)
            if val:
                key = str(val).lower().replace(" ", "_").replace("-", "_")
                key = _MATERIAL_ALIASES.get(key, key)
                materials.append(key)
    seen: set[str] = set()
    return [m for m in materials if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]


def generate_advice_for_materials(materials: list[str]) -> str:
    """Generate formatted advice markdown for an explicit list of material keys."""
    if not materials:
        return ""
    capped = materials[:_MAX_MATERIALS]
    sections: list[str] = ["## Architectural Material Advice\n"]
    for mat in capped:
        live_gwp = get_gwp(mat)
        sections.append(_format_material_advice(mat, live_gwp))
    return "\n".join(sections)


def generate_advice_table_data(
    materials: list[str],
    standard: str = DEFAULT_STANDARD,
    region: str = DEFAULT_REGION,
) -> list[dict]:
    """Return a list of property dicts suitable for table display."""
    standard_key = FIRE_STANDARDS.get(standard, "EN_13501")
    rows: list[dict] = []
    for mat in materials[:_MAX_MATERIALS]:
        live_gwp = get_gwp_regional(mat, region)
        static = _lookup_static(mat)
        label = mat.replace("_", " ").title()

        if live_gwp is not None:
            gwp_display = live_gwp
            gwp_source = "Okobaudat live"
        elif static.get("gwp_fallback_kgco2e") is not None:
            gwp_display = static["gwp_fallback_kgco2e"]
            gwp_source = "reference"
        else:
            gwp_display = None
            gwp_source = "—"

        alt_key, alt_reason = _choose_best_alternative(mat, region, standard_key)
        alt_label = alt_key.replace("_", " ").title() if alt_key else "—"

        rows.append({
            "Material": label,
            "Carbon Footprint": gwp_display,
            "Unit": static.get("gwp_unit", "kgCO2e/m²") if static else "—",
            "GWP Source": gwp_source,
            "Fire Rating": _resolve_fire_rating(static, standard_key) if static else "—",
            "Lifespan (yrs)": static.get("life_cycle_years", "—") if static else "—",
            "Alternative": alt_label,
            "Recommendation": alt_reason or "—",
            "In DB": "yes" if static else "no",
        })
    return rows


def advice_rows_to_csv(rows: list[dict], file_path: pathlib.Path | str) -> pathlib.Path:
    """Write architectural advice rows to a CSV file and return the path."""
    path = pathlib.Path(file_path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = [
        "Material",
        "Carbon Footprint",
        "Unit",
        "GWP Source",
        "Fire Rating",
        "Lifespan (yrs)",
        "Alternative",
        "Recommendation",
        "In DB",
    ]
    with path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return path


def generate_advice_table_csv(
    materials: list[str],
    file_path: pathlib.Path | str,
    standard: str = DEFAULT_STANDARD,
    region: str = DEFAULT_REGION,
) -> pathlib.Path:
    """Generate architectural advice table data and export it to a CSV file."""
    rows = generate_advice_table_data(materials, standard, region)
    return advice_rows_to_csv(rows, file_path)


def build_architectural_advice_node():
    def _architectural_advice_node(state: dict[str, Any]) -> dict[str, Any]:
        print("\n[architectural_advice] Gathering material properties...")

        materials = _extract_materials(state)
        if not materials:
            return {"architectural_advice": None}

        capped = materials[:_MAX_MATERIALS]
        if len(materials) > _MAX_MATERIALS:
            print(f"[architectural_advice] {len(materials)} materials found — capped at {_MAX_MATERIALS}")

        sections: list[str] = ["## Architectural Material Advice\n"]
        for mat in capped:
            live_gwp = get_gwp(mat)
            sections.append(_format_material_advice(mat, live_gwp))

        advice_text = "\n".join(sections)
        print(f"[architectural_advice] Advice generated for {len(capped)} material(s).")
        return {"architectural_advice": advice_text}

    return _architectural_advice_node
