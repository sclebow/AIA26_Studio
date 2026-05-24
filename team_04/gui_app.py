from __future__ import annotations
import json, math, sys, time
from pathlib import Path
import folium
from folium.plugins import Draw
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).parent))
try:
    from agent.tools.generate_building_boundary import (
        generate_building_boundary,
        SUPPORTED_BUILDING_TYPES,
    )
except Exception:
    SUPPORTED_BUILDING_TYPES = ("I", "L", "T", "Y", "H", "X", "O")
    def generate_building_boundary(area, building_type="I", **_kw):
        w = math.sqrt(area)
        pts = [(-w/2,-w/2),(w/2,-w/2),(w/2,w/2),(-w/2,w/2)]
        return {"success":True,"data":{"boundary":[[x,y,0.] for x,y in pts],"boundary_area_sqm":area,"perimeter_m":4*w,"centroid":[0.,0.,0.],"shape_type":building_type}}

BUILDING_FUNCTIONS = ("residential","commercial","healthcare","institutional","entertainment","mixed use")
SHAPE_DESCRIPTIONS = {"I":"linear bar","L":"L-shaped wing","T":"T-shaped","Y":"Y-branched","H":"H-courtyard","X":"cross / plus","O":"O-courtyard"}

# wizard steps: 0=shape, 1=function, 2=floors, 3=trees, 4=done
_DEFAULTS = {
    "site_lat": 41.0082,
    "site_lon": 28.9784,
    "drawn_area": None,
    "step": 0,
    "building_shape": None,
    "building_function": None,
    "building_floors": None,
    "building_trees": None,
    "building_boundary": None,
    "building_area_sqm": None,
    "pending_input": None,
    "chat_history": [],
}

st.set_page_config(page_title="TerraPilot", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');
html,body,[class*="css"],[data-testid="stAppViewContainer"]*{
    font-family:'JetBrains Mono','Fira Code',monospace;
    color:#5b5b5b;
}
[data-testid="stAppViewContainer"]{background:#ffffff;}
[data-testid="stHeader"]{background:rgba(255,255,255,0.92);}
.block-container{padding-top:1rem;padding-bottom:2rem;max-width:1500px;}
.artboard{border:1px solid #2f2f2f;padding:16px 22px 28px 22px;background:#ffffff;}
.top-rule{border-top:1px solid #3c3c3c;margin-top:8px;margin-bottom:14px;}
.brand-row{display:flex;align-items:baseline;gap:18px;flex-wrap:wrap;margin-bottom:8px;}
.brand{font-size:20px;font-weight:700;letter-spacing:0.3px;color:#6d6d6d;}
.tagline{font-size:11px;font-style:italic;color:#7d7d7d;}
.flowline{font-size:10px;color:#ff5d5d;letter-spacing:0.2px;white-space:nowrap;}
.coord-meta{font-size:9px;line-height:1.45;color:#818181;margin-top:4px;margin-bottom:6px;}
.site-desc{font-size:9px;line-height:1.65;color:#b8b8b8;margin-top:5px;margin-bottom:10px;border-top:1px solid #f0f0f0;padding-top:6px;}
.rhino-bar{background:#1a1a1a;color:#555555;font-size:9px;padding:5px 12px;display:flex;gap:12px;align-items:center;border-radius:2px 2px 0 0;}
/* prompt input */
.stTextInput input{
    font-size:12px !important;
    font-family:'JetBrains Mono',monospace !important;
    background:#f8f8f8 !important;
    border:1px solid #d0d0d0 !important;
    border-radius:3px !important;
    color:#2e2e2e !important;
    padding:10px 14px !important;
}
.stTextInput input:focus{background:#f2f2f2 !important;border-color:#888 !important;box-shadow:none !important;}
.stTextInput input::placeholder{color:#aaa !important;font-style:italic !important;}
div[data-testid="stFormSubmitButton"]>button{
    width:100% !important;background:#f0f0f0 !important;color:#666 !important;
    border:1px solid #d8d8d8 !important;border-radius:3px !important;
    font-size:11px !important;letter-spacing:0.5px !important;margin-top:4px !important;
}
div[data-testid="stFormSubmitButton"]>button:hover{background:#e4e4e4 !important;border-color:#aaa !important;}
.stButton>button{font-size:11px !important;padding:4px 10px !important;}
.prompt-question{
    font-size:11px;color:#4a4a4a;letter-spacing:0.2px;
    margin-bottom:6px;line-height:1.7;
    border-left:2px solid #cccccc;padding-left:10px;
}
.prompt-hint{font-size:10px;color:#aaaaaa;margin-bottom:8px;font-style:italic;}
.chat-bubble-user{font-size:11px;color:#3a3a3a;background:#f5f5f5;border-radius:3px;padding:7px 11px;margin-bottom:4px;text-align:right;}
.chat-bubble-agent{font-size:11px;color:#5a5a5a;margin-bottom:10px;line-height:1.7;}
.step-done{font-size:10px;color:#aaa;border-bottom:1px solid #f0f0f0;padding-bottom:6px;margin-bottom:6px;}
</style>
""", unsafe_allow_html=True)

for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── helpers ───────────────────────────────────────────────────────────────────
def _bbox_from_center(lat, lon, radius_km=5.0):
    lat_d = radius_km / 111.32
    lon_d = radius_km / max(math.cos(math.radians(lat)) * 111.32, 0.0001)
    return {"north": lat+lat_d, "south": lat-lat_d, "east": lon+lon_d, "west": lon-lon_d}

cad_bbox = _bbox_from_center(st.session_state.site_lat, st.session_state.site_lon)

def _site_polygon_latlon():
    if st.session_state.drawn_area:
        geom = st.session_state.drawn_area.get("geometry", {})
        coords = geom.get("coordinates", [[]])[0]
        return [c[0] for c in coords], [c[1] for c in coords]
    b = cad_bbox
    return ([b["west"],b["east"],b["east"],b["west"],b["west"]],
            [b["south"],b["south"],b["north"],b["north"],b["south"]])

def _site_area_sqm():
    lons, lats = _site_polygon_latlon()
    n = len(lats)-1; area=0.
    for i in range(n): area += lats[i]*lons[i+1]-lats[i+1]*lons[i]
    area = abs(area)/2.
    clat = sum(lats)/len(lats)
    return area * 111320. * (111320. * math.cos(math.radians(clat)))

def _generate_boundary():
    site_sqm = _site_area_sqm()
    footprint = max(site_sqm * 0.35, 200.)
    try:
        res = generate_building_boundary(
            area=footprint,
            building_type=st.session_state.building_shape,
            rotation_degrees=0.0,
        )
        data = res["data"]
        st.session_state.building_boundary = data["boundary"]
        st.session_state.building_area_sqm = data["boundary_area_sqm"]
    except Exception:
        st.session_state.building_boundary = None
        st.session_state.building_area_sqm = footprint

# ── Rhino viewport ────────────────────────────────────────────────────────────
def _rhino_fig():
    fig = go.Figure()
    GR, STEP = 55, 10
    for v in range(-GR, GR+1, STEP):
        for xs, ys in [([v,v],[-GR,GR]),([-GR,GR],[v,v])]:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                line=dict(color="#1c1c1c", width=1), showlegend=False, hoverinfo="skip"))
    for xs, ys in [([-GR,GR],[0,0]),([0,0],[-GR,GR])]:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
            line=dict(color="#282828", width=1.5), showlegend=False, hoverinfo="skip"))

    lons, lats = _site_polygon_latlon()
    clat = sum(lats)/len(lats); clon = sum(lons)/len(lons)
    cos_lat = math.cos(math.radians(clat))
    sx_m = [(lo-clon)*cos_lat*111320 for lo in lons]
    sy_m = [(la-clat)*111320 for la in lats]
    max_ext = max(max(abs(x) for x in sx_m), max(abs(y) for y in sy_m), 1.)
    scale = (GR*0.80)/max_ext
    sx = [x*scale for x in sx_m]; sy = [y*scale for y in sy_m]
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines",
        line=dict(color="#383838", width=1, dash="dot"),
        fill="toself", fillcolor="rgba(255,255,255,0.015)",
        showlegend=False, hoverinfo="skip"))

    if st.session_state.building_boundary:
        bpts = st.session_state.building_boundary
        bxs = [p[0]*scale for p in bpts]+[bpts[0][0]*scale]
        bys = [p[1]*scale for p in bpts]+[bpts[0][1]*scale]
        fig.add_trace(go.Scatter(x=bxs, y=bys, mode="lines",
            line=dict(color="#ffffff", width=2),
            fill="toself", fillcolor="rgba(255,255,255,0.06)",
            showlegend=False, hovertemplate=f"{st.session_state.building_shape} footprint<extra></extra>"))
        fig.add_annotation(x=0, y=0, text=st.session_state.building_shape or "",
            showarrow=False, font=dict(size=16, color="#444444", family="JetBrains Mono"))

    # tree dots
    if st.session_state.building_trees and st.session_state.building_trees > 0:
        import random; random.seed(42)
        n = min(st.session_state.building_trees, 50)
        txs = [random.uniform(-GR*0.7, GR*0.7) for _ in range(n)]
        tys = [random.uniform(-GR*0.7, GR*0.7) for _ in range(n)]
        fig.add_trace(go.Scatter(x=txs, y=tys, mode="markers",
            marker=dict(color="#3a5a3a", size=5, symbol="circle"),
            showlegend=False, hoverinfo="skip"))

    fig.update_layout(
        plot_bgcolor="#0f0f0f", paper_bgcolor="#0a0a0a",
        margin=dict(l=0,r=0,t=0,b=0),
        xaxis=dict(visible=False, range=[-GR-3,GR+3], scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False, range=[-GR-3,GR+3]),
        height=460,
    )
    fig.add_annotation(x=0.01, y=0.98, xref="paper", yref="paper", text="TOP",
        showarrow=False, font=dict(size=9, color="#444444", family="JetBrains Mono"),
        xanchor="left", yanchor="top")

    parts = []
    if st.session_state.building_shape: parts.append(st.session_state.building_shape)
    if st.session_state.building_function: parts.append(st.session_state.building_function)
    if st.session_state.building_floors: parts.append(f"{st.session_state.building_floors}F")
    if st.session_state.building_trees: parts.append(f"{st.session_state.building_trees} trees")
    if parts:
        fig.add_annotation(x=0.99, y=0.98, xref="paper", yref="paper",
            text="  ·  ".join(parts), showarrow=False,
            font=dict(size=9, color="#555555", family="JetBrains Mono"),
            xanchor="right", yanchor="top")
    return fig

# ── wizard step processor ─────────────────────────────────────────────────────
STEP_QUESTIONS = [
    # (question_text, hint_text, field, validator_fn)
    (
        "1 — select your building shape",
        "(I · L · T · Y · H · X · O)",
        "building_shape",
    ),
    (
        "2 — specify your building function",
        "(residential · commercial · healthcare · institutional · entertainment · mixed use)",
        "building_function",
    ),
    (
        "3 — how many floors?",
        "(enter a number, e.g. 8)",
        "building_floors",
    ),
    (
        "4 — how many trees on the site?",
        "(enter a number, e.g. 12 — or type 0 for none)",
        "building_trees",
    ),
]

def _validate_shape(val: str) -> tuple[bool, str]:
    v = val.strip().upper()
    if v in SUPPORTED_BUILDING_TYPES: return True, v
    aliases = {"RECTANGLE":"I","RECT":"I","LINEAR":"I","BAR":"I","CROSS":"X","PLUS":"X","COURTYARD":"O"}
    if v in aliases: return True, aliases[v]
    return False, f"unrecognised shape — please enter one of: {' · '.join(SUPPORTED_BUILDING_TYPES)}"

def _validate_function(val: str) -> tuple[bool, str]:
    v = val.strip().lower()
    for f in BUILDING_FUNCTIONS:
        if f.startswith(v) or v in f: return True, f
    return False, f"unrecognised function — try: {' · '.join(BUILDING_FUNCTIONS)}"

def _validate_floors(val: str) -> tuple[bool, int]:
    try:
        n = int(val.strip())
        if 1 <= n <= 200: return True, n
        return False, "please enter a number between 1 and 200"
    except ValueError:
        return False, "please enter a valid number"

def _validate_trees(val: str) -> tuple[bool, int]:
    try:
        n = int(val.strip())
        if n >= 0: return True, n
        return False, "please enter 0 or more"
    except ValueError:
        return False, "please enter a valid number (0 for none)"

VALIDATORS = [_validate_shape, _validate_function, _validate_floors, _validate_trees]
FIELDS = ["building_shape", "building_function", "building_floors", "building_trees"]

def _process_step(user_input: str) -> tuple[bool, str]:
    """Returns (ok, message). If ok, advances the step."""
    step = st.session_state.step
    if step >= len(VALIDATORS):
        return False, "design is complete. type 'reset' to start over."
    ok, result = VALIDATORS[step](user_input)
    if not ok:
        return False, result
    st.session_state[FIELDS[step]] = result
    st.session_state.step += 1
    if st.session_state.step == 4:
        _generate_boundary()
    return True, result

# ── layout ────────────────────────────────────────────────────────────────────
st.markdown("<div class='artboard'>", unsafe_allow_html=True)
st.markdown("""
<div class="brand-row">
  <div class="brand">TerraPilot |</div>
  <div class="tagline">your site &amp; building in minutes!</div>
  <div class="flowline">select site &rarr; draw boundary &rarr; define building &rarr; preview &rarr; export</div>
</div>
<div class="top-rule"></div>
""", unsafe_allow_html=True)

left_col, main_col = st.columns([1.2, 4.8], gap="large")

# ── left: site map ────────────────────────────────────────────────────────────
with left_col:
    _m = folium.Map(
        location=[st.session_state.site_lat, st.session_state.site_lon],
        zoom_start=14, tiles="CartoDB Positron", width="100%",
    )
    if st.session_state.drawn_area:
        folium.GeoJson(st.session_state.drawn_area, style_function=lambda _: {
            "color":"#111111","weight":1.5,"fillColor":"#111111","fillOpacity":0.06}).add_to(_m)
    else:
        b = cad_bbox
        folium.Rectangle(
            bounds=[[b["south"],b["west"]],[b["north"],b["east"]]],
            color="#aaaaaa", weight=1, fill=True, fill_color="#aaaaaa",
            fill_opacity=0.04, dash_array="4 4").add_to(_m)

    folium.Marker(
        location=[st.session_state.site_lat, st.session_state.site_lon],
        icon=folium.DivIcon(
            html="<div style='width:8px;height:8px;background:#111;border-radius:50%;'></div>",
            icon_size=(8,8), icon_anchor=(4,4))).add_to(_m)

    Draw(
        draw_options={"polyline":False,"polygon":{"allowIntersection":False},"circle":False,"marker":False,"circlemarker":False,"rectangle":True},
        edit_options={"edit":False,"remove":True},
    ).add_to(_m)

    map_data = st_folium(_m, key="site_map", height=380, width=None)

    if map_data:
        drawings = map_data.get("all_drawings") or []
        if drawings:
            latest = drawings[-1]
            if json.dumps(latest,sort_keys=True) != json.dumps(st.session_state.drawn_area,sort_keys=True):
                st.session_state.drawn_area = latest
        lc = map_data.get("last_clicked")
        if lc and not drawings and not st.session_state.drawn_area:
            nlat, nlon = round(lc["lat"],6), round(lc["lng"],6)
            if nlat != st.session_state.site_lat or nlon != st.session_state.site_lon:
                st.session_state.site_lat = nlat
                st.session_state.site_lon = nlon
                st.rerun()

    area_label = "custom area" if st.session_state.drawn_area else "\u00b15 km auto"
    st.markdown(f"<div class='coord-meta'>{st.session_state.site_lat:.5f}, {st.session_state.site_lon:.5f} &nbsp;|&nbsp; {area_label}</div>", unsafe_allow_html=True)

    if st.session_state.drawn_area:
        if st.button("clear drawing", key="clear_draw"):
            for k in ("drawn_area","building_boundary","building_area_sqm"):
                st.session_state[k] = None
            st.rerun()

    if st.session_state.step > 0 or st.session_state.building_shape:
        if st.button("↺ reset design", key="reset_btn"):
            for k, v in _DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()

    st.markdown("""
    <div class='site-desc'>
        TerraPilot is an AI site agent that reads your chosen plot, understands its
        urban context, and guides you through building geometry, programme, and
        orientation &mdash; producing a Grasshopper-ready brief in minutes.<br/><br/>
        <span style='color:#d0d0d0;'>&copy; 2026 IAAC &middot; Team 4 &mdash; all rights reserved.</span>
    </div>""", unsafe_allow_html=True)

# ── right: viewport + wizard ──────────────────────────────────────────────────
with main_col:
    # rhino bar
    st.markdown("""
    <div class='rhino-bar'>
        <span style='color:#c0392b;font-size:8px;'>&#9632;</span>
        <span style='color:#e67e22;font-size:8px;'>&#9632;</span>
        <span style='color:#2ecc71;font-size:8px;'>&#9632;</span>
        &nbsp;&nbsp; Rhino 8 &nbsp;&rarr;&nbsp; TOP &nbsp;|&nbsp; TerraPilot viewport
    </div>""", unsafe_allow_html=True)

    st.plotly_chart(_rhino_fig(), use_container_width=True, config={"displayModeBar":False})

    # ── wizard prompt area ────────────────────────────────────────────────────
    step = st.session_state.step

    # show completed steps summary
    if step > 0:
        done_lines = []
        if st.session_state.building_shape:
            done_lines.append(f"shape: <b>{st.session_state.building_shape}</b> — {SHAPE_DESCRIPTIONS[st.session_state.building_shape]}")
        if st.session_state.building_function:
            done_lines.append(f"function: <b>{st.session_state.building_function}</b>")
        if st.session_state.building_floors:
            done_lines.append(f"floors: <b>{st.session_state.building_floors}</b>")
        if st.session_state.building_trees is not None:
            done_lines.append(f"trees: <b>{st.session_state.building_trees}</b>")
        if done_lines:
            st.markdown(f"<div class='step-done'>{' &nbsp;·&nbsp; '.join(done_lines)}</div>", unsafe_allow_html=True)

    if step == 4:
        # all done — show summary
        fa = round(st.session_state.building_area_sqm or 0)
        fl = st.session_state.building_floors or 0
        h = round(fl * 3.2, 1)
        st.markdown(f"""
<div class='prompt-question'>
✓ &nbsp; building brief generated
</div>
<div class='chat-bubble-agent'>

| | |
|---|---|
| shape | **{st.session_state.building_shape}** — {SHAPE_DESCRIPTIONS.get(st.session_state.building_shape,"")} |
| function | **{st.session_state.building_function}** |
| floors | **{fl}** |
| footprint | **{fa:,} m²** |
| height | **≈ {h} m** |
| GFA | **{fa*fl:,} m²** |
| trees | **{st.session_state.building_trees}** |

_viewport updated — Grasshopper pipeline ready._
</div>
""", unsafe_allow_html=True)

    elif step < len(STEP_QUESTIONS):
        q, hint, _ = STEP_QUESTIONS[step]
        st.markdown(f"<div class='prompt-question'>{q}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='prompt-hint'>{hint}</div>", unsafe_allow_html=True)

        # handle pending
        if st.session_state.pending_input is not None:
            val = st.session_state.pending_input
            st.session_state.pending_input = None
            st.markdown(f"<div class='chat-bubble-user'>{val}</div>", unsafe_allow_html=True)
            ph = st.empty()
            thinking = ["reading input…","validating…","updating…"]
            for t in thinking:
                ph.markdown(f"<div style='font-size:10px;color:#bbb;'>{t}</div>", unsafe_allow_html=True)
                time.sleep(0.2)
            ph.empty()
            ok, msg = _process_step(val)
            if not ok:
                st.markdown(f"<div class='chat-bubble-agent' style='color:#cc4444;'>⚠ {msg}</div>", unsafe_allow_html=True)
            else:
                st.rerun()

        with st.form(key=f"step_form_{step}", clear_on_submit=True):
            user_val = st.text_input(
                label="input",
                label_visibility="collapsed",
                placeholder="type here and press enter…",
                key=f"step_input_{step}",
            )
            submitted = st.form_submit_button("→ confirm")
            if submitted and user_val.strip():
                st.session_state.pending_input = user_val.strip()
                st.rerun()

st.markdown("</div>", unsafe_allow_html=True)
