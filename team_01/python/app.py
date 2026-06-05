from __future__ import annotations

import base64
import json
import re
import sys
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT           = Path(__file__).resolve().parents[2]
DEFAULT_LAYOUT_PATH = REPO_ROOT / "layout_input" / "layout_schema.json"
EDITED_LAYOUT_PATH  = REPO_ROOT / "team_01_edited_layout.json"
BEFORE_LAYOUT_PATH  = REPO_ROOT / "team_01_edited_layout_before.json"
VIEWER_BASE_URL     = "http://127.0.0.1:8000/layout_viewer.html"
PLAN_VIEWER_URL     = "http://127.0.0.1:8000/plan_viewer.html"
PYTHON_DIR          = Path(__file__).resolve().parent
LOGO_PATH           = PYTHON_DIR / "Assets" / "Logo.png"

_logo_b64 = ""
if LOGO_PATH.exists():
    try:
        _logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    except Exception:
        pass

if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

if not EDITED_LAYOUT_PATH.exists() and DEFAULT_LAYOUT_PATH.exists():
    EDITED_LAYOUT_PATH.write_text(
        DEFAULT_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )


# ── JSON helpers ───────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_layout(payload: object) -> dict:
    if isinstance(payload, dict):
        return payload.get("layout", payload) if isinstance(payload.get("layout"), dict) else payload
    if isinstance(payload, list):
        if not payload:
            raise ValueError("Uploaded JSON list is empty")
        first = payload[0]
        if isinstance(first, dict):
            return first.get("layout", first) if isinstance(first.get("layout"), dict) else first
        raise ValueError("First list item must be a layout object")
    raise ValueError("Layout JSON must be an object or a non-empty list")


def _load_working_layout() -> dict:
    if EDITED_LAYOUT_PATH.exists():
        return _normalize_layout(_read_json(EDITED_LAYOUT_PATH))
    if DEFAULT_LAYOUT_PATH.exists():
        return _normalize_layout(_read_json(DEFAULT_LAYOUT_PATH))
    return {}


@st.cache_data(ttl=5)
def _viewer_is_reachable() -> bool:
    try:
        with urllib.request.urlopen(VIEWER_BASE_URL, timeout=0.8) as r:
            return r.status == 200
    except Exception:
        return False


def _viewer_url(highlight: str = "", compare: bool = False,
                labels: bool = True, option_file: str = "") -> str:
    layout_stamp = int(EDITED_LAYOUT_PATH.stat().st_mtime_ns) if EDITED_LAYOUT_PATH.exists() else 0
    theme        = st.session_state.get("theme", "dark")
    url = (
        f"{VIEWER_BASE_URL}"
        f"?v={st.session_state.viewer_nonce}"
        f"&layout={layout_stamp}"
        f"&theme={theme}"
        f"&labels={'1' if labels else '0'}"
    )
    if highlight:
        url += f"&highlight={highlight}"
    if compare and BEFORE_LAYOUT_PATH.exists():
        url += "&mode=compare"
    if option_file:
        url += f"&optionFile={option_file}"
    return url


def _plan_viewer_url(highlight: str = "", option_file: str = "") -> str:
    layout_stamp = int(EDITED_LAYOUT_PATH.stat().st_mtime_ns) if EDITED_LAYOUT_PATH.exists() else 0
    theme        = st.session_state.get("theme", "dark")
    url = (
        f"{PLAN_VIEWER_URL}"
        f"?v={st.session_state.viewer_nonce}"
        f"&layout={layout_stamp}"
        f"&theme={theme}"
    )
    if highlight:
        url += f"&highlight={highlight}"
    if option_file:
        url += f"&optionFile={option_file}"
    return url


def _count_elements(layout: dict) -> tuple[int, int]:
    cols  = sum(1 for el in layout.get("structure", []) if len(el.get("geometry", [])) == 1)
    beams = sum(1 for el in layout.get("structure", []) if len(el.get("geometry", [])) == 2)
    return cols, beams


# ── SVG Floor Plan ────────────────────────────────────────────────────────────

def _svg_poly_points(geo, fy):
    return " ".join(f"{x},{fy(y)}" for x, y in geo)


def _svg_centroid(geo):
    pts = geo[:-1] if len(geo) > 2 and geo[0] == geo[-1] else geo
    xs, ys = zip(*pts)
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _svg_dims(geo):
    xs = [p[0] for p in geo]; ys = [p[1] for p in geo]
    return max(xs) - min(xs), max(ys) - min(ys), max(ys), (min(xs) + max(xs)) / 2


def _door_swing_points(a, b, fy_fn, n=12):
    import math
    r  = math.hypot(b[0] - a[0], b[1] - a[1])
    t0 = math.atan2(b[1] - a[1], b[0] - a[0])
    pts = []
    for i in range(n + 1):
        t = t0 + (math.pi / 2) * (i / n)
        pts.append((a[0] + r * math.cos(t), fy_fn(a[1] + r * math.sin(t))))
    return " ".join(f"{x},{y}" for x, y in pts)


def _render_floor_plan_svg(
    layout: dict,
    eval_result: dict | None = None,
    selected_el: str = "",
    is_dark: bool = True,
    height: int = 540,
) -> str:
    # ── Colors ──────────────────────────────────────────────────────────────
    FG     = "#c8eeed" if is_dark else "#1a2a30"
    BG     = "#071a1a" if is_dark else "#f5f7fa"
    ACCENT = "#2ac0c0" if is_dark else "#088a87"
    PASS_C = "#40d090"
    FAIL_C = "#ff5050"
    SEL_C  = "#ffd060"
    WIN_C  = "#4696dc"

    # ── Bounding box from all geometry ──────────────────────────────────────
    all_pts: list = list(layout.get("outline", []))
    for r in layout.get("rooms",     []): all_pts.extend(r.get("geometry", []))
    for d in layout.get("doors",     []): all_pts.extend(d.get("geometry", []))
    for w in layout.get("windows",   []): all_pts.extend(w.get("geometry", []))
    for f in layout.get("furniture", []): all_pts.extend(f.get("geometry", []))
    for s in layout.get("structure", []): all_pts.extend(s.get("geometry", []))

    if not all_pts:
        return (
            f'<div style="height:{height}px;display:flex;align-items:center;'
            f'justify-content:center;color:{FG};background:{BG};border-radius:8px">'
            f'No layout data</div>'
        )

    xs = [p[0] for p in all_pts]; ys = [p[1] for p in all_pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    span = max(x1 - x0, y1 - y0) or 1
    pad  = span * 0.07 + 0.5
    vb_x, vb_y = x0 - pad, y0 - pad
    vb_w, vb_h = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad

    def fy(y): return (y0 + y1) - y   # flip: plan y-up → SVG y-down

    u = span * 0.012   # unit: ~1 % of span → scales strokes/text/radii

    # ── Eval status lookup: id → "pass" | "fail" ────────────────────────────
    el_status: dict[str, str] = {}
    if eval_result:
        for b in eval_result.get("beams", []):
            ok = b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"]
            el_status[b["id"]] = "pass" if ok else "fail"
        for c in eval_result.get("columns", []):
            ok = c["stress_PASS"] and c["buckling_PASS"]
            el_status[c["id"]] = "pass" if ok else "fail"

    parts: list[str] = []

    # ── Layer 1: Rooms (fill + label) ────────────────────────────────────────
    for room in layout.get("rooms", []):
        geo = room.get("geometry", [])
        if len(geo) < 3:
            continue
        pts = _svg_poly_points(geo, fy)
        cx, cy = _svg_centroid(geo)
        w, _h, _top, _ = _svg_dims(geo)
        label = room.get("name", "")
        parts.append(
            f'<polygon points="{pts}" fill="{FG}" fill-opacity="0.04" '
            f'stroke="{FG}" stroke-opacity="0.35" stroke-width="{u*0.18}" '
            f'vector-effect="non-scaling-stroke"/>'
        )
        if label and w > u * 3:
            parts.append(
                f'<text x="{cx}" y="{fy(cy)}" text-anchor="middle" '
                f'dominant-baseline="central" font-family="monospace" '
                f'font-size="{u*1.05}" fill="{FG}" fill-opacity="0.55">{label}</text>'
            )

    # ── Layer 2: Exterior outline ────────────────────────────────────────────
    outline = layout.get("outline", [])
    if len(outline) > 1:
        pts = _svg_poly_points(outline, fy)
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{FG}" stroke-opacity="0.9" '
            f'stroke-width="{u*0.3}" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
        )

    # ── Layer 3: Doors (gap + swing arc + radius arm) ────────────────────────
    for door in layout.get("doors", []):
        geo = door.get("geometry", [])
        if len(geo) < 2:
            continue
        a, b = geo[0], geo[-1]
        ax, ay = a[0], fy(a[1])
        arc_pts = _door_swing_points(a, b, fy)
        arc_end_xy = arc_pts.split(" ")[-1].split(",")
        parts.append(
            f'<line x1="{ax}" y1="{ay}" x2="{b[0]}" y2="{fy(b[1])}" '
            f'stroke="{BG}" stroke-width="{u*0.55}" vector-effect="non-scaling-stroke"/>'
        )
        parts.append(
            f'<polyline points="{arc_pts}" fill="none" stroke="{FG}" stroke-opacity="0.45" '
            f'stroke-width="{u*0.18}" stroke-dasharray="{u*0.4} {u*0.3}" '
            f'vector-effect="non-scaling-stroke"/>'
        )
        parts.append(
            f'<line x1="{ax}" y1="{ay}" x2="{arc_end_xy[0]}" y2="{arc_end_xy[1]}" '
            f'stroke="{FG}" stroke-opacity="0.45" stroke-width="{u*0.18}" '
            f'vector-effect="non-scaling-stroke"/>'
        )

    # ── Layer 4: Windows ─────────────────────────────────────────────────────
    for win in layout.get("windows", []):
        geo = win.get("geometry", [])
        if len(geo) < 2:
            continue
        parts.append(
            f'<polyline points="{_svg_poly_points(geo, fy)}" fill="none" stroke="{WIN_C}" '
            f'stroke-width="{u*0.45}" vector-effect="non-scaling-stroke"/>'
        )

    # ── Layer 5: Furniture ───────────────────────────────────────────────────
    for furn in layout.get("furniture", []):
        geo = furn.get("geometry", [])
        if len(geo) < 3:
            continue
        parts.append(
            f'<polygon points="{_svg_poly_points(geo, fy)}" fill="{FG}" fill-opacity="0.09" '
            f'stroke="{FG}" stroke-opacity="0.3" stroke-width="{u*0.14}" '
            f'vector-effect="non-scaling-stroke"/>'
        )

    # ── Layer 6: Structure — beams then columns on top ───────────────────────
    structure = layout.get("structure", [])
    beams = [s for s in structure if len(s.get("geometry", [])) == 2]
    cols  = [s for s in structure if len(s.get("geometry", [])) == 1]

    for beam in beams:
        eid    = beam["id"]
        geo    = beam["geometry"]
        p1, p2 = geo[0], geo[1]
        status = el_status.get(eid, "none")
        stroke = FAIL_C if status == "fail" else (PASS_C if status == "pass" else ACCENT)
        is_sel = eid == selected_el
        sw     = u * 0.38 * (1.6 if is_sel else 1.0)
        # Visible line
        parts.append(
            f'<line data-eid="{eid}" x1="{p1[0]}" y1="{fy(p1[1])}" '
            f'x2="{p2[0]}" y2="{fy(p2[1])}" stroke="{SEL_C if is_sel else stroke}" '
            f'stroke-width="{sw}" stroke-linecap="round" '
            f'vector-effect="non-scaling-stroke" style="cursor:pointer"/>'
        )
        # Wider transparent hit area
        parts.append(
            f'<line data-eid="{eid}" x1="{p1[0]}" y1="{fy(p1[1])}" '
            f'x2="{p2[0]}" y2="{fy(p2[1])}" stroke="transparent" '
            f'stroke-width="{u*1.8}" vector-effect="non-scaling-stroke" style="cursor:pointer"/>'
        )

    for col_el in cols:
        eid    = col_el["id"]
        geo    = col_el["geometry"]
        cx_c   = geo[0][0]
        cy_c   = fy(geo[0][1])
        status = el_status.get(eid, "none")
        fill   = FAIL_C if status == "fail" else (PASS_C if status == "pass" else ACCENT)
        is_sel = eid == selected_el
        r_c    = u * (1.0 if is_sel else 0.75)
        parts.append(
            f'<circle data-eid="{eid}" cx="{cx_c}" cy="{cy_c}" r="{r_c}" '
            f'fill="{SEL_C if is_sel else fill}" fill-opacity="0.85" '
            f'stroke="{FG}" stroke-opacity="0.3" stroke-width="{u*0.12}" '
            f'vector-effect="non-scaling-stroke" style="cursor:pointer"/>'
        )

    # ── Assemble ─────────────────────────────────────────────────────────────
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x} {vb_y} {vb_w} {vb_h}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%;height:{height}px;background:{BG};border-radius:8px;display:block">'
        + "".join(parts)
        + f'</svg>'
        f'<script>'
        f'document.querySelectorAll("[data-eid]").forEach(function(el){{'
        f'  el.addEventListener("click",function(){{'
        f'    var eid=this.getAttribute("data-eid");'
        f'    window.parent.postMessage({{type:"selectElement",elementId:eid}},"*");'
        f'  }});'
        f'}});'
        f'</script>'
    )


# ── Structural helpers ─────────────────────────────────────────────────────────

def _run_evaluate(layout_json_str: str, sdl: float = 3.5, ll: float = 2.0) -> dict | None:
    try:
        from nodes.evaluate import evaluate_structure
        return evaluate_structure(layout_json_str, ll_kNm2=ll, sdl_kNm2=sdl)
    except Exception as e:
        st.warning(f"Evaluation error: {e}")
        return None


def _run_grid_options(layout: dict, material: str) -> list[dict]:
    try:
        from nodes.tools import build_structural_grid_with_options
        bundle = build_structural_grid_with_options(layout, "", material=material)
        return bundle.get("options", [])
    except Exception as e:
        st.warning(f"Grid options error: {e}")
        return []


def _run_cost_flex(before_str: str, after_str: str) -> dict | None:
    try:
        from nodes.cost_flexibility import build_cost_flexibility_node
        node = build_cost_flexibility_node()
        state: dict = {
            "layout_json_string":          after_str,
            "layout_before_change":        before_str,
            "original_layout_json_string": before_str,
            "came_from":                   "modify",
        }
        out = node(state)
        return out.get("cost_flexibility")
    except Exception as e:
        st.warning(f"Cost/flex error: {e}")
        return None


def _get_failure_alternatives(eval_result: dict, material: str) -> list[str]:
    try:
        from nodes.evaluate import _build_failure_alternatives
        return _build_failure_alternatives(eval_result, [], material)
    except Exception:
        return []


def _run_comparison(before_str: str, after_str: str) -> str:
    try:
        from _runtime.bootstrap import bootstrap
        from nodes.comparison import build_comparison_node
        ctx  = bootstrap()
        node = build_comparison_node(ctx.llm)
        state: dict = {
            "layout_json_string":   after_str,
            "layout_before_change": before_str,
            "came_from":            "structural_change",
            "messages":             [],
            "cycle":                0,
        }
        out = node(state)
        return out.get("comparison_result", "")
    except Exception:
        return ""


def _element_cost(el: dict) -> float:
    import math
    _C = {"RCC": 350.0, "STEEL": 12_000.0, "TIMBER": 800.0}
    attrs = el.get("attributes", {})
    mat   = (attrs.get("material") or "RCC").upper()
    key   = "STEEL" if "STEEL" in mat else ("TIMBER" if "TIMBER" in mat else "RCC")
    c_m3  = _C[key]
    if len(el.get("geometry", [])) == 2:
        import math as _m
        span = _m.dist(el["geometry"][0], el["geometry"][1])
        d = float(attrs.get("depth") or 250) / 1000.0
        w = float(attrs.get("width") or 175) / 1000.0
        return round(span * d * w * c_m3)
    else:
        dims  = str(attrs.get("dimensions", "175x175"))
        parts = dims.split("x")
        cw = float(parts[0]) / 1000.0 if parts else 0.175
        cd = float(parts[1]) / 1000.0 if len(parts) > 1 else cw
        return round(cw * cd * 3.0 * c_m3)


def _apply_structural_change(
    before_str: str,
    new_str: str,
    reset_grid: bool = False,
) -> None:
    """Save a structural change: persist files, auto-eval, run cost+comparison."""
    new_layout = json.loads(new_str)
    BEFORE_LAYOUT_PATH.write_text(before_str, encoding="utf-8")
    _write_json(EDITED_LAYOUT_PATH, new_layout)
    st.session_state.viewer_nonce    += 1
    st.session_state.cost_flexibility = None
    st.session_state.last_comparison  = None
    if reset_grid:
        st.session_state.grid_options = []

    if st.session_state.get("auto_eval", True):
        _mat = st.session_state.get("material", "RCC")
        _sdl = st.session_state.get("sdl_kNm2", 3.5)
        _ll  = st.session_state.get("live_load_kNm2", 2.0)
        from nodes.modify import apply_material_override
        with st.spinner("Evaluating structure…"):
            _ev = _run_evaluate(apply_material_override(new_str, _mat), sdl=_sdl, ll=_ll)
        st.session_state.eval_result = _ev
        st.session_state.eval_alts   = _get_failure_alternatives(_ev or {}, _mat)
        with st.spinner("Analysing cost & changes…"):
            _cf = _run_cost_flex(before_str, new_str)
            _cmp = _run_comparison(before_str, new_str)
        if _cf:
            st.session_state.cost_flexibility = _cf
        if _cmp:
            st.session_state.output_log.append(_cmp)
            st.session_state.last_comparison = _cmp
    else:
        st.session_state.eval_result = None
        st.session_state.eval_alts   = []


def _apply_alternative(alt: str, layout_str: str, material: str,
                        sdl: float, ll: float) -> tuple[str, dict | None]:
    from nodes.modify import (
        upgrade_element_section, add_midspan_column,
        apply_material_override, BEAM_SECTION_UPGRADE, BEAM_DIM_UPGRADE,
        COL_SECTION_UPGRADE, COL_DIM_UPGRADE, BASE_MATERIALS,
    )
    from nodes.evaluate import evaluate_structure

    if re.match(r"Auto-upgrade \d+ failing beam", alt, re.IGNORECASE):
        ev = st.session_state.eval_result or {}
        for _ in range(8):
            fails = [b for b in ev.get("beams", [])
                     if not (b["bend_PASS"] and b["shear_PASS"]
                             and b["defl_TL_PASS"] and b["defl_LL_PASS"])]
            if not fails:
                break
            for b in fails:
                cur = b.get("section_mm", "")
                if cur in BEAM_SECTION_UPGRADE:
                    nxt, _, _ = BEAM_SECTION_UPGRADE[cur]
                    layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                elif cur in BEAM_DIM_UPGRADE:
                    nxt, _, _ = BEAM_DIM_UPGRADE[cur]
                    layout_str = upgrade_element_section(layout_str, b["id"], nxt)
            ev = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
        return layout_str, ev

    if re.match(r"Auto-upgrade \d+ failing col", alt, re.IGNORECASE):
        ev = st.session_state.eval_result or {}
        for _ in range(8):
            fails = [c for c in ev.get("columns", [])
                     if not (c["stress_PASS"] and c["buckling_PASS"])]
            if not fails:
                break
            for c in fails:
                cur = c.get("section_mm", "")
                if cur in COL_SECTION_UPGRADE:
                    nxt, _ = COL_SECTION_UPGRADE[cur]
                    layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                elif cur in COL_DIM_UPGRADE:
                    nxt = COL_DIM_UPGRADE[cur]
                    layout_str = upgrade_element_section(layout_str, c["id"], nxt)
            ev = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
        return layout_str, ev

    m = re.match(r"Upgrade (\S+) from \S+ to (\S+)", alt, re.IGNORECASE)
    if m:
        elem_id, new_sec = m.group(1), m.group(2)
        layout_str = upgrade_element_section(layout_str, elem_id, new_sec)
        ev = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
        return layout_str, ev

    m2 = re.match(r"Add midspan column under (?:beam )?(\S+)", alt, re.IGNORECASE)
    if m2:
        beam_id = m2.group(1).rstrip("(")
        layout_str = add_midspan_column(layout_str, beam_id, material)
        ev = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
        return layout_str, ev

    m3 = re.match(r"Switch all framing to (\w+)", alt, re.IGNORECASE)
    if m3:
        new_mat = m3.group(1).upper()
        if new_mat in BASE_MATERIALS:
            layout_str = apply_material_override(layout_str, new_mat)
            ev = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
            return layout_str, ev

    m4 = re.match(r"Upgrade all to (\S+)", alt, re.IGNORECASE)
    if m4:
        tier = m4.group(1)
        layout_str = apply_material_override(layout_str, tier)
        ev = evaluate_structure(layout_str, ll_kNm2=ll, sdl_kNm2=sdl)
        return layout_str, ev

    return layout_str, None


# ── Agent chat ─────────────────────────────────────────────────────────────────

def _run_agent_chat(prompt: str, layout: dict, eval_result: dict | None = None) -> str:
    try:
        from _runtime.bootstrap import bootstrap
        from _runtime.llm import call_llm
        from nodes.reason import SYSTEM_PROMPT
        from nodes.tools import get_action_tools
        from graph import _format_tool_catalog

        ctx          = bootstrap()
        tool_catalog = _format_tool_catalog(get_action_tools())
        structure    = layout.get("structure", [])
        beams        = [el for el in structure if len(el.get("geometry", [])) == 2]
        cols         = [el for el in structure if len(el.get("geometry", [])) == 1]

        eval_lines = ""
        if eval_result:
            s = eval_result.get("summary", {})
            eval_lines = (
                f"\nEvaluation: {'PASS' if s.get('overall_PASS') else 'FAIL'}, "
                f"{s.get('beam_failures', 0)} beam failures, "
                f"{s.get('column_failures', 0)} column failures."
            )
            for b in eval_result.get("beams", []):
                if not (b.get("bend_PASS") and b.get("shear_PASS")
                        and b.get("defl_TL_PASS") and b.get("defl_LL_PASS")):
                    eval_lines += (
                        f"\n  BEAM {b['id']} FAIL "
                        f"(S={b['sigma_bend_MPa']}MPa, span={b['span_m']}m, "
                        f"section={b.get('section_mm','?')})"
                    )
            for c in eval_result.get("columns", []):
                if not (c.get("stress_PASS") and c.get("buckling_PASS")):
                    eval_lines += (
                        f"\n  COL {c['id']} FAIL "
                        f"(S={c['sigma_comp_MPa']}MPa, SF={c['SF_buckling']})"
                    )

        context_msg = {
            "role": "user",
            "content": (
                f"Context: Layout '{layout.get('layoutId', '?')}' has "
                f"{len(cols)} columns and {len(beams)} beams.{eval_lines}\n\n"
                f"Valid rooms: {[r.get('name') for r in layout.get('rooms', [])]}\n\n"
                f"User request:\n{prompt}\n\n"
                f"Layout summaries:\n"
                f"{json.dumps({'layoutId': layout.get('layoutId'), 'rooms': [{'id': r['id'], 'name': r['name']} for r in layout.get('rooms', [])]})}"
            ),
        }

        result = call_llm(ctx.llm, SYSTEM_PROMPT, [context_msg], tool_catalog)

        if result.get("action") == "tool":
            calls = result.get("tool_calls", [])
            if any(c.get("name") == "tag_and_audit" for c in calls):
                return "GENERATE_GRID"
            if calls:
                first = calls[0]
                return (
                    f"Agent wants to apply **{first.get('name', 'action')}** — "
                    "use the controls in the left panel to proceed."
                )

        resp = result.get("final_response", "")
        if not resp:
            return "EVALUATE"
        return resp
    except Exception as e:
        return f"Agent error: {e}"


# ── Session state ──────────────────────────────────────────────────────────────

def _ensure_session() -> None:
    defaults: dict = {
        "viewer_nonce":    0,
        "history":         [],
        "agent_log":       [],
        "eval_result":     None,
        "eval_alts":       [],
        "state_history":   [],
        "cost_flexibility": None,
        "last_comparison": None,
        "material":        "RCC",
        "sdl_kNm2":        3.5,
        "live_load_kNm2":  2.0,
        "grid_options":    [],
        "selected_grid":   None,
        "output_log":      [],
        "theme":           "light",
        "selected_el":     "",
        "compare_mode":    False,
        "labels_on":       False,
        "auto_eval":       True,
        "snapshots":       [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Page setup ─────────────────────────────────────────────────────────────────

st.set_page_config(page_title="PermanenceOS", layout="wide", initial_sidebar_state="collapsed")
_ensure_session()

_pending_sel = st.query_params.get("_sel", "")
if _pending_sel and _pending_sel != st.session_state.get("_last_sel_applied", ""):
    st.session_state.selected_el = _pending_sel
    st.session_state["_last_sel_applied"] = _pending_sel

_is_light = st.session_state.get("theme", "dark") == "light"

_DARK = """
  [data-testid="stAppViewContainer"]{background:#071a1a}
  [data-testid="stMain"]{background:#071a1a}
  [role="tabpanel"]{background:#071a1a!important}
  [data-testid="stTabPanel"]{background:#071a1a!important}
  [data-testid="stVerticalBlock"]{background:transparent}
  [data-testid="stForm"]{background:#0d2828!important;border:1px solid #1a5555!important;border-radius:8px!important}
  [data-testid="stTextArea"] textarea{background:#0d2828!important;color:#c8eeed!important;border-color:#1a5555!important}
  [data-testid="stTextInput"] input{background:#0d2828!important;color:#c8eeed!important;border-color:#1a5555!important}
  [data-baseweb="select"] > div{background:#0d2828!important;border-color:#1a5555!important;color:#c8eeed!important}
  [data-baseweb="popover"] [role="listbox"]{background:#0d2828!important}
  [data-baseweb="popover"] [role="option"]{color:#c8eeed!important}
  [data-testid="stExpander"] details{background:#0d2828!important;border:1px solid #1a5555!important}
  [data-testid="stExpander"] summary{color:#2ac0c0!important}
  [data-testid="stFileUploader"] section{background:#0d2828!important;border-color:#1a5555!important}
  [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"]{background:#2ac0c0!important}
  [data-testid="stRadio"] label p{color:#a0d8d8!important}
  [data-testid="stCheckbox"] label p{color:#a0d8d8!important}
  [data-testid="stSelectSlider"] [data-testid="stMarkdown"]{color:#c8eeed!important}
  p,label{color:#c8eeed}
  [data-testid="stWidgetLabel"] p{color:#a0d8d8!important}
  [data-testid="stMetricLabel"] p{color:#6ab8b8!important;font-size:.72rem}
  [data-testid="stMetricValue"]{color:#c8eeed!important}
  [data-testid="stCaption"] p,[data-testid="stCaptionContainer"] p{color:#6ab8b8!important}
  small{color:#6ab8b8!important}
  [data-testid="stMarkdown"] p{color:#c8eeed}
  .stat-chip{display:inline-block;background:#0d3030;border:1px solid #1a5555;border-radius:4px;padding:2px 10px;margin-left:5px;font-size:.78rem;color:#a0d8d8}
  .stat-chip b{color:#c8eeed}
  .needs-review{background:#3a1a08;color:#ff9860;border-color:#7a4020}
  .panel-hdr{font-size:.72rem;font-weight:700;color:#2ac0c0;letter-spacing:1.5px;text-transform:uppercase;margin:10px 0 5px;padding-bottom:3px;border-bottom:1px solid #1a4040}
  .grid-card{border:1px solid #1a5555;border-radius:6px;padding:7px 10px;margin-bottom:4px;background:#0d2828}
  .grid-card-active{border-color:#2ac0c0;background:#0d3030}
  .grid-label{font-size:.86rem;font-weight:700;color:#c8eeed}
  .grid-spacing{font-size:.73rem;color:#6ab8b8}
  .grid-stats{font-size:.76rem;color:#5a9090;margin-top:2px}
  .eval-big{font-size:2.6rem;font-weight:800;line-height:1.1}
  .eval-label{font-size:.68rem;color:#5a9090;text-transform:uppercase;letter-spacing:.5px}
  .eval-fail{color:#ff5050}.eval-pass{color:#40d090}
  .crit-item{background:#0d2828;border-left:3px solid #cc3030;padding:5px 8px;margin-bottom:4px;border-radius:2px;font-size:.76rem;color:#a0d8d8}
  .pass-badge{background:#0a4040;color:#2ac0c0;padding:2px 10px;border-radius:4px;font-weight:700;font-size:.78rem;display:inline-block;margin:4px 0}
  .agent-response{background:#0d2828;border-left:3px solid #2ac0c0;padding:8px 12px;border-radius:3px;font-size:.80rem;color:#c8eeed;margin-top:6px;line-height:1.5}
  .cost-box{background:#0d2828;border:1px solid #1a5555;border-radius:6px;padding:10px 12px;margin-top:6px}
  .alt-btn{background:#0d3030;border:1px solid #1a5555;border-radius:4px;padding:4px 8px;margin-bottom:4px;font-size:.76rem;color:#6ab8b8;cursor:pointer}
  .snap-pill{display:inline-block;background:#0d3030;border:1px solid #1a5555;color:#6ab8b8;padding:3px 10px;border-radius:10px;margin:2px;font-size:.74rem}
  .snap-pill-active{background:#1a5555;border-color:#2ac0c0;color:#2ac0c0;font-weight:700}
  .viewer-label{font-size:.70rem;color:#5a9090;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px}
  .state-pill{display:inline-block;background:#0d3030;color:#6ab8b8;padding:2px 8px;border-radius:10px;margin:2px;font-size:.74rem}
  .log-entry{background:#0d2828;border-left:3px solid #2ac0c0;padding:5px 8px;margin-bottom:4px;border-radius:3px;font-size:.79rem;color:#8abfbf}
"""
_LIGHT = """
  [data-testid="stAppViewContainer"]{background:#f5f7fa}
  .stat-chip{display:inline-block;background:#fff;border:1px solid #c0d8d8;border-radius:4px;padding:2px 10px;margin-left:5px;font-size:.78rem;color:#2a5050}
  .stat-chip b{color:#088a87}
  .needs-review{background:#fff0e8;color:#c04010;border-color:#e08060}
  .panel-hdr{font-size:.72rem;font-weight:700;color:#088a87;letter-spacing:1.5px;text-transform:uppercase;margin:10px 0 5px;padding-bottom:3px;border-bottom:1px solid #b0d8d8}
  .grid-card{border:1px solid #c8dede;border-radius:6px;padding:7px 10px;margin-bottom:4px;background:#fff}
  .grid-card-active{border-color:#088a87;background:#e6f7f7}
  .grid-label{font-size:.86rem;font-weight:700;color:#1a2a30}
  .grid-spacing{font-size:.73rem;color:#4a7070}
  .grid-stats{font-size:.76rem;color:#5a7070;margin-top:2px}
  .eval-big{font-size:2.6rem;font-weight:800;line-height:1.1}
  .eval-label{font-size:.68rem;color:#4a7070;text-transform:uppercase;letter-spacing:.5px}
  .eval-fail{color:#cc2020}.eval-pass{color:#088a87}
  .crit-item{background:#fff4f4;border-left:3px solid #cc3030;padding:5px 8px;margin-bottom:4px;border-radius:2px;font-size:.76rem;color:#2a3040}
  .pass-badge{background:#d4f0ee;color:#065f5d;padding:2px 10px;border-radius:4px;font-weight:700;font-size:.78rem;display:inline-block;margin:4px 0}
  .agent-response{background:#e8f7f7;border-left:3px solid #088a87;padding:8px 12px;border-radius:3px;font-size:.80rem;color:#1a2a30;margin-top:6px;line-height:1.5}
  .cost-box{background:#f0f9f9;border:1px solid #b0d8d8;border-radius:6px;padding:10px 12px;margin-top:6px}
  .alt-btn{background:#e6f0f0;border:1px solid #a0c8c8;border-radius:4px;padding:4px 8px;margin-bottom:4px;font-size:.76rem;color:#1a4040;cursor:pointer}
  .snap-pill{display:inline-block;background:#e6f0f0;border:1px solid #a0c8c8;color:#1a4040;padding:3px 10px;border-radius:10px;margin:2px;font-size:.74rem}
  .snap-pill-active{background:#c0e4e4;border-color:#088a87;color:#065f5d;font-weight:700}
  .viewer-label{font-size:.70rem;color:#5a7070;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px}
  .state-pill{display:inline-block;background:#e6f0f0;color:#2a5050;padding:2px 8px;border-radius:10px;margin:2px;font-size:.74rem}
  .log-entry{background:#e8f7f7;border-left:3px solid #088a87;padding:5px 8px;margin-bottom:4px;border-radius:3px;font-size:.79rem;color:#1a3030}
"""
_fail_ct = ".fail-ct{color:#ff6060;font-weight:700}.pass-ct{color:#40c040;font-weight:700}"
if _is_light:
    _fail_ct = ".fail-ct{color:#cc2020;font-weight:700}.pass-ct{color:#208020;font-weight:700}"

st.markdown(
    f"<style>"
    f"[data-testid='block-container']{{padding-top:.6rem;padding-bottom:.3rem}}"
    f"div[data-testid='stTabs'] button{{font-size:.82rem}}"
    f"{_fail_ct}"
    f"{''.join((_LIGHT if _is_light else _DARK).splitlines())}"
    f"</style>",
    unsafe_allow_html=True,
)

# ── Load working layout ────────────────────────────────────────────────────────

layout_obj      = _load_working_layout()
n_cols, n_beams = _count_elements(layout_obj)
er              = st.session_state.eval_result
has_failures    = (
    er is not None
    and (er.get("summary", {}).get("beam_failures", 0) > 0
         or er.get("summary", {}).get("column_failures", 0) > 0)
)

# ── Header ─────────────────────────────────────────────────────────────────────

_hdr_logo_html = (
    f'<img src="data:image/png;base64,{_logo_b64}" style="height:88px;width:auto">'
    if _logo_b64 else '<span style="font-size:1.6rem;font-weight:800;color:#1a2a30">PermanenceOS</span>'
)
st.markdown(
    f'<div style="background:#ffffff;margin:-0.6rem -2rem 0.5rem;padding:12px 2rem;'
    f'display:flex;align-items:center;gap:14px;border-bottom:2px solid #E0E0E0">'
    f'{_hdr_logo_html}</div>',
    unsafe_allow_html=True,
)

hdr_stats, hdr_undo, hdr_theme, hdr_export = st.columns([5, 1, 1, 1])

with hdr_stats:
    review    = '<span class="stat-chip needs-review">&#9888; Needs review</span>' if has_failures else ""
    _cf_hdr   = st.session_state.get("cost_flexibility")
    cost_chip = (
        f'<span class="stat-chip">net <b>${_cf_hdr["net_cost_usd"]:+,.0f}</b></span>'
        if _cf_hdr else ""
    )
    st.markdown(
        f'<span class="stat-chip"><b>{n_cols}</b> columns</span>'
        f'<span class="stat-chip"><b>{n_beams}</b> beams</span>'
        f'{cost_chip}{review}',
        unsafe_allow_html=True,
    )

with hdr_undo:
    _can_undo = BEFORE_LAYOUT_PATH.exists()
    if st.button("↩ Undo", use_container_width=True, key="btn_undo",
                 disabled=not _can_undo, help="Restore layout to previous state"):
        _current = EDITED_LAYOUT_PATH.read_text(encoding="utf-8") if EDITED_LAYOUT_PATH.exists() else "{}"
        _before  = BEFORE_LAYOUT_PATH.read_text(encoding="utf-8")
        EDITED_LAYOUT_PATH.write_text(_before,  encoding="utf-8")
        BEFORE_LAYOUT_PATH.write_text(_current, encoding="utf-8")
        st.session_state.viewer_nonce    += 1
        st.session_state.eval_result      = None
        st.session_state.eval_alts        = []
        st.session_state.cost_flexibility = None
        st.session_state.last_comparison  = None
        st.rerun()

with hdr_theme:
    if st.button("Light" if not _is_light else "Dark", use_container_width=True, key="btn_theme"):
        st.session_state.theme = "light" if not _is_light else "dark"
        st.rerun()

with hdr_export:
    st.download_button(
        "Export JSON",
        data=json.dumps(layout_obj, indent=2, ensure_ascii=False),
        file_name="layout_export.json",
        mime="application/json",
        use_container_width=True,
    )

st.divider()

# ── Three-column body ──────────────────────────────────────────────────────────
# Proportions: left controls | large 2D plan | right analysis
col_ctrl, col_plan, col_analysis = st.columns([1.3, 3.2, 1.6], gap="medium")


# ══════════════════════════════════════════════════════════════════════════════
# LEFT — Controls
# ══════════════════════════════════════════════════════════════════════════════

with col_ctrl:

    # ── Layout upload ──────────────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Layout</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload Layout JSON", type=["json"], label_visibility="collapsed")
    if uploaded is not None:
        try:
            loaded = _normalize_layout(json.loads(uploaded.getvalue().decode("utf-8")))
            _write_json(EDITED_LAYOUT_PATH, loaded)
            for k in ("eval_result", "eval_alts", "agent_log", "grid_options",
                      "selected_grid", "cost_flexibility", "last_comparison"):
                st.session_state[k] = [] if k in ("eval_alts", "agent_log", "grid_options") else None
            st.session_state.viewer_nonce += 1
            st.success(f"Loaded '{loaded.get('layoutId', 'unnamed')}'")
            st.rerun()
        except Exception as exc:
            st.error(f"Invalid JSON: {exc}")

    if st.button("Reset to default", use_container_width=True, key="btn_reset"):
        if DEFAULT_LAYOUT_PATH.exists():
            _write_json(EDITED_LAYOUT_PATH, _read_json(DEFAULT_LAYOUT_PATH))
        elif EDITED_LAYOUT_PATH.exists():
            EDITED_LAYOUT_PATH.unlink()
        st.session_state.viewer_nonce += 1
        for k in ("eval_result", "eval_alts", "agent_log", "state_history",
                  "grid_options", "selected_grid", "output_log",
                  "cost_flexibility", "last_comparison"):
            st.session_state[k] = [] if isinstance(st.session_state.get(k), list) else None
        st.rerun()

    # ── Material ───────────────────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Material</div>', unsafe_allow_html=True)
    _MAT_LABELS = {"RCC": "Concrete", "STEEL": "Steel", "TIMBER": "Timber"}
    mat_choice = st.radio(
        "material_selector",
        options=list(_MAT_LABELS.keys()),
        format_func=lambda k: _MAT_LABELS[k],
        index=list(_MAT_LABELS.keys()).index(st.session_state.material),
        horizontal=True,
        label_visibility="collapsed",
    )
    if mat_choice != st.session_state.material:
        st.session_state.material    = mat_choice
        st.session_state.grid_options = []
        st.rerun()

    # ── Loads ──────────────────────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Loads</div>', unsafe_allow_html=True)
    sdl_options = {1.5: "Timber 1.5", 2.5: "Light 2.5", 3.5: "Standard 3.5", 5.0: "Heavy 5.0"}
    sdl_val = st.select_slider(
        "SDL (kN/m²)",
        options=list(sdl_options.keys()),
        value=st.session_state.sdl_kNm2,
        format_func=lambda v: f"{sdl_options[v]} kN/m²",
    )
    if sdl_val != st.session_state.sdl_kNm2:
        st.session_state.sdl_kNm2 = sdl_val

    ll_options = {2.0: "Residential", 3.0: "Office", 5.0: "Retail/Public"}
    ll_val = st.select_slider(
        "LL (kN/m²)",
        options=list(ll_options.keys()),
        value=st.session_state.live_load_kNm2,
        format_func=lambda v: f"{ll_options[v]} {v} kN/m²",
    )
    if ll_val != st.session_state.live_load_kNm2:
        st.session_state.live_load_kNm2 = ll_val

    # ── Grid options ───────────────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Structural Grid</div>', unsafe_allow_html=True)

    _cg, _cr = st.columns(2)
    with _cg:
        gen_clicked = st.button("Generate", use_container_width=True, key="btn_gen")
    with _cr:
        rec_clicked = st.button("↺ Refresh", use_container_width=True, key="btn_rec")

    if gen_clicked or rec_clicked:
        with st.spinner("Computing grid options…"):
            st.session_state.grid_options = _run_grid_options(layout_obj, st.session_state.material)
        for _i, _opt in enumerate(st.session_state.grid_options, 1):
            _op = REPO_ROOT / f"team_01_option_{_i}.json"
            _op.write_text(json.dumps(_opt["layout"], indent=2, ensure_ascii=False), encoding="utf-8")
        st.rerun()

    for opt in st.session_state.grid_options:
        label    = opt["label"]
        spacing  = opt["spacing"]
        failures = opt.get("failures", 0)
        cost_opt = opt.get("cost", 0)
        is_active = st.session_state.selected_grid == label
        fail_cls  = "fail-ct" if failures > 0 else "pass-ct"
        card_cls  = "grid-card grid-card-active" if is_active else "grid-card"
        st.markdown(
            f'<div class="{card_cls}">'
            f'<span class="grid-label">{label}</span>'
            f'<span class="grid-spacing" style="margin-left:6px">{spacing}m</span>'
            f'<div class="grid-stats">'
            f'<span class="{fail_cls}">{failures} fail</span>'
            f' &bull; ${cost_opt:,.0f}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        if st.button(f"Apply {label}", key=f"grid_{label}", use_container_width=True):
            opt_layout = opt.get("layout", {})
            before_str = EDITED_LAYOUT_PATH.read_text(encoding="utf-8") if EDITED_LAYOUT_PATH.exists() else json.dumps(layout_obj)
            BEFORE_LAYOUT_PATH.write_text(before_str, encoding="utf-8")
            _write_json(EDITED_LAYOUT_PATH, opt_layout)
            st.session_state.selected_grid    = label
            st.session_state.viewer_nonce    += 1
            st.session_state.eval_result      = opt.get("evaluation")
            st.session_state.eval_alts        = _get_failure_alternatives(
                opt.get("evaluation") or {}, st.session_state.material
            )
            st.session_state.cost_flexibility = None
            st.session_state.last_comparison  = None
            st.rerun()

    # ── Modify / Delete ────────────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Modify Element</div>', unsafe_allow_html=True)

    structure = layout_obj.get("structure", [])
    all_ids   = [el["id"] for el in structure]
    col_ids   = [el["id"] for el in structure if len(el.get("geometry", [])) == 1]
    beam_ids  = [el["id"] for el in structure if len(el.get("geometry", [])) == 2]

    _sel_col, _del_col = st.columns([3, 1])
    with _sel_col:
        selected_el = st.selectbox(
            "Element",
            options=[""] + all_ids,
            index=([""] + all_ids).index(st.session_state.selected_el)
                  if st.session_state.selected_el in all_ids else 0,
            label_visibility="collapsed",
            key="el_selector",
        )
        st.session_state.selected_el = selected_el

    with _del_col:
        if st.button("Del", use_container_width=True,
                     disabled=not selected_el, key="btn_del",
                     help="Delete selected element"):
            from nodes.modify import remove_element
            before_str = json.dumps(layout_obj)
            new_str    = remove_element(before_str, selected_el)
            st.session_state.selected_el = ""
            _apply_structural_change(before_str, new_str, reset_grid=True)
            st.rerun()

    if selected_el:
        el_obj = next((e for e in structure if e["id"] == selected_el), None)
        if el_obj:
            from nodes.modify import (
                BEAM_SECTION_UPGRADE, BEAM_DIM_UPGRADE,
                COL_SECTION_UPGRADE, COL_DIM_UPGRADE,
            )
            is_beam = len(el_obj.get("geometry", [])) == 2
            attrs   = el_obj.get("attributes", {})
            cur_sec = (
                attrs.get("section")
                or (f"{attrs.get('width','')}x{attrs.get('depth','')}" if is_beam
                    else attrs.get("dimensions", ""))
                or ""
            )
            upgrade_options = {}
            if is_beam:
                if cur_sec in BEAM_SECTION_UPGRADE:
                    nxt, _, _ = BEAM_SECTION_UPGRADE[cur_sec]
                    upgrade_options[f"→ {nxt}"] = nxt
                if cur_sec in BEAM_DIM_UPGRADE:
                    nxt, _, _ = BEAM_DIM_UPGRADE[cur_sec]
                    upgrade_options[f"→ {nxt}"] = nxt
            else:
                if cur_sec in COL_SECTION_UPGRADE:
                    nxt, _ = COL_SECTION_UPGRADE[cur_sec]
                    upgrade_options[f"→ {nxt}"] = nxt
                if cur_sec in COL_DIM_UPGRADE:
                    nxt = COL_DIM_UPGRADE[cur_sec]
                    upgrade_options[f"→ {nxt}"] = nxt

            if upgrade_options:
                _up_a, _up_b = st.columns([3, 1])
                with _up_a:
                    up_label = st.selectbox(
                        "Upgrade",
                        options=["—"] + list(upgrade_options.keys()),
                        label_visibility="collapsed",
                        key="upgrade_sel",
                    )
                with _up_b:
                    if st.button("Up", use_container_width=True,
                                 disabled=(up_label == "—"), key="btn_upgrade",
                                 help="Apply section upgrade"):
                        from nodes.modify import upgrade_element_section
                        before_str = json.dumps(layout_obj)
                        new_str    = upgrade_element_section(
                            before_str, selected_el, upgrade_options[up_label]
                        )
                        _apply_structural_change(before_str, new_str)
                        st.rerun()

            if is_beam:
                if st.button("Add midspan column", key="btn_midspan", use_container_width=True):
                    from nodes.modify import add_midspan_column
                    before_str = json.dumps(layout_obj)
                    new_str    = add_midspan_column(before_str, selected_el, st.session_state.material)
                    _apply_structural_change(before_str, new_str, reset_grid=True)
                    st.rerun()

    # ── Add Beam ───────────────────────────────────────────────────────────────
    with st.expander("➕ Add Beam", expanded=False):
        if len(col_ids) < 2:
            st.caption("Need ≥ 2 columns.")
        else:
            _ab1, _ab2 = st.columns(2)
            with _ab1:
                beam_col_a = st.selectbox("From", col_ids, key="beam_col_a")
            with _ab2:
                _b_opts = [c for c in col_ids if c != beam_col_a]
                beam_col_b = st.selectbox("To", _b_opts, key="beam_col_b")
            if st.button("Add Beam", use_container_width=True, key="btn_add_beam",
                         disabled=not beam_col_a or not beam_col_b):
                from nodes.modify import add_beam
                before_str = json.dumps(layout_obj)
                new_str    = add_beam(before_str, beam_col_a, beam_col_b, st.session_state.material)
                if new_str == before_str:
                    st.warning("Beam already exists between those columns.")
                else:
                    _apply_structural_change(before_str, new_str, reset_grid=True)
                    st.rerun()

    # ── Add Column ─────────────────────────────────────────────────────────────
    with st.expander("➕ Add Column", expanded=False):
        _outline = layout_obj.get("outline", [])
        _xs = [p[0] for p in _outline if len(p) >= 2] or [0.0]
        _ys = [p[1] for p in _outline if len(p) >= 2] or [0.0]
        _cx = round((min(_xs) + max(_xs)) / 2, 1)
        _cy = round((min(_ys) + max(_ys)) / 2, 1)
        _ac1, _ac2 = st.columns(2)
        with _ac1:
            col_x = st.number_input("X (m)", value=_cx, step=0.5, format="%.2f", key="add_col_x")
        with _ac2:
            col_y = st.number_input("Y (m)", value=_cy, step=0.5, format="%.2f", key="add_col_y")
        st.caption(f"X {round(min(_xs),1)}–{round(max(_xs),1)}  ·  Y {round(min(_ys),1)}–{round(max(_ys),1)} m")
        if st.button("Add Column", use_container_width=True, key="btn_add_col"):
            from nodes.modify import add_column
            before_str = json.dumps(layout_obj)
            new_str    = add_column(before_str, col_x, col_y, st.session_state.material)
            if new_str == before_str:
                st.warning("Column already exists at that position.")
            else:
                _apply_structural_change(before_str, new_str, reset_grid=True)
                st.rerun()

    # ── JSON preview ───────────────────────────────────────────────────────────
    with st.expander("JSON Preview", expanded=False):
        s = json.dumps(layout_obj, indent=2, ensure_ascii=False)
        st.code(s[:2000] + ("\n…" if len(s) > 2000 else ""), language="json")


# ══════════════════════════════════════════════════════════════════════════════
# CENTER — Large 2D Floor Plan (dominant view)
# ══════════════════════════════════════════════════════════════════════════════

with col_plan:

    # JS bridge for element selection from viewer
    components.html("""
<script>
  (function() {
    if (window._selBridgeReady) return;
    window._selBridgeReady = true;
    window.parent.addEventListener('message', function(ev) {
      if (!ev.data || ev.data.type !== 'selectElement' || !ev.data.elementId) return;
      var eid = ev.data.elementId;
      var url = new URL(window.parent.location.href);
      url.searchParams.set('_sel', eid);
      window.parent.history.replaceState(null, '', url.toString());
      window.parent.dispatchEvent(new PopStateEvent('popstate', {state: null}));
    });
  })();
</script>""", height=1)

    # ── Snapshot bar ──────────────────────────────────────────────────────────
    _snaps   = st.session_state.get("snapshots", [])
    _sp_l, _sp_m, _sp_r = st.columns([4, 1, 1])
    with _sp_l:
        if _snaps:
            pills_html = " ".join(
                f'<span class="snap-pill{" snap-pill-active" if i == len(_snaps)-1 else ""}">'
                f'{s["label"]}</span>'
                for i, s in enumerate(_snaps)
            )
            st.markdown(pills_html, unsafe_allow_html=True)
        else:
            st.caption("Make changes and save as named snapshots to compare.")
    with _sp_m:
        _snap_n = len(_snaps) + 1
        if st.button(f"Save #{_snap_n}", key="btn_snap", use_container_width=True,
                     help="Save current layout as a snapshot"):
            st.session_state.snapshots.append({
                "label":            f"Change {_snap_n}",
                "layout_json":      json.dumps(layout_obj),
                "eval_result":      st.session_state.eval_result,
                "cost_flexibility": st.session_state.cost_flexibility,
                "before_json":      (BEFORE_LAYOUT_PATH.read_text(encoding="utf-8")
                                     if BEFORE_LAYOUT_PATH.exists() else json.dumps(layout_obj)),
            })
            st.rerun()
    with _sp_r:
        _auto_eval = st.checkbox(
            "Auto-eval",
            value=st.session_state.get("auto_eval", True),
            key="chk_auto_eval",
            help="Automatically evaluate and analyse after each structural change",
        )
        if _auto_eval != st.session_state.get("auto_eval", True):
            st.session_state.auto_eval = _auto_eval

    # ── Viewer toolbar ─────────────────────────────────────────────────────────
    _tv_l, _tv_m, _tv_r = st.columns([1, 3, 1])
    with _tv_l:
        _labels_on = st.toggle(
            "Labels",
            value=st.session_state.labels_on,
            key="labels_toggle",
            help="Show/hide element ID labels",
        )
        if _labels_on != st.session_state.labels_on:
            st.session_state.labels_on = _labels_on
            st.session_state.viewer_nonce += 1
            st.rerun()
    with _tv_r:
        _compare_on = st.toggle(
            "Compare",
            value=st.session_state.compare_mode,
            key="compare_toggle",
            help="Overlay before/after in 3D view",
            disabled=not BEFORE_LAYOUT_PATH.exists(),
        )
        if _compare_on != st.session_state.compare_mode:
            st.session_state.compare_mode = _compare_on
            st.session_state.viewer_nonce += 1
            st.rerun()

    _preview_opt_file = ""
    if st.session_state.grid_options:
        with _tv_m:
            _opt_names = ["Working layout"] + [
                f"{o['label']} ({o.get('failures',0)} fail · ${o.get('cost',0):,.0f})"
                for o in st.session_state.grid_options
            ]
            _prev_sel = st.radio(
                "Preview",
                _opt_names,
                horizontal=True,
                label_visibility="collapsed",
                key="preview_radio",
            )
            if _prev_sel != "Working layout":
                _prev_idx = _opt_names.index(_prev_sel) - 1
                _preview_opt_file = f"team_01_option_{_prev_idx + 1}.json"

    # ── 2D Structural Plan (hero view — native SVG, no server required) ─────────
    st.markdown('<div class="viewer-label">2D Structural Plan</div>', unsafe_allow_html=True)
    _plan_layout = layout_obj
    if _preview_opt_file:
        _opt_path = REPO_ROOT / _preview_opt_file
        if _opt_path.exists():
            try:
                _plan_layout = _normalize_layout(json.loads(_opt_path.read_text(encoding="utf-8")))
            except Exception:
                pass
    components.html(
        _render_floor_plan_svg(
            _plan_layout,
            eval_result=st.session_state.eval_result,
            selected_el=st.session_state.selected_el,
            is_dark=not _is_light,
            height=540,
        ),
        height=560,
        scrolling=False,
    )

    # ── 3D View (collapsible) ──────────────────────────────────────────────────
    with st.expander("3D Structural View", expanded=False):
        if _viewer_is_reachable():
            components.iframe(
                _viewer_url(
                    highlight=st.session_state.selected_el,
                    compare=st.session_state.compare_mode,
                    labels=st.session_state.labels_on,
                    option_file=_preview_opt_file,
                ),
                height=360, scrolling=False,
            )
        else:
            st.caption("Viewer server not running.")


# ══════════════════════════════════════════════════════════════════════════════
# RIGHT — Agent + Evaluation + Cost & Comparison
# ══════════════════════════════════════════════════════════════════════════════

with col_analysis:

    # ── Agent chat ─────────────────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Ask Structural Agent</div>', unsafe_allow_html=True)

    with st.form("agent_form", clear_on_submit=True):
        prompt_input = st.text_area(
            "prompt",
            placeholder="e.g. Why is beam A1-B1 failing? Generate structural grid.",
            label_visibility="collapsed",
            height=68,
        )
        submitted = st.form_submit_button("Ask Agent", use_container_width=True)

    if submitted and prompt_input.strip():
        with st.spinner("Agent reasoning…"):
            response = _run_agent_chat(
                prompt_input.strip(), layout_obj, st.session_state.eval_result,
            )

        if response == "GENERATE_GRID":
            with st.spinner("Generating structural grid options…"):
                st.session_state.grid_options = _run_grid_options(layout_obj, st.session_state.material)
            for _i, _opt in enumerate(st.session_state.grid_options, 1):
                _op = REPO_ROOT / f"team_01_option_{_i}.json"
                _op.write_text(json.dumps(_opt["layout"], indent=2, ensure_ascii=False), encoding="utf-8")
            response = (
                f"Generated {len(st.session_state.grid_options)} structural grid option(s). "
                "Review the Grid Options in the left panel."
            )
        elif response == "EVALUATE":
            from nodes.modify import apply_material_override
            _mat_now = st.session_state.get("material", "RCC")
            _sdl_now = st.session_state.get("sdl_kNm2", 3.5)
            _ll_now  = st.session_state.get("live_load_kNm2", 2.0)
            _ls      = apply_material_override(json.dumps(layout_obj), _mat_now)
            BEFORE_LAYOUT_PATH.write_text(json.dumps(layout_obj), encoding="utf-8")
            _write_json(EDITED_LAYOUT_PATH, json.loads(_ls))
            st.session_state.viewer_nonce += 1
            with st.spinner("Evaluating structure…"):
                _ev = _run_evaluate(_ls, sdl=_sdl_now, ll=_ll_now)
            if _ev:
                st.session_state.eval_result = _ev
                st.session_state.eval_alts   = _get_failure_alternatives(_ev, _mat_now)
            _s = (_ev or {}).get("summary", {})
            response = (
                f"Evaluation: **{'PASS' if _s.get('overall_PASS') else 'FAIL'}** — "
                f"{_s.get('beam_failures', 0)} beam failure(s), "
                f"{_s.get('column_failures', 0)} column failure(s)."
            )

        st.session_state.output_log.append(response)
        st.session_state.history.append({"prompt": prompt_input, "response": response})
        label = prompt_input[:28] + ("…" if len(prompt_input) > 28 else "")
        st.session_state.state_history.append({
            "label":       label,
            "layout_json": _load_working_layout(),
            "eval_result": st.session_state.eval_result,
        })
        st.rerun()

    if st.session_state.output_log:
        last = st.session_state.output_log[-1]
        preview = last[:380] + ("…" if len(last) > 380 else "")
        st.markdown(
            f'<div class="agent-response">{preview}</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Structural Evaluation ──────────────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Structural Evaluation</div>', unsafe_allow_html=True)

    _mat_now = st.session_state.material
    _sdl_now = st.session_state.sdl_kNm2
    _ll_now  = st.session_state.live_load_kNm2

    if st.button("▶  Run Evaluation", use_container_width=True, key="btn_eval"):
        from nodes.modify import apply_material_override
        layout_str     = json.dumps(layout_obj)
        layout_str_mat = apply_material_override(layout_str, _mat_now)
        applied_layout = json.loads(layout_str_mat)
        BEFORE_LAYOUT_PATH.write_text(layout_str, encoding="utf-8")
        _write_json(EDITED_LAYOUT_PATH, applied_layout)
        st.session_state.viewer_nonce += 1
        with st.spinner("Evaluating structure…"):
            ev = _run_evaluate(layout_str_mat, sdl=_sdl_now, ll=_ll_now)
        if ev:
            st.session_state.eval_result = ev
            st.session_state.eval_alts   = _get_failure_alternatives(ev, _mat_now)
        st.rerun()

    er = st.session_state.eval_result
    if er is None:
        st.caption("Press Run Evaluation or apply a grid option.")
    else:
        summary = er.get("summary", {})
        bf      = summary.get("beam_failures", 0)
        cf_cnt  = summary.get("column_failures", 0)
        overall = summary.get("overall_PASS", False)

        # Status row
        _es1, _es2, _es3, _es4 = st.columns(4)
        with _es1:
            cls = "eval-pass" if overall else "eval-fail"
            txt = "PASS" if overall else "FAIL"
            st.markdown(
                f'<div class="{cls}" style="font-size:1.5rem;font-weight:800">{txt}</div>'
                f'<div class="eval-label">Overall</div>',
                unsafe_allow_html=True,
            )
        with _es2:
            total_el = max(len(er.get("beams", [])) + len(er.get("columns", [])), 1)
            score    = round(100 * (1 - (bf + cf_cnt) / total_el), 1)
            s_cls    = "eval-pass" if score >= 90 else ("eval-fail" if score < 70 else "")
            st.markdown(
                f'<div class="{s_cls}" style="font-size:1.5rem;font-weight:800">{score}</div>'
                f'<div class="eval-label">Score</div>',
                unsafe_allow_html=True,
            )
        with _es3:
            bf_cls = "eval-fail" if bf > 0 else "eval-pass"
            st.markdown(
                f'<div class="{bf_cls}" style="font-size:1.5rem;font-weight:800">{bf}</div>'
                f'<div class="eval-label">Beam fail</div>',
                unsafe_allow_html=True,
            )
        with _es4:
            cf_cls = "eval-fail" if cf_cnt > 0 else "eval-pass"
            st.markdown(
                f'<div class="{cf_cls}" style="font-size:1.5rem;font-weight:800">{cf_cnt}</div>'
                f'<div class="eval-label">Col fail</div>',
                unsafe_allow_html=True,
            )

        beams_ev = er.get("beams", [])
        if beams_ev:
            max_span = max((b.get("span_m", 0) for b in beams_ev), default=0)
            st.caption(f"Max beam span: **{max_span:.2f} m**")

        # Critical items
        failing_beams = [b for b in beams_ev
                         if not b.get("bend_PASS") or not b.get("shear_PASS")
                         or not b.get("defl_TL_PASS") or not b.get("defl_LL_PASS")]
        failing_cols  = [c for c in er.get("columns", [])
                         if not c.get("stress_PASS") or not c.get("buckling_PASS")]

        if not failing_beams and not failing_cols:
            st.markdown('<span class="pass-badge">All checks passed ✓</span>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="panel-hdr" style="margin-top:6px">Critical checks</div>',
                        unsafe_allow_html=True)
            for b in failing_beams[:5]:
                chks = []
                if not b.get("bend_PASS"):    chks.append("bending")
                if not b.get("shear_PASS"):   chks.append("shear")
                if not b.get("defl_TL_PASS") or not b.get("defl_LL_PASS"):
                    chks.append("deflection")
                st.markdown(
                    f'<div class="crit-item">'
                    f'<b>{b["id"]}</b> {b.get("span_m", 0):.2f}m · {b.get("section_mm","?")}'
                    f'<br/>Fails: {", ".join(chks)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            for c in failing_cols[:4]:
                chks = []
                if not c.get("stress_PASS"):   chks.append("stress")
                if not c.get("buckling_PASS"): chks.append("buckling")
                st.markdown(
                    f'<div class="crit-item">'
                    f'<b>{c["id"]}</b> {c.get("section_mm","?")} · SF={c.get("SF_buckling","?")}'
                    f'<br/>Fails: {", ".join(chks)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Suggested fixes
        alts = st.session_state.eval_alts
        if alts:
            st.markdown('<div class="panel-hdr" style="margin-top:6px">Suggested fixes</div>',
                        unsafe_allow_html=True)
            for i, alt in enumerate(alts):
                if st.button(alt, key=f"alt_{i}", use_container_width=True):
                    before_str = json.dumps(layout_obj)
                    BEFORE_LAYOUT_PATH.write_text(before_str, encoding="utf-8")
                    with st.spinner(f"Applying: {alt[:40]}…"):
                        new_str, new_ev = _apply_alternative(alt, before_str, _mat_now, _sdl_now, _ll_now)
                    if new_str != before_str:
                        new_layout = json.loads(new_str)
                        _write_json(EDITED_LAYOUT_PATH, new_layout)
                        st.session_state.viewer_nonce    += 1
                        st.session_state.cost_flexibility = None
                        _lbl = alt[:30] + ("…" if len(alt) > 30 else "")
                        st.session_state.state_history.append({
                            "label":       _lbl,
                            "layout_json": new_layout,
                            "eval_result": new_ev,
                        })
                        with st.spinner("Summarising cost & changes…"):
                            _cf_res  = _run_cost_flex(before_str, new_str)
                            _cmp_txt = _run_comparison(before_str, new_str)
                        if _cf_res:
                            st.session_state.cost_flexibility = _cf_res
                        if _cmp_txt:
                            st.session_state.output_log.append(_cmp_txt)
                            st.session_state.last_comparison = _cmp_txt
                    if new_ev is not None:
                        st.session_state.eval_result = new_ev
                        st.session_state.eval_alts   = _get_failure_alternatives(new_ev, _mat_now)
                    st.rerun()

    st.divider()

    # ── Cost & Change Summary (merged) ─────────────────────────────────────────
    st.markdown('<div class="panel-hdr">Cost & Change Summary</div>', unsafe_allow_html=True)

    _cf = st.session_state.get("cost_flexibility")
    _last_cmp = st.session_state.get("last_comparison")

    if _cf is None and er is not None:
        # Offer to run if evaluation exists but no cost analysis yet
        if st.button("Run cost & flexibility analysis", use_container_width=True, key="btn_cf"):
            before_str = (
                BEFORE_LAYOUT_PATH.read_text(encoding="utf-8")
                if BEFORE_LAYOUT_PATH.exists()
                else json.dumps(layout_obj)
            )
            with st.spinner("Analysing cost and flexibility…"):
                cf_res = _run_cost_flex(before_str, json.dumps(layout_obj))
            if cf_res:
                st.session_state.cost_flexibility = cf_res
            st.rerun()
    elif _cf is None:
        st.caption("Run evaluation first, then analyse cost & flexibility.")
    else:
        net     = _cf.get("net_cost_usd", 0)
        ca      = _cf.get("cost_added_usd", 0)
        cs      = _cf.get("cost_saved_usd", 0)
        flex    = _cf.get("flexibility_score", 0)
        fl_lbl  = _cf.get("flexibility_label", "")
        disrupt = _cf.get("disruption_score", 0)
        dl_lbl  = _cf.get("disruption_label", "")
        penalty = _cf.get("spatial_penalty", 0.0)

        _cm1, _cm2 = st.columns(2)
        _cm1.metric("Net Cost Change", f"${net:+,.0f}")
        _cm2.metric("Flexibility", f"{flex:.1f}/10")
        _cm3, _cm4 = st.columns(2)
        _cm3.metric("Disruption", f"{disrupt}/10")
        if ca or cs:
            _cm4.metric("Material added", f"+${ca:,.0f}" if ca else f"-${abs(cs):,.0f}")
        if penalty > 0:
            st.caption(f"Spatial penalty: {penalty:.2f} (mid-room column intrusion)")
        if _cf.get("summary"):
            st.caption(_cf["summary"])

        if _last_cmp:
            st.markdown(
                f'<div class="agent-response" style="margin-top:8px">{_last_cmp[:500]}'
                f'{"…" if len(_last_cmp) > 500 else ""}</div>',
                unsafe_allow_html=True,
            )

    # Per-snapshot cost table (if snapshots saved)
    _snaps_cost = st.session_state.get("snapshots", [])
    if _snaps_cost:
        with st.expander(f"Cost by Change ({len(_snaps_cost)} snapshots)", expanded=False):
            for _sn in _snaps_cost:
                _scf  = _sn.get("cost_flexibility")
                _sev  = (_sn.get("eval_result") or {}).get("summary", {})
                _fail = _sev.get("beam_failures", 0) + _sev.get("column_failures", 0)
                with st.expander(
                    f"{_sn['label']}  ·  {'✓' if _fail == 0 else f'✗ {_fail} fail'}",
                    expanded=False,
                ):
                    if _scf:
                        _sc1, _sc2, _sc3 = st.columns(3)
                        _sc1.metric("Net cost",    f"${_scf.get('net_cost_usd', 0):+,.0f}")
                        _sc2.metric("Flexibility", f"{_scf.get('flexibility_score', 0):.1f}/10")
                        _sc3.metric("Disruption",  f"{_scf.get('disruption_score', 0)}/10")
                        if _scf.get("summary"):
                            st.caption(_scf["summary"])
                    else:
                        st.caption("No cost data. Save again after running analysis.")

            # Snapshot comparison diff
            st.markdown("---")
            _cmp_labels = [s["label"] for s in _snaps_cost] + ["Current"]
            _cf_l, _cf_r = st.columns(2)
            with _cf_l:
                _sel_from = st.selectbox("From", _cmp_labels, index=0, key="cmp_from")
            with _cf_r:
                _sel_to   = st.selectbox("To",   _cmp_labels,
                                         index=len(_cmp_labels)-1, key="cmp_to")
            if _sel_from != _sel_to:
                def _snap_layout(label: str) -> dict:
                    if label == "Current":
                        return layout_obj
                    return json.loads(next(s["layout_json"] for s in _snaps_cost if s["label"] == label))

                _bl = _snap_layout(_sel_from)
                _al = _snap_layout(_sel_to)
                _bm = {el["id"]: el for el in _bl.get("structure", [])}
                _am = {el["id"]: el for el in _al.get("structure", [])}
                _added   = [k for k in _am if k not in _bm]
                _removed = [k for k in _bm if k not in _am]
                _changed = [k for k in _bm if k in _am
                            and _bm[k].get("attributes") != _am[k].get("attributes")]
                _cd1, _cd2, _cd3 = st.columns(3)
                _cd1.metric("Added",   f"+{len(_added)}")
                _cd2.metric("Removed", f"-{len(_removed)}")
                _cd3.metric("Changed", str(len(_changed)))

                _cost_a = sum(_element_cost(_am[k]) for k in _added   if k in _am)
                _cost_r = sum(_element_cost(_bm[k]) for k in _removed if k in _bm)
                _cost_n = _cost_a - _cost_r
                if _added or _removed:
                    _ce1, _ce2, _ce3 = st.columns(3)
                    _ce1.metric("Added",   f"+${_cost_a:,.0f}")
                    _ce2.metric("Saved",   f"-${_cost_r:,.0f}")
                    _ce3.metric("Net",     f"${_cost_n:+,.0f}")

    st.divider()

    # ── History & Output (collapsed) ───────────────────────────────────────────
    with st.expander("State History", expanded=False):
        if not st.session_state.state_history:
            st.caption("No states recorded.")
        else:
            for i, snap in enumerate(reversed(st.session_state.state_history[-10:])):
                real_i = len(st.session_state.state_history) - 1 - i
                is_last = real_i == len(st.session_state.state_history) - 1
                pill_cls = "state-pill" + (" snap-pill-active" if is_last else "")
                st.markdown(
                    f'<span class="{pill_cls}">{real_i + 1}. {snap["label"]}</span>',
                    unsafe_allow_html=True,
                )
                if st.button(f"Restore #{real_i + 1}", key=f"restore_{real_i}"):
                    _write_json(EDITED_LAYOUT_PATH, snap["layout_json"])
                    st.session_state.viewer_nonce  += 1
                    st.session_state.eval_result    = snap.get("eval_result")
                    st.session_state.eval_alts      = _get_failure_alternatives(
                        snap.get("eval_result") or {}, st.session_state.material
                    )
                    st.session_state.grid_options   = []
                    st.rerun()

    with st.expander("Agent Output Log", expanded=False):
        if st.session_state.output_log:
            for i, msg in enumerate(reversed(st.session_state.output_log[-10:])):
                n = len(st.session_state.output_log) - i
                st.markdown(
                    f'<div class="log-entry"><b>{n}.</b> {msg[:300]}{"…" if len(msg) > 300 else ""}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Agent responses and change summaries appear here.")
