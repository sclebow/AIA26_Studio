from __future__ import annotations
"""Pure visual / report helpers extracted from app.py (no Streamlit UI state).
Rendering (2D Plotly, 3D Three.js HTML), material colours, legends, diff, and
PDF / diagram builders. Imported by app.py."""
import json
import math
import copy
import streamlit as st
import plotly.graph_objects as go
from nodes._layout import (
    is_multilevel, get_level_keys, get_level_count, get_outline, get_rooms,
    get_structure, iter_all_structure, get_all_rooms, find_element_in_layout,
)


def _el_spec(el: dict) -> tuple:
    """Material + section/dimensions signature of an element — the only attributes a
    'changed' diff should care about (NOT geometry/position)."""
    a = el.get("attributes") or {}
    return (
        str(a.get("material") or ""),
        str(a.get("section") or ""),
        str(a.get("dimensions") or ""),
        str(a.get("width") or ""), str(a.get("depth") or ""),
        str(a.get("col_dims") or ""),
    )


def _compute_diff(before: dict, after: dict) -> dict:
    """Return sets of 'level|id' keys: added, removed, changed.
    'changed' = a MATERIAL or SECTION/dimension change ONLY (moving a column is not a
    'change' for diff purposes). Keyed per-level because ids repeat across levels.

    Guard: if the baseline has NO element with material set (un-seeded grid — diff_baseline
    was captured before apply_material_override ran) but the current layout IS seeded,
    treat material as a non-diffable field so seeding doesn't look like a user change."""
    b_els = {f"{lk}|{el['id']}": el for lk, el in iter_all_structure(before)}
    a_els = {f"{lk}|{el['id']}": el for lk, el in iter_all_structure(after)}
    added   = set(a_els) - set(b_els)
    removed = set(b_els) - set(a_els)
    common  = set(a_els) & set(b_els)
    # If the baseline is completely un-seeded (all material=None/empty) and the current
    # layout IS seeded, suppress material-only phantom diffs — only flag section/dims changes.
    _b_has_mat = any((b_els[k].get("attributes") or {}).get("material") for k in common)
    _a_has_mat = any((a_els[k].get("attributes") or {}).get("material") for k in common)
    if not _b_has_mat and _a_has_mat:
        # Baseline was un-seeded; compare only non-material fields (section/dims).
        def _spec_no_mat(el):
            s = _el_spec(el)
            return s[1:]   # drop material (index 0), keep section/dims/width/depth/col_dims
        changed = {k for k in common if _spec_no_mat(a_els[k]) != _spec_no_mat(b_els[k])}
    else:
        changed = {k for k in common if _el_spec(a_els[k]) != _el_spec(b_els[k])}
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
    clash_ids: set | None = None,
):
    """Return a Plotly figure of the floor plan with clickable structural elements."""
    import math as _hm
    clash_ids = clash_ids or set()
    CLASH_C = "#ff3df0"   # magenta — structure clashing with a door/window opening
    if is_light:
        BG = "#f0f8f8"; ROOM_F = "rgba(218,234,234,0.80)"; ROOM_L = "#a0c8c8"
        FG = "#1a3535"; ACCENT = "#088a87"
        PASS_C = "#1a8050"; FAIL_C = "#cc2020"; SEL_C = "#0077b6"; WIN_C = "#2060a0"
        REM_C = "#cc2020"; ADD_C = "#1a8050"; MOD_C = "#7c4dff"
    else:
        BG = "#0c2020"; ROOM_F = "rgba(23,46,46,0.88)"; ROOM_L = "#1e4040"
        FG = "#c8eeed"; ACCENT = "#2ac0c0"
        PASS_C = "#40d090"; FAIL_C = "#ff5050"; SEL_C = "#00e5ff"; WIN_C = "#4696dc"
        REM_C = "#ff5050"; ADD_C = "#40d090"; MOD_C = "#9b7cff"

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
        # 'changed' = material/section change only (not a moved column) — matches _compute_diff
        for _key in set(_cur_map) & set(_bef_map):
            if _el_spec(_cur_map[_key]) != _el_spec(_bef_map[_key]):
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
        elif eid in clash_ids:
            clr, lw = CLASH_C, 3.5
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
        elif eid in clash_ids:
            clr, sz = CLASH_C, 15
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


def _render_3d_viewport(
        layout: dict,
        eval_result: dict | None,
        selected_el: str,
        active_level: str,
        is_light: bool,
        height: int = 512,
        before_layout: dict | None = None,
        labels: bool = False,
        footings: bool = False,
        show_conflicts: bool = False,
) -> str:
        level_keys = get_level_keys(layout)
        if not level_keys:
                level_keys = ["level_01"]

        status_by_id: dict[str, str] = {}
        if eval_result:
                for b in eval_result.get("beams", []):
                        b_ok = b.get("bend_PASS") and b.get("shear_PASS") and b.get("defl_TL_PASS") and b.get("defl_LL_PASS")
                        _bid = b.get("id", ""); _blk = b.get("level", "")
                        status_by_id[f"{_blk}|{_bid}" if _blk else _bid] = "pass" if b_ok else "fail"
                for c in eval_result.get("columns", []):
                        c_ok = c.get("stress_PASS") and c.get("buckling_PASS")
                        _cid = c.get("id", ""); _clk = c.get("level", "")
                        status_by_id[f"{_clk}|{_cid}" if _clk else _cid] = "pass" if c_ok else "fail"

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

        # Structure↔opening clashes per level (keyed level|id; ids repeat across levels).
        # Only when show_conflicts is on, so magenta is off by default.
        clash_by_key: dict[str, bool] = {}
        if show_conflicts:
                for lk in level_keys:
                        for _cid in _opening_clashes(layout, lk):
                                clash_by_key[f"{lk}|{_cid}"] = True

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
                "clashByKey": clash_by_key,
                "removed": removed_payload,
                "labels": bool(labels),
                "footings": bool(footings),
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
            <button class=\"cube-btn\" id=\"measureBtn\" style=\"grid-column:1 / 3\">📏 MEASURE</button>
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
                if (d === 'changed') return 0x9b7cff;
                // Clash with a door/window opening → magenta.
                if ((DATA.clashByKey || {{}})[level + '|' + el.id]) return 0xff3df0;
                // Failing elements show red; otherwise colour by material.
                const _skey = level ? (level + '|' + el.id) : el.id;
                if ((statusById[_skey] || statusById[el.id] || 'none') === 'fail') return 0xff5050;
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

            function makeLabel(text, x, y, z) {{
                const cv = document.createElement('canvas');
                let ctx = cv.getContext('2d');
                ctx.font = 'bold 44px Inter, Segoe UI, sans-serif';
                cv.width = Math.ceil(ctx.measureText(text).width) + 24; cv.height = 60;
                ctx = cv.getContext('2d');
                ctx.font = 'bold 44px Inter, Segoe UI, sans-serif';
                ctx.fillStyle = DATA.isLight ? 'rgba(255,255,255,0.88)' : 'rgba(10,28,28,0.85)';
                ctx.fillRect(0, 0, cv.width, cv.height);
                ctx.fillStyle = DATA.isLight ? '#13403e' : '#d6f5f3';
                ctx.textBaseline = 'middle';
                ctx.fillText(text, 12, 32);
                const spr = new THREE.Sprite(new THREE.SpriteMaterial({{
                    map: new THREE.CanvasTexture(cv), depthTest: false, transparent: true }}));
                spr.scale.set(cv.width * 0.006, cv.height * 0.006, 1);
                spr.position.set(x, y, z);
                spr.renderOrder = 999;
                scene.add(spr);
                return spr;
            }}
            function labelOn(level) {{
                return DATA.labels && (DATA.activeLevel === '__ALL__' || level === DATA.activeLevel);
            }}
            // Element label is floor-aware when there is more than one level, so the same
            // id on different floors reads distinctly (e.g. L1·C1 vs L2·C1).
            function elLabel(el, idx) {{
                return ((DATA.levels || []).length > 1) ? ('L' + (idx + 1) + '·' + el.id) : el.id;
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
                if (DATA.footings && idx === 0) addFooting(level, idx, el);
                if (labelOn(level)) makeLabel(elLabel(el, idx), pt[0], idx * STOREY_H + STOREY_H + 0.35, pt[1]);
            }}

            // Footing: a foundation box under a ground-floor column, 1.0 m square and
            // 0.5 m deep below the slab — drawn as a wireframe (+ faint fill) like the
            // reference notebook so the architect can see the foundation footprint.
            function addFooting(level, idx, el) {{
                const pt = (el.geometry || [])[0];
                if (!pt) return;
                const SZ = 1.0, H = 0.5;
                const cy = idx * STOREY_H - H / 2;     // sits below the ground slab
                const c = elColor(el, level);
                const geo = new THREE.BoxGeometry(SZ, H, SZ);
                geo.translate(pt[0], cy, pt[1]);
                const fill = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({{
                    color: c, transparent: true, opacity: 0.16 }}));
                scene.add(fill);
                const edges = new THREE.LineSegments(
                    new THREE.EdgesGeometry(geo),
                    new THREE.LineBasicMaterial({{ color: c }}));
                edges.renderOrder = 997;
                scene.add(edges);
                box.expandByObject(fill);
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
                if (labelOn(level)) makeLabel(elLabel(el, idx), mid.x, idx * STOREY_H + STOREY_H - 0.05, mid.z);
            }}

            (DATA.levels || []).forEach((lvl, idx) => {{
                addSlab(lvl.key, idx, lvl.outline || []);
                (lvl.structure || []).forEach((el) => {{
                    const g = el.geometry || [];
                    if (g.length === 1) addColumn(lvl.key, idx, el);
                    if (g.length === 2) addBeam(lvl.key, idx, el);
                }});
            }});

            // Removed elements (Compare diff): bold red ghosts (+ red wireframe) at their
            // old position so deletions read clearly as "removed in red".
            (DATA.removed || []).forEach((r) => {{
                const g = r.geometry || [];
                const yBase = (r.levelIdx || 0) * STOREY_H;
                let geo = null, pos = null, rotY = 0;
                if (g.length === 1) {{
                    geo = new THREE.BoxGeometry(0.34, STOREY_H, 0.34);
                    pos = new THREE.Vector3(g[0][0], yBase + STOREY_H * 0.5, g[0][1]);
                }} else if (g.length === 2) {{
                    const p1 = new THREE.Vector3(g[0][0], 0, g[0][1]);
                    const p2 = new THREE.Vector3(g[1][0], 0, g[1][1]);
                    const span = p1.distanceTo(p2);
                    if (span <= 0.001) return;
                    geo = new THREE.BoxGeometry(span, 0.30, 0.24);
                    const mid = p1.clone().add(p2).multiplyScalar(0.5);
                    pos = new THREE.Vector3(mid.x, yBase + (STOREY_H - 0.25), mid.z);
                    rotY = Math.atan2(p2.z - p1.z, p2.x - p1.x);
                }}
                if (geo) {{
                    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({{
                        color:0xff3030, transparent:true, opacity:0.45 }}));
                    mesh.position.copy(pos); mesh.rotation.y = rotY;
                    scene.add(mesh); box.expandByObject(mesh);
                    const edges = new THREE.LineSegments(
                        new THREE.EdgesGeometry(geo),
                        new THREE.LineBasicMaterial({{ color:0xff3030 }}));
                    edges.position.copy(pos); edges.rotation.y = rotY; edges.renderOrder = 996;
                    scene.add(edges);
                }}
            }});

            const center = box.isEmpty() ? new THREE.Vector3(0, 0, 0) : box.getCenter(new THREE.Vector3());
            const size = box.isEmpty() ? new THREE.Vector3(10, 10, 10) : box.getSize(new THREE.Vector3());
            const radius = Math.max(size.x, size.y, size.z, 10);
            controls.target.copy(center);
            camera.position.set(center.x + radius * 0.9, center.y + radius * 0.7, center.z + radius * 0.9);
            controls.update();

            // Orientation gizmo: X (red) and Y (green) ground axes at the model corner,
            // so you can read which way x/y run inside the viewport. World Z = layout Y.
            const _amin = box.isEmpty() ? new THREE.Vector3(0, 0, 0) : box.min.clone();
            _amin.y = 0;
            const _aLen = Math.max(2.0, radius * 0.16);
            const _aHead = _aLen * 0.22;
            scene.add(new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), _amin, _aLen, 0xff5050, _aHead, _aHead * 0.6));
            scene.add(new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), _amin, _aLen, 0x40d090, _aHead, _aHead * 0.6));
            makeLabel('X', _amin.x + _aLen + 0.3, 0.1, _amin.z);
            makeLabel('Y', _amin.x, 0.1, _amin.z + _aLen + 0.3);

            const ray = new THREE.Raycaster();
            const ptr = new THREE.Vector2();
            const hud = document.getElementById('hud');
            const HUD_DEFAULT = '3D BIM View<br/>Click element to inspect';
            let hovered = null;
            let selectedObj = null;

            function statusLabel(id, level) {{
                const key = level ? (level + '|' + id) : id;
                const s = statusById[key] || statusById[id] || 'none';
                if (s === 'pass') return ['PASS', '#40d090'];
                if (s === 'fail') return ['FAIL', '#ff5050'];
                return ['not evaluated', DATA.isLight ? '#5a7070' : '#9ab'];
            }}

            // Instant, client-side inspector — fills the moment an element is clicked,
            // independent of the Streamlit round-trip that syncs the full Design Data panel.
            function showHud(obj) {{
                if (!obj) {{ hud.innerHTML = HUD_DEFAULT; return; }}
                const d = obj.userData || {{}};
                const [stxt, scol] = statusLabel(d.id || '', d.level || '');
                hud.innerHTML =
                    '<div style="font-weight:700;font-size:12px;margin-bottom:1px">' + (d.id || '?') + '</div>' +
                    '<div style="opacity:.85">' + (d.type || '') + (d.level ? ' &middot; ' + d.level : '') + '</div>' +
                    '<div style="color:' + scol + ';font-weight:700;margin-top:1px">' + stxt + '</div>' +
                    '<div style="opacity:.6;margin-top:2px">Full details &amp; remove in panel &rarr;</div>';
            }}

            // emissive priority: selected (amber) > hovered (indigo) > none
            function paint(obj) {{
                if (!obj || !obj.material) return;
                if (obj === selectedObj) obj.material.emissive.setHex(0x00e5ff);
                else if (obj === hovered) obj.material.emissive.setHex(0x33ffe0);
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

            // ── Measure tool: click two points → distance + Δx/Δy in metres ──
            const measureBtn = document.getElementById('measureBtn');
            const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
            let measureMode = false;
            let measurePts = [];
            let measureIsCol = [];
            let measureObjs = [];
            function clearMeasure() {{
                measureObjs.forEach((o) => scene.remove(o));
                measureObjs = [];
                measurePts = [];
                measureIsCol = [];
            }}
            function measureMarker(p) {{
                const s = new THREE.Mesh(
                    new THREE.SphereGeometry(0.13, 14, 14),
                    new THREE.MeshBasicMaterial({{ color: 0xffcc33, depthTest: false }}));
                s.position.copy(p); s.renderOrder = 998;
                scene.add(s); measureObjs.push(s);
            }}
            function measurePoint(evt) {{
                pointerToNdc(evt);
                ray.setFromCamera(ptr, camera);
                const hit = ray.intersectObjects(pickables, false)[0];
                let p, isCol = false;
                if (hit) {{
                    const o = hit.object;
                    if ((o.userData || {{}}).type === 'column') {{
                        // Snap to the column's CENTRAL VERTICAL AXIS (its grid point),
                        // at mid-height — so spacing is measured centre-to-centre, not
                        // off the column face.
                        p = new THREE.Vector3(o.position.x, o.position.y, o.position.z);
                        isCol = true;
                    }} else {{
                        p = hit.point.clone();
                    }}
                }} else {{ p = new THREE.Vector3(); if (!ray.ray.intersectPlane(groundPlane, p)) return; }}
                if (measurePts.length >= 2) clearMeasure();
                measureMarker(p);
                measurePts.push(p);
                measureIsCol.push(isCol);
                if (measurePts.length === 2) {{
                    const a = measurePts[0], b = measurePts[1];
                    const dxm = b.x - a.x;          // world X = layout X
                    const dym = b.z - a.z;          // world Z = layout Y
                    const dist = Math.hypot(dxm, dym);   // plan (centre-to-centre) distance
                    const lg = new THREE.BufferGeometry().setFromPoints([a, b]);
                    const ln = new THREE.Line(lg, new THREE.LineBasicMaterial({{ color: 0xffcc33, depthTest: false }}));
                    ln.renderOrder = 998; scene.add(ln); measureObjs.push(ln);
                    const mid = a.clone().add(b).multiplyScalar(0.5);
                    const lbl = makeLabel(dist.toFixed(2) + ' m', mid.x, mid.y + 0.4, mid.z);
                    if (lbl) measureObjs.push(lbl);
                    const ax = Math.abs(dxm) >= Math.abs(dym) ? 'x' : 'y';
                    const amt = (ax === 'x' ? dxm : dym).toFixed(2);
                    const c2c = (measureIsCol[0] && measureIsCol[1]) ? ' (centre&#8209;to&#8209;centre)' : '';
                    hud.innerHTML =
                        '<div style="font-weight:700;font-size:12px">Distance ' + dist.toFixed(2) + ' m' + c2c + '</div>' +
                        '<div style="opacity:.85">Δx ' + dxm.toFixed(2) + ' m &middot; Δy ' + dym.toFixed(2) + ' m</div>' +
                        '<div style="opacity:.6;margin-top:2px">Ask agent: &ldquo;move &lt;col&gt; by ' + amt + ' m in ' + ax + '&rdquo;</div>';
                }} else {{
                    hud.innerHTML = '<div style="font-weight:700">Measure</div><div style="opacity:.7">Click the second point&hellip;</div>';
                }}
            }}
            function setMeasureMode(on) {{
                measureMode = on;
                clearMeasure();
                measureBtn.style.background = on ? (DATA.isLight ? '#ffe39a' : '#3a5e2e') : '';
                measureBtn.style.color = on ? (DATA.isLight ? '#5a3d00' : '#cfe8b0') : '';
                renderer.domElement.style.cursor = on ? 'crosshair' : 'default';
                hud.innerHTML = on
                    ? '<div style="font-weight:700">Measure mode</div><div style="opacity:.7">Click two points</div>'
                    : HUD_DEFAULT;
            }}
            measureBtn.addEventListener('click', () => setMeasureMode(!measureMode));

            renderer.domElement.addEventListener('pointermove', (evt) => {{
                if (measureMode) return;
                pointerToNdc(evt);
                ray.setFromCamera(ptr, camera);
                const hit = ray.intersectObjects(pickables, false)[0];
                setHover(hit ? hit.object : null);
            }});

            renderer.domElement.addEventListener('click', (evt) => {{
                if (measureMode) {{ measurePoint(evt); return; }}
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


def _structural_summary_text(layout: dict, eval_result: dict | None) -> str:
    """Deterministic structural summary — used as the report body when the LLM is offline."""
    cols = beams = 0
    mats: dict[str, int] = {}
    for _l, e in iter_all_structure(layout):
        n = len(e.get("geometry", []))
        if n == 1:
            cols += 1
        elif n == 2:
            beams += 1
        m = (e.get("attributes") or {}).get("material")
        if m:
            mats[str(m)] = mats.get(str(m), 0) + 1
    lines = [
        f"Layout {layout.get('layoutId', '?')} — {get_level_count(layout)} level(s).",
        f"{cols} columns and {beams} beams.",
        "Materials: " + (", ".join(f"{k} x{v}" for k, v in mats.items()) or "not yet assigned") + ".",
    ]
    if eval_result:
        s = eval_result.get("summary", {})
        lines.append(f"Evaluation: {'PASS' if s.get('overall_PASS') else 'FAIL'} — "
                     f"{s.get('beam_failures', 0)} beam and {s.get('column_failures', 0)} column failures.")
        fails = [b["id"] for b in eval_result.get("beams", [])
                 if not (b.get("bend_PASS") and b.get("shear_PASS")
                         and b.get("defl_TL_PASS") and b.get("defl_LL_PASS"))]
        if fails:
            lines.append("Failing beams: " + ", ".join(fails[:24]) + ".")
            lines.append("Suggested fixes: upgrade the failing beam sections, add a midspan "
                         "column to halve the span, or switch those members to a stiffer material.")
    return "\n".join(lines)


def _build_structural_sheet_pdf(layout: dict, eval_result: dict | None,
                                project: str, material: str,
                                revisions: list | None = None,
                                show_labels: bool = False,
                                report_text: str | None = None,
                                before_layout: dict | None = None,
                                prepared_by: str = "") -> bytes:
    """Revit-style structural sheet (A3 landscape, one page per level): plan + title block.

    report_text   — when set, prepend a written cover page (AI / intervention report).
    before_layout — when set, switch to INTERVENTION mode: each page shows the ORIGINAL
                    plan beside the INTERVENTION plan, diff-coloured (added=green,
                    removed=red dashed, changed=purple with a material/section note).
    No force/moment diagrams are produced (removed as not useful on the sheet)."""
    import io as _io
    import datetime as _dt
    import textwrap as _tw
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
    from matplotlib.backends.backend_pdf import PdfPages as _PdfPages

    GREEN, RED, PURPLE = "#1a8050", "#cc2020", "#7c4dff"

    status: dict[str, bool] = {}
    if eval_result:
        for _b in eval_result.get("beams", []):
            status[_b.get("id", "")] = bool(_b.get("bend_PASS") and _b.get("shear_PASS")
                                            and _b.get("defl_TL_PASS") and _b.get("defl_LL_PASS"))
        for _c in eval_result.get("columns", []):
            status[_c.get("id", "")] = bool(_c.get("stress_PASS") and _c.get("buckling_PASS"))

    levels = get_level_keys(layout) or ["level_01"]
    n_levels = len(levels)
    layout_id = layout.get("layoutId", "—")
    today = _dt.date.today().isoformat()
    summary = (eval_result or {}).get("summary", {})
    _meta_mat = (layout.get("meta") or {}).get("material") or material

    # ── Diff + per-change material/section description (intervention mode) ──
    diff = _compute_diff(before_layout, layout) if before_layout else None
    chg_desc: dict[str, str] = {}
    if before_layout and diff:
        _bmap = {f"{lk}|{e['id']}": e for lk, e in iter_all_structure(before_layout)}
        _amap = {f"{lk}|{e['id']}": e for lk, e in iter_all_structure(layout)}
        for k in diff["changed"]:
            ba = (_bmap[k].get("attributes") or {}); aa = (_amap[k].get("attributes") or {})
            if str(ba.get("material") or "") != str(aa.get("material") or ""):
                chg_desc[k] = f"mat {ba.get('material') or '—'}→{aa.get('material') or '—'}"
            else:
                _bs = (ba.get("section") or ba.get("dimensions") or ba.get("col_dims")
                       or f"{ba.get('width','')}x{ba.get('depth','')}")
                _as = (aa.get("section") or aa.get("dimensions") or aa.get("col_dims")
                       or f"{aa.get('width','')}x{aa.get('depth','')}")
                chg_desc[k] = f"sec {_bs}→{_as}"

    def _lvl_material(lay, lk):
        cnt: dict = {}
        for e in get_structure(lay, lk):
            m = (e.get("attributes") or {}).get("material")
            if m:
                cnt[str(m)] = cnt.get(str(m), 0) + 1
        return max(cnt, key=cnt.get) if cnt else _meta_mat

    def _draw_plan(ax, lay, lk, title, diff_mode=False):
        outline = get_outline(lay, lk); rooms = get_rooms(lay, lk)
        structure = get_structure(lay, lk)
        cols  = [e for e in structure if len(e.get("geometry", [])) == 1]
        beams = [e for e in structure if len(e.get("geometry", [])) == 2]
        lvl_mat = _lvl_material(lay, lk)
        for r in rooms:
            g = r.get("geometry", [])
            if len(g) >= 3:
                ax.fill([p[0] for p in g], [p[1] for p in g], color="#f2f2f2",
                        ec="#dcdcdc", lw=0.6, zorder=1)
                if r.get("name") and not diff_mode:
                    ax.text(sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g),
                            r["name"], ha="center", va="center", fontsize=6, color="#b0b0b0", zorder=2)
        if len(outline) >= 2:
            ax.plot([p[0] for p in outline] + [outline[0][0]],
                    [p[1] for p in outline] + [outline[0][1]], color="#111", lw=2.2, zorder=4)
        # Removed elements (intervention only): dashed red ghosts from the original.
        if diff_mode and diff and before_layout:
            for k in diff["removed"]:
                _lvl, _, _eid = k.partition("|")
                if _lvl != lk:
                    continue
                _re = next((e for e in get_structure(before_layout, _lvl) if e.get("id") == _eid), None)
                g = _re.get("geometry", []) if _re else []
                if len(g) == 1:
                    ax.add_patch(_plt.Rectangle((g[0][0] - 0.15, g[0][1] - 0.15), 0.30, 0.30,
                                                facecolor="none", edgecolor=RED, lw=1.2, ls="--", zorder=6))
                elif len(g) == 2:
                    ax.plot([g[0][0], g[1][0]], [g[0][1], g[1][1]], color=RED, lw=1.8, ls="--", zorder=5)

        def _col(el):
            k = f"{lk}|{el.get('id')}"
            if diff_mode and diff:
                if k in diff["added"]:   return GREEN
                if k in diff["changed"]: return PURPLE
            if status.get(el.get("id")) is False:
                return RED
            return _material_color((el.get("attributes") or {}).get("material") or lvl_mat, True)

        for b in beams:
            g = b.get("geometry", [])
            if len(g) < 2:
                continue
            ax.plot([g[0][0], g[1][0]], [g[0][1], g[1][1]], color=_col(b), lw=2.4,
                    zorder=5, solid_capstyle="round")
        for c in cols:
            g = c.get("geometry", [])
            if not g:
                continue
            ax.add_patch(_plt.Rectangle((g[0][0] - 0.15, g[0][1] - 0.15), 0.30, 0.30,
                                        facecolor=_col(c), edgecolor="#111", lw=0.7, zorder=6))
        if show_labels and not diff_mode:
            for b in beams:
                g = b.get("geometry", [])
                if len(g) >= 2:
                    ax.text((g[0][0] + g[1][0]) / 2, (g[0][1] + g[1][1]) / 2, b.get("id", ""),
                            fontsize=4.5, color="#3a3a3a", ha="center", va="center", zorder=8)
            for c in cols:
                g = c.get("geometry", [])
                if g:
                    ax.text(g[0][0], g[0][1] - 0.34, c.get("id", ""), fontsize=4.5,
                            color="#111", ha="center", va="top", zorder=8)
        # Annotate changed elements with the material/section change.
        if diff_mode and diff:
            for k in diff["changed"]:
                _lvl, _, _eid = k.partition("|")
                if _lvl != lk:
                    continue
                _el = next((e for e in structure if e.get("id") == _eid), None)
                g = _el.get("geometry", []) if _el else []
                if not g:
                    continue
                px = g[0][0] if len(g) == 1 else (g[0][0] + g[1][0]) / 2
                py = g[0][1] if len(g) == 1 else (g[0][1] + g[1][1]) / 2
                ax.text(px, py + 0.22, chg_desc.get(k, ""), fontsize=3.8, color=PURPLE,
                        ha="center", va="bottom", zorder=9)
        ax.set_aspect("equal"); ax.grid(True, color="#eee", lw=0.5)
        ax.set_title(title, fontsize=11, fontweight="bold", color="#111", loc="left", pad=8)
        ax.tick_params(labelsize=6, colors="#999")

    buf = _io.BytesIO()
    with _PdfPages(buf) as pdf:
        # ── Report cover / explanation page ──
        if report_text:
            cfig = _plt.figure(figsize=(16.54, 11.69), facecolor="white")
            cfig.add_artist(_plt.Rectangle((0.012, 0.02), 0.976, 0.96, fill=False,
                                           ec="#222", lw=2, transform=cfig.transFigure))
            cax = cfig.add_axes([0.06, 0.05, 0.88, 0.9]); cax.axis("off")
            cax.text(0.0, 1.0, "INTERVENTION REPORT" if before_layout else "STRUCTURAL REPORT",
                     fontsize=22, fontweight="bold", color="#111", va="top", transform=cax.transAxes)
            cax.text(0.0, 0.955, f"{project}   ·   {layout_id}   ·   {today}"
                     + (f"   ·   Prepared by: {prepared_by}" if prepared_by else ""),
                     fontsize=11, color="#555", va="top", transform=cax.transAxes)
            cax.plot([0, 1], [0.93, 0.93], color="#222", lw=1, transform=cax.transAxes)
            _wrapped = "\n".join(_tw.fill(_ln, 108) if _ln.strip() else ""
                                 for _ln in report_text.splitlines())
            cax.text(0.0, 0.89, _wrapped, fontsize=9.5, color="#222", va="top",
                     transform=cax.transAxes, family="monospace", linespacing=1.5)
            pdf.savefig(cfig, facecolor="white")
            _plt.close(cfig)

        for si, lk in enumerate(levels, 1):
            fig = _plt.figure(figsize=(16.54, 11.69), facecolor="white")  # A3 landscape
            fig.add_artist(_plt.Rectangle((0.012, 0.02), 0.976, 0.96, fill=False,
                                          ec="#222", lw=2, transform=fig.transFigure))

            if before_layout:
                # Intervention: ORIGINAL (left) beside INTERVENTION diff (right).
                axL = fig.add_axes([0.04, 0.10, 0.44, 0.80]); axL.set_facecolor("white")
                axR = fig.add_axes([0.53, 0.10, 0.44, 0.80]); axR.set_facecolor("white")
                _draw_plan(axL, before_layout, lk, f"ORIGINAL — {lk.upper()}", diff_mode=False)
                _draw_plan(axR, layout, lk, f"INTERVENTION — {lk.upper()}", diff_mode=True)
                fig.text(0.04, 0.945, "INTERVENTION PLAN", fontsize=15, fontweight="bold", color="#111")
                fig.text(0.53, 0.05, "■ added", color=GREEN, fontsize=9, fontweight="bold")
                fig.text(0.62, 0.05, "▦ removed (dashed)", color=RED, fontsize=9, fontweight="bold")
                fig.text(0.80, 0.05, "■ changed (mat/sec)", color=PURPLE, fontsize=9, fontweight="bold")
                fig.text(0.965, 0.05, f"S-{si:02d}/{n_levels:02d}", fontsize=9, ha="right", color="#555")
            else:
                # Normal sheet: plan (left) + title block (right).
                ax = fig.add_axes([0.05, 0.07, 0.60, 0.88]); ax.set_facecolor("white")
                _draw_plan(ax, layout, lk, f"STRUCTURAL FRAMING PLAN — {lk.upper()}")
                _structure = get_structure(layout, lk)
                _ncol = sum(1 for e in _structure if len(e.get("geometry", [])) == 1)
                _nbm  = sum(1 for e in _structure if len(e.get("geometry", [])) == 2)
                tb = fig.add_axes([0.67, 0.07, 0.30, 0.88]); tb.axis("off")
                tb.add_patch(_plt.Rectangle((0, 0), 1, 1, transform=tb.transAxes,
                                            fill=False, ec="#222", lw=1.4))
                tb.plot([0, 1], [0.93, 0.93], transform=tb.transAxes, color="#222", lw=1.0)
                tb.text(0.5, 0.975, "PermanenceOS — Structural Sheet", ha="center", va="top",
                        fontsize=11, fontweight="bold", transform=tb.transAxes)
                rows = [("Project", project), ("Layout ID", layout_id), ("Level", lk),
                        ("Date", today), ("Material", _lvl_material(layout, lk)),
                        ("Columns", str(_ncol)), ("Beams", str(_nbm))]
                if prepared_by:
                    rows.insert(4, ("Prepared by", prepared_by))
                if eval_result:
                    rows += [("Overall", "PASS" if summary.get("overall_PASS") else "FAIL"),
                             ("Beam failures", str(summary.get("beam_failures", 0))),
                             ("Column failures", str(summary.get("column_failures", 0)))]
                y = 0.88
                for k, v in rows:
                    tb.text(0.04, y, k.upper(), fontsize=7, color="#888", transform=tb.transAxes, va="top")
                    tb.text(0.96, y, str(v), fontsize=8, color="#111", ha="right",
                            fontweight="bold", transform=tb.transAxes, va="top")
                    y -= 0.045
                if revisions:
                    y -= 0.01
                    tb.text(0.04, y, "REVISIONS", fontsize=7, color="#888", transform=tb.transAxes, va="top"); y -= 0.04
                    for rv in list(revisions)[-7:]:
                        tb.text(0.04, y, f"• {str(rv)[:46]}", fontsize=6.5, color="#555",
                                transform=tb.transAxes, va="top"); y -= 0.032
                tb.plot([0, 1], [0.07, 0.07], transform=tb.transAxes, color="#222", lw=0.8)
                tb.text(0.04, 0.04, "SCALE: NTS", fontsize=7.5, color="#555", transform=tb.transAxes)
                tb.text(0.96, 0.04, f"S-{si:02d} / {n_levels:02d}", fontsize=10,
                        fontweight="bold", ha="right", transform=tb.transAxes)

            pdf.savefig(fig, facecolor="white")
            _plt.close(fig)
    return buf.getvalue()


@st.cache_data(show_spinner="Building structural sheet…")
def _sheet_pdf_bytes(layout_json: str, eval_json: str, project: str,
                     material: str, revs: tuple, show_labels: bool = False,
                     report_text: str = "", before_json: str = "",
                     prepared_by: str = "") -> bytes:
    """Cached wrapper — rebuilds only when any input changes (incl. the exact layout
    JSON, so the sheet always matches the version being exported). `before_json` set →
    intervention report (original + diff plan)."""
    return _build_structural_sheet_pdf(
        json.loads(layout_json),
        json.loads(eval_json) if eval_json else None,
        project, material, list(revs),
        show_labels=show_labels,
        report_text=report_text or None,
        before_layout=json.loads(before_json) if before_json else None,
        prepared_by=prepared_by,
    )


@st.cache_data(show_spinner=False)
def _beam_diagram_png(span: float, w: float, m_max: float, label: str, is_light: bool) -> bytes:
    """Shear-force + bending-moment diagram for a simply-supported beam under a UDL.
    Computed from first principles (V = w(L/2 − x), M = w·x(L−x)/2) — no LLM needed."""
    import io as _io
    import numpy as _np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt

    L = max(float(span or 0.0), 0.001)
    w = float(w or 0.0)
    if not m_max:
        m_max = w * L * L / 8.0
    x = _np.linspace(0, L, 60)
    V = w * (L / 2.0 - x)
    M = w * x * (L - x) / 2.0

    fg  = "#1a3535" if is_light else "#c8eeed"
    bg  = "#ffffff" if is_light else "#0c2020"
    acc = "#3f87d6"
    mom = "#cf8a3c"
    she = "#1a8050" if is_light else "#40d090"

    fig, axes = _plt.subplots(3, 1, figsize=(4.6, 5.0), facecolor=bg,
                              gridspec_kw=dict(height_ratios=[1, 1.2, 1.2], hspace=0.55))
    for ax in axes:
        ax.set_facecolor(bg)
        for s in ax.spines.values():
            s.set_color(fg)

    a0 = axes[0]
    a0.plot([0, L], [0, 0], color=fg, lw=2)
    a0.plot([0, L], [0.55, 0.55], color=acc, lw=1)
    for xi in _np.linspace(0, L, 11):
        a0.annotate("", xy=(xi, 0), xytext=(xi, 0.55),
                    arrowprops=dict(arrowstyle="->", color=acc, lw=1))
    a0.plot([0], [0], marker="^", color=fg, ms=11)
    a0.plot([L], [0], marker="^", color=fg, ms=11)
    a0.set_title(f"{label}   ·   L = {L:.2f} m   ·   w = {w:.2f} kN/m",
                 color=fg, fontsize=8.5, fontweight="bold")
    a0.set_ylim(-0.35, 0.95)
    a0.axis("off")

    a1 = axes[1]
    a1.fill_between(x, V, color=she, alpha=0.30)
    a1.plot(x, V, color=she, lw=1.6)
    a1.axhline(0, color=fg, lw=0.8)
    a1.set_title("Shear Force  V (kN)", color=fg, fontsize=8.5)
    a1.tick_params(colors=fg, labelsize=6)
    a1.text(0, w * L / 2, f"+{w * L / 2:.1f}", color=she, fontsize=7, va="bottom")
    a1.text(L, -w * L / 2, f"−{w * L / 2:.1f}", color=she, fontsize=7, va="top", ha="right")

    a2 = axes[2]
    a2.fill_between(x, M, color=mom, alpha=0.30)
    a2.plot(x, M, color=mom, lw=1.6)
    a2.axhline(0, color=fg, lw=0.8)
    a2.set_title("Bending Moment  M (kN·m)", color=fg, fontsize=8.5)
    a2.tick_params(colors=fg, labelsize=6)
    a2.set_xlabel("x (m)", color=fg, fontsize=7)
    a2.annotate(f"Mmax = {m_max:.1f}", xy=(L / 2, M.max() if len(M) else m_max),
                color=mom, fontsize=7, ha="center", va="bottom", fontweight="bold")

    buf = _io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=bg, bbox_inches="tight")
    _plt.close(fig)
    return buf.getvalue()


# ── Flexibility & replacement advice (architect-facing) ─────────────────────────
def _flexibility_rows(eval_result: dict | None) -> list[dict]:
    """Rank every element by utilisation (governing demand/capacity ratio) and attach
    a plain-language flexibility verdict + replacement suggestion. Pure read of the
    existing evaluation fields — no new structural math."""
    rows: list[dict] = []
    if not eval_result:
        return rows
    for b in eval_result.get("beams", []):
        rats = []
        if b.get("allow_bend_MPa"):  rats.append((b.get("sigma_bend_MPa", 0) / b["allow_bend_MPa"], "bending"))
        if b.get("allow_shear_MPa"): rats.append((b.get("tau_MPa", 0) / b["allow_shear_MPa"], "shear"))
        if b.get("limit_TL_mm"):     rats.append((b.get("delta_total_mm", 0) / b["limit_TL_mm"], "deflection"))
        u, gov = max(rats, default=(0.0, "—"))
        rows.append({"id": b.get("id", "?"), "kind": "beam", "util": round(u * 100),
                     "gov": gov, "sec": b.get("section_mm", "")})
    for c in eval_result.get("columns", []):
        rats = []
        if c.get("allow_comp_MPa"): rats.append((c.get("sigma_comp_MPa", 0) / c["allow_comp_MPa"], "compression"))
        if c.get("SF_buckling"):    rats.append((3.0 / c["SF_buckling"], "buckling"))
        u, gov = max(rats, default=(0.0, "—"))
        rows.append({"id": c.get("id", "?"), "kind": "column", "util": round(u * 100),
                     "gov": gov, "sec": c.get("section_mm", "")})
    rows.sort(key=lambda r: r["util"], reverse=True)
    return rows


def _flex_advice(util: float) -> tuple[str, str]:
    """(verdict, suggestion) for a utilisation percentage."""
    if util > 100:
        return ("over capacity", "upgrade a size, add a midspan column, or switch to a stiffer material")
    if util >= 85:
        return ("critical", "near the limit — upgrade one size or add support before relying on it")
    if util < 40:
        return ("very slack", "downsize a tier or use a lighter material to cut weight & cost")
    if util < 65:
        return ("flexible", "spare capacity — a candidate for a lighter section")
    return ("efficient", "well utilised — leave as is")


# ── Structure ↔ opening (door/window) clash detection ───────────────────────────
def _seg_pt_dist(p, a, b) -> float:
    """Distance from point p to segment a-b."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _segs_intersect(p1, p2, p3, p4) -> bool:
    def _ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return (_ccw(p1, p3, p4) != _ccw(p2, p3, p4)
            and _ccw(p1, p2, p3) != _ccw(p1, p2, p4))


def _opening_clashes(layout: dict, level_key: str | None = None, tol: float = 0.3) -> set:
    """Return ids of structural elements that clash with a door/window opening on the
    given level: a COLUMN sitting in/near an opening, or a BEAM crossing an opening.
    (Beams use a true intersection test so perimeter lintel-beams aren't false-flagged.)"""
    lvl = _get_level_payload(layout, level_key) if level_key else {}
    openings = []
    for o in (lvl.get("doors", []) or []) + (lvl.get("windows", []) or []):
        g = o.get("geometry", [])
        if len(g) >= 2:
            openings.append((g[0], g[1]))
    if not openings:
        return set()
    clash = set()
    for el in get_structure(layout, level_key):
        g = el.get("geometry", [])
        if len(g) == 1:
            if any(_seg_pt_dist(g[0], a, b) < tol for a, b in openings):
                clash.add(el.get("id"))
        elif len(g) == 2:
            if any(_segs_intersect(g[0], g[1], a, b) for a, b in openings):
                clash.add(el.get("id"))
    return clash


