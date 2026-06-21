from __future__ import annotations
import json
import math
import re
import sys
from pathlib import Path


def _safe_input(prompt: str, default: str = "") -> str:
    """Return `default` silently when stdin is not a terminal (orchestrator / headless mode)."""
    if not sys.stdin.isatty():
        print(f"{prompt}{default}  [auto]")
        return default
    return input(prompt)
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
UTIL_OVERENGINEERED = 0.50  # below this -> layout change possible (remove / relocate)
UTIL_APPROACHING    = 0.75  # above this -> approaching limit, flag to architect


# ── Helpers ───────────────────────────────────────────────────────────────────

def _material(name: str) -> dict:
    key = name.upper().replace("-", "").replace("_", "").replace(" ", "")
    for k, v in MATERIALS.items():
        if k in key:
            return v
    return MATERIALS["RCC"]


def _parse_dim_mm(s: str) -> tuple[float, float]:
    """'300x600' -> (0.300, 0.600) metres."""
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

def _check_beam_with_point_load(
    bm: dict, L: float, a: float, P_kN: float,
    w_udl: float, w_ll_udl: float,
    A: float, E: float, I: float, Wy_mm3: float,
    mat: dict, sec_label: str, tw: float,
) -> dict:
    """
    Transfer beam check: simply supported span L, UDL w_udl kN/m,
    plus concentrated point load P_kN at distance a from the left end.
    """
    R_A = w_udl * L / 2.0 + P_kN * (L - a) / L
    R_B = w_udl * L / 2.0 + P_kN * a / L

    def _M(x: float) -> float:
        return R_A * x - w_udl * x ** 2 / 2.0 - (P_kN * (x - a) if x > a else 0.0)

    x_cands = [a]
    if w_udl > 1e-9:
        for xc in [R_A / w_udl, (R_A - P_kN) / w_udl]:
            if 1e-6 < xc < L - 1e-6:
                x_cands.append(xc)
    M_max   = max(_M(x) for x in x_cands)
    V_max   = max(abs(R_A), abs(R_B))
    sigma_b = M_max * 1e6 / Wy_mm3
    tau     = V_max * 1e3 / A / 1e6

    # Deflection by superposition (SS beam: UDL midspan + point load at a)
    def _d_udl(w: float) -> float:
        return 5.0 * (w * 1e3) * L ** 4 / (384.0 * E * I) * 1e3  # mm

    def _d_pt(P: float) -> float:
        return P * 1e3 * a ** 2 * (L - a) ** 2 / (3.0 * E * I * L) * 1e3  # mm

    w_frac_ll = w_ll_udl / max(w_udl, 1e-9)
    d_tot = _d_udl(w_udl)    + _d_pt(P_kN)
    d_ll  = _d_udl(w_ll_udl) + _d_pt(P_kN * w_frac_ll)
    lim_tl = L * 1e3 / DEFL_LIMIT_TL
    lim_ll = L * 1e3 / DEFL_LIMIT_LL

    return {
        "id":                     bm["id"],
        "span_m":                 round(L, 3),
        "section_mm":             sec_label,
        "material":               mat.get("name", ""),
        "trib_width_m":           round(tw, 2),
        "is_transfer_beam":       True,
        "transfer_point_load_kN": round(P_kN, 2),
        "transfer_load_pos_m":    round(a, 3),
        "R_left_kN":              round(R_A, 2),
        "R_right_kN":             round(R_B, 2),
        "M_max_kNm":              round(M_max, 3),
        "sigma_bend_MPa":         round(sigma_b, 3),
        "allow_bend_MPa":         mat["allow_bend_MPa"],
        "bend_PASS":              sigma_b <= mat["allow_bend_MPa"],
        "tau_MPa":                round(tau, 4),
        "allow_shear_MPa":        mat["allow_shear_MPa"],
        "shear_PASS":             tau <= mat["allow_shear_MPa"],
        "delta_total_mm":         round(d_tot, 3),
        "delta_LL_mm":            round(d_ll, 3),
        "limit_TL_mm":            round(lim_tl, 3),
        "limit_LL_mm":            round(lim_ll, 3),
        "defl_TL_PASS":           d_tot <= lim_tl,
        "defl_LL_PASS":           d_ll  <= lim_ll,
        "note": f"transfer beam: upper col P={P_kN:.1f}kN at {a:.2f}m from left",
    }


def _find_upper_col_point_loads(
    layout: dict, level_key: str, ll_kNm2: float, sdl_kNm2: float,
) -> dict[str, tuple]:
    """
    Return {beam_id: (a_m, P_kN)} for beams at level_key that have an upper-level
    column's XY position lying on their span (i.e. the beam is a transfer beam).
    a_m = distance from beam start point to the column position.
    """
    from nodes._layout import get_level_keys, get_structure as _gs, load_multiplier_for_level
    TOL = 0.02
    keys = get_level_keys(layout)
    if level_key not in keys:
        return {}
    idx        = keys.index(level_key)
    upper_keys = keys[idx + 1:]
    if not upper_keys:
        return {}

    beams = [el for el in _gs(layout, level_key) if len(el.get("geometry", [])) == 2]

    # Collect all upper-level column positions with their computed load
    upper_col_data: list[tuple] = []  # (x, y, P_kN)
    for uk in upper_keys:
        uk_struct = _gs(layout, uk)
        uk_cols   = [el for el in uk_struct if len(el.get("geometry", [])) == 1]
        if not uk_cols:
            continue
        c_trib = _column_trib_areas(uk_cols)
        mult   = load_multiplier_for_level(layout, uk)
        for r in _check_columns(uk_cols, c_trib, ll_kNm2, sdl_kNm2, load_multiplier=mult):
            col_el = next((e for e in uk_struct if e["id"] == r["id"]), None)
            if col_el:
                cx, cy = col_el["geometry"][0]
                upper_col_data.append((cx, cy, r["P_total_kN"]))

    if not upper_col_data:
        return {}

    result: dict[str, tuple] = {}
    for bm in beams:
        p1, p2 = bm["geometry"][0], bm["geometry"][1]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        L = math.hypot(dx, dy)
        if L < 0.05:
            continue
        for cx, cy, P_kN in upper_col_data:
            t = ((cx - p1[0]) * dx + (cy - p1[1]) * dy) / (L * L)
            if t <= TOL or t >= 1.0 - TOL:
                continue  # endpoint positions are normal column connections, not transfer scenarios
            proj_x = p1[0] + t * dx
            proj_y = p1[1] + t * dy
            if math.hypot(cx - proj_x, cy - proj_y) < TOL:
                a = max(0.0, min(L, t * L))
                result[bm["id"]] = (round(a, 3), round(P_kN, 2))
                break
    return result


def _check_beams(beams: list[dict], trib: dict[str, float], ll_kNm2: float = LL_KNM2, sdl_kNm2: float = SDL_KNM2, point_loads: dict | None = None) -> list[dict]:
    results = []
    for bm in beams:
        g = bm["geometry"]
        attrs = bm.get("attributes", {})
        mat_name = attrs.get("material") or "RCC"
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
            Wy_mm3 = I / (d / 2) * 1e9          # m³ -> mm³
            sec_label = f"{int(b*1000)}x{int(d*1000)}"

        E  = mat["E_MPa"] * 1e6
        tw = trib.get(bm["id"], 2.5)

        w_sw  = mat["density_kNm3"] * A
        w_dl  = sdl_kNm2 * tw
        w_ll  = ll_kNm2  * tw
        w_tot = w_sw + w_dl + w_ll

        # Transfer beam: point load from an upper-level column sitting on this beam
        if point_loads and bm["id"] in point_loads:
            a_m, P_kN = point_loads[bm["id"]]
            results.append(_check_beam_with_point_load(
                bm, L, a_m, P_kN, w_tot, w_ll, A, E, I, Wy_mm3, mat, sec_label, tw
            ))
            continue

        M = w_tot * L ** 2 / 8.0
        sigma_b = M * 1e6 / Wy_mm3
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

def _check_columns(columns: list[dict], trib: dict[str, float], ll_kNm2: float = LL_KNM2, sdl_kNm2: float = SDL_KNM2, load_multiplier: int = 1) -> list[dict]:
    results = []
    for col in columns:
        attrs = col.get("attributes", {})
        mat_name = attrs.get("material") or "RCC"
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

        P_floor = (sdl_kNm2 + ll_kNm2) * ta * load_multiplier
        P_self  = mat["density_kNm3"] * A * H * load_multiplier
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
    # Match: beam IDs like A3-A5, underscore IDs like Col_D1, grid IDs like C2 / D3
    return list(dict.fromkeys(
        m.upper() for m in re.findall(
            r'(?<!\w)([A-Za-z]\d+(?:-[A-Za-z]\d+)+|[A-Za-z]\w*_\d+|[A-Za-z]\d+)(?!\w)', text
        )
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
    beam_dir: tuple | None = None,
) -> float:
    """Walk beam chain from floating_pos through removed columns; return total span.
    beam_dir: normalised (dx,dy) pointing from the far support toward floating_pos.
    When given, only beams collinear with that direction are followed — perpendicular
    framing beams are skipped so they are not misread as span extensions.
    """
    total = initial_dist
    current = floating_pos
    for _ in range(20):
        if current in remaining_positions:
            break
        moved = False
        for bm in beam_idx.get(current, []):
            if bm["id"] in visited:
                continue
            p1, p2 = tuple(bm["geometry"][0]), tuple(bm["geometry"][1])
            other = p2 if p1 == current else p1
            cdx = other[0] - current[0]; cdy = other[1] - current[1]
            seg_len = math.hypot(cdx, cdy)
            if seg_len < 1e-6:
                continue
            if beam_dir is not None:
                cross = abs(beam_dir[0]*cdy - beam_dir[1]*cdx) / seg_len
                dot   = (beam_dir[0]*cdx + beam_dir[1]*cdy) / seg_len
                if cross > 0.15 or dot <= 0:
                    continue  # not collinear — perpendicular framing beam, skip
            visited.add(bm["id"])
            total += seg_len
            current = other
            moved = True
            break
        if not moved:
            break
    return total


def _collect_perp_reactions_at_pos(
    pos: tuple,
    beam_dir: tuple,
    all_beams: list[dict],
    base_trib: dict[str, float],
    sdl_kNm2: float,
    ll_kNm2: float,
) -> float:
    """Sum the reactions delivered to the merged beam by perpendicular framing beams at pos.
    A beam is perpendicular when its direction from pos is not collinear with beam_dir.
    Reaction = (SDL+LL) × trib_width × half_span (simply-supported far end + merged beam support).
    """
    P_total = 0.0
    for bm in all_beams:
        p1, p2 = tuple(bm["geometry"][0]), tuple(bm["geometry"][1])
        if p1 != pos and p2 != pos:
            continue
        other = p2 if p1 == pos else p1
        cdx = other[0] - pos[0]; cdy = other[1] - pos[1]
        bm_span = math.hypot(cdx, cdy)
        if bm_span < 1e-6:
            continue
        cross = abs(beam_dir[0]*cdy - beam_dir[1]*cdx) / bm_span
        if cross < 0.15:
            continue  # collinear with merged beam — not a framing beam
        tw = base_trib.get(bm["id"], 2.5)
        P_total += (sdl_kNm2 + ll_kNm2) * tw * bm_span / 2.0
    return round(P_total, 2)


def _cascade_to_lower_level(
    layout: dict,
    remove_level_key: str,
    removed_positions: set,
    level_beams: list,
    base_trib: dict,
    ll_kNm2: float,
    sdl_kNm2: float,
) -> dict | None:
    """
    After removing columns at remove_level_key, check the level below.
    Each beam that lost one support transfers its old half-span reaction as an
    extra point load to the surviving endpoint column, which cascades to the
    level_01 column at the same XY.
    Returns None when remove_level_key is the bottom level.
    """
    from nodes._layout import get_level_keys, get_structure as _gs, load_multiplier_for_level

    keys = get_level_keys(layout)
    if remove_level_key not in keys:
        return None
    idx = keys.index(remove_level_key)
    if idx == 0:
        return None

    lower_key    = keys[idx - 1]
    lower_struct = _gs(layout, lower_key)

    lower_col_by_pos: dict[tuple, dict] = {}
    for el in lower_struct:
        if len(el.get("geometry", [])) == 1:
            x, y = el["geometry"][0]
            lower_col_by_pos[(round(x, 3), round(y, 3))] = el

    extra_load_map: dict[str, float] = {}

    for bm in level_beams:
        p1, p2 = tuple(bm["geometry"][0]), tuple(bm["geometry"][1])
        p1_rem = p1 in removed_positions
        p2_rem = p2 in removed_positions
        if not p1_rem and not p2_rem:
            continue
        if p1_rem and p2_rem:
            continue  # both ends gone — already a beam failure, not a point-load cascade

        tw    = base_trib.get(bm["id"], 2.5)
        orig  = math.dist(p1, p2)
        w     = (sdl_kNm2 + ll_kNm2) * tw   # kN/m
        extra = w * orig / 2.0               # half-span reaction previously carried by removed col

        surviving = p2 if p1_rem else p1
        sk = (round(surviving[0], 3), round(surviving[1], 3))
        lc = lower_col_by_pos.get(sk)
        if lc:
            extra_load_map[lc["id"]] = extra_load_map.get(lc["id"], 0.0) + extra

    if not extra_load_map:
        return None

    lower_cols = [el for el in lower_struct if len(el.get("geometry", [])) == 1]
    c_trib     = _column_trib_areas(lower_cols)
    mult       = load_multiplier_for_level(layout, lower_key)

    results: list[dict] = []
    for col in lower_cols:
        extra = extra_load_map.get(col["id"], 0.0)
        if extra == 0.0:
            continue

        base_res = _check_columns([col], c_trib, ll_kNm2, sdl_kNm2, load_multiplier=mult)
        if not base_res:
            continue
        r = dict(base_res[0])

        attrs  = col.get("attributes", {})
        mat    = _material(attrs.get("material") or "RCC")
        b_mm, d_mm = _parse_dim_mm(attrs.get("dimensions", "300x300"))
        steel_sec  = None
        if "STEEL" in (attrs.get("material", "") or "").upper():
            steel_sec = STEEL_COL_PROPS.get(attrs.get("section", ""))
        A = steel_sec["A_mm2"] / 1e6 if steel_sec else _rect_props(b_mm, d_mm)[0]

        new_P   = r["P_total_kN"] + extra
        sigma_c = new_P * 1e3 / A / 1e6
        r["P_total_kN"]               = round(new_P, 2)
        r["extra_load_kN_from_above"] = round(extra, 2)
        r["sigma_comp_MPa"]           = round(sigma_c, 4)
        r["stress_PASS"]              = sigma_c <= mat["allow_comp_MPa"]
        r["level"]                    = lower_key
        results.append(r)

    failures = [r for r in results if not (r["stress_PASS"] and r["buckling_PASS"])]
    return {
        "simulation":       "cascade_check",
        "source_level":     remove_level_key,
        "target_level":     lower_key,
        "affected_columns": results,
        "summary": {
            "affected":     len(results),
            "failures":     len(failures),
            "failed_ids":   [r["id"] for r in failures],
            "overall_PASS": not failures,
        },
    }


def _simulate_beam_removal(
    layout_json_string: str,
    beam_id: str,
    base_trib: dict[str, float],
    ll_kNm2: float = LL_KNM2,
    sdl_kNm2: float = SDL_KNM2,
) -> dict:
    """Beam removal what-if: find adjacent parallel beams and re-check them
    with expanded tributary widths after the removed beam's load redistributes."""
    from nodes._layout import get_structure as _gs, is_multilevel, find_element_in_layout

    layout = json.loads(layout_json_string)

    level_key = None
    if is_multilevel(layout):
        level_key, _ = find_element_in_layout(layout, beam_id)
        structure = _gs(layout, level_key) if level_key else _gs(layout)
    else:
        structure = layout.get("structure", [])

    all_beams = [el for el in structure if len(el.get("geometry", [])) == 2]
    target = next((bm for bm in all_beams if bm["id"] == beam_id), None)
    if target is None:
        return {"error": f"Beam {beam_id} not found in structure"}

    g = target["geometry"]
    g0, g1 = g[0], g[1]
    is_horiz = abs(g1[0] - g0[0]) >= abs(g1[1] - g0[1])

    # Perpendicular coordinate: y for horizontal beams, x for vertical
    if is_horiz:
        pos_fn = lambda bm: (bm["geometry"][0][1] + bm["geometry"][1][1]) / 2.0
    else:
        pos_fn = lambda bm: (bm["geometry"][0][0] + bm["geometry"][1][0]) / 2.0

    parallel = [
        bm for bm in all_beams
        if (abs(bm["geometry"][1][0] - bm["geometry"][0][0]) >= abs(bm["geometry"][1][1] - bm["geometry"][0][1])) == is_horiz
    ]
    sorted_par = sorted(parallel, key=pos_fn)
    sorted_pos  = [pos_fn(bm) for bm in sorted_par]
    target_pos  = pos_fn(target)
    t_idx = min(range(len(sorted_pos)), key=lambda i: abs(sorted_pos[i] - target_pos))

    left_bm  = sorted_par[t_idx - 1] if t_idx > 0 else None
    right_bm = sorted_par[t_idx + 1] if t_idx < len(sorted_par) - 1 else None

    removed_trib  = base_trib.get(beam_id, 2.5)
    edge_warnings = []
    affected      = []

    if left_bm and right_bm:
        # Left neighbor inherits the right half of the gap to the right neighbor
        extra_left  = (pos_fn(right_bm) - target_pos) / 2.0
        # Right neighbor inherits the left half of the gap to the left neighbor
        extra_right = (target_pos - pos_fn(left_bm)) / 2.0
        old_l = base_trib.get(left_bm["id"],  2.5)
        old_r = base_trib.get(right_bm["id"], 2.5)
        affected.append((left_bm,  round(old_l, 3), round(old_l  + extra_left,  3)))
        affected.append((right_bm, round(old_r, 3), round(old_r  + extra_right, 3)))
    elif left_bm:
        edge_warnings.append("no parallel beam on the right — floor on that side loses structural support")
        old_l = base_trib.get(left_bm["id"], 2.5)
        affected.append((left_bm, round(old_l, 3), round(old_l + removed_trib, 3)))
    elif right_bm:
        edge_warnings.append("no parallel beam on the left — floor on that side loses structural support")
        old_r = base_trib.get(right_bm["id"], 2.5)
        affected.append((right_bm, round(old_r, 3), round(old_r + removed_trib, 3)))
    else:
        edge_warnings.append("no parallel beams on either side — removing this beam leaves the floor strip unsupported")

    results = []
    for bm, old_tw, new_tw in affected:
        override_trib = dict(base_trib)
        override_trib[bm["id"]] = new_tw
        checked = _check_beams([bm], override_trib, ll_kNm2, sdl_kNm2)
        if checked:
            r = dict(checked[0])
            r["trib_width_before_m"] = old_tw
            r["trib_width_after_m"]  = new_tw
            results.append(r)

    failures = [
        r for r in results
        if not (r.get("bend_PASS", True) and r.get("defl_LL_PASS", True)
                and r.get("defl_TL_PASS", True) and r.get("shear_PASS", True))
    ]
    return {
        "simulation":     "beam_removal_what_if",
        "removed_id":     beam_id,
        "removed_span_m": round(math.dist(g0, g1), 3),
        "removed_trib_m": round(removed_trib, 3),
        "level":          level_key,
        "affected_beams": results,
        "edge_warnings":  edge_warnings,
        "summary": {
            "affected":     len(results),
            "failures":     len(failures),
            "failed_ids":   [r["id"] for r in failures],
            "overall_PASS": not failures and not edge_warnings,
        },
    }


def simulate_what_if_removal(
    layout_json_string: str,
    remove_ids: list[str],
    base_trib: dict[str, float],
    ll_kNm2: float = LL_KNM2,
    sdl_kNm2: float = SDL_KNM2,
) -> dict:
    """Re-evaluate beams whose endpoint columns are removed, extending their spans.
    For multilevel layouts also checks if the load cascades to the level below."""
    from nodes._layout import get_structure as _gs, is_multilevel, find_element_in_layout
    layout = json.loads(layout_json_string)

    # For multilevel: restrict simulation to the level where the column lives
    remove_level_key = None
    if is_multilevel(layout):
        lk, _el = find_element_in_layout(layout, remove_ids[0])
        if lk:
            remove_level_key = lk
            structure = _gs(layout, lk)
        else:
            structure = _gs(layout)
    else:
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

    # ── Transfer beam pre-pass (multilevel only) ─────────────────────────────
    # When removing a column at a lower level that has a column directly above it,
    # the two beams flanking the removed column merge into a transfer beam carrying
    # the upper column as a point load.  Check these before the span-extension loop.
    transfer_ids: set[str] = set()
    if remove_level_key and is_multilevel(layout):
        from nodes._layout import get_level_keys, get_structure as _gs_tr, load_multiplier_for_level as _lmfl
        _keys = get_level_keys(layout)
        _idx  = _keys.index(remove_level_key)
        for _uk in _keys[_idx + 1:]:
            _uk_struct = _gs_tr(layout, _uk)
            _uk_cols   = [el for el in _uk_struct if len(el.get("geometry", [])) == 1]
            if not _uk_cols:
                continue
            _uk_trib = _column_trib_areas(_uk_cols)
            _uk_mult = _lmfl(layout, _uk)
            _uk_res  = {r["id"]: r["P_total_kN"]
                        for r in _check_columns(_uk_cols, _uk_trib, ll_kNm2, sdl_kNm2, load_multiplier=_uk_mult)}
            for _uc in _uk_cols:
                _cx, _cy = _uc["geometry"][0]
                _ck = (round(_cx, 3), round(_cy, 3))
                # Is this upper-col position one of the removed positions?
                _match = next((p for p in removed_positions
                               if abs(p[0]-_cx) < 0.02 and abs(p[1]-_cy) < 0.02), None)
                if _match is None:
                    continue
                P_kN = _uk_res.get(_uc["id"], 0.0)
                if P_kN == 0.0:
                    continue
                # Find the two collinear beams that meet at _match
                _touching = [b for b in all_beams
                             if tuple(b["geometry"][0]) == _match or tuple(b["geometry"][1]) == _match]
                for _b1 in _touching:
                    _far1 = tuple(_b1["geometry"][1]) if tuple(_b1["geometry"][0]) == _match else tuple(_b1["geometry"][0])
                    for _b2 in _touching:
                        if _b2["id"] == _b1["id"] or _b2["id"] in transfer_ids:
                            continue
                        _far2 = tuple(_b2["geometry"][1]) if tuple(_b2["geometry"][0]) == _match else tuple(_b2["geometry"][0])
                        if _far1 == _far2:
                            continue
                        _dx1 = _far1[0]-_match[0]; _dy1 = _far1[1]-_match[1]
                        _dx2 = _far2[0]-_match[0]; _dy2 = _far2[1]-_match[1]
                        _L1  = math.hypot(_dx1, _dy1); _L2 = math.hypot(_dx2, _dy2)
                        if _L1 < 1e-6 or _L2 < 1e-6:
                            continue
                        _cross = abs(_dx1*_dy2 - _dy1*_dx2) / (_L1*_L2)
                        _dot   = (_dx1*_dx2 + _dy1*_dy2) / (_L1*_L2)
                        if _cross < 0.15 and _dot < 0:
                            # Collinear pair — build transfer beam check
                            _L_merged = _L1 + _L2
                            _a        = _L1  # point load at distance _L1 from _far1
                            # Use the shallower beam's section (weaker capacity = conservative check)
                            _d1 = float((_b1.get("attributes") or {}).get("depth") or 600)
                            _d2 = float((_b2.get("attributes") or {}).get("depth") or 600)
                            _attrs    = (_b1 if _d1 <= _d2 else _b2).get("attributes", {})
                            _mn       = _attrs.get("material") or "RCC"
                            _mat      = _material(_mn)
                            _d  = float(_attrs.get("depth") or 600) / 1000.0
                            _bw = float(_attrs.get("width") or BEAM_WIDTH_MM) / 1000.0
                            _ss = STEEL_BEAM_PROPS.get(_attrs.get("section") or "") if "STEEL" in _mn.upper() else None
                            if _ss:
                                _A = _ss["A_mm2"]/1e6; _I = _ss["I_mm4"]/1e12; _Wy = _ss["Wy_mm3"]
                                _sl = _attrs.get("section") or f"{int(_bw*1000)}x{int(_d*1000)}"
                            else:
                                _A, _I, _ = _rect_props(_bw, _d); _Wy = _I/(_d/2)*1e9
                                _sl = f"{int(_bw*1000)}x{int(_d*1000)}"
                            _E   = _mat["E_MPa"]*1e6
                            _tw  = base_trib.get(_b1["id"], 2.5)
                            _wsw = _mat["density_kNm3"]*_A
                            _wdl = sdl_kNm2*_tw; _wll = ll_kNm2*_tw; _wtot = _wsw+_wdl+_wll
                            # Add reactions from perpendicular framing beams at the removed column
                            _ddx = _match[0]-_far1[0]; _ddy = _match[1]-_far1[1]
                            _ddL = math.hypot(_ddx, _ddy)
                            _mdir = (_ddx/_ddL, _ddy/_ddL) if _ddL > 1e-6 else None
                            _P_perp = _collect_perp_reactions_at_pos(
                                _match, _mdir, all_beams, base_trib, sdl_kNm2, ll_kNm2
                            ) if _mdir else 0.0
                            _P_total = P_kN + _P_perp
                            _tr = _check_beam_with_point_load(
                                _b1, _L_merged, _a, _P_total, _wtot, _wll, _A, _E, _I, _Wy, _mat, _sl, _tw
                            )
                            _tr["original_span_m"]        = round(_L1, 3)
                            _tr["effective_span_m"]       = round(_L_merged, 3)
                            _tr["merged_with"]             = _b2["id"]
                            _tr["transfer_upper_col_kN"]  = round(P_kN, 2)
                            _tr["transfer_perp_kN"]       = round(_P_perp, 2)
                            _perp_note = f" + {_P_perp:.1f}kN from framing beams" if _P_perp > 0 else ""
                            _tr["note"] = (
                                f"transfer beam (merged {_b1['id']}+{_b2['id']}): "
                                f"P={P_kN:.1f}kN from upper col{_perp_note} at {_a:.2f}m from left  "
                                f"[span {_L1:.1f}+{_L2:.1f}={_L_merged:.1f}m]"
                            )
                            results.append(_tr)
                            transfer_ids.update([_b1["id"], _b2["id"]])
                            visited.update([_b1["id"], _b2["id"]])
                            break

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
        mat_name = attrs.get("material") or "RCC"
        mat      = _material(mat_name)
        d        = float(attrs.get("depth") or 600) / 1000.0
        b        = BEAM_WIDTH_MM / 1000.0

        # Real IPE properties for steel; solid rect for RCC / Timber
        steel_sec = None
        if "STEEL" in mat_name.upper():
            steel_sec = STEEL_BEAM_PROPS.get(attrs.get("section") or "")

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

        floating    = p1 if p1_removed else p2
        far_end_pos = p2 if p1 == floating else p1
        _dx_be = floating[0] - far_end_pos[0]; _dy_be = floating[1] - far_end_pos[1]
        _dL_be = math.hypot(_dx_be, _dy_be)
        beam_dir = (_dx_be / _dL_be, _dy_be / _dL_be) if _dL_be > 1e-6 else None

        eff_span = _trace_span(floating, beam_idx, removed_positions,
                               remaining_positions, visited, orig_span, beam_dir)

        w_sw  = mat["density_kNm3"] * A
        w_dl  = sdl_kNm2 * tw
        w_ll  = ll_kNm2  * tw
        w_tot = w_sw + w_dl + w_ll

        # Reactions from perpendicular beams framing into the removed column position
        P_perp = _collect_perp_reactions_at_pos(
            floating, beam_dir, all_beams, base_trib, sdl_kNm2, ll_kNm2
        ) if beam_dir else 0.0

        sec_lbl = f"{int(b*1000)}x{int(d*1000)}"

        if P_perp > 0 and eff_span > orig_span:
            # Point load from framing beams at the removed column position (orig_span from far support)
            r = _check_beam_with_point_load(
                bm, eff_span, orig_span, P_perp, w_tot, w_ll, A, E, I, Wy_mm3, mat, sec_lbl, tw
            )
            r["original_span_m"]  = round(orig_span, 3)
            r["effective_span_m"] = round(eff_span, 3)
            r["note"] = (
                f"span {orig_span:.1f}m -> {eff_span:.1f}m after removing {', '.join(remove_ids)}; "
                f"P={P_perp:.1f}kN from framing beams at {orig_span:.2f}m from support"
            )
            results.append(r)
        else:
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
                "section_mm":       sec_lbl,
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
                "note": f"span {orig_span:.1f}m -> {eff_span:.1f}m after removing {', '.join(remove_ids)}",
            })

    failures = [r for r in results if not all(
        r.get(k, False) for k in ("bend_PASS", "shear_PASS", "defl_TL_PASS", "defl_LL_PASS")
    )]
    sim_result = {
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

    # Cascade load to the level below (multilevel only)
    if remove_level_key and is_multilevel(layout):
        cascade = _cascade_to_lower_level(
            layout, remove_level_key, removed_positions,
            all_beams, base_trib, ll_kNm2, sdl_kNm2,
        )
        if cascade:
            sim_result["cascade"] = cascade
            if not cascade["summary"]["overall_PASS"]:
                sim_result["summary"]["overall_PASS"] = False

    return sim_result


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_structure(layout_json_string: str, ll_kNm2: float = LL_KNM2, sdl_kNm2: float = SDL_KNM2) -> dict:
    from nodes._layout import is_multilevel, get_level_keys, get_structure as _gs, load_multiplier_for_level
    layout = json.loads(layout_json_string)

    if is_multilevel(layout):
        all_beam_results: list = []
        all_col_results:  list = []
        for lk in get_level_keys(layout):
            structure = _gs(layout, lk)
            beams   = [s for s in structure if len(s.get("geometry", [])) == 2]
            columns = [s for s in structure if len(s.get("geometry", [])) == 1]
            b_trib  = _beam_trib_widths(beams)
            c_trib  = _column_trib_areas(columns)
            mult    = load_multiplier_for_level(layout, lk)
            pt_loads = _find_upper_col_point_loads(layout, lk, ll_kNm2, sdl_kNm2)
            if pt_loads:
                print(f"  [{lk}] {len(pt_loads)} transfer beam(s) carrying upper-level column load")
            all_beam_results.extend(_check_beams(beams, b_trib, ll_kNm2, sdl_kNm2, point_loads=pt_loads))
            all_col_results.extend(_check_columns(columns, c_trib, ll_kNm2, sdl_kNm2, load_multiplier=mult))
        b_fail = [r for r in all_beam_results if not (r["bend_PASS"] and r["shear_PASS"] and r["defl_TL_PASS"] and r["defl_LL_PASS"])]
        c_fail = [r for r in all_col_results  if not (r["stress_PASS"] and r["buckling_PASS"])]
        return {
            "beams":   all_beam_results,
            "columns": all_col_results,
            "summary": {
                "total_beams":       len(all_beam_results),
                "beam_failures":     len(b_fail),
                "failed_beam_ids":   [r["id"] for r in b_fail],
                "total_columns":     len(all_col_results),
                "column_failures":   len(c_fail),
                "failed_column_ids": [r["id"] for r in c_fail],
                "overall_PASS":      not b_fail and not c_fail,
            },
        }

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
                    f"(span {orig}m -> {mid}m each side)"
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
            f"(span {r['span_m']}m -> {mid}m each side)"
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
    _pt = _get_user_request(state.get("messages", [])).upper()

    # Derive SDL default from prompt keywords (headless mode only; ignored when interactive)
    if any(k in _pt for k in ["LIGHT TIMBER", "LIGHT WOOD", "TIMBER FLOOR", "WOOD FLOOR"]):
        _sdl_default = "1"
    elif any(k in _pt for k in ["LIGHT CONCRETE", "THIN SLAB"]):
        _sdl_default = "2"
    elif any(k in _pt for k in ["HEAVY FLOOR", "HEAVY SLAB", "HEAVY BUILD", "RAISED FLOOR", "THICK SLAB"]):
        _sdl_default = "4"
    elif "STANDARD" in _pt:
        _sdl_default = "3"
    else:
        _sdl_default = ""   # keep current

    # Derive LL default from occupancy keywords
    if any(k in _pt for k in ["RESIDENTIAL", "APARTMENT", "APARTMENTS", "HOME", "HOMES", "HOUSING", "DOMESTIC", "LIVING"]):
        _ll_default = "1"
    elif any(k in _pt for k in ["OFFICE", "OFFICES", "WORKPLACE", "WORK SPACE", "CO-WORKING"]):
        _ll_default = "2"
    elif any(k in _pt for k in ["RETAIL", "SHOP", "SHOPPING", "PUBLIC", "COMMERCIAL", "STORE", "MARKET"]):
        _ll_default = "3"
    else:
        _ll_default = ""   # keep current

    cur_sdl = state.get("sdl_kNm2") or SDL_KNM2
    _sdl_map = {"1": 1.5, "2": 2.5, "3": 3.5, "4": 5.0}
    if _sdl_default:
        state["sdl_kNm2"] = _sdl_map[_sdl_default]
        print(f"\n  Floor load: {state['sdl_kNm2']} kN/m²  [from prompt]")
    else:
        print(f"\nWhat kind of floor build-up are you designing? [current: {cur_sdl} kN/m²]")
        print("  1. Light timber floor — 1.5 kN/m²  (wood framing, light finishes)")
        print("  2. Light concrete     — 2.5 kN/m²  (thin slab, minimal finishes)")
        print("  3. Standard           — 3.5 kN/m²  (125mm slab + finishes + partitions)")
        print("  4. Heavy              — 5.0 kN/m²  (thick slab, heavy finishes, raised floor)")
        print("  [Enter] — keep current")
        raw_sdl = _safe_input("Your choice [1-4 or Enter]: ", "").strip()
        state["sdl_kNm2"] = _sdl_map.get(raw_sdl, cur_sdl)
        print(f"  Floor load: {state['sdl_kNm2']} kN/m²")

    cur_ll = state.get("live_load_kNm2") or LL_KNM2
    _ll_map = {"1": 2.0, "2": 3.0, "3": 5.0}
    if _ll_default:
        state["live_load_kNm2"] = _ll_map[_ll_default]
        print(f"  Live load: {state['live_load_kNm2']} kN/m²  [from prompt]")
    else:
        print(f"\nHow will this space be used? [current: {cur_ll} kN/m²]")
        print("  1. Homes / apartments  — 2.0 kN/m²")
        print("  2. Offices             — 3.0 kN/m²")
        print("  3. Retail / public     — 5.0 kN/m²")
        print("  [Enter] — keep current")
        raw_ll = _safe_input("Your choice [1-3 or Enter]: ", "").strip()
        state["live_load_kNm2"] = _ll_map.get(raw_ll, cur_ll)
        print(f"  Live load: {state['live_load_kNm2']} kN/m²")

    try:
        SETTINGS_PATH.write_text(
            json.dumps({"sdl_kNm2": state["sdl_kNm2"], "live_load_kNm2": state["live_load_kNm2"]}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


_INTERPRET_SYSTEM = """You are a structural advisor helping an architect during early design. You are given structural evaluation results: each element with its ID, type (beam or column), section, and utilisation % (100% = at the structural limit), a "May be removable" list, and — when present — a "Transfer beams" section. Write a concise advisory note.

CRITICAL: If overall_PASS is false, your FIRST sentence MUST identify the structure as failing and name the specific failing element IDs from the data. Do not discuss optimisation or underutilised elements until all failures are addressed.

USE ONLY THE DATA YOU ARE GIVEN:
- Mention only element IDs that appear in the evaluation data. Never invent, guess, or complete an ID. The example IDs below are illustrative format only — never repeat them as if they were real.
- Keep element types exactly as given — never call a beam a column or a column a beam.
- Quote utilisation figures and spans exactly as given. Never invent a number.
- Do NOT name rooms or locations ("living room", "kitchen", "staircase", "corridor") — the geometry does not tell you the room. Describe position only by what the data supports: element IDs, spans, and which elements are adjacent or clustered by their coordinates.

DESIGN INTENT — what to preserve vs reconsider:
- Elements above 75% utilisation are LOAD-PATH CRITICAL. Do not suggest removing or downsizing them; tell the architect these define the load path and must be preserved or upsized if the design changes.
- TRANSFER BEAMS (listed in the "Transfer beams" section) carry an upper-floor column as a point load. They are structurally defining regardless of utilisation — any layout change that removes or shortens them shifts load paths significantly. Always flag transfer beams by name, explain what upper-column load they carry, and call them "structurally defining."
- Elements below 50% are over-engineered. If on the "May be removable" list, removing them frees the plan; if not, the architect could reconsider the span arrangement.
- Elements 50–75%: working range — note them positively as well-calibrated for the current layout.
- NEVER suggest removing an element that is a transfer beam, load-path critical, or not on the "May be removable" list.

UTILISATION THRESHOLDS — use consistently:
- Below 50%: over-engineered. Suggest a specific LAYOUT change — remove the element (only if it is on the "May be removable" list) or open up the span.
- 50–75%: working range — note it positively.
- Above 75%: approaching limit — flag it clearly.
- Failures (100%+): must fix. Give 2 concrete options using exact element IDs.

LEVEL-BY-LEVEL framing (use only when the data has transfer beams or the evaluation covers multiple floor levels):
- Address each level in sequence: ground-level load paths first, then upper-level elements.
- For each transfer beam, state explicitly which upper column it carries and what happens to that column's load if the beam is modified.
- Distinguish "safe to remove" (low util, no transfers, on removable list) from "load-path critical" (transfer beam, high util, or KEEP).

For UNDERUTILISED columns (<70%): use the "May be removable" list to say what happens if removed, e.g. "Column <ID> is at <N>% — removing it keeps the connected beams within limits" or, if it needs an upgrade, "removing <ID> extends beam <ID> to <span> — a larger section would be needed." The "May be removable" list is exhaustive — only name columns that appear on it; never suggest removing any element not on that list, and never suggest removing a perimeter column. Columns marked KEEP must never be suggested for removal, even at low utilisation.

For UNDERUTILISED beams (<70%): ask whether that span is actually needed.

TRADEOFFS — always name the relevant tradeoff explicitly:
- Structural safety vs adaptability: elements near their limit (>75%) leave no headroom for future layout changes. The architect should know this upfront.
- Adaptability vs cost: removing an over-engineered element saves material cost but permanently removes a future structural option. Name both sides when suggesting removal.
- Safety vs cost: upsizing a section improves safety margins but increases material and modification cost. Say so when recommending upgrades.

Structure as a conversation, not a report:
- Line 1: one-sentence overall verdict in plain language.
- 2-3 bullets: the most important observations, each tied to a real element ID and its number. Include tradeoff language where it applies.
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
            from nodes._layout import get_structure as _gs_hint
            _layout_tmp = json.loads(layout_str)
            _all_cols = [
                el for el in _gs_hint(_layout_tmp)
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
            from nodes._layout import get_structure as _gs_hint2
            layout    = json.loads(layout_str)
            structure = _gs_hint2(layout)
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
                    f"safe — beam {worst['id']} extends {orig}m->{eff}m and stays within limits"
                    if safe else
                    f"extends beam {worst['id']} {orig}m->{eff}m — larger section needed"
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
    transfer_beams = summary.get("transfer_beams", [])
    if transfer_beams:
        lines.append("")
        lines.append("Transfer beams (carry upper-floor column loads — structurally defining, do NOT suggest removing):")
        for tb in transfer_beams:
            load_str = f"  upper-col load {tb['carries_upper_col_load_kN']}kN" if tb.get("carries_upper_col_load_kN") else ""
            lines.append(f"  {tb['id']:<10} span {tb['at_span_m']}m{load_str}  util {tb['utilisation_pct']:.1f}%")
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
        "transfer_beams": [
            {
                "id": b["id"],
                "at_span_m": round(b.get("effective_span_m", b.get("span_m", 0)), 2),
                "carries_upper_col_load_kN": round(b["transfer_point_load_kN"], 1) if b.get("transfer_point_load_kN") else None,
                "utilisation_pct": round(_beam_utilisation(b) * 100, 1),
            }
            for b in beams if b.get("is_transfer_beam")
        ],
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
            from nodes._layout import get_structure as _gs_ta
            layout = json.loads(state["layout_json_string"])
            n = len(_gs_ta(layout))
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

            # Read actual section sizes from the live layout (individual upgrades override defaults)
            from nodes._layout import get_structure as _gs_sec
            _struct_els = _gs_sec(json.loads(state["layout_json_string"]))
            _act_beams  = [e for e in _struct_els if len(e.get("geometry", [])) == 2]
            _act_cols   = [e for e in _struct_els if len(e.get("geometry", [])) == 1]

            def _bsec(el):
                a = el.get("attributes", {})
                if a.get("section"):                  return a["section"]
                if a.get("width") and a.get("depth"): return f"{a['width']}x{a['depth']}mm"
                return None

            def _csec(el):
                a = el.get("attributes", {})
                if a.get("section"):    return a["section"]
                if a.get("dimensions"): return str(a["dimensions"])
                return None

            _b_freq: dict = {}
            for _s in [_bsec(e) for e in _act_beams if _bsec(e)]:
                _b_freq[_s] = _b_freq.get(_s, 0) + 1
            _c_freq: dict = {}
            for _s in [_csec(e) for e in _act_cols if _csec(e)]:
                _c_freq[_s] = _c_freq.get(_s, 0) + 1

            _actual_beam_str = (max(_b_freq, key=_b_freq.get) + (" (mixed)" if len(_b_freq) > 1 else "")) if _b_freq else None
            _actual_col_str  = (max(_c_freq, key=_c_freq.get) + (" (mixed)" if len(_c_freq) > 1 else "")) if _c_freq else None

            print(f"\nWhat structural material are you working with? [current: {current}{tier_note}]")
            for i, mat in enumerate(BASE_MATERIALS, 1):
                active = base_current == mat
                display_sec = DEFAULT_SECTIONS.get(current if active else mat, DEFAULT_SECTIONS[mat])
                marker = f"  ← active{tier_note}" if active else ""
                if active and _actual_beam_str:
                    beam_disp = _actual_beam_str
                    col_disp  = _actual_col_str or f"{display_sec['col_dims']}mm"
                else:
                    beam_disp = f"{display_sec['beam_width_mm']}x{display_sec['beam_depth_mm']}mm"
                    col_disp  = f"{display_sec['col_dims']}mm"
                print(f"  {i}. {mat:6s} — beam {beam_disp} | col {col_disp}{marker}")
            print("  4. Right-size sections — find the minimum that still works")
            print("  [Enter] — keep current")
            _pt = _get_user_request(state.get("messages", [])).upper()
            _mat_default = next((m for m in BASE_MATERIALS if m in _pt), "")
            if _mat_default:
                print(f"  Material: {_mat_default}  [from prompt]")
                raw = _mat_default
            else:
                raw = _safe_input("Your choice [1/2/3/4 or RCC/STEEL/TIMBER]: ", "").strip().upper()
            lookup = {"1": "RCC", "2": "STEEL", "3": "TIMBER"}
            if raw == "4":
                print("\nWhich material should I optimise for?")
                for i, mat in enumerate(BASE_MATERIALS, 1):
                    xs_sec = DEFAULT_SECTIONS.get(f"{mat}_XS", DEFAULT_SECTIONS[mat])
                    print(f"  {i}. {mat:6s} — starting from {xs_sec['beam_width_mm']}x{xs_sec['beam_depth_mm']}mm beams | {xs_sec['col_dims']}mm cols")
                raw2 = _safe_input("Your choice [1/2/3 or RCC/STEEL/TIMBER]: ", "TIMBER").strip().upper()
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
            # Only reset sections to material defaults when the material is actually changing.
            # If every element already carries the target material, the layout has been saved
            # with individually upgraded sections — preserve them by skipping the override.
            from nodes._layout import get_structure as _gs_mat
            # Compare base materials only (strip tier suffix: STEEL_M -> STEEL)
            _base_override = material_override.upper().split("_")[0]
            _existing_mats = {
                ((el.get("attributes") or {}).get("material") or "RCC").upper().split("_")[0]
                for el in _gs_mat(json.loads(state["layout_json_string"]))
            }
            if _existing_mats <= {_base_override}:
                layout_str = state["layout_json_string"]
            else:
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
                if _safe_input("Try it? [y/N]: ", "y").strip().lower() == "y":
                    state["evaluation_result"] = json.dumps(result)
                    state["pending_structural_change"] = {"type": "tier_upgrade", "tier": next_tier}
                    state["layout_before_change"] = layout_str
                    return state

        # Assemble evaluation text
        _layout_id = json.loads(layout_str).get("layoutId", "unknown")
        lines = [
            f"Layout : {_layout_id}",
            f"Structural check: {'PASS' if summary['overall_PASS'] else 'FAIL'}",
            f"Beams  : {summary['total_beams']} checked, {summary['beam_failures']} failed",
            f"Columns: {summary['total_columns']} checked, {summary['column_failures']} failed",
        ]

        # What-if simulation: detect removal intent in messages
        # Skip on re-evaluations triggered by a structural change — the original
        # prompt still contains the "remove X" text but the intent is already done.
        remove_ids = [] if came_from == "structural_change" else _extract_removal_ids(state.get("messages", []))
        if remove_ids:
            from nodes._layout import get_structure as _gs_wi
            layout    = json.loads(layout_str)
            structure = _gs_wi(layout)
            col_ids   = {el["id"] for el in structure if len(el.get("geometry", [])) == 1}
            beam_ids  = {el["id"] for el in structure if len(el.get("geometry", [])) == 2}

            remove_cols  = [i for i in remove_ids if i in col_ids]
            remove_beams = [i for i in remove_ids if i in beam_ids]

            # ── ID not found — offer internal columns as a menu ──────────────
            if remove_ids and not remove_cols and not remove_beams:
                missing = ", ".join(remove_ids)
                internal_cols = sorted(
                    el["id"] for el in structure
                    if len(el.get("geometry", [])) == 1
                    and (el.get("attributes") or {}).get("type") == "internal"
                )
                print(f"\n  '{missing}' not found in this layout.")
                if internal_cols:
                    print("  Removable (internal) columns:")
                    for _i, _cid in enumerate(internal_cols, 1):
                        print(f"    {_i}. {_cid}")
                    _pick = _safe_input("  Pick a column to simulate removal [1-N or ID, Enter=skip]: ", "").strip()
                    if _pick:
                        if _pick.isdigit() and 1 <= int(_pick) <= len(internal_cols):
                            remove_cols = [internal_cols[int(_pick) - 1]]
                        elif _pick.upper() in {c.upper() for c in internal_cols}:
                            remove_cols = [_pick.upper()]

            beams  = [s for s in structure if len(s.get("geometry", [])) == 2]
            b_trib = _beam_trib_widths(beams)

            if remove_cols:
                # ── Column removal: full span-extension simulation ────────────
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
                    if r.get("is_transfer_beam"):
                        span_info = f"{r['original_span_m']}m+{round(r['effective_span_m']-r['original_span_m'],2)}m={r['effective_span_m']}m"
                        _P_total = r.get('transfer_point_load_kN', '?')
                        _P_col   = r.get('transfer_upper_col_kN')
                        _P_perp  = r.get('transfer_perp_kN')
                        if _P_col is not None and _P_perp is not None and _P_perp > 0:
                            _p_str = f"P={_P_total}kN ({_P_col} col + {_P_perp} framing)@{r.get('transfer_load_pos_m','?')}m"
                        else:
                            _p_str = f"P={_P_total}kN@{r.get('transfer_load_pos_m','?')}m"
                        lines.append(
                            f"  {r['id']:8s} [TRANSFER] {span_info}"
                            f"  {_p_str}"
                            f"  M={r.get('M_max_kNm','?')}kNm"
                            f"  S={r.get('sigma_bend_MPa','?')}MPa"
                            + (flag if flag else "  ok")
                        )
                    else:
                        span_info = (
                            f"{r['original_span_m']}m->{r['effective_span_m']}m"
                            if r.get("effective_span_m") else "unsupported"
                        )
                        lines.append(
                            f"  {r['id']:8s} {span_info:14s}"
                            f"  M={r.get('M_max_kNm','?')}kNm"
                            f"  S={r.get('sigma_bend_MPa','?')}MPa"
                            + (flag if flag else ("  unsupported" if not r.get("effective_span_m") else "  ok"))
                        )
                print("\n".join(lines[lines.index("") + 1:]))

                # Cascade check — lower-level column impacts
                cascade = whatif.get("cascade")
                if cascade:
                    cs = cascade["summary"]
                    clevel = cascade.get("target_level", "level below")
                    print(f"\n  CASCADE to {clevel}: {cs['affected']} column(s) carry extra load")
                    for cr in cascade.get("affected_columns", []):
                        flag = "FAIL" if not (cr.get("stress_PASS") and cr.get("buckling_PASS")) else "ok"
                        print(
                            f"    {cr['id']:8s}  extra +{cr.get('extra_load_kN_from_above','?')}kN"
                            f"  P_total={cr.get('P_total_kN','?')}kN"
                            f"  S={cr.get('sigma_comp_MPa','?')}MPa  [{flag}]"
                        )

                status = "PASS" if ws.get("overall_PASS", True) else "FAIL"

                # Check perimeter lock before offering the apply prompt
                from nodes._layout import find_element_in_layout as _feil_wi
                _wi_data = json.loads(layout_str)
                _locked = [
                    c for c in remove_cols
                    if (lambda lk, el: el is not None and (el.get("attributes") or {}).get("type") == "perimeter")(
                        *_feil_wi(_wi_data, c)
                    )
                ]
                if _locked:
                    print(
                        f"\nWhat-if result: {status} (structural only — cannot apply)."
                        f"\n  {', '.join(_locked)} {'is a' if len(_locked) == 1 else 'are'} "
                        f"perimeter element{'s' if len(_locked) > 1 else ''} — locked, defines the building envelope."
                    )
                else:
                    print(f"\nWhat-if result: {status}. Apply removal of {', '.join(remove_cols)} permanently?")
                    print("  Connected beams will be merged across the removed column.")
                    if _safe_input("Apply? [y/N]: ", "n").strip().lower() == "y":
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
                        is_tr = r.get("is_transfer_beam", False)
                        span_desc = (
                            f"transfer beam {r.get('original_span_m','?')}m+partner={r.get('effective_span_m','?')}m, "
                            f"point load P={r.get('transfer_point_load_kN','?')}kN at {r.get('transfer_load_pos_m','?')}m"
                        ) if is_tr else (
                            f"span {r.get('original_span_m','?')}m->{r.get('effective_span_m','?')}m"
                        )
                        if not r.get("bend_PASS", True):
                            fail_lines.append(
                                f"{r['id']}: bending S={r.get('sigma_bend_MPa','?')} > "
                                f"{r.get('allow_bend_MPa','?')} MPa ({span_desc})"
                            )
                        if not r.get("defl_LL_PASS", True):
                            fail_lines.append(
                                f"{r['id']}: LL deflection {r.get('delta_LL_mm','?')} > "
                                f"{r.get('limit_LL_mm','?')} mm ({span_desc})"
                            )
                        if not r.get("defl_TL_PASS", True):
                            fail_lines.append(
                                f"{r['id']}: TL deflection {r.get('delta_total_mm','?')} > "
                                f"{r.get('limit_TL_mm','?')} mm ({span_desc})"
                            )
                    cascade = whatif.get("cascade", {})
                    for cr in cascade.get("affected_columns", []):
                        if not (cr.get("stress_PASS") and cr.get("buckling_PASS")):
                            fail_lines.append(
                                f"{cr['id']} ({cr.get('level','lower level')}): "
                                f"cascaded load +{cr.get('extra_load_kN_from_above','?')}kN "
                                f"-> P={cr.get('P_total_kN','?')}kN "
                                f"S={cr.get('sigma_comp_MPa','?')} > {cr.get('allow_comp_MPa','?')} MPa"
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
                # ── Beam removal: tributary-width simulation ──────────────────
                b_id = remove_beams[0]
                from nodes._layout import find_element_in_layout as _feil_bw
                _bw_data = json.loads(layout_str)
                _lk_bw, _bw_el = _feil_bw(_bw_data, b_id)
                _bw_locked = _bw_el is not None and (_bw_el.get("attributes") or {}).get("type") == "perimeter"
                if _bw_locked:
                    print(f"\nWHAT-IF: {b_id} is a perimeter beam — locked, defines the building envelope. Cannot remove.")
                else:
                    bw_sim = _simulate_beam_removal(layout_str, b_id, b_trib, ll_kNm2=ll, sdl_kNm2=sdl)
                    result["what_if_beam"] = bw_sim
                    ws_b   = bw_sim.get("summary", {})
                    status_b = "PASS" if ws_b.get("overall_PASS") else "FAIL"

                    print(f"\nWHAT-IF: remove beam {b_id}  "
                          f"[span {bw_sim['removed_span_m']}m  trib={bw_sim['removed_trib_m']}m]")
                    for ew in bw_sim.get("edge_warnings", []):
                        print(f"  WARNING: {ew}")
                    if bw_sim.get("affected_beams"):
                        print("  Adjacent parallel beams re-checked with expanded tributary width:")
                        for r_b in bw_sim["affected_beams"]:
                            flag_b = ""
                            if not r_b.get("bend_PASS", True):
                                flag_b += f"  BEND FAIL S={r_b.get('sigma_bend_MPa','?')}>{r_b.get('allow_bend_MPa','?')}MPa"
                            if not r_b.get("defl_LL_PASS", True):
                                flag_b += f"  DEFL_LL FAIL {r_b.get('delta_LL_mm','?')}>{r_b.get('limit_LL_mm','?')}mm"
                            if not r_b.get("defl_TL_PASS", True):
                                flag_b += f"  DEFL_TL FAIL {r_b.get('delta_total_mm','?')}>{r_b.get('limit_TL_mm','?')}mm"
                            print(
                                f"  {r_b['id']:8s}  trib {r_b['trib_width_before_m']}m -> {r_b['trib_width_after_m']}m"
                                f"  M={r_b.get('M_max_kNm','?')}kNm  S={r_b.get('sigma_bend_MPa','?')}MPa"
                                + (flag_b if flag_b else "  ok")
                            )

                    print(f"\nWhat-if result: {status_b}. Apply removal of {b_id} permanently?")
                    print("  Adjacent beams carry the redistributed tributary load after removal.")
                    if _safe_input("Apply? [y/N]: ", "n").strip().lower() == "y":
                        state["evaluation_result"] = json.dumps(result)
                        state["pending_structural_change"] = {
                            "type":       "remove_element",
                            "element_id": b_id,
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

                raw_choice = _safe_input("Choice [1-N, comma-separated or range, or Enter]: ", "").strip()
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

            raw = _safe_input("Choice: ", "1").strip()
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

                # Free text -> append to messages so reason node can act on it
                state["messages"].append({
                    "role":    "user",
                    "content": f"User instruction after structural failure: {chosen}",
                })

        return state

    return evaluate_node
