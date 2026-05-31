from __future__ import annotations
import json
import math
import re
from pathlib import Path
from nodes.comparison import print_diff

SETTINGS_PATH = Path(__file__).parent.parent.parent / "team_01_settings.json"
from nodes.modify import (
    STEEL_BEAM_PROPS, STEEL_COL_PROPS, DEFAULT_SECTIONS, SECTION_UPGRADE_MAP,
    BEAM_SECTION_UPGRADE, COL_SECTION_UPGRADE, BEAM_DIM_UPGRADE, COL_DIM_UPGRADE,
    BASE_MATERIALS, apply_material_override, upgrade_element_section,
    add_midspan_column, apply_minimum_sections, remove_element,
)

# ── Material library (working stress, EC2 / EC3 / EN338) ─────────────────────
MATERIALS: dict[str, dict] = {
    "RCC": {
        "E_MPa":        31_000,   # EC2, C25/30
        "density_kNm3": 25.0,
        "allow_bend_MPa":  14.2,  # EC2, fcd = 0.85 × 25 / 1.5
        "allow_comp_MPa":  14.2,  # EC2, fcd = 0.85 × 25 / 1.5
        "allow_shear_MPa":  2.8,  # EC2, VRd reinforced section
    },
    "STEEL": {
        "E_MPa":        200_000,
        "density_kNm3": 78.5,
        "allow_bend_MPa":  235.0,  # EC3, fyd = fy / γM0, S235
        "allow_comp_MPa":  235.0,  # EC3, fyd = fy / γM0, S235
        "allow_shear_MPa": 135.7,  # EC3, fvd = fy / (√3 × γM0)
    },
    "TIMBER": {
        "E_MPa":        8_000,
        "density_kNm3": 5.0,
        "allow_bend_MPa":  12.3,  # EN338 C16, fm,d = kmod × fm,k / γM = 0.8 × 16 / 1.3
        "allow_comp_MPa":  10.5,  # EN338 C16, fc,0,d = kmod × fc,0,k / γM = 0.8 × 17 / 1.3
        "allow_shear_MPa":  1.1,  # EN338 C16, fv,d = kmod × fv,k / γM = 0.8 × 1.8 / 1.3
    },
}

# ── Load assumptions ──────────────────────────────────────────────────────────
SDL_KNM2  = 3.5   # superimposed dead load: 125 mm slab + finishes + partitions
LL_KNM2   = 2.0   # live load, residential (IS 875 Part 2)
BEAM_WIDTH_MM = 300.0  # assumed beam width when not in attributes

# ── Deflection / buckling limits ──────────────────────────────────────────────
DEFL_LIMIT_LL  = 360   # L/360  live load
DEFL_LIMIT_TL  = 250   # L/250  total load
BUCKLING_SF    = 3.0   # minimum Euler buckling safety factor

# ── Utilisation thresholds for advisor feedback ────────────────────────────────
UTIL_OVERENGINEERED = 0.50  # below this → layout change possible (remove / relocate)
UTIL_APPROACHING    = 0.75  # above this → approaching limit, flag to architect


# ── Helpers ───────────────────────────────────────────────────────────────────

def _material(name: str) -> dict:
    key = name.upper().replace("-", "").replace("_", "").replace(" ", "")
    for k, v in MATERIALS.items():
        if k in key:
            return v
    return MATERIALS["RCC"]


def _parse_dim_mm(s: str) -> tuple[float, float]:
    """'300x600' → (0.300, 0.600) metres."""
    parts = str(s).lower().split("x")
    if len(parts) == 2:
        return float(parts[0]) / 1000.0, float(parts[1]) / 1000.0
    v = float(parts[0]) / 1000.0
    return v, v


def _rect_props(b: float, d: float) -> tuple[float, float, float]:
    """Area (m²), I (m⁴), r (m) for b×d rectangle, d is depth (strong axis)."""
    A = b * d
    I = b * d ** 3 / 12.0
    r = math.sqrt(I / A)
    return A, I, r


# ── Tributary geometry ────────────────────────────────────────────────────────

def _beam_trib_widths(beams: list[dict]) -> dict[str, float]:
    """Half-spacing to nearest parallel beam in the perpendicular direction."""
    h_beams, v_beams = [], []
    for bm in beams:
        g = bm["geometry"]
        if len(g) < 2:
            continue
        if abs(g[1][0] - g[0][0]) >= abs(g[1][1] - g[0][1]):
            h_beams.append(bm)
        else:
            v_beams.append(bm)

    trib: dict[str, float] = {}

    def _spacing(beams_1d: list[dict], mid_fn) -> None:
        coords = sorted({round(mid_fn(bm), 4) for bm in beams_1d})
        for bm in beams_1d:
            c = mid_fn(bm)
            idx = min(range(len(coords)), key=lambda i: abs(coords[i] - c))
            gaps = []
            if idx > 0:
                gaps.append((coords[idx] - coords[idx - 1]) / 2)
            if idx < len(coords) - 1:
                gaps.append((coords[idx + 1] - coords[idx]) / 2)
            w = sum(gaps) / len(gaps) if gaps else 2.5
            trib[bm["id"]] = max(1.0, min(4.0, w))

    _spacing(h_beams, lambda bm: (bm["geometry"][0][1] + bm["geometry"][1][1]) / 2)
    _spacing(v_beams, lambda bm: (bm["geometry"][0][0] + bm["geometry"][1][0]) / 2)
    return trib


def _column_trib_areas(columns: list[dict]) -> dict[str, float]:
    """Voronoi tributary area per column from the column grid."""
    pts = [(c["id"], float(c["geometry"][0][0]), float(c["geometry"][0][1])) for c in columns]
    xs = sorted({x for _, x, _ in pts})
    ys = sorted({y for _, _, y in pts})

    trib: dict[str, float] = {}
    for cid, x, y in pts:
        ix = xs.index(x)
        iy = ys.index(y)
        dx_l = (x - xs[ix - 1]) / 2 if ix > 0             else 0.0
        dx_r = (xs[ix + 1] - x) / 2 if ix < len(xs) - 1  else 0.0
        dy_b = (y - ys[iy - 1]) / 2 if iy > 0             else 0.0
        dy_t = (ys[iy + 1] - y) / 2 if iy < len(ys) - 1  else 0.0
        w = dx_l + dx_r
        h = dy_b + dy_t
        trib[cid] = max(1.0, w * h) if (w > 0 and h > 0) else max(1.0, max(w, h) * 2.5)
    return trib


# ── Beam checks ───────────────────────────────────────────────────────────────

def _check_beams(beams: list[dict], trib: dict[str, float], ll_kNm2: float = LL_KNM2, sdl_kNm2: float = SDL_KNM2) -> list[dict]:
    results = []
    for bm in beams:
        g = bm["geometry"]
        attrs = bm.get("attributes", {})
        mat_name = attrs.get("material", "RCC")
        mat = _material(mat_name)

        L = math.dist(g[0], g[1])
        if L < 0.05:
            continue

        d = float(attrs.get("depth", 600)) / 1000.0
        b = float(attrs.get("width", BEAM_WIDTH_MM)) / 1000.0

        # Real IPE section properties for steel; solid rect for RCC / Timber
        steel_sec = None
        if "STEEL" in mat_name.upper():
            steel_sec = STEEL_BEAM_PROPS.get(attrs.get("section", ""))

        if steel_sec:
            A      = steel_sec["A_mm2"] / 1e6    # m²
            I      = steel_sec["I_mm4"] / 1e12   # m⁴
            Wy_mm3 = steel_sec["Wy_mm3"]         # mm³
            sec_label = attrs.get("section", f"{int(b*1000)}x{int(d*1000)}")
        else:
            A, I, _ = _rect_props(b, d)
            Wy_mm3 = I / (d / 2) * 1e9          # m³ → mm³
            sec_label = f"{int(b*1000)}x{int(d*1000)}"

        E  = mat["E_MPa"] * 1e6
        tw = trib.get(bm["id"], 2.5)

        # Loads (kN/m)
        w_sw  = mat["density_kNm3"] * A
        w_dl  = sdl_kNm2 * tw
        w_ll  = ll_kNm2  * tw
        w_tot = w_sw + w_dl + w_ll

        M = w_tot * L ** 2 / 8.0

        # Bending: σ = M / Wy  (M in kN·m, Wy in mm³ → MPa)
        sigma_b = M * 1e6 / Wy_mm3

        # Shear: average τ = V / A  (MPa)
        V   = w_tot * L / 2.0
        tau = V * 1e3 / A / 1e6

        def _defl(w_kNm: float) -> float:
            return 5 * (w_kNm * 1e3) * L ** 4 / (384 * E * I) * 1e3

        d_tot = _defl(w_tot)
        d_ll  = _defl(w_ll)
        lim_tl = L * 1e3 / DEFL_LIMIT_TL
        lim_ll = L * 1e3 / DEFL_LIMIT_LL

        results.append({
            "id":               bm["id"],
            "span_m":           round(L, 3),
            "section_mm":       sec_label,
            "material":         mat_name,
            "trib_width_m":     round(tw, 2),
            "w_total_kNm":      round(w_tot, 3),
            "M_max_kNm":        round(M, 3),
            "sigma_bend_MPa":   round(sigma_b, 3),
            "allow_bend_MPa":   mat["allow_bend_MPa"],
            "bend_PASS":        sigma_b <= mat["allow_bend_MPa"],
            "tau_MPa":          round(tau, 4),
            "allow_shear_MPa":  mat["allow_shear_MPa"],
            "shear_PASS":       tau <= mat["allow_shear_MPa"],
            "delta_total_mm":   round(d_tot, 3),
            "delta_LL_mm":      round(d_ll, 3),
            "limit_TL_mm":      round(lim_tl, 3),
            "limit_LL_mm":      round(lim_ll, 3),
            "defl_TL_PASS":     d_tot <= lim_tl,
            "defl_LL_PASS":     d_ll  <= lim_ll,
        })
    return results


# ── Column checks ─────────────────────────────────────────────────────────────

def _check_columns(columns: list[dict], trib: dict[str, float], ll_kNm2: float = LL_KNM2, sdl_kNm2: float = SDL_KNM2) -> list[dict]:
    results = []
    for col in columns:
        attrs = col.get("attributes", {})
        mat_name = attrs.get("material", "RCC")
        mat = _material(mat_name)

        H    = float(attrs.get("height", 3.5))
        b, d = _parse_dim_mm(attrs.get("dimensions", "300x300"))

        # Real HSS section properties for steel; solid rect for RCC / Timber
        steel_sec = None
        if "STEEL" in mat_name.upper():
            steel_sec = STEEL_COL_PROPS.get(attrs.get("section", ""))

        if steel_sec:
            A     = steel_sec["A_mm2"]    / 1e6    # m²
            I_min = steel_sec["I_mm4"]    / 1e12   # m⁴ (HSS symmetric, I_x = I_y)
            r_min = steel_sec["r_min_mm"] / 1000.0 # m
            sec_label = attrs.get("section", f"{int(b*1000)}x{int(d*1000)}")
        else:
            A, I_strong, _ = _rect_props(b, d)
            _, I_weak,   _ = _rect_props(d, b)
            I_min = min(I_strong, I_weak)
            r_min = math.sqrt(I_min / A)
            sec_label = f"{int(b*1000)}x{int(d*1000)}"

        E  = mat["E_MPa"] * 1e6
        ta = trib.get(col["id"], 9.0)

        P_floor = (sdl_kNm2 + ll_kNm2) * ta
        P_self  = mat["density_kNm3"] * A * H
        P_total = P_floor + P_self

        sigma_c = P_total * 1e3 / A / 1e6

        Le  = 0.65 * H
        lam = Le / r_min

        P_cr = math.pi ** 2 * E * I_min / Le ** 2 / 1e3
        SF   = P_cr / P_total if P_total > 0 else float("inf")

        results.append({
            "id":               col["id"],
            "height_m":         H,
            "section_mm":       sec_label,
            "material":         mat_name,
            "trib_area_m2":     round(ta, 2),
            "P_total_kN":       round(P_total, 2),
            "sigma_comp_MPa":   round(sigma_c, 4),
            "allow_comp_MPa":   mat["allow_comp_MPa"],
            "stress_PASS":      sigma_c <= mat["allow_comp_MPa"],
            "slenderness":      round(lam, 1),
            "P_cr_kN":          round(P_cr, 2),
            "SF_buckling":      round(SF, 2),
            "buckling_PASS":    SF >= BUCKLING_SF,
        })
    return results


# ── What-if removal simulation ────────────────────────────────────────────────

def _extract_removal_ids(messages: list[dict]) -> list[str]:
    """Return element IDs from the user's original request only (not tool results)."""
    if not messages:
        return []
    # Extract only the "User request:" portion of the first message
    content = messages[0].get("content", "")
    if "User request:" in content:
        start = content.index("User request:") + len("User request:")
        end   = content.find("\n\n", start)
        text  = content[start:end].strip() if end > start else content[start:].strip()
    else:
        text = content
    if not any(kw in text.lower() for kw in ("remov", "delet", "what if", "without")):
        return []
    return list(dict.fromkeys(
        m.upper() for m in re.findall(r'\b([A-Za-z]\w*_\d+)\b', text)
    ))


def _build_beam_index(beams: list[dict]) -> dict[tuple, list[dict]]:
    idx: dict[tuple, list[dict]] = {}
    for bm in beams:
        for pt in bm["geometry"]:
            idx.setdefault(tuple(pt), []).append(bm)
    return idx


def _trace_span(
    floating_pos: tuple,
    beam_idx: dict[tuple, list[dict]],
    removed_positions: set[tuple],
    remaining_positions: set[tuple],
    visited: set[str],
    initial_dist: float,
) -> float:
    """Walk beam chain from floating_pos through removed columns; return total span."""
    total = initial_dist
    current = floating_pos
    for _ in range(20):
        if current in remaining_positions:
            break
        moved = False
        for bm in beam_idx.get(current, []):
            if bm["id"] in visited:
                continue
            visited.add(bm["id"])
            p1, p2 = tuple(bm["geometry"][0]), tuple(bm["geometry"][1])
            total += math.dist(p1, p2)
            current = p2 if p1 == current else p1
            moved = True
            break
        if not moved:
            break
    return total


def simulate_what_if_removal(
    layout_json_string: str,
    remove_ids: list[str],
    base_trib: dict[str, float],
    ll_kNm2: float = LL_KNM2,
    sdl_kNm2: float = SDL_KNM2,
) -> dict:
    """Re-evaluate beams whose endpoint columns are removed, extending their spans."""
    layout    = json.loads(layout_json_string)
    structure = layout.get("structure", [])

    # Filter to IDs that are actual columns in this layout
    valid_cols = {el["id"] for el in structure if len(el.get("geometry", [])) == 1}
    remove_ids = [i for i in remove_ids if i in valid_cols]
    if not remove_ids:
        return {"error": f"No valid column IDs found in remove list"}

    remove_set = set(remove_ids)

    removed_positions: set[tuple] = {
        tuple(el["geometry"][0])
        for el in structure
        if el["id"] in remove_set and len(el.get("geometry", [])) == 1
    }
    if not removed_positions:
        return {"error": f"No columns found for IDs: {remove_ids}"}

    remaining_positions: set[tuple] = {
        tuple(el["geometry"][0])
        for el in structure
        if el["id"] not in remove_set and len(el.get("geometry", [])) == 1
    }

    all_beams = [el for el in structure if len(el.get("geometry", [])) == 2]
    beam_idx  = _build_beam_index(all_beams)

    results: list[dict] = []
    visited: set[str] = set()

    for bm in all_beams:
        p1, p2 = tuple(bm["geometry"][0]), tuple(bm["geometry"][1])
        p1_removed = p1 in removed_positions
        p2_removed = p2 in removed_positions
        if not p1_removed and not p2_removed:
            continue
        if bm["id"] in visited:
            continue
        visited.add(bm["id"])

        attrs    = bm.get("attributes", {})
        mat_name = attrs.get("material", "RCC")
        mat      = _material(mat_name)
        d        = float(attrs.get("depth", 600)) / 1000.0
        b        = BEAM_WIDTH_MM / 1000.0

        # Real IPE properties for steel; solid rect for RCC / Timber
        steel_sec = None
        if "STEEL" in mat_name.upper():
            steel_sec = STEEL_BEAM_PROPS.get(attrs.get("section", ""))

        if steel_sec:
            A      = steel_sec["A_mm2"] / 1e6
            I      = steel_sec["I_mm4"] / 1e12
            Wy_mm3 = steel_sec["Wy_mm3"]
        else:
            A, I, _ = _rect_props(b, d)
            Wy_mm3 = I / (d / 2) * 1e9

        E  = mat["E_MPa"] * 1e6
        tw = base_trib.get(bm["id"], 2.5)

        orig_span = math.dist(p1, p2)

        if p1_removed and p2_removed:
            results.append({
                "id": bm["id"], "original_span_m": round(orig_span, 3),
                "effective_span_m": None, "note": "Both endpoints removed — unsupported",
                "bend_PASS": False, "shear_PASS": False,
                "defl_TL_PASS": False, "defl_LL_PASS": False,
            })
            continue

        floating = p1 if p1_removed else p2
        eff_span = _trace_span(floating, beam_idx, removed_positions,
                               remaining_positions, visited, orig_span)

        w_sw  = mat["density_kNm3"] * A
        w_dl  = sdl_kNm2 * tw
        w_ll  = ll_kNm2  * tw
        w_tot = w_sw + w_dl + w_ll

        M       = w_tot * eff_span ** 2 / 8.0
        sigma_b = M * 1e6 / Wy_mm3
        tau     = (w_tot * eff_span / 2) * 1e3 / A / 1e6

        def _d(w: float) -> float:
            return 5 * (w * 1e3) * eff_span ** 4 / (384 * E * I) * 1e3

        d_tot = _d(w_tot);  d_ll = _d(w_ll)
        lim_tl = eff_span * 1e3 / DEFL_LIMIT_TL
        lim_ll = eff_span * 1e3 / DEFL_LIMIT_LL

        results.append({
            "id":               bm["id"],
            "original_span_m":  round(orig_span, 3),
            "effective_span_m": round(eff_span, 3),
            "section_mm":       f"{int(b*1000)}x{int(d*1000)}",
            "M_max_kNm":        round(M, 3),
            "sigma_bend_MPa":   round(sigma_b, 3),
            "allow_bend_MPa":   mat["allow_bend_MPa"],
            "bend_PASS":        sigma_b <= mat["allow_bend_MPa"],
            "tau_MPa":          round(tau, 4),
            "shear_PASS":       tau <= mat["allow_shear_MPa"],
            "delta_total_mm":   round(d_tot, 3),
            "delta_LL_mm":      round(d_ll, 3),
            "limit_TL_mm":      round(lim_tl, 3),
            "limit_LL_mm":      round(lim_ll, 3),
            "defl_TL_PASS":     d_tot <= lim_tl,
            "defl_LL_PASS":     d_ll  <= lim_ll,
            "note": f"span {orig_span:.1f}m → {eff_span:.1f}m after removing {', '.join(remove_ids)}",
        })

    failures = [r for r in results if not all(
        r.get(k, False) for k in ("bend_PASS", "shear_PASS", "defl_TL_PASS", "defl_LL_PASS")
    )]
    return {
        "simulation":    "what_if_removal",
        "removed_ids":   remove_ids,
        "affected_beams": results,
        "summary": {
            "affected": len(results),
            "failures": len(failures),
            "failed_ids": [r["id"] for r in failures],
            "overall_PASS": not failures,
        },
    }


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_structure(layout_json_string: str, ll_kNm2: float = LL_KNM2, sdl_kNm2: float = SDL_KNM2) -> dict:
    layout    = json.loads(layout_json_string)
    structure = layout.get("structure", [])

    beams   = [s for s in structure if len(s.get("geometry", [])) == 2]
    columns = [s for s in structure if len(s.get("geometry", [])) == 1]

    b_trib = _beam_trib_widths(beams)
    c_trib = _column_trib_areas(columns)

    beam_results = _check_beams(beams, b_trib, ll_kNm2, sdl_kNm2)
    col_results  = _check_columns(columns, c_trib, ll_kNm2, sdl_kNm2)

    b_fail = [r for r in beam_results if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"])]
    c_fail = [r for r in col_results  if not (r["stress_PASS"] and r["buckling_PASS"])]

    return {
        "beams":   beam_results,
        "columns": col_results,
        "summary": {
            "total_beams":       len(beam_results),
            "beam_failures":     len(b_fail),
            "failed_beam_ids":   [r["id"] for r in b_fail],
            "total_columns":     len(col_results),
            "column_failures":   len(c_fail),
            "failed_column_ids": [r["id"] for r in c_fail],
            "overall_PASS":      not b_fail and not c_fail,
        },
    }




def _build_failure_alternatives(
    result: dict,
    remove_ids: list[str],
    current_mat: str,
) -> list[str]:
    """Derive concrete, numbered alternatives from the actual failure data."""
    alts: list[str] = []
    next_tier = SECTION_UPGRADE_MAP.get(current_mat)

    # ── What-if failures ──────────────────────────────────────────────────────
    whatif = result.get("what_if")
    if whatif and not whatif["summary"].get("overall_PASS", True):
        removed = ", ".join(remove_ids)
        for r in whatif.get("affected_beams", []):
            fail = not all(r.get(k, True) for k in ("bend_PASS", "shear_PASS", "defl_TL_PASS", "defl_LL_PASS"))
            if not fail:
                continue
            bid  = r["id"]
            eff  = r.get("effective_span_m")
            orig = r.get("original_span_m", "?")
            if eff:
                mid = round(eff / 2, 2)
                alts.append(
                    f"Add intermediate column at midpoint of {bid} "
                    f"(span {orig}m → {mid}m each side)"
                )
                alts.append(
                    f"Replace {bid} with a deeper section to carry {eff}m span "
                    f"(S={r.get('sigma_bend_MPa','?')} > {r.get('allow_bend_MPa','?')} MPa)"
                )
            else:
                alts.append(f"Both endpoints of {bid} removed — add new support column")
        alts.append(f"Add a transfer beam to redirect load path around {removed}")
        return alts[:4]

    # ── Regular beam failures ─────────────────────────────────────────────────
    beam_fails = [
        r for r in result.get("beams", [])
        if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"])
    ]
    col_fails = [
        r for r in result.get("columns", [])
        if not (r["stress_PASS"] and r["buckling_PASS"])
    ]

    # Auto-upgrade all failing beams through the section chain
    if beam_fails:
        n = len(beam_fails)
        alts.append(f"Increase the {n} failing beam{'s' if n > 1 else ''} to the next size up — recommended")

    # Per-element beam upgrades (Steel IPE, RCC dims, Timber dims) — most targeted fix
    for r in beam_fails:
        cur_sec = r.get("section_mm", "")
        if cur_sec in BEAM_SECTION_UPGRADE:
            next_name, _, _ = BEAM_SECTION_UPGRADE[cur_sec]
            alts.append(f"Upgrade {r['id']} from {cur_sec} to {next_name}")
        elif cur_sec in BEAM_DIM_UPGRADE:
            next_name, _, _ = BEAM_DIM_UPGRADE[cur_sec]
            alts.append(f"Upgrade {r['id']} from {cur_sec} to {next_name}")
        if len(alts) >= 2:
            break

    # Auto-upgrade all failing columns through the section chain
    if col_fails and not beam_fails:
        n = len(col_fails)
        alts.append(f"Increase the {n} failing column{'s' if n > 1 else ''} to the next size up — recommended")

    # Per-element column upgrades
    for r in col_fails:
        cur_sec = r.get("section_mm", "")
        if cur_sec in COL_SECTION_UPGRADE:
            next_name, _ = COL_SECTION_UPGRADE[cur_sec]
            alts.append(f"Upgrade {r['id']} from {cur_sec} to {next_name}")
        elif cur_sec in COL_DIM_UPGRADE:
            alts.append(f"Upgrade {r['id']} from {cur_sec} to {COL_DIM_UPGRADE[cur_sec]}")
        if len(alts) >= 2:
            break

    # Midspan column — always available for failing beams
    for r in beam_fails:
        mid = round(r["span_m"] / 2, 2)
        alts.append(
            f"Add midspan column under beam {r['id']} "
            f"(span {r['span_m']}m → {mid}m each side)"
        )
        if len(alts) >= 3:
            break

    # Global material switch (all framing) — offered when at top tier or no upgrade available
    base = next((m for m in BASE_MATERIALS if current_mat.startswith(m)), "RCC")
    if len(alts) < 4:
        for switch_mat in [m for m in BASE_MATERIALS if m != base]:
            alts.append(f"Switch all framing to {switch_mat}")
            if len(alts) >= 4:
                break

    # Global tier upgrade
    if next_tier and len(alts) < 4:
        ns = DEFAULT_SECTIONS[next_tier]
        alts.append(
            f"Upgrade all to {next_tier} "
            f"(beam {ns['beam_width_mm']}x{ns['beam_depth_mm']}mm | col {ns['col_dims']}mm)"
        )

    for r in col_fails:
        if not r.get("buckling_PASS"):
            alts.append(
                f"Add lateral bracing to column {r['id']} "
                f"(buckling SF={r['SF_buckling']} < {BUCKLING_SF})"
            )
        elif not r.get("stress_PASS") and r.get("section_mm", "") not in COL_SECTION_UPGRADE:
            alts.append(
                f"Add adjacent column to share load from {r['id']} "
                f"(S={r['sigma_comp_MPa']} > {r['allow_comp_MPa']} MPa)"
            )

    return alts[:4]



def _get_user_request(messages: list) -> str:
    """Extract the user's raw request text from the first context message."""
    if not messages:
        return ""
    content = messages[0].get("content", "").lower()
    marker = "user request:"
    if marker in content:
        start = content.index(marker) + len(marker)
        end = content.find("layout summaries:", start)
        return content[start: end if end > start else start + 300].strip()
    return content[:300]


def _detect_find_min(messages: list) -> str | None:
    """Return the material name if the user's prompt asks for minimum sections for a specific material."""
    text = _get_user_request(messages)
    if not any(kw in text for kw in ("minimum", "find min", "minimum sufficient", "optimiz")):
        return None
    if "steel" in text:
        return "STEEL"
    if "timber" in text:
        return "TIMBER"
    if "rcc" in text or "concrete" in text:
        return "RCC"
    return None


def _ask_sdl_ll(state: dict) -> None:
    """Prompt for SDL and LL, update state in place, and persist to settings."""
    cur_sdl = state.get("sdl_kNm2") or SDL_KNM2
    print(f"\nWhat kind of floor build-up are you designing? [current: {cur_sdl} kN/m²]")
    print("  1. Light timber floor — 1.5 kN/m²  (wood framing, light finishes)")
    print("  2. Light concrete     — 2.5 kN/m²  (thin slab, minimal finishes)")
    print("  3. Standard           — 3.5 kN/m²  (125mm slab + finishes + partitions)")
    print("  4. Heavy              — 5.0 kN/m²  (thick slab, heavy finishes, raised floor)")
    print("  [Enter] — keep current")
    raw_sdl = input("Your choice [1-4 or Enter]: ").strip()
    state["sdl_kNm2"] = {"1": 1.5, "2": 2.5, "3": 3.5, "4": 5.0}.get(raw_sdl, cur_sdl)
    print(f"  Floor load: {state['sdl_kNm2']} kN/m²")

    cur_ll = state.get("live_load_kNm2") or LL_KNM2
    print(f"\nHow will this space be used? [current: {cur_ll} kN/m²]")
    print("  1. Homes / apartments  — 2.0 kN/m²")
    print("  2. Offices             — 3.0 kN/m²")
    print("  3. Retail / public     — 5.0 kN/m²")
    print("  [Enter] — keep current")
    raw_ll = input("Your choice [1-3 or Enter]: ").strip()
    state["live_load_kNm2"] = {"1": 2.0, "2": 3.0, "3": 5.0}.get(raw_ll, cur_ll)
    print(f"  Live load: {state['live_load_kNm2']} kN/m²")

    try:
        SETTINGS_PATH.write_text(
            json.dumps({"sdl_kNm2": state["sdl_kNm2"], "live_load_kNm2": state["live_load_kNm2"]}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


_INTERPRET_SYSTEM = """You are a structural advisor helping an architect during early design. You are given structural evaluation results: each element with its ID, type (beam or column), section, and utilisation % (100% = at the structural limit), plus a "May be removable" list. Write a concise advisory note.

CRITICAL: If overall_PASS is false, your FIRST sentence MUST identify the structure as failing and name the specific failing element IDs from the data. Do not discuss optimisation or underutilised elements until all failures are addressed.

USE ONLY THE DATA YOU ARE GIVEN:
- Mention only element IDs that appear in the evaluation data. Never invent, guess, or complete an ID. The example IDs below are illustrative format only — never repeat them as if they were real.
- Keep element types exactly as given — never call a beam a column or a column a beam.
- Quote utilisation figures and spans exactly as given. Never invent a number.
- Do NOT name rooms or locations ("living room", "kitchen", "staircase", "corridor") — the geometry does not tell you the room. Describe position only by what the data supports: element IDs, spans, and which elements are adjacent or clustered by their coordinates.

UTILISATION THRESHOLDS — use consistently:
- Below 50%: over-engineered. Suggest a specific LAYOUT change — remove the element (only if it is on the "May be removable" list) or open up the span. (Over-engineered means LOW utilisation only — never call a failing or near-limit element over-engineered.)
- 50–75%: working range — note it positively.
- Above 75%: approaching limit — flag it clearly.
- Failures (100%+): must fix. Give 2 concrete options using exact element IDs.

For UNDERUTILISED columns (<70%): use the "May be removable" list to say what happens if removed, e.g. "Column <ID> is at <N>% — removing it keeps the connected beams within limits" or, if it needs an upgrade, "removing <ID> extends beam <ID> to <span> — a larger section would be needed." The "May be removable" list is exhaustive — only name columns that appear on it; never suggest removing any element not on that list, and never suggest removing a perimeter column. Columns marked KEEP must never be suggested for removal, even at low utilisation.

For UNDERUTILISED beams (<70%): ask whether that span is actually needed.

Structure as a conversation, not a report:
- Line 1: one-sentence overall verdict in plain language.
- 2-3 bullets: the most important observations, each tied to a real element ID and its number.
- 1 closing question: ONE specific question that moves the design forward, referencing real element IDs and their utilisation or proximity from the data — never a generic question, never a named room. (Format example only, do not reuse the IDs: "Columns <ID> and <ID> are both under 25% and sit close together — do you need both?")

If everything passes and some elements are over-engineered: end with "Type 'right-size sections' or pick option 1 in the menu to find the minimum that still works." then still ask the question.

Reply with JSON only: {"action":"final","final_response":"your advisory here","tool_calls":[]}"""


def _beam_utilisation(b: dict) -> float:
    return max(
        b.get("sigma_bend_MPa",  0) / max(b.get("allow_bend_MPa",  0.001), 0.001),
        b.get("tau_MPa",         0) / max(b.get("allow_shear_MPa", 0.001), 0.001),
        b.get("delta_LL_mm",     0) / max(b.get("limit_LL_mm",     0.001), 0.001),
        b.get("delta_total_mm",  0) / max(b.get("limit_TL_mm",     0.001), 0.001),
    )


def _col_utilisation(c: dict) -> float:
    return max(
        c.get("sigma_comp_MPa", 0) / max(c.get("allow_comp_MPa", 0.001), 0.001),
        3.0 / max(c.get("SF_buckling", 99), 0.001),
    )


def _precompute_removal_hints(
    result: dict,
    layout_str: str,
    ll_kNm2: float,
    sdl_kNm2: float,
) -> dict:
    """
    For underutilised elements (below UTIL_OVERENGINEERED), compute removal impact.
    Returns {"columns": [...], "beams": [...]} each capped at 3 entries.
    """
    # ── COLUMNS ──────────────────────────────────────────────────────────────
    # Build a set of perimeter column ids from the layout so we never suggest removing them
    _perimeter_ids: set[str] = set()
    if layout_str:
        try:
            _layout_tmp = json.loads(layout_str)
            _all_cols = [
                el for el in _layout_tmp.get("structure", [])
                if len(el.get("geometry", [])) == 1
            ]
            if _all_cols:
                _xs = [el["geometry"][0][0] for el in _all_cols]
                _ys = [el["geometry"][0][1] for el in _all_cols]
                _min_x, _max_x = min(_xs), max(_xs)
                _min_y, _max_y = min(_ys), max(_ys)
                for _el in _all_cols:
                    _x, _y = _el["geometry"][0][0], _el["geometry"][0][1]
                    if (
                        _x == _min_x or _x == _max_x
                        or _y == _min_y or _y == _max_y
                        or _el.get("attributes", {}).get("type") == "perimeter"
                    ):
                        _perimeter_ids.add(_el["id"])
        except Exception:
            pass

    col_candidates = sorted(
        [
            c for c in result.get("columns", [])
            if _col_utilisation(c) < UTIL_OVERENGINEERED
            and c["id"] not in _perimeter_ids
        ],
        key=_col_utilisation,
    )
    col_hints = []
    if col_candidates and layout_str:
        try:
            layout    = json.loads(layout_str)
            structure = layout.get("structure", [])
            beams     = [el for el in structure if len(el.get("geometry", [])) == 2]
            b_trib    = _beam_trib_widths(beams)
        except Exception:
            b_trib = {}

        for c in col_candidates[:5]:
            col_id = c["id"]
            try:
                whatif = simulate_what_if_removal(layout_str, [col_id], b_trib, ll_kNm2, sdl_kNm2)
            except Exception:
                continue
            ws       = whatif.get("summary", {})
            affected = whatif.get("affected_beams", [])
            safe     = ws.get("overall_PASS", True) and "error" not in whatif
            worst    = max(affected, key=lambda b: b.get("effective_span_m") or 0) if affected else None

            hint: dict = {
                "type": "column", "element_id": col_id,
                "utilisation_pct": round(_col_utilisation(c) * 100, 1),
                "load_kN": c.get("P_total_kN", 0),
                "removal_safe": safe,
            }
            if worst and worst.get("effective_span_m"):
                orig, eff = worst.get("original_span_m", "?"), worst.get("effective_span_m", "?")
                hint["note"] = (
                    f"safe — beam {worst['id']} extends {orig}m→{eff}m and stays within limits"
                    if safe else
                    f"extends beam {worst['id']} {orig}m→{eff}m — larger section needed"
                )
            else:
                hint["note"] = "safe to remove" if safe else "removal not recommended"
            col_hints.append(hint)

    # ── BEAMS ─────────────────────────────────────────────────────────────────
    beam_hints = []
    beam_candidates = sorted(
        [b for b in result.get("beams", []) if _beam_utilisation(b) < UTIL_OVERENGINEERED],
        key=_beam_utilisation,
    )[:3]
    for b in beam_candidates:
        beam_hints.append({
            "type": "beam", "element_id": b["id"],
            "utilisation_pct": round(_beam_utilisation(b) * 100, 1),
            "span_m": b.get("span_m", "?"),
            "note": f"removing this {b.get('span_m','?')}m span — check if this connection is still needed",
        })

    return {"columns": col_hints, "beams": beam_hints}


def _format_summary_for_llm(summary: dict) -> str:
    """Flat plain-text table — easier for small models than nested JSON."""
    thresh = summary.get("thresholds", {})
    lines = [
        f"Overall: {'PASS' if summary['overall_PASS'] else 'FAIL'}",
        f"Beams: {summary['n_beams']}  Columns: {summary['n_columns']}",
        f"Thresholds: over-engineered <{thresh.get('over_engineered_pct', 50)}%  "
        f"approaching >{thresh.get('approaching_limit_pct', 75)}%",
        "",
        f"{'ID':<10} {'Type':<8} {'Util%':>6}  {'Fails'}",
        f"{'-'*10} {'-'*8} {'-'*6}  {'-'*20}",
    ]
    for b in summary.get("critical_beams", []):
        fails = ", ".join(b.get("fails", [])) or "ok"
        lines.append(f"{b['id']:<10} {'beam':<8} {b['utilisation_pct']:>6.1f}  {fails}")
    hint_ids = {h["element_id"] for h in summary.get("removal_hints", [])}
    for c in summary.get("critical_columns", []):
        fails = ", ".join(c.get("fails", [])) or "ok"
        keep = "" if c["id"] in hint_ids else "  KEEP — not removable"
        lines.append(f"{c['id']:<10} {'column':<8} {c['utilisation_pct']:>6.1f}  {fails}{keep}")
    for b in summary.get("underutilised_beams", []):
        lines.append(f"{b['id']:<10} {'beam':<8} {b['utilisation_pct']:>6.1f}  (underutilised)")
    hints = summary.get("removal_hints", [])
    if hints:
        lines.append("")
        lines.append("May be removable (do not suggest removing any element not on this list):")
        for h in hints:
            lines.append(f"  {h['element_id']} ({h['type']}): {h.get('note', '')}")
    return "\n".join(lines)


def _interpret_evaluation(
    llm,
    result: dict,
    layout_str: str = "",
    ll: float = LL_KNM2,
    sdl: float = SDL_KNM2,
    removal_hints: list | None = None,
) -> str:
    """LLM-generated plain-language interpretation with layout-level suggestions."""
    beams   = result.get("beams",   [])
    columns = result.get("columns", [])
    overall = result.get("summary", {}).get("overall_PASS", True)

    beams_ranked   = sorted(beams,   key=_beam_utilisation, reverse=True)
    columns_ranked = sorted(columns, key=_col_utilisation,  reverse=True)

    if removal_hints is None:
        removal_hints = _precompute_removal_hints(result, layout_str, ll, sdl)

    summary = {
        "overall_PASS":    overall,
        "thresholds":      {"over_engineered_pct": 50, "approaching_limit_pct": 75},
        "n_beams":         len(beams),
        "n_columns":       len(columns),
        "critical_beams":  [
            {
                "id": b["id"], "span_m": b["span_m"], "section": b["section_mm"],
                "utilisation_pct": round(_beam_utilisation(b) * 100, 1),
                "fails": [k for k in ["bend_PASS", "shear_PASS", "defl_LL_PASS", "defl_TL_PASS"]
                          if not b.get(k, True)],
            }
            for b in beams_ranked[:4]
        ],
        "critical_columns": [
            {
                "id": c["id"], "section": c["section_mm"],
                "load_kN": c["P_total_kN"],
                "utilisation_pct": round(_col_utilisation(c) * 100, 1),
                "fails": [k for k in ["stress_PASS", "buckling_PASS"] if not c.get(k, True)],
            }
            for c in columns_ranked[:4]
        ],
        "underutilised_beams": [
            {"id": b["id"], "utilisation_pct": round(_beam_utilisation(b) * 100, 1)}
            for b in beams_ranked if _beam_utilisation(b) < UTIL_OVERENGINEERED
        ],
        "removal_hints": (removal_hints or {}).get("columns", []) + (removal_hints or {}).get("beams", []),
    }

    try:
        raw = llm.invoke([
            {"role": "system", "content": _INTERPRET_SYSTEM},
            {"role": "user",   "content": f"Structural evaluation:\n{_format_summary_for_llm(summary)}"},
        ])
        data = json.loads(raw.content)
        response = data.get("final_response", "")
        # Strip any XML/HTML tags that small models sometimes echo back
        import re as _re
        return _re.sub(r"<[^>]+>", "", response).strip()
    except Exception as e:
        print(f"[interpret] LLM unavailable ({e})")
        return ""


def build_evaluate_node(llm):
    """Structural first-principles check node."""

    def evaluate_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: EVALUATE")
        print(f"{'='*50}")

        # If routing forced us here despite reason giving a (wrong) direct answer,
        # discard it so the evaluation table is the sole output
        if state.get("came_from") == "reason" and state.get("final_response") and state.get("evaluation_result") is None:
            state["final_response"] = None

        # Skip full evaluation when tag_and_audit just generated a fresh grid
        if state.get("came_from") == "tag_and_audit":
            layout = json.loads(state["layout_json_string"])
            n = len(layout.get("structure", []))
            state["final_response"] = f"Structural grid generated — {n} elements added to edited layout."
            return state

        # Read came_from before prompt block so it gates which prompts appear
        came_from = state.get("came_from")

        # Human-in-the-loop: ask material + SDL + LL on every fresh evaluate pass
        # Skip only when re-evaluating after an already-confirmed structural change
        if came_from != "structural_change":
            # Auto-detect "find minimum for [material]" from the user's original prompt
            auto_min_mat = _detect_find_min(state.get("messages", []))
            if auto_min_mat:
                print(f"\nRight-sizing sections for {auto_min_mat}...")
                state["material_override"] = auto_min_mat
                _ask_sdl_ll(state)
                state["pending_structural_change"] = {"type": "find_minimum", "material": auto_min_mat}
                state["layout_before_change"] = state["layout_json_string"]
                return state

            current = state.get("material_override") or "RCC"
            base_current = next((m for m in BASE_MATERIALS if current.startswith(m)), "RCC")
            tier_label = current[len(base_current):]
            tier_note = f" [{tier_label[1:]} tier]" if tier_label else ""
            print(f"\nWhat structural material are you working with? [current: {current}{tier_note}]")
            for i, mat in enumerate(BASE_MATERIALS, 1):
                active = base_current == mat
                display_sec = DEFAULT_SECTIONS.get(current if active else mat, DEFAULT_SECTIONS[mat])
                marker = f"  ← active{tier_note}" if active else ""
                print(f"  {i}. {mat:6s} — beam {display_sec['beam_width_mm']}x{display_sec['beam_depth_mm']}mm | col {display_sec['col_dims']}mm{marker}")
            print("  4. Right-size sections — find the minimum that still works")
            print("  [Enter] — keep current")
            raw = input("Your choice [1/2/3/4 or RCC/STEEL/TIMBER]: ").strip().upper()
            lookup = {"1": "RCC", "2": "STEEL", "3": "TIMBER"}
            if raw == "4":
                print("\nWhich material should I optimise for?")
                for i, mat in enumerate(BASE_MATERIALS, 1):
                    xs_sec = DEFAULT_SECTIONS.get(f"{mat}_XS", DEFAULT_SECTIONS[mat])
                    print(f"  {i}. {mat:6s} — starting from {xs_sec['beam_width_mm']}x{xs_sec['beam_depth_mm']}mm beams | {xs_sec['col_dims']}mm cols")
                raw2 = input("Your choice [1/2/3 or RCC/STEEL/TIMBER]: ").strip().upper()
                selected = lookup.get(raw2) or (raw2 if raw2 in BASE_MATERIALS else None) or "RCC"
                state["material_override"] = selected
                _ask_sdl_ll(state)
                state["pending_structural_change"] = {"type": "find_minimum", "material": selected}
                state["layout_before_change"] = state["layout_json_string"]
                return state
            else:
                selected = lookup.get(raw) or (raw if raw in BASE_MATERIALS else None)
                if selected:
                    state["material_override"] = selected

            _ask_sdl_ll(state)

        material_override = state.get("material_override")
        ll  = state.get("live_load_kNm2") or LL_KNM2
        sdl = state.get("sdl_kNm2") or SDL_KNM2

        # After a structural change the layout already has the change applied — evaluate as-is
        if came_from == "structural_change":
            print(f"\nRe-checking the structure after changes...")
            layout_str = state["layout_json_string"]
        elif material_override:
            print(f"\nRunning structural checks for {material_override}...")
            layout_str = apply_material_override(state["layout_json_string"], material_override)
            state["layout_json_string"] = layout_str
        else:
            print("\nRunning structural checks...")
            layout_str = state["layout_json_string"]

        result  = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
        summary = result["summary"]
        current_mat = state.get("material_override") or "RCC"

        # Tier upgrade prompt (one offer per evaluate pass; each accepted upgrade is one modify cycle)
        if not summary.get("overall_PASS") and came_from != "structural_change":
            next_tier = SECTION_UPGRADE_MAP.get(current_mat)
            if next_tier:
                next_sec = DEFAULT_SECTIONS[next_tier]
                print(
                    f"\nThe current {current_mat} sections aren't quite holding. "
                    f"Step up to {next_tier.replace('_', ' ')} "
                    f"(beams {next_sec['beam_width_mm']}x{next_sec['beam_depth_mm']}mm "
                    f"| cols {next_sec['col_dims']}mm)?"
                )
                if input("Try it? [y/N]: ").strip().lower() == "y":
                    state["evaluation_result"] = json.dumps(result)
                    state["pending_structural_change"] = {"type": "tier_upgrade", "tier": next_tier}
                    state["layout_before_change"] = layout_str
                    return state

        # Assemble evaluation text
        lines = [
            f"Structural check: {'PASS' if summary['overall_PASS'] else 'FAIL'}",
            f"Beams  : {summary['total_beams']} checked, {summary['beam_failures']} failed",
            f"Columns: {summary['total_columns']} checked, {summary['column_failures']} failed",
        ]

        # What-if simulation: detect removal intent in messages
        remove_ids = _extract_removal_ids(state.get("messages", []))
        if remove_ids:
            layout    = json.loads(layout_str)
            structure = layout.get("structure", [])
            col_ids   = {el["id"] for el in structure if len(el.get("geometry", [])) == 1}
            beam_ids  = {el["id"] for el in structure if len(el.get("geometry", [])) == 2}

            remove_cols  = [i for i in remove_ids if i in col_ids]
            remove_beams = [i for i in remove_ids if i in beam_ids]

            if remove_cols:
                # ── Column removal: full span-extension simulation ────────────
                beams  = [s for s in structure if len(s.get("geometry", [])) == 2]
                b_trib = _beam_trib_widths(beams)
                whatif = simulate_what_if_removal(layout_str, remove_cols, b_trib, ll_kNm2=ll, sdl_kNm2=sdl)
                result["what_if"] = whatif
                ws = whatif.get("summary", {})
                if not ws.get("overall_PASS", True):
                    result["summary"]["overall_PASS"] = False
                    summary = result["summary"]
                lines.append("")
                lines.append(f"WHAT-IF: remove {', '.join(remove_cols)}")
                lines.append(f"  Affected beams : {ws.get('affected', 0)}")
                lines.append(f"  Failures       : {ws.get('failures', 0)}")
                if ws.get("failed_ids"):
                    lines.append(f"  Failed         : {', '.join(ws['failed_ids'])}")
                for r in whatif.get("affected_beams", []):
                    flag = ""
                    if not r.get("bend_PASS", True):
                        flag += f"  BEND FAIL S={r.get('sigma_bend_MPa','?')}>{r.get('allow_bend_MPa','?')}MPa"
                    if not r.get("defl_LL_PASS", True):
                        flag += f"  DEFL_LL FAIL {r.get('delta_LL_mm','?')}>{r.get('limit_LL_mm','?')}mm"
                    if not r.get("defl_TL_PASS", True):
                        flag += f"  DEFL_TL FAIL {r.get('delta_total_mm','?')}>{r.get('limit_TL_mm','?')}mm"
                    span_info = (
                        f"{r['original_span_m']}m→{r['effective_span_m']}m"
                        if r.get("effective_span_m") else "unsupported"
                    )
                    lines.append(
                        f"  {r['id']:8s} {span_info:14s}"
                        f"  M={r.get('M_max_kNm','?')}kNm"
                        f"  S={r.get('sigma_bend_MPa','?')}MPa"
                        + (flag if flag else ("  unsupported" if not r.get("effective_span_m") else "  ok"))
                    )
                print("\n".join(lines[lines.index("") + 1:]))

                status = "PASS" if ws.get("overall_PASS", True) else "FAIL"
                print(f"\nWhat-if result: {status}. Apply removal of {', '.join(remove_cols)} permanently?")
                print("  Connected beams will be merged across the removed column.")
                if input("Apply? [y/N]: ").strip().lower() == "y":
                    state["evaluation_result"] = json.dumps(result)
                    state["pending_structural_change"] = {
                        "type":       "remove_element",
                        "element_id": remove_cols[0],
                    }
                    state["layout_before_change"] = layout_str
                    return state

                if not ws.get("overall_PASS") and ws.get("failed_ids"):
                    fail_lines = []
                    for r in whatif.get("affected_beams", []):
                        if not r.get("bend_PASS", True):
                            fail_lines.append(
                                f"{r['id']}: bending S={r.get('sigma_bend_MPa','?')} > "
                                f"{r.get('allow_bend_MPa','?')} MPa "
                                f"(span {r.get('original_span_m','?')}m→{r.get('effective_span_m','?')}m)"
                            )
                        if not r.get("defl_LL_PASS", True):
                            fail_lines.append(
                                f"{r['id']}: LL deflection {r.get('delta_LL_mm','?')} > "
                                f"{r.get('limit_LL_mm','?')} mm"
                            )
                        if not r.get("defl_TL_PASS", True):
                            fail_lines.append(
                                f"{r['id']}: TL deflection {r.get('delta_total_mm','?')} > "
                                f"{r.get('limit_TL_mm','?')} mm"
                            )
                    state["messages"].append({
                        "role": "user",
                        "content": (
                            f"STRUCTURAL FAIL after removing {', '.join(remove_cols)}:\n"
                            + "\n".join(fail_lines)
                            + "\nPropose 2-3 specific alternatives to resolve this failure."
                        ),
                    })

            elif remove_beams:
                # ── Beam removal: no span simulation — warn and offer removal ─
                b_list = ", ".join(remove_beams)
                print(f"\nWHAT-IF: remove beam(s) {b_list}")
                print("  Removing a beam eliminates its load path between the two endpoint columns.")
                print("  Adjacent parallel beams will carry additional tributary load.")
                print("  Re-evaluation will run automatically after removal.")
                if input(f"\nRemove {b_list} permanently? [y/N]: ").strip().lower() == "y":
                    state["evaluation_result"] = json.dumps(result)
                    state["pending_structural_change"] = {
                        "type":       "remove_element",
                        "element_id": remove_beams[0],
                    }
                    state["layout_before_change"] = layout_str
                    return state

        for r in result["beams"]:
            if not r["bend_PASS"]:
                lines.append(
                    f"  BEAM {r['id']} bending FAIL: "
                    f"S={r['sigma_bend_MPa']} MPa > {r['allow_bend_MPa']} MPa "
                    f"(span {r['span_m']} m, M={r['M_max_kNm']} kN·m)"
                )
            if not r["defl_LL_PASS"]:
                lines.append(
                    f"  BEAM {r['id']} LL deflection FAIL: "
                    f"d={r['delta_LL_mm']} mm > L/{DEFL_LIMIT_LL}={r['limit_LL_mm']} mm"
                )
            if not r["defl_TL_PASS"]:
                lines.append(
                    f"  BEAM {r['id']} TL deflection FAIL: "
                    f"d={r['delta_total_mm']} mm > L/{DEFL_LIMIT_TL}={r['limit_TL_mm']} mm"
                )
            if not r["shear_PASS"]:
                lines.append(
                    f"  BEAM {r['id']} shear FAIL: "
                    f"T={r['tau_MPa']} MPa > {r['allow_shear_MPa']} MPa"
                )

        for r in result["columns"]:
            if not r["stress_PASS"]:
                lines.append(
                    f"  COL {r['id']} stress FAIL: "
                    f"S={r['sigma_comp_MPa']} MPa > {r['allow_comp_MPa']} MPa "
                    f"(P={r['P_total_kN']} kN)"
                )
            if not r["buckling_PASS"]:
                lines.append(
                    f"  COL {r['id']} buckling FAIL: "
                    f"SF={r['SF_buckling']:.1f} < {BUCKLING_SF} "
                    f"(λ={r['slenderness']}, P_cr={r['P_cr_kN']} kN)"
                )

        eval_text = "\n".join(lines)
        print(eval_text)

        state["evaluation_result"] = json.dumps(result)
        state["messages"].append({
            "role":    "user",
            "content": f"Structural evaluation (first principles):\n{eval_text}",
        })

        # ── Advisor: LLM interprets the numbers and suggests next steps ───────
        removal_hints = _precompute_removal_hints(result, layout_str, ll, sdl)
        interpretation = _interpret_evaluation(llm, result, layout_str, ll, sdl, removal_hints)
        if interpretation:
            print(f"\n[Advisor]\n{interpretation}\n")
            state["final_response"] = interpretation
        # ─────────────────────────────────────────────────────────────────────

        main_fail = not summary.get("overall_PASS", True)

        # ── Unified "what next?" menu when structure passes ───────────────────
        if not main_fail:
            col_hints  = (removal_hints or {}).get("columns", [])
            beam_hints = (removal_hints or {}).get("beams",   [])
            already_find_min = (bool(_detect_find_min(state.get("messages", [])))
                                or bool(state.get("find_minimum_done")))
            current_base = next((m for m in BASE_MATERIALS if current_mat.startswith(m)), "RCC")

            # Build numbered menu items: (kind, payload)
            menu_items: list[tuple] = []
            if not already_find_min:
                menu_items.append(("find_minimum", current_base))
            for h in col_hints:
                menu_items.append(("column", h))
            for h in beam_hints:
                menu_items.append(("beam", h))

            if menu_items:
                print("\nThe structure is holding. What would you like to do?")
                for i, (kind, payload) in enumerate(menu_items, 1):
                    if kind == "find_minimum":
                        print(f"  {i}. Right-size all sections — find the minimum that still works")
                    elif kind == "column":
                        tag = "safe" if payload["removal_safe"] else "needs beam upgrade"
                        print(f"  {i}. Remove column {payload['element_id']} "
                              f"({payload['utilisation_pct']}% utilised) — {tag}")
                        print(f"     {payload['note']}")
                    elif kind == "beam":
                        print(f"  {i}. Remove beam {payload['element_id']} "
                              f"({payload['utilisation_pct']}% utilised, {payload['span_m']}m span)")
                        print(f"     {payload['note']}")
                print("  [Enter] — keep as-is")

                raw_choice = input("Choice [1-N, comma-separated or range, or Enter]: ").strip()
                if raw_choice:
                    tokens = []
                    for part in raw_choice.replace(" ", ",").split(","):
                        part = part.strip()
                        if "-" in part and not part.startswith("-"):
                            bounds = part.split("-", 1)
                            if bounds[0].isdigit() and bounds[1].isdigit():
                                tokens.extend(range(int(bounds[0]), int(bounds[1]) + 1))
                                continue
                        if part.isdigit():
                            tokens.append(int(part))

                    selected = [menu_items[t - 1] for t in tokens if 0 <= t - 1 < len(menu_items)]
                    find_min_sel  = next(((k, p) for k, p in selected if k == "find_minimum"), None)
                    remove_sel    = [p for k, p in selected if k in ("column", "beam")]

                    if find_min_sel and not remove_sel:
                        state["evaluation_result"] = json.dumps(result)
                        state["pending_structural_change"] = {"type": "find_minimum", "material": find_min_sel[1]}
                        state["layout_before_change"] = layout_str
                        return state
                    elif remove_sel:
                        element_ids = [h["element_id"] for h in remove_sel]
                        state["pending_structural_change"] = {"type": "remove_elements", "element_ids": element_ids}
                        state["layout_before_change"] = layout_str
                        state["evaluation_result"]    = json.dumps(result)
                        return state
        # ─────────────────────────────────────────────────────────────────────

        # On failure: show alternatives menu — each option packages pending_structural_change and returns
        if main_fail:
            alts = _build_failure_alternatives(result, remove_ids, current_mat)

            print("\nThe structure needs attention. What would you like to do?")
            for i, alt in enumerate(alts, 1):
                print(f"  {i}. {alt}")
            print("  [Enter or text] — describe what you'd like to change")

            raw = input("Choice: ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                chosen = alts[idx] if 0 <= idx < len(alts) else raw
            else:
                chosen = raw

            if chosen:
                # Increase failing beams to next size up
                if re.match(r"Increase the \d+ failing beam", chosen, re.IGNORECASE):
                    state["pending_structural_change"] = {"type": "auto_upgrade_beams"}
                    state["layout_before_change"] = layout_str
                    return state

                # Increase failing columns to next size up
                if re.match(r"Increase the \d+ failing col", chosen, re.IGNORECASE):
                    state["pending_structural_change"] = {"type": "auto_upgrade_columns"}
                    state["layout_before_change"] = layout_str
                    return state

                # Per-element upgrade: "Upgrade CD_1 from IPE240 to IPE300"
                m = re.match(r"Upgrade (\S+) from \S+ to (\S+)", chosen, re.IGNORECASE)
                if m:
                    elem_id, new_sec = m.group(1), m.group(2)
                    state["pending_structural_change"] = {
                        "type": "upgrade_element",
                        "element_id": elem_id,
                        "new_section": new_sec,
                    }
                    state["layout_before_change"] = layout_str
                    return state

                # Midspan column: "Add midspan column under beam CD_1 ..."
                m2 = re.match(r"Add midspan column under (?:beam )?(\S+)", chosen, re.IGNORECASE)
                if m2:
                    beam_id = m2.group(1).rstrip("(")
                    state["pending_structural_change"] = {
                        "type": "midspan_column",
                        "beam_id": beam_id,
                        "material": current_mat,
                    }
                    state["layout_before_change"] = layout_str
                    return state

                # Global material switch: "Switch all framing to STEEL"
                m3 = re.match(r"Switch all framing to (\w+)", chosen, re.IGNORECASE)
                if m3:
                    new_mat = m3.group(1).upper()
                    if new_mat in BASE_MATERIALS:
                        state["pending_structural_change"] = {
                            "type": "material_switch",
                            "material": new_mat,
                        }
                        state["layout_before_change"] = layout_str
                        return state

                # Free text → append to messages so reason node can act on it
                state["messages"].append({
                    "role":    "user",
                    "content": f"User instruction after structural failure: {chosen}",
                })

        return state

    return evaluate_node
