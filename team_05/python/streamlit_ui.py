"""
AIA Studio Cost Advisor — Team 05
Streamlit GUI: interactive floor-plan cost heatmap + agent chat.

Run with:  streamlit run streamlit_ui.py
Requires:  streamlit>=1.33, plotly, pandas
"""
import base64
import copy
import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from nodes.arch_advice import get_room_carbon_data

from langgraph_agent import LangGraphAgent

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PlanWise",
    page_icon="🏗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── logo ─────────────────────────────────────────────────────────────────────
_LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 364 84">
  <rect x="2" y="2" width="76" height="80" fill="none" stroke="#1e2840" stroke-width="4.5" rx="1"/>
  <line x1="2" y1="52" x2="52" y2="52" stroke="#1e2840" stroke-width="4"/>
  <line x1="52" y1="2" x2="52" y2="82" stroke="#1e2840" stroke-width="4"/>
  <line x1="52" y1="67" x2="78" y2="67" stroke="#1e2840" stroke-width="3.5"/>
  <polyline points="54,2 78,2 78,26" fill="none" stroke="#00AAAC" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="27" cy="67" r="5.5" fill="#00AAAC"/>
  <text x="96" y="66" font-family="Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif" font-size="58" font-weight="700" letter-spacing="-1.5"><tspan fill="#1e2840">Plan</tspan><tspan fill="#00AAAC">Wise</tspan></text>
</svg>"""
_LOGO_B64 = base64.b64encode(_LOGO_SVG.encode()).decode()

_LOGO_SVG_LIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 364 84">
  <rect x="2" y="2" width="76" height="80" fill="none" stroke="#ffffff" stroke-width="4.5" rx="1"/>
  <line x1="2" y1="52" x2="52" y2="52" stroke="#ffffff" stroke-width="4"/>
  <line x1="52" y1="2" x2="52" y2="82" stroke="#ffffff" stroke-width="4"/>
  <line x1="52" y1="67" x2="78" y2="67" stroke="#ffffff" stroke-width="3.5"/>
  <polyline points="54,2 78,2 78,26" fill="none" stroke="#00AAAC" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="27" cy="67" r="5.5" fill="#00AAAC"/>
  <text x="96" y="66" font-family="Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif" font-size="58" font-weight="700" letter-spacing="-1.5"><tspan fill="#ffffff">Plan</tspan><tspan fill="#00AAAC">Wise</tspan></text>
</svg>"""
_LOGO_B64_LIGHT = base64.b64encode(_LOGO_SVG_LIGHT.encode()).decode()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Design System v3 — PlanWise ─────────────────────────────────────────── */
/* This placeholder block intentionally left blank — real CSS is below */
.stApp-placeholder { display: none; }
</style>
""", unsafe_allow_html=True)

# ── Design System v3 — PlanWise ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=block');

/* ── TOKENS ──────────────────────────────────────────────────────────────── */
:root {
  --bg:        #1e2a45;
  --bg-text:   #c8ccdc;
  --card:      #ffffff;
  --card-alt:  #faf9f6;
  --sb-bg:     #1a2035;
  --sb-surf:   #212840;
  --sb-border: #2d3655;
  --sb-text:   #c8ccdc;
  --sb-muted:  #5c6278;
  --sb-lbl:    #3e4562;
  --text:      #171717;
  --text-2:    #404040;
  --muted:     #8a8784;
  --teal:      #00AAAC;
  --teal-dk:   #007b80;
  --teal-lt:   #dff6f6;
  --navy:      #1a2035;
  --green:     #10b981;
  --amber:     #f59e0b;
  --red:       #ef4444;
  --border:    #e0dbd2;
  --border-lt: #eceae2;
  --r-xs:3px; --r-sm:6px; --r:10px; --r-lg:14px;
  --s-xs: 0 1px 2px rgba(0,0,0,0.05);
  --s-sm: 0 1px 3px rgba(0,0,0,0.06),0 2px 8px rgba(0,0,0,0.04);
  --s:    0 2px 8px rgba(0,0,0,0.06),0 8px 24px rgba(0,0,0,0.05);
  --s-lg: 0 4px 16px rgba(0,0,0,0.09),0 16px 40px rgba(0,0,0,0.06);
  --font: 'Inter',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}

/* ── BASE ────────────────────────────────────────────────────────────────── */
.stApp { background: var(--bg) !important; font-family: var(--font); }
.stApp p,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6,
.stApp label,.stApp button,.stApp input,.stApp textarea,.stApp select,
.stApp td,.stApp th,.stApp li { font-family: var(--font); color: var(--bg-text); }

/* Restore dark text inside white card columns */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] p,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] h1,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] h2,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] h3,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] h4,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] h5,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] label,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] td,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] th,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] li { color: var(--text) !important; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] .stCaption,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] small { color: var(--muted) !important; }
[data-testid="stExpander"] p,[data-testid="stExpander"] h1,[data-testid="stExpander"] h2,
[data-testid="stExpander"] h3,[data-testid="stExpander"] h4,[data-testid="stExpander"] label,
[data-testid="stExpander"] td,[data-testid="stExpander"] th,
[data-testid="stExpander"] li { color: var(--text) !important; }

.block-container { padding-top:2rem !important; padding-bottom:3rem !important; max-width:none !important; }

/* Icon font — keeps expander arrows as glyphs */
.material-symbols-rounded {
  font-family:'Material Symbols Rounded' !important;
  font-weight:normal !important; font-style:normal !important;
  font-size:1.2rem !important; line-height:1 !important;
  letter-spacing:normal !important; text-transform:none !important;
  display:inline-block !important; white-space:nowrap !important;
  direction:ltr !important; -webkit-font-smoothing:antialiased !important;
  font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24 !important;
}

/* ── SIDEBAR — dark navy ─────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background: var(--sb-bg) !important;
  border-right: 1px solid var(--sb-border) !important;
}
section[data-testid="stSidebar"] > div { padding: 1.5rem 1.25rem !important; }
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] h1,section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] td,section[data-testid="stSidebar"] th,
section[data-testid="stSidebar"] li { color: var(--sb-text) !important; }
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] small { color: var(--sb-muted) !important; }
section[data-testid="stSidebar"] .section-lbl { color: var(--sb-muted) !important; }
section[data-testid="stSidebar"] .section-lbl::after { background: var(--sb-lbl) !important; }
section[data-testid="stSidebar"] .proj-title { color:#fff !important; font-weight:600 !important; }
section[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background:var(--sb-surf) !important; border-color:var(--sb-border) !important;
  color:var(--sb-text) !important;
}
section[data-testid="stSidebar"] [data-baseweb="select"] svg { fill:var(--sb-muted) !important; }
section[data-testid="stSidebar"] [data-baseweb="popover"] ul,
section[data-testid="stSidebar"] [data-baseweb="popover"] li {
  background:var(--sb-surf) !important; color:var(--sb-text) !important;
  border-color:var(--sb-border) !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
  background:var(--sb-surf) !important; border-color:var(--sb-border) !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] p,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] label {
  color:var(--sb-text) !important;
}
section[data-testid="stSidebar"] [data-testid="stMetric"] {
  background:var(--sb-surf) !important; border-color:var(--sb-border) !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] { color:var(--sb-muted) !important; }
section[data-testid="stSidebar"] [data-testid="stMetricValue"] { color:var(--teal) !important; }
section[data-testid="stSidebar"] [data-testid="stAlertContainer"] {
  background:var(--sb-surf) !important; border-color:var(--sb-border) !important;
}
section[data-testid="stSidebar"] [data-testid="stAlertContainer"] p { color:var(--sb-text) !important; }
section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
  background:var(--teal) !important; border-color:var(--teal) !important; color:#fff !important;
}
section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] * { color:#fff !important; }
section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
  background:var(--sb-surf) !important; border-color:var(--sb-border) !important;
  color:var(--sb-text) !important;
}
section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
  background:var(--sb-border) !important; color:#fff !important;
}

/* ── TYPOGRAPHY ──────────────────────────────────────────────────────────── */
h1,h2,h3,h4,h5 { font-family:var(--font) !important; letter-spacing:-0.025em !important; color:var(--bg-text) !important; }
h4 { font-size:1rem !important; font-weight:600 !important; margin-top:0.5rem !important; }
hr { border-color:var(--border-lt) !important; margin:1rem 0 !important; }
.stCaption,small { color:var(--muted) !important; font-size:0.78rem !important; }

/* ── METRICS ─────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background:var(--card) !important; border:1px solid var(--border) !important;
  border-radius:var(--r-sm) !important; padding:0.85rem 1rem !important;
  box-shadow:var(--s-xs) !important;
}
[data-testid="stMetricLabel"] {
  font-size:0.63rem !important; font-weight:700 !important;
  text-transform:uppercase !important; letter-spacing:0.09em !important; color:var(--muted) !important;
}
[data-testid="stMetricValue"] {
  font-size:1.4rem !important; font-weight:700 !important;
  letter-spacing:-0.03em !important; color:var(--text) !important;
}

/* ── BUTTONS ─────────────────────────────────────────────────────────────── */
[data-testid="stBaseButton-primary"] {
  background:var(--teal) !important; color:#fff !important;
  border:1px solid var(--teal) !important; border-radius:var(--r-sm) !important;
  font-size:0.875rem !important; font-weight:500 !important;
  box-shadow:0 1px 3px rgba(0,170,172,0.25) !important;
  transition:background 0.15s,box-shadow 0.15s !important;
}
[data-testid="stBaseButton-primary"] * { color:#fff !important; }
[data-testid="stBaseButton-primary"]:hover {
  background:var(--teal-dk) !important;
  box-shadow:0 2px 8px rgba(0,170,172,0.35) !important;
}
[data-testid="stBaseButton-secondary"] {
  background:var(--card) !important; color:var(--text-2) !important;
  border:1px solid var(--border) !important; border-radius:var(--r-sm) !important;
  font-size:0.875rem !important; font-weight:400 !important; box-shadow:none !important;
}
[data-testid="stBaseButton-secondary"]:hover {
  background:var(--bg) !important; border-color:#b0aba2 !important; color:var(--text) !important;
}

/* ── INPUTS ──────────────────────────────────────────────────────────────── */
[data-testid="stFileUploaderDropzone"] {
  background:var(--card) !important; border:1.5px dashed var(--border) !important;
  border-radius:var(--r-sm) !important;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color:var(--teal) !important; }
[data-baseweb="select"] > div {
  background:var(--card) !important; border-color:var(--border) !important;
  border-radius:var(--r-sm) !important; color:var(--text) !important;
}
[data-baseweb="select"] [data-testid="stSelectboxVirtualDropdown"],
[data-baseweb="popover"] ul,[data-baseweb="popover"] li {
  background:var(--card) !important; color:var(--text) !important; border-color:var(--border) !important;
}
[data-baseweb="select"] svg { fill:var(--muted) !important; }

/* ── EXPANDERS ───────────────────────────────────────────────────────────── */
[data-testid="stExpander"] details {
  background:var(--card) !important; border:1px solid var(--border) !important;
  border-radius:var(--r) !important; box-shadow:var(--s-xs) !important;
}
[data-testid="stExpander"] summary {
  font-size:0.875rem !important; font-weight:500 !important;
  letter-spacing:-0.01em !important; color:var(--text-2) !important;
}

/* ── CHAT ────────────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
  background:var(--card) !important; border:1.5px solid var(--border) !important;
  border-radius:var(--r-sm) !important; box-shadow:var(--s-xs) !important;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] section { background:var(--card) !important; }
[data-testid="stChatInput"] button { background:transparent !important; border:none !important; }
[data-testid="stChatInput"] textarea,[data-baseweb="textarea"] textarea {
  background:var(--card) !important; color:var(--text) !important;
  font-size:0.875rem !important; border:none !important;
}
[data-testid="stChatMessageContent"] {
  background:var(--card-alt) !important; border:1px solid var(--border-lt) !important;
  border-radius:var(--r) !important; font-size:0.875rem !important;
  line-height:1.65 !important; color:var(--text) !important;
}

/* ── TABLES ──────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] *,[data-testid="stTable"] * {
  background:var(--card) !important; color:var(--text) !important;
  border-color:var(--border-lt) !important;
}
[data-testid="stTable"] { border-radius:var(--r) !important; overflow:hidden !important; }
[data-testid="stTable"] th {
  background:var(--card-alt) !important; font-size:0.7rem !important;
  font-weight:700 !important; text-transform:uppercase !important;
  letter-spacing:0.07em !important; color:var(--muted) !important;
}

/* ── ALERTS ──────────────────────────────────────────────────────────────── */
[data-testid="stAlertContainer"] { border-radius:var(--r-sm) !important; }

/* ── THREE-PANEL CARDS ───────────────────────────────────────────────────── */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  background:var(--card) !important; border-radius:var(--r-lg) !important;
  border:1px solid var(--border) !important; box-shadow:var(--s) !important;
  padding:1.5rem 1.5rem 1.75rem !important;
}
[data-testid="stColumn"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  background:transparent !important; border:none !important;
  box-shadow:none !important; border-radius:0 !important; padding:0 0.5rem !important;
}
[data-testid="stColumn"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:last-child) {
  border-right:1px solid var(--border-lt) !important; padding-right:1rem !important;
}
[data-testid="stColumn"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:first-child) {
  padding-left:1rem !important;
}

/* ── COMPONENT CLASSES ───────────────────────────────────────────────────── */
.section-lbl {
  font-size:0.6rem; font-weight:700; color:var(--muted);
  letter-spacing:0.14em; text-transform:uppercase;
  margin:0.75rem 0 0.65rem; display:flex; align-items:center; gap:0.5rem;
}
.section-lbl::after { content:''; flex:1; height:1px; background:var(--border-lt); }

.sb-card {
  background:var(--sb-surf); border:1px solid var(--sb-border);
  border-radius:var(--r-sm); padding:0.85rem 1rem; margin-bottom:0.5rem;
}

.proj-title {
  font-size:0.88rem; font-weight:600; color:var(--text);
  letter-spacing:-0.01em; margin:0 0 0.6rem; line-height:1.3;
}

.kv-row {
  display:flex; justify-content:space-between; align-items:center;
  padding:0.28rem 0; border-bottom:1px solid var(--border-lt);
  font-size:0.84rem; gap:0.5rem;
}
.kv-row:last-child { border-bottom:none; }
.kv-key { color:var(--muted); }
.kv-val { color:var(--text); font-weight:600; text-align:right; }

.room-card {
  background:var(--card); border:1px solid var(--border);
  border-radius:var(--r-sm); padding:0.85rem 1rem; margin-top:0.4rem;
  box-shadow:var(--s-xs);
}
.room-card h4 { margin:0 0 0.45rem; font-size:0.95rem; font-weight:600; }

@media (max-width:1200px) {
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { border-radius:var(--r) !important; }
}

/* ── CHART LEGEND OVERLAY ────────────────────────────────────────────────── */
.chart-legend-overlay {
  position:relative; float:right; z-index:100;
  margin-top:-770px; margin-right:14px;
  width:172px;
  background:rgba(255,255,255,0.93);
  border:1px solid #e0dbd2; border-radius:8px;
  padding:10px 12px;
  box-shadow:0 2px 10px rgba(0,0,0,0.10);
  pointer-events:none;
}
/* let the column and vertical blocks show the overlay */
[data-testid="stVerticalBlock"],[data-testid="stColumn"] { overflow:visible !important; }
</style>
""", unsafe_allow_html=True)

# ── session state ─────────────────────────────────────────────────────────────
for _k, _v in {
    "layout": None,
    "layouts": {},
    "selected_plan_key": None,
    "_uploaded_ids": [],
    "show_plan_comparison": False,
    "messages": [],
    "selected_room": None,
    "selected_element": None,
    "pending_prompt": "",
    "arch_advice_text": None,
    "arch_advice_rows": [],
    "_advice_mat_sig": "",
    "agent": LangGraphAgent(),
    "client_profile": {},
    "client_summary": "",
    "client_template": {},
    "client_applied": False,
    "active_tab": "Architectural Advice",
    "currency_code": "AED",
    "currency_factor": 1.0,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── helpers ───────────────────────────────────────────────────────────────────
def is_point_in_polygon(x, y, poly):
    """Ray casting algorithm to check if point is inside a polygon."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def render_3d_heatmap(layout_data, extrusion_mode="skyline"):
    """
    Embeds a Three.js interactive 3D heatmap into Streamlit.
    """
    layout_json_str = json.dumps(layout_data)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
        <style>
            body {{ margin: 0; overflow: hidden; font-family: sans-serif; }}
            #canvas-container {{ width: 100vw; height: 100vh; }}
            .hologram-label {{
                position: absolute;
                background: rgba(10, 10, 10, 0.85);
                color: #00ffcc;
                padding: 6px 12px;
                border: 1px solid #00ffcc;
                border-radius: 4px;
                font-size: 12px;
                pointer-events: none;
                transform: translate(-50%, -50%);
                text-align: center;
                box-shadow: 0 0 10px rgba(0, 255, 204, 0.3);
            }}
            .hologram-label span {{ color: #ffffff; font-weight: bold; font-size: 14px; display: block; }}
        </style>
    </head>
    <body>
        <div id="canvas-container"></div>
        <div id="labels-container"></div>

        <script>
            const layoutData = {layout_json_str};
            const mode = "{extrusion_mode}";
            const rooms = layoutData.costs ? layoutData.costs.rooms.rooms : layoutData.rooms;

            const scene = new THREE.Scene();
            scene.background = new THREE.Color('#1e1e1e');
            const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
            const renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            document.getElementById('canvas-container').appendChild(renderer.domElement);

            const controls = new THREE.OrbitControls(camera, renderer.domElement);

            scene.add(new THREE.AmbientLight(0xffffff, 0.6));
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
            dirLight.position.set(10, 20, 10);
            scene.add(dirLight);

            const labelsContainer = document.getElementById('labels-container');
            const labelObjects = [];
            const group = new THREE.Group();
            scene.add(group);

            // --- 1. CALCULATE MIN & MAX COST FOR DYNAMIC COLOR MAPPING ---
            let minCost = Infinity;
            let maxCost = -Infinity;
            Object.values(rooms).forEach(room => {{
                const cost = room.total_cost || 0;
                if (cost > 0 && cost < minCost) minCost = cost;
                if (cost > maxCost) maxCost = cost;
            }});
            if (minCost === Infinity) minCost = 0;
            if (maxCost === -Infinity) maxCost = 1;

            // --- 2. DYNAMIC COLOR RAMP FUNCTION ---
            function getHeatColor(cost) {{
                let t = (maxCost > minCost) ? (cost - minCost) / (maxCost - minCost) : 0;
                t = Math.max(0, Math.min(1, t)); // clamp between 0 and 1

                // Our architectural cost gradient (Cream to Red)
                const stops = [
                    {{ t: 0.00, c: new THREE.Color("#FFF5DC") }}, // Cream (Cheapest)
                    {{ t: 0.25, c: new THREE.Color("#FED976") }}, // Light Yellow
                    {{ t: 0.50, c: new THREE.Color("#FEB24C") }}, // Orange
                    {{ t: 0.75, c: new THREE.Color("#F06913") }}, // Dark Orange
                    {{ t: 1.00, c: new THREE.Color("#BD0026") }}  // Red (Most Expensive)
                ];

                // Smoothly blend (interpolate) colors based on cost
                for (let i = 0; i < stops.length - 1; i++) {{
                    if (t >= stops[i].t && t <= stops[i+1].t) {{
                        const localT = (t - stops[i].t) / (stops[i+1].t - stops[i].t);
                        return stops[i].c.clone().lerp(stops[i+1].c, localT);
                    }}
                }}
                return stops[stops.length-1].c;
            }}

            Object.values(rooms).forEach(room => {{
                if (!room.polygon || room.polygon.length < 3) return;

                const shape = new THREE.Shape();
                shape.moveTo(room.polygon[0][0], room.polygon[0][1]);
                for (let i = 1; i < room.polygon.length; i++) {{
                    shape.lineTo(room.polygon[i][0], room.polygon[i][1]);
                }}

                let height = 3;
                if (mode === "skyline" && room.total_cost) {{
                    height = Math.max(1, room.total_cost / 10000);
                }}

                const extrudeSettings = {{ depth: height, bevelEnabled: false }};
                const geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);

                // --- 3. APPLY THE DYNAMIC COLOR ---
                let finalColor;
                if (layoutData.heatmap && layoutData.heatmap.rooms && layoutData.heatmap.rooms[room.id] && layoutData.heatmap.rooms[room.id].color_hex) {{
                    finalColor = new THREE.Color(layoutData.heatmap.rooms[room.id].color_hex);
                }} else if (room.color_hex) {{
                    finalColor = new THREE.Color(room.color_hex);
                }} else {{
                    finalColor = getHeatColor(room.total_cost || 0);
                }}

                const material = new THREE.MeshLambertMaterial({{
                    color: finalColor,
                    transparent: true,
                    opacity: 0.9
                }});

                const mesh = new THREE.Mesh(geometry, material);
                mesh.rotation.x = -Math.PI / 2;
                group.add(mesh);

                geometry.computeBoundingBox();
                const center = new THREE.Vector3();
                geometry.boundingBox.getCenter(center);

                const labelPos = new THREE.Vector3(center.x, height + 0.5, -center.y);

                const labelDiv = document.createElement('div');
                labelDiv.className = 'hologram-label';
                labelDiv.innerHTML = `${{room.name}} <br> <span>$${{room.total_cost.toLocaleString()}}</span>`;
                labelsContainer.appendChild(labelDiv);

                labelObjects.push({{ div: labelDiv, pos: labelPos }});
            }});

            new THREE.Box3().setFromObject(group).getCenter(controls.target);
            camera.position.set(controls.target.x + 15, 20, controls.target.z + 15);
            controls.update();

            function animate() {{
                requestAnimationFrame(animate);

                labelObjects.forEach(obj => {{
                    const vector = obj.pos.clone();
                    vector.project(camera);

                    const x = (vector.x * .5 + .5) * window.innerWidth;
                    const y = (vector.y * -.5 + .5) * window.innerHeight;

                    obj.div.style.left = `${{x}}px`;
                    obj.div.style.top = `${{y}}px`;
                }});

                renderer.render(scene, camera);
            }}
            animate();

            window.addEventListener('resize', () => {{
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            }});
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=600)

def _merge_gh_colors(base: dict, gh: dict) -> dict:
    """
    Overlay updated color_hex / heat_t / total_cost / rate_per_m2 from gh onto
    the base layout. Matches by id first, then by lowercase name as fallback.
    """
    result = copy.deepcopy(base)
    gh_rooms = gh.get("rooms", [])
    gh_by_id   = {r.get("id"): r for r in gh_rooms}
    gh_by_name = {(r.get("name") or "").lower(): r for r in gh_rooms}
    for room in result.get("rooms", []):
        src = (gh_by_id.get(room.get("id"))
               or gh_by_name.get((room.get("name") or "").lower()))
        if src:
            for key in (
                "color_hex", "color_rgb", "heat_t", "total_cost", "rate_per_m2",
                "floor_finish", "floor-finish",
                "wall_finish", "wall-finish",
                "ceiling_material", "ceiling-material", "ceiling-finish",
                "slab_material", "slab-material",
            ):
                if key in src:
                    room[key] = src[key]
    if "heatmap" in gh:
        result["heatmap"] = gh["heatmap"]
    if "totals" in gh:
        result["totals"] = gh["totals"]
    return result


def _write_gh_file(layout: dict) -> None:
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "team_05_edited_layout.json")
    )
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.warning(f"Could not write to GH file: {e}")


def _unique_plan_key(existing: dict, base_name: str) -> str:
    if base_name not in existing:
        return base_name
    stem, dot, ext = base_name.rpartition(".")
    name_root = stem if dot else base_name
    suffix = f".{ext}" if dot else ""
    idx = 2
    while True:
        candidate = f"{name_root} ({idx}){suffix}"
        if candidate not in existing:
            return candidate
        idx += 1


def _plan_summary_row(plan_name: str, layout: dict) -> dict:
    proj = layout.get("project", {})
    rooms = layout.get("rooms", [])
    currency = proj.get("currency", "")
    totals = layout.get("totals", {})
    room_total = totals.get("rooms", sum((r.get("total_cost", 0) or 0) for r in rooms))
    grand = totals.get("grand", room_total)
    return {
        "Plan": plan_name,
        "Project": proj.get("name", ""),
        "Rooms": len(rooms),
        "Footprint (m²)": round(float(proj.get("footprint_m2", 0) or 0), 1),
        f"Room Cost ({currency})": int(room_total),
        f"Grand Total ({currency})": int(grand),
    }


def _plan_comparison_row(plan_name: str, layout: dict) -> dict:
    proj = layout.get("project", {})
    rooms = layout.get("rooms", [])
    totals = layout.get("totals", {})
    currency = proj.get("currency", "")
    room_total = totals.get("rooms", sum((r.get("total_cost", 0) or 0) for r in rooms))
    grand = totals.get("grand", room_total)
    return {
        "Plan": plan_name,
        "Currency": currency,
        "Grand Total": float(grand),
        "Room Total": float(room_total),
        "Rooms": len(rooms),
        "Footprint (m²)": round(float(proj.get("footprint_m2", 0) or 0), 1),
    }


def _plan_category_costs(plan_name: str, layout: dict) -> dict:
    proj = layout.get("project", {})
    rooms = layout.get("rooms", [])
    openings = layout.get("openings", [])
    columns = layout.get("columns", [])
    currency = proj.get("currency", "")
    totals = layout.get("totals", {})

    room_total = totals.get("rooms", sum((r.get("total_cost", 0) or 0) for r in rooms))
    door_total = sum((o.get("cost", 0) or 0) for o in openings if (o.get("type") or "").lower() == "door")
    window_total = sum((o.get("cost", 0) or 0) for o in openings if (o.get("type") or "").lower() == "window")
    column_total = sum((c.get("cost", 0) or 0) for c in columns)

    return {
        "Plan": plan_name,
        "Currency": currency,
        "Rooms": float(room_total),
        "Doors": float(door_total),
        "Windows": float(window_total),
        "Columns": float(column_total),
    }


# ── colour helpers ────────────────────────────────────────────────────────────
_RAMP = [(255, 255, 224), (255, 200, 0), (255, 120, 0), (189, 0, 38)]

def _lerp_color(t: float) -> str:
    t = max(0.0, min(1.0, t))
    seg = t * (len(_RAMP) - 1)
    lo, hi = int(seg), min(int(seg) + 1, len(_RAMP) - 1)
    f = seg - lo
    r = int(_RAMP[lo][0] + f * (_RAMP[hi][0] - _RAMP[lo][0]))
    g = int(_RAMP[lo][1] + f * (_RAMP[hi][1] - _RAMP[lo][1]))
    b = int(_RAMP[lo][2] + f * (_RAMP[hi][2] - _RAMP[lo][2]))
    return f"rgb({r},{g},{b})"

def _text_on(t: float) -> str:
    return "#111"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return (128, 128, 128)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"


def _interp_hex(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return _rgb_to_hex((r, g, b))


def _cost_color_for_category(layout: dict, category: str, value: float, default_hex: str) -> str:
    heatmap = layout.get("heatmap", {})
    ramps = heatmap.get("ramps", {})
    ranges = heatmap.get("ranges", {})

    fallback_stops: dict[str, list[tuple[str, float]]] = {
        "rooms": [
            ("#FFF5DC", 0.0),
            ("#FED976", 0.25),
            ("#FEB24C", 0.5),
            ("#F06913", 0.75),
            ("#BD0026", 1.0),
        ],
        "doors": [("#E8CDAA", 0.0), ("#B27A41", 0.5), ("#643719", 1.0)],
        "windows": [("#D2E8F0", 0.0), ("#5AA0CD", 0.5), ("#194B91", 1.0)],
        "columns": [("#C8C8C8", 0.0), ("#828282", 0.5), ("#404040", 1.0)],
    }

    category_range = ranges.get(category, {}) if isinstance(ranges, dict) else {}
    lo = float(category_range.get("min", 0.0))
    hi = float(category_range.get("max", 0.0))
    if hi <= lo:
        t = 0.0
    else:
        t = (float(value) - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))

    raw_stops = ramps.get(category, []) if isinstance(ramps, dict) else []
    stops: list[tuple[str, float]] = []
    if isinstance(raw_stops, list):
        for stop in raw_stops:
            if isinstance(stop, dict):
                hex_color = stop.get("hex")
                stop_t = stop.get("t")
                if isinstance(hex_color, str) and isinstance(stop_t, (int, float)):
                    stops.append((hex_color, float(stop_t)))

    if not stops:
        stops = fallback_stops.get(category, [(default_hex, 0.0), (default_hex, 1.0)])

    stops.sort(key=lambda x: x[1])

    if t <= stops[0][1]:
        return stops[0][0]
    if t >= stops[-1][1]:
        return stops[-1][0]

    for idx in range(len(stops) - 1):
        c1, t1 = stops[idx]
        c2, t2 = stops[idx + 1]
        if t1 <= t <= t2:
            local_t = 0.0 if t2 == t1 else (t - t1) / (t2 - t1)
            return _interp_hex(c1, c2, local_t)

    return default_hex


# ── floor plan ────────────────────────────────────────────────────────────────
def build_floor_plan(
    layout: dict,
    selected_id: str | None = None,
    plot_height: int | None = None,
) -> go.Figure:
    rooms    = layout.get("rooms", [])
    openings = layout.get("openings", [])
    columns  = layout.get("columns", [])
    currency = layout.get("project", {}).get("currency", "")

    costs = [r.get("total_cost", 0) for r in rooms]
    mn, mx = (min(costs), max(costs)) if costs else (0, 1)
    span = (mx - mn) or 1

    fig = go.Figure()

    for room in rooms:
        poly = room.get("polygon", [])
        if not poly:
            continue
        xs = [p[0] for p in poly] + [poly[0][0]]
        ys = [p[1] for p in poly] + [poly[0][1]]
        t    = room.get("heat_t", (room.get("total_cost", mn) - mn) / span)
        fill = room.get("color_hex") or _lerp_color(t)
        is_sel = room.get("id") == selected_id
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)

        fig.add_trace(go.Scatter(
            x=xs, y=ys, fill="toself", fillcolor=fill,
            line=dict(color="#00AAAC" if is_sel else "#555", width=3 if is_sel else 1),
            mode="lines", name=room.get("name", ""),
            hoveron="fills+points",
            customdata=[[
                room.get("id", ""), "room", room.get("name", ""),
                room.get("total_cost", 0), room.get("area_m2", 0),
                room.get("rate_per_m2", 0), room.get("category", ""),
            ]],
            hovertemplate=(
                f"<b>{room.get('name', '')}</b><br>"
                f"Area: {room.get('area_m2', 0):.1f} m²<br>"
                f"Rate: {room.get('rate_per_m2', 0):,.0f} {currency}/m²<br>"
                f"<b>Cost: {room.get('total_cost', 0):,.0f} {currency}</b>"
                "<extra></extra>"
            ),
        ))
        fig.add_annotation(
            x=cx, y=cy,
            text=f"<b>{room.get('name','')}</b><br>{room.get('total_cost',0)/1000:.0f}k {currency}",
            showarrow=False, font=dict(size=9, color=_text_on(t)), align="center",
        )

    for op in (openings + columns):
        poly = op.get("polygon", [])
        if not poly:
            continue
        ox = [p[0] for p in poly] + [poly[0][0]]
        oy = [p[1] for p in poly] + [poly[0][1]]
        op_type = (op.get("type") or op.get("category") or "").lower()
        fill   = op.get("color_hex") or ("rgba(92,45,0,0.85)" if "door" in op_type else
                                          "rgba(30,144,255,0.55)" if "window" in op_type else
                                          "rgba(130,130,130,0.7)")
        border = op.get("color_hex") or ("#3d1a00" if "door" in op_type else
                                          "#0050b3" if "window" in op_type else "#444")
        _op_subtype = op.get("subtype") or op_type.capitalize()
        _op_cost    = op.get("cost", 0) or 0
        fig.add_trace(go.Scatter(
            x=ox, y=oy, fill="toself", fillcolor=fill,
            line=dict(color=border, width=1), mode="lines",
            name=op_type.capitalize(), showlegend=False,
            hoveron="fills+points",
            customdata=[[
                op.get("id", ""), op_type, _op_subtype,
                _op_cost, 0, 0, "",
            ]],
            hovertemplate=(
                f"<b>{op_type.capitalize()}</b> ({_op_subtype})<br>"
                f"Cost: {_op_cost:,.0f} {currency}<extra></extra>"
            ),
        ))

    # Compute tight coordinate bounds to eliminate dead whitespace
    _all_pts = (
        [p for r in rooms for p in r.get("polygon", [])] +
        [p for o in (openings + columns) for p in o.get("polygon", [])]
    )
    if _all_pts:
        _xs = [p[0] for p in _all_pts]
        _ys = [p[1] for p in _all_pts]
        _xpad = (max(_xs) - min(_xs)) * 0.03
        _ypad = (max(_ys) - min(_ys)) * 0.03
        _xrange = [min(_xs) - _xpad, max(_xs) + _xpad]
        _yrange = [min(_ys) - _ypad, max(_ys) + _ypad]
    else:
        _xrange = None
        _yrange = None

    fig.update_layout(
        showlegend=False,
        margin=dict(l=4, r=4, t=4, b=4),
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        xaxis=dict(showgrid=False, zeroline=False, scaleanchor="y",
                   scaleratio=1, showticklabels=False, range=_xrange),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=_yrange),
        clickmode="event+select", dragmode="select",
    )
    if plot_height is not None:
        fig.update_layout(height=plot_height)
    return fig


# ── GH legend ────────────────────────────────────────────────────────────────
def build_gh_legend(layout: dict) -> str:
    heatmap  = layout.get("heatmap", {})
    ranges   = heatmap.get("ranges", {})
    ramps    = heatmap.get("ramps", {})
    currency = layout.get("project", {}).get("currency", "")
    _fallback = {
        "rooms":   [("#FFF5DC",0),("#FED976",.25),("#FEB24C",.5),("#F06913",.75),("#BD0026",1)],
        "doors":   [("#E8CDAA",0),("#B27A41",.5),("#643719",1)],
        "windows": [("#D2E8F0",0),("#5AA0CD",.5),("#194B91",1)],
        "columns": [("#C8C8C8",0),("#828282",.5),("#404040",1)],
    }
    blocks = []
    for cat in ("rooms", "doors", "windows", "columns"):
        r = ranges.get(cat, {})
        lo, hi = r.get("min", 0), r.get("max", 0)
        stops = ramps.get(cat, [])
        if stops:
            grad = "linear-gradient(to right," + ",".join(f"{s['hex']} {int(s['t']*100)}%" for s in stops) + ")"
        else:
            grad = "linear-gradient(to right," + ",".join(f"{h} {int(t*100)}%" for h,t in _fallback[cat]) + ")"
        blocks.append(f"""
<div style="margin-bottom:10px">
  <div style="font-size:0.72rem;color:#8a8784;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px">
    {cat.capitalize()}<span style="font-weight:400;letter-spacing:0"> &nbsp;{lo:,.0f}–{hi:,.0f} {currency}</span>
  </div>
  <div style="height:10px;border-radius:4px;background:{grad};border:1px solid #e0dbd2"></div>
  <div style="display:flex;justify-content:space-between;font-size:0.68rem;color:#8a8784;margin-top:2px">
    <span>{lo:,.0f}</span><span>{hi:,.0f}</span>
  </div>
</div>""")
    return "\n".join(blocks)


# ── in-chart legend overlay ───────────────────────────────────────────────────
def _add_legend_to_figure(fig: go.Figure, layout: dict) -> None:
    """Overlay gradient color-scale bars inside the Plotly chart (top-right)."""
    heatmap  = layout.get("heatmap", {})
    ranges   = heatmap.get("ranges", {})
    ramps    = heatmap.get("ramps", {})
    currency = layout.get("project", {}).get("currency", "")

    _fallback: dict[str, list[tuple[str, float]]] = {
        "rooms":   [("#FFF5DC", 0.00), ("#FED976", 0.25), ("#FEB24C", 0.50), ("#F06913", 0.75), ("#BD0026", 1.00)],
        "doors":   [("#E8CDAA", 0.00), ("#B27A41", 0.50), ("#643719", 1.00)],
        "windows": [("#D2E8F0", 0.00), ("#5AA0CD", 0.50), ("#194B91", 1.00)],
        "columns": [("#C8C8C8", 0.00), ("#828282", 0.50), ("#404040", 1.00)],
    }
    cats   = ["rooms", "doors", "windows", "columns"]
    N_SEGS = 20

    # Legend box in the top-right corner (paper coords: 0=plot-left, 1=plot-right)
    lx0, lx1 = 0.72, 0.997
    ly0, ly1 = 0.57, 0.995
    slot_h   = (ly1 - ly0) / len(cats)   # vertical space per category
    bar_h    = 0.038                      # bar thickness in paper units

    # Semi-transparent white backing
    fig.add_shape(
        type="rect", xref="paper", yref="paper",
        x0=lx0 - 0.012, y0=ly0 - 0.012, x1=lx1 + 0.004, y1=ly1 + 0.006,
        fillcolor="rgba(255,255,255,0.90)",
        line=dict(color="#cccccc", width=0.8), layer="above",
    )

    for i, cat in enumerate(cats):
        r  = ranges.get(cat, {})
        lo = float(r.get("min", 0))
        hi = float(r.get("max", 0))

        raw = ramps.get(cat, [])
        stops: list[tuple[str, float]] = []
        if isinstance(raw, list):
            for s in raw:
                if isinstance(s, dict):
                    h = s.get("hex"); t = s.get("t")
                    if isinstance(h, str) and isinstance(t, (int, float)):
                        stops.append((h, float(t)))
        if not stops:
            stops = list(_fallback[cat])
        stops.sort(key=lambda x: x[1])

        top    = ly1 - i * slot_h
        bar_y1 = top - 0.028
        bar_y0 = bar_y1 - bar_h
        val_y  = bar_y0 - 0.008

        # Category label + range text
        fig.add_annotation(
            x=lx0, y=top - 0.004, xref="paper", yref="paper",
            text=f"<b>{cat.upper()}</b>  {lo:,.0f}–{hi:,.0f} {currency}",
            showarrow=False, xanchor="left", yanchor="top",
            font=dict(size=8, color="#444444"),
        )

        # Gradient bar: N_SEGS thin coloured rectangles
        for j in range(N_SEGS):
            t_mid = (j + 0.5) / N_SEGS
            col = stops[-1][0]
            if t_mid <= stops[0][1]:
                col = stops[0][0]
            else:
                for k in range(len(stops) - 1):
                    h1, t1 = stops[k]; h2, t2 = stops[k + 1]
                    if t1 <= t_mid <= t2:
                        lt = (t_mid - t1) / (t2 - t1) if t2 > t1 else 0.0
                        col = _interp_hex(h1, h2, lt)
                        break
            sx0 = lx0 + (lx1 - lx0) * j / N_SEGS
            sx1 = lx0 + (lx1 - lx0) * (j + 1) / N_SEGS
            fig.add_shape(
                type="rect", xref="paper", yref="paper",
                x0=sx0, y0=bar_y0, x1=sx1, y1=bar_y1,
                fillcolor=col, line=dict(width=0), layer="above",
            )

        # Min / max tick labels
        fig.add_annotation(
            x=lx0, y=val_y, xref="paper", yref="paper",
            text=f"{lo:,.0f}", showarrow=False,
            xanchor="left", yanchor="top", font=dict(size=7, color="#888888"),
        )
        fig.add_annotation(
            x=lx1, y=val_y, xref="paper", yref="paper",
            text=f"{hi:,.0f}", showarrow=False,
            xanchor="right", yanchor="top", font=dict(size=7, color="#888888"),
        )


# ── cost table ────────────────────────────────────────────────────────────────
def build_cost_df(layout: dict) -> pd.DataFrame:
    def safe_float(val, default=0.0):
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    labor_mult = safe_float(st.session_state.get("labor", 1.0))
    inflation = 1 + (safe_float(st.session_state.get("inflation", 0)) / 100)
    tax = safe_float(st.session_state.get("carbon_tax", 0))
    cur_code = st.session_state.get("currency_code") or layout.get("project", {}).get("currency", "AED")
    cur_factor = safe_float(st.session_state.get("currency_factor", 1.0), 1.0)

    rooms_list = layout.get("rooms") or layout.get("costs", {}).get("rooms", {}).get("rooms", [])

    rows = []
    for r in rooms_list:
        base_rate = safe_float(r.get("rate_per_m2") or r.get("rate"))
        base_cost = safe_float(r.get("total_cost") or r.get("cost"))
        area = safe_float(r.get("area_m2") or r.get("area"))
        gwp = safe_float(r.get("gwp"))

        adj_rate = base_rate * labor_mult * inflation * cur_factor
        adj_cost = ((base_cost * labor_mult * inflation) + (gwp * tax)) * cur_factor

        rows.append({
            "Room": r.get("name", "Unknown"),
            "Category": r.get("category", "Space").capitalize(),
            "Area (m²)": round(area, 1),
            f"Rate ({cur_code}/m²)": int(adj_rate),
            f"Cost ({cur_code})": int(adj_cost)
        })

    df = pd.DataFrame(rows)
    return df

  # ── room card ─────────────────────────────────────────────────────────────────
def render_room_card(room: dict, currency: str) -> None:
    def kv(k, v):
        return f'<div class="kv-row"><span class="kv-key">{k}</span><span class="kv-val">{v}</span></div>'
    html = (f'<div class="room-card"><h4>{room.get("name","")}</h4>'
            + kv("Category", room.get("category","").capitalize())
            + kv("Area", f'{room.get("area_m2",0):.1f} m²')
            + kv("Rate", f'{room.get("rate_per_m2",0):,.0f} {currency}/m²')
            + kv("Total cost", f'{room.get("total_cost",0):,.0f} {currency}')
            + "</div>")
    st.markdown(html, unsafe_allow_html=True)


# ── element detail panel ──────────────────────────────────────────────────────
def _render_element_panel() -> None:
    """Inline info panel that appears below the floor plan when an element is clicked."""
    el = st.session_state.get("selected_element") or {}
    if not el:
        return
    etype    = el.get("type", "element")
    name     = el.get("name", "—")
    cost     = float(el.get("cost") or 0)
    currency = el.get("currency", "")

    hdr, close_btn = st.columns([8, 1])
    hdr.markdown(
        f'<div style="background:#dff6f6;border:1.5px solid #00AAAC;border-radius:10px;'
        f'padding:0.7rem 1rem 0.2rem 1rem;margin-bottom:0">'
        f'<span style="font-size:0.78rem;color:#00AAAC;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.05em">{etype.capitalize()}</span>'
        f'<h4 style="margin:0 0 0.6rem 0;color:#1a2035">{name}</h4>',
        unsafe_allow_html=True,
    )
    if close_btn.button("✕", key="close_el_panel"):
        st.session_state.selected_element = None
        st.rerun()

    if etype == "room":
        c1, c2, c3 = st.columns(3)
        c1.metric("Cost", f"{cost:,.0f} {currency}")
        c2.metric("Area", f"{el.get('area', 0):.1f} m²")
        c3.metric("Rate", f"{el.get('rate', 0):,.0f} {currency}/m²")

        from nodes.arch_advice import get_room_optimization_tips
        all_rooms = st.session_state.layout.get("rooms", [])
        current_room = next((r for r in all_rooms if r.get("id") == el.get("id")), {})

        if st.button("✨ Generate Optimization Strategy", use_container_width=True):
            tip = get_room_optimization_tips(current_room, all_rooms)
            st.session_state.pending_prompt = (
                f"I am analyzing the {name}. {tip} "
                "Can you provide 3 specific material or design strategies to optimize this?"
            )
            st.session_state.selected_element = None
            st.rerun()
    else:
        st.metric("Cost", f"{cost:,.0f} {currency}")


# ── chat ──────────────────────────────────────────────────────────────────────
def render_chat() -> None:
    for msg in st.session_state.messages:
        role = "user" if msg["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg["content"])


# ── sustainability tab ────────────────────────────────────────────────────────
def render_sustainability_tab():
    st.markdown("#### Carbon vs. Cost Efficiency Comparison")
    st.caption("Comparing carbon intensity vs. cost per m² across all loaded plans.")

    from nodes.arch_advice import get_room_carbon_data

    if not st.session_state.layouts:
        st.info("Upload layouts in the sidebar to see the comparison.")
        return

    _palette = ["#00AAAC", "#f59e0b", "#1a2035", "#10b981", "#8b5cf6"]

    for idx, (name, layout) in enumerate(st.session_state.layouts.items()):
        st.divider()
        st.subheader(f"Plan: {name}")

        data = get_room_carbon_data(layout)
        df = pd.DataFrame(data)

        if not df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['cost'],
                y=df['gwp'],
                mode='markers+text',
                text=df['name'],
                textposition="top center",
                marker=dict(
                    size=14,
                    color=_palette[idx % len(_palette)],
                    opacity=0.8,
                    line=dict(width=1, color="#fff")
                )
            ))

            fig.update_layout(
                xaxis_title="Construction Cost per m² ($)",
                yaxis_title="Embodied Carbon (kgCO2e/m²)",
                paper_bgcolor="#ffffff",
                plot_bgcolor="#f5f2ed",
                height=400,
                margin=dict(l=20, r=20, t=20, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption(f"No finish material data available for {name}.")


# SIDEBAR
with st.sidebar:
    st.markdown(f"""
<div style="margin-bottom:1.25rem">
  <img src="data:image/svg+xml;base64,{_LOGO_B64_LIGHT}" width="192" alt="PlanWise" style="display:block"/>
</div>
""", unsafe_allow_html=True)

    st.markdown('<p class="section-lbl">Load Layouts</p>', unsafe_allow_html=True)
    uploads = st.file_uploader(
        "Layout JSON files",
        type=["json"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="layout_uploader_main"
    )

    # 1. Global Sensitivity Engine
    st.markdown('<p class="section-lbl">Sensitivity Engine</p>', unsafe_allow_html=True)
    st.slider("Labor Cost Multiplier", 0.8, 1.5, 1.0, 0.05, key="labor")
    st.slider("Material Inflation (%)", 0, 20, 0, 1, key="inflation")
    st.slider("Carbon Tax ($/tCO2e)", 0, 200, 0, 5, key="carbon_tax")

    st.session_state.sensitivity = {
        "labor": st.session_state.labor,
        "inflation": 1 + (st.session_state.inflation / 100),
        "carbon_tax": st.session_state.carbon_tax
    }

    # 2. Currency selector
    st.markdown('<p class="section-lbl">Display Currency</p>', unsafe_allow_html=True)
    st.caption("Rates stored in AED — select to convert.")
    _CURRENCIES = {
        "AED — Arab Emirates Dirham": ("AED",  1.000),
        "USD — US Dollar":            ("USD",  0.272),
        "EUR — Euro":                 ("EUR",  0.251),
        "GBP — British Pound":        ("GBP",  0.213),
        "JPY — Japanese Yen":         ("JPY", 40.500),
    }
    _cur_sel = st.selectbox(
        "Display currency",
        options=list(_CURRENCIES.keys()),
        key="currency_selector",
        label_visibility="collapsed",
    )
    _disp_code, _disp_factor = _CURRENCIES[_cur_sel]
    st.session_state.currency_code = _disp_code
    st.session_state.currency_factor = _disp_factor

    # 3. File Processing
    if uploads:
        uploaded_ids = set(st.session_state._uploaded_ids)
        added_count = 0
        failed_names: list[str] = []
        for uploaded in uploads:
            file_uid = uploaded.name
            if file_uid in uploaded_ids:
                continue
            if len(st.session_state.layouts) >= 5:
                st.warning("Maximum 5 plans can be saved at once.")
                break
            try:
                uploaded.seek(0)
                loaded_layout = json.load(uploaded)
                if "rooms" not in loaded_layout:
                    uploaded_ids.add(file_uid)
                    continue
                plan_key = _unique_plan_key(st.session_state.layouts, uploaded.name)
                st.session_state.layouts[plan_key] = loaded_layout
                uploaded_ids.add(file_uid)
                added_count += 1
            except Exception:
                failed_names.append(uploaded.name)

        st.session_state._uploaded_ids = list(uploaded_ids)
        if added_count:
            if st.session_state.selected_plan_key not in st.session_state.layouts:
                st.session_state.selected_plan_key = next(iter(st.session_state.layouts))
            st.success(f"Added {added_count} plan(s).")
        if failed_names:
            st.error("Failed to parse: " + ", ".join(failed_names[:3]))

    # 3. Plan Selection & Analysis
    st.markdown('<p class="section-lbl">Active Plan</p>', unsafe_allow_html=True)
    if st.session_state.layouts:
        plan_keys = list(st.session_state.layouts.keys())
        current_selection = st.session_state.selected_plan_key
        if current_selection not in st.session_state.layouts:
            current_selection = plan_keys[0]
            st.session_state.selected_plan_key = current_selection

        chosen_key = st.selectbox("Active plan", options=plan_keys, index=plan_keys.index(current_selection), label_visibility="collapsed")

        if chosen_key != st.session_state.selected_plan_key:
            st.session_state.selected_plan_key = chosen_key
            st.session_state.selected_room = None
            st.rerun()

        st.session_state.layout = st.session_state.layouts[st.session_state.selected_plan_key]

        proj = st.session_state.layout.get("project", {})
        rooms = st.session_state.layout.get("rooms", [])
        totals = st.session_state.layout.get("totals", {})
        room_total = totals.get("rooms", sum(r.get("total_cost", 0) for r in rooms))
        grand = totals.get("grand", room_total)
        _sb_code = st.session_state.get("currency_code", "AED")
        _sb_factor = st.session_state.get("currency_factor", 1.0)

        _proj_name = proj.get('name', '')
        if _proj_name:
            st.markdown(f'<p class="proj-title">{_proj_name}</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.metric("Rooms", len(rooms))
        c2.metric("Footprint", f"{proj.get('footprint_m2', 0):.0f} m²")
        st.metric("Room construction", f"{room_total * _sb_factor:,.0f} {_sb_code}")
        if grand != room_total:
            st.metric("Grand total", f"{grand * _sb_factor:,.0f} {_sb_code}")

        st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)

        if st.button("Analyze All Saved Plans", use_container_width=True):
            from swiftlet_mcp import push_layout_to_grasshopper
            with st.spinner("Analyzing plans..."):
                for name, layout in list(st.session_state.layouts.items()):
                    try:
                        result = push_layout_to_grasshopper(layout)
                        if result.get("ok"):
                            st.session_state.layouts[name] = _merge_gh_colors(layout, result["gh_layout"])
                    except: pass
            st.rerun()

        if st.button("Remove Active Plan", use_container_width=True):
            key_to_remove = st.session_state.selected_plan_key
            st.session_state.layouts.pop(key_to_remove)
            if st.session_state.layouts:
                st.session_state.selected_plan_key = next(iter(st.session_state.layouts))
            else:
                st.session_state.selected_plan_key = None
                st.session_state.layout = None
            st.rerun()
    else:
        st.info("Upload JSON files to begin.")

    # ── Client DNA ───────────────────────────────────────────────────────────
    st.markdown('<p class="section-lbl">Client DNA</p>', unsafe_allow_html=True)
    st.caption("Upload past project CSVs to learn spending habits (max 3).")

    _dna_uploads = st.file_uploader(
        "Past project CSVs (max 3)",
        type=["csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="dna_uploader",
    )

    if _dna_uploads:
        if len(_dna_uploads) > 3:
            st.warning("Please upload a maximum of 3 CSV files.")
        else:
            if st.button("Analyse Client Profile", use_container_width=True):
                from client_profile import parse_budget_csv, analyze_profiles, generate_summary, propose_template
                _dna_datasets = []
                for _f in _dna_uploads:
                    _rows = parse_budget_csv(_f)
                    if _rows:
                        _dna_datasets.append(_rows)
                if _dna_datasets:
                    _profile = analyze_profiles(_dna_datasets)
                    st.session_state.client_profile  = _profile
                    st.session_state.client_summary  = generate_summary(_profile)
                    st.session_state.client_applied  = False
                    if st.session_state.layout:
                        st.session_state.client_template = propose_template(_profile, st.session_state.layout)
                    st.success(f"Profile built from {len(_dna_datasets)} project(s). See **Client DNA** tab.")
                else:
                    st.error("Could not parse CSVs. Expected columns: room, area, cost (+ optional: category, rate, floor_finish, wall_finish).")

    if st.session_state.get("client_profile"):
        if st.session_state.layout and st.button(
            "Apply to Current Project", use_container_width=True, key="apply_dna_sidebar"
        ):
            from client_profile import propose_template, apply_template
            _old_total = sum(r.get("total_cost", 0) for r in st.session_state.layout.get("rooms", []))
            _tmpl = propose_template(st.session_state.client_profile, st.session_state.layout)
            st.session_state.client_template = _tmpl
            _updated = apply_template(_tmpl, st.session_state.layout)
            _new_total = sum(r.get("total_cost", 0) for r in _updated.get("rooms", []))
            st.session_state.layout = _updated
            _active_key = st.session_state.selected_plan_key
            if _active_key:
                st.session_state.layouts[_active_key] = _updated
            st.session_state.client_applied = True
            st.toast(
                f"Client DNA applied — total changed from {_old_total:,.0f} to {_new_total:,.0f}",
                icon="✅",
            )
            st.rerun()

# =============================================================================
# MAIN
# =============================================================================
st.markdown(f"""
<div style="margin-bottom:0.3rem">
  <img src="data:image/svg+xml;base64,{_LOGO_B64_LIGHT}" width="420" alt="PlanWise" style="display:block"/>
</div>
<p style="font-size:0.82rem;color:#8a95b5;margin:0 0 1.5rem;letter-spacing:0.01em;font-weight:400">
  AI cost advisor for AEC
</p>
""", unsafe_allow_html=True)

with st.expander("How to use this interface", expanded=False):
    st.markdown("""
**Get started in 3 steps:**
1. **Upload** a `layout.json` file using the sidebar — the floor plan heatmap will appear instantly.
2. **Adjust** Labor, Inflation, and Carbon Tax sliders to model real-world cost sensitivity.
3. **Ask** the Agent Chat anything: *"Set master bedroom floor to marble"*, *"What's the total cost?"*

**Right panel tabs:** Architectural Advice · Sustainability Analysis · Cost Matching · Client DNA
    """)

st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)

# =============================================================================
# TWO-COLUMN LAYOUT: Main (left) | Vertical Tabs (right)
# =============================================================================
col_main, col_panel = st.columns([5, 2], gap="large")

# ── LEFT: Heatmap + Chat (top row) | Cost Table (bottom) ─────────────────────
with col_main:
    st.markdown('<p class="section-lbl">Floor Plan · Cost Analysis</p>', unsafe_allow_html=True)
    if st.session_state.layout:

        # ── TOP ROW: Heatmap (left) and Agent Chat (right) side by side ───────
        col_heatmap_inner, col_chat_inner = st.columns([4, 2], gap="medium")

        # ── HEATMAP PANEL ─────────────────────────────────────────────────────
        with col_heatmap_inner:
            st.markdown('<p class="section-lbl">Cost Heatmap</p>', unsafe_allow_html=True)

            view_mode = st.radio(
                "Visualization Mode",
                ["2D Flat Floorplan", "Interactive 3D Skyline"],
                horizontal=True,
                key="view_mode_main",
            )

            if "3D" in view_mode:
                st.caption("Drag to rotate, scroll to zoom. Z-height represents total room cost.")
                render_3d_heatmap(st.session_state.layout, "skyline")
            else:
                st.caption("Colors from Grasshopper. Click a room to select it.")

                sel_id = (st.session_state.selected_room or {}).get("id")
                fig    = build_floor_plan(st.session_state.layout, sel_id, plot_height=800)

                _sel_el = st.session_state.get("selected_element")
                if _sel_el and _sel_el.get("cx") is not None:
                    _ann_cost = float(_sel_el.get("cost") or 0)
                    _ann_cur  = _sel_el.get("currency", "")
                    _ann_type = _sel_el.get("type", "")
                    _ann_name = _sel_el.get("name", "")
                    if _ann_type == "room":
                        _ann_text = (
                            f"<b>{_ann_name}</b><br>"
                            f"Cost: {_ann_cost:,.0f} {_ann_cur}<br>"
                            f"Area: {_sel_el.get('area', 0):.1f} m²<br>"
                            f"Rate: {_sel_el.get('rate', 0):,.0f} {_ann_cur}/m²"
                        )
                    else:
                        _ann_text = (
                            f"<b>{_ann_type.capitalize()}</b> · {_ann_name}<br>"
                            f"Cost: {_ann_cost:,.0f} {_ann_cur}"
                        )
                    fig.add_annotation(
                        x=_sel_el["cx"], y=_sel_el["cy"],
                        text=_ann_text,
                        showarrow=True,
                        arrowhead=2,
                        arrowcolor="#00AAAC",
                        arrowwidth=1.5,
                        bgcolor="white",
                        bordercolor="#00AAAC",
                        borderwidth=1.5,
                        borderpad=6,
                        font=dict(size=10, color="#1a2035"),
                        align="left",
                        ax=60, ay=-60,
                        xanchor="left",
                    )

                try:
                    event = st.plotly_chart(
                        fig, use_container_width=True,
                        on_select="rerun", key="floor_plan_chart",
                    )
                    if event:
                        pts = (event.get("selection") or {}).get("points", [])
                        if pts:
                            cd = pts[0].get("customdata", [])
                            if cd and len(cd) >= 4:
                                el_id    = cd[0]
                                el_type  = cd[1]
                                el_name  = cd[2]
                                el_cost  = float(cd[3] or 0)
                                currency = (st.session_state.layout or {}).get("project", {}).get("currency", "")

                                def _centroid(poly: list) -> tuple:
                                    if not poly:
                                        return (0, 0)
                                    return (
                                        sum(p[0] for p in poly) / len(poly),
                                        sum(p[1] for p in poly) / len(poly),
                                    )

                                if el_type == "room":
                                    all_rooms = st.session_state.layout.get("rooms", [])
                                    room = next((r for r in all_rooms if r.get("id") == el_id), None)
                                    if room:
                                        cx, cy = _centroid(room.get("polygon", []))
                                        st.session_state.selected_room = room
                                        st.session_state.selected_element = {
                                            "type": "room",
                                            "id": el_id,
                                            "name": room.get("name", el_name),
                                            "cost": room.get("total_cost", el_cost),
                                            "area": room.get("area_m2", 0),
                                            "rate": room.get("rate_per_m2", 0),
                                            "category": room.get("category", ""),
                                            "currency": currency,
                                            "cx": cx, "cy": cy,
                                        }
                                else:
                                    all_ops = (
                                        st.session_state.layout.get("openings", [])
                                        + st.session_state.layout.get("columns", [])
                                    )
                                    el_obj = next((o for o in all_ops if o.get("id") == el_id), None)
                                    cx, cy = _centroid((el_obj or {}).get("polygon", []))
                                    st.session_state.selected_room = None
                                    st.session_state.selected_element = {
                                        "type": el_type,
                                        "id": el_id,
                                        "name": el_name or el_type.capitalize(),
                                        "cost": el_cost,
                                        "area": 0.0,
                                        "rate": 0.0,
                                        "category": "",
                                        "currency": currency,
                                        "cx": cx, "cy": cy,
                                    }
                                st.rerun()
                except TypeError:
                    st.plotly_chart(fig, use_container_width=True)

                # HTML legend overlaid in the top-right corner of the chart via CSS negative margin
                st.markdown(
                    '<div class="chart-legend-overlay">'
                    + build_gh_legend(st.session_state.layout)
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Element info panel — appears below chart when any element is clicked
            _render_element_panel()

        # ── AGENT CHAT PANEL ──────────────────────────────────────────────────
        with col_chat_inner:
            st.markdown('<p class="section-lbl">Agent Chat</p>', unsafe_allow_html=True)
            if st.session_state.selected_plan_key:
                st.caption(f"Active: {st.session_state.selected_plan_key}")

            chat_area = st.container(height=560)
            with chat_area:
                if st.session_state.messages:
                    render_chat()
                else:
                    st.caption("Ask a question or click a room to start.")

            pending = st.session_state.pop("pending_prompt", "") \
                      if "pending_prompt" in st.session_state else ""

            user_text = st.chat_input(
                placeholder='e.g. "bedroom 3 floor finish marble" or "total cost?"',
                key="chat_input",
            )

            if pending and not user_text:
                user_text = pending

            if user_text and user_text.strip():
                st.session_state.messages.append({"role": "user", "content": user_text.strip()})
                with chat_area:
                    with st.chat_message("user"):
                        st.markdown(user_text.strip())
                    with st.chat_message("assistant"):
                        placeholder = st.empty()
                        placeholder.markdown("_Thinking..._")
                reply = None
                gh_synced = False
                try:
                    reply = st.session_state.agent.process(
                        user_text.strip(),
                        layout=st.session_state.layout,
                        plans=st.session_state.layouts,
                        active_plan_key=st.session_state.selected_plan_key,
                        history=st.session_state.messages[:-1],
                        client_profile=st.session_state.get("client_profile") or None,
                    )
                    updated = st.session_state.agent.get_updated_layout()
                    if updated is not None and st.session_state.layout is not None:
                        st.session_state.layout = _merge_gh_colors(
                            st.session_state.layout, updated
                        )
                        if st.session_state.selected_plan_key in st.session_state.layouts:
                            st.session_state.layouts[st.session_state.selected_plan_key] = st.session_state.layout
                        st.session_state.selected_room = None
                        _write_gh_file(st.session_state.layout)
                        gh_synced = True
                except Exception as exc:
                    reply = f"Agent error: {exc}"
                finally:
                    if reply is not None:
                        placeholder.markdown(reply)
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                if gh_synced:
                    st.toast("Heatmap & Grasshopper synced", icon="✅")
                st.rerun()

            if st.button("Clear conversation", use_container_width=True, key="clear_chat_main"):
                st.session_state.messages = []
                st.rerun()

            # ── COST BREAKDOWN TABLE (below agent chat) ────────────────────────
            st.divider()
            if st.session_state.get("client_applied"):
                st.info("Client DNA template applied. Rates and costs below reflect the client's spending profile.")
            with st.expander("Cost Breakdown Table", expanded=True):
                df = build_cost_df(st.session_state.layout)
                if not df.empty:
                    st.table(df)
                else:
                    st.info("No cost data available in this layout.")

    else:
        st.info("Upload a layout in the sidebar to see the heatmap.")


# ── RIGHT: Vertical tab navigation ───────────────────────────────────────────
with col_panel:
    _NAV_TABS = [
        "Architectural Advice",
        "Sustainability Analysis",
        "Cost Matching",
        "Client DNA",
    ]
    st.markdown('<p class="section-lbl">Analysis · Navigate</p>', unsafe_allow_html=True)
    for _tab_name in _NAV_TABS:
        _is_active = st.session_state.get("active_tab") == _tab_name
        if st.button(
            _tab_name,
            use_container_width=True,
            key=f"nav_{_tab_name.replace(' ', '_')}",
            type="primary" if _is_active else "secondary",
        ):
            st.session_state.active_tab = _tab_name
            st.rerun()
    active_tab = st.session_state.get("active_tab", "Architectural Advice")
    st.divider()

    # ── TAB: Architectural Advice ─────────────────────────────────────────────
    if "Architectural" in active_tab:
        from nodes.arch_advice import (
            extract_materials_from_layout as _extract_layout_mats,
            extract_materials_from_messages as _extract_msg_mats,
            generate_advice_table_data as _gen_table,
            generate_carbon_matrix_data as _gen_matrix,
            calculate_carbon_budget as _calc_budget,
            FIRE_STANDARDS,
            DEFAULT_STANDARD,
            GWP_REGIONS,
            DEFAULT_REGION,
            CARBON_BUDGETS,
            DEFAULT_BUILDING_TYPE,
        )
        from nodes.bt_client import has_api_key as _bt_has_key

        _hdr_col, _std_col, _reg_col = st.columns([2, 1, 1])
        _hdr_col.markdown("#### Architectural Material Advice")
        _hdr_col.caption("Automatically read from chat history and active plan — fire rating, carbon footprint, and lifespan per material.")
        _selected_standard = _std_col.selectbox(
            "Fire rating standard",
            options=list(FIRE_STANDARDS.keys()),
            index=list(FIRE_STANDARDS.keys()).index(DEFAULT_STANDARD),
            key="fire_standard",
        )
        _selected_region = _reg_col.selectbox(
            "Carbon data source",
            options=list(GWP_REGIONS.keys()),
            index=list(GWP_REGIONS.keys()).index(DEFAULT_REGION),
            key="gwp_region",
        )
        _needs_bt = GWP_REGIONS.get(_selected_region, {}).get("source") == "ec3"
        if _needs_bt and not _bt_has_key():
            _reg_col.caption("Set BT_API_KEY env var to enable EC3 live data — using static fallback for now.")

        _layout_mats: list[str] = (
            _extract_layout_mats(st.session_state.layout)
            if st.session_state.layout else []
        )
        _msg_mats: list[str] = _extract_msg_mats(st.session_state.messages)
        _combined: list[str] = list(dict.fromkeys(_msg_mats + _layout_mats))

        _src_parts: list[str] = []
        if _msg_mats:
            _src_parts.append(f"chat: {', '.join(m.replace('_', ' ') for m in _msg_mats)}")
        if _layout_mats:
            _src_parts.append(f"plan: {', '.join(m.replace('_', ' ') for m in _layout_mats)}")
        if _src_parts:
            st.caption("Detected — " + " | ".join(_src_parts))
        else:
            st.info("No materials detected yet. Mention materials in the chat (e.g. 'bedroom floor finish marble') to populate this table.")

        if _combined:
            _mat_sig = ",".join(_combined) + "|" + _selected_standard + "|" + _selected_region
            if st.session_state.get("_advice_mat_sig") != _mat_sig:
                try:
                    st.session_state.arch_advice_rows = _gen_table(_combined, _selected_standard, _selected_region)
                    st.session_state["_advice_mat_sig"] = _mat_sig
                except Exception as _exc:
                    st.error(f"Advice generation failed: {_exc}")
                    st.session_state.arch_advice_rows = []

        _adv_rows: list[dict] = st.session_state.get("arch_advice_rows") or []
        if _adv_rows:
            _FIRE_COLOR = {
                "A1": "#10b981", "A2": "#10b981",
                "B": "#f59e0b", "C": "#f59e0b",
                "D": "#ef4444", "E": "#ef4444", "F": "#ef4444",
            }
            _th = (
                "text-align:left;padding:7px 14px;background:#faf9f6;"
                "border-bottom:2px solid #e0dbd2;color:#8a8784;font-size:0.68rem;"
                "font-weight:700;text-transform:uppercase;letter-spacing:0.07em"
            )
            _td = "padding:8px 14px;border-bottom:1px solid #eceae2;font-size:0.86rem;color:#171717"
            _headers = ["Material", "Carbon Footprint", "Fire Rating", "Lifespan (yrs)", "Lower-Carbon Alternative", "Recommendation"]
            _head_html = "".join(f'<th style="{_th}">{h}</th>' for h in _headers)
            _body_html = ""
            _td_alt = _td + ";color:#059669;font-style:italic"
            for _r in _adv_rows:
                _fire = str(_r.get("Fire Rating", "—"))
                _fc   = _FIRE_COLOR.get(_fire, "#111")
                _gwp  = _r.get("Carbon Footprint")
                _unit = _r.get("Unit", "")
                _gwp_s = f"{_gwp:,.2f} {_unit}" if isinstance(_gwp, (int, float)) else "—"
                _alt  = _r.get("Alternative", "—") or "—"
                _rec  = _r.get("Recommendation", "—") or "—"
                _body_html += (
                    f'<tr>'
                    f'<td style="{_td};font-weight:600">{_r.get("Material","")}</td>'
                    f'<td style="{_td}">{_gwp_s}</td>'
                    f'<td style="{_td};color:{_fc};font-weight:600">{_fire}</td>'
                    f'<td style="{_td}">{_r.get("Lifespan (yrs)","—")}</td>'
                    f'<td style="{_td_alt}">{_alt}</td>'
                    f'<td style="{_td};color:#555;font-size:0.82rem">{_rec}</td>'
                    f'</tr>'
                )
            st.markdown(
                f'<table style="width:100%;border-collapse:collapse">'
                f'<thead><tr>{_head_html}</tr></thead>'
                f'<tbody>{_body_html}</tbody>'
                f'</table>',
                unsafe_allow_html=True,
            )

            import csv, io as _io
            _csv_buf = _io.StringIO()
            _csv_fields = ["Material", "Carbon Footprint", "Unit", "Fire Rating",
                           "Lifespan (yrs)", "Alternative", "Recommendation"]
            _writer = csv.DictWriter(_csv_buf, fieldnames=_csv_fields, extrasaction="ignore")
            _writer.writeheader()
            _writer.writerows(_adv_rows)
            st.download_button(
                label="Export CSV",
                data=_csv_buf.getvalue(),
                file_name="architectural_advice.csv",
                mime="text/csv",
            )

        st.divider()
        st.markdown("#### Carbon Budget Tracker")
        st.caption("RIBA 2030 Climate Challenge targets. Only rooms with finish materials assigned via chat contribute.")

        _bldg_col, _ = st.columns([2, 3])
        _bldg_type = _bldg_col.selectbox(
            "Building type",
            options=list(CARBON_BUDGETS.keys()),
            index=list(CARBON_BUDGETS.keys()).index(DEFAULT_BUILDING_TYPE),
            key="building_type_select",
        )

        if st.session_state.layout:
            _budget = _calc_budget(st.session_state.layout, _bldg_type, _selected_region, st.session_state.messages)
            _pct    = _budget["pct_of_budget"]

            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Total Embodied Carbon", f"{_budget['total_kgco2e']:,.0f} kgCO2e")
            b2.metric("Normalised", f"{_budget['per_m2']:.1f} kgCO2e/m²")
            b3.metric("RIBA 2030 Target", f"{_budget['target_per_m2']:.0f} kgCO2e/m²")
            _delta_val = round(_pct - 100, 1)
            b4.metric(
                "Budget Used",
                f"{_pct:.1f}%",
                delta=f"{_delta_val:+.1f}%" if _pct > 0 else None,
                delta_color="inverse",
            )

            _bar_color = "#10b981" if _pct < 70 else "#f59e0b" if _pct < 100 else "#ef4444"
            st.markdown(
                f'<div style="background:#e0dbd2;border-radius:6px;height:10px;margin:6px 0">'
                f'<div style="background:{_bar_color};width:{min(_pct,100):.1f}%;'
                f'height:100%;border-radius:6px;transition:width 0.4s"></div></div>',
                unsafe_allow_html=True,
            )
            _status = "under budget" if _pct < 100 else "OVER budget"
            st.caption(
                f"{_status.upper()} — {_budget['coverage_pct']:.0f}% of floor area has assigned finishes "
                f"({_budget['assigned_area_m2']:.0f} / {_budget['total_area_m2']:.0f} m²)"
            )

            if _budget["breakdown"]:
                with st.expander("Room breakdown", expanded=True):
                    _th_s = "text-align:left;padding:6px 12px;background:#faf9f6;border-bottom:2px solid #e0dbd2;color:#8a8784;font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em"
                    _td_s = "padding:6px 12px;border-bottom:1px solid #eceae2;font-size:0.84rem;color:#171717"
                    _cols = ["Room", "Finish", "Material", "Area (m²)", "kgCO2e/m²", "Total kgCO2e"]
                    _head = "".join(f'<th style="{_th_s}">{c}</th>' for c in _cols)
                    _rows = ""
                    for _b in _budget["breakdown"]:
                        _rows += (
                            f'<tr>'
                            f'<td style="{_td_s}">{_b.get("Room","")}</td>'
                            f'<td style="{_td_s}">{_b.get("Finish","")}</td>'
                            f'<td style="{_td_s};font-weight:600">{_b.get("Material","")}</td>'
                            f'<td style="{_td_s}">{_b.get("Area (m²)","")}</td>'
                            f'<td style="{_td_s}">{_b.get("kgCO2e/m²","")}</td>'
                            f'<td style="{_td_s}">{_b.get("Total kgCO2e","")}</td>'
                            f'</tr>'
                        )
                    st.markdown(
                        f'<table style="width:100%;border-collapse:collapse">'
                        f'<thead><tr>{_head}</tr></thead>'
                        f'<tbody>{_rows}</tbody></table>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Assign finish materials to rooms via chat (e.g. 'living room floor finish marble') to track carbon.")
        else:
            st.info("Upload a layout to enable the carbon budget tracker.")

        st.divider()
        st.markdown("#### Cost × Carbon Matrix")
        st.caption(
            "Each dot is a room with an assigned finish. "
            "Dot size = floor area. Bottom-left = cheap & low carbon (ideal). "
            "Top-right = expensive & high carbon (avoid)."
        )

        if st.session_state.layout:
            _matrix = _gen_matrix(st.session_state.layout, _selected_region, st.session_state.messages)
            if _matrix:
                _is_estimated = any(p.get("estimated") for p in _matrix)
                if _is_estimated:
                    st.caption("Showing estimated positions based on chat-detected materials + average room stats. Assign finishes to specific rooms via chat for precise data.")
                _mx_by_mat: dict[str, list] = {}
                for _pt in _matrix:
                    _mx_by_mat.setdefault(_pt["material"], []).append(_pt)

                _mx_fig = go.Figure()
                for _mat_label, _pts in _mx_by_mat.items():
                    _mx_fig.add_trace(go.Scatter(
                        x=[p["cost_per_m2"] for p in _pts],
                        y=[p["gwp"] for p in _pts],
                        mode="markers+text",
                        name=_mat_label,
                        text=[f"{p['room']}<br>({p['finish_type']})" for p in _pts],
                        textposition="top center",
                        textfont=dict(size=9),
                        marker=dict(
                            size=[max(12, p["area_m2"] * 0.6) for p in _pts],
                            opacity=0.82,
                            line=dict(width=1, color="#fff"),
                        ),
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            f"Material: {_mat_label}<br>"
                            "Cost: %{x:,.0f}/m²<br>"
                            "Carbon: %{y:.2f} kgCO2e/m²"
                            "<extra></extra>"
                        ),
                    ))

                _all_costs = [p["cost_per_m2"] for p in _matrix]
                _all_gwps  = [p["gwp"] for p in _matrix]
                _avg_cost  = sum(_all_costs) / len(_all_costs)
                _avg_gwp   = sum(_all_gwps)  / len(_all_gwps)
                _mx_fig.add_hline(y=_avg_gwp,  line_dash="dot", line_color="#aaa",
                                  annotation_text=f"avg {_avg_gwp:.1f} kgCO2e/m²", annotation_position="right")
                _mx_fig.add_vline(x=_avg_cost, line_dash="dot", line_color="#aaa",
                                  annotation_text=f"avg {_avg_cost:,.0f}/m²", annotation_position="top")

                _mx_fig.update_layout(
                    xaxis_title="Construction cost per m²",
                    yaxis_title="Embodied carbon (kgCO2e/m²)",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#f5f2ed",
                    font=dict(color="#171717"),
                    height=420,
                    margin=dict(l=10, r=10, t=20, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
                )
                st.plotly_chart(_mx_fig, use_container_width=True)
            else:
                st.info("Assign finish materials to rooms via chat to populate the matrix.")
        else:
            st.info("Upload a layout to enable the cost × carbon matrix.")

    # ── TAB: Sustainability Analysis ──────────────────────────────────────────
    elif "Sustainability" in active_tab:
        render_sustainability_tab()

    # ── TAB: Cost Matching ────────────────────────────────────────────────────
    elif "Cost Matching" in active_tab:
        st.markdown("### Cost Matching")
        st.caption(
            "Enter your target budget — the advisor will suggest material and finish "
            "changes per room to reach your cost as closely as possible."
        )

        if not st.session_state.layout:
            st.info("Upload a layout in the sidebar to enable cost matching.")
        else:
            _cm_layout   = st.session_state.layout
            _cm_currency = _cm_layout.get("project", {}).get("currency", "USD")
            _cm_rooms    = _cm_layout.get("rooms", [])
            _cm_summary  = _cm_layout.get("summary") or _cm_layout.get("totals") or {}
            _cm_room_sum = sum(r.get("total_cost", 0) for r in _cm_rooms)
            _cm_non_room = (
                (_cm_summary.get("doors_total")   or _cm_summary.get("doors")   or 0) +
                (_cm_summary.get("windows_total") or _cm_summary.get("windows") or 0) +
                (_cm_summary.get("columns_total") or _cm_summary.get("columns") or 0)
            )
            _cm_grand = _cm_room_sum + _cm_non_room

            _col_in, _col_cur = st.columns([2, 1])
            with _col_in:
                _cm_target = st.number_input(
                    f"Your target total cost ({_cm_currency})",
                    min_value=0,
                    value=int(_cm_grand),
                    step=1000,
                    format="%d",
                    key="cm_target_input",
                )
            with _col_cur:
                st.metric("Current grand total", f"{_cm_grand:,.0f} {_cm_currency}")

            if st.button("Match Cost", type="primary", key="cm_run_btn"):
                from python_copilot import cost_match as _cost_match
                st.session_state.cm_result = _cost_match(_cm_layout, float(_cm_target))

            _cm_res = st.session_state.get("cm_result")
            if _cm_res:
                st.divider()
                _pct   = _cm_res["match_pct"]
                _adj   = _cm_res["adjusted_total"]
                _tgt   = _cm_res["target"]
                _delta = _adj - _cm_res["current_grand"]
                _cur   = _cm_currency

                _k1, _k2, _k3, _k4 = st.columns(4)
                _k1.metric("Target",         f"{_tgt:,.0f} {_cur}")
                _k2.metric("Adjusted total", f"{_adj:,.0f} {_cur}",
                           delta=f"{_delta:+,.0f}")
                _k3.metric("Gap remaining",  f"{abs(_tgt - _adj):,.0f} {_cur}")
                _k4.metric("Similarity",     f"{_pct:.1f}%",
                           delta=f"{'On target' if _pct >= 99 else 'Approx match'}")

                _bar_color = "#10b981" if _pct >= 90 else "#f59e0b" if _pct >= 70 else "#ef4444"
                st.markdown(
                    f'<div style="background:#e0dbd2;border-radius:6px;height:10px;margin:6px 0 14px">'
                    f'<div style="background:{_bar_color};width:{min(_pct,100):.1f}%;height:100%;'
                    f'border-radius:8px;transition:width 0.5s"></div></div>',
                    unsafe_allow_html=True,
                )

                _sugg = _cm_res["suggestions"]
                if not _sugg:
                    st.success("Plan is already at your target — no changes needed.")
                else:
                    st.markdown(f"#### Suggested finish changes ({len(_sugg)} adjustment{'s' if len(_sugg)!=1 else ''})")

                    _th = "".join(
                        f'<th style="padding:6px 10px;text-align:left;background:#faf9f6;'
                        f'border-bottom:2px solid #e0dbd2;white-space:nowrap;font-size:0.68rem;'
                        f'font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#8a8784">{h}</th>'
                        for h in ["Room", "Surface", "From", f"Rate ({_cur}/m²)",
                                  "To", f"Rate ({_cur}/m²)", "Area m²",
                                  f"Delta ({_cur})", f"New room total ({_cur})"]
                    )
                    _rows_html = ""
                    for i, s in enumerate(_sugg):
                        _bg  = "#ffffff" if i % 2 == 0 else "#f9f9f9"
                        _d   = s["delta_cost"]
                        _dc  = "#ef4444" if _d > 0 else "#10b981"
                        def _td(v, bold=False, color=None):
                            _st = f'padding:5px 10px;white-space:nowrap;'
                            if color: _st += f'color:{color};'
                            if bold:  _st += 'font-weight:600;'
                            return f'<td style="{_st}">{v}</td>'
                        _rows_html += (
                            f'<tr style="background:{_bg}">'
                            + _td(s["room"], bold=True)
                            + _td(s["surface"].capitalize())
                            + _td(s["from_material"])
                            + _td(f"{s['from_rate']:,.0f}")
                            + _td(f"<b>{s['to_material']}</b>", bold=True)
                            + _td(f"{s['to_rate']:,.0f}", bold=True)
                            + _td(f"{s['area']:.1f}")
                            + _td(f"{_d:+,.0f}", bold=True, color=_dc)
                            + _td(f"{s['new_room_total']:,.0f}", bold=True)
                            + "</tr>"
                        )
                    st.markdown(
                        f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse">'
                        f'<thead><tr>{_th}</tr></thead><tbody>{_rows_html}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

                    _total_delta = sum(s["delta_cost"] for s in _sugg)
                    _dc_total = "#ef4444" if _total_delta > 0 else "#10b981"
                    st.markdown(
                        f'<p style="margin-top:10px;font-size:13px;color:#555">'
                        f'Total adjustment: <b style="color:{_dc_total}">{_total_delta:+,.0f} {_cur}</b> '
                        f'across {len(_sugg)} room{"s" if len(_sugg)!=1 else ""}. '
                        f'Non-room costs (doors, windows, columns) are fixed at '
                        f'<b>{_cm_non_room:,.0f} {_cur}</b>.</p>',
                        unsafe_allow_html=True,
                    )

                st.divider()
                st.markdown("#### Room Cost — Before vs After")
                st.caption("Each room shows its original cost and the adjusted cost after suggested finish changes.")

                _all_rooms   = _cm_layout.get("rooms", [])
                _room_names  = [r.get("name", "") for r in _all_rooms]
                _orig_costs  = [r.get("total_cost", 0) or 0 for r in _all_rooms]

                _adj_map = {r.get("name"): r.get("total_cost", 0) or 0 for r in _all_rooms}
                if _sugg:
                    for _s in _sugg:
                        _adj_map[_s["room"]] = _s["new_room_total"]
                _adj_costs = [_adj_map.get(n, 0) for n in _room_names]

                _bar_colors = [
                    "#10b981" if _adj_map.get(n, 0) < (r.get("total_cost", 0) or 0)
                    else "#ef4444" if _adj_map.get(n, 0) > (r.get("total_cost", 0) or 0)
                    else "#b8b4ac"
                    for n, r in zip(_room_names, _all_rooms)
                ]

                _fig_bar = go.Figure()
                _fig_bar.add_trace(go.Bar(
                    name="Current cost",
                    x=_room_names,
                    y=_orig_costs,
                    marker_color="#c8c4bc",
                    text=[f"{v:,.0f}" for v in _orig_costs],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>Current: %{y:,.0f} " + _cur + "<extra></extra>",
                ))
                _fig_bar.add_trace(go.Bar(
                    name="Adjusted cost",
                    x=_room_names,
                    y=_adj_costs,
                    marker_color=_bar_colors,
                    text=[f"{v:,.0f}" for v in _adj_costs],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>Adjusted: %{y:,.0f} " + _cur + "<extra></extra>",
                ))
                _fig_bar.add_hline(
                    y=_tgt / max(len(_room_names), 1),
                    line_dash="dot", line_color="#f59e0b", line_width=1.5,
                    annotation_text=f"Target avg/room: {_tgt/max(len(_room_names),1):,.0f}",
                    annotation_position="top right",
                )
                _fig_bar.update_layout(
                    barmode="group",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#f5f2ed",
                    font=dict(color="#171717"),
                    height=380,
                    margin=dict(l=10, r=10, t=30, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.25,
                                xanchor="center", x=0.5),
                    yaxis=dict(title=f"Cost ({_cur})", gridcolor="#e0dbd2"),
                    xaxis=dict(tickangle=-20),
                )
                st.plotly_chart(_fig_bar, use_container_width=True)

    # ── TAB: Client DNA ───────────────────────────────────────────────────────
    elif "Client DNA" in active_tab:
        st.markdown("#### Client DNA — Spending Profile")

        if not st.session_state.get("client_profile"):
            st.info(
                "Upload up to 3 past project CSVs in the sidebar and click "
                "**Analyse Client Profile** to get started.\n\n"
                "**Expected CSV columns:** `room`, `area`, `cost` — optional: "
                "`category`, `rate`, `floor_finish`, `wall_finish`, `ceiling`"
            )
        else:
            _dna_profile = st.session_state.client_profile
            _dna_summary = st.session_state.get("client_summary", "")
            _dna_cats    = _dna_profile.get("categories", {})
            _dna_ranked  = _dna_profile.get("ranked_categories", [])

            st.markdown(_dna_summary)

            if _dna_ranked and _dna_cats:
                st.divider()
                st.markdown("#### Spending by Category")

                _ch_labels = [c.capitalize() for c in _dna_ranked]
                _ch_pcts   = [_dna_cats[c]["avg_budget_pct"] for c in _dna_ranked]
                _ch_rates  = [_dna_cats[c]["avg_rate_per_m2"] for c in _dna_ranked]

                _ch_col1, _ch_col2 = st.columns(2)
                with _ch_col1:
                    _fig_pct = go.Figure(go.Bar(
                        x=_ch_labels, y=_ch_pcts,
                        marker_color="#00AAAC",
                        text=[f"{p:.0f}%" for p in _ch_pcts],
                        textposition="outside",
                    ))
                    _fig_pct.update_layout(
                        title="Budget allocation (%)",
                        yaxis_title="% of total budget",
                        paper_bgcolor="#ffffff", plot_bgcolor="#f5f2ed",
                        height=300, margin=dict(l=10, r=10, t=40, b=10),
                        font=dict(color="#171717"),
                    )
                    st.plotly_chart(_fig_pct, use_container_width=True)

                with _ch_col2:
                    _fig_rate = go.Figure(go.Bar(
                        x=_ch_labels, y=_ch_rates,
                        marker_color="#1a2035",
                        text=[f"{r:,.0f}" for r in _ch_rates],
                        textposition="outside",
                    ))
                    _fig_rate.update_layout(
                        title="Average rate per m²",
                        yaxis_title="Rate (currency/m²)",
                        paper_bgcolor="#ffffff", plot_bgcolor="#f5f2ed",
                        height=300, margin=dict(l=10, r=10, t=40, b=10),
                        font=dict(color="#171717"),
                    )
                    st.plotly_chart(_fig_rate, use_container_width=True)

            _dna_template = st.session_state.get("client_template", {})

            if not _dna_template and st.session_state.layout:
                from client_profile import propose_template as _propose_tpl
                _dna_template = _propose_tpl(_dna_profile, st.session_state.layout)
                st.session_state.client_template = _dna_template

            if _dna_template and st.session_state.layout:
                st.divider()
                st.markdown("#### Proposed Spending Template")
                st.caption(
                    "Rates and finishes are suggested from this client's past projects. "
                    "▲ = more expensive than current · ▼ = cheaper than current."
                )

                _currency = st.session_state.layout.get("project", {}).get("currency", "")
                _tpl_rows = []
                for _tid, _t in _dna_template.items():
                    _delta = _t["delta_cost"]
                    _sign  = "▲" if _delta > 0 else ("▼" if _delta < 0 else "–")
                    _tpl_rows.append({
                        "Room":                               _t["room_name"],
                        "Category":                           _t["category"].capitalize(),
                        f"Current rate ({_currency}/m²)":    int(_t["current_rate"]),
                        f"Suggested rate ({_currency}/m²)":  int(_t["suggested_rate"]),
                        f"Current cost ({_currency})":        int(_t["current_cost"]),
                        f"Suggested cost ({_currency})":      int(_t["suggested_cost"]),
                        f"Delta ({_currency})":               f"{_sign} {abs(int(_delta)):,}",
                        "Preferred floor finish":             _t["preferred_floor"] or "—",
                        "Preferred wall finish":              _t["preferred_wall"]  or "—",
                    })

                st.table(pd.DataFrame(_tpl_rows))

                _total_cur  = sum(_t["current_cost"]  for _t in _dna_template.values())
                _total_sugg = sum(_t["suggested_cost"] for _t in _dna_template.values())
                _total_d    = _total_sugg - _total_cur

                _m1, _m2, _m3 = st.columns(3)
                _m1.metric("Current room total",  f"{_total_cur:,.0f} {_currency}")
                _m2.metric("Suggested room total", f"{_total_sugg:,.0f} {_currency}")
                _m3.metric("Difference", f"{_total_d:+,.0f} {_currency}", delta_color="inverse")

                st.divider()
                if not st.session_state.get("client_applied"):
                    if st.button(
                        "Apply Template to Current Project",
                        use_container_width=True,
                        key="apply_dna_tab",
                        type="primary",
                    ):
                        from client_profile import apply_template as _apply_tpl
                        _old_total = sum(r.get("total_cost", 0) for r in st.session_state.layout.get("rooms", []))
                        _updated = _apply_tpl(_dna_template, st.session_state.layout)
                        _new_total = sum(r.get("total_cost", 0) for r in _updated.get("rooms", []))
                        st.session_state.layout = _updated
                        _active_key = st.session_state.selected_plan_key
                        if _active_key:
                            st.session_state.layouts[_active_key] = _updated
                        st.session_state.client_applied = True
                        st.toast(
                            f"Client DNA applied — total changed from {_old_total:,.0f} to {_new_total:,.0f}",
                            icon="✅",
                        )
                        st.rerun()
                else:
                    st.success(
                        "Template applied to the current project. "
                        "The floor plan heatmap and cost table reflect the client's spending habits."
                    )
                    if st.button("Re-apply Template", use_container_width=True, key="reapply_dna_tab"):
                        from client_profile import apply_template as _apply_tpl
                        _old_total = sum(r.get("total_cost", 0) for r in st.session_state.layout.get("rooms", []))
                        _updated = _apply_tpl(_dna_template, st.session_state.layout)
                        _new_total = sum(r.get("total_cost", 0) for r in _updated.get("rooms", []))
                        st.session_state.layout = _updated
                        _active_key = st.session_state.selected_plan_key
                        if _active_key:
                            st.session_state.layouts[_active_key] = _updated
                        st.toast(
                            f"Template re-applied — total changed from {_old_total:,.0f} to {_new_total:,.0f}",
                            icon="✅",
                        )
                        st.rerun()

            elif not st.session_state.layout:
                st.info("Upload a layout in the sidebar to generate a spending template.")


# =============================================================================
# FULL WIDTH: Cost Breakdown Charts
# =============================================================================
if st.session_state.layout:
    _layout   = st.session_state.layout
    _currency = _layout.get("project", {}).get("currency", "")
    _rooms    = _layout.get("rooms", [])
    _openings = _layout.get("openings", [])
    _cols     = _layout.get("columns", [])
    _doors    = [o for o in _openings if (o.get("type") or "").lower() == "door"]
    _windows  = [o for o in _openings if (o.get("type") or "").lower() == "window"]

    st.divider()
    st.markdown("#### Cost Breakdown")

    pie_r, pie_d, pie_w, pie_c = st.columns(4, gap="large")

    def _pie_legend(labels, colors):
        items = "".join(
            f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:3px">'
            f'<div style="width:10px;height:10px;border-radius:2px;background:{c};flex-shrink:0"></div>'
            f'<span style="font-size:11px;color:#444;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{l}</span>'
            f'</div>'
            for l, c in zip(labels, colors)
        )
        return f'<div style="padding-top:4px">{items}</div>'

    _PIE_LAYOUT = dict(
        margin=dict(l=5, r=5, t=30, b=5),
        paper_bgcolor="#ffffff",
        showlegend=False,
        height=220,
    )

    with pie_r:
        if _rooms:
            labels = [r.get("name", "") for r in _rooms]
            values = [r.get("total_cost", 0) or 0 for r in _rooms]
            room_min = min(values) if values else 0
            room_max = max(values) if values else 1
            room_span = (room_max - room_min) or 1
            colors = [
                r.get("color_hex")
                or _lerp_color(((r.get("total_cost", 0) or 0) - room_min) / room_span)
                for r in _rooms
            ]
            fig_r = go.Figure(go.Pie(
                labels=labels, values=values,
                marker=dict(colors=colors, line=dict(color="#fff", width=1)),
                textinfo="percent",
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} " + _currency + "<extra></extra>",
                hole=0.4,
            ))
            fig_r.update_layout(title=dict(text="Rooms", font=dict(size=13, color="#333"), x=0.5), **_PIE_LAYOUT)
            st.plotly_chart(fig_r, use_container_width=True)
            st.markdown(_pie_legend(labels, colors), unsafe_allow_html=True)

    with pie_d:
        if _doors:
            d_labels = [d.get("subtype") or d.get("id") or "Door" for d in _doors]
            d_values = [d.get("cost", 0) or 0 for d in _doors]
            d_colors = [
                d.get("color_hex")
                or _cost_color_for_category(_layout, "doors", d.get("cost", 0) or 0, "#B27A41")
                for d in _doors
            ]
            fig_d = go.Figure(go.Pie(
                labels=d_labels, values=d_values,
                marker=dict(colors=d_colors, line=dict(color="#fff", width=1)),
                textinfo="percent",
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} " + _currency + "<extra></extra>",
                hole=0.4,
            ))
            fig_d.update_layout(title=dict(text="Doors", font=dict(size=13, color="#333"), x=0.5), **_PIE_LAYOUT)
            st.plotly_chart(fig_d, use_container_width=True)
            st.markdown(_pie_legend(d_labels, d_colors), unsafe_allow_html=True)
        else:
            st.caption("No door data")

    with pie_w:
        if _windows:
            w_labels = [w.get("subtype") or w.get("id") or "Window" for w in _windows]
            w_values = [w.get("cost", 0) or 0 for w in _windows]
            w_colors = [
                w.get("color_hex")
                or _cost_color_for_category(_layout, "windows", w.get("cost", 0) or 0, "#5AA0CD")
                for w in _windows
            ]
            fig_w = go.Figure(go.Pie(
                labels=w_labels, values=w_values,
                marker=dict(colors=w_colors, line=dict(color="#fff", width=1)),
                textinfo="percent",
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} " + _currency + "<extra></extra>",
                hole=0.4,
            ))
            fig_w.update_layout(title=dict(text="Windows", font=dict(size=13, color="#333"), x=0.5), **_PIE_LAYOUT)
            st.plotly_chart(fig_w, use_container_width=True)
            st.markdown(_pie_legend(w_labels, w_colors), unsafe_allow_html=True)
        else:
            st.caption("No window data")

    with pie_c:
        if _cols:
            c_labels = [c.get("subtype") or c.get("id") or "Column" for c in _cols]
            c_values = [c.get("cost", 0) or 0 for c in _cols]
            c_colors = [
                c.get("color_hex")
                or _cost_color_for_category(_layout, "columns", c.get("cost", 0) or 0, "#828282")
                for c in _cols
            ]
            fig_c = go.Figure(go.Pie(
                labels=c_labels, values=c_values,
                marker=dict(colors=c_colors, line=dict(color="#fff", width=1)),
                textinfo="percent",
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} " + _currency + "<extra></extra>",
                hole=0.4,
            ))
            fig_c.update_layout(title=dict(text="Columns", font=dict(size=13, color="#333"), x=0.5), **_PIE_LAYOUT)
            st.plotly_chart(fig_c, use_container_width=True)
            st.markdown(_pie_legend(c_labels, c_colors), unsafe_allow_html=True)
        else:
            st.caption("No column data")

    # ── Economic Spatial Distribution ─────────────────────────────────────────
    st.divider()
    st.markdown("#### Economic Spatial Distribution")

    ids = ["Total Project"]
    labels = ["Project Total"]
    parents = [""]
    values = [0]

    if _rooms:
        for r in _rooms:
            room_id = str(r.get("id"))
            ids.append(room_id)
            labels.append(r.get("name", "Room"))
            parents.append("Total Project")
            values.append(max(float(r.get("total_cost", 0)), 1))

        def add_elements(elements, type_name):
            for e in elements:
                poly = e.get("polygon", [])
                if not poly: continue
                cx = sum(p[0] for p in poly) / len(poly)
                cy = sum(p[1] for p in poly) / len(poly)

                found_parent = "Total Project"
                for r in _rooms:
                    if is_point_in_polygon(cx, cy, r.get("polygon", [])):
                        found_parent = str(r.get("id"))
                        break

                ids.append(f"{type_name}_{e.get('id', id(e))}")
                labels.append(e.get("subtype", type_name).capitalize())
                parents.append(found_parent)
                values.append(max(float(e.get("cost", 0)), 1))

        add_elements(_doors, "Door")
        add_elements(_windows, "Window")
        add_elements(_cols, "Column")

        with st.expander("DEBUG: Check Hierarchy Data"):
            debug_df = pd.DataFrame({"ID": ids, "Parent": parents, "Value": values})
            st.write(debug_df)

        fig_tree = go.Figure(go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            textinfo="label+value",
            marker=dict(colorscale="YlOrRd", showscale=False),
            pathbar=dict(visible=True)
        ))
        fig_tree.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=500)
        st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("No room data found for hierarchy.")


# =============================================================================
# FULL WIDTH: Multi-plan comparison
# =============================================================================
if len(st.session_state.layouts) >= 2:
    st.divider()
    st.markdown("#### Multi-Plan Comparison")
    st.caption("Compare saved plans by totals and visual heatmaps.")

    summary_rows = [
        _plan_summary_row(name, layout)
        for name, layout in st.session_state.layouts.items()
    ]
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    cmp_left, cmp_right = st.columns([2, 1], gap="large")

    with cmp_left:
        for idx, (name, layout) in enumerate(st.session_state.layouts.items()):
            st.markdown(f"**{name}**")
            fig_cmp = build_floor_plan(layout, plot_height=240)
            st.plotly_chart(
                fig_cmp,
                use_container_width=True,
                key=f"compare_heatmap_{idx}_{name}",
            )

    with cmp_right:
        if st.session_state.show_plan_comparison:
            st.markdown("### Spider Chart Comparison")
            st.caption("Rooms, doors, windows, and columns costs for each saved plan.")

            spider_rows = [
                _plan_category_costs(name, layout)
                for name, layout in st.session_state.layouts.items()
            ]
            spider_df = pd.DataFrame(spider_rows)
            _palette = ["#00AAAC", "#f59e0b", "#1a2035", "#10b981", "#8b5cf6"]
            plan_color_map = {name: _palette[i % len(_palette)] for i, name in enumerate(st.session_state.layouts)}

            if not spider_df.empty:
                currency_label = spider_df["Currency"].dropna().astype(str)
                currency_label = currency_label[currency_label != ""]
                currency = currency_label.iloc[0] if not currency_label.empty else ""

                categories = ["Rooms", "Doors", "Windows", "Columns"]
                category_max = {
                    cat: max(float(v or 0) for v in spider_df[cat].tolist()) if not spider_df.empty else 1.0
                    for cat in categories
                }
                for cat in categories:
                    if category_max[cat] <= 0:
                        category_max[cat] = 1.0

                radar_fig = go.Figure()
                palette_rgba = [
                    "rgba(239,68,68,0.18)",
                    "rgba(245,158,11,0.18)",
                    "rgba(59,130,246,0.18)",
                    "rgba(16,185,129,0.18)",
                    "rgba(139,92,246,0.18)",
                ]

                for idx, row in spider_df.iterrows():
                    color = plan_color_map[row["Plan"]]
                    actual_values = [float(row[cat]) for cat in categories]
                    norm_values = [100.0 * (actual_values[i] / category_max[categories[i]]) for i in range(len(categories))]
                    norm_values.append(norm_values[0])
                    radar_fig.add_trace(
                        go.Scatterpolar(
                            r=norm_values,
                            theta=categories + [categories[0]],
                            name=row["Plan"],
                            mode="lines+markers",
                            line=dict(color=color, width=2.2),
                            marker=dict(size=5, color=color),
                            fill="toself",
                            fillcolor=palette_rgba[idx % len(palette_rgba)],
                            hovertemplate=f"<b>{row['Plan']}</b><br>%{{theta}}<extra></extra>",
                        )
                    )

                radar_fig.update_layout(
                    height=500,
                    margin=dict(l=6, r=6, t=12, b=18),
                    paper_bgcolor="#ffffff",
                    font=dict(color="#111111"),
                    polar=dict(
                        bgcolor="#ffffff",
                        radialaxis=dict(
                            showline=False,
                            ticks="",
                            showticklabels=False,
                            gridcolor="#edf2f7",
                            range=[0, 100],
                            angle=90,
                            tickfont=dict(color="#111111"),
                        ),
                        angularaxis=dict(
                            gridcolor="#edf2f7",
                            tickfont=dict(color="#111111", size=12),
                            direction="clockwise",
                            rotation=90,
                        ),
                    ),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.12,
                        xanchor="center",
                        x=0.5,
                        font=dict(size=10, color="#111111"),
                    ),
                )
                st.plotly_chart(radar_fig, use_container_width=True, key="plan_spider_chart")

                st.markdown("### Total Cost Comparison")
            comparison_rows = [
                _plan_comparison_row(name, layout)
                for name, layout in st.session_state.layouts.items()
            ]
            comparison_df = pd.DataFrame(comparison_rows)
            if not comparison_df.empty:
                comparison_df = comparison_df.sort_values("Grand Total", ascending=True).reset_index(drop=True)
                cheapest = comparison_df["Grand Total"].min()
                comparison_df["Delta vs Cheapest"] = comparison_df["Grand Total"] - cheapest
                comparison_df["Delta %"] = comparison_df["Grand Total"].apply(
                    lambda v: 0.0 if cheapest == 0 else ((v - cheapest) / cheapest) * 100.0
                )

                currency_label = comparison_df["Currency"].dropna().astype(str)
                currency_label = currency_label[currency_label != ""]
                currency = currency_label.iloc[0] if not currency_label.empty else ""

                cheapest_row = comparison_df.iloc[0]
                most_expensive_row = comparison_df.iloc[-1]
                top_left, top_right = st.columns(2)
                with top_left:
                    st.markdown(
                        f"**Cheapest Plan**\n\n"
                        f"{cheapest_row['Grand Total']:,.0f} {currency}\n\n"
                        f"{cheapest_row['Plan']}"
                    )
                with top_right:
                    st.markdown(
                        f"**Most Expensive**\n\n"
                        f"{most_expensive_row['Grand Total']:,.0f} {currency}\n\n"
                        f"{most_expensive_row['Plan']}"
                    )

                bar_colors = [plan_color_map.get(plan, "#f59e0b") for plan in comparison_df["Plan"]]
                bar_fig = go.Figure(
                    go.Bar(
                        x=comparison_df["Grand Total"],
                        y=comparison_df["Plan"],
                        orientation="h",
                        marker=dict(color=bar_colors),
                        text=[f"{v:,.0f}" for v in comparison_df["Grand Total"]],
                        textposition="outside",
                        hovertemplate="<b>%{y}</b><br>Total: %{x:,.0f} " + currency + "<extra></extra>",
                    )
                )
                bar_fig.update_layout(
                    height=260,
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#f5f2ed",
                    font=dict(color="#111111"),
                    xaxis=dict(title=dict(text=f"Grand Total ({currency})", font=dict(color="#111111")), tickfont=dict(color="#111111")),
                    yaxis=dict(tickfont=dict(color="#111111"), title=""),
                    showlegend=False,
                )
                st.plotly_chart(bar_fig, use_container_width=True, key="plan_total_comparison_bar")

                display_df = comparison_df[["Plan", "Grand Total", "Room Total", "Delta vs Cheapest", "Delta %", "Rooms", "Footprint (m²)"]].copy()
                display_df["Grand Total"] = display_df["Grand Total"].round(0).astype(int)
                display_df["Room Total"] = display_df["Room Total"].round(0).astype(int)
                display_df["Delta vs Cheapest"] = display_df["Delta vs Cheapest"].round(0).astype(int)
                display_df["Delta %"] = display_df["Delta %"].map(lambda v: f"{v:.1f}%")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.empty()

    toggle_col, info_col = st.columns([1, 3], gap="small")
    with toggle_col:
        if st.button("Show comparison", use_container_width=True):
            st.session_state.show_plan_comparison = True
            st.rerun()
    with info_col:
        st.caption("Comparison is hidden until you choose to show it.")




