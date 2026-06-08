"""
cost_flexibility.py — Three-Pillar Cost & Flexibility Node (V4)

Pillars:
  1. Financial Cost        — 8-component additive model (A–H)
  2. Administrative Burden — process checklist (P0–P9), critical-path duration
  3. Adaptability V4       — SC / CR / LPS / RF with V4 corrections applied

V4 changes from V3:
  Change 1 — Room-size normalization: classify_position() uses normalized thresholds
             derived from the outline bounding box, not absolute metre constants.
  Change 2 — CHANGE_MATERIAL SC: uses resulting element position score, not
             hardcoded material-based scores (7.0/5.0).
  Change 3 — Heritage ratchet: read from state["heritage_ratchet"] (persistent
             building flag); node sets it True when P4 triggers; never resets it.
  Change 4 — Weakest-link CR aggregation: CR_agg = mean × (1 − 0.5 × (mean−min)/10)
             for multi-element interventions; single-element unchanged.
  Change 5 — Labels-only user output: decimal scores are underscore-prefixed
             (internal, for comparison node ranking only); user-facing fields
             carry string labels and confidence levels.

Removed (V3 only — see FILE CHANGE LOG):
  _material_cost_usd, _single_element_flexibility, _aggregate_flexibility,
  _disruption_score, _spatial_penalty, _flex_label, _disruption_label
"""
from __future__ import annotations
import json
import math
from typing import Any

from nodes.evaluate import _parse_dim_mm, MATERIALS  # noqa: F401
from nodes.modify import STEEL_BEAM_PROPS, STEEL_COL_PROPS


# ── V4 MODIFIED: renamed fallback constants ───────────────────────────────────
# Previously _CORNER_DIST_M and _WALL_DIST_M (absolute metres).
# Now used only when outline is absent or malformed; classify_position() derives
# thresholds dynamically from the outline bounding box in all other cases.
_FALLBACK_CORNER_M        = 0.4
_FALLBACK_WALL_M          = 1.0
_FALLBACK_CHARACTERISTIC_M = 4.0   # 4 m small room reproduces V3 thresholds exactly


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Normalized position thresholds (Change 1) ─────────────────────────────────
_CORNER_FRAC = 0.10   # within 10 % of characteristic_dim from any vertex → corner
_WALL_FRAC   = 0.25   # within 25 % of characteristic_dim from any edge   → wall
                      # beyond WALL_FRAC from all edges                    → midroom

# ── Location cost indices (Barcelona = 1.0 baseline) ──────────────────────────
_LOCATION_INDEX: dict[str, float] = {
    "Barcelona":      1.00,
    "Spain":          0.85,
    "Monaco":         2.80,
    "Paris":          1.60,
    "London":         1.50,
    "New York":       1.80,
    "Cairo":          0.45,
    "Western Europe": 1.10,
    "Global":         0.90,
}

# ── Occupancy day-rate multipliers (applied to Component B labour) ─────────────
# HIGH reduced from 1.7 → 1.35: a 70 % uplift was overcounting coordination
# overhead already captured in Component E (occupancy coordination cost).
_OCC_DAY_RATE: dict[str, float] = {
    "VACANT":   1.0,
    "LOW":      1.15,
    "HIGH":     1.35,
    "CRITICAL": 2.0,
}

# ── Building context labour multipliers ───────────────────────────────────────
_CTX_LABOR: dict[str, float] = {
    "NEW":              0.85,
    "EXISTING_KNOWN":   1.00,
    "EXISTING_UNKNOWN": 1.35,
}

# ── Labour position multipliers (access difficulty) ───────────────────────────
# ADD operations: midroom requires hauling materials across the floor — 2.8× is
# appropriate. REMOVE operations have a separate (lower) table because the element
# is already in place; access is easier and staging needs are different.
_POS_LABOR: dict[str, float] = {
    "corner":  1.0,
    "wall":    1.4,
    "midroom": 1.9,
}
_POS_LABOR_REMOVE: dict[str, float] = {
    "corner":  1.0,
    "wall":    1.15,
    "midroom": 1.6,
}

# ── Heritage multipliers ───────────────────────────────────────────────────────
_HERITAGE_LABOR_MULT = 1.9
_HERITAGE_DEMO_MULT  = 1.8

# ── Base worker-days per intervention type ─────────────────────────────────────
# RCC baseline. Apply _MATERIAL_LABOR_FACTOR for steel/timber (see below).
_BASE_WORKER_DAYS: dict[str, float] = {
    "ADD_COL_CORNER":   4.0,
    "ADD_COL_WALL":     5.0,
    "ADD_COL_MIDROOM":  6.0,
    "ADD_BEAM":         3.0,
    "REMOVE_BEAM":      2.0,
    "REMOVE_COL":       4.0,
    "UPSIZE_SAME_MAT":  4.0,
    "CHANGE_MATERIAL": 10.0,
}

_BASE_DAY_RATE_EUR = 370.0   # EUR/day, 2-person Barcelona crew baseline

# ── Material labour factors (relative to RCC = 1.0) ──────────────────────────
# Steel and timber need no curing and less formwork — significantly faster.
_MATERIAL_LABOR_FACTOR: dict[str, float] = {
    "RCC":    1.0,
    "STEEL":  0.45,
    "TIMBER": 0.60,
}

# ── Material placement rates (EUR per m³) ─────────────────────────────────────
_MATERIAL_RATE_EUR: dict[str, float] = {
    "RCC":    620.0,
    "STEEL":  15_000.0,
    "TIMBER": 950.0,
}

# ── Mobilisation base costs (EUR) by occupancy ────────────────────────────────
_MOBILIZATION_EUR: dict[str, float] = {
    "VACANT":   320.0,
    "LOW":      480.0,
    "HIGH":     640.0,
    "CRITICAL": 1_200.0,
}

# ── Temp-works flat cost (EUR) — triggered for REMOVE_COL, CHANGE_MATERIAL ─────
_TEMP_WORKS_MID_EUR = 2_800.0

# ── Professional fees: % of non-material subtotal (A+B+C+D+E+G) ──────────────
_PROFESSIONAL_FEE_PCT = 0.12

# ── New-build rates (EUR/m³, coordinated project, Barcelona 2024) ─────────────
# Material supply = _MATERIAL_RATE_EUR. These are installation/erection rates only.
# Calibrated to CYPE 2024: GL24h timber at €869/m³ supply + €1,500/m³ erection.
_INSTALL_RATE_NEW_EUR: dict[str, float] = {
    "RCC":    800.0,    # formwork, rebar labour, pour, cure
    "STEEL":  3_000.0,  # crane, bolted connections, alignment
    "TIMBER": 1_500.0,  # frame erection, mechanical connections
}
_PERMIT_BASE_EUR   = 1_200.0   # ICIO 4 % PEM + tasa + visado, Barcelona
_FEE_PCT_NEW_BUILD = 0.18      # architect + structural engineer + safety coordinator

# ── Financial Cost score bands (EUR mid → score 1–10 → label) ────────────────
_FC_BANDS: list[tuple[float, int, str]] = [
    (2_000,        1, "Negligible"),
    (8_000,        3, "Low"),
    (25_000,       5, "Moderate"),
    (80_000,       7, "High"),
    (float("inf"), 10, "Very High"),
]

# ── Admin Burden: process durations (weeks, Barcelona baseline) ────────────────
# Tuple: (best_case, mid, worst_case)
_PROCESS_DURATION: dict[str, tuple[int, int, int]] = {
    "P0": (2,  6,  18),
    "P1": (8, 24,  72),
    "P2": (6, 10,  18),
    "P3": (3,  6,  14),
    "P4": (4, 12,  26),
    "P5": (2,  4,   8),
    "P6": (1,  2,   3),
    "P7": (3,  5,   9),
    "P8": (2,  4,   6),
    "P9": (1,  2,   4),
}

# ── Admin Burden: process costs (EUR mid, Barcelona baseline) ─────────────────
_PROCESS_COST_MID: dict[str, float] = {
    "P0": 4_000.0,
    "P1": 8_000.0,
    "P2": 2_500.0,
    "P3": 1_200.0,
    "P4": 6_000.0,
    "P5":   600.0,
    "P6":   800.0,
    "P7": 3_000.0,
    "P8": 1_200.0,
    "P9":   400.0,
}

_PROCESS_NAMES: dict[str, str] = {
    "P0": "P0 — Pre-authorization",
    "P1": "P1 — Regularization",
    "P2": "P2 — Municipal Building Permit",
    "P3": "P3 — Community Consent",
    "P4": "P4 — Heritage Authority Review",
    "P5": "P5 — Neighbor Notification",
    "P6": "P6 — Professional Registration",
    "P7": "P7 — Structural Survey",
    "P8": "P8 — Completion Certificate",
    "P9": "P9 — Occupancy Notification",
}

# ── Admin Burden score bands ───────────────────────────────────────────────────
_AB_BANDS: list[tuple[float, str]] = [
    (2.0,  "Negligible"),
    (4.0,  "Low"),
    (5.5,  "Moderate"),
    (7.5,  "Significant"),
    (10.1, "Complex"),
]

# ── Adaptability: Spatial Commitment (SC) scores ──────────────────────────────
_SC_ADD_COL: dict[str, float] = {
    "corner":  7.0,
    "wall":    4.5,
    "midroom": 2.0,
}
_SC_ADD_BEAM: dict[str, float] = {
    "perimeter": 7.5,
    "internal":  5.5,
}
_SC_REMOVE_COL: dict[str, float] = {
    "corner":  7.5,  # corner removal restores fewer options than midroom removal
    "wall":    8.5,
    "midroom": 9.5,
}
_SC_REMOVE_BEAM = 8.0
_SC_UPSIZE      = 6.0

# ── Adaptability: LPS sensitivity rates and position weights ──────────────────
_LPS_SENSITIVITY_RATE: dict[str, float] = {
    "corner":  0.8,
    "wall":    1.2,
    "midroom": 1.8,
}
_LPS_POSITION_WEIGHT: dict[str, float] = {
    "corner":  0.8,
    "wall":    1.2,
    "midroom": 2.0,
    "beam":    0.6,
}
_LPS_UPSIZE_RATE     = 0.9
_LPS_CHANGE_MAT_RATE = 0.4

# LPS for REMOVE_BEAM / REMOVE_COL: position-based hardcoded values
# Midroom columns carry the most tributary load — hardest to remove (highest sensitivity).
# Corner columns carry the least — can often be eliminated with an edge beam.
_LPS_REMOVE_COL: dict[str, float] = {
    "corner":  5.0,
    "wall":    7.0,
    "midroom": 9.0,
}
_LPS_REMOVE_BEAM = 7.0

# ── Adaptability: Regulatory Footprint (RF) parameters ───────────────────────
_RF_BASE_NORMAL       = 5.0
_RF_BASE_HERITAGE     = 2.0   # when heritage_ratchet is True
_RF_P8_BONUS          = 1.5
_RF_P7_BONUS          = 1.0
_RF_COMPLEXITY_PENALTY = -1.0  # when 4+ processes triggered

# ── Adaptability: sub-dimension weights ───────────────────────────────────────
_W_SC  = 0.35
_W_CR  = 0.30
_W_LPS = 0.25
_W_RF  = 0.10

# ── Adaptability: label bands ─────────────────────────────────────────────────
_ADAPT_BANDS: list[tuple[float, str]] = [
    (2.0,  "Very Low"),
    (4.0,  "Low"),
    (6.0,  "Moderate"),
    (8.0,  "High"),
    (10.1, "Very High"),
]
# ### V4 END ───────────────────────────────────────────────────────────────────


# ── Geometry helpers (unchanged from V3) ─────────────────────────────────────

def _pt_to_segment_dist(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """Euclidean distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _min_dist_to_outline(point: list, outline: list) -> float:
    """Minimum 2D distance from a layout point to the nearest outline polygon edge."""
    if not outline or len(outline) < 2:
        return float("inf")
    x, y = float(point[0]), float(point[1])
    n = len(outline)
    return min(
        _pt_to_segment_dist(
            x, y,
            float(outline[i][0]),       float(outline[i][1]),
            float(outline[(i+1)%n][0]), float(outline[(i+1)%n][1]),
        )
        for i in range(n)
    )


# ── Element volume estimation (unchanged from V3) ─────────────────────────────

def _element_volume_m3(el: dict) -> float:
    """Estimate placed structural volume (m³) from geometry + section attributes."""
    attrs   = el.get("attributes", {})
    geo     = el.get("geometry", [])
    mat     = attrs.get("material", "RCC").upper()
    is_beam = len(geo) == 2

    if is_beam:
        span = math.dist(geo[0], geo[1])
        sec  = attrs.get("section", "")
        if "STEEL" in mat and sec in STEEL_BEAM_PROPS:
            A_m2 = STEEL_BEAM_PROPS[sec]["A_mm2"] / 1e6
        else:
            d_m  = float(attrs.get("depth",  400)) / 1000.0
            w_m  = float(attrs.get("width",  200)) / 1000.0
            A_m2 = w_m * d_m
        return span * A_m2
    else:
        H   = float(attrs.get("height", 3.5))
        sec = attrs.get("section", "")
        if "STEEL" in mat and sec in STEEL_COL_PROPS:
            A_m2 = STEEL_COL_PROPS[sec]["A_mm2"] / 1e6
        else:
            b_m, d_m = _parse_dim_mm(attrs.get("dimensions", "300x300"))
            A_m2 = b_m * d_m
        return H * A_m2


# ── Layout diff detection (unchanged from V3) ─────────────────────────────────

def _detect_changes(before_str: str, after_str: str) -> dict[str, Any]:
    """Compare two layout JSON strings and return categorised element lists."""
    def _struct_map(s: str) -> dict[str, dict]:
        try:
            return {el["id"]: el for el in json.loads(s).get("structure", [])}
        except (json.JSONDecodeError, TypeError):
            return {}

    before  = _struct_map(before_str)
    after   = _struct_map(after_str)

    added   = [after[k]  for k in after  if k not in before]
    removed = [before[k] for k in before if k not in after]
    chg_ids = [
        k for k in before
        if k in after and before[k].get("attributes") != after[k].get("attributes")
    ]

    return {
        "added":          added,
        "removed":        removed,
        "changed_after":  [after[k]  for k in chg_ids],
        "changed_before": [before[k] for k in chg_ids],
    }


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Normalised position classification (Change 1) ─────────────────────────────

def _compute_characteristic_dim(outline: list) -> tuple[float, bool]:
    """
    Returns (characteristic_dim, used_fallback).
    characteristic_dim = min(room_width, room_depth) from the outline bounding box.
    Falls back to _FALLBACK_CHARACTERISTIC_M when outline is absent or malformed.
    """
    if not outline or len(outline) < 3:
        return _FALLBACK_CHARACTERISTIC_M, True
    try:
        xs  = [float(p[0]) for p in outline]
        ys  = [float(p[1]) for p in outline]
        dim = min(max(xs) - min(xs), max(ys) - min(ys))
        if dim <= 0:
            return _FALLBACK_CHARACTERISTIC_M, True
        return dim, False
    except (TypeError, IndexError, ValueError):
        return _FALLBACK_CHARACTERISTIC_M, True


def classify_position(point: list, outline: list) -> tuple[str, bool]:
    """
    Returns (position_class, used_fallback).
    position_class: "corner" | "wall" | "midroom"
    used_fallback:  True when characteristic_dim derived from fallback constant.

    Corner  — distance to nearest vertex ≤ CORNER_FRAC × characteristic_dim
    Wall    — distance to nearest edge   ≤ WALL_FRAC   × characteristic_dim
    Midroom — further than WALL_FRAC from all edges
    """
    dim, used_fallback = _compute_characteristic_dim(outline)
    corner_thresh = _CORNER_FRAC * dim
    wall_thresh   = _WALL_FRAC   * dim

    try:
        px, py = float(point[0]), float(point[1])
    except (TypeError, IndexError, ValueError):
        return "midroom", True

    if not outline or len(outline) < 2:
        return "midroom", True

    for v in outline:
        try:
            if math.hypot(px - float(v[0]), py - float(v[1])) <= corner_thresh:
                return "corner", used_fallback
        except (TypeError, IndexError, ValueError):
            continue

    if _min_dist_to_outline([point[0], point[1]], outline) <= wall_thresh:
        return "wall", used_fallback

    return "midroom", used_fallback

# ### V4 END ───────────────────────────────────────────────────────────────────


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Label helpers (Change 5) ──────────────────────────────────────────────────

def _financial_cost_label(mid_eur: float) -> tuple[str, int]:
    for threshold, score, label in _FC_BANDS:
        if mid_eur < threshold:
            return label, score
    return "Very High", 10


def _admin_burden_label(score: float) -> str:
    for threshold, label in _AB_BANDS:
        if score <= threshold:
            return label
    return "Complex"


def _adaptability_label(score: float) -> str:
    for threshold, label in _ADAPT_BANDS:
        if score <= threshold:
            return label
    return "Very High"


def _adaptability_confidence(
    building_context: str | None,
    heritage_ratchet: bool,
    outline_valid: bool,
) -> str:
    if not outline_valid:
        return "VERY_LOW"
    if heritage_ratchet and building_context == "EXISTING_UNKNOWN":
        return "VERY_LOW"
    if heritage_ratchet or building_context == "EXISTING_UNKNOWN":
        return "LOW"
    if building_context == "NEW":
        return "HIGH"
    return "MEDIUM"

# ### V4 END ───────────────────────────────────────────────────────────────────


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Intervention classification ───────────────────────────────────────────────

def _count_connected_beams(col_el: dict, all_elements: list[dict]) -> int:
    """Count beams in all_elements whose endpoints are within 0.1 m of col_el's position."""
    col_geo = col_el.get("geometry", [])
    if not col_geo or not all_elements:
        return 2
    col_pt = col_geo[0]
    count = 0
    for el in all_elements:
        geo = el.get("geometry", [])
        if len(geo) != 2:
            continue
        for end_pt in geo:
            try:
                if math.hypot(
                    float(end_pt[0]) - float(col_pt[0]),
                    float(end_pt[1]) - float(col_pt[1]),
                ) < 0.1:
                    count += 1
                    break
            except (TypeError, IndexError, ValueError):
                pass
    return max(1, count)


def _classify_beam_position(el: dict, outline: list) -> str:
    """Returns 'perimeter' or 'internal' based on beam midpoint distance from outline."""
    geo = el.get("geometry", [])
    if len(geo) < 2:
        return "internal"
    mid = [(geo[0][i] + geo[1][i]) / 2.0 for i in range(2)]
    dim, _ = _compute_characteristic_dim(outline)
    return "perimeter" if _min_dist_to_outline(mid, outline) <= _WALL_FRAC * dim else "internal"


def _classify_element(
    el_after:     dict,
    el_before:    dict | None,
    is_added:     bool,
    is_removed:   bool,
    outline:      list,
    all_elements: list[dict] | None = None,
) -> dict:
    """
    Returns a typed intervention dict:
      type            — ADD_COL_CORNER | ADD_COL_WALL | ADD_COL_MIDROOM |
                        ADD_BEAM | REMOVE_BEAM | REMOVE_COL | UPSIZE_SAME_MAT | CHANGE_MATERIAL
      position        — "corner"|"wall"|"midroom" for columns; "perimeter"|"internal" for beams
      material        — resulting material (uppercase)
      material_before — prior material for CHANGE_MATERIAL; else None
      is_beam         — True when element has 2 geometry points
      used_fallback   — True when position was classified with fallback thresholds
      n_beams_connected — count of connected beams (for LPS formula)
      element         — el_after dict
    """
    geo     = el_after.get("geometry", [])
    attrs_a = el_after.get("attributes", {})
    attrs_b = el_before.get("attributes", {}) if el_before else {}
    is_beam = len(geo) == 2

    mat_a = attrs_a.get("material", "RCC").upper()
    mat_b = attrs_b.get("material", "RCC").upper() if el_before else mat_a
    mat_changed = mat_a != mat_b

    if is_beam:
        pos = _classify_beam_position(el_after, outline)
        if is_added:
            typ = "ADD_BEAM"
        elif is_removed:
            typ = "REMOVE_BEAM"
        elif mat_changed:
            typ = "CHANGE_MATERIAL"
        else:
            typ = "UPSIZE_SAME_MAT"
        return {
            "type": typ, "position": pos,
            "material": mat_a, "material_before": mat_b if el_before else None,
            "is_beam": True, "used_fallback": False,
            "n_beams_connected": 2,
            "element": el_after,
        }

    pt = geo[0] if geo else [0, 0, 0]
    pos_class, used_fallback = classify_position(pt, outline)

    if is_added:
        typ = {"corner": "ADD_COL_CORNER",
               "wall":   "ADD_COL_WALL",
               "midroom":"ADD_COL_MIDROOM"}.get(pos_class, "ADD_COL_MIDROOM")
    elif is_removed:
        typ = "REMOVE_COL"
    elif mat_changed:
        typ = "CHANGE_MATERIAL"
    else:
        typ = "UPSIZE_SAME_MAT"

    n_beams = _count_connected_beams(el_after, all_elements) if all_elements else 2

    return {
        "type": typ, "position": pos_class,
        "material": mat_a, "material_before": mat_b if el_before else None,
        "is_beam": False, "used_fallback": used_fallback,
        "n_beams_connected": n_beams,
        "element": el_after,
    }

# ### V4 END ───────────────────────────────────────────────────────────────────


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Pillar 1 — Financial Cost ─────────────────────────────────────────────────

def _floor_logistics_eur(floor_level: int) -> float:
    """Logistics cost addition (EUR) based on floor level. Ground floor = minimal."""
    if floor_level <= 0:
        return 1_200.0 + abs(floor_level) * 300.0   # basement: chain hoist + slab opening
    if floor_level == 1:
        return 80.0
    return 80.0 + (floor_level - 1) * 200.0          # crane/hoist escalation per floor


def _compute_financial_cost(
    interventions:    list[dict],
    occupancy_class:  str,
    building_context: str,
    floor_level:      int,
    heritage_ratchet: bool,
    location:         str = "Barcelona",
) -> dict:
    """
    Compute Financial Cost across 8 components (A–H) and return the pillar output dict.
    All monetary values in EUR. location defaults to Barcelona until location state key added.
    """
    if not interventions:
        return {
            "_financial_cost_score": 0,
            "financial_cost_label": "Negligible",
            "financial_cost_range": {"low": 0.0, "mid": 0.0, "high": 0.0, "currency": "EUR"},
            "overhead_mid_eur": 0.0,
            "intervention_mid_eur": 0.0,
            "dominant_cost_driver": "—",
        }

    loc   = _LOCATION_INDEX.get(location, 1.0)
    occ_m = _OCC_DAY_RATE.get(occupancy_class, 1.7)
    ctx_m = _CTX_LABOR.get(building_context, 1.0)
    hr_m  = _HERITAGE_LABOR_MULT if heritage_ratchet else 1.0

    # A — Mobilisation
    a = _MOBILIZATION_EUR.get(occupancy_class, 640.0) * loc

    # B — Labour (days × position × material factor × day rate)
    b = 0.0
    for iv in interventions:
        days     = _BASE_WORKER_DAYS.get(iv["type"], 10.0)
        if not iv["is_beam"]:
            pos_m = (_POS_LABOR_REMOVE if iv["type"] == "REMOVE_COL" else _POS_LABOR).get(iv["position"], 1.0)
        else:
            pos_m = 1.0
        mat_key    = next((k for k in _MATERIAL_LABOR_FACTOR if k in iv["material"]), "RCC")
        mat_factor = _MATERIAL_LABOR_FACTOR[mat_key]
        day_rate   = _BASE_DAY_RATE_EUR * occ_m * ctx_m * hr_m * loc
        b         += days * pos_m * mat_factor * day_rate

    # C — Temporary works (shoring/propping for column removal or material change only)
    # Beam removal does not require shoring — no temp works charge.
    needs_temp = any(iv["type"] in ("REMOVE_COL", "CHANGE_MATERIAL") for iv in interventions)
    c = _TEMP_WORKS_MID_EUR * loc if needs_temp else 0.0

    # D — Logistics (floor level + element count)
    d = _floor_logistics_eur(floor_level) * len(interventions) * loc

    # E — Occupancy coordination (scheduling, safety management overhead on labour)
    # Reduced from 10% HIGH → 4%: the occupancy uplift in _OCC_DAY_RATE already
    # captures the main cost impact; E now covers only residual coordination.
    e_frac = {"VACANT": 0.0, "LOW": 0.02, "HIGH": 0.04, "CRITICAL": 0.08}
    e = b * e_frac.get(occupancy_class, 0.04)

    # F — Material (volume × rate per m³)
    f = 0.0
    for iv in interventions:
        if iv["type"] not in ("REMOVE_BEAM", "REMOVE_COL"):
            vol     = _element_volume_m3(iv["element"])
            mat_key = next((k for k in _MATERIAL_RATE_EUR if k in iv["material"]), "RCC")
            f      += vol * _MATERIAL_RATE_EUR[mat_key]

    # G — Demolition (for removals and the demolition phase of CHANGE_MATERIAL)
    g = 0.0
    hr_demo = _HERITAGE_DEMO_MULT if heritage_ratchet else 1.0
    for iv in interventions:
        if iv["type"] in ("REMOVE_BEAM", "REMOVE_COL", "CHANGE_MATERIAL"):
            vol      = _element_volume_m3(iv["element"])
            src_mat  = (iv.get("material_before") or iv["material"])
            demo_rate = 280.0 if "RCC" in src_mat else 120.0
            g        += vol * demo_rate * hr_demo * loc

    # H — Professional fees (12 % of non-material subtotal A+B+C+D+E+G)
    # Split proportionally between overhead and intervention groups.
    overhead_base     = a + c                          # fixed per project
    intervention_base = b + d + e + f + g              # scales with what you do
    h_overhead        = overhead_base     * _PROFESSIONAL_FEE_PCT
    h_intervention    = intervention_base * _PROFESSIONAL_FEE_PCT

    overhead_mid     = round(overhead_base     + h_overhead,     0)
    intervention_mid = round(intervention_base + h_intervention, 0)
    total_mid        = overhead_mid + intervention_mid

    total_low  = round(total_mid * 0.70, 0)
    total_high = round(total_mid * 1.50, 0)

    components = {
        "Component A — Mobilisation":           a,
        "Component B — Labour":                 b,
        "Component C — Temp Works":             c,
        "Component D — Logistics":              d,
        "Component E — Occupancy Coordination": e,
        "Component F — Material":               f,
        "Component G — Demolition":             g,
        "Component H — Professional Fees":      h_overhead + h_intervention,
    }
    dominant = max(components, key=lambda k: components[k])
    label, score = _financial_cost_label(total_mid)

    return {
        "_financial_cost_score":  score,
        "financial_cost_label":   label,
        "financial_cost_range": {
            "low": total_low, "mid": total_mid, "high": total_high, "currency": "EUR",
        },
        "overhead_mid_eur":      overhead_mid,
        "intervention_mid_eur":  intervention_mid,
        "dominant_cost_driver":  dominant,
    }


def _compute_total_build_cost(all_elements: list[dict], location: str = "Barcelona") -> dict:
    """
    Volume-based new-build cost for the complete current structure.
    Supply = _MATERIAL_RATE_EUR; installation = _INSTALL_RATE_NEW_EUR.
    Calibrated to CYPE 2024 Barcelona reference: GL24h at €869/m³ supply + €1,500/m³ erection.
    Professional fees (18 %) and a permit base charge are added on top of the PEM.
    """
    if not all_elements:
        return {
            "total_build_mid_eur":  0.0, "total_build_low_eur":  0.0,
            "total_build_high_eur": 0.0, "total_build_label":    "—",
            "total_build_pem_eur":  0.0, "total_build_vol_m3":   {},
        }

    loc = _LOCATION_INDEX.get(location, 1.0)
    vol_by_mat: dict[str, float] = {}
    for el in all_elements:
        mat = el.get("attributes", {}).get("material", "RCC").upper()
        mat_key = next((k for k in _MATERIAL_RATE_EUR if k in mat), "RCC")
        vol_by_mat[mat_key] = vol_by_mat.get(mat_key, 0.0) + _element_volume_m3(el)

    material_cost = sum(vol * _MATERIAL_RATE_EUR[k]                  * loc for k, vol in vol_by_mat.items())
    install_cost  = sum(vol * _INSTALL_RATE_NEW_EUR.get(k, 1_500.0)  * loc for k, vol in vol_by_mat.items())
    pem       = material_cost + install_cost
    fees      = pem * _FEE_PCT_NEW_BUILD
    total_mid = round(pem + fees + _PERMIT_BASE_EUR * loc, 0)
    label, _  = _financial_cost_label(total_mid)

    return {
        "total_build_mid_eur":  total_mid,
        "total_build_low_eur":  round(total_mid * 0.70, 0),
        "total_build_high_eur": round(total_mid * 1.50, 0),
        "total_build_label":    label,
        "total_build_pem_eur":  round(pem, 0),
        "total_build_vol_m3":   {k: round(v, 3) for k, v in vol_by_mat.items()},
    }


def _element_avoided_cost(el: dict, location: str = "Barcelona") -> float:
    """Build cost of a single element at new-construction rates (supply + install + 18 % fees)."""
    mat = el.get("attributes", {}).get("material", "RCC").upper()
    mat_key = next((k for k in _MATERIAL_RATE_EUR if k in mat), "RCC")
    vol = _element_volume_m3(el)
    loc = _LOCATION_INDEX.get(location, 1.0)
    unit = (_MATERIAL_RATE_EUR[mat_key] + _INSTALL_RATE_NEW_EUR.get(mat_key, 1_500.0)) * loc
    return vol * unit * (1.0 + _FEE_PCT_NEW_BUILD)

# ### V4 END ───────────────────────────────────────────────────────────────────


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Pillar 2 — Administrative Burden V2 ───────────────────────────────────────

def _compute_admin_burden(
    interventions:    list[dict],
    occupancy_class:  str,
    building_context: str,
    heritage_ratchet: bool,
    is_condominium:   bool = False,  # default False; set True via settings for condominium buildings
    location:         str  = "Barcelona",  # TODO: read from state when location key added
) -> dict:
    """
    Determine which processes P0–P9 are triggered, compute critical-path duration,
    and score across process load (35 %), duration (40 %), cost (25 %).
    """
    triggered: list[str] = []

    # P0 — Pre-authorisation (discretionary jurisdictions)
    if location in {"Monaco", "New York", "Paris"}:
        triggered.append("P0")

    # P7 — Structural survey (must precede P2 for EXISTING_UNKNOWN)
    if building_context == "EXISTING_UNKNOWN":
        triggered.append("P7")

    # P1 — Regularisation risk (EXISTING_UNKNOWN; probability-based; see TODO 6)
    p1_risk = "none"
    if building_context == "EXISTING_UNKNOWN":
        p1_risk = "moderate"   # 60 % base probability; defaults to UNDOCUMENTED
        triggered.append("P1")

    # P2 — Municipal building permit (always required)
    triggered.append("P2")

    # P3 — Community / ownership consent (condominium with structural impact)
    if is_condominium:
        triggered.append("P3")

    # P4 — Heritage authority review (if heritage_ratchet is True)
    if heritage_ratchet:
        triggered.append("P4")

    # P5 — Neighbor / party wall notification
    has_removal   = any(iv["type"] in ("REMOVE_BEAM", "REMOVE_COL") for iv in interventions)
    has_perimeter = any(
        (not iv["is_beam"] and iv["position"] in ("wall", "corner")) or
        (iv["is_beam"] and iv["position"] == "perimeter")
        for iv in interventions
    )
    if has_removal or (has_perimeter and is_condominium):
        triggered.append("P5")

    # P6 — Professional registration (always required for structural work)
    triggered.append("P6")

    # P8 — Project completion certificate (always required)
    triggered.append("P8")

    # P9 — Occupancy notification (HIGH or CRITICAL only)
    if occupancy_class in ("HIGH", "CRITICAL"):
        triggered.append("P9")

    # ── Critical-path computation ──────────────────────────────────────────────
    # Dependency order: P0 → P7 → P1 (sequential pre-permit chain) → P2
    # P3, P4, P5 run concurrently with P2 (take the max for during-permit phase)
    # P6 runs in parallel (excluded from critical path)
    # P8, P9 run post-construction in parallel (take the max)

    def _dur(p: str, idx: int) -> int:
        return _PROCESS_DURATION[p][idx] if p in triggered else 0

    pre_best  = _dur("P0", 0) + _dur("P7", 0) + _dur("P1", 0)
    pre_mid   = _dur("P0", 1) + _dur("P7", 1) + _dur("P1", 1)
    pre_worst = _dur("P0", 2) + _dur("P7", 2) + _dur("P1", 2)

    during_mid = max(
        _PROCESS_DURATION["P2"][1],
        *[_PROCESS_DURATION[p][1] for p in ("P3", "P4", "P5") if p in triggered],
        0,
    )
    during_best = max(
        _PROCESS_DURATION["P2"][0],
        *[_PROCESS_DURATION[p][0] for p in ("P3", "P4", "P5") if p in triggered],
        0,
    )

    post_mid  = max((_PROCESS_DURATION[p][1] for p in ("P8", "P9") if p in triggered), default=0)
    post_best = max((_PROCESS_DURATION[p][0] for p in ("P8", "P9") if p in triggered), default=0)

    cp_mid   = pre_mid  + during_mid  + post_mid
    cp_best  = pre_best + during_best + post_best
    cp_worst = min(
        sum(_PROCESS_DURATION[p][2] for p in triggered if p != "P6"),
        156,  # cap at 3 years
    )

    # ── Composite score ────────────────────────────────────────────────────────
    n_proc   = len(triggered)
    load_s   = min(10.0, n_proc * 1.2)
    dur_s    = min(10.0, cp_mid / 120.0 * 10.0)
    cost_tot = sum(_PROCESS_COST_MID.get(p, 0) for p in triggered)
    cost_s   = min(10.0, cost_tot / 80_000.0 * 10.0)
    ab_score = 0.35 * load_s + 0.40 * dur_s + 0.25 * cost_s

    # Dominant process = longest mid duration on the critical path
    cp_candidates = [p for p in triggered if p in _PROCESS_DURATION and p != "P6"]
    dominant_p = max(cp_candidates, key=lambda p: _PROCESS_DURATION[p][1]) if cp_candidates else "P2"

    return {
        "_admin_burden_score":       round(ab_score, 2),
        "admin_burden_label":        _admin_burden_label(ab_score),
        "processes_triggered":       triggered,
        "admin_critical_path_weeks": {
            "best":  cp_best,
            "mid":   cp_mid,
            "worst": cp_worst,
        },
        "dominant_admin_process": _PROCESS_NAMES.get(dominant_p, dominant_p),
        "regularization_risk":    p1_risk,
    }

# ### V4 END ───────────────────────────────────────────────────────────────────


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Pillar 3 — Adaptability V4 ────────────────────────────────────────────────

def _cr_score(mat: str, is_new_building: bool, is_removal: bool, is_upsize: bool) -> float:
    """Configuration Reversibility score for ADD, REMOVE, and UPSIZE interventions."""
    m = mat.upper()
    if is_removal:
        if "STEEL"  in m: return 8.5
        if "TIMBER" in m: return 7.0
        return 3.0   # RCC demolition leaves repair patches
    if is_upsize:
        if "STEEL"  in m: return 8.5   # steel upsize remains bolted
        if "TIMBER" in m: return 7.5
        return 1.0   # RCC upsize: more permanently cast than a fresh add
    # ADD
    if "STEEL"  in m: return 9.5 if is_new_building else 9.0
    if "TIMBER" in m: return 8.5 if is_new_building else 8.0
    return 1.5   # RCC add


def _cr_change_material(mat_after: str) -> float:
    """CR score for CHANGE_MATERIAL interventions based on resulting material."""
    m = mat_after.upper()
    if "STEEL"  in m: return 7.5   # interface zone reduces from 9.0 new-steel
    if "TIMBER" in m: return 7.0
    return 1.5   # →RCC: element is now permanently cast


def _compute_rf(processes_triggered: list[str], heritage_ratchet: bool) -> float:
    """Regulatory Footprint score — building-level, not per-element."""
    base = _RF_BASE_HERITAGE if heritage_ratchet else _RF_BASE_NORMAL
    rf   = base
    if "P8" in processes_triggered: rf += _RF_P8_BONUS
    if "P7" in processes_triggered: rf += _RF_P7_BONUS
    if len(processes_triggered) >= 4: rf += _RF_COMPLEXITY_PENALTY
    return max(0.0, min(10.0, rf))


def _lps_formula(n: int, sensitivity_rate: float, position_weight: float) -> float:
    return max(0.5, 10.0 - n * sensitivity_rate * position_weight)


def _single_element_scores(iv: dict, is_new_building: bool) -> tuple[float, float, float]:
    """
    Returns (SC, CR, LPS) for one typed intervention.
    RF is building-level and computed separately via _compute_rf().
    """
    typ        = iv["type"]
    pos        = iv["position"]
    mat        = iv["material"]
    is_beam    = iv["is_beam"]
    is_removal = (typ in ("REMOVE_BEAM", "REMOVE_COL"))
    is_upsize  = (typ == "UPSIZE_SAME_MAT")
    n          = iv.get("n_beams_connected", 2)

    # SC ───────────────────────────────────────────────────────────────────────
    if is_removal:
        sc = _SC_REMOVE_BEAM if is_beam else _SC_REMOVE_COL.get(pos, 9.5)
    elif is_upsize:
        sc = _SC_UPSIZE
    elif typ == "ADD_BEAM":
        sc = _SC_ADD_BEAM.get(pos, 5.5)
    elif typ in ("ADD_COL_CORNER", "ADD_COL_WALL", "ADD_COL_MIDROOM"):
        sc = _SC_ADD_COL.get(pos, 2.0)
    elif typ == "CHANGE_MATERIAL":
        # Change 2: SC reflects resulting position, not material direction
        sc = _SC_ADD_BEAM.get(pos, 5.5) if is_beam else _SC_ADD_COL.get(pos, 2.0)
    else:
        sc = 5.0

    # CR ───────────────────────────────────────────────────────────────────────
    if typ == "CHANGE_MATERIAL":
        cr = _cr_change_material(mat)
    else:
        cr = _cr_score(mat, is_new_building, is_removal, is_upsize)

    # LPS ──────────────────────────────────────────────────────────────────────
    if is_removal:
        lps = _LPS_REMOVE_BEAM if is_beam else _LPS_REMOVE_COL.get(pos, 5.5)
    elif is_beam:
        lps = _lps_formula(2, 0.5, _LPS_POSITION_WEIGHT["beam"])
    elif is_upsize:
        lps = _lps_formula(n, _LPS_UPSIZE_RATE, _LPS_POSITION_WEIGHT.get(pos, 2.0))
    elif typ == "CHANGE_MATERIAL":
        lps = _lps_formula(n, _LPS_CHANGE_MAT_RATE, _LPS_POSITION_WEIGHT.get(pos, 2.0))
    else:
        lps = _lps_formula(n, _LPS_SENSITIVITY_RATE.get(pos, 1.8), _LPS_POSITION_WEIGHT.get(pos, 2.0))

    return sc, cr, lps


def _compute_adaptability(
    interventions:       list[dict],
    building_context:    str,
    heritage_ratchet:    bool,
    processes_triggered: list[str],
    outline_valid:       bool,
) -> dict:
    """Compute Adaptability V4 output dict across all interventions."""
    if not interventions:
        rf = _compute_rf(processes_triggered, heritage_ratchet)
        return {
            "_adaptability_score":     10.0,
            "_adaptability_subscores": {"SC": 10.0, "CR": 10.0, "LPS": 10.0, "RF": round(rf, 2)},
            "adaptability_label":     "Very High",
            "adaptability_confidence": _adaptability_confidence(building_context, heritage_ratchet, outline_valid),
            "adaptability_constraint": "—",
            "adaptability_strength":   "—",
        }

    is_new = (building_context == "NEW")
    rf     = _compute_rf(processes_triggered, heritage_ratchet)

    sc_list, cr_list, lps_list = [], [], []
    for iv in interventions:
        sc, cr, lps = _single_element_scores(iv, is_new)
        sc_list.append(sc)
        cr_list.append(cr)
        lps_list.append(lps)

    # SC: arithmetic mean (spatial commitment is additive)
    sc_agg = sum(sc_list) / len(sc_list)

    # CR: weakest-link penalty (Change 4) — single element bypasses formula
    cr_mean = sum(cr_list) / len(cr_list)
    cr_min  = min(cr_list)
    if len(cr_list) == 1:
        cr_agg = cr_mean
    else:
        cr_agg = cr_mean * (1.0 - 0.5 * (cr_mean - cr_min) / 10.0)

    # LPS: arithmetic mean
    lps_agg = sum(lps_list) / len(lps_list)

    composite = _W_SC * sc_agg + _W_CR * cr_agg + _W_LPS * lps_agg + _W_RF * rf

    subscores = {
        "SC":  round(sc_agg,  2),
        "CR":  round(cr_agg,  2),
        "LPS": round(lps_agg, 2),
        "RF":  round(rf,       2),
    }

    # Identify the dimension with the lowest weighted contribution (constraint)
    weighted = {
        "Spatial Commitment":          _W_SC  * sc_agg,
        "Configuration Reversibility": _W_CR  * cr_agg,
        "Load Path Sensitivity":        _W_LPS * lps_agg,
        "Regulatory Footprint":         _W_RF  * rf,
    }
    constraint_dim = min(weighted, key=weighted.get)
    strength_dim   = max(weighted, key=weighted.get)

    # Annotate constraint with material / position context
    def _constraint_note() -> str:
        if "Reversibility" in constraint_dim:
            mats = {iv["material"] for iv in interventions}
            if any("RCC" in m for m in mats):    return " — RCC cast in place"
            if any("STEEL" in m for m in mats):  return " — steel element"
        if "Spatial" in constraint_dim:
            pos_set = {iv["position"] for iv in interventions if not iv["is_beam"]}
            if "midroom" in pos_set: return " — mid-room element"
        if "Regulatory" in constraint_dim and heritage_ratchet:
            return " — heritage ratchet active"
        return ""

    def _strength_note() -> str:
        pos_set = [iv["position"] for iv in interventions if not iv["is_beam"]]
        return f" — {pos_set[0]} position" if pos_set else ""

    return {
        "_adaptability_score":     round(composite, 2),
        "_adaptability_subscores": subscores,
        "adaptability_label":      _adaptability_label(composite),
        "adaptability_confidence": _adaptability_confidence(building_context, heritage_ratchet, outline_valid),
        "adaptability_constraint": constraint_dim + _constraint_note(),
        "adaptability_strength":   strength_dim   + _strength_note(),
    }

# ### V4 END ───────────────────────────────────────────────────────────────────


# ### V4 START ─────────────────────────────────────────────────────────────────
# ── Decision signal ───────────────────────────────────────────────────────────

def _build_decision_signal(fc_score: int, ab_score: float, adapt_score: float) -> str:
    if fc_score <= 3 and adapt_score >= 7.0:  return "efficient_and_adaptable"
    if fc_score >= 6 and adapt_score >= 7.0:  return "adaptability_premium"
    if fc_score <= 4 and adapt_score <= 3.0:  return "cheap_and_locking"
    if fc_score >= 7 and adapt_score <= 5.0:  return "costly_and_inflexible"
    if fc_score <= 4 and adapt_score >= 6.0:  return "low_cost_high_freedom"
    return "balanced"

# ### V4 END ───────────────────────────────────────────────────────────────────


# ── Node builder ──────────────────────────────────────────────────────────────

def build_cost_flexibility_node():
    # ### V4 MODIFIED — replaced V3 single-score model with three-pillar V4 model
    def cost_flexibility_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: COST & FLEXIBILITY  (V4)")
        print(f"{'='*50}")

        # ### V4 START — heritage ratchet: seed from heritage_status if not yet set
        if "heritage_ratchet" not in state or state.get("heritage_ratchet") is None:
            state["heritage_ratchet"] = bool(state.get("heritage_status", False))
        heritage_ratchet: bool = state["heritage_ratchet"]
        # ### V4 END

        layout_str = state.get("layout_json_string", "")
        before_str = (
            state.get("layout_before_change")
            or state.get("original_layout_json_string")
        )

        try:
            layout_data  = json.loads(layout_str)
            outline      = layout_data.get("outline", [])
            all_elements = layout_data.get("structure", [])
        except (json.JSONDecodeError, TypeError):
            outline      = []
            all_elements = []

        # Always compute total new-build cost for the full current structure
        tbc = _compute_total_build_cost(all_elements)
        if tbc["total_build_mid_eur"]:
            vol_str = ", ".join(f"{v:.3f} m³ {k}" for k, v in tbc["total_build_vol_m3"].items())
            print(
                f"  Full structure build cost: {tbc['total_build_label']} "
                f"(EUR {tbc['total_build_mid_eur']:,.0f}  "
                f"range {tbc['total_build_low_eur']:,.0f}–{tbc['total_build_high_eur']:,.0f})"
                f"  [{vol_str}]"
            )

        if not before_str:
            print("  No before-snapshot — showing build cost only.")
            state["cost_flexibility"] = {
                "total_build_cost": tbc,
                "summary": (
                    f"Full structure: {tbc['total_build_label']} "
                    f"(EUR {tbc['total_build_mid_eur']:,.0f} / "
                    f"{tbc['total_build_low_eur']:,.0f}–{tbc['total_build_high_eur']:,.0f})"
                ),
            }
            return state

        diff           = _detect_changes(before_str, layout_str)
        added          = diff["added"]
        removed        = diff["removed"]
        changed_after  = diff["changed_after"]
        changed_before = diff["changed_before"]

        if not added and not removed and not changed_after:
            print("  No structural changes — showing build cost only.")
            state["cost_flexibility"] = {
                "total_build_cost": tbc,
                "summary": (
                    f"Full structure: {tbc['total_build_label']} "
                    f"(EUR {tbc['total_build_mid_eur']:,.0f} / "
                    f"{tbc['total_build_low_eur']:,.0f}–{tbc['total_build_high_eur']:,.0f})"
                ),
            }
            return state

        # ### V4 START ─────────────────────────────────────────────────────────
        # Read context inputs
        occupancy_class  = state.get("building_occupancy_class") or "HIGH"
        building_context = state.get("building_context") or "EXISTING_KNOWN"
        floor_level      = int(state.get("floor_level") or 1)
        outline_valid    = len(outline) >= 3

        # Build typed intervention list
        interventions: list[dict] = []
        for el in added:
            interventions.append(_classify_element(el, None, True, False, outline, all_elements))
        for el in removed:
            interventions.append(_classify_element(el, None, False, True, outline, all_elements))
        for el_a, el_b in zip(changed_after, changed_before):
            interventions.append(_classify_element(el_a, el_b, False, False, outline, all_elements))

        # Pillar 1: Financial Cost
        fc = _compute_financial_cost(
            interventions, occupancy_class, building_context,
            floor_level, heritage_ratchet,
        )

        # Pillar 2: Administrative Burden
        ab = _compute_admin_burden(
            interventions, occupancy_class, building_context, heritage_ratchet,
        )

        # Heritage ratchet escalation — write back to state if P4 triggered for first time
        ratchet_triggered_now = False
        if "P4" in ab["processes_triggered"] and not heritage_ratchet:
            state["heritage_ratchet"] = True
            ratchet_triggered_now = True
            print("  [V4] Heritage ratchet triggered — building permanently elevated.")

        # Pillar 3: Adaptability (reads updated ratchet after potential escalation)
        ad = _compute_adaptability(
            interventions, building_context,
            state["heritage_ratchet"],
            ab["processes_triggered"],
            outline_valid,
        )

        # Decision signal
        signal = _build_decision_signal(
            fc["_financial_cost_score"],
            ab["_admin_burden_score"],
            ad["_adaptability_score"],
        )

        # Design-phase savings: avoided new-build cost for each removed element
        design_savings_eur = round(sum(_element_avoided_cost(el) for el in removed), 0)
        if design_savings_eur:
            print(f"  Design-phase saving (not building removed elements): EUR {design_savings_eur:,.0f}")

        # Summary string — labels only, no decimal scores (Change 5)
        parts = []
        if added:         parts.append(f"{len(added)} added")
        if removed:       parts.append(f"{len(removed)} removed")
        if changed_after: parts.append(f"{len(changed_after)} changed")
        change_desc = ", ".join(parts) or "no changes"

        fc_r = fc["financial_cost_range"]
        summary = (
            f"Full structure: {tbc['total_build_label']} (EUR {tbc['total_build_mid_eur']:,.0f}) | "
            f"{change_desc} | "
            f"Cost: {fc['financial_cost_label']} "
            f"({fc_r['currency']} {fc_r['mid']:,.0f} total"
            f" / {fc['intervention_mid_eur']:,.0f} intervention"
            f" / {fc['overhead_mid_eur']:,.0f} overhead) | "
            f"Admin: {ab['admin_burden_label']} "
            f"({ab['admin_critical_path_weeks']['mid']} wks mid) | "
            f"Adaptability: {ad['adaptability_label']} "
            f"({ad['adaptability_confidence']} confidence) | "
            f"Signal: {signal}"
        )
        print(f"  {summary}")
        if ratchet_triggered_now:
            print("  Heritage ratchet: PERMANENT — all future modifications require heritage review.")

        state["cost_flexibility"] = {
            # Internal — for comparison node ranking; not surfaced in LLM narrative
            "_financial_cost_score":    fc["_financial_cost_score"],
            "_admin_burden_score":      ab["_admin_burden_score"],
            "_adaptability_score":      ad["_adaptability_score"],
            "_adaptability_subscores":  ad["_adaptability_subscores"],
            # Total structure build cost (new construction, volume-based)
            "total_build_cost":         tbc,
            "design_savings_eur":       design_savings_eur,
            # Financial Cost (last modification, renovation rates)
            "financial_cost_label":     fc["financial_cost_label"],
            "financial_cost_range":     fc["financial_cost_range"],
            "overhead_mid_eur":         fc["overhead_mid_eur"],
            "intervention_mid_eur":     fc["intervention_mid_eur"],
            "dominant_cost_driver":     fc["dominant_cost_driver"],
            # Administrative Burden
            "admin_burden_label":       ab["admin_burden_label"],
            "admin_critical_path_weeks": ab["admin_critical_path_weeks"],
            "processes_triggered":      ab["processes_triggered"],
            "dominant_admin_process":   ab["dominant_admin_process"],
            "regularization_risk":      ab["regularization_risk"],
            # Adaptability
            "adaptability_label":       ad["adaptability_label"],
            "adaptability_confidence":  ad["adaptability_confidence"],
            "adaptability_constraint":  ad["adaptability_constraint"],
            "adaptability_strength":    ad["adaptability_strength"],
            # Cross-pillar
            "heritage_ratchet_triggered_this_intervention": ratchet_triggered_now,
            "decision_signal":          signal,
            "summary":                  summary,
        }
        # ### V4 END ────────────────────────────────────────────────────────────
        return state

    return cost_flexibility_node


# ════════════════════════════════════════════════════════════════════════════════
# FILE CHANGE LOG
# ────────────────────────────────────────────────────────────────────────────────
# Added:
#   _FALLBACK_CHARACTERISTIC_M constant
#   _CORNER_FRAC, _WALL_FRAC normalised threshold constants
#   All V4 pillar data tables (location indices, occupancy rates, SC/CR/LPS/RF
#     tables, Admin Burden process definitions, Financial Cost component rates)
#   _compute_characteristic_dim()
#   classify_position()                  — replaces inline threshold checks
#   _financial_cost_label()
#   _admin_burden_label()
#   _adaptability_label()
#   _adaptability_confidence()
#   _count_connected_beams()
#   _classify_beam_position()
#   _classify_element()                  — typed intervention builder
#   _floor_logistics_eur()
#   _compute_financial_cost()            — Pillar 1 (8-component additive model)
#   _compute_admin_burden()              — Pillar 2 (P0–P9 process checklist)
#   _cr_score(), _cr_change_material()   — Pillar 3 CR helpers
#   _compute_rf()                        — Pillar 3 RF (building-level)
#   _lps_formula()
#   _single_element_scores()             — Pillar 3 per-element SC/CR/LPS
#   _compute_adaptability()              — Pillar 3 aggregation + output
#   _build_decision_signal()
#
# Modified:
#   Module docstring — updated for V4
#   _CORNER_DIST_M → _FALLBACK_CORNER_M (renamed, purpose narrowed)
#   _WALL_DIST_M   → _FALLBACK_WALL_M   (renamed, purpose narrowed)
#   build_cost_flexibility_node() — full V4 three-pillar implementation
#   state["cost_flexibility"] output dict — V4 structure (see architecture spec)
#
# Removed (V3 only):
#   _flex_label()
#   _disruption_label()
#   _material_cost_usd()
#   _single_element_flexibility()
#   _aggregate_flexibility()
#   _disruption_score()
#   _spatial_penalty()
#
# New state keys written:
#   state["heritage_ratchet"] — set True when P4 triggers; never reset to False
#   state["cost_flexibility"] — V4 output dict (see architecture spec for full schema)
#
# Backwards compatibility risks:
#   HIGH   — state["cost_flexibility"] dict structure changed. comparison.py reads
#            only cf.get("summary") which exists in V4; no breakage there.
#            graph.py _write_evaluation_report() already updated to V4 dual-path.
#            Any other consumer reading old field names (cost_added_usd,
#            flexibility_score, disruption_score, spatial_penalty) will receive
#            None from .get() or KeyError on direct access. No known other consumers.
#   MEDIUM — _CORNER_DIST_M and _WALL_DIST_M no longer exported. If any external
#            file imported these constants, it will NameError. Search codebase
#            before deploying: grep -r "_CORNER_DIST_M\|_WALL_DIST_M" .
#   LOW    — is_condominium defaults to True in _compute_admin_burden(). P3 will
#            always trigger for non-VACANT buildings until ownership state key added.
#   LOW    — location defaults to "Barcelona" in both pillar functions. All sessions
#            will use Barcelona cost/process profiles until location state key added.
# ════════════════════════════════════════════════════════════════════════════════
