"""
Client DNA — analyse past project budgets (CSV) to learn client spending habits.

Public API:
  parse_budget_csv(file_like)        → list[dict]          one CSV → normalised rooms
  analyze_profiles(datasets)         → profile dict         aggregate stats
  generate_summary(profile)          → markdown string      human-readable habits
  propose_template(profile, layout)  → template dict        per-room suggestions
  apply_template(template, layout)   → updated layout copy  mutates rates + finishes
"""
import copy
import re
from collections import Counter, defaultdict

import pandas as pd


# ── column name aliases ────────────────────────────────────────────────────────
_COL_ALIASES: dict[str, list[str]] = {
    "room":         ["room", "room_name", "name", "space", "room name"],
    "category":     ["category", "type", "room_type", "room type"],
    "area":         ["area", "area_m2", "area (m2)", "area(m2)", "size", "sqm", "m2"],
    "cost":         ["cost", "total_cost", "total", "budget", "amount",
                     "cost ($)", "cost (aed)", "cost (usd)", "cost (eur)", "construction cost"],
    "rate":         ["rate", "rate_per_m2", "rate/m2", "rate ($/m2)", "rate per m2", "rate per sqm"],
    "floor_finish": ["floor_finish", "floor finish", "floor", "floor material", "flooring"],
    "wall_finish":  ["wall_finish", "wall finish", "wall", "wall material", "walls"],
    "ceiling":      ["ceiling", "ceiling_material", "ceiling finish", "ceiling material"],
}

# ── category normalisation ─────────────────────────────────────────────────────
_CAT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("bedroom",     ["bedroom", "bed room", "master", "suite", "guest room"]),
    ("bathroom",    ["bathroom", "toilet", "wc", "wet", "bath", "shower", "ensuite", "laundry"]),
    ("kitchen",     ["kitchen", "cooking", "pantry"]),
    ("living",      ["living", "lounge", "reception", "family room", "sitting"]),
    ("dining",      ["dining", "dinner"]),
    ("circulation", ["corridor", "hallway", "foyer", "entry", "lobby", "stairs", "lift"]),
    ("service",     ["service", "utility", "storage", "store", "maid", "mechanical"]),
    ("office",      ["office", "study", "work"]),
    ("common",      ["common", "open"]),
]


def _normalise_category(raw: str) -> str:
    low = raw.lower().strip()
    for cat, keywords in _CAT_KEYWORDS:
        if any(kw in low for kw in keywords):
            return cat
    return low or "other"


def _find_col(df: pd.DataFrame, field: str) -> str | None:
    aliases = _COL_ALIASES.get(field, [field])
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in cols_lower:
            return cols_lower[alias.lower()]
    return None


def _safe_float(val) -> float:
    if val is None:
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(val))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


# ── public API ─────────────────────────────────────────────────────────────────

def parse_budget_csv(file_like) -> list[dict]:
    """Parse a budget CSV and return a list of normalised room dicts."""
    try:
        df = pd.read_csv(file_like)
    except Exception:
        return []

    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(how="all")

    room_col     = _find_col(df, "room")
    category_col = _find_col(df, "category")
    area_col     = _find_col(df, "area")
    cost_col     = _find_col(df, "cost")
    rate_col     = _find_col(df, "rate")
    floor_col    = _find_col(df, "floor_finish")
    wall_col     = _find_col(df, "wall_finish")
    ceiling_col  = _find_col(df, "ceiling")

    def _finish(row, col):
        if col and pd.notna(row.get(col)):
            v = str(row[col]).strip().lower()
            return v if v not in ("nan", "none", "") else ""
        return ""

    rows = []
    for i, row in df.iterrows():
        name = str(row[room_col]).strip() if room_col else f"Room {i + 1}"
        if not name or name.lower() in ("nan", "none", ""):
            continue

        raw_cat  = str(row[category_col]).strip() if category_col else name
        category = _normalise_category(raw_cat)
        area     = _safe_float(row[area_col]) if area_col else 0.0
        cost     = _safe_float(row[cost_col]) if cost_col else 0.0
        rate     = _safe_float(row[rate_col]) if rate_col else (cost / area if area > 0 else 0.0)

        rows.append({
            "name":         name,
            "category":     category,
            "area_m2":      area,
            "total_cost":   cost,
            "rate_per_m2":  rate,
            "floor_finish": _finish(row, floor_col),
            "wall_finish":  _finish(row, wall_col),
            "ceiling":      _finish(row, ceiling_col),
        })

    return rows


def analyze_profiles(datasets: list[list[dict]]) -> dict:
    """Aggregate multiple parsed CSVs into a client spending profile."""
    if not datasets:
        return {}

    cat_rates:    dict[str, list[float]] = defaultdict(list)
    cat_costs:    dict[str, list[float]] = defaultdict(list)
    cat_areas:    dict[str, list[float]] = defaultdict(list)
    cat_floors:   dict[str, list[str]]   = defaultdict(list)
    cat_walls:    dict[str, list[str]]   = defaultdict(list)
    cat_ceilings: dict[str, list[str]]   = defaultdict(list)
    project_totals: list[float] = []

    for dataset in datasets:
        proj_total = sum(r["total_cost"] for r in dataset)
        project_totals.append(proj_total)
        for r in dataset:
            cat = r["category"]
            if r["rate_per_m2"] > 0:
                cat_rates[cat].append(r["rate_per_m2"])
            if r["total_cost"] > 0:
                cat_costs[cat].append(r["total_cost"])
            if r["area_m2"] > 0:
                cat_areas[cat].append(r["area_m2"])
            if r["floor_finish"]:
                cat_floors[cat].append(r["floor_finish"])
            if r["wall_finish"]:
                cat_walls[cat].append(r["wall_finish"])
            if r["ceiling"]:
                cat_ceilings[cat].append(r["ceiling"])

    avg_total = sum(project_totals) / len(project_totals) if project_totals else 0

    def _top(lst: list, n: int = 2) -> list[str]:
        return [x for x, _ in Counter(lst).most_common(n)] if lst else []

    categories: dict[str, dict] = {}
    for cat in set(cat_rates) | set(cat_costs):
        avg_rate = sum(cat_rates[cat]) / len(cat_rates[cat]) if cat_rates[cat] else 0.0
        avg_cost = sum(cat_costs[cat]) / len(cat_costs[cat]) if cat_costs[cat] else 0.0
        avg_area = sum(cat_areas[cat]) / len(cat_areas[cat]) if cat_areas[cat] else 0.0
        avg_pct  = (avg_cost / avg_total * 100) if avg_total > 0 else 0.0

        categories[cat] = {
            "avg_rate_per_m2":   round(avg_rate, 1),
            "avg_cost":          round(avg_cost, 0),
            "avg_area_m2":       round(avg_area, 1),
            "avg_budget_pct":    round(avg_pct, 1),
            "preferred_floor":   _top(cat_floors[cat]),
            "preferred_wall":    _top(cat_walls[cat]),
            "preferred_ceiling": _top(cat_ceilings[cat]),
            "sample_count":      len(cat_costs[cat]),
        }

    ranked = sorted(categories.items(), key=lambda kv: kv[1]["avg_cost"], reverse=True)

    return {
        "num_projects":      len(datasets),
        "avg_total_budget":  round(avg_total, 0),
        "project_totals":    [round(t, 0) for t in project_totals],
        "categories":        categories,
        "ranked_categories": [cat for cat, _ in ranked],
    }


def generate_summary(profile: dict) -> str:
    """Generate a human-readable markdown summary of the client spending profile."""
    if not profile:
        return "_No profile data available._"

    n      = profile.get("num_projects", 0)
    avg    = profile.get("avg_total_budget", 0)
    ranked = profile.get("ranked_categories", [])
    cats   = profile.get("categories", {})
    totals = profile.get("project_totals", [])

    lines = [
        f"**Client Spending Profile** _(based on {n} past project{'s' if n != 1 else ''})_",
        "",
        f"Average project budget: **{avg:,.0f}**",
    ]
    if len(totals) > 1:
        spread = max(totals) - min(totals)
        lines.append(
            f"Budget range: {min(totals):,.0f} – {max(totals):,.0f}  ·  spread: {spread:,.0f}"
        )

    if ranked:
        lines += ["", "**Where the money goes:**"]
        for cat in ranked[:6]:
            info   = cats.get(cat, {})
            pct    = info.get("avg_budget_pct", 0)
            rate   = info.get("avg_rate_per_m2", 0)
            floors = info.get("preferred_floor", [])
            bar    = "█" * max(1, int(pct / 4)) + "░" * max(0, 25 - int(pct / 4))
            finish = f"  ·  prefers _{', '.join(floors)}_" if floors else ""
            lines.append(
                f"  **{cat.capitalize()}** {bar} {pct:.0f}%  ·  {rate:,.0f}/m²{finish}"
            )

    patterns = []
    for cat, info in cats.items():
        rate = info.get("avg_rate_per_m2", 0)
        pct  = info.get("avg_budget_pct", 0)
        if cat == "bathroom" and rate > 900:
            patterns.append("invests in premium bathroom finishes")
        if cat == "bedroom" and pct > 30:
            patterns.append("allocates a high share of budget to bedrooms")
        if cat == "kitchen" and rate > 1000:
            patterns.append("prioritises high-spec kitchen finishes")
        if cat == "living" and pct > 25:
            patterns.append("places strong emphasis on living and common areas")

    if patterns:
        lines += ["", "**Key habits detected:**"]
        for p in patterns:
            lines.append(f"  • This client {p}")

    return "\n".join(lines)


def propose_template(profile: dict, layout: dict) -> dict:
    """
    Build a per-room spending template from client history.
    Returns a dict keyed by room id with suggested rates, costs, and finishes.
    """
    if not profile or not layout:
        return {}

    cats  = profile.get("categories", {})
    rooms = layout.get("rooms", [])
    template: dict[str, dict] = {}

    for room in rooms:
        raw_cat       = room.get("category", room.get("name", "other"))
        cat_norm      = _normalise_category(raw_cat)
        info          = cats.get(cat_norm, {})
        current_rate  = room.get("rate_per_m2", 0)
        suggested_rate = info.get("avg_rate_per_m2", current_rate)
        area          = room.get("area_m2", 0)
        current_cost  = room.get("total_cost", 0)
        suggested_cost = round(suggested_rate * area, 0) if area > 0 else current_cost

        template[room["id"]] = {
            "room_name":       room.get("name", ""),
            "category":        cat_norm,
            "current_rate":    current_rate,
            "suggested_rate":  round(suggested_rate, 1),
            "current_cost":    current_cost,
            "suggested_cost":  suggested_cost,
            "delta_cost":      round(suggested_cost - current_cost, 0),
            "preferred_floor": (info.get("preferred_floor") or [""])[0],
            "preferred_wall":  (info.get("preferred_wall")  or [""])[0],
            "data_source":     "client history" if info else "no history — kept as-is",
        }

    return template


def apply_template(template: dict, layout: dict) -> dict:
    """
    Apply the spending template to a layout.
    Returns a deep copy with updated room rates, costs, and finishes.
    """
    from python_copilot import _recompute_totals, _recompute_heatmap

    updated = copy.deepcopy(layout)
    for room in updated.get("rooms", []):
        rid = room.get("id")
        if rid not in template:
            continue
        t    = template[rid]
        area = room.get("area_m2", 0)
        room["rate_per_m2"] = t["suggested_rate"]
        room["total_cost"]  = round(t["suggested_rate"] * area, 2) if area > 0 else room["total_cost"]
        if t["preferred_floor"]:
            room["floor-finish"] = t["preferred_floor"]
        if t["preferred_wall"]:
            room["wall-finish"] = t["preferred_wall"]

    _recompute_totals(updated)
    _recompute_heatmap(updated)
    return updated
