from __future__ import annotations

import base64
import json
import re
import sys
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT           = Path(__file__).resolve().parents[2]
DEFAULT_LAYOUT_PATH = REPO_ROOT / "layout_input" / "layout_schema.json"
EDITED_LAYOUT_PATH  = REPO_ROOT / "team_01_edited_layout.json"
BEFORE_LAYOUT_PATH  = REPO_ROOT / "team_01_edited_layout_before.json"
USER_DATA_DIR       = REPO_ROOT / "user_data"   # per-user saved work (keyed by email)
VIEWER_BASE_URL     = "http://127.0.0.1:8000/layout_viewer.html"
PLAN_VIEWER_URL     = "http://127.0.0.1:8000/plan_viewer.html"
PYTHON_DIR           = Path(__file__).resolve().parent
LOGO_PATH_LIGHT      = PYTHON_DIR / "Assets" / "Logo.png"
LOGO_PATH_DARK       = PYTHON_DIR / "Assets" / "Logo_dark.png"

def _load_logo(path: Path) -> str:
    try:
        return base64.b64encode(path.read_bytes()).decode() if path.exists() else ""
    except Exception:
        return ""

_logo_b64_light = _load_logo(LOGO_PATH_LIGHT)
_logo_b64_dark  = _load_logo(LOGO_PATH_DARK)

st.set_page_config(
    page_title="PermanenceOS",
    layout="wide",
    initial_sidebar_state="expanded",
)

if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from nodes._layout import (
    find_element_in_layout,
    get_all_rooms,
    get_level_count,
    get_level_keys,
    get_outline,
    get_rooms,
    get_structure,
    is_multilevel,
    iter_all_structure,
)
from viz import (
    _render_floor_plan_plotly, _render_3d_viewport, _count_elements, _present_legend_items,
    _materials_present, _material_legend_html, _structural_summary_text,
    _sheet_pdf_bytes, _beam_diagram_png, _normalize_layout, _strip_structure,
    _flexibility_rows, _flex_advice, _opening_clashes, _compute_diff,
)
from ui.theme import theme_tokens, build_css
from ui.bridge import SELECTION_BRIDGE_JS, agent_drawer_html
from ui.state import AppState
from ui.header import render_header
from ui.sidebar import render_sidebar

# No default layout — app starts empty until the user uploads a file.


# ── JSON helpers ───────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _push_version(new_layout: dict) -> None:
    """Commit a structural change:
    - push currentLayout onto versionHistory
    - make new_layout the new currentLayout
    - persist to disk (for 3D viewer HTTP access)
    - write a numbered version file
    - clear selected_opt_bar_idx so 2D plan always reads currentLayout
    """
    prev = st.session_state.get("currentLayout") or {}
    if prev:
        hist = st.session_state.get("versionHistory", [])
        hist.append(prev)
        st.session_state.versionHistory = hist

    v = st.session_state.get("currentVersion", 0) + 1
    st.session_state.currentVersion = v
    st.session_state.currentLayout  = new_layout
    st.session_state["selected_opt_bar_idx"] = -1

    # After ANY layout change, reset the selection AND its URL bridge to a clean slate so
    # the next click always registers — nothing stays "stuck" (e.g. an add-column
    # reference). Re-click the element to see its updated details.
    st.session_state.selected_el = ""
    st.session_state.active_element_level = ""
    try:
        if "_sel" in st.query_params:
            del st.query_params["_sel"]
        if "_lvl" in st.query_params:
            del st.query_params["_lvl"]
    except Exception:
        pass
    st.session_state["_last_url_sel"] = ""
    st.session_state["_last_url_lvl"] = ""

    # Single working file only — version history lives in session_state.versionHistory
    # (we no longer litter the repo with one layout_v{n}.json per change).
    _write_json(EDITED_LAYOUT_PATH, new_layout)
    _save_user_store()   # persist this change to the user's saved work
    _sync_viewers()


def _sync_viewers() -> None:
    """Signal both viewers to re-read currentLayout on the next rerun."""
    st.session_state.viewer_nonce = st.session_state.get("viewer_nonce", 0) + 1








def _load_working_layout() -> dict:
    """Load the persisted working layout from disk. Returns {} if no file exists."""
    if EDITED_LAYOUT_PATH.exists():
        return _normalize_layout(_read_json(EDITED_LAYOUT_PATH))
    return {}


# ── Per-user saved work (keyed by email) ───────────────────────────────────────

def _user_store_path():
    """Path to the logged-in user's saved-work bundle, or None if not logged in."""
    import hashlib
    em = (st.session_state.get("user_email") or "").strip().lower()
    if not em:
        return None
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DATA_DIR / (hashlib.md5(em.encode()).hexdigest()[:12] + ".json")


def _save_user_store() -> None:
    """Persist the current user's layout + snapshots + settings so it's there next login."""
    p = _user_store_path()
    if not p:
        return
    try:
        p.write_text(json.dumps({
            "name":           st.session_state.get("user_name", ""),
            "email":          st.session_state.get("user_email", ""),
            "currentLayout":  st.session_state.get("currentLayout"),
            "currentVersion": st.session_state.get("currentVersion", 0),
            "versionHistory": st.session_state.get("versionHistory", []),
            "snapshots":      st.session_state.get("snapshots", []),
            "material":       st.session_state.get("material"),
            "sdl_kNm2":       st.session_state.get("sdl_kNm2"),
            "live_load_kNm2": st.session_state.get("live_load_kNm2"),
            "setupDone":      st.session_state.get("setupDone", False),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as _e:
        st.session_state["_last_error"] = f"save user store: {_e}"


def _load_user_store() -> None:
    """Restore a user's saved work into session_state on login (if any exists)."""
    p = _user_store_path()
    if not p or not p.exists():
        return
    try:
        b = json.loads(p.read_text(encoding="utf-8"))
        for _k in ("currentLayout", "currentVersion", "versionHistory", "snapshots",
                   "material", "sdl_kNm2", "live_load_kNm2", "setupDone"):
            if b.get(_k) is not None:
                st.session_state[_k] = b[_k]
    except Exception as _e:
        st.session_state["_last_error"] = f"load user store: {_e}"


def _clear_user_store() -> None:
    """Delete the current user's saved work + reset the workspace (keeps them signed in)."""
    p = _user_store_path()
    try:
        if p and p.exists():
            p.unlink()
    except Exception:
        pass
    try:
        if EDITED_LAYOUT_PATH.exists():
            EDITED_LAYOUT_PATH.unlink()
    except Exception:
        pass
    for _k, _v in {
        "currentLayout": None, "versionHistory": [], "currentVersion": 0,
        "setupDone": False, "eval_result": None, "eval_alts": [], "grid_options": [],
        "selected_grid": None, "snapshots": [], "cmp_sel_indices": [], "history": [],
        "selected_el": "", "active_element_level": "", "selected_opt_bar_idx": -1,
        "diff_baseline": None, "cost_flexibility": None,
    }.items():
        st.session_state[_k] = _v


@st.cache_data(ttl=5)




















def _grid_option_kpis(layout_dict: dict) -> dict:
    """Compute KPIs for a generated grid option to show in the option card."""
    import math as _m
    structure = get_structure(layout_dict)
    cols  = [el for el in structure if len(el.get("geometry", [])) == 1]
    beams = [el for el in structure if len(el.get("geometry", [])) == 2]
    spans = []
    for bm in beams:
        g = bm.get("geometry", [])
        if len(g) == 2:
            spans.append(round(_m.dist(g[0], g[1]), 2))
    perimeter_cols = sum(1 for c in cols if (c.get("attributes") or {}).get("type") == "perimeter")
    internal_cols  = len(cols) - perimeter_cols
    max_span       = max(spans) if spans else 0.0
    avg_span       = round(sum(spans) / len(spans), 2) if spans else 0.0
    mat_set = {(el.get("attributes") or {}).get("material") for el in structure}
    mat_set.discard(None)
    mat_str = ", ".join(sorted(mat_set)) if mat_set else "—"
    return {
        "n_cols": len(cols), "n_beams": len(beams),
        "perimeter_cols": perimeter_cols, "internal_cols": internal_cols,
        "max_span": max_span, "avg_span": avg_span,
        "n_spans": len(spans), "material": mat_str,
    }


def _grid_option_description(idx: int, kpis: dict) -> str:
    """Return a 1-sentence description of a structural grid option based on its KPIs."""
    if kpis["n_cols"] == 0:
        return "No structural elements placed."
    ratio = kpis["n_beams"] / max(kpis["n_cols"], 1)
    if kpis["max_span"] > 6.0:
        style = "long-span open grid"
    elif kpis["internal_cols"] == 0:
        style = "perimeter-only frame"
    elif ratio > 3:
        style = "dense beam network"
    else:
        style = "regular structural grid"
    return (
        f"Option {idx+1}: {style} — {kpis['n_cols']} col / {kpis['n_beams']} beam, "
        f"max span {kpis['max_span']}m (avg {kpis['avg_span']}m)."
    )







# ── Material colour mapping (shared by 2D, 3D and the legend) ───────────────────
# Mid-tones chosen to read on both the light (#f0f8f8) and dark (#0c2020) canvases.


















def _el_detail_html(el_obj: dict, eval_result: dict | None,
                    level: str | None = None, fallback_mat: str = "RCC") -> str:
    """SENSI-style element detail card with utilization bars.

    `level` disambiguates eval entries (ids repeat across floors). `fallback_mat` is
    shown when the element has no per-element material yet (e.g. material set globally)."""
    import math as _math
    eid     = el_obj.get("id", "")
    attrs   = el_obj.get("attributes", {})
    is_beam = len(el_obj.get("geometry", [])) == 2
    el_type = "BEAM" if is_beam else "COL"
    mat     = attrs.get("material") or fallback_mat
    sec     = (attrs.get("section") or attrs.get("dimensions", "")
               or (f"{attrs.get('width','')}x{attrs.get('depth','')}" if is_beam else ""))
    span_txt = ""
    geo = el_obj.get("geometry", [])
    if is_beam and len(geo) == 2:
        span_txt = f" · {_math.dist(geo[0], geo[1]):.1f} m"

    def _bar(val, allow, passed, label, unit="MPa"):
        ratio = min(val / max(allow, 0.001), 1.0)
        pct   = f"{ratio * 100:.0f}%"
        fc    = "#40d090" if passed else "#ff5050"
        tick  = "✓" if passed else "✗"
        return (
            f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:5px">'
            f'<span style="color:#6ab8b8;width:72px;flex-shrink:0;font-size:.65rem;'
            f'letter-spacing:.5px;text-transform:uppercase">{label}</span>'
            f'<div style="flex:1;height:3px;background:#0d3030;border-radius:2px;overflow:hidden">'
            f'<div style="width:{pct};height:100%;background:{fc};border-radius:2px"></div></div>'
            f'<span style="color:#8ab8b8;width:52px;text-align:right;font-size:.69rem">'
            f'{val:.2f}{unit}</span>'
            f'<span style="color:{fc};font-size:.72rem;font-weight:700;width:12px;text-align:right">{tick}</span>'
            f'</div>'
        )

    overall_pass = None
    checks_html  = ""
    extra_info   = ""

    if is_beam and eval_result:
        for b in eval_result.get("beams", []):
            if b.get("id") != eid or (level and b.get("level") and b.get("level") != level):
                continue
            overall_pass = (b.get("bend_PASS") and b.get("shear_PASS")
                            and b.get("defl_TL_PASS") and b.get("defl_LL_PASS"))
            checks_html = (
                _bar(b.get("sigma_bend_MPa", 0), b.get("allow_bend_MPa", 1),
                     b.get("bend_PASS", False), "Bending")
                + _bar(b.get("tau_MPa", 0), b.get("allow_shear_MPa", 1),
                       b.get("shear_PASS", False), "Shear")
                + _bar(b.get("delta_total_mm", 0), b.get("limit_TL_mm", 1),
                       b.get("defl_TL_PASS", False), "Defl TL", "mm")
                + _bar(b.get("delta_LL_mm", 0), b.get("limit_LL_mm", 1),
                       b.get("defl_LL_PASS", False), "Defl LL", "mm")
            )
            extra_info = (f'<div style="font-size:.67rem;color:#5a9090;margin-top:4px">'
                          f'M={b.get("M_max_kNm",0):.1f} kNm · w={b.get("w_total_kNm",0):.2f} kN/m</div>')
            break

    elif not is_beam and eval_result:
        for c in eval_result.get("columns", []):
            if c.get("id") != eid or (level and c.get("level") and c.get("level") != level):
                continue
            overall_pass = c.get("stress_PASS") and c.get("buckling_PASS")
            sf       = max(c.get("SF_buckling", 3.0), 0.01)
            sf_limit = 3.0
            checks_html = (
                _bar(c.get("sigma_comp_MPa", 0), c.get("allow_comp_MPa", 1),
                     c.get("stress_PASS", False), "Stress")
                + _bar(sf_limit / sf, 1.0, c.get("buckling_PASS", False), "Buckling", "×SF")
            )
            extra_info = (f'<div style="font-size:.67rem;color:#5a9090;margin-top:4px">'
                          f'P={c.get("P_total_kN",0):.1f} kN · trib={c.get("trib_area_m2",0):.1f} m²</div>')
            break

    status_color = "#40d090" if overall_pass else ("#ff5050" if overall_pass is False else "#5a9090")
    status_text  = "PASS" if overall_pass else ("FAIL" if overall_pass is False else "—")

    return (
        f'<div style="background:#0d2828;border:1px solid #1a5555;border-radius:8px;padding:12px 14px;margin-bottom:8px">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;'
        f'margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #1a4040">'
        f'<div>'
        f'<div style="font-size:.62rem;color:#5a9090;letter-spacing:1px;text-transform:uppercase">{el_type}</div>'
        f'<div style="font-size:.9rem;font-weight:700;color:#c8eeed;letter-spacing:.3px;margin-top:1px">{eid}</div>'
        f'<div style="font-size:.7rem;color:#5a9090;margin-top:2px">{mat}{(" · " + sec) if sec else ""}{span_txt}</div>'
        f'</div>'
        f'<div style="font-size:1.3rem;font-weight:800;color:{status_color};padding-top:4px;text-align:right">'
        f'{status_text}</div>'
        f'</div>'
        f'{checks_html or "<div style=\'color:#5a9090;font-size:.74rem;padding:4px 0\'>Run evaluation to see checks</div>"}'
        f'{extra_info}'
        f'</div>'
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
    import traceback as _tb

    _rooms = get_all_rooms(layout)
    _level_keys = get_level_keys(layout)
    _outline = get_outline(layout, _level_keys[0] if _level_keys else None)

    if not _rooms:
        st.error("Generate Grid failed: layout has no **rooms** key.")
        return []
    if not _outline:
        st.error("Generate Grid failed: layout has no **outline** key.")
        return []

    try:
        from nodes.tag_and_audit import generate_structure
        raw = generate_structure(layout)

        # generate_structure returns a list of full layout dicts on success,
        # or the original unchanged dict when it cannot build a grid.
        if not isinstance(raw, list) or len(raw) == 0:
            st.warning(
                "Generate Grid: no structural options were produced. "
                f"generate_structure returned {type(raw).__name__} "
                f"(rooms={len(_rooms)}, "
                f"outline pts={len(_outline)})."
            )
            return []

        # Opening-aware: slide whole grid-lines so columns/beams clear doors & windows
        # (stays orthogonal; columns stay stacked). On by default; toggle in the sidebar.
        _respect = st.session_state.get("respect_openings", True)

        # Wrap each layout dict into the UI's expected format and stamp material.
        opts = []
        for lay in raw:
            lay_copy = dict(lay)
            if "meta" not in lay_copy or not isinstance(lay_copy.get("meta"), dict):
                lay_copy["meta"] = {}
            lay_copy["meta"]["material"] = material
            if _respect:
                try:
                    from nodes.modify import resolve_clashes_orthogonal
                    _fixed, _nmoved = resolve_clashes_orthogonal(json.dumps(lay_copy))
                    if _nmoved:
                        lay_copy = json.loads(_fixed)
                        lay_copy.setdefault("meta", {})["material"] = material
                except Exception as _rce:
                    st.session_state["_last_error"] = f"respect_openings: {_rce}"
            # Seed per-element material + sections so the option is material-complete: the
            # diff baseline isn't null-material (no phantom "whole model changed" after
            # analysis), and exports show the right material. Real edits still diff.
            try:
                from nodes.modify import apply_material_override as _ami
                lay_copy = json.loads(_ami(json.dumps(lay_copy), material))
                lay_copy.setdefault("meta", {})["material"] = material
            except Exception as _mse:
                st.session_state["_last_error"] = f"seed material: {_mse}"
            opts.append({"layout": lay_copy, "evaluation": None})

        return opts

    except Exception as e:
        st.error(f"Generate Grid error: **{e}**")
        st.code(_tb.format_exc(), language="python")
        return []




def _get_failure_alternatives(eval_result: dict, material: str) -> list[str]:
    try:
        from nodes.evaluate import _build_failure_alternatives
        return _build_failure_alternatives(eval_result, [], material)
    except Exception:
        return []


def _auto_eval_after_change(new_layout: dict) -> str:
    """Re-evaluate the structure right after an edit so the user sees its effect
    immediately. Sets eval_result/eval_alts and returns a short PASS/FAIL status."""
    try:
        _ls = json.dumps(new_layout)
        if not any((e.get("attributes") or {}).get("material")
                   for _l, e in iter_all_structure(new_layout)):
            from nodes.modify import apply_material_override
            _ls = apply_material_override(_ls, _mat_now)
        with st.spinner("Re-evaluating…"):
            _ev = _run_evaluate(_ls, sdl=_sdl_now, ll=_ll_now)
        if _ev:
            st.session_state.eval_result = _ev
            st.session_state.eval_alts = _get_failure_alternatives(_ev, _mat_now)
            _s = _ev.get("summary", {})
            if _s.get("overall_PASS"):
                return "now **PASS** ✓"
            return (f"still **FAIL** — {_s.get('beam_failures', 0)} beam / "
                    f"{_s.get('column_failures', 0)} column failure(s)")
    except Exception as _aee:
        st.session_state["_last_error"] = f"auto-eval: {_aee}"
    st.session_state.eval_result = None
    return "added (run analysis to evaluate)"


def _intervention_report_text(before: dict, after: dict, ev: dict | None) -> str:
    """Plain-text intervention summary: what changed vs the original, the change type
    (material/section) per element, a complexity rating, and the resulting cost."""
    d = _compute_diff(before, after)
    _bmap = {f"{lk}|{e['id']}": e for lk, e in iter_all_structure(before)}
    _amap = {f"{lk}|{e['id']}": e for lk, e in iter_all_structure(after)}
    n_mat = n_sec = 0
    chg_lines: list[str] = []
    for k in sorted(d["changed"]):
        be, ae = _bmap[k], _amap[k]
        ba = be.get("attributes") or {}; aa = ae.get("attributes") or {}
        _id = k.split("|", 1)[1]
        if str(ba.get("material") or "") != str(aa.get("material") or ""):
            chg_lines.append(f"  - {_id}: material {ba.get('material') or '—'} -> {aa.get('material') or '—'}")
            n_mat += 1
        else:
            _bs = (ba.get("section") or ba.get("dimensions") or ba.get("col_dims")
                   or f"{ba.get('width','')}x{ba.get('depth','')}")
            _as = (aa.get("section") or aa.get("dimensions") or aa.get("col_dims")
                   or f"{aa.get('width','')}x{aa.get('depth','')}")
            chg_lines.append(f"  - {_id}: section {_bs} -> {_as}")
            n_sec += 1
    added = sorted(d["added"]); removed = sorted(d["removed"])
    n_add, n_rem, n_chg = len(added), len(removed), len(d["changed"])
    n_total = n_add + n_rem + n_chg
    if n_rem > 0 or n_add >= 3:
        complexity = "HIGH (members added/removed — structural intervention)"
    elif n_add > 0 or n_mat > 0:
        complexity = "MEDIUM (material swap or new member)"
    elif n_total > 0:
        complexity = "LOW (section resizing only)"
    else:
        complexity = "NONE (identical to the original)"
    _w, _c = _eval_weight_cost(ev or {})
    L = ["INTERVENTION SUMMARY  (vs the original design you started with)", ""]
    L.append(f"Changes: {n_add} added, {n_rem} removed, {n_chg} changed "
             f"({n_mat} material, {n_sec} section).")
    L.append(f"Intervention complexity: {complexity}.")
    if _c:
        L.append(f"Resulting design cost: ${_c:,.0f}   ({_w:.0f} kN total weight).")
    if ev:
        s = ev.get("summary", {})
        L.append(f"Structural result: {'PASS' if s.get('overall_PASS') else 'FAIL'} — "
                 f"{s.get('beam_failures', 0)} beam / {s.get('column_failures', 0)} column failure(s).")
    L.append("")
    if added:
        L.append("Added:   " + ", ".join(k.split('|', 1)[1] for k in added[:40]))
    if removed:
        L.append("Removed: " + ", ".join(k.split('|', 1)[1] for k in removed[:40]))
    if chg_lines:
        L.append("Changed:")
        L.extend(chg_lines[:50])
    if n_total == 0:
        L.append("No structural changes vs the original — modify the design to create an intervention.")
    return "\n".join(L)





def _apply_alternative(alt: str, layout_str: str, material: str,
                        sdl: float, ll: float) -> tuple[str, dict | None]:
    from nodes.modify import (
        upgrade_element_section, add_midspan_column,
        apply_material_override, BEAM_SECTION_UPGRADE, BEAM_DIM_UPGRADE,
        COL_SECTION_UPGRADE, COL_DIM_UPGRADE, BASE_MATERIALS,
    )
    from nodes.evaluate import evaluate_structure

    if re.match(r"(Increase the|Auto-upgrade) \d+ failing beam", alt, re.IGNORECASE):
        ev = st.session_state.eval_result or {}
        _orig_sec = {b["id"]: b.get("section_mm", "") for b in ev.get("beams", [])}
        _gov0 = {}  # id -> governing failing check (for transparency)
        for b in ev.get("beams", []):
            if not (b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"]):
                _gov0[b["id"]] = ("bending" if not b["bend_PASS"] else "shear" if not b["shear_PASS"]
                                  else "deflection")
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
        _final = {b["id"]: b.get("section_mm", "") for b in (ev or {}).get("beams", [])}
        st.session_state["_last_fix_log"] = [
            {"id": i, "kind": "beam", "from": _orig_sec.get(i, "?"),
             "to": _final.get(i, "?"), "gov": _gov0.get(i, "—")}
            for i in _gov0 if _orig_sec.get(i) != _final.get(i)
        ]
        return layout_str, ev

    if re.match(r"(Increase the|Auto-upgrade) \d+ failing col", alt, re.IGNORECASE):
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


# ── Alt-metrics helpers ────────────────────────────────────────────────────────

_MAT_DENSITY_KNM3  = {"RCC": 25.0,   "STEEL": 78.5,   "TIMBER": 5.0}
_MAT_COST_PER_M3   = {"RCC": 200,    "STEEL": 8_000,  "TIMBER": 1_000}


def _section_area_m2(section_mm: str, material: str) -> float:
    from nodes.modify import STEEL_BEAM_PROPS, STEEL_COL_PROPS
    if "STEEL" in material.upper():
        sp = STEEL_BEAM_PROPS.get(section_mm) or STEEL_COL_PROPS.get(section_mm)
        if sp:
            return sp["A_mm2"] / 1e6
    if "x" in section_mm:
        parts = section_mm.split("x")
        if len(parts) == 2:
            try:
                return float(parts[0]) / 1000.0 * float(parts[1]) / 1000.0
            except ValueError:
                pass
    return 0.01


def _eval_weight_cost(ev: dict) -> tuple[float, float]:
    w = c = 0.0
    for b in ev.get("beams", []):
        mk = next((k for k in _MAT_DENSITY_KNM3 if k in b.get("material", "").upper()), "RCC")
        A  = _section_area_m2(b.get("section_mm", ""), b.get("material", ""))
        v  = A * b.get("span_m", 0.0)
        w += _MAT_DENSITY_KNM3[mk] * v
        c += _MAT_COST_PER_M3[mk]  * v
    for col in ev.get("columns", []):
        mk = next((k for k in _MAT_DENSITY_KNM3 if k in col.get("material", "").upper()), "RCC")
        A  = _section_area_m2(col.get("section_mm", ""), col.get("material", ""))
        v  = A * col.get("height_m", 3.0)
        w += _MAT_DENSITY_KNM3[mk] * v
        c += _MAT_COST_PER_M3[mk]  * v
    return w, c


def _compute_alt_metrics(alt: str, layout_obj: dict, ev0: dict,
                          mat: str, sdl: float, ll: float) -> dict:
    try:
        w0, c0 = _eval_weight_cost(ev0)
        d0 = max((b.get("delta_total_mm", 0) for b in ev0.get("beams", [])), default=0.0)
        _, ev1 = _apply_alternative(alt, json.dumps(layout_obj), mat, sdl, ll)
        if not ev1:
            return {}
        w1, c1 = _eval_weight_cost(ev1)
        d1 = max((b.get("delta_total_mm", 0) for b in ev1.get("beams", [])), default=0.0)
        def _pct(a, b): return (a - b) / max(abs(b), 0.001) * 100
        return {
            "weight_pct": _pct(w1, w0),
            "cost_pct":   _pct(c1, c0),
            "defl_pct":   _pct(d1, d0),
        }
    except Exception:
        return {}


# ── Agent chat ─────────────────────────────────────────────────────────────────

def _llm_is_reachable(timeout: float = 3.0) -> bool:
    try:
        from _runtime.config import load_settings
        _s = load_settings()
        # Anthropic (Claude): reachable as long as an API key is configured.
        if _s.provider == "anthropic":
            return bool(_s.api_key)
        # Local OpenAI-compatible endpoint (e.g. LM Studio): probe /v1/models.
        import urllib.request as _ur
        _url = _s.base_url.rstrip("/").replace("/v1", "") + "/v1/models"
        with _ur.urlopen(_url, timeout=timeout):
            return True
    except Exception:
        return False


def _run_agent_chat(prompt: str, layout: dict, eval_result: dict | None = None) -> str:
    import math as _math
    import re as _re
    try:
        if not _llm_is_reachable():
            from _runtime.config import load_settings as _ls
            if _ls().provider == "anthropic":
                return (
                    "No Anthropic API key configured. "
                    "Add ANTHROPIC_API_KEY to the project .env file, then try again."
                )
            return (
                "LM Studio is not running. "
                "Start LM Studio, load a model, then try again."
            )

        from _runtime.bootstrap import bootstrap
        from _runtime.llm import call_llm
        from nodes.tools import get_action_tools
        SYSTEM_PROMPT = _APP_AGENT_PROMPT
        from graph import _format_tool_catalog

        ctx          = bootstrap()
        tool_catalog = _format_tool_catalog(get_action_tools())
        structure    = get_structure(layout)
        beams        = [el for el in structure if len(el.get("geometry", [])) == 2]
        cols         = [el for el in structure if len(el.get("geometry", [])) == 1]
        sdl          = st.session_state.get("sdl_kNm2", 3.5)
        ll           = st.session_state.get("live_load_kNm2", 2.0)

        # Build comprehensive structure summary (element IDs + sections + spans)
        beam_lines, col_lines = [], []
        for el in structure:
            attrs = el.get("attributes", {})
            geo   = el.get("geometry", [])
            mat   = attrs.get("material", "RCC")
            sec   = (attrs.get("section") or attrs.get("dimensions")
                     or (f"{attrs.get('width','?')}x{attrs.get('depth','?')}"
                         if attrs.get("depth") and attrs.get("width") else "?"))
            if len(geo) == 2:
                span = round(_math.dist(geo[0], geo[1]), 2)
                beam_lines.append(f"{el['id']} {mat} {sec} {span}m")
            elif len(geo) == 1:
                col_lines.append(f"{el['id']} {mat} {sec}")

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

        col_summary  = ", ".join(col_lines[:30])  if col_lines  else "none generated yet"
        beam_summary = ", ".join(beam_lines[:20]) if beam_lines else "none generated yet"

        # ── Grounding metrics: weight/cost per design + option, cheapest/lightest,
        #    material unit costs, and the most-utilised members — so the model can
        #    answer cost/which-option/which-beam questions with real numbers. ──
        _metric_lines: list[str] = []
        _opt_cw: list[tuple] = []   # (label, weight_kN, cost_usd, pass)
        if eval_result:
            _w0, _c0 = _eval_weight_cost(eval_result)
            _metric_lines.append(f"Current design: weight {_w0:.1f} kN, cost ${_c0:,.0f}")
        for _gi, _go in enumerate(st.session_state.get("grid_options", []), 1):
            _gev = _go.get("evaluation")
            if _gev:
                _gw, _gc = _eval_weight_cost(_gev)
                _gp = (_gev.get("summary", {}) or {}).get("overall_PASS")
                _opt_cw.append((f"Option {_gi}", _gw, _gc, _gp))
                _metric_lines.append(
                    f"Option {_gi}: weight {_gw:.1f} kN, cost ${_gc:,.0f}, "
                    f"{'PASS' if _gp else 'FAIL'}")
        if _opt_cw:
            _cheap = min(_opt_cw, key=lambda x: x[2])
            _light = min(_opt_cw, key=lambda x: x[1])
            _metric_lines.append(
                f"Cheapest = {_cheap[0]} (${_cheap[2]:,.0f}); Lightest = {_light[0]} ({_light[1]:.1f} kN)")
        _metric_lines.append(
            "Material unit cost ($/m³): " + ", ".join(f"{k} {v}" for k, v in _MAT_COST_PER_M3.items())
            + "  (timber is the cheapest & lightest per m³; steel the most expensive)")
        _flex_top = _flexibility_rows(eval_result) if eval_result else []
        if _flex_top:
            _metric_lines.append("Most utilised members: " + "; ".join(
                f"{r['id']} {r['util']:.0f}% ({r['gov']})" for r in _flex_top[:4]))
        metrics_block = ("\nMetrics:\n  " + "\n  ".join(_metric_lines)) if _metric_lines else ""

        context_msg = {
            "role": "user",
            "content": (
                f"Context: Layout '{layout.get('layoutId', '?')}' has "
                f"{len(cols)} columns and {len(beams)} beams.{eval_lines}{metrics_block}\n"
                f"Columns: {col_summary}\n"
                f"Beams: {beam_summary}\n\n"
                f"User request:\n{prompt}"
            ),
        }

        # ── Conversation memory: replay the last few turns so follow-ups like
        #    "do so" / "which is cheaper" / "why?" resolve against prior context. ──
        _SIGNAL_PREFIXES = ("APPLY_TOOL:", "APPLY_MATERIAL:", "GENERATE_GRID",
                            "EVALUATE", "FIX_FAILING")
        _hist_msgs: list[dict] = []
        for _h in st.session_state.get("history", [])[-4:]:
            _hq = (_h.get("prompt") or "").strip()
            _ha = (_h.get("response") or "").strip()
            if _hq:
                _hist_msgs.append({"role": "user", "content": _hq[:400]})
            if _ha and not _ha.startswith(_SIGNAL_PREFIXES):
                _hist_msgs.append({"role": "assistant", "content": _ha[:400]})

        try:
            result = call_llm(ctx.llm, SYSTEM_PROMPT, _hist_msgs + [context_msg], tool_catalog)
        except Exception as _llm_err:
            # Malformed/unparseable model output → don't crash; fall through to the
            # deterministic intent parser below (handles add/remove/move/material/etc.).
            st.session_state["_last_error"] = f"LLM parse fallback: {_llm_err}"
            result = {"action": "final", "final_response": ""}

        # ── Question / hypothetical guard ────────────────────────────────────────
        # Detect prompts that are asking for advice, opinion, or a "what if"
        # simulation rather than issuing a command. When this flag is set,
        # any tool call that mutates the structure (set_material, remove, upgrade)
        # is ignored and the agent falls through to a text-only answer instead.
        _prompt_lower = prompt.lower()
        _is_question_prompt = any(k in _prompt_lower for k in (
            "what if", "if i ", "if we ", "would it", "should i", "should we",
            "is it", "is that", "is steel", "is timber", "is rcc", "is concrete",
            "better than", " vs ", "versus", "or steel", "or timber", "or rcc",
            "or concrete", "good option", "good choice", "a good", "opinion",
            "advice", "recommend", "what do you think", "make sense", "worth it",
            "is upgrading", "is switching", "which is better", "which material",
            "what material", "does it make", "?",
        ))

        if result.get("action") == "tool":
            calls = result.get("tool_calls", [])
            # Advisory text from the agent (explanation + alternatives)
            _advisory = (result.get("final_response") or "").strip()
            _force = "force" in prompt.lower()
            for _c in calls:
                _cname  = _c.get("name", "")
                _cinput = _c.get("input", _c.get("arguments", {})) or {}

                if _cname == "tag_and_audit":
                    return "GENERATE_GRID" + (f"\n{_advisory}" if _advisory else "")
                if _cname == "evaluate_structure":
                    return "EVALUATE"
                if _cname == "set_material":
                    # Block material change when user is asking a question/opinion.
                    if _is_question_prompt:
                        result = {"action": "final", "final_response": _advisory}
                        break
                    _mt = str(_cinput.get("material") or _cinput.get("value") or "").upper()
                    if _mt:
                        _lvl = str(_cinput.get("level") or "").strip()
                        _et = str(_cinput.get("element_type") or "").strip()
                        return f"APPLY_MATERIAL:{_mt}|{_lvl}|{_et}"
                if _cname == "modify_structure":
                    _ms_action = _cinput.get("action", "")
                    _ms_eid    = _cinput.get("element_id", "")
                    _ms_attr   = str(_cinput.get("attribute") or "").lower()
                    _ms_val    = _cinput.get("value", "")
                    if _ms_action == "remove" and _ms_eid:
                        return ("APPLY_TOOL:" + json.dumps(
                            {"name": "remove_element",
                             "input": {"element_id": _ms_eid, "force": _force},
                             "advisory": _advisory}))
                    # material set via set_attribute → real material switch
                    if _ms_action == "set_attribute" and _ms_attr == "material" and _ms_val:
                        if _is_question_prompt:
                            result = {"action": "final", "final_response": _advisory}
                            break
                        return f"APPLY_MATERIAL:{str(_ms_val).upper()}"
                    if _ms_action == "set_attribute" and _ms_eid and _ms_val:
                        return ("APPLY_TOOL:" + json.dumps(
                            {"name": "upgrade_element_section",
                             "input": {"element_id": _ms_eid, "new_section": _ms_val},
                             "advisory": _advisory}))
                if _cname == "remove_element" and _cinput.get("element_id"):
                    _cinput["force"] = _force
                    return "APPLY_TOOL:" + json.dumps(
                        {"name": "remove_element", "input": _cinput, "advisory": _advisory})
                if _cname == "add_midspan_column" and (_cinput.get("beam_id") or _cinput.get("element_id")):
                    return "APPLY_TOOL:" + json.dumps(
                        {"name": "add_midspan_column", "input": _cinput, "advisory": _advisory})
                if _cname == "upgrade_element_section" and _cinput.get("element_id"):
                    return "APPLY_TOOL:" + json.dumps(
                        {"name": "upgrade_element_section", "input": _cinput, "advisory": _advisory})
                if _cname == "move_element" and _cinput.get("element_id"):
                    return "APPLY_TOOL:" + json.dumps(
                        {"name": "move_element", "input": _cinput, "advisory": _advisory})
                if _cname == "add_column" and _cinput.get("reference_id"):
                    return "APPLY_TOOL:" + json.dumps(
                        {"name": "add_column", "input": _cinput, "advisory": _advisory})
                if _cname == "add_beam" and _cinput.get("column_a") and _cinput.get("column_b"):
                    return "APPLY_TOOL:" + json.dumps(
                        {"name": "add_beam", "input": _cinput, "advisory": _advisory})

            # The model asked for an action but the parameters were malformed
            # (e.g. empty element_id) — be honest instead of faking success.
            if calls:
                _avail = ", ".join(el["id"] for el in structure[:18])
                return ((_advisory + "\n\n") if _advisory else "") + (
                    "I understood you want an action, but I couldn't read which element to act on. "
                    f"Please name it — available IDs: {_avail}{'…' if len(structure) > 18 else ''}.")

        resp = result.get("final_response", "")

        # ── Cost-comparison safety-net: if the user asked about cost and the model
        #    gave nothing or a waffle, answer with the real figures from Metrics. ──
        def _cost_answer() -> str:
            if _opt_cw:
                _parts = [f"{l}: ${c:,.0f} ({w:.0f} kN, {'PASS' if p else 'FAIL'})"
                          for l, w, c, p in _opt_cw]
                _ch = min(_opt_cw, key=lambda x: x[2])
                return ("Cost comparison — " + "; ".join(_parts)
                        + f". **{_ch[0]} is the cheapest at ${_ch[2]:,.0f}.** "
                        "Timber is cheapest per m³, steel the most expensive.")
            if eval_result:
                _w, _c = _eval_weight_cost(eval_result)
                return (f"Current design ≈ **${_c:,.0f}** ({_w:.0f} kN). "
                        "Save snapshots / options and I can compare their costs.")
            return "Generate a grid and run analysis first, then I can compare option costs."

        # ── "Best option / which snapshot is best" — rank options + snapshots + current ──
        def _best_answer() -> str:
            _items = list(_opt_cw)   # grid options (label, w, c, pass)
            for _sn in st.session_state.get("snapshots", []):
                _ev = _sn.get("eval_result")
                if _ev:
                    _sw, _sc = _eval_weight_cost(_ev)
                    _sp = (_ev.get("summary", {}) or {}).get("overall_PASS")
                    _items.append((_sn.get("label", "Snapshot"), _sw, _sc, _sp))
            if eval_result:
                _cw0, _cc0 = _eval_weight_cost(eval_result)
                _cp0 = (eval_result.get("summary", {}) or {}).get("overall_PASS")
                _items.append(("Current design", _cw0, _cc0, _cp0))
            if not _items:
                return ("Generate grid options or save snapshots and run analysis — "
                        "then I can rank them and tell you the best.")
            _passing = [i for i in _items if i[3]]
            _pool = _passing or _items
            _best = min(_pool, key=lambda x: (x[2], x[1]))   # cheapest, then lightest
            _parts = [f"{l}: ${c:,.0f} ({w:.0f} kN, {'PASS' if p else 'FAIL'})"
                      for l, w, c, p in _items]
            _why = ("cheapest option that passes" if _passing
                    else "cheapest — but note NONE pass yet, so upgrade/fix before building")
            return ("Comparison — " + "; ".join(_parts)
                    + f". **Best: {_best[0]}** ({_why}) at ${_best[2]:,.0f}, {_best[1]:.0f} kN.")

        _is_best = any(k in prompt.lower() for k in
                       ("best option", "best one", "best snapshot", "which option",
                        "which is best", "which is the best", "recommend",
                        "compare the option", "compare options", "compare saved",
                        "compare snapshot", "compare both", "which one is best",
                        "compare the snapshot"))
        if _is_best:
            return _best_answer()

        _is_cost = any(k in prompt.lower() for k in
                       ("cheap", "cost", "price", "expensive", "budget", "carbon", "$"))
        _generic = bool(resp) and any(p in resp.lower() for p in (
            "we can analyz", "we can analys", "i suggest", "to determine",
            "various factors", "difficult to recommend", "without further",
            "evaluation: pass", "evaluation: fail", "0 beam failure", "0 column failure"))
        if _is_cost and (not resp or _generic):
            return _cost_answer()

        # ── Material comparison / "what if" advice ────────────────────────────
        def _material_advice() -> str:
            _MAT_INFO = {
                "RCC":    ("cheapest (~$120/m³)", "medium spans 4–8 m", "heaviest (~24 kN/m³)", "fire-resistant, easy to form"),
                "STEEL":  ("most expensive (~$2 400/m³)", "longest spans 8–20 m", "lightest (~77 kN/m³ but tiny sections)", "fast to erect, fully recyclable"),
                "TIMBER": ("low cost (~$400/m³)", "short–medium spans 3–6 m", "very light (~5 kN/m³)", "lowest carbon, natural aesthetic"),
            }
            _cur = _mat_now
            _lines = ["**Material comparison for your design:**\n"]
            for _m, (_cost, _span, _wt, _note) in _MAT_INFO.items():
                _tag = " ← **current**" if _m == _cur else ""
                _lines.append(f"- **{_m}**: {_cost} · {_span} · {_wt} · {_note}{_tag}")
            if eval_result:
                _w, _c = _eval_weight_cost(eval_result)
                _sm_now = (eval_result.get("summary") or {})
                _pass = _sm_now.get("overall_PASS")
                _lines.append(f"\nYour current **{_cur}** design: ≈ **${_c:,.0f}** · **{_w:.0f} kN** — {'PASS ✓' if _pass else 'FAIL ✗'}")
            _lines.append("\nTo actually switch: type **\"change to steel\"** (or timber / concrete).")
            return "\n".join(_lines)

        _is_mat_advice = any(k in _prompt_lower for k in (
            "what if", "better than", " vs ", "versus", "which material", "what material",
            "or steel", "or timber", "or rcc", "or concrete", "steel or", "timber or",
            "which is better", "is steel", "is timber", "is rcc", "is concrete",
        )) and any(m in _prompt_lower for m in ("steel", "timber", "rcc", "concrete", "wood"))
        if _is_mat_advice and (not resp or _generic):
            return _material_advice()

        # ── Follow-up / "explain more" ────────────────────────────────────────
        _is_explain_more = any(k in _prompt_lower for k in (
            "explain more", "explain further", "tell me more", "more detail",
            "why is that", "why that", "how so", "why option", "elaborate",
            "can you explain", "expand on", "go into more", "what does that mean",
            "why is it", "why did you", "why do you", "why is option",
        ))
        if _is_explain_more:
            _hist = st.session_state.get("history", [])
            _last_r = _hist[-1].get("response", "") if _hist else ""
            # ── Case 1: last answer was a best-option comparison ──────────────
            if _last_r and ("Best:" in _last_r or "Comparison —" in _last_r or
                            "best option" in _last_r.lower() or
                            "Option 1" in _last_r):
                _explain_lines = ["**Here's the reasoning in more detail:**\n"]
                # Collect all option items for ranking
                _opt_items_ex = []
                for _sn_ex in st.session_state.get("snapshots", []):
                    _ev_ex = _sn_ex.get("eval_result")
                    if _ev_ex:
                        _sw_ex, _sc_ex = _eval_weight_cost(_ev_ex)
                        _sp_ex = (_ev_ex.get("summary", {}) or {}).get("overall_PASS")
                        _opt_items_ex.append((_sn_ex.get("label", "Snapshot"), _sw_ex, _sc_ex, _sp_ex))
                if eval_result:
                    _sw0_ex, _sc0_ex = _eval_weight_cost(eval_result)
                    _sp0_ex = (eval_result.get("summary", {}) or {}).get("overall_PASS")
                    _opt_items_ex.append(("Current design", _sw0_ex, _sc0_ex, _sp0_ex))
                if _opt_items_ex:
                    _pass_ex = [i for i in _opt_items_ex if i[3]]
                    _pool_ex = _pass_ex if _pass_ex else _opt_items_ex
                    _best_ex = min(_pool_ex, key=lambda x: (x[2], x[1]))
                    _sorted_ex = sorted(_opt_items_ex, key=lambda x: (0 if x[3] else 1, x[2]))
                    _explain_lines.append(
                        f"**Cost is directly tied to material volume.** "
                        f"Fewer elements and smaller sections = less material used = lower cost. "
                        f"Weight follows the same pattern — a lighter structure uses less material overall.\n"
                    )
                    if _pass_ex:
                        _explain_lines.append(
                            f"All {len(_pass_ex)} of {len(_opt_items_ex)} option(s) that pass satisfy "
                            f"the structural checks (bending, shear, deflection for beams; stress and "
                            f"buckling safety factor ≥ 3.0 for columns). "
                            f"Since they're structurally equivalent, **cost becomes the deciding factor**.\n"
                        )
                    else:
                        _explain_lines.append(
                            "None of the options currently pass — the cheapest is suggested as a "
                            "starting point. Run analysis and fix failing elements before building.\n"
                        )
                    _explain_lines.append("**Full ranking:**")
                    for _rank_i, (_lbl_e, _w_e, _c_e, _p_e) in enumerate(_sorted_ex, 1):
                        _status_e = "PASS ✓" if _p_e else "FAIL ✗"
                        _explain_lines.append(
                            f"{_rank_i}. **{_lbl_e}** — ${_c_e:,.0f} · {_w_e:.0f} kN · {_status_e}"
                        )
                    _explain_lines.append(
                        f"\n**{_best_ex[0]}** ranks first because it has the lowest cost "
                        + ("among passing options. " if _pass_ex else "overall. ")
                        + "To lock it in, press **Save Snapshot** and apply it."
                    )
                else:
                    _explain_lines.append(
                        "Generate options and run analysis first — then ask again and I can explain "
                        "the ranking in full."
                    )
                return "\n".join(_explain_lines)

            # ── Case 2: last answer was a structural evaluation ───────────────
            elif _last_r and ("PASS" in _last_r or "FAIL" in _last_r or
                              "beam failure" in _last_r.lower() or
                              "column failure" in _last_r.lower()):
                if eval_result:
                    _er_sm_ex = eval_result.get("summary", {}) or {}
                    _bf_ex = _er_sm_ex.get("beam_failures", 0)
                    _cf_ex = _er_sm_ex.get("column_failures", 0)
                    _pass_ex2 = _er_sm_ex.get("overall_PASS")
                    _w_ex2, _c_ex2 = _eval_weight_cost(eval_result)
                    if _pass_ex2:
                        return (
                            f"**Why it passes:**\n"
                            f"- All beam spans are short enough that bending stress, shear, and "
                            f"deflection stay within code limits for **{_mat_now}** sections.\n"
                            f"- All column heights are within safe buckling limits "
                            f"(Euler factor of safety ≥ 3.0).\n"
                            f"- Total structural weight: **{_w_ex2:.0f} kN** · "
                            f"Estimated material cost: **${_c_ex2:,.0f}**.\n\n"
                            f"You can still optimise — ask me to **'fix failing beams'** after "
                            f"reducing sections, or **'compare options'** to find a lighter/cheaper pass."
                        )
                    else:
                        return (
                            f"**Why it fails:**\n"
                            f"- **{_bf_ex} beam(s) failing**: bending moment or deflection exceeds the "
                            f"allowable limit for the current span and section size. "
                            f"Long spans need deeper beams or a midspan column.\n"
                            f"- **{_cf_ex} column(s) failing**: compressive stress or Euler buckling "
                            f"safety factor is below 3.0. Tall slender columns need larger sections.\n\n"
                            f"**Quick fixes**: ask me to *'fix failing beams'* or "
                            f"*'add a midspan column on B5'* to split the longest spans."
                        )
                return _last_r + "\n\n(Run **Run Analysis** first for a detailed structural breakdown.)"

            # ── Case 3: any other prior answer ───────────────────────────────
            elif _last_r and not _generic:
                # Re-use the prior answer and add a note
                return (
                    _last_r
                    + "\n\n*(That's the full breakdown available — ask me 'what is the best option?' "
                    "or 'run analysis' for fresh data.)*"
                )
            # Fall through: let the LLM try with history context

        if not resp:
            # LLM deferred to the in-app pipeline — handle based on intent.
            _lower = prompt.lower()
            # "what if" = simulation only; bare "remove/delete" = execute immediately
            _is_explicit_whatif = any(kw in _lower for kw in
                                      ("what if", "if i remove", "if we remove",
                                       "if you remove", "without"))
            _is_removal = any(kw in _lower for kw in ("remove", "delete"))

            if not structure:
                return (
                    "No structural grid found. "
                    "Click **Generate Grid**, then select an option."
                )

            # Shared ID resolver for both paths
            _sm  = {el["id"].upper(): el["id"] for el in structure}
            _snm = {el["id"].upper().replace("_", ""): el["id"] for el in structure}
            def _rid(m: str):
                k = m.upper()
                return _sm.get(k) or _snm.get(k.replace("_", ""))
            _pat = _re.findall(r'\b([A-Za-z]+_?\d+)\b', prompt, _re.IGNORECASE)
            _ids_in_prompt = list(dict.fromkeys(
                m for m in _pat if _rid(m) and len(m) <= 14
            ))

            # ── Level extractor: "level 02", "level_02", "floor 2", "second floor" ──
            def _extract_level(text: str) -> str:
                """Return canonical level key (e.g. 'level_02') or '' if not found."""
                import re as _rre
                _t = text.lower()
                # "level_02", "level02", "level 02"
                m = _rre.search(r'level[_ ]?0*(\d+)', _t)
                if m:
                    return f"level_{int(m.group(1)):02d}"
                # "floor 2", "2nd floor", "second floor" …
                _floor_words = {"first": 1, "second": 2, "third": 3, "fourth": 4,
                                "fifth": 5, "ground": 1}
                for word, num in _floor_words.items():
                    if word in _t:
                        return f"level_{num:02d}"
                m2 = _rre.search(r'(\d+)(?:st|nd|rd|th)?\s*floor', _t)
                if m2:
                    return f"level_{int(m2.group(1)):02d}"
                return ""

            _prompt_level = _extract_level(prompt)

            # ── ADD a beam between two columns (orthogonal only) ──────────────
            if ("beam" in _lower and any(k in _lower for k in ("add", "connect", "between"))
                    and len(_ids_in_prompt) >= 2):
                _ab_in = {"column_a": _rid(_ids_in_prompt[0]),
                          "column_b": _rid(_ids_in_prompt[1])}
                if _prompt_level:
                    _ab_in["level_key"] = _prompt_level
                return "APPLY_TOOL:" + json.dumps({"name": "add_beam", "input": _ab_in})

            # ── ADD a column at an offset from a reference column ──────────────
            if (any(k in _lower for k in ("add", "put", "place")) and "column" in _lower
                    and "from" in _lower and _ids_in_prompt):
                _nums = _re.findall(r'(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?', prompt)
                _amt = abs(float(_nums[0])) if _nums else 1.0
                _is_y = any(k in _lower for k in (" y", "vertical", "north", "south",
                                                  "above", "below", "up", "down"))
                _neg = any(k in _lower for k in ("left", "west", "south", "below",
                                                 "down", "minus", "negative"))
                _amt = -_amt if _neg else _amt
                _ac_in = {"reference_id": _rid(_ids_in_prompt[0]),
                          ("dy" if _is_y else "dx"): _amt}
                if _prompt_level:
                    _ac_in["level_key"] = _prompt_level
                return "APPLY_TOOL:" + json.dumps({"name": "add_column", "input": _ac_in})

            # ── ADD a midspan column (split a beam) ───────────────────────────
            if (any(k in _lower for k in ("add column", "add a column", "midspan",
                                          "mid-span", "mid col", "intermediate column",
                                          "split beam")) and _ids_in_prompt):
                return ("APPLY_TOOL:" + json.dumps(
                    {"name": "add_midspan_column",
                     "input": {"beam_id": _rid(_ids_in_prompt[0])}}))

            # ── MOVE a column (clear a clash / fine-tune spacing) ─────────────
            if (any(k in _lower for k in ("move ", "shift ", "nudge ", "relocate"))
                    and _ids_in_prompt):
                # numbers NOT glued to a letter, so 'C4' / 'level_02' don't leak in
                _nums = _re.findall(r'(?<![A-Za-z0-9_])\d+(?:\.\d+)?', prompt)
                _amt = abs(float(_nums[0])) if _nums else 0.5
                _is_y = any(k in _lower for k in (" y", "vertical", "north", "south",
                                                  "up", "down", "forward", "backward"))
                _neg = any(k in _lower for k in ("left", "west", "south", "down",
                                                 "backward", "back", "minus", "negative"))
                _signed = -_amt if _neg else _amt
                _mv_in = {"element_id": _rid(_ids_in_prompt[0]),
                          ("dy" if _is_y else "dx"): _signed}
                return "APPLY_TOOL:" + json.dumps({"name": "move_element", "input": _mv_in})

            # ── MATERIAL switch (all elements) ────────────────────────────────
            # Only execute if this is a command, NOT a question/opinion request.
            # "is steel a good option?" or "should I upgrade to timber?" must NOT trigger
            # a material change — the user is asking for advice, not issuing a command.
            _is_opinion = any(k in _lower for k in (
                "is it", "is that", "good option", "good choice", "a good", "better option",
                "would it", "should i", "should we", "is steel", "is timber", "is rcc",
                "is concrete", "opinion", "advice", "think about", "worth it",
                "recommend", "what do you think", "is it worth", "is upgrading",
                "is switching", "make sense", "does it make", "?",
            ))
            _mat_kw = ("STEEL" if "steel" in _lower
                       else "TIMBER" if ("timber" in _lower or "wood" in _lower)
                       else "RCC" if ("rcc" in _lower or "concrete" in _lower)
                       else "")
            if _mat_kw and not _is_opinion and any(k in _lower for k in
                               ("switch", "change", "make it", "convert", "use ", "to ")):
                return f"APPLY_MATERIAL:{_mat_kw}"

            # ── FIX failing elements ─────────────────────────────────────────
            if any(k in _lower for k in ("fix", "repair", "make it pass",
                                          "make them pass", "resolve")):
                return "FIX_FAILING"

            # ── Imperative removal — execute immediately ──────────────────────
            if _is_removal and not _is_explicit_whatif:
                if _ids_in_prompt:
                    _eid_exec = _rid(_ids_in_prompt[0])
                    _force_rm = "force" in _lower   # "force remove G3" overrides perimeter lock
                    return f"APPLY_TOOL:{json.dumps({'name': 'remove_element', 'input': {'element_id': _eid_exec, 'force': _force_rm}})}"
                _id_list = ", ".join(el["id"] for el in structure[:15])
                return (
                    f"Could not find that element ID. "
                    f"Enable **Labels** to see exact IDs. "
                    f"Available: {_id_list}{'…' if len(structure) > 15 else ''}."
                )

            # ── What-if simulation ─────────────────────────────────────────────
            if _is_explicit_whatif or _is_removal:
                _remove_ids = [_rid(m) for m in _ids_in_prompt]
                if _remove_ids:
                    from nodes.evaluate import simulate_what_if_removal, _beam_trib_widths
                    _b_trib = _beam_trib_widths(beams)
                    _wi = simulate_what_if_removal(
                        json.dumps(layout), _remove_ids, _b_trib,
                        ll_kNm2=ll, sdl_kNm2=sdl,
                    )
                    _aff  = _wi.get("affected_beams", [])
                    _wism = _wi.get("summary", {})
                    if not _aff:
                        return (
                            f"Removing **{', '.join(_remove_ids)}** does not directly "
                            "affect any beam spans — the remaining structure can carry the load."
                        )
                    _lines = [
                        f"**What-if: Remove {', '.join(_remove_ids)}**",
                        f"Result: **{'FAIL' if not _wism.get('overall_PASS') else 'PASS'}** — "
                        f"{_wism.get('failures', 0)} affected beam(s) would fail",
                    ]
                    for _r in _aff[:6]:
                        _orig = _r.get("original_span_m", "?")
                        _eff  = _r.get("effective_span_m")
                        _stxt = (f"{_orig}m → {_eff}m" if _eff else "unsupported")
                        _fails = [k for k, f in [
                            ("bending",    not _r.get("bend_PASS",    True)),
                            ("shear",      not _r.get("shear_PASS",   True)),
                            ("deflection", not (_r.get("defl_TL_PASS", True)
                                                 and _r.get("defl_LL_PASS", True))),
                        ] if f]
                        _st = f"  FAIL ({', '.join(_fails)})" if _fails else "  ok"
                        _lines.append(f"• Beam **{_r['id']}**: span {_stxt}{_st}")
                    if not _wism.get("overall_PASS"):
                        _lines.append(
                            "\nOptions: (1) Add intermediate column to halve the span, "
                            "(2) Upgrade the beam section, "
                            "(3) Add a transfer beam to redirect the load path."
                        )
                    return "\n".join(_lines)
                _id_list = ", ".join(el["id"] for el in structure[:15])
                return (
                    f"Could not find that element ID. "
                    f"Enable **Labels** to see exact IDs. "
                    f"Available: {_id_list}{'…' if len(structure) > 15 else ''}."
                )

            return "EVALUATE"
        return resp
    except Exception as e:
        msg = str(e)
        if any(kw in msg.lower() for kw in
               ("empty response", "unavailable", "rate-limited", "rate limited")):
            return "The AI model is not responding right now — please try again in a moment."
        return f"Agent error: {msg}"


# ── Session state ──────────────────────────────────────────────────────────────

def _ensure_session() -> None:
    defaults: dict = {
        # ── Version / layout state ─────────────────────────────────────────
        "currentLayout":    None,   # dict | None — the live working copy
        "versionHistory":   [],     # list[dict] — every committed past layout
        "currentVersion":   0,      # int — increments on every _push_version
        "setupDone":        False,  # bool — True after upload + OK pressed
        "_last_upload_fp":  None,   # (name, size) of last processed upload
        # ── UI state ───────────────────────────────────────────────────────
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
        "diff_baseline":   None,   # the applied grid/option — Diff toggle compares vs this
        "output_log":      [],
        "selected_el":     "",
        "active_level":    "level_01",
        "active_element_level": "",
        "_last_url_sel": "\x00",   # last _sel query-param value the URL→state bridge applied
        "_last_url_lvl": "\x00",
        "cmp_sel_indices": [],      # indices into snapshots list for compare tab
        "compare_mode":    False,
        "labels_on":       False,
        "footings_on":     True,
        "respect_openings": False,   # opt-in: keep Generate Grid's clean perimeter-following grid
        "show_conflicts":  False,    # magenta window/door clashes only when toggled on
        "user_name":       "",       # set at the launch gate
        "user_email":      "",
        "auto_eval":       True,
        "snapshots":       [],
        "theme":           "dark",
        "view_mode":       "2D",
        "compare_view_mode": "2D",
        "inputs_expanded": True,
        "selected_opt_bar_idx": -1,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_ensure_session()

# ─── query params ─────────────────────────────────────────────────────────────
# URL→state bridge: apply a _sel/_lvl query param ONLY when it actually changes
# (tracked by a dedicated key). Direct selections (2D on_select) update selected_el
# without touching these keys, so a stale URL value never clobbers a new selection.
_pending_sel = st.query_params.get("_sel", "")
if _pending_sel != st.session_state.get("_last_url_sel", "\x00"):
    st.session_state.selected_el = _pending_sel
    st.session_state["_last_url_sel"] = _pending_sel
_pending_lvl = st.query_params.get("_lvl", "")
if _pending_lvl != st.session_state.get("_last_url_lvl", "\x00"):
    st.session_state.active_element_level = _pending_lvl
    if _pending_lvl:
        st.session_state.active_level = _pending_lvl
    st.session_state["_last_url_lvl"] = _pending_lvl

# Toolbar state via query params (set by JS bridge when overlay buttons are clicked)
_tb_vm = st.query_params.get("_tb_vm", "")
if _tb_vm in ("2D", "3D"):
    st.session_state["view_mode"] = _tb_vm
_tb_labels = st.query_params.get("_tb_labels", "")
if _tb_labels in ("0", "1"):
    _new_lab = _tb_labels == "1"
    if _new_lab != st.session_state.labels_on:
        st.session_state.labels_on = _new_lab
        st.session_state.viewer_nonce += 1
_tb_diff = st.query_params.get("_tb_diff", "")
if _tb_diff in ("0", "1"):
    st.session_state.compare_mode = _tb_diff == "1"
_tb_auto = st.query_params.get("_tb_auto", "")
if _tb_auto in ("0", "1"):
    st.session_state["auto_eval"] = _tb_auto == "1"
_aq_raw = st.query_params.get("_aq", "")

# ── UI agent system prompt (direct-LLM path only, does not affect reason.py / LangGraph CLI) ──
_APP_AGENT_PROMPT = """You are a structural design assistant embedded in the PermanenceOS UI.
You help architects modify, evaluate, and understand structural layouts.

ADVISORY-FIRST RULE — for every action that modifies the structure, you MUST:
1. In final_response: briefly explain what this change will do (1-2 sentences), name 1-2 alternatives, then confirm you are executing.
2. Set action="tool" with the correct tool call.
Both final_response and tool_calls MUST be filled simultaneously when executing.

Example format for a remove action:
{{
  "action": "tool",
  "final_response": "Removing column C4. This will merge the beams on either side into a longer span — check that the resulting beam span is within limits. Alternative: you could add a midspan support instead, or simply leave it in place if span limits are already tight. Executing now.",
  "tool_calls": [{{"name": "remove_element", "arguments": {{"element_id": "C4"}}}}]
}}

PERIMETER / NOT-ALLOWED ELEMENTS:
If the element type is "perimeter" or it defines the building envelope, do NOT call a tool.
Set action="final" and explain: why it can't be removed, what the structural risk is, and offer 2 concrete alternatives the architect can actually do (e.g. upgrade sections, add internal support, redesign the span).

ACTIONS:
- REMOVE any element: set action="tool", call remove_element with the exact element_id. Include advisory in final_response.
- ADD midspan column: set action="tool", call add_midspan_column with the beam_id. Include advisory in final_response.
- UPGRADE a section: set action="tool", call upgrade_element_section with element_id (and new_section if known). Include advisory in final_response.
- MOVE a column to clear a window/door clash or adjust spacing (e.g. "move C4 0.5 m to the right", "shift C3 left 0.4 m", "move C2 in x by -0.6"): set action="tool", call move_element with element_id and dx/dy in metres (east/north positive). Keep it to ONE axis (dx OR dy) so the grid stays orthogonal. Beams joined to the column follow automatically. Include advisory in final_response.
- ADD a column at a distance from a reference column (e.g. "add a column 2 m in x from C3", "put a column 1.5 m below C5"): set action="tool", call add_column with reference_id and dx/dy in metres (east/north positive; west/south negative). Measured along the axes from that column. Include advisory in final_response.
- ADD a beam between two columns (e.g. "add a beam between C3 and C5"): set action="tool", call add_beam with column_a and column_b. The two columns MUST share an X or a Y — beams are always orthogonal; never propose a diagonal beam. Include advisory in final_response.
- CHANGE MATERIAL (e.g. "switch to timber", "change material to concrete/RCC", "make it steel"): set action="tool", call set_material with {{"material": "RCC"|"STEEL"|"TIMBER"}}. To scope it, add "level" (e.g. "level_02") and/or "element_type" ("column" or "beam") — e.g. "change all columns and beams of level 2 to timber" → {{"material":"TIMBER","level":"level_02"}}. Do NOT use upgrade_element_section for material changes.
- GENERATE structural grid: set action="tool", call tag_and_audit. Include advisory in final_response.

ALWAYS include the real element_id from the layout context in tool_calls. Never emit a tool call with an empty or placeholder element_id — if you don't know the id, ask for it in final_response with action="final".

EVALUATION (user asks to evaluate, check structure, run analysis, run loads):
Set action="final", final_response="" (empty string). The evaluation runs automatically.

QUESTIONS (explain results, describe layout, interpret failures, cost/weight, which option):
Set action="final" and write a clear, concise answer (1-3 sentences) in final_response.
Use element IDs and values from the layout context. Never invent IDs.
When the Context "Metrics" section already contains the figures (cost, weight, cheapest/lightest
option, utilisation, pass/fail), STATE THEM DIRECTLY — e.g. "Option 2 is cheaper at $2,134 vs
$2,160." NEVER answer with "we can analyse…", "I suggest evaluating…", "to determine… we need
to consider various factors", or any non-answer when the data is present in the Context.
Earlier turns are included for context — resolve follow-ups like "do so", "which is cheaper",
"why?" against them.

Toolbox:
{tool_catalog}

Return strictly valid JSON:
{{"action": "final" | "tool", "final_response": "...", "tool_calls": [{{"name": "<tool>", "arguments": {{...}}}}]}}
Rules: JSON only, no markdown. If action is final: tool_calls must be []. If action is tool: BOTH final_response AND tool_calls must be filled.
"""

_is_light = st.session_state.get("theme", "dark") == "light"

_t = theme_tokens(_is_light)
_BG=_t["BG"]; _SB=_t["SB"]; _CARD=_t["CARD"]; _ACC=_t["ACC"]; _ACC2=_t["ACC2"]; _BORD=_t["BORD"]; _TEXT=_t["TEXT"]; _MUT=_t["MUT"]; _DIM=_t["DIM"]; _FAIL=_t["FAIL"]; _PASS_C=_t["PASS_C"]; _PASS_BG=_t["PASS_BG"]; _FAIL_BG=_t["FAIL_BG"]; _CHAT_Q=_t["CHAT_Q"]
_CHAT_A=_t["CHAT_A"]; _NUM1_BG=_t["NUM1_BG"]; _NUM1_C=_t["NUM1_C"]; _NUM2_BG=_t["NUM2_BG"]; _NUM3_BG=_t["NUM3_BG"]; _HIGH_BG=_t["HIGH_BG"]; _HIGH_C=_t["HIGH_C"]; _MED_BG=_t["MED_BG"]; _MED_C=_t["MED_C"]; _LOW_BG=_t["LOW_BG"]; _LOW_C=_t["LOW_C"]; _LOAD_BG=_t["LOAD_BG"]; _SNAP_BG=_t["SNAP_BG"]; _F=_t["F"]
_CSS = build_css(_t)

st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

# ─── Launch gate: lightweight name + email (no password) ───────────────────────
# Gates the workspace until a name + email are entered; loads that user's saved work.
if not st.session_state.get("user_email"):
    _lg1, _lg2, _lg3 = st.columns([1, 1.25, 1])
    with _lg2:
        st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
        _active_logo = _logo_b64_light if _is_light else _logo_b64_dark
        if _active_logo:
            st.markdown(
                f'<img src="data:image/png;base64,{_active_logo}" '
                f'style="width:62%;max-height:120px;object-fit:contain;display:block;'
                f'margin:0 auto 6px">', unsafe_allow_html=True)
        st.markdown(
            "<div class='sb-brand' style='text-align:center'>PermanenceOS</div>"
            "<div class='sb-sub' style='text-align:center;margin-bottom:14px'>"
            "AI-Powered Structural Design</div>", unsafe_allow_html=True)
        with st.form("login_gate", clear_on_submit=False):
            _ln = st.text_input("Your name", placeholder="e.g. Rania Chihaoui")
            _le = st.text_input("Your email", placeholder="e.g. rania@studio.com")
            _lgo = st.form_submit_button("Continue  ▶", width="stretch", type="primary")
        if _lgo:
            if _ln.strip() and "@" in _le and "." in _le.split("@")[-1]:
                st.session_state.user_name  = _ln.strip()
                st.session_state.user_email = _le.strip()
                _load_user_store()           # restore this user's saved work
                st.rerun()
            else:
                st.error("Please enter your name and a valid email address.")
        st.markdown(
            f"<div style='text-align:center;font-size:.6rem;color:{_MUT};margin-top:10px'>"
            "Your work is saved per email and restored next time you sign in.</div>",
            unsafe_allow_html=True)
    st.stop()

# ─── JS bridge ────────────────────────────────────────────────────────────────
st.html(SELECTION_BRIDGE_JS, unsafe_allow_javascript=True, width="content")


# ─── layout data ──────────────────────────────────────────────────────────────
# currentLayout in session state is the authoritative source. Cross-session recovery
# is per-user via _load_user_store() (run at the launch gate), so we no longer recover
# from the shared working file (which could leak another user's layout).

layout_obj      = st.session_state.currentLayout or {}
_lid            = layout_obj.get("layoutId", "")
# NOTE: diff_baseline is set ONLY when a grid is generated or an option/recommendation
# is applied (see Generate Grid / Apply Option / agent handlers). We deliberately do
# NOT capture it from the raw uploaded layout — otherwise Diff would draw phantom
# "removed/added" ghosts before any grid exists.
_level_keys_now = get_level_keys(layout_obj) if layout_obj else ["level_01"]
if st.session_state.get("active_level") not in (_level_keys_now + ["__ALL__"]):
    st.session_state.active_level = _level_keys_now[0] if _level_keys_now else "level_01"
n_cols, n_beams = _count_elements(layout_obj)
er              = st.session_state.eval_result
_sm             = (er or {}).get("summary", {})
_has_fail       = _sm.get("beam_failures", 0) > 0 or _sm.get("column_failures", 0) > 0
_mat_now        = st.session_state.material
_sdl_now        = st.session_state.sdl_kNm2
_ll_now         = st.session_state.live_load_kNm2

_S = AppState(
    tokens=_t,
    fns={
        "push_version": _push_version,
        "run_evaluate": _run_evaluate,
        "run_grid_options": _run_grid_options,
        "get_failure_alternatives": _get_failure_alternatives,
        "grid_option_kpis": _grid_option_kpis,
        "grid_option_description": _grid_option_description,
        "normalize_layout": _normalize_layout,
        "strip_structure": _strip_structure,
        "write_json": _write_json,
        "sync_viewers": _sync_viewers,
        "sheet_pdf_bytes": _sheet_pdf_bytes,
        "count_elements": _count_elements,
        "materials_present": _materials_present,
        "is_multilevel": is_multilevel,
        "get_level_count": get_level_count,
        "llm_is_reachable": _llm_is_reachable,
        "clear_user_store": _clear_user_store,
    },
    is_light=_is_light, layout_obj=layout_obj, eval_result=er, lid=_lid,
    n_cols=n_cols, n_beams=n_beams, has_fail=_has_fail, mat_now=_mat_now,
    sdl_now=_sdl_now, ll_now=_ll_now,
    logo_light=_logo_b64_light, logo_dark=_logo_b64_dark,
    edited_layout_path=EDITED_LAYOUT_PATH, repo_root=REPO_ROOT,
    user_name=st.session_state.get("user_name", ""),
    user_email=st.session_state.get("user_email", ""),
)

# ─── agent drawer: process query + inject global slide-out panel ───────────────
if _aq_raw.strip():
    st.query_params["_aq"] = ""
    _aq_resp = _run_agent_chat(_aq_raw, layout_obj, er)
    if _aq_resp.startswith("APPLY_TOOL:"):
        try:
            _aq_td = json.loads(_aq_resp[len("APPLY_TOOL:"):])
            _aq_tn, _aq_ti = _aq_td.get("name", ""), _aq_td.get("input", {})
            if _aq_tn == "remove_element":
                from nodes.modify import remove_element as _aq_rem
                _aq_eid = _aq_ti.get("element_id", "")
                if _aq_eid:
                    _aq_nl = json.loads(_aq_rem(json.dumps(layout_obj), _aq_eid, bool(_aq_ti.get("force"))))
                    if find_element_in_layout(_aq_nl, _aq_eid)[1] is not None:
                        _aq_resp = f"**{_aq_eid}** is a perimeter element (locked). Say 'force remove {_aq_eid}' to override."
                    else:
                        _push_version(_aq_nl)
                        _aq_resp = f"Removed **{_aq_eid}** from the layout."
            elif _aq_tn == "add_midspan_column":
                from nodes.modify import add_midspan_column as _aq_amc
                _aq_bid = _aq_ti.get("beam_id", "") or _aq_ti.get("element_id", "")
                if _aq_bid:
                    _push_version(json.loads(_aq_amc(json.dumps(layout_obj), _aq_bid, _mat_now)))
                    _aq_resp = f"Added midspan column to **{_aq_bid}**."
            elif _aq_tn == "upgrade_element_section":
                from nodes.modify import upgrade_element_section as _aq_ups
                _aq_uid = _aq_ti.get("element_id", "")
                if _aq_uid:
                    _push_version(json.loads(_aq_ups(json.dumps(layout_obj), _aq_uid,
                                                     _aq_ti.get("new_section", "") or _aq_ti.get("value", ""))))
                    _aq_resp = f"Upgraded section of **{_aq_uid}**."
            elif _aq_tn == "move_element":
                from nodes.modify import move_element as _aq_mv
                _aq_mid = _aq_ti.get("element_id", "")
                if _aq_mid:
                    _push_version(json.loads(_aq_mv(
                        json.dumps(layout_obj), _aq_mid,
                        float(_aq_ti.get("dx") or 0.0), float(_aq_ti.get("dy") or 0.0),
                        _aq_ti.get("x"), _aq_ti.get("y"))))
                    st.session_state.eval_result = None
                    _aq_resp = f"Moved **{_aq_mid}**. Run analysis to confirm it still holds."
            elif _aq_tn == "add_column":
                from nodes.modify import add_column_at_offset as _aq_addc
                _aq_ref = _aq_ti.get("reference_id", "")
                if _aq_ref:
                    _push_version(json.loads(_aq_addc(
                        json.dumps(layout_obj), _aq_ref,
                        float(_aq_ti.get("dx") or 0.0), float(_aq_ti.get("dy") or 0.0), _mat_now)))
                    st.session_state.eval_result = None
                    _aq_resp = f"Added a column offset from **{_aq_ref}**. Connect it with a beam, then run analysis."
            elif _aq_tn == "add_beam":
                from nodes.modify import add_beam as _aq_addb
                _aq_ca, _aq_cb = _aq_ti.get("column_a", ""), _aq_ti.get("column_b", "")
                if _aq_ca and _aq_cb:
                    _aq_bl = json.loads(_aq_addb(json.dumps(layout_obj), _aq_ca, _aq_cb, None, _mat_now))
                    if _count_elements(_aq_bl) != _count_elements(layout_obj):
                        _push_version(_aq_bl)
                        st.session_state.eval_result = None
                        _aq_resp = f"Added a beam between **{_aq_ca}** and **{_aq_cb}**."
                    else:
                        _aq_resp = (f"Can't add a beam between **{_aq_ca}** and **{_aq_cb}** — they must "
                                    "share an X or a Y (no diagonal beams).")
        except Exception as _aq_tex:
            _aq_resp = f"Tool execution failed: {_aq_tex}"
    elif _aq_resp.startswith("APPLY_MATERIAL:"):
        try:
            from nodes.modify import apply_material_override
            _aqp = _aq_resp[len("APPLY_MATERIAL:"):].split("|")
            _aq_mt = (_aqp[0].strip() or _mat_now).upper()
            _aq_lvl = _aqp[1].strip() if len(_aqp) > 1 else ""
            _aq_et  = _aqp[2].strip() if len(_aqp) > 2 else ""
            _push_version(json.loads(apply_material_override(
                json.dumps(layout_obj), _aq_mt, level=_aq_lvl or None, element_type=_aq_et or None)))
            _aq_resp = f"Switched **{_aq_mt}**" + (f" ({_aq_et or 'all'} of {_aq_lvl})" if _aq_lvl else "") + ". Run analysis to check it."
        except Exception as _aqme:
            _aq_resp = f"Material switch failed: {_aqme}"
    elif _aq_resp in ("GENERATE_GRID", "EVALUATE", "FIX_FAILING") or _aq_resp.startswith("GENERATE_GRID"):
        _aq_resp = "Use the sidebar **AI Agent** chat to run that action."
    st.session_state.history.append({"prompt": _aq_raw, "response": _aq_resp})


_drawer_history_html = ""
for _dh in st.session_state.get("history", [])[-3:]:
    _dq = str(_dh.get("prompt", "")).replace("<", "&lt;").replace(">", "&gt;")
    _da = str(_dh.get("response", "")).replace("<", "&lt;").replace(">", "&gt;")
    _drawer_history_html += f'<div class="dq">You: {_dq}</div><div>{_da}</div>'
_hist_js = json.dumps(_drawer_history_html)

st.html(agent_drawer_html(_is_light, _hist_js), unsafe_allow_javascript=True, width="content")

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
prompt_input, submitted = render_sidebar(_S)

# ─── Agent processing ─────────────────────────────────────────────────────────
if submitted and prompt_input.strip():
    with st.spinner("Agent reasoning…"):
        _resp = _run_agent_chat(prompt_input.strip(), layout_obj, er)

    if _resp == "GENERATE_GRID" or _resp.startswith("GENERATE_GRID\n"):
        _gen_advisory = _resp[len("GENERATE_GRID"):].strip()
        with st.spinner("Generating structural grid options…"):
            st.session_state.grid_options = _run_grid_options(layout_obj, _mat_now)
        # Auto-apply option 1 to the working layout
        if st.session_state.grid_options:
            _ag_opt = st.session_state.grid_options[0].get("layout", {})
            if _ag_opt:
                _push_version(_ag_opt)
                st.session_state.diff_baseline = json.loads(json.dumps(_ag_opt))
                st.session_state["selected_opt_bar_idx"] = 0
        _resp = (f"{_gen_advisory}\n\n" if _gen_advisory else "") + f"Generated {len(st.session_state.grid_options)} grid option(s). Option 1 applied."
    elif _resp.startswith("APPLY_TOOL:"):
        try:
            _td = json.loads(_resp[len("APPLY_TOOL:"):])
            _tn, _ti = _td.get("name", ""), _td.get("input", {})
            _advisory_txt = _td.get("advisory", "")
            if _tn == "remove_element":
                from nodes.modify import remove_element as _rem_el
                _eid = _ti.get("element_id", "")
                _frc = bool(_ti.get("force"))
                if _eid:
                    _new_l = json.loads(_rem_el(json.dumps(layout_obj), _eid, _frc))
                    if find_element_in_layout(_new_l, _eid)[1] is not None:
                        # removal was blocked (perimeter / envelope lock)
                        _resp = (f"{_advisory_txt}\n\n" if _advisory_txt else "") + (
                            f"**{_eid}** is a perimeter element that defines the building "
                            f"envelope, so I left it in place — removing it risks the structure. "
                            f"Say **force remove {_eid}** if you want me to delete it anyway.")
                    else:
                        _push_version(_new_l)
                        _resp = (f"{_advisory_txt}\n\n" if _advisory_txt else "") + f"Removed **{_eid}** from the layout."
            elif _tn == "add_midspan_column":
                from nodes.modify import add_midspan_column as _amc
                _bid = _ti.get("beam_id", "") or _ti.get("element_id", "")
                if _bid:
                    _push_version(json.loads(_amc(json.dumps(layout_obj), _bid, _mat_now)))
                    _resp = (f"{_advisory_txt}\n\n" if _advisory_txt else "") + f"Added midspan column to **{_bid}**."
            elif _tn == "upgrade_element_section":
                from nodes.modify import upgrade_element_section as _ups
                _uid = _ti.get("element_id", "")
                _usec = _ti.get("new_section", "") or _ti.get("value", "")
                if _uid:
                    _push_version(json.loads(_ups(json.dumps(layout_obj), _uid, _usec)))
                    _resp = (f"{_advisory_txt}\n\n" if _advisory_txt else "") + f"Upgraded section of **{_uid}**."
            elif _tn == "move_element":
                from nodes.modify import move_element as _mv_el
                _mid = _ti.get("element_id", "")
                if _mid:
                    _mdx = float(_ti.get("dx") or 0.0)
                    _mdy = float(_ti.get("dy") or 0.0)
                    _mx  = _ti.get("x")
                    _my  = _ti.get("y")
                    _moved_l = json.loads(_mv_el(json.dumps(layout_obj), _mid, _mdx, _mdy,
                                                 _mx if _mx is not None else None,
                                                 _my if _my is not None else None))
                    _push_version(_moved_l)
                    st.session_state.eval_result = None  # geometry changed → re-run analysis
                    _where = (f"to ({float(_mx):g}, {float(_my):g}) m"
                              if (_mx is not None or _my is not None)
                              else f"by ({_mdx:+g}, {_mdy:+g}) m")
                    _resp = ((f"{_advisory_txt}\n\n" if _advisory_txt else "")
                             + f"Moved **{_mid}** {_where}. Re-run analysis to confirm it still holds.")
            elif _tn == "add_column":
                from nodes.modify import add_column_at_offset as _add_col
                import re as _re_lk
                def _parse_level_kw(text: str) -> str:
                    m = _re_lk.search(r'level[_ ]?0*(\d+)', text.lower())
                    return f"level_{int(m.group(1)):02d}" if m else ""
                _rid_c = _ti.get("reference_id", "") or _ti.get("element_id", "")
                if _rid_c:
                    _cdx = float(_ti.get("dx") or 0.0)
                    _cdy = float(_ti.get("dy") or 0.0)
                    _col_lk = (_ti.get("level_key") or _ti.get("level") or
                               _parse_level_kw(prompt))
                    _new_l = json.loads(_add_col(json.dumps(layout_obj), _rid_c,
                                                 _cdx, _cdy, _col_lk, _mat_now))
                    if _count_elements(_new_l) != _count_elements(layout_obj):
                        _push_version(_new_l)
                        _status = _auto_eval_after_change(_new_l)
                        _on_lk = f" on **{_col_lk}**" if _col_lk else ""
                        _resp = ((f"{_advisory_txt}\n\n" if _advisory_txt else "")
                                 + f"Added a column at ({_cdx:+g}, {_cdy:+g}) m from **{_rid_c}**{_on_lk} — {_status}. "
                                 "Note: a free-standing column carries no load until a **beam sits on it** — "
                                 "to actually fix a failing beam, put the column under it "
                                 "(*\"add a midspan column on <beam>\"*) or connect it (*\"add a beam between …\"*).")
                    else:
                        _resp = f"Couldn't add the column — **{_rid_c}** not found."
            elif _tn == "add_beam":
                from nodes.modify import add_beam as _add_beam
                import re as _re_lk2
                def _parse_level_kw2(text: str) -> str:
                    m = _re_lk2.search(r'level[_ ]?0*(\d+)', text.lower())
                    return f"level_{int(m.group(1)):02d}" if m else ""
                _ca, _cb = _ti.get("column_a", ""), _ti.get("column_b", "")
                if _ca and _cb:
                    _beam_lk = (_ti.get("level_key") or _ti.get("level") or
                                _parse_level_kw2(prompt))
                    _new_l = json.loads(_add_beam(json.dumps(layout_obj), _ca, _cb,
                                                  _beam_lk or None, _mat_now))
                    if _count_elements(_new_l) != _count_elements(layout_obj):
                        _push_version(_new_l)
                        _status = _auto_eval_after_change(_new_l)
                        _on_lk2 = f" on **{_beam_lk}**" if _beam_lk else ""
                        _resp = ((f"{_advisory_txt}\n\n" if _advisory_txt else "")
                                 + f"Added a beam between **{_ca}** and **{_cb}**{_on_lk2} — {_status}.")
                    else:
                        _resp = (f"Couldn't add a beam between **{_ca}** and **{_cb}** — they must share "
                                 "an X or a Y (I never create diagonal beams). Pick two columns in the "
                                 "same row or column, or add an aligned column first.")
        except Exception as _tex:
            _resp = f"Tool execution failed: {_tex}"
            st.session_state["_last_error"] = f"APPLY_TOOL: {_tex}"
    elif _resp.startswith("APPLY_MATERIAL:"):
        _mparts = _resp[len("APPLY_MATERIAL:"):].split("|")
        _new_mat = (_mparts[0].strip() or _mat_now).upper()
        _m_lvl = _mparts[1].strip() if len(_mparts) > 1 else ""
        _m_et  = _mparts[2].strip() if len(_mparts) > 2 else ""
        try:
            from nodes.modify import apply_material_override
            _ls_m = apply_material_override(json.dumps(layout_obj), _new_mat,
                                            level=_m_lvl or None, element_type=_m_et or None)
            _push_version(json.loads(_ls_m))
            with st.spinner(f"Applying {_new_mat} and evaluating…"):
                _ev_m = _run_evaluate(_ls_m, sdl=_sdl_now, ll=_ll_now)
            if _ev_m:
                st.session_state.eval_result = _ev_m
                st.session_state.eval_alts   = _get_failure_alternatives(_ev_m, _new_mat)
            _sm_m = (_ev_m or {}).get("summary", {})
            _scope = (f" ({_m_et or 'all'} elements"
                      + (f" of {_m_lvl}" if _m_lvl else "") + ")") if (_m_lvl or _m_et) else " (whole structure)"
            _resp = (f"Switched **{_new_mat}**{_scope}. "
                     f"Result: {'PASS' if _sm_m.get('overall_PASS') else 'FAIL'} — "
                     f"{_sm_m.get('beam_failures', 0)} beam / {_sm_m.get('column_failures', 0)} column failures. "
                     f"Ask me to *fix the failing beams* if you'd like options.")
        except Exception as _mex:
            _resp = f"Material switch failed: {_mex}"
            st.session_state["_last_error"] = f"APPLY_MATERIAL: {_mex}"
    elif _resp == "FIX_FAILING":
        try:
            _ev_fix = st.session_state.eval_result or _run_evaluate(
                json.dumps(layout_obj), sdl=_sdl_now, ll=_ll_now)
            _alts_fix = _get_failure_alternatives(_ev_fix or {}, _mat_now)
            _auto_alt = next((a for a in _alts_fix
                              if "increase the" in a.lower() or "upgrade" in a.lower()),
                             (_alts_fix[0] if _alts_fix else None))
            if _auto_alt:
                _nl, _nev = _apply_alternative(_auto_alt, json.dumps(layout_obj),
                                               _mat_now, _sdl_now, _ll_now)
                if _nev:
                    _push_version(json.loads(_nl))
                    st.session_state.eval_result = _nev
                    st.session_state.eval_alts = _get_failure_alternatives(_nev, _mat_now)
                    _ns = _nev.get("summary", {})
                    _resp = (f"Applied an automatic fix. Now "
                             f"{'PASS' if _ns.get('overall_PASS') else 'FAIL'} — "
                             f"{_ns.get('beam_failures', 0)} beam / {_ns.get('column_failures', 0)} column failures.")
                else:
                    _resp = "Tried to auto-fix but evaluation did not return — try upgrading sections manually."
            else:
                _resp = "Nothing to fix — run analysis first, or there are no failing elements."
        except Exception as _fex:
            _resp = f"Auto-fix failed: {_fex}"
            st.session_state["_last_error"] = f"FIX_FAILING: {_fex}"
    elif _resp == "EVALUATE":
        # Evaluate as-is; only seed the global material when nothing is assigned yet
        # (never revert an applied timber/steel change).
        _any_mat_ag = any((e.get("attributes") or {}).get("material")
                          for _l, e in iter_all_structure(layout_obj))
        if _any_mat_ag:
            _ls_ag = json.dumps(layout_obj)
        else:
            from nodes.modify import apply_material_override
            _ls_ag = apply_material_override(json.dumps(layout_obj), _mat_now)
            _push_version(json.loads(_ls_ag))
        with st.spinner("Evaluating structure…"):
            _ev_ag = _run_evaluate(_ls_ag, sdl=_sdl_now, ll=_ll_now)
        if _ev_ag:
            st.session_state.eval_result = _ev_ag
            st.session_state.eval_alts   = _get_failure_alternatives(_ev_ag, _mat_now)
        _sag  = (_ev_ag or {}).get("summary", {})
        _resp = (
            f"Evaluation: {'PASS' if _sag.get('overall_PASS') else 'FAIL'} — "
            f"{_sag.get('beam_failures',0)} beam failure(s), "
            f"{_sag.get('column_failures',0)} column failure(s)."
        )

    st.session_state.output_log.append(_resp)
    st.session_state.history.append({"prompt": prompt_input, "response": _resp})
    st.session_state.state_history.append({
        "label":       prompt_input[:28] + ("…" if len(prompt_input) > 28 else ""),
        "layout_json": layout_obj,
        "eval_result": st.session_state.eval_result,
    })
    st.rerun()

# ─── Page header ──────────────────────────────────────────────────────────────
render_header(_S)

# ══════════════════════════════════════════════════════════════════════════════
# EMPTY STATE GATE — nothing renders until upload + OK
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("setupDone", False):
    st.markdown(
        f'<div style="display:flex;flex-direction:column;align-items:center;'
        f'justify-content:center;min-height:60vh;gap:16px;text-align:center">'
        f'<div style="font-size:2.5rem;opacity:.25">⬡</div>'
        f'<div style="font-size:1.1rem;font-weight:700;color:{_TEXT}">'
        f'No model loaded</div>'
        f'<div style="font-size:.82rem;color:{_MUT};max-width:320px;line-height:1.6">'
        f'Upload a JSON layout file in the sidebar, configure your loads and material, '
        f'then press <b>OK ▶ Apply & Render</b> to begin.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_mod, tab_cmp = st.tabs(["  MODIFY WORK PLACE  ", "  COMPARE WORK PLACE  "])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MODIFY
# ══════════════════════════════════════════════════════════════════════════════
with tab_mod:

    _er_done = er is not None
    _alts_ok = bool(st.session_state.eval_alts)
    _snap_ok = bool(st.session_state.snapshots)

    _steps = [
        ("1", "Upload",          "Model & Data",      True),
        ("2", "Define Loads",    "Set load cases",    True),
        ("3", "Evaluate",        "Run analysis",      _er_done),
        ("4", "Recommendations", "AI suggestions",    _alts_ok),
        ("5", "Apply Changes",   "Modify design",     _snap_ok),
        ("6", "Compare",         "Evaluate options",  False),
    ]
    _sbar_html = '<div class="step-bar">'
    for _si, (_sn, _sl, _ss, _sdone) in enumerate(_steps):
        _cls = "stp-done" if _sdone else (
            "stp-active" if (_si == 2 and not _er_done) else "stp-todo")
        _sbar_html += (
            f'<div class="stp {_cls}">'
            f'<span class="stp-n">{_sn}</span>'
            f'<div><div class="stp-lbl">{_sl}</div>'
            f'<div class="stp-sub">{_ss}</div></div></div>'
        )
        if _si < len(_steps) - 1:
            _sbar_html += '<span class="stp-arr">›</span>'
    _sbar_html += '</div>'

    # Step bar in main area; Run Analysis + Save Snapshot aligned to right panel.
    # Proportions match the main/right column split below (2.1 : 0.55).
    _sb_col, _btn_area = st.columns([2.1, 0.55], gap="small")
    with _sb_col:
        st.markdown(_sbar_html, unsafe_allow_html=True)
    with _btn_area:
        _run_col, _snap_col = st.columns([1, 1], gap="small")
        with _run_col:
            _run_clicked = st.button(
                "▶  Run Analysis",
                type="primary", width="stretch", key="btn_run_analysis",
                disabled=not st.session_state.get("setupDone", False),
            )
        with _snap_col:
            _sn_n = len(st.session_state.snapshots) + 1
            _snap_clicked = st.button(
                f"Snapshot #{_sn_n}", key="btn_snap", width="stretch",
            )

    if _snap_clicked:
        st.session_state.snapshots.append({
            "label":            f"Option {_sn_n}",
            "layout_json":      json.dumps(layout_obj),
            "eval_result":      er,
            "cost_flexibility": st.session_state.cost_flexibility,
            "before_json":      json.dumps(
                                    st.session_state.versionHistory[-1]
                                    if st.session_state.get("versionHistory")
                                    else layout_obj
                                ),
        })
        _save_user_store()   # persist snapshots to the user's saved work
        st.rerun()

    if _run_clicked:
        _struct_els = get_structure(layout_obj)
        if not _struct_els:
            st.warning(
                "No structural elements found. "
                "Generate a structural grid first using the Agent or the Generate Grid button.",
                icon="⚠️",
            )
        else:
            # Remember which option is active BEFORE any _push_version (which resets it),
            # so Run Analysis keeps the user's chosen option active (e.g. Option 3).
            _oi_keep = st.session_state.get("selected_opt_bar_idx", -1)
            # Only seed the global material when NO element has a material yet
            # (fresh grid). If timber/steel/etc. was already applied, evaluate the
            # layout AS-IS so Run Analysis never reverts an applied material change.
            _any_mat = any((e.get("attributes") or {}).get("material")
                           for _l, e in iter_all_structure(layout_obj))
            if _any_mat:
                _ls2 = json.dumps(layout_obj)
            else:
                from nodes.modify import apply_material_override
                _ls2 = apply_material_override(json.dumps(layout_obj), _mat_now)
                _seeded = json.loads(_ls2)
                _push_version(_seeded)
                # Keep diff_baseline in sync: if it was un-seeded, updating it here
                # prevents ALL elements from appearing "changed" in the diff view.
                st.session_state.diff_baseline = json.loads(json.dumps(_seeded))
            with st.spinner("Evaluating structure…"):
                _ev2 = _run_evaluate(_ls2, sdl=_sdl_now, ll=_ll_now)
            if _ev2:
                st.session_state.eval_result = _ev2
                st.session_state.eval_alts   = _get_failure_alternatives(_ev2, _mat_now)
                # Attach the evaluation to the option that was active before analysis,
                # and keep that option active (don't snap back to Option 1).
                _gopts_run = st.session_state.grid_options
                if 0 <= _oi_keep < len(_gopts_run):
                    st.session_state.grid_options[_oi_keep]["evaluation"] = _ev2
                    st.session_state["selected_opt_bar_idx"] = _oi_keep
                elif _gopts_run:
                    st.session_state.grid_options[0]["evaluation"] = _ev2
                    st.session_state["selected_opt_bar_idx"] = 0
                _ev2_sm = _ev2.get("summary", {})
                _ev2_pass = _ev2_sm.get("overall_PASS")
                _ev2_bf   = _ev2_sm.get("beam_failures", 0)
                _ev2_cf   = _ev2_sm.get("column_failures", 0)
                _ev2_sc   = _ev2_sm.get("score")
                _ev2_icon = "✅" if _ev2_pass else "❌"
                _ev2_lbl  = "PASS" if _ev2_pass else "FAIL"
                st.markdown(
                    f'<div style="background:{"rgba(40,180,100,0.12)" if _ev2_pass else "rgba(200,40,40,0.12)"};'
                    f'border:1px solid {"#40d090" if _ev2_pass else "#ff5050"};'
                    f'border-radius:8px;padding:10px 14px;margin:6px 0;font-family:{_F}">'
                    f'<span style="font-size:1.1rem;font-weight:800;color:{"#40d090" if _ev2_pass else "#ff5050"}">'
                    f'{_ev2_icon} {_ev2_lbl}</span>'
                    f'<span style="font-size:.75rem;color:{_MUT};margin-left:10px">'
                    f'{_ev2_bf} beam fail · {_ev2_cf} col fail'
                    f'{f" · score {_ev2_sc:.0f}/100" if _ev2_sc is not None else ""}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )
            st.rerun()

    # ── Toolbar + viewer ─────────────────────────────────────────────────────
    _vm = st.session_state.get("view_mode", "2D")

    _snaps = st.session_state.snapshots
    if _snaps:
        _pills = "".join(
            f'<span class="snap-pill{" snap-pill-active" if i==len(_snaps)-1 else ""}">'
            f'{s["label"]}</span>'
            for i, s in enumerate(_snaps)
        )
        st.markdown(_pills, unsafe_allow_html=True)

    # currentLayout is always authoritative — _push_version keeps it in sync
    # with EDITED_LAYOUT_PATH, so both viewers always read the same data.
    _plan_layout = layout_obj

    # ── Preview (non-committal) — render a recommendation's result without saving ─
    _preview_active = False
    _preview_alt = st.session_state.get("preview_alt")
    if _preview_alt:
        try:
            _pv_ls, _pv_ev = _apply_alternative(
                _preview_alt, json.dumps(layout_obj), _mat_now, _sdl_now, _ll_now,
            )
            _plan_layout = json.loads(_pv_ls)
            if _pv_ev:
                er = _pv_ev
            _preview_active = True
        except Exception:
            st.session_state["preview_alt"] = None

    # ── Main: floor plan | right panel ───────────────────────────────────────
    _main_col, _right_col = st.columns([2.1, 0.55], gap="small")

    with _main_col:
        if _preview_active:
            _pvb1, _pvb2, _pvb3 = st.columns([3, 1, 1], gap="small")
            with _pvb1:
                st.markdown(
                    f'<div style="background:{_MED_BG};color:{_MED_C};border:1px solid {_MED_C};'
                    f'border-radius:6px;padding:6px 10px;font-size:.68rem;font-weight:700">'
                    f'👁 Previewing a recommendation — not applied yet.</div>',
                    unsafe_allow_html=True,
                )
            with _pvb2:
                if st.button("✓ Apply", key="preview_apply", type="primary", width="stretch"):
                    _push_version(_plan_layout)
                    st.session_state.eval_result = er
                    st.session_state.eval_alts = _get_failure_alternatives(er or {}, _mat_now)
                    st.session_state["preview_alt"] = None
                    st.rerun()
            with _pvb3:
                if st.button("✕ Cancel", key="preview_cancel", width="stretch"):
                    st.session_state["preview_alt"] = None
                    st.rerun()
        # Native toolbar (replaces the in-iframe JS bridge toolbar)
        _is_ml = is_multilevel(_plan_layout)
        _tb_cols = ([0.55, 1.1, 0.7, 0.6, 0.85, 1.0, 2.2] if _is_ml
                    else [0.55, 0.7, 0.6, 0.85, 1.0, 2.8])
        _tb = st.columns(_tb_cols, gap="small")
        _tb1 = _tb[0]
        _tb_lvl = _tb[1] if _is_ml else None
        _tb2 = _tb[2] if _is_ml else _tb[1]
        _tb3 = _tb[3] if _is_ml else _tb[2]
        _tb4 = _tb[4] if _is_ml else _tb[3]
        _tb5 = _tb[5] if _is_ml else _tb[4]
        with _tb1:
            if st.button("3D" if _vm == "2D" else "2D",
                         key="tb_vm_btn", width="stretch"):
                st.session_state["view_mode"] = "3D" if _vm == "2D" else "2D"
                st.rerun()
        if _is_ml and _tb_lvl is not None:
            with _tb_lvl:
                _lvl_keys = get_level_keys(_plan_layout)
                _lvl_opts = _lvl_keys + ["All levels"]
                _cur_lvl = ("All levels" if st.session_state.active_level == "__ALL__"
                            else st.session_state.active_level)
                _lvl_idx = _lvl_opts.index(_cur_lvl) if _cur_lvl in _lvl_opts else 0
                _new_level = st.selectbox(
                    "Level",
                    _lvl_opts,
                    index=_lvl_idx,
                    format_func=lambda x: ("Show all levels" if x == "All levels" else x),
                    label_visibility="collapsed",
                    key="tb_active_level",
                )
                _new_level = "__ALL__" if _new_level == "All levels" else _new_level
                if _new_level != st.session_state.active_level:
                    st.session_state.active_level = _new_level
        with _tb2:
            _new_lab = st.toggle("Labels", value=st.session_state.labels_on,
                                 key="tb_lab_tog")
            if _new_lab != st.session_state.labels_on:
                st.session_state.labels_on = _new_lab
        with _tb3:
            _new_diff = st.toggle("Diff", value=st.session_state.compare_mode,
                                  key="tb_diff_tog")
            if _new_diff != st.session_state.compare_mode:
                st.session_state.compare_mode = _new_diff
        with _tb4:
            _new_foot = st.toggle("Footings", value=st.session_state.footings_on,
                                  key="tb_foot_tog",
                                  help="Show foundation footing boxes under ground-floor columns (3D).")
            if _new_foot != st.session_state.footings_on:
                st.session_state.footings_on = _new_foot
        with _tb5:
            _new_conf = st.toggle("Conflicts", value=st.session_state.show_conflicts,
                                  key="tb_conf_tog",
                                  help="Highlight columns/beams that clash with a window or door (magenta). Off by default.")
            if _new_conf != st.session_state.show_conflicts:
                st.session_state.show_conflicts = _new_conf

        # If the active level has no structure yet, say so (explains "switching level
        # shows nothing" before a grid is generated on that level).
        _al_now = st.session_state.active_level
        if _al_now != "__ALL__" and not get_structure(_plan_layout, _al_now):
            st.markdown(
                f'<div style="font-size:.62rem;color:{_MUT};margin:2px 0 4px">'
                f'<b>{_al_now}</b> has no structural elements yet — generate a grid to populate it.</div>',
                unsafe_allow_html=True,
            )

        # ── Structure ↔ opening (window/door) clash detection ──
        # Only computed/shown when the "Conflicts" toggle is on (magenta off by default).
        _clash_ids = set()
        if st.session_state.get("show_conflicts", False):
            if _al_now == "__ALL__":
                for _lk in get_level_keys(_plan_layout):
                    _clash_ids |= _opening_clashes(_plan_layout, _lk)
            else:
                _clash_ids = _opening_clashes(_plan_layout, _al_now)
        if _clash_ids:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:6px;margin:6px 0 0;'
                f'font-size:.62rem;color:{_FAIL}">'
                f'<span style="width:10px;height:10px;border-radius:2px;background:#ff3df0;'
                f'display:inline-block"></span>'
                f'<b>⚠ {len(_clash_ids)} element(s) clash with a window/door</b>'
                f'<span style="color:{_MUT}"> (magenta) — adjust the grid spacing or move the opening.</span></div>',
                unsafe_allow_html=True,
            )

        # Diff compares the live layout against the baseline (the applied grid/option),
        # so it shows everything you've changed since — not just the last edit.
        _before_lay = (st.session_state.get("diff_baseline")
                       if st.session_state.compare_mode else None)
        if st.session_state.compare_mode:
            if _before_lay:
                _da, _dr, _dm = (("#1a8050", "#cc2020", "#7c4dff") if _is_light
                                 else ("#40d090", "#ff5050", "#9b7cff"))
                st.markdown(
                    f'<div style="display:flex;gap:14px;align-items:center;margin:2px 0 6px;'
                    f'font-size:.60rem;color:{_MUT}">'
                    f'<span style="font-weight:700;text-transform:uppercase;letter-spacing:.5px">vs Baseline grid</span>'
                    f'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:{_da};display:inline-block"></span>Added</span>'
                    f'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:{_dr};display:inline-block"></span>Removed</span>'
                    f'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:{_dm};display:inline-block"></span>Changed</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="font-size:.60rem;color:{_MUT};margin:2px 0 6px">'
                    f'Diff on — generate or apply a grid first to set the baseline.</div>',
                    unsafe_allow_html=True,
                )
        if _vm == "2D":
            _fig2d = _render_floor_plan_plotly(
                _plan_layout, eval_result=er,
                highlight=st.session_state.selected_el,
                level_key=st.session_state.active_level,
                labels=st.session_state.labels_on,
                height_px=510, is_light=_is_light,
                diff_on=st.session_state.compare_mode,
                before_layout=_before_lay,
                revision=st.session_state.get("currentVersion", 0),
                clash_ids=_clash_ids,
            )
            _sel_ev = st.plotly_chart(
                _fig2d, on_select="rerun",
                width="stretch",
                selection_mode=("points",),
                config=dict(
                    scrollZoom=True, displaylogo=False,
                    modeBarButtonsToRemove=["lasso2d", "select2d",
                                            "zoomIn2d", "zoomOut2d",
                                            "autoScale2d"],
                ),
                key="floor_plan_plotly",
            )
            # Handle element selection from click.
            # Streamlit's on_select returns dict-like point objects.
            if _sel_ev and _sel_ev.selection and _sel_ev.selection.points:
                try:
                    _new_sel = ""
                    _lvl_changed = False
                    for _pt in _sel_ev.selection.points:
                        # Support both attribute-style and dict-style access.
                        _cd = (
                            _pt.get("customdata") if isinstance(_pt, dict)
                            else getattr(_pt, "customdata", None)
                        )
                        if not _cd:
                            continue
                        if isinstance(_cd, (list, tuple)):
                            _cand = str(_cd[0]) if _cd else ""
                            _kind = str(_cd[1]).lower() if len(_cd) > 1 else ""
                            _lvl = str(_cd[2]) if len(_cd) > 2 else ""
                            if _cand and (_kind in ("beam", "column") or not _kind):
                                _new_sel = _cand
                                if _lvl and _lvl != st.session_state.get("active_element_level", ""):
                                    _lvl_changed = True
                                if _lvl:
                                    st.session_state.active_element_level = _lvl
                                    st.session_state.active_level = _lvl
                                break
                        else:
                            _new_sel = str(_cd)
                            break
                    if _new_sel and (
                        _new_sel != st.session_state.selected_el
                        or _lvl_changed
                    ):
                        st.session_state.selected_el = _new_sel
                        st.rerun()
                except Exception:
                    pass
        else:
            components.html(
                _render_3d_viewport(
                    _plan_layout,
                    eval_result=er,
                    selected_el=st.session_state.selected_el,
                    active_level=st.session_state.active_level,
                    is_light=_is_light,
                    height=512,
                    before_layout=_before_lay,
                    labels=st.session_state.labels_on,
                    footings=st.session_state.footings_on,
                    show_conflicts=st.session_state.show_conflicts,
                ),
                height=520,
                scrolling=False,
            )

        st.markdown(
            '<div class="plan-legend">'
            '<span class="leg-item"><span class="leg-col"></span>Columns</span>'
            '<span class="leg-item"><span class="leg-beam"></span>Beams</span>'
            '<span class="leg-item"><span class="leg-wall"></span>Walls</span>'
            '<span class="leg-item"><span class="leg-dash"></span>Load Path</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        _mat_leg = _material_legend_html(_plan_layout, _is_light, _MUT)
        if _mat_leg:
            st.markdown(_mat_leg, unsafe_allow_html=True)

        _mdef  = _sm.get("max_defl_mm", None)
        _tw    = _sm.get("total_weight_kN", None)
        _bf_sb = _sm.get("beam_failures", 0)
        _cf_sb = _sm.get("column_failures", 0)
        if er and _sm.get("overall_PASS"):
            _anlys = '<span class="sb-pass">✓ Analysis Complete</span>'
        elif er:
            _anlys = '<span class="sb-fail">✗ Analysis Failed</span>'
        else:
            _anlys = '<span class="sb-pend">Not analysed</span>'

        st.markdown(
            f'<div class="stat-bar">'
            f'<span class="sb-i">Nodes <b>{n_cols}</b></span>'
            f'<span class="sb-i">Beams <b>{n_beams}</b></span>'
            f'<span class="sb-i">Columns <b>{n_cols}</b></span>'
            + (f'<span class="sb-i">Weight <b>{_tw:.1f}</b> kN</span>' if _tw else "")
            + (f'<span class="sb-i">Max Defl <b>{_mdef:.1f}</b> mm</span>' if _mdef else "")
            + f'<span class="sb-i">Beam fail <b>{_bf_sb}</b></span>'
            f'<span class="sb-i">Col fail <b>{_cf_sb}</b></span>'
            f'{_anlys}</div>',
            unsafe_allow_html=True,
        )

    with _right_col:
        _rt1, _rt2 = st.tabs(["  ANALYSIS  ", "  DESIGN DETAILS  "])

        with _rt1:
            # Transparency: after an auto-upgrade fix, show exactly what was resized.
            _fix_log = st.session_state.get("_last_fix_log")
            if _fix_log:
                _fix_rows = "".join(
                    f'<div style="font-size:.62rem;color:{_TEXT};line-height:1.6">'
                    f'<b>{r["id"]}</b> ({r["kind"]}): {r["from"]} → <b>{r["to"]}</b>'
                    f' <span style="color:{_MUT}">· governed by {r["gov"]}</span></div>'
                    for r in _fix_log[:30]
                )
                st.markdown(
                    f'<div style="background:{_PASS_BG};border:1px solid {_PASS_C};border-radius:8px;'
                    f'padding:8px 10px;margin-bottom:8px">'
                    f'<div style="font-size:.64rem;font-weight:700;color:{_PASS_C};margin-bottom:4px">'
                    f'✓ Auto-upgrade applied — {len(_fix_log)} element(s) resized to the next passing section</div>'
                    f'{_fix_rows}</div>',
                    unsafe_allow_html=True,
                )
                st.session_state["_last_fix_log"] = None

            _sel_opt_i2 = st.session_state.get("selected_opt_bar_idx", -1)
            _gopts_main = st.session_state.grid_options

            if not _gopts_main:
                st.markdown(
                    f'<div style="font-size:.70rem;color:{_MUT};padding:8px 2px;line-height:1.6">'
                    f'Click <b>Generate Grid</b> in the sidebar, then select an option '
                    f'to view structural analysis.</div>',
                    unsafe_allow_html=True,
                )
            elif _sel_opt_i2 < 0:
                st.markdown(
                    f'<div style="font-size:.70rem;color:{_MUT};padding:8px 2px;line-height:1.6">'
                    f'Select <b>Option 1</b>, <b>2</b> or <b>3</b> in the sidebar '
                    f'to view its structural analysis here.</div>',
                    unsafe_allow_html=True,
                )
            else:
                _sel_gopt = _gopts_main[_sel_opt_i2]
                _sel_ev   = _sel_gopt.get("evaluation") or {}
                _sel_sm   = _sel_ev.get("summary", {})
                _sel_pass = _sel_sm.get("overall_PASS")

                if not _sel_ev:
                    st.markdown(
                        f'<div style="font-size:.70rem;color:{_MUT}">No analysis data yet.</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    _is_pass  = _sel_pass is True
                    _is_fail  = _sel_pass is False
                    _res_clr  = _PASS_C if _is_pass else (_FAIL if _is_fail else _MUT)
                    _res_lbl  = "PASS" if _is_pass else ("FAIL" if _is_fail else "—")
                    _bf       = _sel_sm.get("beam_failures",   0)
                    _cf2      = _sel_sm.get("column_failures", 0)
                    _score    = _sel_sm.get("score",           None)
                    _mspan    = _sel_sm.get("max_beam_span_m", None)

                    def _stat(val, label):
                        return (
                            f'<div style="display:flex;flex-direction:column;gap:2px">'
                            f'<span style="font-size:1.5rem;font-weight:800;color:{_TEXT};line-height:1">{val}</span>'
                            f'<span style="font-size:.58rem;font-weight:700;color:{_MUT};'
                            f'letter-spacing:1px;text-transform:uppercase">{label}</span>'
                            f'</div>'
                        )

                    _score_html = _stat(f"{_score:.1f}" if _score is not None else "—", "Score / 100")
                    _mspan_html = (
                        f'<div style="font-size:.63rem;color:{_MUT};margin-top:6px">'
                        f'Max beam span: <b style="color:{_TEXT}">{_mspan:.2f} m</b></div>'
                        if _mspan else ""
                    )
                    st.markdown(
                        f'<div style="background:{_CARD};border:1px solid {_BORD};'
                        f'border-radius:10px;padding:16px 18px;margin:4px 0">'
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px">'
                        f'<div style="display:flex;flex-direction:column;gap:2px">'
                        f'<span style="font-size:1.7rem;font-weight:900;color:{_res_clr};line-height:1">{_res_lbl}</span>'
                        f'<span style="font-size:.58rem;font-weight:700;color:{_MUT};letter-spacing:1px;text-transform:uppercase">Overall</span>'
                        f'</div>'
                        f'{_score_html}'
                        f'</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                        f'{_stat(_bf, "Beam Failures")}'
                        f'{_stat(_cf2, "Column Failures")}'
                        f'</div>'
                        f'{_mspan_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # ── AI Recommendations ────────────────────────────────────────────
                    _alts_tab = st.session_state.eval_alts
                    if _alts_tab:
                        st.markdown(
                            f'<div class="panel-hdr" style="margin-top:16px;margin-bottom:6px">'
                            f'AI Recommendations</div>',
                            unsafe_allow_html=True,
                        )
                        # Cache metrics so re-runs don't re-evaluate 3x every time
                        _mck = tuple(_alts_tab[:3])
                        if st.session_state.get("_alt_mck") != _mck:
                            st.session_state["_alt_mck"] = _mck
                            st.session_state["_alt_mcache"] = [
                                _compute_alt_metrics(
                                    _a, layout_obj, er or {},
                                    _mat_now, _sdl_now, _ll_now,
                                )
                                for _a in _alts_tab[:3]
                            ]
                        _mcache = st.session_state.get("_alt_mcache", [])

                        def _metric_col(pct, label):
                            if pct is None:
                                clr, arrow, val = _MUT, "", "—"
                            else:
                                arrow = "↓" if pct < 0 else "↑"
                                clr   = _PASS_C if pct < 0 else _FAIL
                                val   = f"{abs(pct):.2f}%"
                            return (
                                f'<div style="flex:1;text-align:center">'
                                f'<div style="font-size:.58rem;color:{_MUT};'
                                f'font-weight:600;text-transform:uppercase;'
                                f'letter-spacing:.5px;margin-bottom:3px">{label}</div>'
                                f'<div style="font-size:.70rem;font-weight:700;'
                                f'color:{clr}">{arrow} {val}</div>'
                                f'</div>'
                            )

                        for _ri, _alt in enumerate(_alts_tab[:3]):
                            _nc = [_NUM1_BG, _NUM2_BG, _NUM3_BG][min(_ri, 2)]
                            _alt_lo = _alt.lower()
                            if ("recommended" in _alt_lo
                                    or _alt_lo.startswith("increase the")):
                                _icss, _ilbl = "imp-high", "HIGH IMPACT"
                            elif "upgrade all" in _alt_lo or "switch all" in _alt_lo:
                                _icss, _ilbl = "imp-high", "HIGH IMPACT"
                            elif ("add midspan" in _alt_lo or "add lateral" in _alt_lo
                                  or "add transfer" in _alt_lo
                                  or "add intermediate" in _alt_lo):
                                _icss, _ilbl = "imp-med", "MED IMPACT"
                            elif "upgrade " in _alt_lo:
                                _icss, _ilbl = "imp-med", "MED IMPACT"
                            else:
                                _icss, _ilbl = "imp-low", "LOW IMPACT"
                            if " — " in _alt:
                                _rt, _rd = _alt.split(" — ", 1)
                            elif " (" in _alt:
                                _rt = _alt.split(" (")[0]
                                _rd = "(" + _alt.split(" (", 1)[1]
                            else:
                                _rt, _rd = _alt, ""
                            _rt = _rt.strip(); _rd = _rd.strip()
                            _desc_html = (
                                f'<div style="font-size:.63rem;color:{_MUT};'
                                f'line-height:1.5;margin-top:6px">{_rd}</div>'
                                if _rd else ""
                            )
                            _m = _mcache[_ri] if _ri < len(_mcache) else {}
                            _metrics_html = (
                                f'<div style="display:flex;gap:4px;margin-top:10px;'
                                f'padding-top:8px;border-top:1px solid {_BORD}">'
                                + _metric_col(_m.get("weight_pct"), "Weight")
                                + _metric_col(_m.get("cost_pct"),   "Cost")
                                + _metric_col(_m.get("defl_pct"),   "Max Deflection")
                                + '</div>'
                            ) if _m else ""
                            st.markdown(
                                f'<div class="rec-card" style="margin-bottom:6px">'
                                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
                                f'<span class="rec-n" style="background:{_nc};flex-shrink:0">{_ri+1}</span>'
                                f'<span class="rec-title">{_rt}</span>'
                                f'<span class="{_icss}">{_ilbl}</span>'
                                f'</div>'
                                f'{_desc_html}'
                                f'{_metrics_html}'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            _bc1, _bc2 = st.columns(2)
                            with _bc1:
                                if st.button(
                                    "Preview", key=f"rec_prev_{_ri}",
                                    width="stretch",
                                ):
                                    st.session_state["preview_alt"] = _alt
                                    st.session_state.viewer_nonce += 1
                                    st.rerun()
                            with _bc2:
                                if st.button(
                                    "Apply Change", key=f"rec_apply_{_ri}",
                                    width="stretch", type="primary",
                                ):
                                    _new_ls, _new_ev = _apply_alternative(
                                        _alt, json.dumps(layout_obj),
                                        _mat_now, _sdl_now, _ll_now,
                                    )
                                    if _new_ev:
                                        _push_version(json.loads(_new_ls))
                                        st.session_state.eval_result = _new_ev
                                        st.session_state.eval_alts = _get_failure_alternatives(
                                            _new_ev, _mat_now
                                        )
                                        st.rerun()

            # ── Flexibility & alternatives (architect-facing advice) ──────────
            if er:
                _flex = _flexibility_rows(er)
                if _flex:
                    with st.expander("🧭  Flexibility & alternatives", expanded=False):
                        st.markdown(
                            f'<div style="font-size:.62rem;color:{_MUT};margin-bottom:6px">'
                            f'Demand/capacity per member — which are tight (need attention) vs '
                            f'slack (could be lighter).</div>', unsafe_allow_html=True)

                        def _flex_row(r):
                            _v = r["util"]
                            _c = (_FAIL if _v > 100 else "#c07800" if _v >= 85
                                  else _PASS_C if _v < 40 else _TEXT)
                            _verdict, _sugg = _flex_advice(_v)
                            return (
                                f'<div style="border-top:1px solid {_BORD};padding:5px 0">'
                                f'<div style="display:flex;justify-content:space-between;font-size:.66rem">'
                                f'<span style="color:{_TEXT};font-weight:700">{r["id"]}</span>'
                                f'<span style="color:{_c};font-weight:700">{_v:.0f}% · {_verdict}</span></div>'
                                f'<div style="font-size:.58rem;color:{_MUT}">{r["kind"]} · {r["sec"] or "—"} '
                                f'· governed by {r["gov"]} → {_sugg}</div></div>'
                            )

                        _tight = _flex[:5]
                        _slack = [r for r in reversed(_flex) if r["util"] < 65][:5]
                        st.markdown(
                            f'<div style="font-size:.60rem;font-weight:700;color:{_FAIL};'
                            f'text-transform:uppercase;letter-spacing:.5px">Most critical / tight</div>'
                            + "".join(_flex_row(r) for r in _tight), unsafe_allow_html=True)
                        if _slack:
                            st.markdown(
                                f'<div style="font-size:.60rem;font-weight:700;color:{_PASS_C};'
                                f'text-transform:uppercase;letter-spacing:.5px;margin-top:8px">'
                                f'Most flexible / slack</div>'
                                + "".join(_flex_row(r) for r in _slack), unsafe_allow_html=True)
                        st.caption("Ask the agent e.g. \"explain the flexibility of A3-A5\" "
                                   "or \"fix the failing beams\" for actions.")

        with _rt2:
            if st.button("⟳  Show details for selected element", key="dd_show_details",
                         width="stretch",
                         help="Click an element in the 3D/2D view, then press this to load its details here."):
                st.rerun()
            _sel     = st.session_state.selected_el
            _sel_level = st.session_state.get("active_element_level", "")
            # Element ids repeat across floors — resolve on the SELECTED level first so
            # Design Details shows the element you clicked (and its live material/section),
            # not the first id-match on level_01.
            _sel_obj = None
            _found_level = None
            if _sel:
                if (_sel_level and is_multilevel(layout_obj)
                        and _sel_level in get_level_keys(layout_obj)):
                    _sel_obj = next((e for e in get_structure(layout_obj, _sel_level)
                                     if e.get("id") == _sel), None)
                    _found_level = _sel_level if _sel_obj else None
                if _sel_obj is None:
                    _found_level, _sel_obj = find_element_in_layout(layout_obj, _sel)
            if _found_level:
                _sel_level = _found_level
                st.session_state.active_element_level = _found_level

            if _sel:
                st.markdown(
                    f'<div style="font-size:.64rem;color:{_MUT};margin:2px 0 8px 0">'
                    f'Selected element ID: '
                    f'<span style="color:{_TEXT};font-weight:700">{_sel}</span>'
                    f'{f" <span style=\"color:{_MUT};font-weight:600\">({_sel_level})</span>" if _sel_level else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            if _sel_obj:
                _eff_mat = (layout_obj.get("meta") or {}).get("material") or _mat_now
                st.markdown(_el_detail_html(_sel_obj, er, level=_sel_level,
                                            fallback_mat=_eff_mat), unsafe_allow_html=True)

                # ── Force & moment diagram (any selected beam — passing OR failing) ──
                _sel_is_beam = len(_sel_obj.get("geometry", [])) == 2
                if _sel_is_beam:
                    _bev = next((b for b in (er or {}).get("beams", [])
                                 if b.get("id") == _sel
                                 and (not _sel_level or not b.get("level")
                                      or b.get("level") == _sel_level)), None)
                    with st.expander("📐  Force & moment diagram", expanded=False):
                        try:
                            if _bev:
                                _d_span = _bev.get("span_m", 0.0)
                                _d_w    = _bev.get("w_total_kNm", 0.0)
                                _d_mmax = _bev.get("M_max_kNm", 0.0)
                            else:
                                import math as _dmath
                                _dg = _sel_obj.get("geometry", [])
                                _d_span = _dmath.dist(_dg[0], _dg[1]) if len(_dg) >= 2 else 0.0
                                _d_w    = (_sdl_now + _ll_now) * 3.0   # nominal 3 m tributary
                                _d_mmax = _d_w * _d_span * _d_span / 8.0
                            st.image(
                                _beam_diagram_png(_d_span, _d_w, _d_mmax, _sel, _is_light),
                                width="stretch",
                            )
                            if not _bev:
                                st.caption("Estimated loads — run analysis for exact values.")
                        except Exception as _de:
                            st.caption(f"Diagram unavailable: {_de}")

                # ── Direct action buttons (bypass agent) ──────────────────
                _act_cols = st.columns(2, gap="small") if _sel_is_beam else st.columns([1, 1], gap="small")

                with _act_cols[0]:
                    if st.button(f"✕  Remove", key="btn_direct_remove",
                                 width="stretch"):
                        try:
                            from nodes.modify import remove_element as _direct_rem
                            _new_layout = json.loads(_direct_rem(json.dumps(layout_obj), _sel,
                                                                 level_key=_sel_level or None))
                            # If the element is still present on that level, removal was blocked.
                            if (next((e for e in get_structure(_new_layout, _sel_level or None)
                                      if e.get("id") == _sel), None) is not None):
                                st.session_state["_remove_blocked"] = _sel
                                st.rerun()
                            else:
                                _push_version(_new_layout)
                                st.session_state.selected_el = ""
                                st.session_state.active_element_level = ""
                                st.session_state["_remove_blocked"] = ""
                                st.rerun()
                        except Exception as _re:
                            st.error(f"Remove failed: {_re}")

                if _sel_is_beam:
                    with _act_cols[1]:
                        if st.button("⊕  Add Mid-col", key="btn_direct_midcol",
                                     width="stretch"):
                            try:
                                from nodes.modify import add_midspan_column as _direct_amc
                                _new_layout = json.loads(_direct_amc(json.dumps(layout_obj), _sel, _mat_now))
                                _push_version(_new_layout)
                                st.session_state.selected_el = ""
                                st.session_state.active_element_level = ""
                                st.rerun()
                            except Exception as _me:
                                st.error(f"Add midspan column failed: {_me}")

                # Perimeter elements are envelope-locked — explain, then allow a forced remove.
                if st.session_state.get("_remove_blocked") == _sel:
                    st.markdown(
                        f'<div style="background:{_FAIL_BG};color:{_FAIL};border:1px solid {_FAIL};'
                        f'border-radius:6px;padding:7px 10px;font-size:.66rem;line-height:1.5;margin-top:6px">'
                        f'<b>{_sel}</b> is a <b>perimeter</b> element — it defines the building '
                        f'envelope and is locked. Removing it may compromise the structure. '
                        f'Remove it anyway only if you are sure.</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("⚠  Force remove anyway", key="btn_force_remove",
                                 width="stretch", type="primary"):
                        try:
                            from nodes.modify import remove_element as _force_rem
                            _new_layout = json.loads(_force_rem(json.dumps(layout_obj), _sel, True,
                                                               level_key=_sel_level or None))
                            _push_version(_new_layout)
                            st.session_state.selected_el = ""
                            st.session_state.active_element_level = ""
                            st.session_state["_remove_blocked"] = ""
                            st.rerun()
                        except Exception as _fre:
                            st.error(f"Force remove failed: {_fre}")

                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

            elif _sel:
                # A selection is set but the element isn't in the current layout — it was
                # removed/renamed by an edit. Clear it so the next click shows cleanly.
                st.markdown(
                    f'<div style="font-size:.68rem;color:{_FAIL};padding:4px 0">'
                    f'<b>{_sel}</b> is no longer in the design (removed or renamed). '
                    f'Select another element in the plan.</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Clear selection", key="dd_clear_stale", width="stretch"):
                    st.session_state.selected_el = ""
                    st.session_state.active_element_level = ""
                    st.rerun()
            else:
                st.markdown(
                    f'<div style="font-size:.70rem;color:{_MUT};padding:4px 0">'
                    f'Click an element in the plan, then press <b>⟳ Show details</b> above.</div>',
                    unsafe_allow_html=True,
                )

            if er:
                _fbeams = [b for b in er.get("beams", [])
                           if not all([b.get("bend_PASS"), b.get("shear_PASS"),
                                       b.get("defl_TL_PASS"), b.get("defl_LL_PASS")])]
                _fcols  = [c for c in er.get("columns", [])
                           if not all([c.get("stress_PASS"), c.get("buckling_PASS")])]
                if _fbeams or _fcols:
                    st.markdown(
                        '<div class="panel-hdr" style="margin-top:8px">Critical Elements</div>',
                        unsafe_allow_html=True,
                    )
                    _crit_html = ""
                    for _b in _fbeams[:4]:
                        _b_lvl, _ = find_element_in_layout(layout_obj, _b["id"])
                        _chks = [k for k, f in [
                            ("bend",  not _b.get("bend_PASS")),
                            ("shear", not _b.get("shear_PASS")),
                            ("defl",  not _b.get("defl_TL_PASS") or not _b.get("defl_LL_PASS")),
                        ] if f]
                        _crit_html += (
                            f'<div class="crit-item" '
                            f'onclick="window.parent.postMessage({{type:\'selectElement\','
                            f'elementId:\'{_b["id"]}\',level:\'{_b_lvl or ""}\'}},\'*\')">'
                            f'<b>{_b["id"]}</b> {_b.get("span_m",0):.1f}m'
                            f'<span style="float:right;color:{_FAIL}">{", ".join(_chks)}</span></div>'
                        )
                    for _c in _fcols[:2]:
                        _c_lvl, _ = find_element_in_layout(layout_obj, _c["id"])
                        _chks = [k for k, f in [
                            ("stress", not _c.get("stress_PASS")),
                            ("buck",   not _c.get("buckling_PASS")),
                        ] if f]
                        _crit_html += (
                            f'<div class="crit-item" '
                            f'onclick="window.parent.postMessage({{type:\'selectElement\','
                            f'elementId:\'{_c["id"]}\',level:\'{_c_lvl or ""}\'}},\'*\')">'
                            f'<b>{_c["id"]}</b>'
                            f'<span style="float:right;color:{_FAIL}">{", ".join(_chks)}</span></div>'
                        )
                    st.markdown(_crit_html, unsafe_allow_html=True)
                elif er:
                    st.markdown('<span class="pass-badge">✓ All elements pass</span>',
                                unsafe_allow_html=True)

            # ── Stress Hierarchy ──────────────────────────────────────────────
            if er:
                st.markdown(
                    '<div class="panel-hdr" style="margin-top:10px">Stress Hierarchy</div>',
                    unsafe_allow_html=True,
                )
                _hier_items = []
                for _hb in er.get("beams", []):
                    _hu = max(
                        _hb.get("sigma_bend_MPa", 0) / max(_hb.get("allow_bend_MPa",  1), 1e-6),
                        _hb.get("tau_MPa",         0) / max(_hb.get("allow_shear_MPa", 1), 1e-6),
                        _hb.get("delta_total_mm",  0) / max(_hb.get("limit_TL_mm",     1), 1e-6),
                    )
                    _hier_items.append({
                        "id": _hb.get("id", ""), "type": "Primary Girder",
                        "util": _hu, "dim": f'{_hb.get("span_m", 0):.1f} m',
                    })
                for _hc in er.get("columns", []):
                    _hu = max(
                        _hc.get("sigma_comp_MPa", 0) / max(_hc.get("allow_comp_MPa", 1), 1e-6),
                        (1 / max(_hc.get("SF_buckling", 3.0), 0.01)) * 3.0,
                    )
                    _hier_items.append({
                        "id": _hc.get("id", ""), "type": "Column",
                        "util": _hu, "dim": f'{_hc.get("trib_area_m2", 0):.1f} m²',
                    })
                _hier_items.sort(key=lambda x: x["util"], reverse=True)
                _hh = '<div style="display:flex;flex-direction:column;gap:3px;margin-top:5px">'
                for _hi in _hier_items[:16]:
                    _u    = min(_hi["util"], 1.0)
                    _pct  = int(_u * 100)
                    _pw   = f"{_u * 100:.0f}%"
                    _hclr = ("#e05050" if _u >= 0.70 else
                             "#e08020" if _u >= 0.50 else
                             "#d4a800" if _u >= 0.35 else "#40d090")
                    _hh += (
                        f'<div style="display:flex;align-items:center;gap:5px;padding:2px 0">'
                        f'<span style="width:7px;height:7px;border-radius:50%;'
                        f'background:{_hclr};flex-shrink:0"></span>'
                        f'<span style="font-size:.62rem;font-weight:700;color:#c8eeed;'
                        f'width:48px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;'
                        f'white-space:nowrap">{_hi["id"]}</span>'
                        f'<span style="font-size:.58rem;color:#5a8080;flex:1;min-width:0;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
                        f'{_hi["type"]}</span>'
                        f'<div style="width:68px;height:3px;background:#0d3030;'
                        f'border-radius:2px;overflow:hidden;flex-shrink:0">'
                        f'<div style="width:{_pw};height:100%;background:{_hclr};'
                        f'border-radius:2px"></div></div>'
                        f'<span style="font-size:.62rem;font-weight:700;color:{_hclr};'
                        f'width:26px;text-align:right;flex-shrink:0">{_pct}%</span>'
                        f'<span style="font-size:.58rem;color:#5a8080;width:36px;'
                        f'text-align:right;flex-shrink:0">{_hi["dim"]}</span>'
                        f'</div>'
                    )
                if not _hier_items:
                    _hh += f'<div style="font-size:.70rem;color:#5a9090;padding:6px 0">Run structural analysis to see hierarchy.</div>'
                _hh += '</div>'
                st.markdown(_hh, unsafe_allow_html=True)

            st.markdown(
                '<div class="panel-hdr" style="margin-top:10px">History</div>',
                unsafe_allow_html=True,
            )
            _sh = st.session_state.state_history
            if not _sh:
                st.markdown(
                    f'<div style="font-size:.70rem;color:{_MUT}">No history yet.</div>',
                    unsafe_allow_html=True,
                )
            else:
                _hist_html = ""
                for _h in reversed(_sh[-5:]):
                    _hev  = (_h.get("eval_result") or {}).get("summary", {})
                    _hbf  = _hev.get("beam_failures", 0)
                    _hcf2 = _hev.get("column_failures", 0)
                    _hp   = _hev.get("overall_PASS", None)
                    _ht   = "Pass" if _hp else ("Fail" if _hp is False else "--")
                    _hist_html += (
                        f'<div class="hist-item">'
                        f'<div class="hist-dot"></div>'
                        f'<div><div class="hist-label">{_h["label"]}</div>'
                        f'<div class="hist-sub">{_ht} · {_hbf}B {_hcf2}C</div></div></div>'
                    )
                st.markdown(_hist_html, unsafe_allow_html=True)

            if _snaps:
                with st.expander(f"Saved Snapshots ({len(_snaps)})", expanded=False):
                    for _sn in _snaps:
                        _sev   = (_sn.get("eval_result") or {}).get("summary", {})
                        _sfail = _sev.get("beam_failures",0) + _sev.get("column_failures",0)
                        _scf   = _sn.get("cost_flexibility")
                        with st.expander(
                            f"{_sn['label']} · {'OK' if _sfail==0 else f'{_sfail} fail'}",
                            expanded=False,
                        ):
                            if _scf:
                                _s1, _s2 = st.columns(2)
                                _s1.metric("Net",  f"${_scf.get('net_cost_usd',0):+,.0f}")
                                _s2.metric("Flex", f"{_scf.get('flexibility_score',0):.1f}/10")
                            if st.button(f"Restore {_sn['label']}",
                                         key=f"restore_{_sn['label']}"):
                                _push_version(json.loads(_sn["layout_json"]))
                                st.session_state.eval_result = _sn.get("eval_result")
                                st.session_state.eval_alts   = _get_failure_alternatives(
                                    _sn.get("eval_result") or {}, _mat_now)
                                st.rerun()

            with st.expander("Output Log", expanded=False):
                for _msg in reversed(st.session_state.output_log[-6:]):
                    st.markdown(
                        f'<div class="log-entry">{_msg[:220]}'
                        f'{"…" if len(_msg)>220 else ""}</div>',
                        unsafe_allow_html=True,
                    )

            # (Inline agent chat removed from Design Details — the single agent
            #  chat now lives only in the left sidebar to avoid duplication.)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMPARE
# ══════════════════════════════════════════════════════════════════════════════
with tab_cmp:

    # ── Data ─────────────────────────────────────────────────────────────────
    _snaps_c = st.session_state.snapshots
    _cvm_now = st.session_state.get("compare_view_mode", "2D")
    _cmp_ids = st.session_state.get("cmp_labels", False)
    _cmp_ev  = st.session_state.get("cmp_eval",   True)
    _DOT_C   = [_ACC, _ACC2, "#ffd060", "#ff8080", "#88d088", "#c0a0ff"]

    def _snap_fails(s):
        _ev_ = (s.get("eval_result") or {}).get("summary", {})
        return _ev_.get("beam_failures", 0) + _ev_.get("column_failures", 0)

    # ── Validate cmp_sel_indices against current snapshots ─────────────────────
    _all_snap_labels = [s["label"] for s in _snaps_c]
    _sel_idx_raw = st.session_state.get("cmp_sel_indices", [])
    _sel_idx = [i for i in _sel_idx_raw if i < len(_snaps_c)]
    if _sel_idx != _sel_idx_raw:
        st.session_state.cmp_sel_indices = _sel_idx

    # Always include baseline + selected snapshots
    _cmp_opts = [
        {"label": "Baseline", "sub": "Current design",
         "layout_json": json.dumps(layout_obj),
         "eval_result": er, "cost_flexibility": st.session_state.cost_flexibility,
         "dot": _DOT_C[0]}
    ] + [
        {"label": _snaps_c[i]["label"],
         "sub":   "Pass" if _snap_fails(_snaps_c[i]) == 0 else f"{_snap_fails(_snaps_c[i])} fail",
         "layout_json":      _snaps_c[i]["layout_json"],
         "eval_result":      _snaps_c[i].get("eval_result"),
         "cost_flexibility": _snaps_c[i].get("cost_flexibility"),
         "dot": _DOT_C[min(_j + 1, len(_DOT_C)-1)]}
        for _j, i in enumerate(_sel_idx)
    ]
    _n_opts = len(_cmp_opts)

    # ── Metric helpers ────────────────────────────────────────────────────────
    def _co_weight(co):
        return _eval_weight_cost(co.get("eval_result") or {})[0]

    def _co_cost(co):
        cf = co.get("cost_flexibility") or {}
        if cf.get("net_cost_usd") is not None:
            return float(cf["net_cost_usd"])
        return _eval_weight_cost(co.get("eval_result") or {})[1]

    def _co_max_defl(co):
        bs = (co.get("eval_result") or {}).get("beams", [])
        return max((b.get("delta_total_mm", 0) for b in bs), default=None) if bs else None

    def _co_max_util(co):
        ev  = co.get("eval_result") or {}
        rat = []
        for b in ev.get("beams", []):
            if b.get("allow_bend_MPa"):
                rat.append(b["sigma_bend_MPa"] / b["allow_bend_MPa"])
            if b.get("allow_shear_MPa"):
                rat.append(b["tau_MPa"] / b["allow_shear_MPa"])
            if b.get("limit_TL_mm"):
                rat.append(b["delta_total_mm"] / b["limit_TL_mm"])
        for c in ev.get("columns", []):
            if c.get("allow_comp_MPa"):
                rat.append(c["sigma_comp_MPa"] / c["allow_comp_MPa"])
        return round(max(rat) * 100, 1) if rat else None

    def _best_from(pairs, lower=True):
        valid = [(l, v) for l, v in pairs if isinstance(v, (int, float))]
        if not valid:
            return "—", None
        return (min if lower else max)(valid, key=lambda x: x[1])

    # -- Layout: comparison plans (left) + View Settings / Comparison Set rail
    #    Mirrors the ANALYSIS / DESIGN DETAILS rail in the Modify workspace.
    _cmp_main, _cmp_right = st.columns([2.1, 0.55], gap="small")

    with _cmp_right:
        _ct_vs, _ct_set = st.tabs(["  VIEW SETTINGS  ", "  COMPARISON SET  "])
        with _ct_vs:
            st.markdown(
                f'<div class="sb-section" style="margin-top:4px">View Settings</div>',
                unsafe_allow_html=True,
            )
            _vs1, _vs2 = st.columns(2, gap="small")
            with _vs1:
                if st.button("2D", key="cmp_2d", width="stretch",
                             type="primary" if _cvm_now == "2D" else "secondary"):
                    st.session_state["compare_view_mode"] = "2D"
                    st.rerun()
            with _vs2:
                if st.button("3D", key="cmp_3d", width="stretch",
                             type="primary" if _cvm_now == "3D" else "secondary"):
                    st.session_state["compare_view_mode"] = "3D"
                    st.rerun()
            # Level selector (replaces the old Overlay-IDs / Eval-overlay toggles).
            _cmp_lvl_keys = get_level_keys(layout_obj) or ["level_01"]
            _cmp_lvl_opts = (_cmp_lvl_keys + ["All levels"]) if len(_cmp_lvl_keys) > 1 else _cmp_lvl_keys
            _cmp_cur = st.session_state.get("cmp_level", _cmp_lvl_keys[0])
            if _cmp_cur not in _cmp_lvl_opts:
                _cmp_cur = _cmp_lvl_keys[0]
            _cmp_level_sel = st.selectbox(
                "Show", _cmp_lvl_opts,
                index=_cmp_lvl_opts.index(_cmp_cur),
                format_func=lambda x: ("Show all levels" if x == "All levels" else f"Show {x}"),
                key="cmp_level_sel",
            )
            st.session_state.cmp_level = _cmp_level_sel
            _cmp_ids = st.toggle("Show labels", value=_cmp_ids, key="cmp_labels")

            st.markdown(
                f'<div class="sb-section" style="margin-top:10px">Legend</div>',
                unsafe_allow_html=True,
            )
            _legend_items = _present_legend_items(layout_obj, _is_light)
            if _legend_items:
                _leg_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 6px;margin-top:2px">'
                for _lc, _ll in _legend_items:
                    _leg_html += (
                        f'<div style="display:flex;align-items:center;gap:4px;font-size:.60rem;color:{_MUT}">'
                        f'<span style="width:8px;height:8px;border-radius:50%;background:{_lc};flex-shrink:0;display:inline-block"></span>'
                        f'{_ll}</div>'
                    )
                _leg_html += '</div>'
                st.markdown(_leg_html, unsafe_allow_html=True)
            _cmp_mat_leg = _material_legend_html(layout_obj, _is_light, _MUT)
            if _cmp_mat_leg:
                st.markdown(_cmp_mat_leg, unsafe_allow_html=True)

            st.markdown('<div style="margin-top:10px"></div>', unsafe_allow_html=True)
            if st.button("Reset View", key="cmp_reset_view", width="stretch"):
                st.session_state["compare_view_mode"] = "2D"
                st.session_state["cmp_labels"] = False
                st.session_state["cmp_eval"]   = True
                st.rerun()
        with _ct_set:
            st.markdown(
                f'<div style="font-size:.60rem;color:{_MUT};margin:4px 0 6px;line-height:1.5">'
                f'Pick which snapshots to compare — add as many as you need.</div>',
                unsafe_allow_html=True,
            )
            # Baseline always shown
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:7px;padding:4px 6px;'
                f'border-radius:5px;background:{"#eef7f7" if _is_light else "#0d2828"};margin-bottom:3px">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{_DOT_C[0]};flex-shrink:0;display:inline-block"></span>'
                f'<span style="font-size:.70rem;font-weight:700;color:{_TEXT}">Baseline (Current)</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if _snaps_c:
                _ca1, _ca2 = st.columns(2, gap="small")
                with _ca1:
                    if st.button("Add all", key="cmp_add_all", width="stretch"):
                        st.session_state.cmp_sel_indices = list(range(len(_snaps_c)))
                        st.rerun()
                with _ca2:
                    if st.button("Clear", key="cmp_clear_all", width="stretch",
                                 disabled=not _sel_idx):
                        st.session_state.cmp_sel_indices = []
                        st.rerun()
                for _si, _sn in enumerate(_snaps_c):
                    _in_cmp = _si in _sel_idx
                    _dot_c  = _DOT_C[min(_sel_idx.index(_si)+1 if _in_cmp else 0, len(_DOT_C)-1)]
                    _s_fails = _snap_fails(_sn)
                    _s_sub  = "Pass" if _s_fails == 0 else f"{_s_fails} fail"
                    _s_bg   = f"{'rgba(42,192,192,0.08)' if _in_cmp else 'transparent'}"
                    _s_brd  = f"border:1px solid {_ACC if _in_cmp else _BORD}"
                    _c1, _c2 = st.columns([4, 1], gap="small")
                    with _c1:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:6px;padding:4px 6px;'
                            f'border-radius:5px;background:{_s_bg};{_s_brd};margin-bottom:2px">'
                            f'<span style="width:8px;height:8px;border-radius:50%;background:{_dot_c if _in_cmp else _MUT};flex-shrink:0;display:inline-block"></span>'
                            f'<div style="min-width:0"><div style="font-size:.70rem;font-weight:{"700" if _in_cmp else "400"};color:{_TEXT if _in_cmp else _MUT};overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_sn["label"]}</div>'
                            f'<div style="font-size:.58rem;color:{_MUT}">{_s_sub}</div></div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with _c2:
                        if _in_cmp:
                            if st.button("✕", key=f"cmp_rm_{_si}", width="stretch"):
                                _new_idx = [i for i in _sel_idx if i != _si]
                                st.session_state.cmp_sel_indices = _new_idx
                                st.rerun()
                        else:
                            if st.button("+", key=f"cmp_add_{_si}", width="stretch"):
                                st.session_state.cmp_sel_indices = _sel_idx + [_si]
                                st.rerun()
            else:
                st.markdown(
                    f'<div style="font-size:.60rem;color:{_MUT};padding:6px 4px;'
                    f'border:1px dashed {_BORD};border-radius:6px;margin-top:3px">'
                    f'Save snapshots in the Modify tab to compare options here.</div>',
                    unsafe_allow_html=True,
                )

    with _cmp_main:
        # ── Report options bar (Export JSON lives in the global top bar) ────────────
        _rp1, _rp3, _rp4 = st.columns([4.4, 0.9, 0.7], gap="small")
        with _rp1:
            st.markdown(
                f'<div style="font-size:.60rem;font-weight:700;color:{_MUT};'
                f'text-transform:uppercase;letter-spacing:1px;padding:6px 0">'
                f'Compare Options</div>',
                unsafe_allow_html=True,
            )
        with _rp3:
            # Direct button (NOT inside a popover — a popover closes on the rerun and the
            # result would never show). The report renders in a persistent panel below.
            if st.button("🧾 AI Report", key="cmp_gen_report", width="stretch",
                         help="Generate an intervention report (shown below) + a downloadable PDF."):
                with st.spinner("Writing intervention report…"):
                    # If we have the original baseline, produce a CHANGE-focused intervention
                    # report (what changed, type, complexity, cost) + a diff plan in the PDF.
                    _orig = st.session_state.get("diff_baseline")
                    if _orig:
                        _rep = _intervention_report_text(_orig, layout_obj, er)
                        st.session_state["_cmp_report_before"] = json.dumps(_orig)
                    else:
                        st.session_state["_cmp_report_before"] = ""
                        _rep = ""
                        if _llm_is_reachable():
                            try:
                                _rep = _run_agent_chat(
                                    "Write a concise structural report for this layout: summarise the "
                                    "framing system, materials, spans, any failing elements and the "
                                    "recommended fixes. Plain prose, no JSON.",
                                    layout_obj, er,
                                )
                            except Exception as _rerr:
                                st.session_state["_last_error"] = f"AI report: {_rerr}"
                                _rep = ""
                        if (not _rep) or _rep.startswith(("APPLY_TOOL:", "APPLY_MATERIAL:",
                                                          "GENERATE_GRID", "EVALUATE", "FIX_FAILING")):
                            _rep = _structural_summary_text(layout_obj, er)
                st.session_state["_cmp_report_txt"] = _rep
                st.rerun()
        with _rp4:
            if st.button("✕ Reset", width="stretch", key="btn_reset_cmp"):
                st.session_state.snapshots = []
                st.session_state.cmp_sel_indices = []
                st.rerun()

        # ── Structural report panel (persistent — shows after clicking AI Report) ──
        _rep_txt = st.session_state.get("_cmp_report_txt")
        if _rep_txt:
            with st.expander("🧾 Structural report", expanded=True):
                st.markdown(
                    f'<div style="font-size:.66rem;color:{_MUT};white-space:pre-wrap;'
                    f'line-height:1.55">{_rep_txt}</div>',
                    unsafe_allow_html=True,
                )
                try:
                    _rep_pdf = _sheet_pdf_bytes(
                        json.dumps(layout_obj), json.dumps(er) if er else "",
                        str(_lid), str(_mat_now),
                        tuple((h.get("prompt") or h.get("label") or "")
                              for h in st.session_state.get("history", [])[-7:]),
                        True, _rep_txt,
                        st.session_state.get("_cmp_report_before", ""),
                        (f"{st.session_state.get('user_name','')} "
                         f"({st.session_state.get('user_email','')})"
                         if st.session_state.get("user_name") else ""),
                    )
                    _rpc1, _rpc2 = st.columns(2, gap="small")
                    with _rpc1:
                        st.download_button(
                            "⤓ Download report (PDF)", data=_rep_pdf,
                            file_name=f"{_lid}_structural_report.pdf",
                            mime="application/pdf", width="stretch", key="cmp_dl_report",
                        )
                    with _rpc2:
                        if st.button("Clear report", width="stretch", key="cmp_clear_report"):
                            st.session_state["_cmp_report_txt"] = ""
                            st.rerun()
                except Exception as _re:
                    st.caption(f"Report build failed: {_re}")

        # ── Comparison plans area ─────────────────────────────────────────────────
        st.markdown(f'<div style="margin-top:10px;border-top:1px solid {_BORD}"></div>',
                    unsafe_allow_html=True)

        if _n_opts < 2:
            st.markdown(
                f'<div style="font-size:.70rem;color:{_MUT};padding:20px 8px;'
                f'text-align:center;line-height:1.9">'
                f'Select at least one snapshot using <b>+</b> in the '
                f'<b>Comparison Set</b> tab on the right.</div>',
                unsafe_allow_html=True,
            )
        else:
            # (Baseline-only insight chips removed — the metric cards below already
            #  show the per-option comparison.)

            # ── Metric row ─────────────────────────────────────────────────────────
            def _delta_badge(val, base, lower_good=True):
                if val is None or base is None or abs(base) < 0.001:
                    return ""
                d    = (val - base) / abs(base) * 100
                good = (d < 0) if lower_good else (d > 0)
                clr  = _PASS_C if good else _FAIL
                arr  = "↓" if d < 0 else "↑"
                return (f'<span style="font-size:.58rem;font-weight:700;'
                        f'color:{clr};margin-left:3px">{arr}&nbsp;{abs(d):.1f}%</span>')

            def _met_card(title, unit, vals, fmt=".1f", lower_good=True):
                base = vals[0]
                html = (
                    f'<div style="flex:1;border:1px solid {_BORD};border-radius:8px;'
                    f'padding:8px 10px;background:{_CARD};min-width:0">'
                    f'<div style="font-size:.58rem;font-weight:700;color:{_MUT};'
                    f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">'
                    f'{title}</div>'
                    f'<div style="font-size:.55rem;color:{_MUT};margin-bottom:6px">({unit})</div>'
                    f'<div style="display:flex;gap:6px">'
                )
                for _i, (_co, _v) in enumerate(zip(_cmp_opts, vals)):
                    _vstr = (f'{_v:{fmt}}' if isinstance(_v, (int, float)) else "—")
                    _dlta = "" if _i == 0 else _delta_badge(_v, base, lower_good)
                    _lbl_clr = _MUT if _i == 0 else (
                        (_PASS_C if (isinstance(_v, (int, float)) and isinstance(base, (int, float))
                                     and ((_v < base) if lower_good else (_v > base)))
                         else _TEXT)
                    )
                    html += (
                        f'<div style="flex:1;min-width:0;text-align:center">'
                        f'<div style="font-size:.55rem;color:{_MUT};margin-bottom:2px;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                        f'{_co["label"]}</div>'
                        f'<div style="font-size:.75rem;font-weight:800;color:{_lbl_clr}">'
                        f'{_vstr}</div>'
                        f'{_dlta}</div>'
                    )
                html += '</div></div>'
                return html

            _wvals = [_co_weight(c)   for c in _cmp_opts]
            _cvals = [_co_cost(c)     for c in _cmp_opts]
            _dvals = [_co_max_defl(c) for c in _cmp_opts]
            _uvals = [_co_max_util(c) for c in _cmp_opts]

            st.markdown(
                f'<div style="display:flex;gap:8px;margin-bottom:12px">'
                + _met_card("Total Weight",    "kN",  _wvals, ".1f")
                + _met_card("Total Cost",      "USD", _cvals, ".0f")
                + _met_card("Max Deflection",  "mm",  _dvals, ".1f")
                + _met_card("Max Utilization", "%",   _uvals, ".1f")
                + '</div>',
                unsafe_allow_html=True,
            )

            # ── Diff legend (each non-baseline window is coloured vs the baseline) ──
            _baseline_layout = _normalize_layout(json.loads(_cmp_opts[0]["layout_json"]))
            _add_c = "#1a8050" if _is_light else "#40d090"
            _rem_c = "#cc2020" if _is_light else "#ff5050"
            _mod_c = "#7c4dff" if _is_light else "#9b7cff"
            st.markdown(
                f'<div style="display:flex;gap:14px;align-items:center;margin-bottom:8px;'
                f'font-size:.60rem;color:{_MUT}">'
                f'<span style="font-weight:700;text-transform:uppercase;letter-spacing:.5px">vs Baseline</span>'
                f'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:{_add_c};display:inline-block"></span>Added</span>'
                f'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:{_rem_c};display:inline-block"></span>Removed</span>'
                f'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:{_mod_c};display:inline-block"></span>Changed</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Floor plan columns ─────────────────────────────────────────────────
            _pcols = st.columns(_n_opts, gap="small")
            for _ci, (_pcol, _co) in enumerate(zip(_pcols, _cmp_opts)):
                with _pcol:
                    _dc = _co.get("dot", _DOT_C[min(_ci, len(_DOT_C)-1)])
                    _badge = (
                        '<span class="badge-curr">Current Design</span>'
                        if _ci == 0 else
                        f'<span class="badge-opt">Applied Changes ({_ci})</span>'
                    )
                    st.markdown(
                        f'<div class="cmp-card-hdr">'
                        f'<span style="display:flex;align-items:center;gap:6px">'
                        f'<span style="width:8px;height:8px;border-radius:50%;'
                        f'background:{_dc};flex-shrink:0;display:inline-block"></span>'
                        f'<span class="cmp-title">{_co["label"]}</span></span>'
                        f'{_badge}</div>',
                        unsafe_allow_html=True,
                    )
                    _plan_ci = _normalize_layout(json.loads(_co["layout_json"]))
                    _ph = max(220, 300 - (_n_opts - 2) * 20)
                    _cmp_lk = ("__ALL__" if st.session_state.get("cmp_level") == "All levels"
                               else st.session_state.get("cmp_level", "level_01"))
                    if _cvm_now == "2D":
                        _fig_ci = _render_floor_plan_plotly(
                            _plan_ci,
                            eval_result=_co["eval_result"] if _cmp_ev else None,
                            level_key=_cmp_lk,
                            labels=_cmp_ids, height_px=_ph, is_light=_is_light,
                            diff_on=(_ci > 0),
                            before_layout=(_baseline_layout if _ci > 0 else None),
                        )
                        st.plotly_chart(
                            _fig_ci, width="stretch",
                            config=dict(scrollZoom=True, displaylogo=False,
                                        modeBarButtonsToRemove=[
                                            "lasso2d", "select2d",
                                            "zoomIn2d", "zoomOut2d", "autoScale2d",
                                        ]),
                            key=f"cmp_plan_{_ci}",
                        )
                    else:
                        components.html(
                            _render_3d_viewport(
                                _plan_ci,
                                eval_result=_co["eval_result"] if _cmp_ev else None,
                                selected_el="",
                                active_level=_cmp_lk,
                                is_light=_is_light,
                                height=_ph,
                                before_layout=(_baseline_layout if _ci > 0 else None),
                                labels=_cmp_ids,
                                footings=st.session_state.footings_on,
                            ),
                            height=_ph + 8,
                            scrolling=False,
                        )
                    # Diff summary vs baseline — makes added/removed/changed explicit
                    # (and shows "identical to baseline" when a snapshot matches current).
                    if _ci > 0:
                        _dd = _compute_diff(_baseline_layout, _plan_ci)
                        _na, _nr, _nc = len(_dd["added"]), len(_dd["removed"]), len(_dd["changed"])
                        if _na or _nr or _nc:
                            _dparts = []
                            if _na: _dparts.append(f'<span style="color:{_add_c};font-weight:700">+{_na} added</span>')
                            if _nr: _dparts.append(f'<span style="color:{_rem_c};font-weight:700">−{_nr} removed</span>')
                            if _nc: _dparts.append(f'<span style="color:{_mod_c};font-weight:700">~{_nc} changed</span>')
                            _dtxt = " · ".join(_dparts)
                        else:
                            _dtxt = '<span style="opacity:.7">identical to baseline</span>'
                        st.markdown(
                            f'<div style="font-size:.58rem;color:{_MUT};text-align:center;'
                            f'padding:3px 2px;line-height:1.5">vs baseline: {_dtxt}</div>',
                            unsafe_allow_html=True,
                        )

                    # Per-plan footer metrics
                    _fw = _co_weight(_co)
                    _fc = _co_cost(_co)
                    _fd = _co_max_defl(_co)
                    _fu = _co_max_util(_co)
                    _fparts = []
                    if _fw is not None: _fparts.append(f"Weight: {_fw:.1f} kN")
                    if _fc is not None: _fparts.append(f"Cost: ${_fc:,.0f}")
                    if _fd is not None: _fparts.append(f"Max Defl: {_fd:.1f} mm")
                    if _fu is not None: _fparts.append(f"Util: {_fu:.0f}%")
                    st.markdown(
                        f'<div style="font-size:.58rem;color:{_MUT};text-align:center;'
                        f'padding:4px 2px;border-top:1px solid {_BORD};line-height:1.6">'
                        + " &nbsp;·&nbsp; ".join(_fparts) + '</div>',
                        unsafe_allow_html=True,
                    )


