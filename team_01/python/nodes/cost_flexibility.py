"""
cost_flexibility.py — Independent Cost + Flexibility evaluation node.

Runs after every evaluate:
    generate_grid → evaluate → cost_flexibility → END
    evaluate      →            cost_flexibility → END
    modify        → evaluate → cost_flexibility → comparison → END

Reads the structural diff between original_layout_json_string and layout_json_string,
computes material cost and flexibility score, and writes state["cost_flexibility"].
Skips silently when there is no before-snapshot or no structural diff.
Does NOT overwrite state["came_from"] — routing in _route_from_cost_flexibility depends on it.
"""
from __future__ import annotations
import json
import math
from typing import Any

from nodes.evaluate import _parse_dim_mm, MATERIALS  # noqa: F401
from nodes.modify import STEEL_BEAM_PROPS, STEEL_COL_PROPS

# ── Cost parameters (USD per m³ of placed material) ──────────────────────────
_COST_PER_M3_USD: dict[str, float] = {
    "RCC":    350.0,
    "STEEL":  12_000.0,
    "TIMBER": 800.0,
}

# ── Position thresholds for column flexibility classification (metres) ────────
_CORNER_DIST_M = 0.4   # ≤ 0.4 m to any outline vertex  → "corner"
_WALL_DIST_M   = 1.0   # ≤ 1.0 m to any outline edge    → "near wall"
                        # > 1.0 m from all edges          → "mid-room"


# ── Label helpers ─────────────────────────────────────────────────────────────

def _flex_label(score: float) -> str:
    if score <= 2.0: return "Very Low"
    if score <= 4.0: return "Low"
    if score <= 6.0: return "Moderate"
    if score <= 8.0: return "High"
    return "Very High"


def _disruption_label(score: int) -> str:
    if score <= 1:  return "Negligible"
    if score <= 3:  return "Low"
    if score <= 5:  return "Moderate"
    if score <= 7:  return "Significant"
    return "High"


# ── Geometry helpers ──────────────────────────────────────────────────────────

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


# ── Element volume estimation ─────────────────────────────────────────────────

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


# ── Layout diff ───────────────────────────────────────────────────────────────

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


# ── Cost computation ──────────────────────────────────────────────────────────

def _material_cost_usd(
    added: list[dict],
    removed: list[dict],
    changed_after: list[dict],
    changed_before: list[dict],
) -> tuple[float, float, float]:
    """
    Returns (cost_added, cost_saved, net_cost).
    cost_added ≥ 0 (new material), cost_saved ≤ 0 (removed material), net = sum of both.
    """
    cost_added = 0.0
    cost_saved = 0.0

    for el in added:
        mat = el.get("attributes", {}).get("material", "RCC").upper()
        key = next((k for k in _COST_PER_M3_USD if k in mat), "RCC")
        cost_added += _element_volume_m3(el) * _COST_PER_M3_USD[key]

    for el in removed:
        mat = el.get("attributes", {}).get("material", "RCC").upper()
        key = next((k for k in _COST_PER_M3_USD if k in mat), "RCC")
        cost_saved -= _element_volume_m3(el) * _COST_PER_M3_USD[key]

    for el_a, el_b in zip(changed_after, changed_before):
        mat_a = el_a.get("attributes", {}).get("material", "RCC").upper()
        mat_b = el_b.get("attributes", {}).get("material", "RCC").upper()
        key_a = next((k for k in _COST_PER_M3_USD if k in mat_a), "RCC")
        key_b = next((k for k in _COST_PER_M3_USD if k in mat_b), "RCC")
        delta = _element_volume_m3(el_a) * _COST_PER_M3_USD[key_a] \
              - _element_volume_m3(el_b) * _COST_PER_M3_USD[key_b]
        if delta >= 0:
            cost_added += delta
        else:
            cost_saved += delta

    net = cost_added + cost_saved
    return round(cost_added, 2), round(cost_saved, 2), round(net, 2)


# ── Flexibility scoring ───────────────────────────────────────────────────────

def _single_element_flexibility(
    el_after:  dict,
    el_before: dict | None,
    is_added:   bool,
    is_removed: bool,
    outline:    list,
) -> float:
    """Flexibility score (0–10) for a single element intervention."""
    geo     = el_after.get("geometry", [])
    is_beam = len(geo) == 2
    attrs_a = el_after.get("attributes", {})
    attrs_b = (el_before.get("attributes", {}) if el_before else {})

    if is_removed:
        return 1.0

    if is_added:
        if is_beam:
            return 6.5
        pt = geo[0] if geo else [0, 0, 0]
        d  = _min_dist_to_outline(pt, outline)
        if d < _CORNER_DIST_M:
            return 8.0
        if d < _WALL_DIST_M:
            return 7.0
        return 2.0

    def _sec_str(attrs: dict, beam: bool) -> str:
        if not beam:
            return attrs.get("section") or attrs.get("dimensions") or ""
        return (
            attrs.get("section")
            or attrs.get("dimensions")
            or (
                f"{attrs.get('width','')}x{attrs.get('depth','')}"
                if (attrs.get("depth") or attrs.get("width"))
                else ""
            )
        )

    sec_a = _sec_str(attrs_a, is_beam)
    sec_b = _sec_str(attrs_b, is_beam)
    mat_a = attrs_a.get("material", "")
    mat_b = attrs_b.get("material", "")
    sec_changed = sec_a != sec_b
    mat_changed = mat_a != mat_b

    if is_beam:
        if sec_changed and not mat_changed:
            return 9.0
        if mat_changed:
            return 5.0
        return 7.0

    if sec_changed and not mat_changed:
        return 7.0
    if mat_changed:
        return 5.0
    return 6.0


def _aggregate_flexibility(
    added:          list[dict],
    removed:        list[dict],
    changed_after:  list[dict],
    changed_before: list[dict],
    outline:        list,
) -> float:
    """Weighted mean flexibility score (0–10)."""
    sw: list[tuple[float, float]] = []

    for el in removed:
        sw.append((_single_element_flexibility(el, None, False, True, outline), 3.0))

    for el in added:
        score   = _single_element_flexibility(el, None, True, False, outline)
        geo     = el.get("geometry", [])
        is_beam = len(geo) == 2
        w = 2.0 if (not is_beam and geo and _min_dist_to_outline(geo[0], outline) >= _WALL_DIST_M) else 1.0
        sw.append((score, w))

    for el_a, el_b in zip(changed_after, changed_before):
        sw.append((_single_element_flexibility(el_a, el_b, False, False, outline), 1.0))

    if not sw:
        return 10.0

    total_w = sum(w for _, w in sw)
    return round(sum(s * w for s, w in sw) / total_w, 2)


# ── Disruption scoring ────────────────────────────────────────────────────────

def _disruption_score(
    added:   list[dict],
    removed: list[dict],
    changed: list[dict],
    outline: list,
) -> int:
    """0–10 disruption score based on intervention type and spatial position."""
    score = 0
    score += min(6, len(removed) * 3)

    for el in added:
        geo     = el.get("geometry", [])
        is_beam = len(geo) == 2
        if is_beam:
            score += 1
        elif geo:
            d = _min_dist_to_outline(geo[0], outline)
            if d >= _WALL_DIST_M:
                score += 3
            elif d >= _CORNER_DIST_M:
                score += 1

    score += min(2, len(changed))
    return min(10, score)


# ── Spatial penalty ───────────────────────────────────────────────────────────

def _spatial_penalty(added: list[dict], outline: list) -> float:
    """Mean spatial intrusion index for added column elements (0.0–1.0)."""
    if not added:
        return 0.0
    col_penalties: list[float] = []
    for el in added:
        geo     = el.get("geometry", [])
        is_beam = len(geo) == 2
        if not is_beam and geo:
            d = _min_dist_to_outline(geo[0], outline)
            if d >= _WALL_DIST_M:
                col_penalties.append(1.0)
            elif d >= _CORNER_DIST_M:
                col_penalties.append(0.3)
            else:
                col_penalties.append(0.0)
    return round(sum(col_penalties) / len(col_penalties), 3) if col_penalties else 0.0


# ── Node builder ──────────────────────────────────────────────────────────────

def build_cost_flexibility_node():
    def cost_flexibility_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: COST & FLEXIBILITY")
        print(f"{'='*50}")

        layout_str = state.get("layout_json_string", "")
        before_str = (
            state.get("layout_before_change")
            or state.get("original_layout_json_string")
        )
        if not before_str:
            print("  No before-snapshot available — skipping cost/flexibility analysis.")
            state["cost_flexibility"] = None
            return state

        try:
            outline = json.loads(layout_str).get("outline", [])
        except (json.JSONDecodeError, TypeError):
            outline = []

        diff           = _detect_changes(before_str, layout_str)
        added          = diff["added"]
        removed        = diff["removed"]
        changed_after  = diff["changed_after"]
        changed_before = diff["changed_before"]

        if not added and not removed and not changed_after:
            print("  No structural changes detected — skipping cost/flexibility analysis.")
            state["cost_flexibility"] = None
            return state

        cost_added, cost_saved, net_cost = _material_cost_usd(added, removed, changed_after, changed_before)
        flex    = _aggregate_flexibility(added, removed, changed_after, changed_before, outline)
        disrupt = _disruption_score(added, removed, changed_after, outline)
        penalty = _spatial_penalty(added, outline)
        flex_lbl = _flex_label(flex)
        dis_lbl  = _disruption_label(disrupt)

        parts = []
        if added:         parts.append(f"{len(added)} added")
        if removed:       parts.append(f"{len(removed)} removed")
        if changed_after: parts.append(f"{len(changed_after)} upgraded")
        change_desc = ", ".join(parts) or "no changes"

        # Cost breakdown string
        if cost_added and cost_saved:
            cost_str = f"Added: +${cost_added:,.0f} | Saved: -${abs(cost_saved):,.0f} | Net: ${net_cost:+,.0f}"
        elif cost_added:
            cost_str = f"Cost: +${cost_added:,.0f}"
        elif cost_saved:
            cost_str = f"Saved: -${abs(cost_saved):,.0f}"
        else:
            cost_str = "Cost: $0"

        summary = (
            f"{change_desc} | "
            f"{cost_str} | "
            f"Flexibility: {flex:.1f}/10 ({flex_lbl}) | "
            f"Disruption: {disrupt}/10 ({dis_lbl})"
        )
        print(f"  {summary}")
        if penalty > 0:
            print(f"  Spatial penalty: {penalty:.2f}  (mid-room column intrusion detected)")

        state["cost_flexibility"] = {
            "cost_added_usd":    cost_added,
            "cost_saved_usd":    cost_saved,
            "net_cost_usd":      net_cost,
            "disruption_score":  disrupt,
            "disruption_label":  dis_lbl,
            "spatial_penalty":   penalty,
            "flexibility_score": flex,
            "flexibility_label": flex_lbl,
            "summary":           summary,
        }
        return state

    return cost_flexibility_node
