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

    _write_json(EDITED_LAYOUT_PATH, new_layout)
    _write_json(REPO_ROOT / f"layout_v{v}.json", new_layout)
    _sync_viewers()


def _sync_viewers() -> None:
    """Signal both viewers to re-read currentLayout on the next rerun."""
    st.session_state.viewer_nonce = st.session_state.get("viewer_nonce", 0) + 1


def _compute_diff(before: dict, after: dict) -> dict:
    """Return sets of 'level|id' keys: added, removed, changed (geometry OR attributes).
    Keyed per-level because element ids repeat across levels in multilevel layouts."""
    b_els = {f"{lk}|{el['id']}": el for lk, el in iter_all_structure(before)}
    a_els = {f"{lk}|{el['id']}": el for lk, el in iter_all_structure(after)}
    added   = set(a_els) - set(b_els)
    removed = set(b_els) - set(a_els)
    changed = set()
    for k in (set(a_els) & set(b_els)):
        ae, be = a_els[k], b_els[k]
        if (json.dumps(ae.get("geometry"),   sort_keys=True) != json.dumps(be.get("geometry"),   sort_keys=True)
                or json.dumps(ae.get("attributes"), sort_keys=True) != json.dumps(be.get("attributes"), sort_keys=True)):
            changed.add(k)
    return {"added": added, "removed": removed, "changed": changed}


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


def _strip_structure(layout: dict) -> dict:
    """Remove all structural elements from a layout so the user starts with a blank grid.
    Works for both flat (structure key) and multilevel (levels.*.structure) formats."""
    import copy
    layout = copy.deepcopy(layout)
    if isinstance(layout.get("levels"), dict):
        for lk in layout["levels"]:
            layout["levels"][lk]["structure"] = []
    else:
        layout["structure"] = []
    return layout


def _load_working_layout() -> dict:
    """Load the persisted working layout from disk. Returns {} if no file exists."""
    if EDITED_LAYOUT_PATH.exists():
        return _normalize_layout(_read_json(EDITED_LAYOUT_PATH))
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
    if compare and st.session_state.get("versionHistory"):
        url += "&mode=compare"
    if option_file:
        url += f"&optionFile={option_file}"
    return url


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


def _get_level_payload(layout: dict, level_key: str | None = None) -> dict:
    if not is_multilevel(layout):
        return layout
    keys = get_level_keys(layout)
    if not keys:
        return {}
    lk = level_key if level_key in keys else keys[0]
    return layout.get("levels", {}).get(lk, {})


def _render_floor_plan_plotly(
    layout: dict,
    eval_result: dict | None = None,
    highlight: str = "",
    level_key: str | None = None,
    labels: bool = False,
    height_px: int = 510,
    is_light: bool = False,
    diff_on: bool = False,
    before_layout: dict | None = None,
    revision: int = 0,
):
    """Return a Plotly figure of the floor plan with clickable structural elements."""
    import math as _hm
    if is_light:
        BG = "#f0f8f8"; ROOM_F = "rgba(218,234,234,0.80)"; ROOM_L = "#a0c8c8"
        FG = "#1a3535"; ACCENT = "#088a87"
        PASS_C = "#1a8050"; FAIL_C = "#cc2020"; SEL_C = "#c07800"; WIN_C = "#2060a0"
        REM_C = "#cc2020"; ADD_C = "#1a8050"; MOD_C = "#c07800"
    else:
        BG = "#0c2020"; ROOM_F = "rgba(23,46,46,0.88)"; ROOM_L = "#1e4040"
        FG = "#c8eeed"; ACCENT = "#2ac0c0"
        PASS_C = "#40d090"; FAIL_C = "#ff5050"; SEL_C = "#ffd060"; WIN_C = "#4696dc"
        REM_C = "#ff5050"; ADD_C = "#40d090"; MOD_C = "#ffd060"

    # Base (un-evaluated) structural colour: blue in light mode, white in dark mode.
    STRUCT_BASE = "#2563c0" if is_light else "#e8eef5"

    level_keys = get_level_keys(layout)
    _show_all = (level_key == "__ALL__")   # render every level solid (Compare "All levels")
    active_level = level_key if level_key in level_keys else (level_keys[0] if level_keys else "level_01")
    level_payload = _get_level_payload(layout, active_level)
    active_rooms = get_rooms(layout, active_level)
    active_outline = get_outline(layout, active_level)
    active_doors = level_payload.get("doors", []) if is_multilevel(layout) else layout.get("doors", [])
    active_windows = level_payload.get("windows", []) if is_multilevel(layout) else layout.get("windows", [])
    active_furniture = level_payload.get("furniture", []) if is_multilevel(layout) else layout.get("furniture", [])

    el_status: dict[str, str] = {}
    eval_map_b: dict = {}
    eval_map_c: dict = {}
    if eval_result:
        for b in eval_result.get("beams", []):
            ok = b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"]
            el_status[b["id"]] = "pass" if ok else "fail"
            eval_map_b[b["id"]] = b
        for c in eval_result.get("columns", []):
            ok = c["stress_PASS"] and c["buckling_PASS"]
            el_status[c["id"]] = "pass" if ok else "fail"
            eval_map_c[c["id"]] = c

    # ── DIFF: added / removed / changed sets, keyed by (level, id) ─────────────
    # (element ids repeat across levels, so a flat id key would miss per-level edits)
    _diff_removed: set = set()
    _diff_added:   set = set()
    _diff_changed: set = set()
    _before_el_map: dict = {}
    if diff_on and before_layout:
        _cur_map = {(lk, el["id"]): el for lk, el in iter_all_structure(layout)}
        _bef_map = {(lk, el["id"]): el for lk, el in iter_all_structure(before_layout)}
        _before_el_map = _bef_map
        _diff_removed  = set(_bef_map) - set(_cur_map)
        _diff_added    = set(_cur_map) - set(_bef_map)
        import json as _j
        for _key in set(_cur_map) & set(_bef_map):
            _ce, _be = _cur_map[_key], _bef_map[_key]
            if (_j.dumps(_ce.get("geometry"),   sort_keys=True) != _j.dumps(_be.get("geometry"),   sort_keys=True)
                    or _j.dumps(_ce.get("attributes"), sort_keys=True) != _j.dumps(_be.get("attributes"), sort_keys=True)):
                _diff_changed.add(_key)

    traces: list = []
    annotations: list = []

    # ── ROOMS ─────────────────────────────────────────────────────────────────
    for room in active_rooms:
        geo = room.get("geometry", [])
        if len(geo) < 3:
            continue
        rxs = [p[0] for p in geo] + [geo[0][0]]
        rys = [p[1] for p in geo] + [geo[0][1]]
        rname = room.get("name", "")
        area = abs(sum(
            (geo[i][0]*geo[(i+1)%len(geo)][1] - geo[(i+1)%len(geo)][0]*geo[i][1])
            for i in range(len(geo))
        )) / 2
        traces.append(go.Scatter(
            x=rxs, y=rys, fill="toself",
            fillcolor=ROOM_F,
            line=dict(color=ROOM_L, width=0.8),
            mode="lines", showlegend=False,
            hovertemplate=(f"<b>{rname}</b><br>Area: {area:.1f} m²<extra></extra>"
                           if rname else None),
            hoverinfo=("skip" if not rname else None),
        ))
        if rname:
            cx = sum(p[0] for p in geo) / len(geo)
            cy = sum(p[1] for p in geo) / len(geo)
            annotations.append(dict(
                x=cx, y=cy, text=rname, showarrow=False,
                font=dict(size=8, color=FG, family="monospace"),
                opacity=0.55,
            ))

    # ── OUTLINE ───────────────────────────────────────────────────────────────
    outline = active_outline
    if len(outline) > 1:
        traces.append(go.Scatter(
            x=[p[0] for p in outline], y=[p[1] for p in outline],
            mode="lines", line=dict(color=ACCENT, width=1.5),
            showlegend=False, hoverinfo="skip",
        ))

    # ── WINDOWS ───────────────────────────────────────────────────────────────
    for win in active_windows:
        geo = win.get("geometry", [])
        if len(geo) >= 2:
            traces.append(go.Scatter(
                x=[p[0] for p in geo], y=[p[1] for p in geo],
                mode="lines", line=dict(color=WIN_C, width=1.5),
                showlegend=False, hoverinfo="skip",
            ))

    # ── FURNITURE ─────────────────────────────────────────────────────────────
    for furn in active_furniture:
        geo = furn.get("geometry", [])
        if len(geo) >= 3:
            fxs = [p[0] for p in geo] + [geo[0][0]]
            fys = [p[1] for p in geo] + [geo[0][1]]
            traces.append(go.Scatter(
                x=fxs, y=fys, fill="toself",
                fillcolor="rgba(200,238,237,0.06)",
                line=dict(color=FG, width=0.5),
                mode="lines", showlegend=False, hoverinfo="skip",
            ))

    all_structure = list(iter_all_structure(layout))
    beams = [(lk, s) for lk, s in all_structure if len(s.get("geometry", [])) == 2]
    cols  = [(lk, s) for lk, s in all_structure if len(s.get("geometry", [])) == 1]

    # ── DIFF: ghost removed elements at the back ───────────────────────────────
    if diff_on and before_layout:
        for (_rlvl, _eid) in _diff_removed:
            if not (_show_all or _rlvl == active_level):
                continue
            _bel = _before_el_map[(_rlvl, _eid)]
            _bg  = _bel.get("geometry", [])
            if len(_bg) == 2:
                traces.insert(0, go.Scatter(
                    x=[_bg[0][0], _bg[1][0]], y=[_bg[0][1], _bg[1][1]],
                    mode="lines", line=dict(color=REM_C, width=2.5, dash="dot"),
                    opacity=0.65, showlegend=False,
                    hovertemplate=f"<b>{_eid}</b><br><i>Removed</i><extra></extra>",
                ))
            elif len(_bg) == 1:
                traces.insert(0, go.Scatter(
                    x=[_bg[0][0]], y=[_bg[0][1]],
                    mode="markers",
                    marker=dict(color=REM_C, size=11, symbol="square-open",
                                line=dict(color=REM_C, width=2.5), opacity=0.75),
                    showlegend=False,
                    hovertemplate=f"<b>{_eid}</b><br><i>Removed</i><extra></extra>",
                ))

    # ── BEAMS ─────────────────────────────────────────────────────────────────
    for beam_level, beam in beams:
        eid   = beam["id"]
        geo   = beam["geometry"]
        p1, p2 = geo[0], geo[1]
        attrs = beam.get("attributes", {})
        mat   = attrs.get("material") or "—"
        sec   = (attrs.get("section") or
                 (f"{attrs.get('width','')}×{attrs.get('depth','')}"
                  if attrs.get("depth") else None) or "—")
        span  = round(_hm.dist(p1, p2), 2)

        status = el_status.get(eid, "none")
        # Diff colour overrides evaluation colour
        if (not _show_all) and beam_level != active_level:
            clr, lw = ACCENT, 1.2
        elif diff_on and (beam_level, eid) in _diff_added:
            clr, lw = ADD_C, 3.0
        elif diff_on and (beam_level, eid) in _diff_changed:
            clr, lw = MOD_C, 3.0
        else:
            clr = FAIL_C if status == "fail" else _material_color(mat, is_light)
            lw  = 4.5 if eid == highlight else 2.5
        if eid == highlight:
            clr = SEL_C
            lw  = 4.5
        _opacity = 1.0 if (_show_all or beam_level == active_level) else 0.28

        bev  = eval_map_b.get(eid, {})
        htxt = (
            f"<b>{eid}</b>  BEAM<br>"
            f"Level: {beam_level}<br>"
            f"Mat: {mat} · Sec: {sec} · Span: {span} m<br>"
            f"Status: {'✓ PASS' if status=='pass' else ('✗ FAIL' if status=='fail' else '—')}"
        )
        if bev:
            htxt += (f"<br>σ = {bev.get('sigma_bend_MPa','?')} MPa"
                     f"  δ = {bev.get('delta_total_mm','?')} mm")

        traces.append(go.Scatter(
            x=[p1[0], p2[0]], y=[p1[1], p2[1]],
            mode="lines",
            line=dict(color=clr, width=lw),
            opacity=_opacity,
            customdata=[[eid, "beam", beam_level], [eid, "beam", beam_level]],
            name=eid, showlegend=False,
            hovertemplate=htxt + "<extra></extra>",
        ))
        # Wide invisible hit-area: dense markers along the beam.
        _n   = max(13, int(span * 3) + 2)
        _hxs = [p1[0] + (p2[0] - p1[0]) * i / (_n - 1) for i in range(_n)]
        _hys = [p1[1] + (p2[1] - p1[1]) * i / (_n - 1) for i in range(_n)]
        traces.append(go.Scatter(
            x=_hxs, y=_hys,
            mode="markers",
            marker=dict(size=20, color=clr, opacity=0.001),
            customdata=[[eid, "beam", beam_level]] * _n,
            name=eid, showlegend=False,
            hovertemplate=htxt + "<extra></extra>",
        ))
        if labels and (_show_all or beam_level == active_level):
            mx, my = (p1[0]+p2[0])/2, (p1[1]+p2[1])/2
            annotations.append(dict(
                x=mx, y=my, text=eid, showarrow=False, yshift=7,
                font=dict(size=7, color=clr, family="monospace"),
            ))

    # ── COLUMNS ───────────────────────────────────────────────────────────────
    for col_level, col_el in cols:
        eid  = col_el["id"]
        geo  = col_el["geometry"]
        cx, cy = geo[0][0], geo[0][1]
        attrs = col_el.get("attributes", {})
        mat   = attrs.get("material") or "—"
        sec   = (attrs.get("section") or
                 (f"{attrs.get('width','')}×{attrs.get('depth','')}"
                  if attrs.get("depth") else None) or "—")

        status = el_status.get(eid, "none")
        if (not _show_all) and col_level != active_level:
            clr, sz = ACCENT, 8
        elif diff_on and (col_level, eid) in _diff_added:
            clr, sz = ADD_C, 12
        elif diff_on and (col_level, eid) in _diff_changed:
            clr, sz = MOD_C, 12
        else:
            clr = FAIL_C if status == "fail" else _material_color(mat, is_light)
            sz  = 16 if eid == highlight else 10
        if eid == highlight:
            clr = SEL_C
            sz  = 16
        _opacity = 1.0 if (_show_all or col_level == active_level) else 0.26

        cev  = eval_map_c.get(eid, {})
        htxt = (
            f"<b>{eid}</b>  COL<br>"
            f"Level: {col_level}<br>"
            f"Mat: {mat} · Sec: {sec}<br>"
            f"Status: {'✓ PASS' if status=='pass' else ('✗ FAIL' if status=='fail' else '—')}"
        )
        if cev:
            htxt += (f"<br>σ = {cev.get('sigma_comp_MPa','?')} MPa"
                     f"  SF = {cev.get('SF_buckling','?')}")

        traces.append(go.Scatter(
            x=[cx], y=[cy],
            mode="markers",
            marker=dict(color=clr, size=sz, symbol="square",
                        line=dict(color=BG, width=1.5)),
            opacity=_opacity,
            customdata=[[eid, "column", col_level]],
            name=eid, showlegend=False,
            hovertemplate=htxt + "<extra></extra>",
        ))
        # Large invisible hit-area for columns.
        traces.append(go.Scatter(
            x=[cx], y=[cy],
            mode="markers",
            marker=dict(size=32, color=clr, opacity=0.001),
            customdata=[[eid, "column", col_level]],
            name=eid, showlegend=False,
            hovertemplate=htxt + "<extra></extra>",
        ))
        if labels and (_show_all or col_level == active_level):
            annotations.append(dict(
                x=cx, y=cy, text=eid, showarrow=False, yshift=-14,
                font=dict(size=7, color=clr, family="monospace"),
            ))

    # ── AXIS BOUNDS ───────────────────────────────────────────────────────────
    all_pts: list = list(active_outline)
    for _key in ("rooms", "doors", "windows", "furniture"):
        for _el in level_payload.get(_key, []):
            all_pts.extend(_el.get("geometry", []))
    for _, _el in all_structure:
        all_pts.extend(_el.get("geometry", []))
    if all_pts:
        _axs  = [p[0] for p in all_pts]; _ays = [p[1] for p in all_pts]
        _span = max(max(_axs)-min(_axs), max(_ays)-min(_ays), 1)
        _pad  = _span * 0.06 + 0.3
        xr = [min(_axs)-_pad, max(_axs)+_pad]
        yr = [min(_ays)-_pad, max(_ays)+_pad]
    else:
        xr = yr = [0, 10]

    fig = go.Figure(data=traces)
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(range=xr, constrain="domain",
                   showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=yr, scaleanchor="x", scaleratio=1,
                   showgrid=False, zeroline=False, showticklabels=False),
        showlegend=False,
        hovermode="closest",
        # "zoom" mode: single click fires the select event on a point.
        # "select" mode requires a drag box — breaks individual click selection.
        dragmode="zoom",
        clickmode="event+select",
        annotations=annotations,
        # uirevision: stable key preserves zoom/pan.
        # Change it only when the layout version changes so zoom resets on new layouts.
        uirevision=f"plan-v{revision}",
    )
    return fig


def _render_floor_plan_html(
    layout: dict,
    eval_result: dict | None = None,
    highlight: str = "",
    level_key: str | None = None,
    labels: bool = False,
    height_px: int = 380,
    is_light: bool = False,
    view_mode: str = "2D",
    diff_on: bool = False,
    auto_on: bool = True,
) -> str:
    if is_light:
        BG     = "#f0f8f8"
        ROOM   = "#daeaea"
        FG     = "#1a3535"
        ACCENT = "#088a87"
        PASS_C = "#1a8050"
        FAIL_C = "#cc2020"
        SEL_C  = "#c07800"
        WIN_C  = "#2060a0"
    else:
        BG     = "#0c2020"
        ROOM   = "#172e2e"
        FG     = "#c8eeed"
        ACCENT = "#2ac0c0"
        PASS_C = "#40d090"
        FAIL_C = "#ff5050"
        SEL_C  = "#ffd060"
        WIN_C  = "#4696dc"

    _level_payload = _get_level_payload(layout, level_key)
    all_pts: list = list(get_outline(layout, level_key))
    for r in get_rooms(layout, level_key): all_pts.extend(r.get("geometry", []))
    for d in _level_payload.get("doors", []): all_pts.extend(d.get("geometry", []))
    for w in _level_payload.get("windows", []): all_pts.extend(w.get("geometry", []))
    for f in _level_payload.get("furniture", []): all_pts.extend(f.get("geometry", []))
    for s in get_structure(layout): all_pts.extend(s.get("geometry", []))

    if not all_pts:
        return (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            f'*{{margin:0;padding:0}}html,body{{background:{BG};height:100%;display:flex;'
            f'align-items:center;justify-content:center}}</style></head><body>'
            f'<span style="color:{ACCENT};font-family:monospace;font-size:.82rem">'
            f'Upload a layout JSON to view the plan</span></body></html>'
        )

    xs = [p[0] for p in all_pts]; ys = [p[1] for p in all_pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    span = max(x1 - x0, y1 - y0) or 1
    pad  = span * 0.07 + 0.5
    vb_x, vb_y = x0 - pad, y0 - pad
    vb_w, vb_h = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad

    def fy(y): return (y0 + y1) - y

    u = span * 0.012  # SVG-unit scalar for column radii and label sizes

    el_status: dict[str, str] = {}
    if eval_result:
        for b in eval_result.get("beams", []):
            ok = b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"]
            el_status[b["id"]] = "pass" if ok else "fail"
        for c in eval_result.get("columns", []):
            ok = c["stress_PASS"] and c["buckling_PASS"]
            el_status[c["id"]] = "pass" if ok else "fail"

    # Needed for score badges — define before the room loop
    _all_structure = get_structure(layout)

    parts: list[str] = []

    # ── ROOMS ──────────────────────────────────────────────────────────────────
    for room in get_rooms(layout, level_key):
        geo = room.get("geometry", [])
        if len(geo) < 3:
            continue
        pts_str = _svg_poly_points(geo, fy)
        cx, cy  = _svg_centroid(geo)
        w       = _svg_dims(geo)[0]
        label   = room.get("name", "")
        rid     = room.get("id", "")
        # Tooltip text for hover
        _area   = abs(sum(
            (geo[i][0]*geo[(i+1)%len(geo)][1] - geo[(i+1)%len(geo)][0]*geo[i][1])
            for i in range(len(geo))
        )) / 2
        _tip    = f"{label}&#10;Area: {_area:.1f} m²" if label else ""
        parts.append(
            f'<polygon data-room="{rid}" data-name="{label}" '
            f'points="{pts_str}" fill="{ROOM}" fill-opacity="0.88" '
            f'stroke="{FG}" stroke-opacity="0.22" stroke-width="0.8" '
            f'vector-effect="non-scaling-stroke" style="cursor:pointer">'
            + (f'<title>{_tip}</title>' if _tip else "")
            + f'</polygon>'
        )
        if label and w > u * 3:
            parts.append(
                f'<text x="{cx}" y="{fy(cy)}" text-anchor="middle" '
                f'dominant-baseline="central" font-family="monospace" '
                f'font-size="{u*1.05}" fill="{FG}" fill-opacity="0.55" '
                f'pointer-events="none">{label}</text>'
            )
        if el_status:
            _rxs = [p[0] for p in geo]; _rys = [p[1] for p in geo]
            _rx0, _rx1 = min(_rxs), max(_rxs)
            _ry0, _ry1 = min(_rys), max(_rys)
            _rpad = max(_rx1-_rx0, _ry1-_ry0, 0.1) * 0.12
            _near = []
            for _el in _all_structure:
                _eg = _el.get("geometry", [])
                _eid2 = _el.get("id", "")
                if _eid2 not in el_status:
                    continue
                if len(_eg) == 1:
                    if (_rx0-_rpad) <= _eg[0][0] <= (_rx1+_rpad) and (_ry0-_rpad) <= _eg[0][1] <= (_ry1+_rpad):
                        _near.append(el_status[_eid2])
                elif len(_eg) == 2:
                    _mx = (_eg[0][0]+_eg[1][0])/2; _my = (_eg[0][1]+_eg[1][1])/2
                    if (_rx0-_rpad) <= _mx <= (_rx1+_rpad) and (_ry0-_rpad) <= _my <= (_ry1+_rpad):
                        _near.append(el_status[_eid2])
            if _near:
                _rs = sum(1 for s in _near if s == "pass") / len(_near)
                _sc = "#40d090" if _rs >= 0.9 else ("#ffaa22" if _rs >= 0.5 else "#ff5050")
                _badge_y = fy(cy) + (u * 1.4 if label else 0)
                parts.append(
                    f'<text x="{cx}" y="{_badge_y}" text-anchor="middle" '
                    f'dominant-baseline="central" font-family="monospace" font-weight="700" '
                    f'font-size="{u*2.0}" fill="{_sc}" fill-opacity="0.72">'
                    f'{_rs:.2f}</text>'
                )

    # ── OUTLINE ────────────────────────────────────────────────────────────────
    outline = get_outline(layout, level_key)
    if len(outline) > 1:
        parts.append(
            f'<polyline points="{_svg_poly_points(outline, fy)}" fill="none" '
            f'stroke="{ACCENT}" stroke-opacity="0.8" stroke-width="1.5" '
            f'stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
        )

    # ── DOORS ──────────────────────────────────────────────────────────────────
    for door in layout.get("doors", []):
        geo = door.get("geometry", [])
        if len(geo) < 2:
            continue
        a, b = geo[0], geo[-1]
        ax, ay = a[0], fy(a[1])
        arc_pts = _door_swing_points(a, b, fy)
        arc_end = arc_pts.split(" ")[-1].split(",")
        parts.append(
            f'<line x1="{ax}" y1="{ay}" x2="{b[0]}" y2="{fy(b[1])}" '
            f'stroke="{BG}" stroke-width="4" vector-effect="non-scaling-stroke"/>'
        )
        parts.append(
            f'<polyline points="{arc_pts}" fill="none" stroke="{FG}" stroke-opacity="0.5" '
            f'stroke-width="0.8" stroke-dasharray="3 2" '
            f'vector-effect="non-scaling-stroke"/>'
        )
        parts.append(
            f'<line x1="{ax}" y1="{ay}" x2="{arc_end[0]}" y2="{arc_end[1]}" '
            f'stroke="{FG}" stroke-opacity="0.5" stroke-width="0.8" '
            f'vector-effect="non-scaling-stroke"/>'
        )

    # ── WINDOWS ────────────────────────────────────────────────────────────────
    for win in layout.get("windows", []):
        geo = win.get("geometry", [])
        if len(geo) >= 2:
            parts.append(
                f'<polyline points="{_svg_poly_points(geo, fy)}" fill="none" '
                f'stroke="{WIN_C}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>'
            )

    # ── FURNITURE ──────────────────────────────────────────────────────────────
    for furn in layout.get("furniture", []):
        geo = furn.get("geometry", [])
        if len(geo) >= 3:
            parts.append(
                f'<polygon points="{_svg_poly_points(geo, fy)}" fill="{FG}" fill-opacity="0.06" '
                f'stroke="{FG}" stroke-opacity="0.22" stroke-width="0.6" '
                f'vector-effect="non-scaling-stroke"/>'
            )

    # ── BEAMS ──────────────────────────────────────────────────────────────────
    # stroke-width values are in screen pixels (vector-effect="non-scaling-stroke")
    structure = _all_structure
    beams = [s for s in structure if len(s.get("geometry", [])) == 2]
    cols  = [s for s in structure if len(s.get("geometry", [])) == 1]

    for beam in beams:
        eid    = beam["id"]
        geo    = beam["geometry"]
        p1, p2 = geo[0], geo[1]
        status = el_status.get(eid, "none")
        stroke = FAIL_C if status == "fail" else (PASS_C if status == "pass" else ACCENT)
        is_sel = eid == highlight
        sw     = "3.5" if is_sel else "2"
        sc     = SEL_C if is_sel else stroke
        parts.append(
            f'<line data-eid="{eid}" x1="{p1[0]}" y1="{fy(p1[1])}" '
            f'x2="{p2[0]}" y2="{fy(p2[1])}" stroke="{sc}" '
            f'stroke-width="{sw}" stroke-linecap="round" '
            f'vector-effect="non-scaling-stroke" style="cursor:pointer"/>'
        )
        # Wide transparent hit area (12 px) for easy clicking
        parts.append(
            f'<line data-eid="{eid}" x1="{p1[0]}" y1="{fy(p1[1])}" '
            f'x2="{p2[0]}" y2="{fy(p2[1])}" stroke="transparent" '
            f'stroke-width="12" vector-effect="non-scaling-stroke" style="cursor:pointer"/>'
        )
        if labels:
            mx = (p1[0] + p2[0]) / 2
            my = (fy(p1[1]) + fy(p2[1])) / 2
            parts.append(
                f'<text x="{mx}" y="{my - u*0.6}" text-anchor="middle" '
                f'font-size="{u*0.85}" fill="{SEL_C if is_sel else stroke}" '
                f'font-family="monospace" pointer-events="none">{eid}</text>'
            )

    # ── COLUMNS ────────────────────────────────────────────────────────────────
    for col_el in cols:
        eid    = col_el["id"]
        geo    = col_el["geometry"]
        cx_c   = geo[0][0]
        cy_c   = fy(geo[0][1])
        status = el_status.get(eid, "none")
        fill   = FAIL_C if status == "fail" else (PASS_C if status == "pass" else ACCENT)
        is_sel = eid == highlight
        r_c    = u * (1.0 if is_sel else 0.75)
        parts.append(
            f'<circle data-eid="{eid}" cx="{cx_c}" cy="{cy_c}" r="{r_c}" '
            f'fill="{SEL_C if is_sel else fill}" fill-opacity="0.92" '
            f'stroke="{BG}" stroke-width="1" '
            f'vector-effect="non-scaling-stroke" style="cursor:pointer"/>'
        )
        if labels:
            parts.append(
                f'<text x="{cx_c}" y="{cy_c + r_c + u*0.8}" text-anchor="middle" '
                f'font-size="{u*0.85}" fill="{SEL_C if is_sel else fill}" '
                f'font-family="monospace" pointer-events="none">{eid}</text>'
            )

    # ── LEGEND ────────────────────────────────────────────────────────────────
    if el_status:
        lx  = vb_x + vb_w * 0.015
        ly  = vb_y + vb_h * 0.973
        dr  = u * 0.4
        gap = u * 3.8
        parts.append(
            f'<circle cx="{lx}" cy="{ly}" r="{dr}" fill="{PASS_C}"/>'
            f'<text x="{lx + dr*2.2}" y="{ly}" dominant-baseline="middle" '
            f'font-size="{u*0.82}" fill="#5a9898" font-family="monospace">pass</text>'
            f'<circle cx="{lx + gap}" cy="{ly}" r="{dr}" fill="{FAIL_C}"/>'
            f'<text x="{lx + gap + dr*2.2}" y="{ly}" dominant-baseline="middle" '
            f'font-size="{u*0.82}" fill="#5a9898" font-family="monospace">fail</text>'
        )

    svg_inner = "".join(parts)
    hl_json   = json.dumps(highlight)

    _tt_bg  = "rgba(20,50,50,0.92)" if not is_light else "rgba(230,245,245,0.96)"
    _tt_clr = "#c8eeed" if not is_light else "#1a2a30"
    _tt_brd = "#2ac0c0" if not is_light else "#088a87"

    # Toolbar overlay state
    _tb_vm_txt   = view_mode
    _tb_lab_js   = "true"  if labels   else "false"
    _tb_diff_js  = "true"  if diff_on  else "false"
    _tb_auto_js  = "true"  if auto_on  else "false"
    _tb_bg       = "rgba(7,26,26,0.82)"    if not is_light else "rgba(230,245,245,0.92)"
    _tb_brd      = "#1a4040"               if not is_light else "#c0d8d8"
    _tb_clr      = "#6ab8b8"              if not is_light else "#336868"
    _tb_act_clr  = "#2ac0c0"              if not is_light else "#088a87"
    _tb_act_bg   = "rgba(42,192,192,0.18)" if not is_light else "rgba(8,138,135,0.12)"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box }}
html, body {{ background:{BG}; overflow:hidden; width:100%; height:100% }}
svg {{ display:block; width:100%; height:{height_px}px; cursor:grab; user-select:none }}
svg.panning {{ cursor:grabbing }}
[data-eid] {{ cursor:pointer }}
[data-room] {{ cursor:pointer; transition: fill-opacity .15s; }}
[data-room]:hover {{ fill-opacity: .98 !important; filter: brightness(1.06); }}
#tt {{
  position:fixed; pointer-events:none; display:none;
  background:{_tt_bg}; color:{_tt_clr}; border:1px solid {_tt_brd};
  border-radius:6px; padding:6px 10px; font-size:11px; font-family:'Suisse Intl','Suisse Int\'l','Inter','Segoe UI',sans-serif;
  line-height:1.5; box-shadow:0 4px 16px rgba(0,0,0,.25); z-index:9999; max-width:180px;
  white-space:pre-line;
}}
#tt .tt-name {{ font-weight:700; font-size:12px; color:{_tt_brd}; margin-bottom:2px; }}
#vis-tb {{
  position:fixed; top:8px; right:8px; z-index:1000;
  display:flex; align-items:center; gap:2px;
  background:{_tb_bg}; border:1px solid {_tb_brd};
  border-radius:8px; padding:3px 5px;
  backdrop-filter:blur(6px);
}}
.tb-btn {{
  background:none; border:none; cursor:pointer;
  color:{_tb_clr}; font-size:.60rem; font-family:'Suisse Intl','Suisse Int\'l','Inter','Segoe UI',sans-serif;
  font-weight:700; letter-spacing:.6px; text-transform:uppercase;
  padding:3px 8px; border-radius:5px;
  transition:background .12s,color .12s;
}}
.tb-btn:hover {{ background:{_tb_act_bg}; color:{_tb_act_clr}; }}
.tb-btn.tb-on {{ background:{_tb_act_bg}; color:{_tb_act_clr}; }}
.tb-sep {{ width:1px; height:13px; background:{_tb_brd}; margin:0 3px; flex-shrink:0; }}
</style></head>
<body>
<div id="tt"><span class="tt-name" id="tt-name"></span><span id="tt-body"></span></div>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="{vb_x} {vb_y} {vb_w} {vb_h}"
     preserveAspectRatio="xMidYMid meet">
  <rect x="{vb_x}" y="{vb_y}" width="{vb_w}" height="{vb_h}" fill="{BG}"/>
  {svg_inner}
</svg>
<div id="vis-tb">
  <button id="tb-vm"   class="tb-btn" onclick="tbToggleVM()">{_tb_vm_txt}</button>
  <div class="tb-sep"></div>
  <button id="tb-lab"  class="tb-btn" onclick="tbToggleLabels()">Labels</button>
  <button id="tb-diff" class="tb-btn" onclick="tbToggleDiff()">Diff</button>
  <button id="tb-auto" class="tb-btn" onclick="tbToggleAuto()">Auto</button>
</div>
<script>
(function(){{
  // ── Toolbar state ──────────────────────────────────────────────────────────
  var _tbVM    = '{_tb_vm_txt}';
  var _tbLab   = {_tb_lab_js};
  var _tbDiff  = {_tb_diff_js};
  var _tbAuto  = {_tb_auto_js};

  function tbPost(key, val) {{
    window.parent.postMessage({{type:'toolbar', key:key, val:String(val)}}, '*');
  }}
  function tbUI() {{
    var bvm   = document.getElementById('tb-vm');
    var blab  = document.getElementById('tb-lab');
    var bdiff = document.getElementById('tb-diff');
    var bauto = document.getElementById('tb-auto');
    if(bvm)  {{ bvm.textContent = _tbVM; bvm.className  = 'tb-btn' + (_tbVM === '3D' ? ' tb-on' : ''); }}
    if(blab)  blab.className  = 'tb-btn' + (_tbLab  ? ' tb-on' : '');
    if(bdiff) bdiff.className = 'tb-btn' + (_tbDiff ? ' tb-on' : '');
    if(bauto) bauto.className = 'tb-btn' + (_tbAuto ? ' tb-on' : '');
  }}
  function tbToggleVM()     {{ _tbVM  = _tbVM==='2D'?'3D':'2D'; tbPost('vm',    _tbVM);           tbUI(); }}
  function tbToggleLabels() {{ _tbLab  = !_tbLab;               tbPost('labels', _tbLab?'1':'0'); tbUI(); }}
  function tbToggleDiff()   {{ _tbDiff = !_tbDiff;              tbPost('diff',   _tbDiff?'1':'0'); tbUI(); }}
  function tbToggleAuto()   {{ _tbAuto = !_tbAuto;              tbPost('auto',   _tbAuto?'1':'0'); tbUI(); }}
  tbUI();

  var HL = {hl_json};
  var svg = document.querySelector('svg');
  var tt  = document.getElementById('tt');
  var ttName = document.getElementById('tt-name');
  var ttBody = document.getElementById('tt-body');
  var vbArr = svg.getAttribute('viewBox').split(' ').map(Number);
  var origX = vbArr[0], origY = vbArr[1], origW = vbArr[2], origH = vbArr[3];
  var vbx = origX, vby = origY, vbw = origW, vbh = origH;

  function setVB(){{ svg.setAttribute('viewBox', vbx+' '+vby+' '+vbw+' '+vbh); }}

  // Restore highlight for already-selected element
  if(HL) {{
    document.querySelectorAll('[data-eid="'+HL+'"]').forEach(function(el){{
      if(el.getAttribute('stroke') !== 'transparent')
        el.style.filter = 'brightness(1.8) drop-shadow(0 0 3px {SEL_C})';
    }});
  }}

  // ── Room hover tooltip ────────────────────────────────────────────────────
  document.querySelectorAll('[data-room]').forEach(function(el){{
    var name = el.getAttribute('data-name') || '';
    el.addEventListener('mouseenter', function(e){{
      if(!name) return;
      ttName.textContent = name;
      // Try to extract area from title
      var titleEl = el.querySelector('title');
      var extra = titleEl ? titleEl.textContent.replace(name,'').replace(/^\\n/,'') : '';
      ttBody.textContent = extra;
      tt.style.display = 'block';
      positionTT(e);
    }});
    el.addEventListener('mousemove', positionTT);
    el.addEventListener('mouseleave', function(){{ tt.style.display = 'none'; }});
  }});

  function positionTT(e){{
    var x = e.clientX + 12, y = e.clientY + 12;
    var w = tt.offsetWidth, h = tt.offsetHeight;
    if(x + w > window.innerWidth  - 8) x = e.clientX - w - 8;
    if(y + h > window.innerHeight - 8) y = e.clientY - h - 8;
    tt.style.left = x + 'px';
    tt.style.top  = y + 'px';
  }}

  // ── Room click: flash highlight ───────────────────────────────────────────
  document.querySelectorAll('[data-room]').forEach(function(el){{
    el.addEventListener('click', function(e){{
      if(moved) return;
      // deselect structural elements
      document.querySelectorAll('[data-eid]').forEach(function(x){{ x.style.filter=''; }});
      el.style.filter = 'brightness(1.12) saturate(1.4)';
      setTimeout(function(){{ el.style.filter=''; }}, 600);
      window.parent.postMessage({{type:'selectElement', elementId:''}}, '*');
    }});
  }});

  // ── Zoom on wheel ─────────────────────────────────────────────────────────
  svg.addEventListener('wheel', function(e){{
    e.preventDefault();
    var rect = svg.getBoundingClientRect();
    var px = (e.clientX - rect.left) / rect.width;
    var py = (e.clientY - rect.top)  / rect.height;
    var factor = e.deltaY < 0 ? 0.87 : 1/0.87;
    var cx = vbx + px*vbw, cy = vby + py*vbh;
    vbw *= factor; vbh *= factor;
    vbx = cx - px*vbw; vby = cy - py*vbh;
    setVB();
  }}, {{passive:false}});

  // ── Pan on drag ───────────────────────────────────────────────────────────
  var drag = false, moved = false, lx, ly;
  svg.addEventListener('mousedown', function(e){{
    drag=true; moved=false; lx=e.clientX; ly=e.clientY;
    svg.classList.add('panning');
    tt.style.display = 'none';
  }});
  document.addEventListener('mousemove', function(e){{
    if(!drag) return;
    var dx=e.clientX-lx, dy=e.clientY-ly;
    if(Math.abs(dx)+Math.abs(dy) > 2) moved=true;
    var rect=svg.getBoundingClientRect();
    vbx -= dx*vbw/rect.width; vby -= dy*vbh/rect.height;
    lx=e.clientX; ly=e.clientY; setVB();
  }});
  document.addEventListener('mouseup', function(){{ drag=false; svg.classList.remove('panning'); }});

  // ── Double-click to reset zoom ────────────────────────────────────────────
  svg.addEventListener('dblclick', function(e){{
    if(!e.target.closest('[data-eid]') && !e.target.closest('[data-room]')){{
      vbx=origX; vby=origY; vbw=origW; vbh=origH; setVB();
    }}
  }});

  // ── Click structural elements ─────────────────────────────────────────────
  document.querySelectorAll('[data-eid]').forEach(function(el){{
    var id = el.getAttribute('data-eid');
    el.addEventListener('click', function(e){{
      if(moved) return;
      e.stopPropagation();
      document.querySelectorAll('[data-eid]').forEach(function(x){{ x.style.filter=''; }});
      document.querySelectorAll('[data-eid="'+id+'"]').forEach(function(x){{
        if(x.getAttribute('stroke') !== 'transparent')
          x.style.filter = 'brightness(1.8) drop-shadow(0 0 3px {SEL_C})';
      }});
      window.parent.postMessage({{type:'selectElement', elementId:id}}, '*');
    }});
  }});

  // ── Click empty to deselect ───────────────────────────────────────────────
  svg.addEventListener('click', function(e){{
    if(!moved && !e.target.closest('[data-eid]') && !e.target.closest('[data-room]')){{
      document.querySelectorAll('[data-eid]').forEach(function(x){{ x.style.filter=''; }});
      window.parent.postMessage({{type:'selectElement', elementId:''}}, '*');
    }}
  }});
}})();
</script>
</body></html>"""


def _render_3d_viewport(
        layout: dict,
        eval_result: dict | None,
        selected_el: str,
        active_level: str,
        is_light: bool,
        height: int = 512,
        before_layout: dict | None = None,
) -> str:
        level_keys = get_level_keys(layout)
        if not level_keys:
                level_keys = ["level_01"]

        status_by_id: dict[str, str] = {}
        if eval_result:
                for b in eval_result.get("beams", []):
                        b_ok = b.get("bend_PASS") and b.get("shear_PASS") and b.get("defl_TL_PASS") and b.get("defl_LL_PASS")
                        status_by_id[b.get("id", "")] = "pass" if b_ok else "fail"
                for c in eval_result.get("columns", []):
                        c_ok = c.get("stress_PASS") and c.get("buckling_PASS")
                        status_by_id[c.get("id", "")] = "pass" if c_ok else "fail"

        # Diff vs a baseline (Compare windows): added/changed recolour, removed render as ghosts.
        # Keys are "level|id" because element ids repeat across levels.
        diff_by_key: dict[str, str] = {}
        removed_payload: list[dict] = []
        if before_layout:
                _d = _compute_diff(before_layout, layout)
                for _k in _d["added"]:
                        diff_by_key[_k] = "added"
                for _k in _d["changed"]:
                        diff_by_key[_k] = "changed"
                _bkeys = get_level_keys(before_layout)
                for _k in _d["removed"]:
                        _lvl, _, _eid = _k.partition("|")
                        _el = next((e for e in get_structure(before_layout, _lvl)
                                    if e.get("id") == _eid), None)
                        if _el is None:
                                continue
                        removed_payload.append({
                                "geometry": _el.get("geometry", []),
                                "levelIdx": _bkeys.index(_lvl) if _lvl in _bkeys else 0,
                        })

        levels_payload: list[dict] = []
        for lk in level_keys:
                lvl_obj = _get_level_payload(layout, lk)
                levels_payload.append(
                        {
                                "key": lk,
                                "outline": get_outline(layout, lk),
                                "structure": get_structure(layout, lk),
                                "doors": lvl_obj.get("doors", []),
                                "windows": lvl_obj.get("windows", []),
                                "furniture": lvl_obj.get("furniture", []),
                        }
                )

        payload = {
                "levels": levels_payload,
                "activeLevel": active_level,
                "selected": selected_el or "",
                "statusById": status_by_id,
                "isLight": is_light,
                "diffByKey": diff_by_key,
                "removed": removed_payload,
        }
        data_json = json.dumps(payload)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <style>
        html, body {{ margin:0; padding:0; width:100%; height:100%; overflow:hidden; background:{'#f0f7f7' if is_light else '#071a1a'}; }}
        #root {{ position:relative; width:100%; height:{height}px; border:1px solid {'#c0d8d8' if is_light else '#1a4040'}; border-radius:8px; overflow:hidden; }}
        #cnv {{ width:100%; height:100%; display:block; }}
        #hud {{ position:absolute; top:10px; left:10px; z-index:5; color:{'#1a2a30' if is_light else '#c8eeed'}; font:600 11px/1.3 'Inter', 'Segoe UI', sans-serif; background:{'rgba(255,255,255,0.86)' if is_light else 'rgba(7,26,26,0.82)'}; border:1px solid {'#c0d8d8' if is_light else '#1a4040'}; border-radius:6px; padding:6px 8px; }}
        #cube {{ position:absolute; top:10px; right:10px; z-index:6; display:grid; grid-template-columns:1fr 1fr; gap:4px; }}
        .cube-btn {{ border:1px solid {'#c0d8d8' if is_light else '#1a4040'}; background:{'rgba(255,255,255,0.9)' if is_light else 'rgba(13,40,40,0.9)'}; color:{'#1a2a30' if is_light else '#c8eeed'}; border-radius:4px; padding:4px 7px; font:700 10px/1 'Inter', sans-serif; cursor:pointer; }}
        #err {{ position:absolute; inset:0; display:none; align-items:center; justify-content:center; color:{'#c02020' if is_light else '#ff8080'}; font:600 12px/1.4 'Inter', sans-serif; background:{'rgba(255,255,255,0.92)' if is_light else 'rgba(7,26,26,0.95)'}; padding:20px; text-align:center; }}
    </style>
    <script type=\"importmap\">{{
        \"imports\": {{
            \"three\": \"https://unpkg.com/three@0.166.1/build/three.module.js\",
            \"three/addons/\": \"https://unpkg.com/three@0.166.1/examples/jsm/\"
        }}
    }}</script>
</head>
<body>
    <div id=\"root\">
        <canvas id=\"cnv\"></canvas>
        <div id=\"hud\">3D BIM View<br/>Click element to inspect</div>
        <div id=\"cube\">
            <button class=\"cube-btn\" data-view=\"top\">TOP</button>
            <button class=\"cube-btn\" data-view=\"front\">FRONT</button>
            <button class=\"cube-btn\" data-view=\"right\">RIGHT</button>
            <button class=\"cube-btn\" data-view=\"iso\">ISO</button>
        </div>
        <div id=\"err\"></div>
    </div>
    <script type=\"module\">
        import * as THREE from 'three';
        import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

        const DATA = {data_json};
        const STOREY_H = 3.0;

        function showError(msg) {{
            const el = document.getElementById('err');
            el.textContent = msg;
            el.style.display = 'flex';
        }}

        try {{
            const root = document.getElementById('root');
            const canvas = document.getElementById('cnv');
            const renderer = new THREE.WebGLRenderer({{ canvas, antialias:true, alpha:true }});
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            renderer.setSize(root.clientWidth, root.clientHeight, false);

            const scene = new THREE.Scene();
            scene.background = new THREE.Color(DATA.isLight ? 0xf0f7f7 : 0x071a1a);

            const camera = new THREE.PerspectiveCamera(50, root.clientWidth / root.clientHeight, 0.01, 2000);
            camera.position.set(16, 14, 16);

            const controls = new OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.08;

            scene.add(new THREE.HemisphereLight(0xffffff, 0x1a1a1a, 0.95));
            const dir = new THREE.DirectionalLight(0xffffff, 0.6);
            dir.position.set(12, 20, 10);
            scene.add(dir);

            const grid = new THREE.GridHelper(80, 80, DATA.isLight ? 0x9cb3b3 : 0x264848, DATA.isLight ? 0xd3e3e3 : 0x163737);
            scene.add(grid);

            const pickables = [];
            const box = new THREE.Box3();
            const statusById = DATA.statusById || {{}};

            function matColor(mat) {{
                const m = (mat || '').toLowerCase();
                if (m.indexOf('steel') === 0) return 0x3f87d6;
                if (m.indexOf('timber') === 0 || m.indexOf('wood') === 0) return 0xcf8a3c;
                if (m.indexOf('rcc') === 0 || m.indexOf('concrete') === 0) return 0x9aa0a6;
                // Base (no material): white in dark mode, blue in light mode.
                return DATA.isLight ? 0x2563c0 : 0xffffff;
            }}
            function elColor(el, level) {{
                // Diff (Compare): added=green, changed=orange override everything.
                const d = (DATA.diffByKey || {{}})[level + '|' + el.id];
                if (d === 'added')   return 0x40d090;
                if (d === 'changed') return 0xffd060;
                // Failing elements show red; otherwise colour by material.
                if ((statusById[el.id] || 'none') === 'fail') return 0xff5050;
                return matColor((el.attributes || {{}}).material);
            }}

            function levelOpacity(level) {{
                if (DATA.activeLevel === '__ALL__') return 0.95;
                return level === DATA.activeLevel ? 0.95 : 0.28;
            }}

            function addSlab(level, idx, outline) {{
                if (!Array.isArray(outline) || outline.length < 3) return;
                const shape = new THREE.Shape();
                // Negate Y so that after the slab's -90deg X rotation (which maps shape-Y -> world -Z)
                // the slab footprint lands on world +Z, matching how columns/beams are placed
                // (world z = geometry y). Without this the slab is mirrored off the structure.
                shape.moveTo(outline[0][0], -outline[0][1]);
                for (let i = 1; i < outline.length; i++) shape.lineTo(outline[i][0], -outline[i][1]);
                const geo = new THREE.ExtrudeGeometry(shape, {{ depth: 0.18, bevelEnabled: false }});
                const mat = new THREE.MeshStandardMaterial({{
                    color: DATA.isLight ? 0xe8efef : 0x0f2f2f,
                    metalness: 0.05,
                    roughness: 0.86,
                    transparent: true,
                    opacity: levelOpacity(level),
                }});
                const slab = new THREE.Mesh(geo, mat);
                slab.rotation.x = -Math.PI / 2;
                slab.position.y = idx * STOREY_H;
                scene.add(slab);
                box.expandByObject(slab);
            }}

            function addColumn(level, idx, el) {{
                const pt = (el.geometry || [])[0];
                if (!pt) return;
                const geo = new THREE.BoxGeometry(0.32, STOREY_H, 0.32);
                const mat = new THREE.MeshStandardMaterial({{
                    color: elColor(el, level),
                    transparent: true,
                    opacity: levelOpacity(level),
                    emissive: 0x000000,
                }});
                const m = new THREE.Mesh(geo, mat);
                m.position.set(pt[0], idx * STOREY_H + STOREY_H * 0.5, pt[1]);
                m.userData = {{ id: el.id, level, type: 'column' }};
                scene.add(m);
                pickables.push(m);
                box.expandByObject(m);
            }}

            function addBeam(level, idx, el) {{
                const g = el.geometry || [];
                if (g.length < 2) return;
                const p1 = new THREE.Vector3(g[0][0], 0, g[0][1]);
                const p2 = new THREE.Vector3(g[1][0], 0, g[1][1]);
                const span = p1.distanceTo(p2);
                if (span <= 0.001) return;
                const geo = new THREE.BoxGeometry(span, 0.28, 0.22);
                const mat = new THREE.MeshStandardMaterial({{
                    color: elColor(el, level),
                    transparent: true,
                    opacity: levelOpacity(level),
                    emissive: 0x000000,
                }});
                const m = new THREE.Mesh(geo, mat);
                const mid = p1.clone().add(p2).multiplyScalar(0.5);
                m.position.set(mid.x, idx * STOREY_H + (STOREY_H - 0.25), mid.z);
                m.rotation.y = Math.atan2(p2.z - p1.z, p2.x - p1.x);
                m.userData = {{ id: el.id, level, type: 'beam' }};
                scene.add(m);
                pickables.push(m);
                box.expandByObject(m);
            }}

            (DATA.levels || []).forEach((lvl, idx) => {{
                addSlab(lvl.key, idx, lvl.outline || []);
                (lvl.structure || []).forEach((el) => {{
                    const g = el.geometry || [];
                    if (g.length === 1) addColumn(lvl.key, idx, el);
                    if (g.length === 2) addBeam(lvl.key, idx, el);
                }});
            }});

            // Removed elements (Compare diff): translucent red ghosts at their old position.
            (DATA.removed || []).forEach((r) => {{
                const g = r.geometry || [];
                const yBase = (r.levelIdx || 0) * STOREY_H;
                let mesh = null;
                if (g.length === 1) {{
                    mesh = new THREE.Mesh(
                        new THREE.BoxGeometry(0.32, STOREY_H, 0.32),
                        new THREE.MeshStandardMaterial({{ color:0xff5050, transparent:true, opacity:0.30 }}),
                    );
                    mesh.position.set(g[0][0], yBase + STOREY_H * 0.5, g[0][1]);
                }} else if (g.length === 2) {{
                    const p1 = new THREE.Vector3(g[0][0], 0, g[0][1]);
                    const p2 = new THREE.Vector3(g[1][0], 0, g[1][1]);
                    const span = p1.distanceTo(p2);
                    if (span <= 0.001) return;
                    mesh = new THREE.Mesh(
                        new THREE.BoxGeometry(span, 0.28, 0.22),
                        new THREE.MeshStandardMaterial({{ color:0xff5050, transparent:true, opacity:0.30 }}),
                    );
                    const mid = p1.clone().add(p2).multiplyScalar(0.5);
                    mesh.position.set(mid.x, yBase + (STOREY_H - 0.25), mid.z);
                    mesh.rotation.y = Math.atan2(p2.z - p1.z, p2.x - p1.x);
                }}
                if (mesh) {{ scene.add(mesh); box.expandByObject(mesh); }}
            }});

            const center = box.isEmpty() ? new THREE.Vector3(0, 0, 0) : box.getCenter(new THREE.Vector3());
            const size = box.isEmpty() ? new THREE.Vector3(10, 10, 10) : box.getSize(new THREE.Vector3());
            const radius = Math.max(size.x, size.y, size.z, 10);
            controls.target.copy(center);
            camera.position.set(center.x + radius * 0.9, center.y + radius * 0.7, center.z + radius * 0.9);
            controls.update();

            const ray = new THREE.Raycaster();
            const ptr = new THREE.Vector2();
            const hud = document.getElementById('hud');
            const HUD_DEFAULT = '3D BIM View<br/>Click element to inspect';
            let hovered = null;
            let selectedObj = null;

            function statusLabel(id) {{
                const s = statusById[id] || 'none';
                if (s === 'pass') return ['PASS', '#40d090'];
                if (s === 'fail') return ['FAIL', '#ff5050'];
                return ['not evaluated', DATA.isLight ? '#5a7070' : '#9ab'];
            }}

            // Instant, client-side inspector — fills the moment an element is clicked,
            // independent of the Streamlit round-trip that syncs the full Design Data panel.
            function showHud(obj) {{
                if (!obj) {{ hud.innerHTML = HUD_DEFAULT; return; }}
                const d = obj.userData || {{}};
                const [stxt, scol] = statusLabel(d.id || '');
                hud.innerHTML =
                    '<div style="font-weight:700;font-size:12px;margin-bottom:1px">' + (d.id || '?') + '</div>' +
                    '<div style="opacity:.85">' + (d.type || '') + (d.level ? ' &middot; ' + d.level : '') + '</div>' +
                    '<div style="color:' + scol + ';font-weight:700;margin-top:1px">' + stxt + '</div>' +
                    '<div style="opacity:.6;margin-top:2px">Full details &amp; remove in panel &rarr;</div>';
            }}

            // emissive priority: selected (amber) > hovered (indigo) > none
            function paint(obj) {{
                if (!obj || !obj.material) return;
                if (obj === selectedObj) obj.material.emissive.setHex(0xffb020);
                else if (obj === hovered) obj.material.emissive.setHex(0x4f46e5);
                else obj.material.emissive.setHex(0x000000);
            }}

            function setHover(obj) {{
                const prev = hovered;
                hovered = obj;
                paint(prev);
                paint(hovered);
                renderer.domElement.style.cursor = obj ? 'pointer' : 'default';
            }}

            function setSelected(obj) {{
                const prev = selectedObj;
                selectedObj = obj;
                paint(prev);
                paint(selectedObj);
                showHud(obj);
            }}

            function pointerToNdc(evt) {{
                const rect = renderer.domElement.getBoundingClientRect();
                ptr.x = ((evt.clientX - rect.left) / rect.width) * 2 - 1;
                ptr.y = -((evt.clientY - rect.top) / rect.height) * 2 + 1;
            }}

            renderer.domElement.addEventListener('pointermove', (evt) => {{
                pointerToNdc(evt);
                ray.setFromCamera(ptr, camera);
                const hit = ray.intersectObjects(pickables, false)[0];
                setHover(hit ? hit.object : null);
            }});

            renderer.domElement.addEventListener('click', (evt) => {{
                pointerToNdc(evt);
                ray.setFromCamera(ptr, camera);
                const hit = ray.intersectObjects(pickables, false)[0];
                if (!hit) {{
                    setSelected(null);
                    window.parent.postMessage({{ type:'selectElement', elementId:'', level:'' }}, '*');
                    return;
                }}
                const id = hit.object.userData?.id || '';
                const level = hit.object.userData?.level || '';
                setSelected(hit.object);   // instant feedback, no rerun wait
                window.parent.postMessage({{ type:'selectElement', elementId:id, level }}, '*');
            }});

            function lookFrom(v) {{
                const start = camera.position.clone();
                const end = center.clone().add(v.clone().multiplyScalar(radius * 1.25));
                const t0 = performance.now();
                const ms = 260;
                function step(t) {{
                    const k = Math.min((t - t0) / ms, 1);
                    const e = 1 - Math.pow(1 - k, 3);
                    camera.position.lerpVectors(start, end, e);
                    controls.target.copy(center);
                    controls.update();
                    if (k < 1) requestAnimationFrame(step);
                }}
                requestAnimationFrame(step);
            }}

            document.querySelectorAll('.cube-btn').forEach((btn) => {{
                btn.addEventListener('click', () => {{
                    const v = btn.getAttribute('data-view');
                    if (v === 'top') lookFrom(new THREE.Vector3(0, 1, 0.001));
                    if (v === 'front') lookFrom(new THREE.Vector3(0, 0.1, 1));
                    if (v === 'right') lookFrom(new THREE.Vector3(1, 0.1, 0));
                    if (v === 'iso') lookFrom(new THREE.Vector3(1, 0.7, 1));
                }});
            }});

            const selected = (DATA.selected || '').trim();
            if (selected) {{
                const target = pickables.find((m) => (m.userData?.id || '') === selected);
                if (target) setSelected(target);
            }}

            function onResize() {{
                const w = root.clientWidth;
                const h = root.clientHeight;
                camera.aspect = w / Math.max(h, 1);
                camera.updateProjectionMatrix();
                renderer.setSize(w, h, false);
            }}
            window.addEventListener('resize', onResize);

            function animate() {{
                controls.update();
                renderer.render(scene, camera);
                requestAnimationFrame(animate);
            }}
            animate();
        }} catch (err) {{
            showError('3D viewer failed to load. Check internet/CDN access for Three.js.');
            console.error(err);
        }}
    </script>
</body>
</html>"""


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



def _count_elements(layout: dict) -> tuple[int, int]:
    structure = get_structure(layout)
    cols  = sum(1 for el in structure if len(el.get("geometry", [])) == 1)
    beams = sum(1 for el in structure if len(el.get("geometry", [])) == 2)
    return cols, beams


def _present_legend_items(layout: dict, is_light: bool) -> list[tuple[str, str]]:
    """Legend entries for ONLY the element categories actually present in `layout`,
    so we never show Doors/Windows/Furniture when the JSON doesn't contain them."""
    items: list[tuple[str, str]] = []
    # iter_all_structure yields (level, element) tuples.
    struct = [e for _lvl, e in iter_all_structure(layout)] if layout else []
    has_col  = any(len(e.get("geometry", [])) == 1 for e in struct)
    has_beam = any(len(e.get("geometry", [])) == 2 for e in struct)

    def _has(cat: str) -> bool:
        if is_multilevel(layout):
            return any((_get_level_payload(layout, lk).get(cat) or [])
                       for lk in (get_level_keys(layout) or []))
        return bool(layout.get(cat))

    el_col = "#2563c0" if is_light else "#e8eef5"   # structural base: blue (light) / white (dark)
    if get_all_rooms(layout):  items.append(("#7cb2ff", "Rooms"))  # noqa: E701
    if has_col:                items.append((el_col, "Columns"))
    if has_beam:               items.append(("#ffd36a", "Beams"))
    if _has("walls"):          items.append(("#9aa7b2", "Walls"))
    if _has("doors"):          items.append(("#ff8a7a", "Doors"))
    if _has("windows"):        items.append(("#8ad4ff", "Windows"))
    if _has("furniture"):      items.append(("#9b7cff", "Furniture / MEP"))
    return items


# ── Material colour mapping (shared by 2D, 3D and the legend) ───────────────────
# Mid-tones chosen to read on both the light (#f0f8f8) and dark (#0c2020) canvases.
_MATERIAL_PALETTE = {
    "rcc":      ("#9aa0a6", "Concrete (RCC)"),
    "concrete": ("#9aa0a6", "Concrete (RCC)"),
    "steel":    ("#3f87d6", "Steel"),
    "timber":   ("#cf8a3c", "Timber"),
    "wood":     ("#cf8a3c", "Timber"),
}


def _material_key(material) -> str | None:
    m = (material or "").strip().lower()
    for k in ("concrete", "rcc", "steel", "timber", "wood"):
        if m.startswith(k):
            return k
    return None


def _material_color(material, is_light: bool) -> str:
    """Colour an element by its material; fall back to the white/blue base colour."""
    k = _material_key(material)
    if k:
        return _MATERIAL_PALETTE[k][0]
    return "#2563c0" if is_light else "#e8eef5"


def _materials_present(layout: dict) -> list[tuple[str, str]]:
    """(colour, label) for each material actually used in the layout, de-duplicated."""
    seen: dict[str, str] = {}
    if layout:
        for _lvl, e in iter_all_structure(layout):
            k = _material_key((e.get("attributes") or {}).get("material"))
            if k:
                col, label = _MATERIAL_PALETTE[k]
                seen[label] = col
    return [(c, l) for l, c in seen.items()]


def _material_legend_html(layout: dict, is_light: bool, mut: str) -> str:
    mats = _materials_present(layout)
    if not mats:
        return ""
    html = ('<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;'
            f'margin-top:4px;font-size:.60rem;color:{mut}">'
            '<span style="font-weight:700;text-transform:uppercase;letter-spacing:.5px">Material</span>')
    for col, label in mats:
        html += (
            f'<span style="display:flex;align-items:center;gap:4px">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:{col};'
            f'display:inline-block"></span>{label}</span>'
        )
    html += ('<span style="display:flex;align-items:center;gap:4px">'
             '<span style="width:10px;height:10px;border-radius:2px;background:#ff5050;'
             'display:inline-block"></span>Failing</span></div>')
    return html


def _el_detail_html(el_obj: dict, eval_result: dict | None) -> str:
    """SENSI-style element detail card with utilization bars."""
    import math as _math
    eid     = el_obj.get("id", "")
    attrs   = el_obj.get("attributes", {})
    is_beam = len(el_obj.get("geometry", [])) == 2
    el_type = "BEAM" if is_beam else "COL"
    mat     = attrs.get("material", "RCC")
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
            if b.get("id") != eid:
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
            if c.get("id") != eid:
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

        # Wrap each layout dict into the UI's expected format and stamp material.
        opts = []
        for lay in raw:
            lay_copy = dict(lay)
            if "meta" not in lay_copy or not isinstance(lay_copy.get("meta"), dict):
                lay_copy["meta"] = {}
            lay_copy["meta"]["material"] = material
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
        context_msg = {
            "role": "user",
            "content": (
                f"Context: Layout '{layout.get('layoutId', '?')}' has "
                f"{len(cols)} columns and {len(beams)} beams.{eval_lines}\n"
                f"Columns: {col_summary}\n"
                f"Beams: {beam_summary}\n\n"
                f"User request:\n{prompt}"
            ),
        }

        result = call_llm(ctx.llm, SYSTEM_PROMPT, [context_msg], tool_catalog)

        if result.get("action") == "tool":
            calls = result.get("tool_calls", [])
            # Advisory text from the agent (explanation + alternatives)
            _advisory = result.get("final_response", "").strip()
            if any(c.get("name") == "tag_and_audit" for c in calls):
                return "GENERATE_GRID" + (f"\n{_advisory}" if _advisory else "")
            for _c in calls:
                _cname  = _c.get("name", "")
                _cinput = _c.get("input", _c.get("arguments", {}))
                # Map modify_structure tool → local function signals
                if _cname == "modify_structure":
                    _ms_action = _cinput.get("action", "")
                    _ms_eid    = _cinput.get("element_id", "")
                    if _ms_action == "remove" and _ms_eid:
                        return f"APPLY_TOOL:{json.dumps({'name': 'remove_element', 'input': {'element_id': _ms_eid}})}"
                    if _ms_action == "set_attribute" and _ms_eid:
                        _ms_val = _cinput.get("value", "")
                        if _ms_val:
                            return f"APPLY_TOOL:{json.dumps({'name': 'upgrade_element_section', 'input': {'element_id': _ms_eid, 'new_section': _ms_val}})}"
                elif _cname == "evaluate_structure":
                    return "EVALUATE"
                elif _cname in {"remove_element", "add_midspan_column",
                                "upgrade_element_section"}:
                    _tool_payload = {"name": _cname, "input": _cinput, "advisory": _advisory}
                    return f"APPLY_TOOL:{json.dumps(_tool_payload)}"
            if calls:
                first = calls[0]
                return (
                    f"Agent wants to apply **{first.get('name', 'action')}** — "
                    "use the controls in the left panel to proceed."
                )

        resp = result.get("final_response", "")
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

            # ── Imperative removal — execute immediately ──────────────────────
            if _is_removal and not _is_explicit_whatif:
                if _ids_in_prompt:
                    _eid_exec = _rid(_ids_in_prompt[0])
                    return f"APPLY_TOOL:{json.dumps({'name': 'remove_element', 'input': {'element_id': _eid_exec}})}"
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
        "output_log":      [],
        "selected_el":     "",
        "active_level":    "level_01",
        "active_element_level": "",
        "_last_sel_applied": "\x00",
        "_last_lvl_applied": "\x00",
        "cmp_sel_indices": [],      # indices into snapshots list for compare tab
        "last_click_debug": {},
        "compare_mode":    False,
        "labels_on":       False,
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
_pending_sel = st.query_params.get("_sel", "")
if _pending_sel != st.session_state.get("_last_sel_applied", "\x00"):
    st.session_state.selected_el = _pending_sel
    st.session_state["_last_sel_applied"] = _pending_sel
_pending_lvl = st.query_params.get("_lvl", "")
if _pending_lvl != st.session_state.get("_last_lvl_applied", "\x00"):
    st.session_state.active_element_level = _pending_lvl
    if _pending_lvl:
        st.session_state.active_level = _pending_lvl
    st.session_state["_last_lvl_applied"] = _pending_lvl

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
- REMOVE any element: set action="tool", call remove_element. Include advisory in final_response.
- ADD midspan column: set action="tool", call add_midspan_column. Include advisory in final_response.
- UPGRADE a section: set action="tool", call upgrade_element_section. Include advisory in final_response.
- GENERATE structural grid: set action="tool", call tag_and_audit. Include advisory in final_response.
- MODIFY attributes: set action="tool", call modify_structure. Include advisory in final_response.

EVALUATION (user asks to evaluate, check structure, run analysis, run loads):
Set action="final", final_response="" (empty string). The evaluation runs automatically.

QUESTIONS (explain results, describe layout, interpret failures):
Set action="final" and write a clear, concise answer in final_response.
Use element IDs and values from the layout context. Never invent IDs.

Toolbox:
{tool_catalog}

Return strictly valid JSON:
{{"action": "final" | "tool", "final_response": "...", "tool_calls": [{{"name": "<tool>", "arguments": {{...}}}}]}}
Rules: JSON only, no markdown. If action is final: tool_calls must be []. If action is tool: BOTH final_response AND tool_calls must be filled.
"""

_is_light = st.session_state.get("theme", "dark") == "light"

if _is_light:
    _BG="#f0f7f7"; _SB="#e2eeee"; _CARD="#ffffff"; _ACC="#088a87"; _ACC2="#40a090"
    _BORD="#c0d8d8"; _TEXT="#1a2a30"; _MUT="#5a7070"; _DIM="#8aacac"
    _FAIL="#c02020"; _PASS_C="#097040"; _PASS_BG="#d0f4e8"; _FAIL_BG="#fce8e8"
    _CHAT_Q="#ddeef0"; _CHAT_A="#f0f9f9"; _NUM1_BG=_ACC; _NUM1_C="#fff"
    _NUM2_BG="#c07020"; _NUM3_BG="#3070a0"
    _HIGH_BG="#d4f0d4"; _HIGH_C="#1a7020"
    _MED_BG="#f4e4b0";  _MED_C="#806010"
    _LOW_BG="#c8ddf0";  _LOW_C="#2060a0"
    _LOAD_BG="#eef6f6"; _SNAP_BG="#e0eef0"
else:
    _BG="#071a1a"; _SB="#091f1f"; _CARD="#0d2828"; _ACC="#2ac0c0"; _ACC2="#222D28"
    _BORD="#1a4040"; _TEXT="#c8eeed"; _MUT="#5a9090"; _DIM="#3a6060"
    _FAIL="#ff5050"; _PASS_C="#40d090"; _PASS_BG="#0a3020"; _FAIL_BG="#300a0a"
    _CHAT_Q="#0a3030"; _CHAT_A="#071a1a"; _NUM1_BG=_ACC; _NUM1_C="#071a1a"
    _NUM2_BG="#c07020"; _NUM3_BG="#3070a0"
    _HIGH_BG="#0d2e0d"; _HIGH_C="#60d060"
    _MED_BG="#2e2400";  _MED_C="#d0a020"
    _LOW_BG="#0a1e30";  _LOW_C="#40a0c8"
    _LOAD_BG="#0d2020"; _SNAP_BG="#0d2020"

_F = "'Suisse Intl','Suisse Int\\'l','Inter','Segoe UI',system-ui,sans-serif"

_CSS = f"""
@import url('https://fonts.cdnfonts.com/css/suisse-intl');
/* ── Universal font: all text elements except icon spans ────────────────── */
html,body,p,h1,h2,h3,h4,h5,h6,
div,section,article,aside,header,main,footer,nav,
label,a,li,td,th,caption,
input,textarea,select,option,
button,
[data-testid]:not([data-testid="stIconMaterial"]){{
  font-family:{_F}!important;
  -webkit-font-smoothing:antialiased!important;
  -moz-osx-font-smoothing:grayscale!important;
}}
/* ── Restore Material Symbols for Streamlit icon spans ───────────────────── */
[data-testid="stIconMaterial"],
[class*="material-symbols"],
[class*="material-icons"]{{
  font-family:'Material Symbols Rounded','Material Symbols Sharp','Material Icons Rounded','Material Icons'!important;
  font-feature-settings:'liga'!important;
  -webkit-font-feature-settings:'liga'!important;
}}
/* ── Buttons: always fit text, no overflow ───────────────────────────────── */
button{{overflow:hidden!important}}
button>div,button p,button span:not([data-testid="stIconMaterial"]){{
  overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;
}}
/* ── Type scale (5 steps) ──────────────────────────────────────────────── */
/* xs=0.63rem  sm=0.70rem  md=0.78rem  lg=0.88rem  xl=1.0rem             */
html,body,[data-testid="stApp"],[data-testid="stAppViewContainer"],[data-testid="stMain"]{{
  background:{_BG}!important;font-family:{_F}!important;font-size:13px!important;
  letter-spacing:.01em!important}}
[data-testid="block-container"]{{padding:.3rem 1rem .2rem!important}}
section[data-testid="stSidebar"]{{
  background:{_SB}!important;border-right:1px solid {_BORD}!important;
  width:380px!important;min-width:380px!important;
  flex:0 0 380px!important}}
section[data-testid="stSidebar"]>div:first-child{{padding:14px 14px 10px!important}}
.react-resizable-handle{{display:none!important;pointer-events:none!important}}
[data-testid="stSidebarHeader"]{{display:none!important;height:0!important;padding:0!important;margin:0!important}}
section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] label{{color:{_TEXT}!important;font-family:{_F}!important}}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{{color:{_MUT}!important;font-size:.70rem!important}}
[data-testid="stHeader"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stToolbar"]{{display:none!important;height:0!important;overflow:hidden!important;padding:0!important;margin:0!important}}
/* ── Tabs ──────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"]{{background:transparent!important;border-bottom:1px solid {_BORD}!important;gap:0!important;padding:0!important;display:flex!important}}
[data-testid="stTabs"] [data-baseweb="tab"]{{flex:1!important;text-align:center!important;justify-content:center!important;color:{_MUT}!important;font-size:.63rem!important;font-weight:700!important;letter-spacing:1.4px!important;text-transform:uppercase!important;padding:6px 8px!important;border-bottom:2px solid transparent!important;background:transparent!important;font-family:{_F}!important}}
[data-testid="stTabs"] [aria-selected="true"]{{color:{_ACC}!important;border-bottom:2px solid {_ACC}!important}}
[data-testid="stTabs"] [data-baseweb="tab-border"]{{display:none!important}}
[data-testid="stTabPanel"]{{padding-top:6px!important}}
/* ── Form elements ─────────────────────────────────────────────────────── */
[data-testid="stForm"]{{background:{_CARD}!important;border:1px solid {_BORD}!important;border-radius:8px!important;padding:8px!important}}
[data-testid="stTextArea"] textarea{{background:{_CARD}!important;color:{_TEXT}!important;border-color:{_BORD}!important;font-size:.70rem!important;font-family:{_F}!important}}
[data-testid="stTextInput"] input{{background:{_CARD}!important;color:{_TEXT}!important;border-color:{_BORD}!important;font-family:{_F}!important}}
[data-baseweb="select"]>div{{background:{_CARD}!important;border-color:{_BORD}!important;color:{_TEXT}!important;font-family:{_F}!important}}
[data-baseweb="popover"] [role="listbox"]{{background:{_CARD}!important}}
[data-baseweb="popover"] [role="option"]{{color:{_TEXT}!important;font-family:{_F}!important}}
[data-testid="stExpander"] details{{background:{_CARD}!important;border:1px solid {_BORD}!important;border-radius:6px!important}}
[data-testid="stExpander"] summary{{color:{_ACC}!important;font-size:.70rem!important;font-weight:600!important;font-family:{_F}!important}}
/* ── INPUTS dropdown button ────────────────────────────────────────────── */
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type details{{
  background:{_ACC}!important;border:none!important;border-radius:8px!important}}
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type summary{{
  color:#ffffff!important;font-size:.78rem!important;
  font-weight:800!important;letter-spacing:1.2px!important;text-transform:uppercase!important;
  padding:10px 14px!important;font-family:{_F}!important}}
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type details[open]{{
  background:{_CARD}!important;border:1px solid {_ACC}!important}}
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type details[open] summary{{
  color:{_ACC}!important;border-bottom:1px solid {_BORD}!important;margin-bottom:4px!important}}
.inp-sub-hdr{{font-size:.63rem;font-weight:700;color:{_ACC};letter-spacing:1.1px;font-family:{_F};
  text-transform:uppercase;margin:4px 0 6px;padding-bottom:3px;border-bottom:1px solid {_BORD}}}
[data-testid="stFileUploader"] section{{background:{_CARD}!important;border-color:{_BORD}!important}}
[data-testid="stFileUploaderDropzoneInstructions"]{{display:none!important}}
[data-testid="stFileUploaderDropzone"]{{min-height:auto!important;padding:5px 10px!important;background:{_CARD}!important;border-color:{_BORD}!important}}
[data-testid="stRadio"] label p{{color:{_TEXT}!important;font-size:.70rem!important;font-family:{_F}!important}}
[data-testid="stCheckbox"] label p{{color:{_TEXT}!important;font-size:.70rem!important;font-family:{_F}!important}}
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"]{{background:{_ACC}!important}}
p,label{{color:{_TEXT};font-family:{_F}}}
[data-testid="stMarkdown"] p{{color:{_TEXT};font-family:{_F}}}
small,[data-testid="stCaption"] p{{color:{_MUT}!important;font-size:.63rem!important;font-family:{_F}!important}}
[data-testid="stMetricValue"]{{color:{_TEXT}!important;font-size:.88rem!important;font-family:{_F}!important}}
[data-testid="stMetricLabel"] p{{color:{_MUT}!important;font-size:.63rem!important;font-family:{_F}!important}}
hr{{border-color:{_BORD}!important;margin:8px 0!important}}
button[kind="primary"]{{background:{_ACC}!important;color:#ffffff!important;border:none!important;font-weight:700!important;font-size:.70rem!important;border-radius:6px!important;font-family:{_F}!important;letter-spacing:.3px!important}}
button[kind="secondary"]{{background:transparent!important;color:{_TEXT}!important;border:1px solid {_BORD}!important;font-size:.70rem!important;border-radius:6px!important;font-family:{_F}!important}}
[data-testid="stFormSubmitButton"] button{{color:#ffffff!important}}
/* ── INPUTS expander label ────────────────────────────────────────────── */
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type summary{{
  color:#ffffff!important}}
/* ── Sidebar components ────────────────────────────────────────────────── */
.sb-brand{{font-size:.88rem;font-weight:800;color:{_ACC};letter-spacing:.8px;line-height:1.1;font-family:{_F}}}
.sb-sub{{font-size:.63rem;color:{_MUT};margin-bottom:10px;font-family:{_F}}}
.sb-section{{font-size:.63rem;font-weight:700;color:{_ACC};letter-spacing:1.5px;text-transform:uppercase;margin:12px 0 5px;display:flex;align-items:center;gap:6px;font-family:{_F}}}
.sb-section::after{{content:'';flex:1;height:1px;background:{_BORD}}}
.sb-filename{{font-size:.70rem;font-weight:600;color:{_TEXT};margin:3px 0 1px;font-family:{_F}}}
.sb-success{{font-size:.63rem;color:{_ACC2};font-weight:600;font-family:{_F}}}
.beta{{background:{"#d4f0ee" if _is_light else "#0a3030"};color:{_ACC};font-size:.60rem;font-weight:700;padding:1px 5px;border-radius:3px;vertical-align:middle;margin-left:4px;text-transform:uppercase;letter-spacing:.5px;border:1px solid {_BORD};font-family:{_F}}}
.load-row{{display:flex;justify-content:space-between;font-size:.70rem;padding:3px 0;border-bottom:1px solid {_BORD};color:{_MUT};font-family:{_F}}}
.load-row b{{color:{_TEXT};font-weight:600}}
.load-block{{background:{_LOAD_BG};border:1px solid {_BORD};border-radius:6px;padding:8px 10px}}
/* ── Page header ───────────────────────────────────────────────────────── */
.page-hdr{{display:flex;align-items:center;gap:4px;padding:4px 0 3px;font-family:{_F}}}
.hdr-lid{{font-size:.70rem;color:{_MUT};margin-right:6px;font-family:{_F}}}
.stat-chip{{display:inline-block;background:{"#e8f4f4" if _is_light else "#0d3030"};border:1px solid {_BORD};border-radius:4px;padding:2px 7px;margin-left:3px;font-size:.63rem;color:{_MUT};font-family:{_F}}}
.stat-chip b{{color:{_ACC}}}
.needs-review{{background:{"#fff0e8" if _is_light else "#3a1a08"}!important;color:{"#c04010" if _is_light else "#ff9860"}!important;border-color:{"#d08060" if _is_light else "#7a4020"}!important}}
/* ── Step bar ──────────────────────────────────────────────────────────── */
.step-bar{{display:flex;align-items:center;gap:0;overflow:hidden;padding:2px 0;font-family:{_F}}}
.stp{{display:flex;align-items:center;gap:4px;padding:3px 5px;white-space:nowrap;min-width:0}}
.stp-n{{display:inline-flex;width:20px;height:20px;border-radius:50%;font-size:.60rem;font-weight:800;align-items:center;justify-content:center;flex-shrink:0;font-family:{_F}}}
.stp-done .stp-n{{background:{_ACC};color:{"#fff" if _is_light else "#071a1a"}}}
.stp-active .stp-n{{background:{"#fff" if _is_light else "#0d2828"};color:{_ACC};border:2px solid {_ACC}}}
.stp-todo .stp-n{{background:{"#dde8e8" if _is_light else "#1a3030"};color:{_MUT}}}
.stp-lbl{{font-size:.63rem;font-weight:600;font-family:{_F}}}
.stp-done .stp-lbl{{color:{_TEXT}}}
.stp-active .stp-lbl{{color:{_ACC};font-weight:700}}
.stp-todo .stp-lbl{{color:{_MUT}}}
.stp-sub{{font-size:.60rem;color:{_MUT};font-family:{_F}}}
.stp-arr{{color:{_BORD};font-size:.63rem;margin:0 0px;flex-shrink:0}}
/* ── Plan legend ───────────────────────────────────────────────────────── */
.plan-legend{{display:flex;gap:12px;padding:5px 4px 3px;flex-wrap:wrap;font-family:{_F}}}
.leg-item{{display:flex;align-items:center;gap:4px;font-size:.63rem;color:{_MUT}}}
.leg-col{{width:9px;height:9px;border-radius:50%;background:{_ACC};flex-shrink:0}}
.leg-beam{{width:14px;height:3px;background:{_ACC2};flex-shrink:0;border-radius:1px}}
.leg-wall{{width:14px;height:3px;background:{"#889898" if _is_light else "#445858"};flex-shrink:0}}
.leg-dash{{width:14px;height:0;border-top:2px dashed {_MUT};flex-shrink:0}}
.stat-bar{{background:{_CARD};border:1px solid {_BORD};border-radius:6px;padding:6px 12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:4px;font-family:{_F}}}
.sb-i{{font-size:.63rem;color:{_MUT};white-space:nowrap;font-family:{_F}}}
.sb-i b{{color:{_TEXT};font-weight:600}}
.sb-pass{{background:{_PASS_BG};color:{_PASS_C};font-size:.63rem;font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap;font-family:{_F}}}
.sb-fail{{background:{_FAIL_BG};color:{_FAIL};font-size:.63rem;font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap;font-family:{_F}}}
.sb-pend{{color:{_MUT};font-size:.63rem;font-family:{_F}}}
/* ── Panel header ──────────────────────────────────────────────────────── */
.panel-hdr{{font-size:.60rem;font-weight:700;color:{_ACC};letter-spacing:1.4px;text-transform:uppercase;margin:4px 0 7px;display:flex;align-items:center;gap:6px;font-family:{_F}}}
.panel-hdr::after{{content:'';flex:1;height:1px;background:{_BORD}}}
/* ── Recommendation cards ──────────────────────────────────────────────── */
.rec-card{{background:{_CARD};border:1px solid {_BORD};border-radius:8px;padding:12px;margin-bottom:9px;font-family:{_F}}}
.rec-top{{display:flex;align-items:center;gap:6px;margin-bottom:4px}}
.rec-n{{display:inline-flex;width:22px;height:22px;border-radius:50%;font-size:.63rem;font-weight:800;align-items:center;justify-content:center;flex-shrink:0;color:#fff;font-family:{_F}}}
.rec-title{{font-size:.78rem;font-weight:700;color:{_TEXT};flex:1;min-width:0;font-family:{_F}}}
.imp-high{{background:{_HIGH_BG};color:{_HIGH_C};font-size:.60rem;font-weight:700;padding:2px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;font-family:{_F}}}
.imp-med{{background:{_MED_BG};color:{_MED_C};font-size:.60rem;font-weight:700;padding:2px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;font-family:{_F}}}
.imp-low{{background:{_LOW_BG};color:{_LOW_C};font-size:.60rem;font-weight:700;padding:2px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;font-family:{_F}}}
.rec-desc{{font-size:.70rem;color:{_MUT};line-height:1.4;margin-bottom:8px;font-family:{_F}}}
.rec-metrics{{display:flex;gap:0;border-top:1px solid {_BORD};padding-top:8px;margin-bottom:8px}}
.rec-met{{flex:1;text-align:center}}
.rec-met-lbl{{font-size:.60rem;color:{_MUT};text-transform:uppercase;letter-spacing:.3px;margin-bottom:1px;font-family:{_F}}}
.rec-met-pos{{font-size:.70rem;font-weight:700;color:{_PASS_C};font-family:{_F}}}
.rec-met-neg{{font-size:.70rem;font-weight:700;color:{_FAIL};font-family:{_F}}}
/* ── Chat & agent ──────────────────────────────────────────────────────── */
.chat-q{{background:{_CHAT_Q};border-left:3px solid {_ACC};border-radius:3px;padding:5px 8px;margin-bottom:4px;font-size:.80rem;color:{_TEXT};line-height:1.5;font-family:{_F}}}
.chat-a{{background:{_CHAT_A};border-left:3px solid {_ACC2};border-radius:3px;padding:5px 8px;margin-bottom:4px;font-size:.80rem;color:{_TEXT};line-height:1.5;font-family:{_F}}}
.agent-resp{{background:{_CHAT_Q};border-left:3px solid {_ACC};padding:8px 10px;border-radius:3px;font-size:.80rem;color:{_TEXT};line-height:1.6;margin-top:5px;font-family:{_F}}}
/* ── Element & analysis ────────────────────────────────────────────────── */
.crit-item{{background:{"#fff4f4" if _is_light else "#200808"};border-left:3px solid {"#cc2020" if _is_light else "#aa2020"};padding:4px 7px;margin-bottom:3px;border-radius:2px;font-size:.70rem;color:{_TEXT};cursor:pointer;font-family:{_F}}}
.pass-badge{{background:{_PASS_BG};color:{_PASS_C};padding:2px 8px;border-radius:4px;font-weight:700;font-size:.70rem;display:inline-block;margin:3px 0;font-family:{_F}}}
.hist-item{{display:flex;gap:8px;margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid {_BORD};font-family:{_F}}}
.hist-dot{{width:7px;height:7px;border-radius:50%;background:{_ACC};margin-top:4px;flex-shrink:0}}
.hist-label{{font-size:.70rem;color:{_TEXT};font-weight:600;font-family:{_F}}}
.hist-sub{{font-size:.63rem;color:{_MUT};font-family:{_F}}}
.log-entry{{background:{_CARD};border-left:3px solid {_ACC};padding:4px 7px;margin-bottom:3px;border-radius:3px;font-size:.70rem;color:{_TEXT};font-family:{_F}}}
/* ── Grid option cards ─────────────────────────────────────────────────── */
.grid-card{{border:1px solid {_BORD};border-radius:6px;padding:6px 9px;margin-bottom:4px;background:{_CARD};font-family:{_F}}}
.grid-card-active{{border-color:{_ACC};background:{"#ddf4f4" if _is_light else "#0d3030"}}}
.grid-label{{font-size:.78rem;font-weight:700;color:{_TEXT};font-family:{_F}}}
.grid-spacing{{font-size:.63rem;color:{_MUT};font-family:{_F}}}
.fail-ct{{color:{_FAIL};font-weight:700}}.pass-ct{{color:{_PASS_C};font-weight:700}}
.snap-pill{{display:inline-block;background:{_SNAP_BG};border:1px solid {_BORD};color:{_MUT};padding:2px 8px;border-radius:10px;margin:2px;font-size:.63rem;font-family:{_F}}}
.snap-pill-active{{border-color:{_ACC};color:{_ACC};font-weight:700}}
/* ── Compare cards ─────────────────────────────────────────────────────── */
.cmp-card-hdr{{background:{"#eef7f7" if _is_light else "#0d2828"};border-bottom:1px solid {_BORD};padding:6px 11px;display:flex;justify-content:space-between;align-items:center;font-family:{_F}}}
.cmp-title{{font-size:.70rem;font-weight:700;color:{_TEXT};font-family:{_F}}}
.badge-curr{{background:{"#d0ecec" if _is_light else "#0d3030"};color:{_ACC};font-size:.60rem;padding:2px 7px;border-radius:8px;font-family:{_F}}}
.badge-opt{{background:{_HIGH_BG};color:{_HIGH_C};font-size:.60rem;padding:2px 7px;border-radius:8px;font-family:{_F}}}
.insight-card{{background:{_CARD};border:1px solid {_BORD};border-radius:8px;padding:10px 12px;margin-bottom:6px;display:flex;align-items:flex-start;gap:10px;font-family:{_F}}}
.insight-ico{{font-size:1.0rem;margin-top:1px}}
.insight-lbl{{font-size:.60rem;color:{_MUT};text-transform:uppercase;letter-spacing:.3px;font-family:{_F}}}
.insight-opt{{font-size:.78rem;font-weight:700;color:{_TEXT};font-family:{_F}}}
.insight-det{{font-size:.63rem;color:{_MUT};font-family:{_F}}}
.rec-box{{background:{_HIGH_BG};border:1px solid {"#90c8a0" if _is_light else "#1a5020"};border-radius:8px;padding:11px;margin-top:7px;font-family:{_F}}}
.rec-box-lbl{{font-size:.60rem;color:{_HIGH_C};text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:4px;font-family:{_F}}}
.rec-box-txt{{font-size:.70rem;color:{_TEXT};line-height:1.5;font-family:{_F}}}
/* ── Compare table ─────────────────────────────────────────────────────── */
.cmp-tbl{{width:100%;border-collapse:collapse;border:1px solid {_BORD};border-radius:8px;overflow:hidden;font-family:{_F}}}
.cmp-tbl th{{padding:6px 10px;background:{_CARD};border-bottom:1px solid {_BORD};font-size:.63rem;color:{_MUT};text-transform:uppercase;letter-spacing:.6px;text-align:center;font-family:{_F}}}
.cmp-tbl th:first-child{{text-align:left}}
.cmp-tbl td{{padding:6px 10px;font-size:.70rem;text-align:center;border-bottom:1px solid {_BORD};font-family:{_F}}}
.cmp-tbl td:first-child{{text-align:left;color:{_MUT};font-size:.63rem;font-weight:600}}
.cmp-best{{color:{_PASS_C};font-weight:700}}
.cmp-norm{{color:{_TEXT};font-weight:600}}
/* ── Layout ────────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"]{{overflow-x:hidden!important}}
[data-testid="stMainBlockContainer"]{{padding:.4rem .8rem .4rem!important;max-width:100%!important}}
[data-testid="block-container"]{{padding:.4rem .8rem .4rem!important;max-width:100%!important}}
/* ── Static sidebar ────────────────────────────────────────────────────── */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
button[aria-label="Close sidebar"],
button[aria-label="Open sidebar"],
button[aria-label="collapse"],
button[aria-label="expand"]{{display:none!important;pointer-events:none!important}}
section[data-testid="stSidebar"]{{
  width:380px!important;min-width:380px!important;max-width:380px!important;
  transform:translateX(0)!important;transition:none!important;visibility:visible!important}}
section[data-testid="stSidebar"]>div:first-child{{
  width:380px!important;padding:12px 16px 10px!important;overflow-y:auto!important}}
.inp-toggle button{{
  padding:1px 6px!important;min-height:unset!important;font-size:.70rem!important;
  background:transparent!important;border:1px solid {_BORD}!important;
  color:{_MUT}!important;border-radius:4px!important;line-height:1.4!important;font-family:{_F}!important}}
/* ── Compare tab: slightly narrower sidebar to give more room ─────── */
body:has([role="tablist"] [role="tab"]:nth-child(2)[aria-selected="true"])
  [data-testid="stMainBlockContainer"]{{padding-left:.4rem!important;max-width:100%!important}}
"""

st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

# ─── JS bridge ────────────────────────────────────────────────────────────────
st.html("""
<script>
(function(){
  if(window._selBridgeReady)return;window._selBridgeReady=true;
  function _rerun(url){
    window.parent.history.replaceState(null,'',url.toString());
    window.parent.dispatchEvent(new PopStateEvent('popstate',{state:null}));
    setTimeout(function(){window.parent.dispatchEvent(new PopStateEvent('popstate',{state:null}));},40);
  }
  window.parent.addEventListener('message',function(ev){
    if(!ev.data||!ev.data.type)return;
    var url=new URL(window.parent.location.href);
    if(ev.data.type==='selectElement'){
      var eid=ev.data.elementId||'';
            var lvl=ev.data.level||'';
      var prev=url.searchParams.get('_sel')||'';
            var prevLvl=url.searchParams.get('_lvl')||'';
            if(eid===prev && lvl===prevLvl)return;
      if(eid){url.searchParams.set('_sel',eid);}else{url.searchParams.delete('_sel');}
            if(lvl){url.searchParams.set('_lvl',lvl);}else{url.searchParams.delete('_lvl');}
      _rerun(url);
    } else if(ev.data.type==='toolbar'){
      url.searchParams.set('_tb_'+ev.data.key, ev.data.val);
      _rerun(url);
    } else if(ev.data.type==='agentQuery'){
      url.searchParams.set('_aq', ev.data.text.slice(0,600));
      _rerun(url);
    }
  });
})();
</script>""", unsafe_allow_javascript=True, width="content")


# ─── layout data ──────────────────────────────────────────────────────────────
# currentLayout in session state is the authoritative source.
# On first load after a browser refresh we recover from disk (if the user had
# previously uploaded) so they don't lose work on an accidental refresh.
if st.session_state.currentLayout is None and EDITED_LAYOUT_PATH.exists():
    _recovered = _load_working_layout()
    if _recovered:
        st.session_state.currentLayout = _recovered
        st.session_state.setupDone = True   # disk file = previously committed

layout_obj      = st.session_state.currentLayout or {}
_level_keys_now = get_level_keys(layout_obj) if layout_obj else ["level_01"]
if st.session_state.get("active_level") not in _level_keys_now:
    st.session_state.active_level = _level_keys_now[0] if _level_keys_now else "level_01"
n_cols, n_beams = _count_elements(layout_obj)
er              = st.session_state.eval_result
_sm             = (er or {}).get("summary", {})
_has_fail       = _sm.get("beam_failures", 0) > 0 or _sm.get("column_failures", 0) > 0
_mat_now        = st.session_state.material
_sdl_now        = st.session_state.sdl_kNm2
_ll_now         = st.session_state.live_load_kNm2

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
                    _push_version(json.loads(_aq_rem(json.dumps(layout_obj), _aq_eid)))
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
                    _push_version(json.loads(_aq_ups(json.dumps(layout_obj), _aq_uid)))
                    _aq_resp = f"Upgraded section of **{_aq_uid}**."
        except Exception as _aq_tex:
            _aq_resp = f"Tool execution failed: {_aq_tex}"
    st.session_state.history.append({"prompt": _aq_raw, "response": _aq_resp})

_drawer_bg    = "#ffffff" if _is_light else "#0d2828"
_drawer_bord  = "#c0d8d8" if _is_light else "#1a4040"
_drawer_text  = "#1a2a30" if _is_light else "#c8eeed"
_drawer_acc   = "#088a87" if _is_light else "#2ac0c0"
_drawer_mut   = "#5a7070" if _is_light else "#5a9090"
_drawer_btn_c = "#ffffff" if _is_light else "#071a1a"

_drawer_history_html = ""
for _dh in st.session_state.get("history", [])[-3:]:
    _dq = str(_dh.get("prompt", "")).replace("<", "&lt;").replace(">", "&gt;")
    _da = str(_dh.get("response", "")).replace("<", "&lt;").replace(">", "&gt;")
    _drawer_history_html += f'<div class="dq">You: {_dq}</div><div>{_da}</div>'
_hist_js = json.dumps(_drawer_history_html)

st.html(f"""<script>
(function(){{
  var par = window.parent.document;
  var win = window.parent;
  var _hh = {_hist_js};

  // Always re-inject or update styles so they survive Streamlit hot-reloads
  var _sid = 'agent-drawer-styles';
  var _oldStyle = par.getElementById(_sid);
  if(_oldStyle) _oldStyle.remove();
  var style = par.createElement('style');
  style.id = _sid;
  style.textContent =
    '#agent-drawer{{position:fixed;top:50%;right:0;transform:translateY(-50%) translateX(100%);transition:transform 0.28s cubic-bezier(.4,0,.2,1);width:290px;z-index:99999;background:{_drawer_bg};border:1px solid {_drawer_bord};border-right:none;border-radius:12px 0 0 12px;box-shadow:-6px 0 24px rgba(0,0,0,0.4);font-family:\'Suisse Intl\',\'Inter\',sans-serif;}}'
    +'#agent-drawer.open{{transform:translateY(-50%) translateX(0);}}'
    +'#agent-drawer-tab{{position:absolute;left:-30px;top:50%;transform:translateY(-50%);width:30px;height:52px;background:{_drawer_bg};border:1px solid {_drawer_bord};border-right:none;border-radius:10px 0 0 10px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:14px;color:{_drawer_acc};user-select:none;}}'
    +'#agent-drawer-body{{padding:14px 14px 12px;}}'
    +'#agent-drawer-title{{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:{_drawer_acc};margin-bottom:10px;}}'
    +'#agent-drawer-history{{max-height:180px;overflow-y:auto;font-size:11px;color:{_drawer_mut};margin-bottom:10px;line-height:1.5;}}'
    +'#agent-drawer-history .dq{{color:{_drawer_text};font-weight:600;}}'
    +'#agent-drawer-input{{width:100%;box-sizing:border-box;background:rgba(128,128,128,0.08);border:1px solid {_drawer_bord};border-radius:6px;color:{_drawer_text};font-size:12px;padding:8px 10px;resize:none;font-family:inherit;margin-bottom:8px;}}'
    +'#agent-drawer button{{width:100%;background:{_drawer_acc};color:{_drawer_btn_c};border:none;border-radius:6px;font-size:12px;font-weight:700;padding:7px;cursor:pointer;font-family:inherit;}}';
  par.head.appendChild(style);

  // Update history if panel already exists
  var existing = par.getElementById('agent-drawer');
  if(existing){{
    var he = par.getElementById('agent-drawer-history');
    if(he) he.innerHTML = _hh;
    return;
  }}

  // Build panel — note: onclick runs in parent page context so call functions directly
  var panel = par.createElement('div');
  panel.id = 'agent-drawer';
  panel.innerHTML =
    '<div id="agent-drawer-tab" onclick="toggleDrawer()">&#9664;</div>'
    +'<div id="agent-drawer-body">'
    +'<div id="agent-drawer-title">Ask Agent</div>'
    +'<div id="agent-drawer-history"></div>'
    +'<textarea id="agent-drawer-input" placeholder="Ask about this design…" rows="3"></textarea>'
    +'<button onclick="submitDrawerQuery()">Send ›</button>'
    +'</div>';
  par.body.appendChild(panel);
  par.getElementById('agent-drawer-history').innerHTML = _hh;

  // Define functions on parent window (global scope of the Streamlit page)
  win._drawerOpen = false;
  win.toggleDrawer = function(){{
    win._drawerOpen = !win._drawerOpen;
    par.getElementById('agent-drawer').classList.toggle('open', win._drawerOpen);
    par.getElementById('agent-drawer-tab').innerHTML = win._drawerOpen ? '&#9654;' : '&#9664;';
  }};
  win.submitDrawerQuery = function(){{
    var txt = par.getElementById('agent-drawer-input').value.trim();
    if(!txt) return;
    par.getElementById('agent-drawer-input').value = '';
    var h = par.getElementById('agent-drawer-history');
    h.innerHTML += '<div class="dq">You: '+txt.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div><div>Processing…</div>';
    h.scrollTop = h.scrollHeight;
    win.postMessage({{type:'agentQuery',text:txt}}, '*');
  }};
}})();
</script>""", unsafe_allow_javascript=True, width="content")

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
prompt_input = ""
submitted    = False

with st.sidebar:
    _active_logo = _logo_b64_light if _is_light else _logo_b64_dark
    if _active_logo:
        st.markdown(
            f'<img src="data:image/png;base64,{_active_logo}"'
            f' style="width:100%;max-height:120px;object-fit:contain;'
            f'object-position:left center;display:block;margin-bottom:6px">',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sb-brand">PermanenceOS</div>'
            '<div class="sb-sub">AI-Powered Structural Design</div>',
            unsafe_allow_html=True,
        )

    # ── INPUTS dropdown ───────────────────────────────────────────────────────
    _lid = layout_obj.get("layoutId", "")   # always defined for page header use

    with st.expander("INPUTS", expanded=True):

        # ── Upload ────────────────────────────────────────────────────────────
        st.markdown(
            f'<div class="inp-sub-hdr">Upload</div>',
            unsafe_allow_html=True,
        )
        _upload = st.file_uploader(
            "layout", type=["json"], label_visibility="collapsed", key="sb_uploader"
        )
        # Only process the file when it is genuinely new (name+size changed).
        # Without this guard the handler runs on EVERY rerun while the file
        # sits in the uploader, calling st.rerun() each time and preventing
        # any other button (OK, agent, etc.) from executing.
        if _upload is not None:
            _upload_fp = (_upload.name, _upload.size)
            if _upload_fp != st.session_state.get("_last_upload_fp"):
                try:
                    _loaded = _normalize_layout(json.loads(_upload.getvalue().decode("utf-8")))
                    # Strip any pre-built structure from the JSON so the user always
                    # starts with a blank design and must press "Generate Grid" explicitly.
                    _loaded = _strip_structure(_loaded)
                    # Reset all derived state — new file, clean slate
                    for _k in ("eval_result", "eval_alts", "agent_log", "grid_options",
                               "selected_grid", "cost_flexibility", "last_comparison",
                               "history", "state_history", "output_log", "snapshots"):
                        st.session_state[_k] = (
                            [] if isinstance(st.session_state.get(_k), list) else None)
                    st.session_state.currentLayout   = _loaded
                    st.session_state.versionHistory  = []
                    st.session_state.currentVersion  = 1
                    st.session_state.setupDone       = False
                    st.session_state.selected_el     = ""
                    st.session_state.active_level    = "level_01"
                    st.session_state.active_element_level = ""
                    st.session_state["_last_upload_fp"]      = _upload_fp
                    st.session_state["_last_sel_applied"]    = "\x00"
                    st.session_state["_last_lvl_applied"]    = "\x00"
                    st.session_state["selected_opt_bar_idx"] = -1
                    _write_json(EDITED_LAYOUT_PATH, _loaded)
                    st.rerun()
                except Exception as _exc:
                    st.error(f"Invalid JSON: {_exc}")
        if _lid:
            st.markdown(
                f'<div class="sb-filename">{_lid}</div>'
                f'<div class="sb-success">✓ Model loaded — press OK ▶ Apply & Render</div>',
                unsafe_allow_html=True,
            )
            if st.button("↺  Clear & Reset", width="stretch",
                         key="btn_reset_layout"):
                # Wipe everything — user must re-upload
                for _rk, _rv in {
                    "currentLayout": None, "versionHistory": [], "currentVersion": 0,
                    "setupDone": False, "_last_upload_fp": None,
                    "eval_result": None, "eval_alts": [], "agent_log": [],
                    "grid_options": [], "selected_grid": None,
                    "cost_flexibility": None, "last_comparison": None,
                    "history": [], "state_history": [], "output_log": [],
                    "snapshots": [], "selected_el": "",
                    "active_level": "level_01", "active_element_level": "",
                    "_last_sel_applied": "\x00", "selected_opt_bar_idx": -1,
                    "_last_lvl_applied": "\x00",
                }.items():
                    st.session_state[_rk] = _rv
                if EDITED_LAYOUT_PATH.exists():
                    EDITED_LAYOUT_PATH.unlink()
                st.rerun()

        st.divider()

        # ── Define Loads ──────────────────────────────────────────────────────
        st.markdown(
            f'<div class="inp-sub-hdr">Define Loads</div>',
            unsafe_allow_html=True,
        )
        _sdl_opts = {1.5: "1.5", 2.5: "2.5", 3.5: "3.5", 5.0: "5.0"}
        _sdl_v = st.select_slider(
            "Dead Load SDL (kN/m²)", list(_sdl_opts.keys()),
            value=_sdl_now, format_func=lambda v: f"{v} kN/m²",
        )
        if _sdl_v != _sdl_now:
            st.session_state.sdl_kNm2 = _sdl_v

        _ll_opts = {2.0: "2.0", 3.0: "3.0", 5.0: "5.0"}
        _ll_v = st.select_slider(
            "Live Load LL (kN/m²)", list(_ll_opts.keys()),
            value=_ll_now, format_func=lambda v: f"{v} kN/m²",
        )
        if _ll_v != _ll_now:
            st.session_state.live_load_kNm2 = _ll_v

        st.divider()

        # ── Define Materials ──────────────────────────────────────────────────
        st.markdown(
            f'<div class="inp-sub-hdr">Define Materials</div>',
            unsafe_allow_html=True,
        )
        _MAT_LABELS = {"RCC": "Concrete", "STEEL": "Steel", "TIMBER": "Timber"}
        mat_choice = st.radio(
            "Material", list(_MAT_LABELS.keys()),
            format_func=lambda k: _MAT_LABELS[k],
            index=list(_MAT_LABELS.keys()).index(_mat_now),
            horizontal=True, label_visibility="collapsed",
        )
        if mat_choice != _mat_now:
            st.session_state.material     = mat_choice
            st.session_state.grid_options = []
            st.session_state.setupDone    = False   # require OK again after material change

        # ── OK button — commits loads/material into layout metadata and enables viewers
        _ok_disabled = st.session_state.currentLayout is None
        if st.button(
            "OK  ▶  Apply & Render",
            width="stretch", type="primary",
            key="btn_ok_apply", disabled=_ok_disabled,
        ):
            if st.session_state.currentLayout is not None:
                _cl = st.session_state.currentLayout
                if "meta" not in _cl or not isinstance(_cl.get("meta"), dict):
                    _cl["meta"] = {}
                _cl["meta"]["material"] = mat_choice
                _cl["meta"]["SDL"]      = st.session_state.sdl_kNm2
                _cl["meta"]["LL"]       = st.session_state.live_load_kNm2
                st.session_state.currentLayout = _cl
                _write_json(EDITED_LAYOUT_PATH, _cl)
                st.session_state.setupDone  = True
                st.session_state.material   = mat_choice
                _sync_viewers()
                st.rerun()

    # ── Generate Grid + Options ───────────────────────────────────────────────
    st.markdown(
        f'<div style="margin:8px 0 6px;border-top:1px solid {_BORD}"></div>',
        unsafe_allow_html=True,
    )
    _gopts_sb  = st.session_state.grid_options
    _gate_off  = not st.session_state.get("setupDone", False)
    if st.button("⊕  Generate Grid", width="stretch",
                 type="primary", key="btn_gen_main", disabled=_gate_off):
        with st.spinner("Computing grid options…"):
            st.session_state.grid_options = _run_grid_options(layout_obj, _mat_now)
        for _gi, _gopt_g in enumerate(st.session_state.grid_options, 1):
            (REPO_ROOT / f"team_01_option_{_gi}.json").write_text(
                json.dumps(_gopt_g["layout"], indent=2, ensure_ascii=False),
                encoding="utf-8")
        # Auto-apply option 1 so structure is immediately available
        if st.session_state.grid_options:
            _auto_opt = st.session_state.grid_options[0].get("layout", {})
            if _auto_opt:
                _push_version(_auto_opt)
        st.session_state["selected_opt_bar_idx"] = 0
        st.rerun()

    if _gopts_sb:
        for _bi, _gopt_sb in enumerate(_gopts_sb[:3]):
            _is_sel_sb = st.session_state.get("selected_opt_bar_idx", -1) == _bi
            _kpis = _grid_option_kpis(_gopt_sb.get("layout", {}))
            _desc  = _grid_option_description(_bi, _kpis)
            _bcard_bg  = f"background:{'rgba(42,192,192,0.10)' if _is_sel_sb else _CARD}"
            _bcard_brd = f"border:1px solid {_ACC if _is_sel_sb else _BORD}"
            st.markdown(
                f'<div style="{_bcard_bg};{_bcard_brd};border-radius:8px;'
                f'padding:8px 10px;margin-bottom:6px">'
                f'<div style="font-size:.63rem;font-weight:700;color:{"#2ac0c0" if _is_sel_sb else _TEXT};'
                f'margin-bottom:4px">Option {_bi+1}'
                f'{"  ✓ Active" if _is_sel_sb else ""}</div>'
                f'<div style="font-size:.60rem;color:{_MUT};line-height:1.55;margin-bottom:6px">{_desc}</div>'
                f'<div style="display:flex;gap:8px;flex-wrap:wrap">'
                f'<span style="font-size:.60rem;color:{_TEXT}">⬛ {_kpis["n_cols"]} col</span>'
                f'<span style="font-size:.60rem;color:{_TEXT}">— {_kpis["n_beams"]} beam</span>'
                f'<span style="font-size:.60rem;color:{_TEXT}">↔ max {_kpis["max_span"]}m</span>'
                f'<span style="font-size:.60rem;color:{_TEXT}">avg {_kpis["avg_span"]}m</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            if st.button(
                f"Apply Option {_bi+1}", key=f"sb_opt_{_bi}",
                width="stretch",
                type="primary" if _is_sel_sb else "secondary",
            ):
                _opt_layout = _gopt_sb.get("layout", {})
                _opt_ev = _gopt_sb.get("evaluation")
                if _opt_ev is None:
                    with st.spinner(f"Evaluating Option {_bi+1}…"):
                        _opt_ev = _run_evaluate(
                            json.dumps(_opt_layout),
                            sdl=_sdl_now, ll=_ll_now)
                    if _opt_ev:
                        st.session_state.grid_options[_bi]["evaluation"] = _opt_ev
                if _opt_layout:
                    _push_version(_opt_layout)
                st.session_state["selected_opt_bar_idx"] = _bi
                st.session_state.eval_result = _opt_ev
                st.session_state.eval_alts = _get_failure_alternatives(
                    _opt_ev or {}, _mat_now)
                st.rerun()

    # ── AI AGENT ──────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="border-top:1px solid {_BORD};margin:10px 0 6px"></div>'
        f'<div style="font-size:.76rem;font-weight:700;color:{_TEXT};margin-bottom:4px">'
        f'AI Agent <span class="beta">BETA</span></div>',
        unsafe_allow_html=True,
    )
    _history = st.session_state.get("history", [])
    if _history:
        _bub = ""
        for _msg in _history[-8:]:
            _q = _msg.get("prompt", "")
            _a = _msg.get("response", "")
            if _q:
                _bub += f'<div class="chat-q">{_q}</div>'
            if _a:
                _bub += f'<div class="chat-a">{_a}</div>'
        st.markdown(
            f'<div style="max-height:460px;overflow-y:auto;margin-bottom:8px">{_bub}</div>',
            unsafe_allow_html=True,
        )

    with st.form("agent_form", clear_on_submit=True):
        prompt_input = st.text_area(
            "Ask agent",
            placeholder="Ask anything about your structure…\ne.g. remove column C4 / explain beam B1 failure",
            label_visibility="collapsed",
            height=130,
        )
        submitted = st.form_submit_button("Ask Agent  ›", width="stretch")

    # ── AI Recommendations (shown in ANALYSIS tab) ────────────────────────────
    _alts_sb = st.session_state.eval_alts
    if _alts_sb:
        st.markdown(
            f'<div style="font-size:.63rem;color:{_MUT};margin-top:8px;line-height:1.6">'
            f'{len(_alts_sb)} recommendation{"s" if len(_alts_sb)>1 else ""} ready — '
            f'open the <b style="color:{_ACC}">Analysis</b> tab to preview or apply.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="font-size:.63rem;color:{_MUT};margin-top:8px;line-height:1.5">'
            f'Generate a grid and run analysis to see AI recommendations.</div>',
            unsafe_allow_html=True,
        )

# ─── Agent processing ─────────────────────────────────────────────────────────
if submitted and prompt_input.strip():
    with st.spinner("Agent reasoning…"):
        _resp = _run_agent_chat(prompt_input.strip(), layout_obj, er)

    if _resp == "GENERATE_GRID" or _resp.startswith("GENERATE_GRID\n"):
        _gen_advisory = _resp[len("GENERATE_GRID"):].strip()
        with st.spinner("Generating structural grid options…"):
            st.session_state.grid_options = _run_grid_options(layout_obj, _mat_now)
        for _gi, _gopt in enumerate(st.session_state.grid_options, 1):
            (REPO_ROOT / f"team_01_option_{_gi}.json").write_text(
                json.dumps(_gopt["layout"], indent=2, ensure_ascii=False), encoding="utf-8")
        # Auto-apply option 1 to the working layout
        if st.session_state.grid_options:
            _ag_opt = st.session_state.grid_options[0].get("layout", {})
            if _ag_opt:
                _push_version(_ag_opt)
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
                if _eid:
                    _push_version(json.loads(_rem_el(json.dumps(layout_obj), _eid)))
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
                if _uid:
                    _push_version(json.loads(_ups(json.dumps(layout_obj), _uid)))
                    _resp = (f"{_advisory_txt}\n\n" if _advisory_txt else "") + f"Upgraded section of **{_uid}**."
        except Exception as _tex:
            _resp = f"Tool execution failed: {_tex}"
    elif _resp == "EVALUATE":
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
_cf_h  = st.session_state.get("cost_flexibility")
_hcols = st.columns([5, 1, 1, 0.35], gap="small")

with _hcols[0]:
    _rev_chip  = ('<span class="stat-chip needs-review">⚠ Review</span>'
                  if _has_fail else "")
    _cost_chip = (f'<span class="stat-chip">net <b>${_cf_h["net_cost_usd"]:+,.0f}</b></span>'
                  if _cf_h else "")
    st.markdown(
        f'<div class="page-hdr">'
        f'<span class="hdr-lid">{_lid}</span>'
        f'<span class="stat-chip"><b>{n_cols}</b> col</span>'
        f'<span class="stat-chip"><b>{n_beams}</b> beam</span>'
        f'<span class="stat-chip"><b>{_mat_now}</b></span>'
        f'{_cost_chip}{_rev_chip}</div>',
        unsafe_allow_html=True,
    )
with _hcols[1]:
    if st.button("Light" if not _is_light else "Dark",
                 width="stretch", key="btn_theme"):
        st.session_state.theme        = "light" if not _is_light else "dark"
        st.session_state.viewer_nonce += 1
        st.rerun()
with _hcols[2]:
    st.download_button(
        "Export JSON",
        data=json.dumps(layout_obj, indent=2, ensure_ascii=False),
        file_name="layout_export.json",
        mime="application/json",
        width="stretch",
    )
with _hcols[3]:
    with st.popover("⋮", width="stretch"):
        st.markdown(
            f'<div style="font-size:.72rem;font-weight:700;color:#c8eeed;'
            f'margin-bottom:6px">PermanenceOS</div>'
            f'<div style="font-size:.65rem;color:#5a9090">AI Structural Design</div>',
            unsafe_allow_html=True,
        )
        st.divider()
        if st.button("Rerun", key="btn_menu_rerun", width="stretch"):
            st.rerun()
        _theme_lbl = "Switch to Light" if not _is_light else "Switch to Dark"
        if st.button(_theme_lbl, key="btn_menu_theme", width="stretch"):
            st.session_state.theme        = "light" if not _is_light else "dark"
            st.session_state.viewer_nonce += 1
            st.rerun()
        st.download_button(
            "Export JSON",
            data=json.dumps(layout_obj, indent=2, ensure_ascii=False),
            file_name="layout_export.json",
            mime="application/json",
            width="stretch",
            key="btn_menu_export",
        )

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
            from nodes.modify import apply_material_override
            _ls2 = apply_material_override(json.dumps(layout_obj), _mat_now)
            _push_version(json.loads(_ls2))
            with st.spinner("Evaluating structure…"):
                _ev2 = _run_evaluate(_ls2, sdl=_sdl_now, ll=_ll_now)
            if _ev2:
                st.session_state.eval_result = _ev2
                st.session_state.eval_alts   = _get_failure_alternatives(_ev2, _mat_now)
                # Keep the selected option's evaluation in sync so the ANALYSIS tab shows results
                _oi_run = st.session_state.get("selected_opt_bar_idx", -1)
                _gopts_run = st.session_state.grid_options
                if 0 <= _oi_run < len(_gopts_run):
                    st.session_state.grid_options[_oi_run]["evaluation"] = _ev2
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
        _tb_cols = [0.55, 0.9, 0.7, 0.6, 0.6, 3.6] if _is_ml else [0.55, 0.7, 0.6, 0.6, 4]
        _tb = st.columns(_tb_cols, gap="small")
        _tb1 = _tb[0]
        _tb_lvl = _tb[1] if _is_ml else None
        _tb2 = _tb[2] if _is_ml else _tb[1]
        _tb3 = _tb[3] if _is_ml else _tb[2]
        _tb4 = _tb[4] if _is_ml else _tb[3]
        with _tb1:
            if st.button("3D" if _vm == "2D" else "2D",
                         key="tb_vm_btn", width="stretch"):
                st.session_state["view_mode"] = "3D" if _vm == "2D" else "2D"
                st.rerun()
        if _is_ml and _tb_lvl is not None:
            with _tb_lvl:
                _lvl_keys = get_level_keys(_plan_layout)
                _lvl_idx = _lvl_keys.index(st.session_state.active_level) if st.session_state.active_level in _lvl_keys else 0
                _new_level = st.selectbox(
                    "Level",
                    _lvl_keys,
                    index=_lvl_idx,
                    label_visibility="collapsed",
                    key="tb_active_level",
                )
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
            _new_auto = st.toggle("Auto", value=st.session_state.get("auto_eval", True),
                                  key="tb_auto_tog")
            if _new_auto != st.session_state.get("auto_eval", True):
                st.session_state["auto_eval"] = _new_auto

        if _vm == "2D":
            _before_lay = None
            if st.session_state.compare_mode and st.session_state.get("versionHistory"):
                try:
                    _before_lay = st.session_state.versionHistory[-1]
                except Exception:
                    pass
            _fig2d = _render_floor_plan_plotly(
                _plan_layout, eval_result=er,
                highlight=st.session_state.selected_el,
                level_key=st.session_state.active_level,
                labels=st.session_state.labels_on,
                height_px=510, is_light=_is_light,
                diff_on=st.session_state.compare_mode,
                before_layout=_before_lay,
                revision=st.session_state.get("currentVersion", 0),
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
                    _cand_dbg = []
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
                            _cand_dbg.append(
                                f"id={_cand or '-'} kind={_kind or '-'} lvl={_lvl or '-'}"
                            )
                            if _cand and (_kind in ("beam", "column") or not _kind):
                                _new_sel = _cand
                                if _lvl and _lvl != st.session_state.get("active_element_level", ""):
                                    _lvl_changed = True
                                if _lvl:
                                    st.session_state.active_element_level = _lvl
                                    st.session_state.active_level = _lvl
                                    st.session_state["_last_lvl_applied"] = _lvl
                                break
                        else:
                            _cand_dbg.append(f"id={str(_cd)} kind=-")
                            _new_sel = str(_cd)
                            break
                    st.session_state["last_click_debug"] = {
                        "selected_id": _new_sel,
                        "points_count": len(_sel_ev.selection.points),
                        "candidates": _cand_dbg,
                        "raw_first_point": (
                            _sel_ev.selection.points[0]
                            if _sel_ev.selection.points else None
                        ),
                    }
                    if _new_sel and (
                        _new_sel != st.session_state.selected_el
                        or _lvl_changed
                    ):
                        st.session_state.selected_el = _new_sel
                        st.session_state["_last_sel_applied"] = _new_sel
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

        with _rt2:
            if st.button("⟳  Show details for selected element", key="dd_show_details",
                         width="stretch",
                         help="Click an element in the 3D/2D view, then press this to load its details here."):
                st.rerun()
            _sel     = st.session_state.selected_el
            _sel_level = st.session_state.get("active_element_level", "")
            _found_level, _found_el = find_element_in_layout(layout_obj, _sel) if _sel else (None, None)
            _sel_obj = _found_el
            if _found_level:
                _sel_level = _found_level
                st.session_state.active_element_level = _found_level
            _dbg = st.session_state.get("last_click_debug", {})

            if _sel:
                st.markdown(
                    f'<div style="font-size:.64rem;color:{_MUT};margin:2px 0 8px 0">'
                    f'Selected element ID: '
                    f'<span style="color:{_TEXT};font-weight:700">{_sel}</span>'
                    f'{f" <span style=\"color:{_MUT};font-weight:600\">({_sel_level})</span>" if _sel_level else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            if _dbg:
                _dbg_id = _dbg.get("selected_id", "") or "(none)"
                _dbg_pts = _dbg.get("points_count", 0)
                _dbg_cands = _dbg.get("candidates", [])
                _dbg_cands_txt = " | ".join(_dbg_cands) if _dbg_cands else "(none)"
                st.markdown(
                    f'<div style="font-size:.62rem;color:{_MUT};line-height:1.55;'
                    f'border:1px dashed {_BORD};border-radius:8px;padding:8px;margin:0 0 8px 0">'
                    f'<b style="color:{_TEXT}">Selection Debug</b><br>'
                    f'points captured: <b style="color:{_TEXT}">{_dbg_pts}</b><br>'
                    f'candidate(s): <span style="color:{_TEXT}">{_dbg_cands_txt}</span><br>'
                    f'resolved selected_id: <b style="color:{_TEXT}">{_dbg_id}</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("Raw click payload", expanded=False):
                    st.json(_dbg.get("raw_first_point", {}))

            if _sel_obj:
                st.markdown(_el_detail_html(_sel_obj, er), unsafe_allow_html=True)

                # ── Direct action buttons (bypass agent) ──────────────────
                _sel_is_beam = len(_sel_obj.get("geometry", [])) == 2
                _act_cols = st.columns(2, gap="small") if _sel_is_beam else st.columns([1, 1], gap="small")

                with _act_cols[0]:
                    if st.button(f"✕  Remove", key="btn_direct_remove",
                                 width="stretch"):
                        try:
                            from nodes.modify import remove_element as _direct_rem
                            _new_layout = json.loads(_direct_rem(json.dumps(layout_obj), _sel))
                            # If the element is still present, removal was blocked (perimeter lock).
                            if find_element_in_layout(_new_layout, _sel)[1] is not None:
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
                            _new_layout = json.loads(_force_rem(json.dumps(layout_obj), _sel, True))
                            _push_version(_new_layout)
                            st.session_state.selected_el = ""
                            st.session_state.active_element_level = ""
                            st.session_state["_remove_blocked"] = ""
                            st.rerun()
                        except Exception as _fre:
                            st.error(f"Force remove failed: {_fre}")

                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

            else:
                st.markdown(
                    f'<div style="font-size:.70rem;color:{_MUT};padding:4px 0">'
                    f'Click an element in the plan to inspect it.</div>',
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
            st.button("↓ Export PDF", width="stretch", disabled=True,
                      key="cmp_export_pdf", help="Revit-style report export (coming soon)")
        with _rp4:
            if st.button("✕ Reset", width="stretch", key="btn_reset_cmp"):
                st.session_state.snapshots = []
                st.session_state.cmp_sel_indices = []
                st.rerun()

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
            _mod_c = "#c07800" if _is_light else "#ffd060"
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
                            ),
                            height=_ph + 8,
                            scrolling=False,
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


