from __future__ import annotations
import json
import math
import re

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

# ── Steel section property tables (actual profiles, not solid approximations) ─
STEEL_BEAM_PROPS: dict[str, dict] = {
    "IPE160": {"A_mm2": 2_009, "I_mm4": 8.69e6,  "Wy_mm3": 108_700},
    "IPE200": {"A_mm2": 2_848, "I_mm4": 19.43e6, "Wy_mm3": 194_300},
    "IPE240": {"A_mm2": 3_912, "I_mm4": 38.92e6, "Wy_mm3": 324_300},
}

STEEL_COL_PROPS: dict[str, dict] = {
    "HSS100x100x6": {"A_mm2": 2_256, "I_mm4": 3.61e6,  "r_min_mm": 40.0},
    "HSS120x120x6": {"A_mm2": 2_736, "I_mm4": 6.39e6,  "r_min_mm": 48.3},
    "HSS150x150x6": {"A_mm2": 3_456, "I_mm4": 12.69e6, "r_min_mm": 60.6},
}

# ── Load assumptions ──────────────────────────────────────────────────────────
SDL_KNM2  = 3.5   # superimposed dead load: 125 mm slab + finishes + partitions
LL_KNM2   = 2.0   # live load, residential (IS 875 Part 2)
BEAM_WIDTH_MM = 300.0  # assumed beam width when not in attributes

# ── Deflection limits ─────────────────────────────────────────────────────────
DEFL_LIMIT_LL  = 360   # L/360  live load
DEFL_LIMIT_TL  = 250   # L/250  total load
BUCKLING_SF    = 3.0   # minimum Euler buckling safety factor

# ── Default section sizes per material (base + upgrade tiers) ─────────────────
# Steel beams approximated as solid rect (IPE flange-width × height) — conservative estimate
# Steel cols treated as solid square (HSS outer dims) — conservative
DEFAULT_SECTIONS: dict[str, dict] = {
    "RCC":      {"beam_depth_mm": 300, "beam_width_mm": 200, "col_dims": "200x200"},
    "RCC_M":    {"beam_depth_mm": 450, "beam_width_mm": 250, "col_dims": "250x250"},
    "RCC_L":    {"beam_depth_mm": 600, "beam_width_mm": 300, "col_dims": "300x300"},
    "STEEL":    {"beam_depth_mm": 160, "beam_width_mm": 82,  "col_dims": "100x100", "beam_section": "IPE160", "col_section": "HSS100x100x6"},
    "STEEL_M":  {"beam_depth_mm": 200, "beam_width_mm": 100, "col_dims": "120x120", "beam_section": "IPE200", "col_section": "HSS120x120x6"},
    "STEEL_L":  {"beam_depth_mm": 240, "beam_width_mm": 120, "col_dims": "150x150", "beam_section": "IPE240", "col_section": "HSS150x150x6"},
    "TIMBER":    {"beam_depth_mm": 240, "beam_width_mm": 100, "col_dims": "100x100"},
    "TIMBER_M":  {"beam_depth_mm": 300, "beam_width_mm": 120, "col_dims": "120x120"},
    "TIMBER_L":  {"beam_depth_mm": 360, "beam_width_mm": 150, "col_dims": "150x150"},
    "TIMBER_XL": {"beam_depth_mm": 480, "beam_width_mm": 200, "col_dims": "200x200"},
}

SECTION_UPGRADE_MAP: dict[str, str] = {
    "RCC": "RCC_M",       "RCC_M": "RCC_L",
    "STEEL": "STEEL_M",   "STEEL_M": "STEEL_L",
    "TIMBER": "TIMBER_M", "TIMBER_M": "TIMBER_L", "TIMBER_L": "TIMBER_XL",
}

# Per-element steel section upgrades (beam: IPE chain, col: HSS chain)
BEAM_SECTION_UPGRADE: dict[str, tuple] = {
    "IPE160": ("IPE200", 200, 100),
    "IPE200": ("IPE240", 240, 120),
    "IPE240": ("IPE270", 270, 135),
}
COL_SECTION_UPGRADE: dict[str, tuple] = {
    "HSS100x100x6": ("HSS120x120x6", "120x120"),
    "HSS120x120x6": ("HSS150x150x6", "150x150"),
}
# Per-element RCC / Timber beam upgrades (width x depth → next tier)
BEAM_DIM_UPGRADE: dict[str, tuple] = {
    "200x300": ("250x450", 450, 250),   # RCC base → RCC_M
    "250x450": ("300x600", 600, 300),   # RCC_M   → RCC_L
    "100x240": ("120x300", 300, 120),   # TIMBER base → TIMBER_M
    "120x300": ("150x360", 360, 150),   # TIMBER_M    → TIMBER_L
    "150x360": ("200x480", 480, 200),   # TIMBER_L    → TIMBER_XL
}
# Per-element RCC / Timber column upgrades (dims → next tier)
COL_DIM_UPGRADE: dict[str, str] = {
    "200x200": "250x250",   # RCC base → RCC_M
    "250x250": "300x300",   # RCC_M   → RCC_L
    "100x100": "120x120",   # TIMBER base → TIMBER_M
    "120x120": "150x150",   # TIMBER_M    → TIMBER_L
    "150x150": "200x200",   # TIMBER_L    → TIMBER_XL
}

BASE_MATERIALS = ["RCC", "STEEL", "TIMBER"]


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

def _check_beams(beams: list[dict], trib: dict[str, float]) -> list[dict]:
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
        w_dl  = SDL_KNM2 * tw
        w_ll  = LL_KNM2  * tw
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

def _check_columns(columns: list[dict], trib: dict[str, float]) -> list[dict]:
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

        P_floor = (SDL_KNM2 + LL_KNM2) * ta
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
        w_dl  = SDL_KNM2 * tw
        w_ll  = LL_KNM2  * tw
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

def evaluate_structure(layout_json_string: str) -> dict:
    layout    = json.loads(layout_json_string)
    structure = layout.get("structure", [])

    beams   = [s for s in structure if len(s.get("geometry", [])) == 2]
    columns = [s for s in structure if len(s.get("geometry", [])) == 1]

    b_trib = _beam_trib_widths(beams)
    c_trib = _column_trib_areas(columns)

    beam_results = _check_beams(beams, b_trib)
    col_results  = _check_columns(columns, c_trib)

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


def _apply_material_override(layout_json_string: str, material: str) -> str:
    """Patch all structure elements with the given material and its default sections."""
    layout = json.loads(layout_json_string)
    sec = DEFAULT_SECTIONS.get(material, DEFAULT_SECTIONS["RCC"])
    is_steel = "STEEL" in material.upper()
    for el in layout.get("structure", []):
        attrs = el.setdefault("attributes", {})
        attrs["material"] = material
        if len(el.get("geometry", [])) == 2:   # beam
            attrs["depth"] = str(sec["beam_depth_mm"])
            attrs["width"] = str(sec["beam_width_mm"])
            if is_steel and "beam_section" in sec:
                attrs["section"] = sec["beam_section"]
        else:                                   # column
            attrs["dimensions"] = sec["col_dims"]
            if is_steel and "col_section" in sec:
                attrs["section"] = sec["col_section"]
    return json.dumps(layout)


def _upgrade_element_section(layout_str: str, element_id: str, new_section: str) -> str:
    """Update a single structural element's section in the layout JSON."""
    _BEAM_DIMS = {
        "IPE160": (160, 82), "IPE200": (200, 100),
        "IPE240": (240, 120), "IPE270": (270, 135),
    }
    _COL_DIMS = {
        "HSS100x100x6": "100x100", "HSS120x120x6": "120x120", "HSS150x150x6": "150x150",
    }
    layout = json.loads(layout_str)
    for el in layout.get("structure", []):
        if el["id"] == element_id:
            attrs  = el.setdefault("attributes", {})
            is_beam = len(el.get("geometry", [])) == 2
            if new_section in _BEAM_DIMS:                   # Steel beam (IPE)
                attrs["section"] = new_section
                d, w = _BEAM_DIMS[new_section]
                attrs["depth"] = str(d)
                attrs["width"] = str(w)
            elif new_section in _COL_DIMS:                  # Steel column (HSS)
                attrs["section"] = new_section
                attrs["dimensions"] = _COL_DIMS[new_section]
            elif is_beam and "x" in new_section:            # RCC/Timber beam (WxD)
                w_str, d_str = new_section.split("x", 1)
                attrs["depth"] = d_str
                attrs["width"] = w_str
            elif not is_beam and "x" in new_section:        # RCC/Timber column
                attrs["dimensions"] = new_section
            break
    return json.dumps(layout)


def _add_midspan_column(layout_str: str, beam_id: str, material: str) -> str:
    """Split a beam at its midpoint and insert a new column there."""
    sec = DEFAULT_SECTIONS.get(material, DEFAULT_SECTIONS["RCC"])
    layout = json.loads(layout_str)
    structure = layout.get("structure", [])
    beam = next((e for e in structure if e["id"] == beam_id and len(e.get("geometry", [])) == 2), None)
    if not beam:
        return layout_str
    p1, p2 = beam["geometry"]
    mid = [round((p1[0] + p2[0]) / 2, 3), round((p1[1] + p2[1]) / 2, 3)]
    bat = beam.get("attributes", {})
    new_col = {
        "id": f"{beam_id}_M",
        "name": f"Column_{beam_id}_M",
        "geometry": [mid],
        "attributes": {
            "type": "interior",
            "dimensions": sec["col_dims"],
            "height": bat.get("height", "3.5"),
            "isWallAligned": "false",
            "structuralRole": "primary",
            "material": material,
            "conflict": "None",
        },
    }
    new_a = {"id": f"{beam_id}a", "name": f"Beam_{beam_id}a",
             "geometry": [p1, mid], "attributes": dict(bat)}
    new_b = {"id": f"{beam_id}b", "name": f"Beam_{beam_id}b",
             "geometry": [mid, p2], "attributes": dict(bat)}
    new_structure = []
    for el in structure:
        if el["id"] == beam_id:
            new_structure += [new_a, new_b]
        else:
            new_structure.append(el)
    new_structure.append(new_col)
    layout["structure"] = new_structure
    return json.dumps(layout)


def _switch_element_material(layout_str: str, element_id: str, new_material: str) -> str:
    """Switch a single beam or column to a different material using its base section."""
    sec = DEFAULT_SECTIONS.get(new_material)
    if not sec:
        return layout_str
    is_steel = "STEEL" in new_material.upper()
    layout = json.loads(layout_str)
    for el in layout.get("structure", []):
        if el["id"] == element_id:
            attrs = el.setdefault("attributes", {})
            attrs["material"] = new_material
            is_beam = len(el.get("geometry", [])) == 2
            if is_beam:
                attrs["depth"] = str(sec["beam_depth_mm"])
                attrs["width"] = str(sec["beam_width_mm"])
                if is_steel and "beam_section" in sec:
                    attrs["section"] = sec["beam_section"]
                else:
                    attrs.pop("section", None)
            else:
                attrs["dimensions"] = sec["col_dims"]
                if is_steel and "col_section" in sec:
                    attrs["section"] = sec["col_section"]
                else:
                    attrs.pop("section", None)
            break
    return json.dumps(layout)


def _auto_upgrade_failing_beams(layout_str: str, result: dict) -> tuple[str, dict]:
    """Upgrade each failing beam through the section chain until all pass or top tier reached."""
    for _ in range(6):
        beam_fails = [b for b in result["beams"]
                      if not (b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"])]
        if not beam_fails:
            break
        upgraded = False
        for b in beam_fails:
            cur = b.get("section_mm", "")
            if cur in BEAM_SECTION_UPGRADE:
                nxt, _, _ = BEAM_SECTION_UPGRADE[cur]
                layout_str = _upgrade_element_section(layout_str, b["id"], nxt)
                print(f"  Auto-upgrade {b['id']}: {cur} → {nxt}")
                upgraded = True
            elif cur in BEAM_DIM_UPGRADE:
                nxt, _, _ = BEAM_DIM_UPGRADE[cur]
                layout_str = _upgrade_element_section(layout_str, b["id"], nxt)
                print(f"  Auto-upgrade {b['id']}: {cur} → {nxt}")
                upgraded = True
        if not upgraded:
            break
        result = evaluate_structure(layout_str)
    return layout_str, result


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
        alts.append(f"Auto-upgrade {n} failing beam{'s' if n > 1 else ''} through section sizes until PASS")

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


def build_evaluate_node(_):
    """Structural first-principles check node — unused arg kept for graph API compatibility."""

    def evaluate_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: EVALUATE")
        print(f"{'='*50}")

        # Skip full evaluation when tag_and_audit just generated a fresh grid
        if state.get("came_from") == "tag_and_audit":
            layout = json.loads(state["layout_json_string"])
            n = len(layout.get("structure", []))
            state["final_response"] = f"Structural grid generated — {n} elements added to edited layout."
            return state

        # Human-in-the-loop: ask material on first evaluate pass only
        if state.get("evaluation_result") is None:
            current = state.get("material_override") or "RCC"
            base_current = next((m for m in BASE_MATERIALS if current.startswith(m)), "RCC")
            tier_label = current[len(base_current):]  # "" | "_M" | "_L"
            tier_note = f" [{tier_label[1:]} tier]" if tier_label else ""
            print(f"\nMaterial (current: {current}{tier_note}):")
            for i, mat in enumerate(BASE_MATERIALS, 1):
                active = base_current == mat
                display_sec = DEFAULT_SECTIONS.get(current if active else mat, DEFAULT_SECTIONS[mat])
                marker = f" <-- active{tier_note}" if active else ""
                print(f"  {i}. {mat:6s} — beam {display_sec['beam_width_mm']}x{display_sec['beam_depth_mm']}mm | col {display_sec['col_dims']}mm{marker}")
            print("  [Enter] — keep current")
            raw = input("Choice [1/2/3 or RCC/STEEL/TIMBER]: ").strip().upper()
            lookup = {"1": "RCC", "2": "STEEL", "3": "TIMBER"}
            selected = lookup.get(raw) or (raw if raw in BASE_MATERIALS else None)
            if selected:
                state["material_override"] = selected

        material_override = state.get("material_override")

        if material_override:
            print(f"\nEvaluating structural integrity (first principles) — material: {material_override}...")
            layout_str = _apply_material_override(state["layout_json_string"], material_override)
        else:
            print("\nEvaluating structural integrity (first principles)...")
            layout_str = state["layout_json_string"]

        # Run standard evaluation
        result  = evaluate_structure(layout_str)
        summary = result["summary"]

        # Offer section upgrades on failure — loop through all tiers
        current_mat = state.get("material_override") or "RCC"
        while not summary.get("overall_PASS"):
            next_tier = SECTION_UPGRADE_MAP.get(current_mat)
            if not next_tier:
                break
            next_sec = DEFAULT_SECTIONS[next_tier]
            print(
                f"\nStructural FAIL with {current_mat}. "
                f"Upgrade to {next_tier.replace('_', ' ')} "
                f"(beam {next_sec['beam_width_mm']}x{next_sec['beam_depth_mm']}mm "
                f"| col {next_sec['col_dims']}mm)?"
            )
            if input("Upgrade? [y/N]: ").strip().lower() != "y":
                break
            current_mat = next_tier
            state["material_override"] = next_tier
            layout_str = _apply_material_override(state["layout_json_string"], next_tier)
            result  = evaluate_structure(layout_str)
            summary = result["summary"]
            print(f"Re-evaluated with {next_tier}: {'PASS' if summary['overall_PASS'] else 'FAIL'}")

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
            beams     = [s for s in structure if len(s.get("geometry", [])) == 2]
            b_trib    = _beam_trib_widths(beams)
            whatif    = simulate_what_if_removal(layout_str, remove_ids, b_trib)
            result["what_if"] = whatif
            ws = whatif.get("summary", {})
            lines.append("")
            lines.append(f"WHAT-IF: remove {', '.join(remove_ids)}")
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

            # Feed failures back to reason
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
                        f"STRUCTURAL FAIL after removing {', '.join(remove_ids)}:\n"
                        + "\n".join(fail_lines)
                        + "\nPropose 2-3 specific alternatives to resolve this failure."
                    ),
                })

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

        # Store eval in state and messages first so reason has full context
        state["evaluation_result"] = json.dumps(result)
        state["messages"].append({
            "role":    "user",
            "content": f"Structural evaluation (first principles):\n{eval_text}",
        })

        # On failure: show computed alternatives menu (same UX as material picker)
        main_fail   = not summary.get("overall_PASS", True)
        whatif_fail = (
            not result.get("what_if", {}).get("summary", {}).get("overall_PASS", True)
            if result.get("what_if") else False
        )

        while main_fail or whatif_fail:
            alts = _build_failure_alternatives(result, remove_ids, current_mat)

            print("\nStructural issues detected. Choose an action:")
            for i, alt in enumerate(alts, 1):
                print(f"  {i}. {alt}")
            print("  [Enter or text] — describe a custom change")

            raw = input("Choice: ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                chosen = alts[idx] if 0 <= idx < len(alts) else raw
            else:
                chosen = raw

            if not chosen:
                break

            # Auto-upgrade all failing beams through section chain
            if re.match(r"Auto-upgrade \d+ failing", chosen, re.IGNORECASE):
                print("\nAuto-upgrading failing beams through section sizes...")
                layout_str, result = _auto_upgrade_failing_beams(layout_str, result)
                summary = result["summary"]
                state["layout_json_string"] = layout_str
                state["evaluation_result"] = json.dumps(result)
                print(f"Re-evaluated: {'PASS' if summary['overall_PASS'] else 'FAIL'}")
                for r in result["beams"]:
                    if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"]):
                        print(f"  BEAM {r['id']} still fails at top section size")
                main_fail   = not summary.get("overall_PASS", True)
                whatif_fail = False
                continue

            # Per-element section upgrade: "Upgrade CD_1 from IPE240 to IPE270"
            m = re.match(r"Upgrade (\S+) from \S+ to (\S+)", chosen, re.IGNORECASE)
            if m:
                elem_id, new_sec = m.group(1), m.group(2)
                layout_str = _upgrade_element_section(layout_str, elem_id, new_sec)
                state["layout_json_string"] = layout_str
                result  = evaluate_structure(layout_str)
                summary = result["summary"]
                state["evaluation_result"] = json.dumps(result)
                print(f"\nRe-evaluated after upgrading {elem_id} to {new_sec}: "
                      f"{'PASS' if summary['overall_PASS'] else 'FAIL'}")
                for r in result["beams"]:
                    if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"]):
                        print(f"  BEAM {r['id']} still fails")
                for r in result["columns"]:
                    if not (r["stress_PASS"] and r["buckling_PASS"]):
                        print(f"  COL {r['id']} still fails")
                main_fail   = not summary.get("overall_PASS", True)
                whatif_fail = False
                continue

            # Add midspan column: "Add midspan column under beam CD_1 ..."
            m2 = re.match(r"Add midspan column under (?:beam )?(\S+)", chosen, re.IGNORECASE)
            if m2:
                beam_id = m2.group(1).rstrip("(")
                layout_str = _add_midspan_column(layout_str, beam_id, current_mat)
                state["layout_json_string"] = layout_str
                result  = evaluate_structure(layout_str)
                summary = result["summary"]
                state["evaluation_result"] = json.dumps(result)
                print(f"\nAdded midspan column under {beam_id} — split into {beam_id}a / {beam_id}b")
                print(f"Re-evaluated: {'PASS' if summary['overall_PASS'] else 'FAIL'}")
                for r in result["beams"]:
                    if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"]):
                        print(f"  BEAM {r['id']} still fails")
                main_fail   = not summary.get("overall_PASS", True)
                whatif_fail = False
                continue

            # Global material switch: "Switch all framing to STEEL"
            m3 = re.match(r"Switch all framing to (\w+)", chosen, re.IGNORECASE)
            if m3:
                new_mat = m3.group(1).upper()
                if new_mat in BASE_MATERIALS:
                    layout_str = _apply_material_override(layout_str, new_mat)
                    state["layout_json_string"] = layout_str
                    state["material_override"] = new_mat
                    current_mat = new_mat
                    result  = evaluate_structure(layout_str)
                    summary = result["summary"]
                    state["evaluation_result"] = json.dumps(result)
                    print(f"\nSwitched all framing to {new_mat} — Re-evaluated: "
                          f"{'PASS' if summary['overall_PASS'] else 'FAIL'}")
                    for r in result["beams"]:
                        if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"]):
                            print(f"  BEAM {r['id']} still fails")
                    main_fail   = not summary.get("overall_PASS", True)
                    whatif_fail = False
                    continue

            # Anything else — send to reason node
            state["messages"].append({
                "role":    "user",
                "content": f"User instruction after structural failure: {chosen}",
            })
            break

        return state

    return evaluate_node
