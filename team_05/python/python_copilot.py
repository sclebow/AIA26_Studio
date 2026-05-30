"""
Python Copilot Logic
Answers cost questions using the loaded layout JSON + cost_rates.json rates.
Routing order: most-specific match first, generic last.
"""
import copy
import json
import os
import re

# ── cost rate table (mirrors cost_rates.json) ─────────────────────────────────
# Loaded once at import time; falls back to inline defaults if file not found.

_RATES_PATH = os.path.join(os.path.dirname(__file__), "..", "gh", "cost_rates.json")

def _load_rates() -> dict:
    try:
        with open(_RATES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_COST_RATES = _load_rates()

def _floor_rate(material: str) -> float:
    """Return AED/m² for a given floor finish material name."""
    by_mat = (_COST_RATES
              .get("room_finishes", {})
              .get("floor_finish", {})
              .get("by_material", {}))
    key = _normalise(material)
    for k, v in by_mat.items():
        if _normalise(k) == key or key in _normalise(k):
            return float(v)
    return float(_COST_RATES.get("room_finishes", {}).get("floor_finish", {}).get("default", 180))

def _wall_rate(material: str) -> float:
    by_mat = (_COST_RATES
              .get("room_finishes", {})
              .get("wall_finish", {})
              .get("by_material", {}))
    key = _normalise(material)
    for k, v in by_mat.items():
        if _normalise(k) == key or key in _normalise(k):
            return float(v)
    return float(_COST_RATES.get("room_finishes", {}).get("wall_finish", {}).get("default", 90))

def _ceiling_rate(material: str) -> float:
    by_mat = (_COST_RATES
              .get("room_finishes", {})
              .get("ceiling_material", {})
              .get("by_material", {}))
    key = _normalise(material)
    for k, v in by_mat.items():
        if _normalise(k) == key or key in _normalise(k):
            return float(v)
    return float(_COST_RATES.get("room_finishes", {}).get("ceiling_material", {}).get("default", 130))

def _normalise(s: str) -> str:
    return re.sub(r"[\s\-_]+", "_", s.strip().lower())


def _slab_rate_per_m3(material: str) -> float:
    """Return USD/m³ for a given slab material."""
    by_mat = (_COST_RATES
              .get("room_finishes", {})
              .get("slab_material", {})
              .get("by_material", {}))
    key = _normalise(material)
    for k, v in by_mat.items():
        if _normalise(k) == key or key in _normalise(k):
            return float(v)
    return float(_COST_RATES.get("room_finishes", {}).get("slab_material", {}).get("default", 435))


# ── entry point ───────────────────────────────────────────────────────────────

def process_with_copilot(context: dict) -> str:
    user_input: str = context.get("user_input", "")
    layout_json: str = context.get("layout_json", "")

    if not layout_json:
        return (
            "No layout is loaded yet. Please upload a layout JSON file so I can "
            "analyse costs. Use --file in the CLI or 'Upload layout JSON' in the GUI."
        )
    try:
        layout = json.loads(layout_json)
    except json.JSONDecodeError:
        return "Could not parse the layout data."

    try:
        return _route(user_input, layout)
    except Exception as exc:
        return f"⚠️ Copilot error: {exc}"


# ── router — most-specific first ─────────────────────────────────────────────

def _route(user_input: str, layout: dict) -> str:
    lower = user_input.lower()
    rooms = layout.get("rooms", [])
    currency = layout.get("project", {}).get("currency", "")

    if not rooms:
        return "The layout contains no rooms."

    # 1a. slab cost (volume-based: area × thickness × rate/m³)
    if _mentions_slab_change(lower):
        return _recalculate_with_slab(user_input, lower, rooms, currency)

    # 1b. finish-change calculation (e.g. "bedroom 3 floor finish marble")
    if _mentions_finish(lower):
        return _recalculate_with_finish(user_input, lower, rooms, currency)

    # 2. cost-reduction advice
    if any(k in lower for k in ("reduce", "save", "cut", "lower", "cheaper", "how to")):
        return _cost_reduction_advice(user_input, rooms, currency)

    # 3. room comparison / ranking
    if any(k in lower for k in ("compare", " vs ", "versus")):
        return _compare_rooms(user_input, rooms, currency)

    if any(k in lower for k in ("rank", "ranking", "ranked")):
        return _rank_all_rooms(rooms, currency)

    # 3b. best value / recommendation
    if any(k in lower for k in ("best value", "best plan", "best option",
                                 "choose", "recommend", "which plan",
                                 "which is best", "which option")):
        return _best_value_recommendation(rooms, currency)

    # 4. rate-per-m² table
    if any(k in lower for k in ("rate", "per m", "per square", "cost per")):
        return _rate_comparison(rooms, currency)

    # 5. project-level total — only when NO room is named
    if "total" in lower and not _find_room(lower, rooms):
        return _total_cost(rooms, currency, layout)

    # 6. cheapest / most expensive
    if any(k in lower for k in ("cheap", "lowest", "minimum", "least expensive")):
        return _cheapest_room(rooms, currency)
    if any(k in lower for k in ("expensive", "highest", "maximum", "most")):
        return _most_expensive_room(rooms, currency)

    # 7. named room detail (also handles "total cost of <room>")
    match = _find_room(lower, rooms)
    if match:
        return _room_detail(match, currency)

    # 8. fallback: project total
    return _total_cost(rooms, currency, layout)


# ── finish detection helpers ──────────────────────────────────────────────────

_FINISH_MATERIALS = [
    "marble", "granite", "porcelain", "ceramic", "natural stone",
    "engineered wood", "solid wood", "laminate", "vinyl", "epoxy",
    "polished concrete", "carpet", "terrazzo",
    "paint", "wallpaper", "wood panel", "veneer", "stucco",
    "gypsum board", "acoustic tile", "metal panel", "wood slat",
]
_FINISH_SURFACES = ["floor", "wall", "ceiling"]

_SLAB_MATERIALS = [
    "rc_solid", "rc solid", "rc_waffle", "rc waffle",
    "rc_ribbed", "rc ribbed", "post_tensioned", "post tensioned",
    "hollow_core", "hollow core", "composite_steel", "composite steel",
    "precast", "timber_joist", "timber joist",
]

def _mentions_finish(lower: str) -> bool:
    has_surface = any(s in lower for s in _FINISH_SURFACES)
    has_material = any(m in lower for m in _FINISH_MATERIALS)
    return has_surface and has_material


def _find_room(lower: str, rooms: list) -> dict | None:
    for r in rooms:
        name = r.get("name", "").lower()
        rid = r.get("id", "").lower()
        if name in lower or rid.replace("_", " ") in lower or rid in lower:
            return r
        # normalised token match: "bed room 3" -> "bed_room_3"; "bedroom_3" -> "bedroom_3"
        name_norm = _normalise(name)
        query_norm = _normalise(lower)
        if name_norm in query_norm:
            return r
        # space-stripped match: handles "bed room 3" vs "bedroom 3"
        name_nospace = re.sub(r"\s+", "", name)
        query_nospace = re.sub(r"\s+", "", lower)
        if name_nospace and name_nospace in query_nospace:
            return r
    return None


def _detect_material(lower: str) -> tuple[str, str] | tuple[None, None]:
    """Return (surface, material) e.g. ('floor', 'marble') or (None, None)."""
    surface = next((s for s in _FINISH_SURFACES if s in lower), None)
    material = next((m for m in _FINISH_MATERIALS if m in lower), None)
    return surface, material


def _mentions_slab_change(lower: str) -> bool:
    """True if the query references a structural slab material (with or without 'slab' keyword)."""
    # Check for explicit material mention
    if any(_normalise(m) in _normalise(lower) for m in _SLAB_MATERIALS):
        return True
    # Also detect "slab" + thickness/depth keywords
    if "slab" in lower and any(kw in lower for kw in ["thickness", "depth", "thick", "mm", " m "]):
        return True
    return False


def _detect_thickness(lower: str) -> float | None:
    """Extract slab thickness in meters. Accepts '0.1 m', '100mm', '0.2m'."""
    m = re.search(r"(\d+\.?\d*)\s*(mm|m)\b", lower)
    if m:
        val = float(m.group(1))
        if m.group(2) == "mm":
            val /= 1000
        if 0.05 <= val <= 1.0:  # sanity: 50 mm – 1000 mm
            return val
    return None


def _recalculate_with_slab(user_input: str, lower: str, rooms: list, currency: str) -> str:
    room = _find_room(lower, rooms)
    if not room:
        return (
            "I could see you want a slab calculation, but I couldn't identify the room. "
            "Please mention the room name, e.g. 'Living Room slab rc_solid 0.1 m'."
        )

    mat_key = next(
        (m for m in _SLAB_MATERIALS if _normalise(m) in _normalise(lower)), "default"
    )
    thickness = _detect_thickness(lower) or 0.10  # default 100 mm

    area      = room.get("area_m2", 0)
    old_total = room.get("total_cost", 0) or 0
    breakdown = room.get("_rate_breakdown", {})
    name      = room.get("name", "")
    cur       = currency or "USD"

    rate_m3        = _slab_rate_per_m3(mat_key)
    new_slab_rate  = thickness * rate_m3          # USD/m²
    old_slab_rate  = breakdown.get("slab", 0.0)   # USD/m² already in layout

    slab_cost  = new_slab_rate * area
    delta_rate = new_slab_rate - old_slab_rate
    delta_cost = delta_rate * area
    new_total  = old_total + delta_cost

    sign      = "+" if delta_cost >= 0 else ""
    direction = "increase" if delta_cost >= 0 else "saving"
    mat_label = mat_key.replace("_", " ").capitalize()

    lines = [
        f"**{name} — Slab: {mat_label} @ {thickness * 1000:.0f} mm**",
        "",
        f"| | Slab rate ({cur}/m²) | Slab cost ({cur}) | Room total ({cur}) |",
        "|---|---|---|---|",
        f"| Current slab ({breakdown.get('slab-material', 'existing')}) "
        f"| {old_slab_rate:,.1f} | {old_slab_rate * area:,.0f} | {old_total:,.0f} |",
        f"| **{mat_label} @ {thickness * 1000:.0f} mm** "
        f"| **{new_slab_rate:,.1f}** | **{slab_cost:,.0f}** | **{new_total:,.0f}** |",
        "",
        f"Volume: {area:.1f} m² × {thickness:.3f} m = **{area * thickness:.2f} m³** "
        f"@ {rate_m3:,.0f} {cur}/m³",
        f"**{direction.capitalize()}: {sign}{delta_cost:,.0f} {cur}** "
        f"(Δ {sign}{delta_rate:,.1f} {cur}/m² × {area:.1f} m²)",
    ]

    if old_total > 0 and delta_cost != 0:
        pct = delta_cost / old_total * 100
        lines.append(
            f"\nThis changes the room total by **{abs(pct):.1f}%**."
        )

    return "\n".join(lines)


# ── finish-change recalculation ───────────────────────────────────────────────

def _recalculate_with_finish(user_input: str, lower: str, rooms: list, currency: str) -> str:
    room = _find_room(lower, rooms)
    if not room:
        return (
            "I could see you want to change a finish, but I couldn't identify which room. "
            "Please mention the room name, e.g. 'bedroom 3 floor finish marble'."
        )

    surface, material = _detect_material(lower)
    if not material:
        return f"I recognised the room **{room.get('name')}** but couldn't identify the finish material."
    if not surface:
        return f"I recognised **{material}** but couldn't tell which surface (floor/wall/ceiling)."

    area = room.get("area_m2", 0)
    old_total = room.get("total_cost", 0) or 0
    breakdown = room.get("_rate_breakdown", {})
    name = room.get("name", "")
    cur = currency or "AED"

    if surface == "floor":
        old_rate_surface = breakdown.get("floor", _floor_rate("default"))
        new_rate_surface  = _floor_rate(material)
    elif surface == "wall":
        old_rate_surface = breakdown.get("wall", _wall_rate("default"))
        new_rate_surface  = _wall_rate(material)
    elif surface == "ceiling":
        old_rate_surface = breakdown.get("ceiling", _ceiling_rate("default"))
        new_rate_surface  = _ceiling_rate(material)
    else:
        return "Slab-material recalculation is not yet supported. Ask about floor/wall/ceiling."

    delta_rate = new_rate_surface - old_rate_surface
    delta_cost = delta_rate * area
    new_total  = old_total + delta_cost

    sign = "+" if delta_cost >= 0 else ""
    direction = "increase" if delta_cost >= 0 else "saving"

    lines = [
        f"**{name} - recalculated with {material} {surface}:**",
        "",
        f"| | Rate ({cur}/m2) | Room cost ({cur}) |",
        f"|---|---|---|",
        f"| Current ({room.get(surface + '-finish', 'existing')}) "
        f"| {old_rate_surface:,.0f} | {old_total:,.0f} |",
        f"| **{material.capitalize()} {surface}** "
        f"| **{new_rate_surface:,.0f}** | **{new_total:,.0f}** |",
        "",
        f"**{direction.capitalize()}: {sign}{delta_cost:,.0f} {cur}** "
        f"({sign}{delta_rate:,.0f} {cur}/m2 x {area:.1f} m2)",
    ]

    if old_total > 0:
        pct = delta_cost / old_total * 100
        lines.append(
            f"\nThis is a {abs(pct):.1f}% {'increase' if delta_cost >= 0 else 'decrease'} "
            f"in the cost of this room."
        )

    return "\n".join(lines)


# ── answer generators ─────────────────────────────────────────────────────────

def _total_cost(rooms: list, currency: str, layout: dict) -> str:
    # prefer pre-computed totals from GH JSON
    totals = layout.get("totals", {})
    room_total = totals.get("rooms", sum(r.get("total_cost", 0) for r in rooms))
    door_total = totals.get("doors", 0)
    win_total  = totals.get("windows", 0)
    col_total  = totals.get("columns", 0)
    grand      = totals.get("grand", room_total + door_total + win_total + col_total)

    lines = ["**Total project cost breakdown:**",
             f"  Room construction : {room_total:>12,.0f} {currency}"]
    if door_total:
        lines.append(f"  Doors             : {door_total:>12,.0f} {currency}")
    if win_total:
        lines.append(f"  Windows           : {win_total:>12,.0f} {currency}")
    if col_total:
        lines.append(f"  Columns           : {col_total:>12,.0f} {currency}")
    if grand != room_total:
        lines.append(f"  **Grand total**   : {grand:>12,.0f} {currency}")
    return "\n".join(lines)


def _room_detail(r: dict, currency: str) -> str:
    breakdown = r.get("_rate_breakdown", {})
    bd_lines = ""
    if breakdown:
        bd_lines = (
            f"\n  Floor   : {breakdown.get('floor', 0):>6,.0f} {currency}/m²"
            f"\n  Wall    : {breakdown.get('wall', 0):>6,.0f} {currency}/m²"
            f"\n  Ceiling : {breakdown.get('ceiling', 0):>6,.0f} {currency}/m²"
            f"\n  Slab    : {breakdown.get('slab', 0):>6,.0f} {currency}/m²"
        )
    return (
        f"**{r.get('name', '')}**\n"
        f"  Category  : {r.get('category', r.get('room-name', ''))}\n"
        f"  Area      : {r.get('area_m2', 0):.1f} m²\n"
        f"  Rate      : {r.get('rate_per_m2', 0):,.0f} {currency}/m²"
        f"{bd_lines}\n"
        f"  **Total   : {r.get('total_cost', 0):,.0f} {currency}**"
    )


def _cheapest_room(rooms: list, currency: str) -> str:
    r = min(rooms, key=lambda x: x.get("total_cost", float("inf")))
    return (
        f"The cheapest room is **{r['name']}** at "
        f"{r.get('total_cost', 0):,.0f} {currency} "
        f"({r.get('area_m2', 0):.1f} m² @ {r.get('rate_per_m2', 0):,.0f} {currency}/m²)."
    )


def _most_expensive_room(rooms: list, currency: str) -> str:
    r = max(rooms, key=lambda x: x.get("total_cost", 0))
    return (
        f"The most expensive room is **{r['name']}** at "
        f"{r.get('total_cost', 0):,.0f} {currency} "
        f"({r.get('area_m2', 0):.1f} m² @ {r.get('rate_per_m2', 0):,.0f} {currency}/m²)."
    )


def _rate_comparison(rooms: list, currency: str) -> str:
    sorted_rooms = sorted(rooms, key=lambda x: x.get("rate_per_m2", 0), reverse=True)
    lines = [f"**Cost rates by room** ({currency}/m²):"]
    for r in sorted_rooms:
        lines.append(
            f"  {r.get('name', ''):<22} {r.get('rate_per_m2', 0):>8,.0f} {currency}/m²"
        )
    return "\n".join(lines)


def _compare_rooms(user_input: str, rooms: list, currency: str) -> str:
    lower = user_input.lower()
    # show all rooms when "all", "rank", or a count like "5" appears
    show_all = "all" in lower or "rank" in lower or any(str(n) in lower for n in range(3, len(rooms) + 1))

    matched = [r for r in rooms if
               r.get("name", "").lower() in lower
               or _normalise(r.get("name", "")) in _normalise(lower)
               or r.get("id", "").lower() in lower]
    if len(matched) < 2:
        all_sorted = sorted(rooms, key=lambda x: x.get("total_cost", 0), reverse=True)
        matched = all_sorted if show_all else all_sorted[:2]

    if show_all or len(matched) > 2:
        return _rank_all_rooms(rooms, currency)

    lines = ["**Room cost comparison:**"]
    for r in matched:
        lines.append(
            f"  {r.get('name', ''):<22} "
            f"{r.get('area_m2', 0):>6.1f} m²  "
            f"{r.get('rate_per_m2', 0):>8,.0f} {currency}/m²  "
            f"= {r.get('total_cost', 0):>10,.0f} {currency}"
        )
    if len(matched) >= 2:
        delta = abs(matched[0].get("total_cost", 0) - matched[1].get("total_cost", 0))
        pct = delta / max(matched[1].get("total_cost", 1), 1) * 100
        lines.append(
            f"\n  **{matched[0].get('name')}** costs "
            f"{delta:,.0f} {currency} ({pct:.0f}%) more than "
            f"**{matched[1].get('name')}**."
        )
    return "\n".join(lines)


def _rank_all_rooms(rooms: list, currency: str) -> str:
    """Rank all rooms by total cost with cost/m² and estimated maintenance."""
    _MAINT_PCT = {"wet": 0.020, "bedroom": 0.012, "common": 0.010,
                  "circulation": 0.008, "service": 0.015}
    sorted_rooms = sorted(rooms, key=lambda x: x.get("total_cost", 0), reverse=True)
    cur = currency or "USD"

    lines = [f"**All rooms ranked by total cost** ({cur}):\n",
             f"| # | Room | Area m² | Rate {cur}/m² | Total {cur} | Est. annual maintenance |",
             "|---|------|---------|-------------|------------|------------------------|"]

    for i, r in enumerate(sorted_rooms, 1):
        area  = r.get("area_m2", 0)
        rate  = r.get("rate_per_m2", 0)
        total = r.get("total_cost", 0)
        cat   = r.get("category", "").lower()
        maint_pct = _MAINT_PCT.get(cat, 0.012)
        maint_yr  = total * maint_pct
        lines.append(
            f"| {i} | {r.get('name','')} | {area:.1f} | {rate:,.0f} "
            f"| **{total:,.0f}** | ~{maint_yr:,.0f} ({maint_pct*100:.1f}%/yr) |"
        )

    grand = sum(r.get("total_cost", 0) for r in rooms)
    total_maint = sum(r.get("total_cost", 0) *
                      _MAINT_PCT.get(r.get("category", "").lower(), 0.012)
                      for r in rooms)
    lines += [
        "",
        f"**Grand total construction: {grand:,.0f} {cur}**  "
        f"| Est. annual maintenance: ~{total_maint:,.0f} {cur}",
        "",
        "_Maintenance rates: wet areas 2%/yr | bedrooms 1.2%/yr | common 1%/yr | "
        "circulation 0.8%/yr | service 1.5%/yr (rule-of-thumb; adjust per BoQ)._",
    ]
    return "\n".join(lines)


def _best_value_recommendation(rooms: list, currency: str) -> str:
    """Recommend the best-value room/plan based on cost efficiency and flexibility."""
    cur = currency or "USD"
    sorted_by_rate = sorted(rooms, key=lambda x: x.get("rate_per_m2", 0))
    sorted_by_total = sorted(rooms, key=lambda x: x.get("total_cost", 0))

    # score: lower rate is better (value), larger area is more flexible
    max_area  = max(r.get("area_m2", 1) for r in rooms)
    max_total = max(r.get("total_cost", 1) for r in rooms)

    def value_score(r: dict) -> float:
        rate_norm  = 1 - r.get("rate_per_m2", 0) / max(r.get("rate_per_m2", 1) for r in rooms)
        area_norm  = r.get("area_m2", 0) / max_area
        cost_norm  = 1 - r.get("total_cost", 0) / max_total
        return rate_norm * 0.5 + area_norm * 0.3 + cost_norm * 0.2

    scored = sorted(rooms, key=value_score, reverse=True)
    best   = scored[0]
    runner = scored[1] if len(scored) > 1 else None

    cheapest_rate = sorted_by_rate[0]
    smallest_cost = sorted_by_total[0]

    lines = [
        "**Best-value recommendation:**\n",
        f"Based on cost per m2, usable area, and total budget:\n",
        f"**Top pick: {best.get('name')}**",
        f"  Area: {best.get('area_m2', 0):.1f} m2  |  "
        f"Rate: {best.get('rate_per_m2', 0):,.0f} {cur}/m2  |  "
        f"Total: {best.get('total_cost', 0):,.0f} {cur}",
        f"  Category: {best.get('category', '-')}  |  "
        f"Flexibility: {'high (large area)' if best.get('area_m2', 0) >= 0.6 * max_area else 'moderate'}",
    ]
    if runner:
        lines += [
            "",
            f"**Runner-up: {runner.get('name')}**",
            f"  Area: {runner.get('area_m2', 0):.1f} m2  |  "
            f"Rate: {runner.get('rate_per_m2', 0):,.0f} {cur}/m2  |  "
            f"Total: {runner.get('total_cost', 0):,.0f} {cur}",
        ]
    lines += [
        "",
        f"**Lowest rate/m2:** {cheapest_rate.get('name')} "
        f"@ {cheapest_rate.get('rate_per_m2', 0):,.0f} {cur}/m2 "
        f"(best finish economy)",
        f"**Lowest total cost:** {smallest_cost.get('name')} "
        f"@ {smallest_cost.get('total_cost', 0):,.0f} {cur} "
        f"(smallest budget impact)",
        "",
        "_Scoring weights: rate/m2 50% + area 30% + absolute cost 20%._",
        "_For long-term flexibility, prefer larger-area spaces -- easier to subdivide or repurpose._",
    ]
    return "\n".join(lines)


def _cost_reduction_advice(user_input: str, rooms: list, currency: str) -> str:
    lower = user_input.lower()
    target = _find_room(lower, rooms) or max(rooms, key=lambda x: x.get("total_cost", 0))
    name = target.get("name", "this room")
    cost = target.get("total_cost", 0)
    cat  = target.get("category", "")

    advice = [f"**Cost reduction options for {name}** ({cost:,.0f} {currency}):"]
    if cat == "wet":
        advice += [
            "  • Mid-range sanitary ware instead of premium (saves ~15–20%)",
            "  • Reduce tile area with feature panels rather than full-coverage",
            "  • Group wet rooms back-to-back to share plumbing runs",
        ]
    elif cat == "bedroom":
        advice += [
            "  • Engineered wood flooring instead of solid timber (saves ~10%)",
            "  • Reduce ceiling height to 2.7 m (saves formwork cost)",
            "  • Simplify built-in joinery or use flat-pack alternatives",
        ]
    elif cat in ("common", ""):
        advice += [
            "  • Open-plan merge with adjacent space to reduce partition costs",
            "  • Polished concrete floor as a cost-effective finish",
            "  • Improve insulation to reduce air-conditioning zone size",
        ]
    else:
        advice += [
            f"  • Reduce finish specification (current rate: {target.get('rate_per_m2', 0):,.0f} {currency}/m²)",
            f"  • Reduce area by ~10% → saves ~{cost * 0.1:,.0f} {currency}",
        ]
    advice.append(
        f"\n  A 10% rate reduction → saves **{cost * 0.10:,.0f} {currency}**."
    )
    return "\n".join(advice)


# =============================================================================
# Layout mutation — apply finish change and recompute heatmap colors
# =============================================================================

def apply_finish_to_layout(user_input: str, layout: dict) -> dict | None:
    """
    If user_input is a finish-change request, return a deep copy of the layout
    with the affected room's cost updated and all heatmap colors recomputed.
    Returns None if no finish change was detected or room not found.
    """
    lower = user_input.lower()

    # slab change path
    if _mentions_slab_change(lower):
        rooms = layout.get("rooms", [])
        room = _find_room(lower, rooms)
        if not room:
            return None
        mat_key   = next((m for m in _SLAB_MATERIALS if _normalise(m) in _normalise(lower)), "default")
        thickness = _detect_thickness(lower) or 0.10
        area      = room.get("area_m2", 0)
        breakdown = room.get("_rate_breakdown", {})
        old_rate  = breakdown.get("slab", 0.0)
        new_rate  = thickness * _slab_rate_per_m3(mat_key)
        delta_cost = (new_rate - old_rate) * area
        if delta_cost == 0:
            return None
        updated = copy.deepcopy(layout)
        for r in updated.get("rooms", []):
            if r.get("id") == room.get("id"):
                r["total_cost"] = round(r.get("total_cost", 0) + delta_cost, 2)
                r["rate_per_m2"] = round(r.get("rate_per_m2", 0) + (new_rate - old_rate), 2)
                if "_rate_breakdown" in r:
                    r["_rate_breakdown"]["slab"] = new_rate
                r["slab-material"] = mat_key
                break
        _recompute_totals(updated)
        _recompute_heatmap(updated)
        return updated

    if not _mentions_finish(lower):
        return None

    rooms = layout.get("rooms", [])
    room = _find_room(lower, rooms)
    if not room:
        return None

    surface, material = _detect_material(lower)
    if not surface or not material:
        return None

    area = room.get("area_m2", 0)
    breakdown = room.get("_rate_breakdown", {})

    if surface == "floor":
        old_rate = breakdown.get("floor", _floor_rate("default"))
        new_rate = _floor_rate(material)
    elif surface == "wall":
        old_rate = breakdown.get("wall", _wall_rate("default"))
        new_rate = _wall_rate(material)
    elif surface == "ceiling":
        old_rate = breakdown.get("ceiling", _ceiling_rate("default"))
        new_rate = _ceiling_rate(material)
    else:
        return None

    delta_cost = (new_rate - old_rate) * area
    if delta_cost == 0:
        return None

    # deep copy so we never mutate the original
    updated = copy.deepcopy(layout)
    updated_rooms = updated.get("rooms", [])

    for r in updated_rooms:
        if r.get("id") == room.get("id"):
            r["total_cost"] = round(r.get("total_cost", 0) + delta_cost, 2)
            r["rate_per_m2"] = round(r.get("rate_per_m2", 0) + (new_rate - old_rate), 2)
            # update breakdown if present
            if "_rate_breakdown" in r and surface in r["_rate_breakdown"]:
                r["_rate_breakdown"][surface] = new_rate
            # record what finish was applied
            r[f"{surface}-finish"] = material
            break

    # recompute totals
    _recompute_totals(updated)
    # recompute heatmap colors for all rooms
    _recompute_heatmap(updated)

    return updated


def _recompute_totals(layout: dict) -> None:
    """Update layout['totals'] from current room/opening costs."""
    rooms    = layout.get("rooms", [])
    openings = layout.get("openings", [])
    columns  = layout.get("columns", [])

    room_total = sum(r.get("total_cost", 0) for r in rooms)
    door_total = sum(o.get("cost", 0) for o in openings if (o.get("type") or "").lower() == "door")
    win_total  = sum(o.get("cost", 0) for o in openings if (o.get("type") or "").lower() == "window")
    col_total  = sum(c.get("cost", 0) for c in columns)
    grand      = room_total + door_total + win_total + col_total

    layout["totals"] = {
        "currency": layout.get("project", {}).get("currency", "AED"),
        "rooms":    round(room_total, 2),
        "doors":    round(door_total, 2),
        "windows":  round(win_total, 2),
        "columns":  round(col_total, 2),
        "grand":    round(grand, 2),
    }


def _recompute_heatmap(layout: dict) -> None:
    """Recompute heat_t and color_hex/color_rgb for all rooms using the layout ramp."""
    rooms = layout.get("rooms", [])
    if not rooms:
        return

    costs = [r.get("total_cost", 0) for r in rooms]
    mn, mx = min(costs), max(costs)
    span = (mx - mn) or 1

    # use ramp stops from the JSON (or fall back to built-in warm ramp)
    ramp_stops = (layout.get("heatmap", {}).get("ramps", {}).get("rooms") or [
        {"t": 0.00, "hex": "#FFF5DC"},
        {"t": 0.25, "hex": "#FED976"},
        {"t": 0.50, "hex": "#FEB24C"},
        {"t": 0.75, "hex": "#F06913"},
        {"t": 1.00, "hex": "#BD0026"},
    ])

    for r in rooms:
        t = (r.get("total_cost", mn) - mn) / span
        t = max(0.0, min(1.0, t))
        r["heat_t"] = round(t, 4)
        hex_color = _ramp_hex(ramp_stops, t)
        r["color_hex"] = hex_color
        r["color_rgb"] = _hex_to_rgb(hex_color)

    # update ranges in heatmap block
    if "heatmap" not in layout:
        layout["heatmap"] = {}
    if "ranges" not in layout["heatmap"]:
        layout["heatmap"]["ranges"] = {}
    layout["heatmap"]["ranges"]["rooms"] = {"min": round(mn, 2), "max": round(mx, 2)}


def _ramp_hex(stops: list[dict], t: float) -> str:
    """Interpolate a hex color from an ordered list of {t, hex} stops."""
    if not stops:
        return "#FEB24C"
    if t <= stops[0]["t"]:
        return stops[0]["hex"]
    if t >= stops[-1]["t"]:
        return stops[-1]["hex"]
    for i in range(len(stops) - 1):
        lo, hi = stops[i], stops[i + 1]
        if lo["t"] <= t <= hi["t"]:
            f = (t - lo["t"]) / ((hi["t"] - lo["t"]) or 1)
            r0, g0, b0 = _hex_to_rgb(lo["hex"])
            r1, g1, b1 = _hex_to_rgb(hi["hex"])
            r = int(r0 + f * (r1 - r0))
            g = int(g0 + f * (g1 - g0))
            b = int(b0 + f * (b1 - b0))
            return f"#{r:02X}{g:02X}{b:02X}"
    return stops[-1]["hex"]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 245, 220)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
