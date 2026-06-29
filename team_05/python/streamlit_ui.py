"""
AIA Studio Cost Advisor — Team 05
Streamlit GUI: interactive floor-plan cost heatmap + agent chat.

Run with:  streamlit run streamlit_ui.py
Requires:  streamlit>=1.33, plotly, pandas
"""
import base64
import copy
import io
import json
import math
import os
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from nodes.arch_advice import get_room_carbon_data

from langgraph_agent import LangGraphAgent

# ── Color palette for space types ─────────────────────────────────────────────
SPACE_TYPE_COLORS = {
    # Residential spaces
    "bedroom": "#FFB6C1",          # Light pink
    "bathroom": "#87CEEB",         # Sky blue
    "kitchen": "#FFD700",          # Gold
    "living": "#98FB98",           # Pale green
    "dining": "#DEB887",           # Burlywood
    "corridor": "#D3D3D3",         # Light gray
    "laundry": "#DDA0DD",          # Plum
    "balcony": "#F0E68C",          # Khaki
    "common": "#98FB98",           # Pale green
    # Core spaces
    "lift": "#FF6B6B",             # Red
    "stair": "#8B4513",            # Saddle brown
    "stairs": "#8B4513",           # Saddle brown
    "lobby": "#FFB347",            # Pastel orange
    "duct": "#808080",             # Gray (MEP)
    "mep": "#808080",              # Gray (MEP)
    "door": "#CD853F",             # Peru
    "window": "#E6F2FF",           # Light blue
    "column": "#6F6F6F",           # Medium gray
    "columns": "#6F6F6F",          # Medium gray
    "core": "#A0A0A0",             # Core gray
    "staircase": "#8B4513",        # Saddle brown
    "elevator": "#FF6B6B",         # Red (lift synonym)
    # Circulation
    "circulation": "#D3D3D3",      # Light gray
    # Fallback
    "default": "#CCCCCC"           # Light gray
}

COMPONENT_COLOR_TYPES = {
    "lift", "elevator", "stair", "stairs", "staircase",
    "duct", "mep", "lobby", "door", "doors",
    "window", "windows", "column", "columns", "core"
}

STAIR_TYPES = {"stair", "stairs", "staircase"}
MEP_TYPES = {"mep", "duct"}
FIXED_COMPONENT_TYPES = COMPONENT_COLOR_TYPES - STAIR_TYPES - MEP_TYPES

# ── Geometry utilities ────────────────────────────────────────────────────────
def _transform_polygon(polygon: list, rotation_deg: float, mirror: bool, offset_x: float, offset_y: float) -> list:
    """Transform polygon with rotation, mirror, and translation."""
    if not polygon:
        return polygon
    
    rad = math.radians(rotation_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    
    transformed = []
    for pt in polygon:
        x, y = pt[0], pt[1]
        
        # Apply mirror around y-axis if needed
        if mirror:
            x = -x
        
        # Apply rotation around origin
        rotated_x = x * cos_a - y * sin_a
        rotated_y = x * sin_a + y * cos_a
        
        # Apply translation
        final_x = rotated_x + offset_x
        final_y = rotated_y + offset_y
        
        transformed.append([final_x, final_y])
    
    return transformed


def _get_space_color(space_type: str, category: str = None) -> str:
    """Get color for a space type."""
    space_type = (space_type or "").strip().lower()
    category = (category or "").strip().lower() if category else None

    alias_map = {
        "elevator": "lift",
        "staircase": "stair",
        "doors": "door",
        "windows": "window",
        "columns": "column",
    }
    space_type = alias_map.get(space_type, space_type)
    if category:
        category = alias_map.get(category, category)

    # Try exact match first
    if space_type in SPACE_TYPE_COLORS:
        return SPACE_TYPE_COLORS[space_type]
    # Try category match
    if category and category in SPACE_TYPE_COLORS:
        return SPACE_TYPE_COLORS[category]
    # Return default
    return SPACE_TYPE_COLORS.get("default", "#CCCCCC")


def _format_space_label(value: str) -> str:
    """Format labels while preserving visible spacing between words/tokens."""
    text = str(value or "").replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", text)
    text = re.sub(r"(?<=[0-9])(?=[A-Za-z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Room"
    return text.title() if text.islower() else text


def _compact_space_label(value: str) -> str:
    """Return a short single-word label to avoid multi-line stacking on dense plans."""
    label = _format_space_label(value)
    lower = label.lower()
    shorthand = {
        "bedroom": "Bed",
        "bed room": "Bed",
        "living room": "Living",
        "bathroom": "Bath",
        "bath room": "Bath",
        "powder room": "Powder",
        "maid room": "Maid",
        "storage room": "Storage",
        "store room": "Store",
    }
    if lower in shorthand:
        return shorthand[lower]
    if lower.endswith(" room"):
        label = label[:-5].strip()
    parts = label.split()
    if not parts:
        return "Room"
    first = parts[0]
    m = re.search(r"\b(\d+)\b", label)
    if m and m.group(1) not in first:
        return f"{first} {m.group(1)}"
    return first


def _generate_component_polygon(component: dict, x_center: float = 0, y_center: float = 0) -> list:
    """Generate a rectangular polygon for core components (lifts, stairs, MEP)."""
    comp_type = component.get("type", "")
    
    if comp_type == "lift":
        width = component.get("width_m", 2.1)
        depth = component.get("depth_m", 2.1)
    elif comp_type in ["stair", "stairs"]:
        width = component.get("width_m", 1.5)
        depth = component.get("depth_m", 3.0)
    elif comp_type in ["duct", "mep"]:
        width = component.get("width_m", 1.2)
        depth = component.get("depth_m", 1.2)
    elif comp_type == "door":
        width = 1.0
        depth = 0.1
    elif comp_type == "lobby":
        width = component.get("width_m", 4.0)
        depth = component.get("depth_m", 4.0)
    else:
        width = 1.0
        depth = 1.0
    
    w2 = width / 2
    d2 = depth / 2
    
    polygon = [
        [x_center - w2, y_center - d2],
        [x_center + w2, y_center - d2],
        [x_center + w2, y_center + d2],
        [x_center - w2, y_center + d2]
    ]
    
    return polygon


def _rect_polygon_from_xywh(x: float, y: float, w: float, h: float) -> list:
    """Create rectangle polygon from x/y origin and width/depth dimensions."""
    return [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
    ]


def _rect_polygon_from_center(cx: float, cy: float, w: float, h: float) -> list:
    """Create rectangle polygon from center point and dimensions."""
    x0 = cx - (w / 2)
    y0 = cy - (h / 2)
    return _rect_polygon_from_xywh(x0, y0, w, h)


def _room_bbox(room: dict) -> tuple[float, float, float, float] | None:
    """Return (x0, y0, x1, y1) bbox for a room-like object."""
    x = room.get("x")
    y = room.get("y")
    w = room.get("width")
    d = room.get("depth")
    if all(isinstance(v, (int, float)) for v in (x, y, w, d)):
        return float(x), float(y), float(x) + float(w), float(y) + float(d)

    poly = room.get("polygon") or []
    if isinstance(poly, list) and poly:
        xs = [p[0] for p in poly if isinstance(p, (list, tuple)) and len(p) >= 2]
        ys = [p[1] for p in poly if isinstance(p, (list, tuple)) and len(p) >= 2]
        if xs and ys:
            return min(xs), min(ys), max(xs), max(ys)
    return None


def _host_edges_from_bboxes(host_bboxes: list[tuple[float, float, float, float]]) -> list[tuple[str, float, float, float]]:
    """Build axis-aligned wall-edge segments from room bboxes."""
    edges: list[tuple[str, float, float, float]] = []
    for x0, y0, x1, y1 in host_bboxes:
        edges.append(("v", x0, y0, y1))
        edges.append(("v", x1, y0, y1))
        edges.append(("h", y0, x0, x1))
        edges.append(("h", y1, x0, x1))
    return edges


def _point_to_axis_segment_distance(px: float, py: float, edge: tuple[str, float, float, float]) -> float:
    """Distance from point to axis-aligned segment represented by edge tuple."""
    orient, line_val, seg_min, seg_max = edge
    if orient == "v":
        x = line_val
        y = min(max(py, seg_min), seg_max)
        return math.hypot(px - x, py - y)
    y = line_val
    x = min(max(px, seg_min), seg_max)
    return math.hypot(px - x, py - y)


def _oriented_opening_polygon(
    room: dict,
    host_bboxes: list[tuple[float, float, float, float]],
    host_edges: list[tuple[str, float, float, float]] | None = None,
) -> list | None:
    """Orient door/window to nearest host wall edge (parallel to wall)."""
    x = room.get("x")
    y = room.get("y")
    w = room.get("width")
    d = room.get("depth")
    if not all(isinstance(v, (int, float)) for v in (x, y, w, d)):
        return None

    x = float(x)
    y = float(y)
    w = float(w)
    d = float(d)
    cx = x + (w / 2)
    cy = y + (d / 2)
    long_dim = max(w, d)
    thin_dim = min(w, d)

    if not host_bboxes:
        return _rect_polygon_from_xywh(x, y, w, d)

    edges = host_edges or _host_edges_from_bboxes(host_bboxes)
    if not edges:
        return _rect_polygon_from_xywh(x, y, w, d)

    nearest = min(edges, key=lambda e: _point_to_axis_segment_distance(cx, cy, e))
    nearest_orient = nearest[0]

    # Openings should run parallel to the nearest wall edge.
    if nearest_orient == "v":
        return _rect_polygon_from_center(cx, cy, thin_dim, long_dim)
    return _rect_polygon_from_center(cx, cy, long_dim, thin_dim)


def _normalize_layout_schema(layout: dict) -> dict:
    """Normalize heterogeneous JSON room schemas into the dashboard's canonical shape."""
    if not isinstance(layout, dict):
        return {"rooms": []}

    proj = layout.get("project", {})
    if isinstance(proj, str):
        proj = {"name": proj}
    elif not isinstance(proj, dict):
        proj = {}

    rooms = layout.get("rooms", [])
    if isinstance(rooms, list):
        host_bboxes: list[tuple[float, float, float, float]] = []
        for host in rooms:
            if not isinstance(host, dict):
                continue
            h_type = (host.get("room_type") or host.get("type") or host.get("category") or "").strip().lower()
            if h_type in COMPONENT_COLOR_TYPES:
                continue
            bb = _room_bbox(host)
            if bb is not None:
                host_bboxes.append(bb)
        host_edges = _host_edges_from_bboxes(host_bboxes)

        for idx, room in enumerate(rooms):
            if not isinstance(room, dict):
                continue

            room.setdefault("id", room.get("name") or f"room_{idx}")

            room_type = (room.get("room_type") or room.get("type") or "").strip().lower()
            if room_type:
                room.setdefault("type", room_type)
                room.setdefault("category", room_type)

            if room.get("total_cost") is None:
                room["total_cost"] = (
                    room.get("total_cost_usd")
                    or room.get("cost_usd")
                    or room.get("cost")
                    or 0
                )

            if room.get("rate_per_m2") is None:
                room["rate_per_m2"] = (
                    room.get("rate_per_m2_usd")
                    or room.get("rate")
                    or 0
                )

            if room.get("area_m2") is None:
                w = room.get("width")
                d = room.get("depth")
                if isinstance(w, (int, float)) and isinstance(d, (int, float)):
                    room["area_m2"] = float(w) * float(d)

            if not room.get("space_color_hex"):
                room["space_color_hex"] = room.get("color_hex") or room.get("color")

            if not room.get("polygon"):
                x = room.get("x")
                y = room.get("y")
                w = room.get("width")
                d = room.get("depth")
                if all(isinstance(v, (int, float)) for v in (x, y, w, d)):
                    if room_type in {"door", "window"}:
                        room["polygon"] = _oriented_opening_polygon(room, host_bboxes, host_edges) or _rect_polygon_from_xywh(float(x), float(y), float(w), float(d))
                    else:
                        room["polygon"] = _rect_polygon_from_xywh(float(x), float(y), float(w), float(d))

    if not proj.get("currency"):
        if any(isinstance(r, dict) and r.get("total_cost_usd") is not None for r in rooms if isinstance(rooms, list)):
            proj["currency"] = "USD"
        else:
            proj["currency"] = "AED"

    layout["project"] = proj
    return layout

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
  /* ── Backgrounds ── */
  --bg:        #1e2a45;
  --bg-text:   #c8ccdc;
  --card:      #ffffff;
  --card-alt:  #f9f8f6;
  /* ── Sidebar ── */
  --sb-bg:     #1a2035;
  --sb-surf:   #212840;
  --sb-border: #2d3655;
  --sb-text:   #c8ccdc;
  --sb-muted:  #5c6278;
  --sb-lbl:    #3e4562;
  /* ── Text ── */
  --text:      #1a1a1a;
  --text-2:    #404040;
  --muted:     #8a8784;
  /* ── Accent ── */
  --teal:      #00AAAC;
  --teal-dk:   #007b80;
  --teal-lt:   #e0f5f5;
  --navy:      #1a2035;
  /* ── Status ── */
  --green:     #10b981;
  --amber:     #f59e0b;
  --red:       #ef4444;
  /* ── Borders ── */
  --border:    #e4dfd8;
  --border-lt: #eee9e2;
  /* ── Radius ── */
  --r-xs:4px; --r-sm:8px; --r:12px; --r-lg:18px;
  /* ── Shadows ── */
  --s-xs: 0 1px 3px rgba(0,0,0,0.06);
  --s-sm: 0 2px 6px rgba(0,0,0,0.06),0 1px 3px rgba(0,0,0,0.04);
  --s:    0 4px 18px rgba(0,0,0,0.07),0 1px 4px rgba(0,0,0,0.04);
  --s-lg: 0 8px 32px rgba(0,0,0,0.10),0 2px 8px rgba(0,0,0,0.06);
  /* ── Spacing ── */
    --sp-xs:3px; --sp-sm:6px; --sp-md:12px; --sp-lg:18px; --sp-xl:28px;
  /* ── Font ── */
  --font: 'Inter',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}

/* ── BASE ────────────────────────────────────────────────────────────────── */
.stApp { background: var(--bg) !important; font-family: var(--font); }
.stApp p,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6,
.stApp label,.stApp button,.stApp input,.stApp textarea,.stApp select,
.stApp td,.stApp th,.stApp li { font-family: var(--font); color: var(--bg-text); }

html, body { overflow: hidden !important; height: 100% !important; }
.stApp { height: 100vh !important; overflow: hidden !important; }

/* Hide Streamlit chrome visually, but keep sidebar open/close controls reachable. */
[data-testid="stHeader"] {
  display:block !important;
  height:2.75rem !important;
  min-height:2.75rem !important;
  background:transparent !important;
  pointer-events:auto !important;
}
[data-testid="stToolbar"] { display:none !important; }
[data-testid="stDecoration"] { display:none !important; }
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stHeader"] button {
  display:flex !important;
  visibility:visible !important;
  opacity:1 !important;
  pointer-events:auto !important;
}
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
  position:fixed !important;
  top:0.55rem !important;
  left:0.55rem !important;
  z-index:1000000 !important;
  width:2.25rem !important;
  height:2.25rem !important;
  align-items:center !important;
  justify-content:center !important;
  background:var(--sb-bg) !important;
  border:1px solid var(--sb-border) !important;
  border-radius:var(--r-sm) !important;
  box-shadow:var(--s-sm) !important;
}
[data-testid="collapsedControl"] *,
[data-testid="stSidebarCollapsedControl"] * {
  color:#ffffff !important;
  fill:#ffffff !important;
}
[data-testid="stAppViewContainer"] { margin-top:0 !important; }
[data-testid="stAppViewContainer"] > .main { height: 100vh !important; overflow: hidden !important; }
[data-testid="stAppViewContainer"] section.stMain { overflow-y: auto !important; }
[data-testid="stAppViewContainer"] > .main .block-container { height: 100vh !important; overflow: hidden !important; }

/* Keep layout usable without page scroll: each main column scrolls internally. */
[data-testid="stAppViewContainer"] > .main .block-container > div > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    max-height: calc(100vh - 54px) !important;
    overflow-y: auto !important;
    overscroll-behavior: contain !important;
}

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

.block-container { padding-top:0.35rem !important; padding-bottom:0.55rem !important; padding-left:0.7rem !important; padding-right:0.7rem !important; max-width:none !important; }

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
  display:block !important;
  visibility:visible !important;
  opacity:1 !important;
  transform:none !important;
  margin-left:0 !important;
  left:0 !important;
  min-width:21rem !important;
  width:21rem !important;
  max-width:21rem !important;
  flex:0 0 21rem !important;
  z-index:999999 !important;
}
section[data-testid="stSidebar"] > div { padding: 2rem 1.5rem 3rem !important; }
section[data-testid="stSidebar"] button[kind="header"],
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
  display:flex !important;
  visibility:visible !important;
  opacity:1 !important;
  pointer-events:auto !important;
  color:#ffffff !important;
}
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
h4 { font-size:0.96rem !important; font-weight:600 !important; margin-top:0.5rem !important; margin-bottom:0.15rem !important; }
hr { border-color:var(--border-lt) !important; margin:0.8rem 0 !important; }
.stCaption,small { color:var(--muted) !important; font-size:0.74rem !important; line-height:1.4 !important; }

/* ── METRICS ─────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background:var(--card) !important; border:1px solid var(--border) !important;
    border-radius:var(--r) !important; padding:0.75rem 0.9rem !important;
  box-shadow:var(--s-xs) !important;
}
[data-testid="stMetricLabel"] {
  font-size:0.65rem !important; font-weight:600 !important;
  text-transform:uppercase !important; letter-spacing:0.07em !important; color:var(--muted) !important;
}
[data-testid="stMetricValue"] {
    font-size:1.25rem !important; font-weight:700 !important;
  letter-spacing:-0.04em !important; color:var(--text) !important; line-height:1.15 !important;
}

/* ── BUTTONS ─────────────────────────────────────────────────────────────── */
[data-testid="stBaseButton-primary"] {
  background:var(--teal) !important; color:#fff !important;
  border:1px solid var(--teal) !important; border-radius:var(--r-sm) !important;
  font-size:0.875rem !important; font-weight:600 !important;
  box-shadow:0 1px 4px rgba(0,170,172,0.28) !important;
  transition:background 0.15s,box-shadow 0.15s !important;
}
[data-testid="stBaseButton-primary"] * { color:#fff !important; }
[data-testid="stBaseButton-primary"]:hover {
  background:var(--teal-dk) !important;
  box-shadow:0 3px 10px rgba(0,170,172,0.38) !important;
}
[data-testid="stBaseButton-secondary"] {
  background:var(--card) !important; color:var(--text-2) !important;
  border:1px solid var(--border) !important; border-radius:var(--r-sm) !important;
  font-size:0.875rem !important; font-weight:500 !important; box-shadow:none !important;
  transition:border-color 0.12s,background 0.12s !important;
}
[data-testid="stBaseButton-secondary"]:hover {
  background:var(--card-alt) !important; border-color:#c0bab2 !important; color:var(--text) !important;
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
  padding:0 0.85rem !important;
}
[data-testid="stExpander"] summary {
    font-size:0.82rem !important; font-weight:600 !important;
  letter-spacing:-0.01em !important; color:var(--text-2) !important;
    padding:0.72rem 0 !important;
}

/* ── CHAT ────────────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
  background:var(--card) !important; border:1.5px solid var(--border) !important;
  border-radius:var(--r) !important; box-shadow:var(--s-xs) !important;
  margin-top:0.5rem !important;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] section { background:var(--card) !important; }
[data-testid="stChatInput"] button { background:transparent !important; border:none !important; }
[data-testid="stChatInput"] textarea,[data-baseweb="textarea"] textarea {
  background:var(--card) !important; color:var(--text) !important;
    font-size:0.82rem !important; border:none !important; padding:0.48rem 0.62rem !important;
}
[data-testid="stChatMessageContent"] {
  background:var(--card-alt) !important; border:1px solid var(--border-lt) !important;
    border-radius:var(--r) !important; font-size:0.8rem !important;
    line-height:1.45 !important; color:var(--text) !important;
    padding:0.58rem 0.75rem !important;
}
.st-key-agent_chat_scroll_area {
  height: 380px !important;
  max-height: 380px !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  overscroll-behavior: contain !important;
  padding: 0.35rem 0.35rem 0.45rem !important;
  border: 1px solid var(--border-lt) !important;
  border-radius: var(--r) !important;
  background: #ffffff !important;
}
.st-key-agent_chat_scroll_area [data-testid="stVerticalBlock"] {
  overflow: visible !important;
}
.st-key-agent_chat_scroll_area::-webkit-scrollbar {
  width: 8px;
}
.st-key-agent_chat_scroll_area::-webkit-scrollbar-thumb {
  background: #c9c3ba;
  border-radius: 999px;
}
.st-key-agent_chat_scroll_area::-webkit-scrollbar-track {
  background: #f5f2ed;
}

/* ── TABLES ──────────────────────────────────────────────────────────────── */
[data-testid="stTable"] * {
  background:var(--card) !important; color:var(--text) !important;
  border-color:var(--border-lt) !important;
}
[data-testid="stDataFrame"] {
  background:var(--card) !important;
  border-radius:var(--r) !important;
  overflow:hidden !important;
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
    padding:1.1rem 1.15rem 1.2rem !important;
}
[data-testid="stColumn"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  background:transparent !important; border:none !important;
  box-shadow:none !important; border-radius:0 !important; padding:0 0.75rem !important;
}
[data-testid="stColumn"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:last-child) {
  border-right:1px solid var(--border-lt) !important; padding-right:1.5rem !important;
}
[data-testid="stColumn"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:first-child) {
  padding-left:1.5rem !important;
}

/* ── COMPONENT CLASSES ───────────────────────────────────────────────────── */
.section-lbl {
  font-size:0.65rem; font-weight:600; color:var(--muted);
  letter-spacing:0.1em; text-transform:uppercase;
    margin:0.72rem 0 0.46rem; display:flex; align-items:center; gap:0.45rem;
}
.section-lbl:first-child { margin-top:0.25rem; }
.section-lbl::after { content:''; flex:1; height:1px; background:var(--border-lt); }

.sb-card {
  background:var(--sb-surf); border:1px solid var(--sb-border);
  border-radius:var(--r-sm); padding:1rem 1.1rem; margin-bottom:0.6rem;
}

.proj-title {
    font-size:0.8rem; font-weight:600; color:var(--text);
    letter-spacing:-0.01em; margin:0 0 0.36rem; line-height:1.2;
}

.kv-row {
  display:flex; justify-content:space-between; align-items:center;
    padding:0.26rem 0; border-bottom:1px solid var(--border-lt);
    font-size:0.78rem; gap:0.4rem;
}
.kv-row:last-child { border-bottom:none; }
.kv-key { color:var(--muted); }
.kv-val { color:var(--text); font-weight:600; text-align:right; }

.room-card {
  background:var(--card); border:1px solid var(--border);
    border-radius:var(--r); padding:0.72rem 0.82rem; margin-top:0.42rem;
  box-shadow:var(--s-xs);
}
.room-card h4 { margin:0 0 0.35rem; font-size:0.84rem; font-weight:600; }

@media (max-width:1200px) {
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { border-radius:var(--r) !important; }
}

/* ── CHART LEGEND OVERLAY ────────────────────────────────────────────────── */
.chart-legend-wrap {
  height: 0;
  overflow: visible;
  position: relative;
  z-index: 100;
}
.chart-legend-overlay {
  position: absolute;
  top: -680px;
  right: 10px;
  width: 172px;
  background: rgba(255,255,255,0.93);
  border: 1px solid #e0dbd2;
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.10);
  pointer-events: none;
}
</style>
""", unsafe_allow_html=True)

# Streamlit can remember a collapsed sidebar in the browser. Reopen it once
# per tab on load, then leave normal sidebar toggling to the user.
components.html(
    """
    <script>
    (function () {
      const flag = "planwise_sidebar_opened_once_v2";
      const parentWindow = window.parent;
      const doc = parentWindow && parentWindow.document;
      if (!doc || parentWindow.sessionStorage.getItem(flag) === "1") return;

      function sidebarIsOpen() {
        const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
        if (!sidebar) return false;
        const rect = sidebar.getBoundingClientRect();
        return rect.width > 80 && rect.right > 80;
      }

      function openSidebar(attempt) {
        if (sidebarIsOpen()) {
          parentWindow.sessionStorage.setItem(flag, "1");
          return;
        }

        const candidates = [
          '[data-testid="collapsedControl"] button',
          '[data-testid="stSidebarCollapsedControl"] button',
          '[data-testid="collapsedControl"]',
          '[data-testid="stSidebarCollapsedControl"]'
        ];
        let button = null;
        for (const selector of candidates) {
          button = doc.querySelector(selector);
          if (button) break;
        }
        if (!button) {
          button = Array.from(doc.querySelectorAll('button')).find((el) => {
            const label = (el.getAttribute('aria-label') || el.title || '').toLowerCase();
            return label.includes('sidebar') || label.includes('navigation');
          });
        }

        if (button) {
          button.click();
          window.setTimeout(() => {
            if (sidebarIsOpen()) {
              parentWindow.sessionStorage.setItem(flag, "1");
            } else if (attempt < 30) {
              openSidebar(attempt + 1);
            }
          }, 150);
          return;
        }
        if (attempt < 30) {
          window.setTimeout(() => openSidebar(attempt + 1), 150);
        }
      }

      openSidebar(0);
    })();
    </script>
    """,
    height=0,
)

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


def render_3d_heatmap(layout_data, extrusion_mode="skyline", color_mode="heatmap"):
    """
    Embeds a Three.js interactive 3D heatmap into Streamlit.
    """
    def _safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _el_cost(el: dict) -> float:
        return _safe_float(
            el.get("total_cost")
            or el.get("total_cost_usd")
            or el.get("cost")
            or el.get("cost_usd")
            or 0
        )

    labor_mult = _safe_float(st.session_state.get("labor", 1.0), 1.0)
    inflation = 1 + (_safe_float(st.session_state.get("inflation", 0.0), 0.0) / 100.0)
    tax = _safe_float(st.session_state.get("carbon_tax", 0.0), 0.0)
    cur_factor = _safe_float(st.session_state.get("currency_factor", 1.0), 1.0)
    cur_code = st.session_state.get("currency_code") or ((layout_data.get("project", {}) or {}).get("currency", "AED"))

    def _adj_room_cost(room: dict) -> float:
        base = _el_cost(room)
        gwp = _safe_float(room.get("gwp"), 0.0)
        return ((base * labor_mult * inflation) + (gwp * tax)) * cur_factor

    def _adj_simple_cost(el: dict) -> float:
        return _el_cost(el) * cur_factor

    rooms_src = layout_data.get("costs", {}).get("rooms", {}).get("rooms", layout_data.get("rooms", []))
    if isinstance(rooms_src, dict):
        rooms_src = list(rooms_src.values())

    room_style_map = {}
    def _room_kind(room: dict) -> str:
        return (
            room.get("type")
            or room.get("room_type")
            or room.get("category")
            or ""
        ).strip().lower()

    def _norm_t(value: float, vals: list[float]) -> float:
        if not vals:
            return 0.0
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))

    gradient_rooms = [r for r in rooms_src if _room_kind(r) not in COMPONENT_COLOR_TYPES]
    stair_rooms = [r for r in rooms_src if _room_kind(r) in STAIR_TYPES]
    mep_rooms = [r for r in rooms_src if _room_kind(r) in MEP_TYPES]

    costs = [_adj_room_cost(r) for r in gradient_rooms] if gradient_rooms else [_adj_room_cost(r) for r in rooms_src]
    mn, mx = (min(costs), max(costs)) if costs else (0.0, 1.0)
    span = (mx - mn) or 1.0

    stair_costs = [_adj_room_cost(r) for r in stair_rooms]
    mep_costs = [_adj_room_cost(r) for r in mep_rooms]

    for idx, room in enumerate(rooms_src):
        room_key = str(room.get("id") or f"idx_{idx}")
        room_type = _room_kind(room)
        geom_color = room.get("space_color_hex") or room.get("color_hex") or room.get("color")
        rgb = room.get("color_rgb")
        if not geom_color and isinstance(rgb, (list, tuple)) and len(rgb) >= 3:
            try:
                geom_color = _rgb_to_hex((int(rgb[0]), int(rgb[1]), int(rgb[2])))
            except (TypeError, ValueError):
                geom_color = None

        if color_mode == "space":
            adj_cost = _adj_room_cost(room)
            color_hex = geom_color or _get_space_color(room_type, room.get("category", ""))
        elif room_type in STAIR_TYPES:
            adj_cost = _adj_room_cost(room)
            stair_t = _norm_t(adj_cost, stair_costs)
            color_hex = _interp_hex("#E8CDAA", "#8B4513", stair_t)
        elif room_type in MEP_TYPES:
            adj_cost = _adj_room_cost(room)
            mep_t = _norm_t(adj_cost, mep_costs)
            color_hex = _interp_hex("#D7D7D7", "#6A6A6A", mep_t)
        elif room_type in COMPONENT_COLOR_TYPES:
            adj_cost = _adj_room_cost(room)
            color_hex = _get_space_color(room_type, room.get("category", ""))
        elif room_type == "door":
            adj_cost = _adj_simple_cost(room)
            color_hex = _cost_color_for_category(layout_data, "doors", adj_cost, _get_space_color("door", room.get("category", "")))
        elif room_type == "window":
            adj_cost = _adj_simple_cost(room)
            color_hex = _cost_color_for_category(layout_data, "windows", adj_cost, _get_space_color("window", room.get("category", "")))
        elif room_type in {"column", "columns"}:
            adj_cost = _adj_simple_cost(room)
            color_hex = _cost_color_for_category(layout_data, "columns", adj_cost, _get_space_color("column", room.get("category", "")))
        else:
            adj_cost = _adj_room_cost(room)
            t = room.get("heat_t", (adj_cost - mn) / span)
            color_hex = _lerp_color(float(t))

        display_name = _format_space_label(room.get("room_type") or room.get("name") or room.get("id") or "Room")
        room_style_map[room_key] = {
            "color_hex": color_hex,
            "cost": round(adj_cost, 2),
            "currency": cur_code,
            "name": display_name,
            "label_name": _compact_space_label(display_name),
        }

    layout_json_str = json.dumps(layout_data)
    room_style_json = json.dumps(room_style_map)

    import hashlib as _hl
    _cost_hash = _hl.md5(
        json.dumps({k: v["cost"] for k, v in room_style_map.items()}, sort_keys=True).encode()
    ).hexdigest()[:8]
    # Geometry hash — changes only when room polygons change (new file), NOT when costs change.
    # This controls whether the iframe reloads. Cost updates go through the bridge.
    _geom_hash = _hl.md5(
        json.dumps(
            [(r.get("id"), r.get("polygon")) for r in rooms_src],
            sort_keys=True
        ).encode()
    ).hexdigest()[:12]

    # ── Bridge: publish current costs to window.parent BEFORE the 3D viewer.
    # The viewer polls this every 600 ms; no iframe reload needed for cost changes.
    components.html(
        f"""<script>
            window.parent.planwise_room_style_map = {room_style_json};
            window.parent.planwise_cost_version   = '{_cost_hash}';
            window.parent.planwise_3d_mode        = '{extrusion_mode}';
        </script>""",
        height=0,
    )

    html_code = f"""<!-- geom:{_geom_hash} -->
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
        <style>
            body {{ margin: 0; overflow: hidden; font-family: sans-serif; background: #ffffff; color: #111; }}
            #canvas-container {{ width: 100vw; height: 100vh; }}
            .hologram-label {{
                position: absolute;
                background: rgba(255, 255, 255, 0.90);
                color: #1f2937;
                padding: 2px 7px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 10px;
                pointer-events: none;
                transform: translate(-50%, -50%);
                text-align: center;
                white-space: nowrap;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
            }}
            .hologram-label span {{ color: #111827; font-weight: 600; font-size: 10px; display: block; }}
            .pick-popup {{
                position: fixed;
                z-index: 9999;
                min-width: 200px;
                background: rgba(255, 255, 255, 0.85);
                border: 1px solid #9B6FD0;
                border-radius: 8px;
                box-shadow: 0 4px 16px rgba(107, 63, 160, 0.15);
                padding: 10px 14px;
                color: #1a1a2e;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
                display: none;
                pointer-events: none;
                backdrop-filter: blur(6px);
            }}
            .pick-popup .ttl {{
                font-weight: 700;
                margin-bottom: 6px;
                font-size: 13px;
                color: #1a1a2e;
            }}
            .pick-popup .amt {{
                font-weight: 800;
                color: #6B3FA0;
                font-size: 18px;
                line-height: 1.2;
                letter-spacing: 0.01em;
            }}
        </style>
    </head>
    <body>
        <div id="canvas-container"></div>
        <div id="labels-container"></div>
        <div id="pick-popup" class="pick-popup"></div>

        <script>
            const layoutData = {layout_json_str};
            // Read initial style map from parent bridge (set before this iframe loaded).
            // On subsequent reruns the bridge updates window.parent values; the polling
            // loop below picks them up WITHOUT reloading this iframe → camera is preserved.
            let roomStyleMap = (function() {{
                try {{ return window.parent.planwise_room_style_map || {{}}; }}
                catch(e) {{ return {{}}; }}
            }})();
            const mode = "{extrusion_mode}";
            const rooms = layoutData.costs ? layoutData.costs.rooms.rooms : layoutData.rooms;

            const scene = new THREE.Scene();
            scene.background = new THREE.Color('#ffffff');
            const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
            const renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            document.getElementById('canvas-container').appendChild(renderer.domElement);

            const controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.zoomSpeed    = 0.5;   // half default (1.0)
            controls.rotateSpeed  = 0.25;  // half default (0.5)
            controls.panSpeed     = 0.25;  // half default (0.5)
            controls.enableDamping = true;
            controls.dampingFactor = 0.08;

            scene.add(new THREE.AmbientLight(0xffffff, 0.55));
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
            dirLight.position.set(10, 20, 10);
            dirLight.castShadow = true;
            dirLight.shadow.mapSize.width = 2048;
            dirLight.shadow.mapSize.height = 2048;
            dirLight.shadow.camera.near = 0.5;
            dirLight.shadow.camera.far = 200;
            dirLight.shadow.bias = -0.0002;
            scene.add(dirLight);

            const fillLight = new THREE.DirectionalLight(0xffffff, 0.35);
            fillLight.position.set(-14, 14, -10);
            scene.add(fillLight);

            const labelsContainer = document.getElementById('labels-container');
            const pickPopup = document.getElementById('pick-popup');
            const labelObjects = [];
            const group = new THREE.Group();
            scene.add(group);
            const raycaster = new THREE.Raycaster();
            const mouse = new THREE.Vector2();
            let selectedMesh = null;

            function pickMeshAtEvent(event) {{
                const rect = renderer.domElement.getBoundingClientRect();
                mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
                mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
                raycaster.setFromCamera(mouse, camera);
                const hits = raycaster.intersectObjects(group.children, false);
                return hits.length ? hits[0].object : null;
            }}

            function roomKey(room, idx) {{
                return String(room.id || `idx_${{idx}}`);
            }}

            function getRoomCost(room) {{
                return Number(room.total_cost || room.total_cost_usd || room.cost || room.cost_usd || 0);
            }}

            function hidePopup() {{
                pickPopup.style.display = 'none';
            }}

            function showPopup(mesh, event) {{
                const d = mesh.userData || {{}};
                const amount = Number(d.cost || 0);
                const cur = d.currency || '';
                pickPopup.innerHTML = `
                    <div class="ttl">${{d.name || 'Space'}}</div>
                    <div style="font-size:11px;color:#6B6B9B;margin-bottom:4px">Total Cost</div>
                    <div class="amt">${{amount.toLocaleString()}} ${{cur}}</div>
                `;
                const margin = 12;
                const maxX = window.innerWidth - 220;
                const maxY = window.innerHeight - 100;
                const x = Math.max(margin, Math.min((event.clientX || 0) + 14, maxX));
                const y = Math.max(margin, Math.min((event.clientY || 0) + 14, maxY));
                pickPopup.style.left = `${{x}}px`;
                pickPopup.style.top = `${{y}}px`;
                pickPopup.style.display = 'block';
            }}

            Object.values(rooms).forEach((room, idx) => {{
                if (!room.polygon || room.polygon.length < 3) return;

                const rType = String(room.room_type || room.type || room.category || '').toLowerCase();
                const hideLabelTypes = ['door', 'window', 'column', 'columns'];
                const shouldLabel = !hideLabelTypes.includes(rType);

                const shape = new THREE.Shape();
                shape.moveTo(room.polygon[0][0], room.polygon[0][1]);
                for (let i = 1; i < room.polygon.length; i++) {{
                    shape.lineTo(room.polygon[i][0], room.polygon[i][1]);
                }}

                const key = roomKey(room, idx);
                const style = roomStyleMap[key] || {{}};
                const roomCost = Number(style.cost) || getRoomCost(room);
                let height = 3;
                if (mode === "skyline" && roomCost) {{
                    height = Math.max(1, roomCost / 10000);
                }}

                const extrudeSettings = {{ depth: height, bevelEnabled: false }};
                const geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);

                const finalColor = new THREE.Color(style.color_hex || room.color_hex || '#cccccc');

                const material = new THREE.MeshLambertMaterial({{
                    color: finalColor,
                    transparent: true,
                    opacity: 0.9,
                    emissive: new THREE.Color('#000000'),
                    emissiveIntensity: 0.25
                }});

                const mesh = new THREE.Mesh(geometry, material);
                mesh.rotation.x = -Math.PI / 2;
                mesh.castShadow = true;
                mesh.receiveShadow = true;
                mesh.userData = {{
                    id: key,
                    name: style.name || String(room.room_type || room.name || 'Room').replaceAll('_', ' '),
                    cost: Number(style.cost ?? roomCost ?? 0),
                    currency: style.currency || '',
                    originalHeight: height,
                }};
                group.add(mesh);

                geometry.computeBoundingBox();
                const center = new THREE.Vector3();
                geometry.boundingBox.getCenter(center);

                const labelPos = new THREE.Vector3(center.x, height + 0.5, -center.y);

                if (shouldLabel) {{
                    const labelDiv = document.createElement('div');
                    labelDiv.className = 'hologram-label';
                    const cleanName = String(style.label_name || room.room_type || room.name || 'Room').replaceAll('_', ' ');
                    labelDiv.innerHTML = `<span>${{cleanName}}</span>`;
                    labelsContainer.appendChild(labelDiv);

                    labelObjects.push({{ div: labelDiv, pos: labelPos, priority: roomCost || 0 }});
                }}
            }});

            const modelBox = new THREE.Box3().setFromObject(group);
            const modelSize = modelBox.getSize(new THREE.Vector3());
            modelBox.getCenter(controls.target);

            const gridSize = Math.max(modelSize.x, modelSize.z) * 1.35;
            const gridDivisions = Math.max(12, Math.round(gridSize / 2));
            const grid = new THREE.GridHelper(gridSize, gridDivisions, 0x94a3b8, 0xd1d5db);
            grid.position.set(controls.target.x, -0.02, controls.target.z);
            scene.add(grid);

            const groundGeo = new THREE.PlaneGeometry(gridSize * 1.1, gridSize * 1.1);
            const groundMat = new THREE.ShadowMaterial({{ opacity: 0.22 }});
            const ground = new THREE.Mesh(groundGeo, groundMat);
            ground.rotation.x = -Math.PI / 2;
            ground.position.set(controls.target.x, -0.03, controls.target.z);
            ground.receiveShadow = true;
            scene.add(ground);

            camera.position.set(controls.target.x + 15, 20, controls.target.z + 15);
            controls.update();

            renderer.domElement.addEventListener('pointermove', (event) => {{
                const mesh = pickMeshAtEvent(event);
                renderer.domElement.style.cursor = mesh ? 'pointer' : 'default';
                if (mesh) {{
                    showPopup(mesh, event);
                }} else if (!selectedMesh) {{
                    hidePopup();
                }}
            }});

            renderer.domElement.addEventListener('pointerleave', () => {{
                renderer.domElement.style.cursor = 'default';
                if (!selectedMesh) {{
                    hidePopup();
                }}
            }});

            renderer.domElement.addEventListener('pointerdown', (event) => {{
                const mesh = pickMeshAtEvent(event);

                if (!mesh) {{
                    if (selectedMesh && selectedMesh.material && selectedMesh.material.emissive) {{
                        selectedMesh.material.emissive.set('#000000');
                    }}
                    selectedMesh = null;
                    hidePopup();
                    return;
                }}
                if (selectedMesh && selectedMesh !== mesh && selectedMesh.material && selectedMesh.material.emissive) {{
                    selectedMesh.material.emissive.set('#000000');
                }}
                selectedMesh = mesh;
                if (mesh.material && mesh.material.emissive) {{
                    mesh.material.emissive.set('#213547');
                }}
                showPopup(mesh, event);
            }});

            function animate() {{
                requestAnimationFrame(animate);
                controls.update();

                // Simple screen-space collision culling to reduce label overlap.
                const occupied = [];
                const minDx = 90;
                const minDy = 24;
                const sorted = [...labelObjects].sort((a, b) => b.priority - a.priority);

                sorted.forEach(obj => {{
                    const vector = obj.pos.clone();
                    vector.project(camera);

                    const x = (vector.x * .5 + .5) * window.innerWidth;
                    const y = (vector.y * -.5 + .5) * window.innerHeight;

                    let show = (vector.z < 1 && vector.z > -1);
                    if (show) {{
                        for (const p of occupied) {{
                            if (Math.abs(p.x - x) < minDx && Math.abs(p.y - y) < minDy) {{
                                show = false;
                                break;
                            }}
                        }}
                    }}

                    if (show) {{
                        occupied.push({{ x, y }});
                        obj.div.style.display = 'block';
                        obj.div.style.left = `${{x}}px`;
                        obj.div.style.top = `${{y}}px`;
                    }} else {{
                        obj.div.style.display = 'none';
                    }}
                }});

                renderer.render(scene, camera);
            }}
            animate();

            window.addEventListener('resize', () => {{
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
                hidePopup();
            }});

            // ── Live cost update — polls parent for new roomStyleMap ──────────
            // Updates only building heights and colors; camera is never touched.
            let _lastCostVersion = null;
            setInterval(() => {{
                try {{
                    const p = window.parent;
                    const ver = p.planwise_cost_version;
                    if (!ver || ver === _lastCostVersion) return;
                    _lastCostVersion = ver;
                    const newMap = p.planwise_room_style_map;
                    if (!newMap) return;
                    group.children.forEach(mesh => {{
                        const d = mesh.userData || {{}};
                        if (!d.id || !d.originalHeight) return;
                        const s = newMap[d.id];
                        if (!s) return;
                        const newCost = Number(s.cost) || 0;
                        const newH = mode === "skyline" && newCost
                            ? Math.max(1, newCost / 10000)
                            : d.originalHeight;
                        // Scale along local Z (which is world Y after rotation.x = -PI/2)
                        mesh.scale.z = newH / d.originalHeight;
                        // Update fill color
                        if (s.color_hex) mesh.material.color.set(s.color_hex);
                        // Update hover popup data
                        d.cost = newCost;
                        d.currency = s.currency || d.currency;
                        d.name = s.name || d.name;
                    }});
                }} catch(e) {{}}
            }}, 600);
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=540)

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
        if not room.get("space_color_hex"):
            room["space_color_hex"] = room.get("color_hex") or room.get("color")

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
    label_mode: str = "all",
    color_mode: str = "heatmap",
) -> go.Figure:
    rooms    = layout.get("rooms", [])
    openings = layout.get("openings", [])
    columns  = layout.get("columns", [])
    proj = layout.get("project", {})
    # Handle case where project is a string instead of dict
    if isinstance(proj, str):
        proj = {}
    currency = proj.get("currency", "")

    def _safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    labor_mult = _safe_float(st.session_state.get("labor", 1.0), 1.0)
    inflation = 1 + (_safe_float(st.session_state.get("inflation", 0.0), 0.0) / 100.0)
    tax = _safe_float(st.session_state.get("carbon_tax", 0.0), 0.0)
    cur_factor = _safe_float(st.session_state.get("currency_factor", 1.0), 1.0)

    def _room_cost(room: dict) -> float:
        base_cost = _safe_float(
            room.get("total_cost")
            or room.get("total_cost_usd")
            or room.get("cost")
            or room.get("cost_usd")
            or 0
        )
        gwp = _safe_float(room.get("gwp"), 0.0)
        return ((base_cost * labor_mult * inflation) + (gwp * tax)) * cur_factor

    def _room_kind(room: dict) -> str:
        return (
            room.get("type")
            or room.get("room_type")
            or room.get("category")
            or ""
        ).strip().lower()

    def _norm_t(value: float, vals: list[float]) -> float:
        if not vals:
            return 0.0
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))

    # Gradient range should reflect room spaces only, not fixed-color components.
    gradient_rooms = [r for r in rooms if _room_kind(r) not in COMPONENT_COLOR_TYPES]
    stair_rooms = [r for r in rooms if _room_kind(r) in STAIR_TYPES]
    mep_rooms = [r for r in rooms if _room_kind(r) in MEP_TYPES]
    named_component_types = set(STAIR_TYPES) | set(MEP_TYPES) | {"lift", "elevator"}
    costs = [_room_cost(r) for r in gradient_rooms] if gradient_rooms else [_room_cost(r) for r in rooms]
    mn, mx = (min(costs), max(costs)) if costs else (0, 1)
    span = (mx - mn) or 1

    stair_costs = [_room_cost(r) for r in stair_rooms]
    mep_costs = [_room_cost(r) for r in mep_rooms]

    room_areas = [
        _safe_float(r.get("area_m2"), 0.0)
        for r in rooms
        if isinstance(r, dict)
    ]
    area_lo, area_hi = (min(room_areas), max(room_areas)) if room_areas else (0.0, 1.0)
    area_span = (area_hi - area_lo) or 1.0

    def _font_for_room(area_m2: float, base_small: int, base_large: int) -> int:
        rel = (_safe_float(area_m2, 0.0) - area_lo) / area_span
        rel = max(0.0, min(1.0, rel))
        return int(round(base_small + (base_large - base_small) * rel))

    # Avoid label collisions on very dense plans unless user forces all labels.
    dense_plan = len(rooms) > 120
    medium_plan = 60 < len(rooms) <= 120

    fig = go.Figure()

    for room in rooms:
        poly = room.get("polygon", [])
        if not poly:
            continue
        xs = [p[0] for p in poly] + [poly[0][0]]
        ys = [p[1] for p in poly] + [poly[0][1]]
        room_cost = _room_cost(room)
        t    = room.get("heat_t", (room_cost - mn) / span)
        
        # Determine color: use space type color for core elements, heat gradient for rooms
        room_type = _room_kind(room)
        is_component_room = room_type in COMPONENT_COLOR_TYPES
        room_geom_color = room.get("space_color_hex") or room.get("color_hex") or room.get("color")
        room_rgb = room.get("color_rgb")
        if not room_geom_color and isinstance(room_rgb, (list, tuple)) and len(room_rgb) >= 3:
            try:
                room_geom_color = _rgb_to_hex((int(room_rgb[0]), int(room_rgb[1]), int(room_rgb[2])))
            except (TypeError, ValueError):
                room_geom_color = None
        if color_mode == "space":
            fill = room_geom_color or _get_space_color(room_type, room.get("category", ""))
        elif room_type in STAIR_TYPES:
            stair_t = _norm_t(room_cost, stair_costs)
            fill = _interp_hex("#E8CDAA", "#8B4513", stair_t)
        elif room_type in MEP_TYPES:
            mep_t = _norm_t(room_cost, mep_costs)
            fill = _interp_hex("#D7D7D7", "#6A6A6A", mep_t)
        elif room_type in FIXED_COMPONENT_TYPES:
            # Use dedicated colors for infrastructure elements
            fill = _get_space_color(room_type, room_type)
        else:
            # Always use live heat gradient for room costs.
            fill = _lerp_color(t)
        
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
                room_cost, room.get("area_m2", 0),
                room.get("rate_per_m2", 0), room.get("category", ""),
            ]],
            hovertemplate=(
                f"<b>{room.get('name', '')}</b><br>"
                f"Area: {room.get('area_m2', 0):.1f} m²<br>"
                f"Rate: {room.get('rate_per_m2', 0):,.0f} {currency}/m²<br>"
                f"<b>Cost: {room_cost:,.0f} {currency}</b>"
                "<extra></extra>"
            ),
        ))
        # Invisible centroid marker — ensures hover fires anywhere inside the fill,
        # not just on the border line (Plotly fill hover is unreliable without this).
        fig.add_trace(go.Scatter(
            x=[cx], y=[cy],
            mode="markers",
            marker=dict(size=1, opacity=0, color=fill),
            showlegend=False,
            hovertemplate=(
                f"<b>{room.get('name', '')}</b><br>"
                f"Area: {room.get('area_m2', 0):.1f} m²<br>"
                f"Rate: {room.get('rate_per_m2', 0):,.0f} {currency}/m²<br>"
                f"<b>Cost: {room_cost:,.0f} {currency}</b>"
                "<extra></extra>"
            ),
            customdata=[[
                room.get("id", ""), "room", room.get("name", ""),
                room_cost, room.get("area_m2", 0),
                room.get("rate_per_m2", 0), room.get("category", ""),
            ]],
        ))
        
        # Add annotation with smart text sizing and density control.
        room_name = room.get('name', '')
        is_multi_apt = "(Apt" in room_name
        area_m2 = _safe_float(room.get("area_m2"), 0.0)
        font_size = _font_for_room(area_m2, 7, 12)
        if is_multi_apt:
            font_size = max(7, font_size - 1)

        # Labels are shown for rooms and key service components (stairs/lifts/mep).
        show_label = (not is_component_room) or (room_type in named_component_types)
        if label_mode == "off":
            show_label = False
        elif label_mode == "smart":
            if room_type in named_component_types:
                show_label = True
            elif dense_plan:
                # Only label high-value spaces in dense plans to keep text readable.
                show_label = room_cost >= (mn + span * 0.80)
                font_size = min(font_size, 8)
            elif medium_plan:
                # Label only more significant rooms in medium-density plans.
                show_label = room_cost >= (mn + span * 0.55)
                font_size = min(font_size, 9)
        else:
            # Force show all labels (room names visible for every room).
            font_size = max(7, min(font_size, 10 if dense_plan else 11))
        
        # Display clean room names only (no IDs/costs/codes).
        room_label = (
            room.get("room_type")
            or room.get("type")
            or room.get("category")
            or room_name
            or "Room"
        )
        room_label = _format_space_label(room_label)
        if room_type in named_component_types and room_name:
            room_label = _format_space_label(room_name)
        if room_label in {"Common", "Room"} and room_name:
            room_label = _format_space_label(str(room_name).split(" (Apt ")[0])

        if room_type in named_component_types:
            label_text = f"<b>{room_label}</b>"
        else:
            label_text = f"<b>{_compact_space_label(room_label)}</b>"
        
        if show_label:
            fig.add_annotation(
                x=cx, y=cy,
                text=label_text,
                showarrow=False,
                font=dict(size=font_size, color=_text_on(t)),
                align="center",
                bgcolor="rgba(255,255,255,0.18)" if label_mode == "all" else None,
            )

    for op in (openings + columns):
        poly = op.get("polygon", [])
        if not poly:
            continue
        ox = [p[0] for p in poly] + [poly[0][0]]
        oy = [p[1] for p in poly] + [poly[0][1]]
        op_type = (op.get("type") or op.get("category") or "").lower()
        op_geom_color = op.get("space_color_hex") or op.get("color_hex") or op.get("color")
        op_rgb = op.get("color_rgb")
        if not op_geom_color and isinstance(op_rgb, (list, tuple)) and len(op_rgb) >= 3:
            try:
                op_geom_color = _rgb_to_hex((int(op_rgb[0]), int(op_rgb[1]), int(op_rgb[2])))
            except (TypeError, ValueError):
                op_geom_color = None
        if color_mode == "space":
            fill = op_geom_color or _get_space_color(op_type, op_type)
            border = op_geom_color or "#4a4a4a"
        elif op_type in STAIR_TYPES:
            fill = _interp_hex("#E8CDAA", "#8B4513", 0.6)
            border = "#6B3510"
        elif op_type in MEP_TYPES:
            fill = _interp_hex("#D7D7D7", "#6A6A6A", 0.6)
            border = "#4F4F4F"
        elif op_type in FIXED_COMPONENT_TYPES:
            fill = _get_space_color(op_type, op_type)
            border = "#3d1a00" if "door" in op_type else "#0050b3" if "window" in op_type else "#444"
        else:
            fill = op.get("color_hex") or ("rgba(92,45,0,0.85)" if "door" in op_type else
                                            "rgba(30,144,255,0.55)" if "window" in op_type else
                                            "rgba(130,130,130,0.7)")
            border = op.get("color_hex") or ("#3d1a00" if "door" in op_type else
                                              "#0050b3" if "window" in op_type else "#444")
        _op_subtype = op.get("subtype") or op_type.capitalize()
        _op_cost    = op.get("cost", 0) or 0
        _op_poly    = op.get("polygon", [])
        _ocx = sum(p[0] for p in _op_poly) / len(_op_poly) if _op_poly else 0
        _ocy = sum(p[1] for p in _op_poly) / len(_op_poly) if _op_poly else 0
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
        # Invisible centroid marker for reliable fill hover on openings/columns.
        fig.add_trace(go.Scatter(
            x=[_ocx], y=[_ocy],
            mode="markers",
            marker=dict(size=1, opacity=0, color=fill),
            showlegend=False,
            hovertemplate=(
                f"<b>{op_type.capitalize()}</b> ({_op_subtype})<br>"
                f"Cost: {_op_cost:,.0f} {currency}<extra></extra>"
            ),
            customdata=[[
                op.get("id", ""), op_type, _op_subtype,
                _op_cost, 0, 0, "",
            ]],
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
        hovermode="closest",
        hoverdistance=20,
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.85)",
            font=dict(color="#1a1a2e", size=12, family="Segoe UI, Arial, sans-serif"),
            bordercolor="#9B6FD0",
            namelength=0,
        ),
    )
    if plot_height is not None:
        fig.update_layout(height=plot_height)
    return fig


# ── GH legend ────────────────────────────────────────────────────────────────
def build_gh_legend(layout: dict) -> str:
    heatmap  = layout.get("heatmap", {})
    ranges   = heatmap.get("ranges", {})
    ramps    = heatmap.get("ramps", {})
    proj = layout.get("project", {})
    if isinstance(proj, str):
        proj = {}
    currency = proj.get("currency", "")

    def _safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _el_cost(el: dict) -> float:
        return _safe_float(
            el.get("total_cost")
            or el.get("total_cost_usd")
            or el.get("cost")
            or el.get("cost_usd")
            or 0
        )

    labor_mult = _safe_float(st.session_state.get("labor", 1.0), 1.0)
    inflation = 1 + (_safe_float(st.session_state.get("inflation", 0.0), 0.0) / 100.0)
    tax = _safe_float(st.session_state.get("carbon_tax", 0.0), 0.0)
    cur_factor = _safe_float(st.session_state.get("currency_factor", 1.0), 1.0)

    def _adj_room_cost(room: dict) -> float:
        base = _el_cost(room)
        gwp = _safe_float(room.get("gwp"), 0.0)
        return ((base * labor_mult * inflation) + (gwp * tax)) * cur_factor

    def _adj_simple_cost(el: dict) -> float:
        return _el_cost(el) * cur_factor

    # If ranges are missing/empty (common in normalized plans), infer them from current data.
    def _is_missing_or_zero(cat: str) -> bool:
        r = ranges.get(cat, {}) if isinstance(ranges, dict) else {}
        lo = _safe_float(r.get("min", 0.0), 0.0)
        hi = _safe_float(r.get("max", 0.0), 0.0)
        return hi <= lo

    if any(_is_missing_or_zero(cat) for cat in ("rooms", "doors", "windows", "columns")):
        rooms = layout.get("rooms", [])
        openings = layout.get("openings", [])
        columns = layout.get("columns", [])

        room_vals = []
        stair_vals = []
        mep_vals = []
        door_vals = []
        window_vals = []
        column_vals = []

        for r in rooms:
            rtype = (r.get("type") or r.get("room_type") or r.get("category") or "").lower()
            if rtype == "door":
                door_vals.append(_adj_simple_cost(r))
            elif rtype == "window":
                window_vals.append(_adj_simple_cost(r))
            elif rtype == "column":
                column_vals.append(_adj_simple_cost(r))
            elif rtype in STAIR_TYPES:
                stair_vals.append(_adj_room_cost(r))
            elif rtype in MEP_TYPES:
                mep_vals.append(_adj_room_cost(r))
            elif rtype in COMPONENT_COLOR_TYPES:
                # Fixed-color components are not part of heat gradients.
                continue
            else:
                room_vals.append(_adj_room_cost(r))

        for op in openings:
            otype = (op.get("type") or op.get("category") or "").lower()
            if "door" in otype:
                door_vals.append(_adj_simple_cost(op))
            elif "window" in otype:
                window_vals.append(_adj_simple_cost(op))

        for c in columns:
            column_vals.append(_adj_simple_cost(c))

        inferred = {
            "rooms": {"min": min(room_vals) if room_vals else 0.0, "max": max(room_vals) if room_vals else 0.0},
            "stairs": {"min": min(stair_vals) if stair_vals else 0.0, "max": max(stair_vals) if stair_vals else 0.0},
            "mep": {"min": min(mep_vals) if mep_vals else 0.0, "max": max(mep_vals) if mep_vals else 0.0},
            "doors": {"min": min(door_vals) if door_vals else 0.0, "max": max(door_vals) if door_vals else 0.0},
            "windows": {"min": min(window_vals) if window_vals else 0.0, "max": max(window_vals) if window_vals else 0.0},
            "columns": {"min": min(column_vals) if column_vals else 0.0, "max": max(column_vals) if column_vals else 0.0},
        }
        if not isinstance(ranges, dict):
            ranges = {}
        ranges = {**inferred, **ranges}

    _fallback = {
        "rooms":   [("#FFF5DC",0),("#FED976",.25),("#FEB24C",.5),("#F06913",.75),("#BD0026",1)],
        "stairs":  [("#E8CDAA",0),("#B27A41",.5),("#8B4513",1)],
        "mep":     [("#D7D7D7",0),("#9E9E9E",.5),("#6A6A6A",1)],
        "doors":   [("#E8CDAA",0),("#B27A41",.5),("#643719",1)],
        "windows": [("#D2E8F0",0),("#5AA0CD",.5),("#194B91",1)],
        "columns": [("#C8C8C8",0),("#828282",.5),("#404040",1)],
    }
    blocks = []
    for cat in ("rooms", "stairs", "mep", "doors", "windows", "columns"):
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

    # Dedicated component colors: show each exactly once.
    _component_legend = [
        ("Lifts", _get_space_color("lift")),
    ]
    for title, color in _component_legend:
        blocks.append(f"""
<div style="margin-bottom:10px">
    <div style="font-size:0.72rem;color:#8a8784;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px">
        {title}<span style="font-weight:400;letter-spacing:0"> &nbsp;single color</span>
    </div>
    <div style="height:10px;border-radius:4px;background:{color};border:1px solid #e0dbd2"></div>
</div>""")
    return "\n".join(blocks)


# ── in-chart legend overlay ───────────────────────────────────────────────────
def _add_legend_to_figure(fig: go.Figure, layout: dict) -> None:
    """Overlay gradient color-scale bars inside the Plotly chart (top-right)."""
    heatmap  = layout.get("heatmap", {})
    ranges   = heatmap.get("ranges", {})
    ramps    = heatmap.get("ramps", {})
    proj = layout.get("project", {})
    if isinstance(proj, str):
        proj = {}
    currency = proj.get("currency", "")

    _fallback: dict[str, list[tuple[str, float]]] = {
        "rooms":   [("#FFF5DC", 0.00), ("#FED976", 0.25), ("#FEB24C", 0.50), ("#F06913", 0.75), ("#BD0026", 1.00)],
        "doors":   [("#E8CDAA", 0.00), ("#B27A41", 0.50), ("#643719", 1.00)],
        "windows": [("#D2E8F0", 0.00), ("#5AA0CD", 0.50), ("#194B91", 1.00)],
        "columns": [("#C8C8C8", 0.00), ("#828282", 0.50), ("#404040", 1.00)],
    }
    cats   = ["rooms", "doors", "windows", "columns"]
    N_SEGS = 20

    # Legend box in the top-right corner (paper coords: 0=plot-left, 1=plot-right)
    lx0, lx1 = 0.83, 0.995
    ly0, ly1 = 0.68, 0.992
    slot_h   = (ly1 - ly0) / len(cats)   # vertical space per category
    bar_h    = 0.022                       # bar thickness in paper units

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
            font=dict(size=7, color="#444444"),
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
            xanchor="left", yanchor="top", font=dict(size=6, color="#888888"),
        )
        fig.add_annotation(
            x=lx1, y=val_y, xref="paper", yref="paper",
            text=f"{hi:,.0f}", showarrow=False,
            xanchor="right", yanchor="top", font=dict(size=6, color="#888888"),
        )


# ── cost table ────────────────────────────────────────────────────────────────
def build_cost_df(layout: dict) -> pd.DataFrame:
    def safe_float(val, default=0.0):
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def as_items(value) -> list:
        if isinstance(value, dict):
            return list(value.values())
        if isinstance(value, list):
            return value
        return []

    def first_value(source: dict, keys: tuple[str, ...], default=None):
        attrs = source.get("attributes", {}) if isinstance(source.get("attributes"), dict) else {}
        for key in keys:
            value = source.get(key)
            if value is None:
                value = attrs.get(key)
            if value is not None:
                return value
        return default

    def source_collection(*paths: tuple[str, ...]) -> list:
        for path in paths:
            current = layout
            for part in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(part)
            items = as_items(current)
            if items:
                return items
        return []

    labor_mult = safe_float(st.session_state.get("labor", 1.0))
    inflation = 1 + (safe_float(st.session_state.get("inflation", 0)) / 100)
    tax = safe_float(st.session_state.get("carbon_tax", 0))
    proj = layout.get("project", {})
    if isinstance(proj, str):
        proj = {}
    cur_code = st.session_state.get("currency_code") or proj.get("currency", "AED")
    cur_factor = safe_float(st.session_state.get("currency_factor", 1.0), 1.0)
    
    rows = []

    # 1. Rooms/Spaces. Layouts arrive in both flat and nested cost schemas.
    rooms_source = source_collection(
        ("rooms",),
        ("costs", "rooms", "rooms"),
        ("costs", "rooms"),
    )
    explicit_openings = bool(as_items(layout.get("openings")))
    explicit_columns = bool(as_items(layout.get("columns")))

    for r in rooms_source:
        if not isinstance(r, dict):
            continue

        category_raw = str(first_value(r, ("category", "room_type", "type", "program"), "Zone") or "Zone")
        category_key = category_raw.strip().lower()
        if explicit_openings and category_key in {"door", "doors", "window", "windows"}:
            continue
        if explicit_columns and category_key in {"column", "columns"}:
            continue

        base_rate = safe_float(r.get("rate_per_m2") or r.get("rate_per_m2_usd") or r.get("rate"))
        base_cost = safe_float(first_value(r, ("total_cost", "total_cost_usd", "cost_usd", "cost", "total"), 0))
        area = safe_float(first_value(r, ("area_m2", "area"), 0))
        gwp = safe_float(first_value(r, ("gwp", "kgco2e", "carbon"), 0))

        if base_rate <= 0 and base_cost > 0 and area > 0:
            base_rate = base_cost / area
        if base_cost <= 0 and base_rate > 0 and area > 0:
            base_cost = base_rate * area

        is_simple_component = category_key in {"door", "doors", "window", "windows", "column", "columns"}
        calc_total = int(
            (base_cost * cur_factor)
            if is_simple_component
            else ((base_cost * labor_mult * inflation) + (gwp * tax)) * cur_factor
        )
        qty = "1 Unit" if is_simple_component and area <= 0 else f"{round(area, 1)} m²"
        rows.append({
            "Element": str(first_value(r, ("name", "id"), "Space") or "Space").title(), 
            "Category": category_raw.title(), 
            "Qty/Area": qty,
            f"Unit Rate ({cur_code})": int(base_rate * labor_mult * inflation * cur_factor), 
            f"Total Cost ({cur_code})": calc_total
        })
            
    # 2. Openings (Doors/Windows)
    openings_source = source_collection(
        ("openings",),
        ("costs", "openings", "openings"),
        ("costs", "openings"),
    )
    for o in openings_source:
        if not isinstance(o, dict):
            continue
        cost = safe_float(first_value(o, ("cost", "cost_usd", "total_cost", "total_cost_usd"), 0))
        calc_total = int(cost * labor_mult * inflation * cur_factor)
        rows.append({
            "Element": str(first_value(o, ("subtype", "name", "type", "id"), "Opening") or "Opening").title(), 
            "Category": str(first_value(o, ("type", "category"), "Opening") or "Opening").title(), 
            "Qty/Area": "1 Unit",
            f"Unit Rate ({cur_code})": calc_total, 
            f"Total Cost ({cur_code})": calc_total
        })
            
    # 3. Columns
    columns_source = source_collection(
        ("columns",),
        ("costs", "columns", "columns"),
        ("costs", "columns"),
    )
    for c in columns_source:
        if not isinstance(c, dict):
            continue
        cost = safe_float(first_value(c, ("cost", "cost_usd", "total_cost", "total_cost_usd"), 0))
        calc_total = int(cost * labor_mult * inflation * cur_factor)
        rows.append({
            "Element": str(first_value(c, ("name", "subtype", "id"), "Structural Column") or "Structural Column").title(), 
            "Category": "Structure", 
            "Qty/Area": "1 Unit",
            f"Unit Rate ({cur_code})": calc_total, 
            f"Total Cost ({cur_code})": calc_total
        })

    # Fallback if empty
    if not rows:
        rows.append({
            "Element": "Awaiting Calculation...", 
            "Category": "-", 
            "Qty/Area": "-",
            f"Unit Rate ({cur_code})": 0, 
            f"Total Cost ({cur_code})": 0
        })

    return pd.DataFrame(rows)


def render_cost_breakdown_table(layout: dict) -> None:
    """Render cost rows as plain HTML so Streamlit's dataframe canvas cannot appear blank."""
    import html

    df = build_cost_df(layout)
    if df.empty:
        st.info("No cost rows found in the current layout.")
        return

    st.caption(f"Showing {len(df):,} cost row{'s' if len(df) != 1 else ''}.")
    display_df = df.head(250).copy()
    total_rows = len(df)

    numeric_cols = [
        col for col in display_df.columns
        if "Cost" in str(col) or "Rate" in str(col)
    ]
    for col in numeric_cols:
        display_df[col] = display_df[col].map(
            lambda v: f"{float(v):,.0f}" if pd.notna(v) else ""
        )

    header_cells = "".join(
        f'<th style="padding:7px 10px;text-align:left;background:#faf9f6;'
        f'border-bottom:2px solid #e0dbd2;color:#6f6b66;font-size:0.68rem;'
        f'font-weight:700;text-transform:uppercase;letter-spacing:0.06em;'
        f'white-space:nowrap">{html.escape(str(col))}</th>'
        for col in display_df.columns
    )

    body_rows = []
    for idx, row in display_df.iterrows():
        bg = "#ffffff" if idx % 2 == 0 else "#fbfaf8"
        cells = "".join(
            f'<td style="padding:7px 10px;border-bottom:1px solid #eceae2;'
            f'font-size:0.82rem;color:#171717;white-space:nowrap">'
            f'{html.escape(str(value))}</td>'
            for value in row.tolist()
        )
        body_rows.append(f'<tr style="background:{bg}">{cells}</tr>')

    more_note = ""
    if total_rows > len(display_df):
        more_note = (
            f'<p style="margin:8px 0 0;color:#6f6b66;font-size:0.76rem">'
            f'Showing first {len(display_df):,} of {total_rows:,} rows.</p>'
        )

    st.markdown(
        f'<div style="max-height:270px;overflow:auto;border:1px solid #e0dbd2;'
        f'border-radius:8px;background:#fff">'
        f'<table style="width:100%;border-collapse:collapse;background:#fff">'
        f'<thead style="position:sticky;top:0;z-index:1"><tr>{header_cells}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>{more_note}',
        unsafe_allow_html=True,
    )


def build_cost_report_pdf(layout: dict) -> bytes:
    """Generate a compact PDF report with room cost table and element cost chart."""
    def _pdf_escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _simple_pdf(lines: list[str]) -> bytes:
        # Tiny single-page PDF generator (Helvetica font) as a dependency-free fallback.
        safe_lines = [str(x) for x in lines if x is not None]
        max_lines = 55
        safe_lines = safe_lines[:max_lines]

        parts = ["BT", "/F1 10 Tf", "40 800 Td"]
        for idx, line in enumerate(safe_lines):
            if idx > 0:
                parts.append("0 -14 Td")
            parts.append(f"({_pdf_escape(line)}) Tj")
        parts.append("ET")
        content = "\n".join(parts).encode("latin-1", errors="replace")

        objs = []
        objs.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
        objs.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
        objs.append(
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj\n"
        )
        objs.append(f"4 0 obj << /Length {len(content)} >> stream\n".encode("ascii") + content + b"\nendstream endobj\n")
        objs.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")

        out = io.BytesIO()
        out.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objs:
            offsets.append(out.tell())
            out.write(obj)

        xref_pos = out.tell()
        out.write(f"xref\n0 {len(objs) + 1}\n".encode("ascii"))
        out.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.write(f"{off:010d} 00000 n \n".encode("ascii"))
        out.write(
            (
                "trailer\n"
                f"<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
                "startxref\n"
                f"{xref_pos}\n"
                "%%EOF"
            ).encode("ascii")
        )
        return out.getvalue()

    df = build_cost_df(layout)
    proj = layout.get("project", {})
    if isinstance(proj, str):
        proj = {"name": proj}
    currency = st.session_state.get("currency_code") or proj.get("currency", "AED")

    openings = layout.get("openings", [])
    columns = layout.get("columns", [])
    doors = [o for o in openings if (o.get("type") or "").lower() == "door"]
    windows = [o for o in openings if (o.get("type") or "").lower() == "window"]

    room_total = float(df[df.columns[-1]].sum()) if not df.empty else 0.0
    door_total = float(sum((d.get("cost", 0) or 0) for d in doors))
    window_total = float(sum((w.get("cost", 0) or 0) for w in windows))
    column_total = float(sum((c.get("cost", 0) or 0) for c in columns))

    labels = ["Rooms", "Doors", "Windows", "Columns"]
    values = [room_total, door_total, window_total, column_total]

    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages

        buffer = io.BytesIO()
        with PdfPages(buffer) as pdf:
            fig1, ax1 = plt.subplots(figsize=(11.69, 8.27))
            ax1.axis("off")
            ax1.text(0.01, 0.97, "PlanWise Cost Report", fontsize=18, fontweight="bold", va="top")
            ax1.text(0.01, 0.92, f"Project: {proj.get('name', 'Unnamed Project')}", fontsize=11, va="top")
            ax1.text(
                0.01,
                0.885,
                f"Currency: {currency} | Rooms: {len(layout.get('rooms', []))} | Total: {sum(values):,.0f} {currency}",
                fontsize=11,
                va="top",
            )

            if not df.empty:
                table_df = df.sort_values(by=df.columns[-1], ascending=False).head(28).copy()
                for col in table_df.columns:
                    if "Cost" in col or "Rate" in col:
                        table_df[col] = table_df[col].map(lambda v: f"{float(v):,.0f}")
                table = ax1.table(
                    cellText=table_df.values,
                    colLabels=table_df.columns,
                    loc="upper left",
                    bbox=[0.01, 0.06, 0.98, 0.78],
                )
                table.auto_set_font_size(False)
                table.set_fontsize(8)
                table.scale(1, 1.1)
            else:
                ax1.text(0.01, 0.78, "No room cost rows found in layout.", fontsize=11)
            pdf.savefig(fig1, bbox_inches="tight")
            plt.close(fig1)

            fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))
            bars = ax2.bar(labels, values, color=["#f59e0b", "#b27a41", "#5aa0cd", "#828282"])
            ax2.set_title("Element Cost Breakdown", fontsize=16, pad=16)
            ax2.set_ylabel(f"Cost ({currency})")
            ax2.grid(axis="y", alpha=0.25)
            for bar, val in zip(bars, values):
                ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:,.0f}", ha="center", va="bottom", fontsize=10)
            pdf.savefig(fig2, bbox_inches="tight")
            plt.close(fig2)

        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        lines = [
            "PlanWise Cost Report",
            f"Project: {proj.get('name', 'Unnamed Project')}",
            f"Currency: {currency}",
            f"Rooms: {len(layout.get('rooms', []))}",
            f"Total (all elements): {sum(values):,.0f} {currency}",
            "",
            "Element totals:",
            f"- Rooms: {room_total:,.0f} {currency}",
            f"- Doors: {door_total:,.0f} {currency}",
            f"- Windows: {window_total:,.0f} {currency}",
            f"- Columns: {column_total:,.0f} {currency}",
            "",
            "Top room costs:",
        ]
        if not df.empty:
            room_col = "Element" if "Element" in df.columns else df.columns[0]
            cost_col = df.columns[-1]
            for _, row in df.sort_values(by=cost_col, ascending=False).head(30).iterrows():
                lines.append(f"- {row.get(room_col, 'Room')}: {float(row.get(cost_col, 0)):,.0f} {currency}")
        else:
            lines.append("- No room cost rows found.")
        return _simple_pdf(lines)


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


def _highlight_intent(user_text: str) -> bool:
    t = (user_text or "").lower()
    # tolerate common typos: hilight/highlite, hheat
    t = t.replace("highlite", "highlight").replace("hilight", "highlight").replace("hheat", "heat")
    has_highlight = any(k in t for k in ("highlight", "mark", "show", "point"))
    has_cost = any(k in t for k in ("costly", "expensive", "highest cost", "most cost", "most expensive"))
    has_target = any(k in t for k in ("heat map", "heatmap", "map", "area", "room", "space"))
    return has_highlight and has_cost and has_target


def _find_most_expensive_room(layout: dict) -> dict | None:
    rooms = (layout or {}).get("rooms", [])
    if not rooms:
        return None

    def _safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    labor_mult = _safe_float(st.session_state.get("labor", 1.0), 1.0)
    inflation = 1 + (_safe_float(st.session_state.get("inflation", 0.0), 0.0) / 100.0)
    tax = _safe_float(st.session_state.get("carbon_tax", 0.0), 0.0)
    cur_factor = _safe_float(st.session_state.get("currency_factor", 1.0), 1.0)

    best = None
    best_cost = -1.0
    for r in rooms:
        rtype = (r.get("type") or r.get("room_type") or r.get("category") or "").lower()
        if rtype in {"door", "window", "column", "columns"}:
            continue
        base = _safe_float(r.get("total_cost") or r.get("total_cost_usd") or r.get("cost") or r.get("cost_usd") or 0)
        gwp = _safe_float(r.get("gwp"), 0.0)
        c = ((base * labor_mult * inflation) + (gwp * tax)) * cur_factor
        if c > best_cost:
            best_cost = c
            best = r
    return best


def _set_selected_room_from_chat(room: dict, layout: dict) -> None:
    if not room:
        return
    poly = room.get("polygon", [])
    if poly:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
    else:
        cx, cy = 0.0, 0.0

    proj = (layout or {}).get("project", {})
    if isinstance(proj, str):
        proj = {}
    currency = proj.get("currency", "")

    st.session_state.selected_room = room
    st.session_state.selected_element = {
        "type": "room",
        "id": room.get("id", ""),
        "name": room.get("name") or room.get("room_type") or "Room",
        "cost": float(room.get("total_cost") or room.get("total_cost_usd") or room.get("cost") or room.get("cost_usd") or 0),
        "area": room.get("area_m2", 0),
        "rate": room.get("rate_per_m2", 0),
        "category": room.get("category", ""),
        "currency": currency,
        "cx": cx,
        "cy": cy,
    }


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

    # ── 3DM Rhino converter ───────────────────────────────────────────────────
    st.markdown('<p class="section-lbl">Import from Rhino (.3dm)</p>', unsafe_allow_html=True)
    _3dm_file = st.file_uploader(
        "Upload .3dm file",
        type=["3dm"],
        accept_multiple_files=False,
        label_visibility="collapsed",
        key="rhino_3dm_uploader",
        help="Reads rooms, doors, windows and columns directly from a Rhino 8 file. No script needed inside Rhino.",
    )
    if _3dm_file is not None:
        _3dm_uid = f"3dm::{_3dm_file.name}"
        if _3dm_uid not in st.session_state.get("_uploaded_ids", []):
            with st.spinner(f"Converting {_3dm_file.name} …"):
                try:
                    from rhino_converter import convert_3dm_bytes
                    _3dm_currency = st.session_state.get("currency_code", "AED")
                    _converted = convert_3dm_bytes(
                        _3dm_file.read(),
                        filename=_3dm_file.name,
                        currency=_3dm_currency,
                    )
                    _plan_key = Path(_3dm_file.name).stem
                    if len(st.session_state.layouts) >= 5:
                        st.warning("Maximum 5 plans loaded. Remove one before importing.")
                    else:
                        _converted = _normalize_layout_schema(_converted)
                        st.session_state.layouts[_plan_key] = _converted
                        if st.session_state.layout is None:
                            st.session_state.layout = _converted
                        st.session_state._uploaded_ids = list(
                            st.session_state.get("_uploaded_ids", [])
                        ) + [_3dm_uid]
                        n_rooms = len(_converted.get("rooms", []))
                        grand   = _converted.get("totals", {}).get("grand", 0)
                        cur     = _converted.get("project", {}).get("currency", "AED")
                        st.success(
                            f"✓ **{_plan_key}** imported — "
                            f"{n_rooms} rooms · {cur} {grand:,.0f} estimated"
                        )
                        # offer JSON download so user can save for later
                        st.download_button(
                            "⬇ Save as layout JSON",
                            data=json.dumps(_converted, indent=2),
                            file_name=f"{_plan_key}_layout.json",
                            mime="application/json",
                            key=f"dl_3dm_{_plan_key}",
                        )
                except ImportError:
                    st.error(
                        "**rhino3dm not installed.** Run once in your terminal:\n\n"
                        "```\npip install rhino3dm\n```\n\nthen restart Streamlit."
                    )
                except ValueError as _ve:
                    st.error(f"Conversion error: {_ve}")
                except Exception as _ex:
                    st.error(f"Unexpected error: {_ex}")

    # 1. Global Sensitivity Engine
    st.markdown('<p class="section-lbl">Sensitivity Engine</p>', unsafe_allow_html=True)
    st.slider("Labor Cost Multiplier", 0.8, 1.5, 1.0, 0.05, key="labor")
    st.slider("Material Inflation (%)", 0, 20, 0, 1, key="inflation")
    # st.slider("Carbon Tax ($/tCO2e)", 0, 200, 0, 5, key="carbon_tax")

    st.session_state.sensitivity = {
        "labor": st.session_state.labor,
        "inflation": 1 + (st.session_state.inflation / 100),
        # "carbon_tax": st.session_state.carbon_tax
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
                
                # Handle nested rooms structure (canonical_unit.rooms → flatten to root)
                if "rooms" not in loaded_layout and "canonical_unit" in loaded_layout:
                    if "rooms" in loaded_layout["canonical_unit"]:
                        canonical_rooms = loaded_layout["canonical_unit"]["rooms"]
                        proj = loaded_layout.get("project", {})
                        if isinstance(proj, str):
                            proj = {}
                        num_apartments = proj.get("units_per_floor", 1)
                        layout_meta = loaded_layout.get("layout", {})
                        apartments_info = layout_meta.get("apartments", [])
                        
                        canonical_columns = loaded_layout.get("canonical_unit", {}).get("columns", [])
                        canonical_openings = loaded_layout.get("canonical_unit", {}).get("openings", [])
                        canonical_core = loaded_layout.get("core", {})
                        
                        # Expand rooms, columns, and openings for all apartments with geometric transformation
                        expanded_rooms = []
                        expanded_columns = []
                        expanded_openings = []
                        
                        # Define apartment positions for non-overlapping pinwheel layout (in meters)
                        # Core is at approximately (7, 7.5), units are 14m x 11m
                        apt_positions = {
                            "apt_SW": (0, 0, 0, False),            # Southwest: origin, no rotation
                            "apt_SE": (15, 0, 270, False),         # Southeast: x offset, -90° rotation
                            "apt_NE": (15, 15, 180, False),       # Northeast: x,y offset, 180° rotation
                            "apt_NW": (0, 15, 90, False),         # Northwest: y offset, 90° rotation
                            "apt_N": (7, 26, 0, False),           # North: centered x, far y offset, no rotation
                        }
                        
                        for apt_idx in range(num_apartments):
                            apt_info = apartments_info[apt_idx] if apt_idx < len(apartments_info) else {}
                            apt_id = apt_info.get("apt_id", f"apt_{apt_idx}")
                            
                            # Get transformation data
                            if apt_id in apt_positions:
                                offset_x, offset_y, rotation_deg, mirror = apt_positions[apt_id]
                            else:
                                offset_x, offset_y, rotation_deg, mirror = 0, 0, 0, False
                            
                            # Transform rooms
                            for room in canonical_rooms:
                                room_copy = room.copy()
                                
                                # Transform polygon coordinates
                                if room_copy.get("polygon"):
                                    room_copy["polygon"] = _transform_polygon(
                                        room_copy["polygon"],
                                        rotation_deg,
                                        mirror,
                                        offset_x,
                                        offset_y
                                    )
                                
                                # Create unique ID and name for each apartment's room
                                room_copy["id"] = f"{room.get('id')}_apt{apt_idx+1}"
                                room_copy["name"] = f"{room.get('name')} (Apt {apt_idx+1})"
                                expanded_rooms.append(room_copy)
                            
                            # Transform columns
                            for col in canonical_columns:
                                col_copy = col.copy()
                                if col_copy.get("polygon"):
                                    col_copy["polygon"] = _transform_polygon(
                                        col_copy["polygon"],
                                        rotation_deg,
                                        mirror,
                                        offset_x,
                                        offset_y
                                    )
                                col_copy["id"] = f"{col.get('id')}_apt{apt_idx+1}"
                                expanded_columns.append(col_copy)
                            
                            # Transform openings (doors, windows)
                            for opening in canonical_openings:
                                op_copy = opening.copy()
                                if op_copy.get("polygon"):
                                    op_copy["polygon"] = _transform_polygon(
                                        op_copy["polygon"],
                                        rotation_deg,
                                        mirror,
                                        offset_x,
                                        offset_y
                                    )
                                op_copy["id"] = f"{opening.get('id')}_apt{apt_idx+1}"
                                expanded_openings.append(op_copy)
                        
                        # Add expanded data back to layout
                        loaded_layout["rooms"] = expanded_rooms
                        if expanded_columns:
                            loaded_layout["columns"] = expanded_columns
                        if expanded_openings:
                            loaded_layout["openings"] = expanded_openings
                        
                        # Add central core (shared, not repeated per apartment)
                        # Extract individual core components (lifts, stairs, MEP, etc.)
                        if canonical_core:
                            core_components = canonical_core.get("components", [])
                            core_cost_total = canonical_core.get("cost_estimate", 0)
                            
                            # Group components by type for cost distribution
                            component_types = {}
                            for comp in core_components:
                                comp_type = comp.get("type", "unknown")
                                if comp_type not in component_types:
                                    component_types[comp_type] = []
                                component_types[comp_type].append(comp)
                            
                            # Create rooms for each component or group
                            core_x_positions = [6.2, 7.8, 6.2, 7.8]  # For 4 corners
                            core_y_positions = [6.2, 6.2, 8.8, 8.8]
                            comp_idx = 0
                            
                            for comp_type, comps in component_types.items():
                                for i, comp in enumerate(comps):
                                    # Estimate cost per component
                                    comp_cost = core_cost_total / len(core_components) if core_components else 0
                                    
                                    # Generate polygon for component
                                    x_pos = core_x_positions[min(i, len(core_x_positions)-1)]
                                    y_pos = core_y_positions[min(i, len(core_y_positions)-1)]
                                    polygon = _generate_component_polygon(comp, x_pos, y_pos)
                                    
                                    core_item = {
                                        "id": f"core_{comp_type}_{i}",
                                        "name": f"{comp_type.title()} {i+1}" if comp_type != "lift" else f"Lift {i+1}",
                                        "category": comp_type,
                                        "type": comp_type,
                                        "area_m2": comp.get("width_m", 2.0) * comp.get("depth_m", 2.0),
                                        "polygon": polygon,
                                        "rate_per_m2": 3500,  # MEP rates
                                        "total_cost": comp_cost
                                    }
                                    expanded_rooms.append(core_item)
                                    comp_idx += 1
                            
                            # If no components listed, add a general core placeholder
                            if not core_components:
                                core_room = {
                                    "id": "core_central",
                                    "name": "Core (Central)",
                                    "category": "core",
                                    "area_m2": canonical_core.get("area_m2", 80),
                                    "polygon": [[6, 6], [9, 6], [9, 9], [6, 9]],
                                    "rate_per_m2": 5000,
                                    "total_cost": canonical_core.get("cost_estimate", 280000)
                                }
                                expanded_rooms.append(core_room)
                
                loaded_layout = _normalize_layout_schema(loaded_layout)

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
        # Handle case where project is a string instead of dict
        if isinstance(proj, str):
            proj = {"name": proj}
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
col_main, col_panel = st.columns([6, 3], gap="large")

# ── LEFT: Heatmap + Chat (top row) | Cost Table (bottom) ─────────────────────
with col_main:
    st.markdown('<p class="section-lbl">Floor Plan · Cost Analysis</p>', unsafe_allow_html=True)
    if st.session_state.layout:

        # ── HEATMAP PANEL (full width of main column) ────────────────────────
        with st.container():
            st.markdown('<p class="section-lbl">Cost Heatmap</p>', unsafe_allow_html=True)

            ctl_view, ctl_color, ctl_labels = st.columns([1.55, 1.45, 1.05], gap="small")

            with ctl_view:
                view_mode = st.radio(
                    "Visualization Mode",
                    ["2D Flat Floorplan", "Interactive 3D Skyline"],
                    horizontal=True,
                    key="view_mode_main",
                )

            with ctl_color:
                _color_mode_ui = st.radio(
                    "Color Mode",
                    ["Heatmap colors", "Space-type colors"],
                    horizontal=True,
                    key="color_mode_main",
                )

            with ctl_labels:
                if "3D" in view_mode:
                    st.markdown("<div style='height:0.15rem'></div>", unsafe_allow_html=True)
                    st.caption("Room labels apply to 2D")
                    _label_mode = "smart"
                else:
                    _label_mode_ui = st.radio(
                        "Room labels",
                        options=["All names", "Smart", "Off"],
                        horizontal=True,
                        key="room_label_mode_main",
                    )
                    _label_mode = (
                        "all" if _label_mode_ui == "All names" else
                        "smart" if _label_mode_ui == "Smart" else
                        "off"
                    )

            _color_mode = "space" if _color_mode_ui == "Space-type colors" else "heatmap"

            if "3D" in view_mode:
                st.caption("Drag to rotate, scroll to zoom. Z-height represents total room cost.")
                render_3d_heatmap(st.session_state.layout, "skyline", color_mode=_color_mode)
            else:
                st.caption("Colors from Grasshopper. Click a room to select it. Use mouse wheel or modebar to zoom.")

                sel_id = (st.session_state.selected_room or {}).get("id")
                fig    = build_floor_plan(
                    st.session_state.layout,
                    sel_id,
                    plot_height=560,
                    label_mode=_label_mode,
                    color_mode=_color_mode,
                )
                floor_plan_config = {
                    "scrollZoom": True,
                    "displayModeBar": True,
                    "displaylogo": False,
                    "doubleClick": "reset",
                }

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
                        on_select="rerun", key="floor_plan_chart", config=floor_plan_config,
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
                                proj = (st.session_state.layout or {}).get("project", {})
                                if isinstance(proj, str):
                                    proj = {}
                                currency = proj.get("currency", "")

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
                                            "cost": el_cost,
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
                    st.plotly_chart(fig, use_container_width=True, config=floor_plan_config)

                # HTML legend overlaid in the top-right corner of the chart via CSS negative margin
                st.markdown(
                    '<div class="chart-legend-wrap"><div class="chart-legend-overlay">'
                    + build_gh_legend(st.session_state.layout)
                    + "</div></div>",
                    unsafe_allow_html=True,
                )

            # Element info panel — appears below chart when any element is clicked
            _render_element_panel()

            st.markdown("<h3 style='margin-top:1rem;'>Cost Breakdown</h3>", unsafe_allow_html=True)
            render_cost_breakdown_table(st.session_state.layout)

        # ── Cost Matching results — always below the floor plan ───────────────
        _cm_res_blw   = st.session_state.get("cm_result")
        _active_tab_b = st.session_state.get("active_tab", "")
        if "Cost Matching" in _active_tab_b and _cm_res_blw:
            _cur_b   = (st.session_state.layout.get("project") or {}).get("currency", "AED")
            _sugg_b  = _cm_res_blw.get("suggestions", [])
            _pct_b   = _cm_res_blw.get("match_pct", 0)
            _adj_b   = _cm_res_blw.get("adjusted_total", 0)
            _tgt_b   = _cm_res_blw.get("target", 0)
            st.divider()
            st.markdown("### Cost Matching — Results")
            _mk1, _mk2, _mk3, _mk4 = st.columns(4)
            _mk1.metric("Target",         f"{_tgt_b:,.0f} {_cur_b}")
            _mk2.metric("Adjusted total", f"{_adj_b:,.0f} {_cur_b}",
                        delta=f"{_adj_b - _cm_res_blw.get('current_grand', 0):+,.0f}")
            _mk3.metric("Gap remaining",  f"{abs(_tgt_b - _adj_b):,.0f} {_cur_b}")
            _mk4.metric("Similarity",     f"{_pct_b:.1f}%",
                        delta="On target" if _pct_b >= 99 else "Approx match")
            _bc_b = "#10b981" if _pct_b >= 90 else "#f59e0b" if _pct_b >= 70 else "#ef4444"
            st.markdown(
                f'<div style="background:#e0dbd2;border-radius:6px;height:10px;margin:4px 0 14px">'
                f'<div style="background:{_bc_b};width:{min(_pct_b,100):.1f}%;height:100%;border-radius:8px"></div></div>',
                unsafe_allow_html=True,
            )

            # ── Before vs After chart — shown FIRST, above the table ─────────
            _all_r_b = st.session_state.layout.get("rooms", [])
            _rn_b    = [r.get("name", "") for r in _all_r_b]
            _oc_b    = [r.get("total_cost", 0) or 0 for r in _all_r_b]
            _am_b    = {r.get("name"): r.get("total_cost", 0) or 0 for r in _all_r_b}
            for _s in (_sugg_b or []):
                _am_b[_s["room"]] = _s["new_room_total"]
            _ac_b = [_am_b.get(n, 0) for n in _rn_b]
            _bf2 = go.Figure()
            _bf2.add_trace(go.Bar(
                name="Original cost",
                x=_rn_b, y=_oc_b,
                marker_color="#1245A8",
                opacity=0.9,
            ))
            _bf2.add_trace(go.Bar(
                name="After matching",
                x=_rn_b, y=_ac_b,
                marker_color="#C85A00",
                opacity=0.9,
            ))
            _bf2.update_layout(
                barmode="group",
                height=340,
                margin=dict(l=10, r=10, t=10, b=90),
                paper_bgcolor="#ffffff",
                plot_bgcolor="#f5f2ed",
                font=dict(color="#111111"),
                xaxis=dict(tickangle=-45, tickfont=dict(size=8, color="#555")),
                yaxis=dict(
                    title=dict(text=_cur_b, font=dict(color="#111111")),
                    tickfont=dict(color="#111111"),
                    gridcolor="#e0dbd2",
                ),
                legend=dict(
                    orientation="h", y=1.06, x=0,
                    font=dict(size=12, color="#111111"),
                    bgcolor="rgba(0,0,0,0)",
                ),
                bargap=0.15, bargroupgap=0.05,
            )
            st.plotly_chart(_bf2, use_container_width=True,
                            config={"displaylogo": False}, key="cm_ba_grouped")

            if not _sugg_b:
                st.success("Plan is already at your target — no changes needed.")
            else:
                st.markdown(
                    f"#### Suggested finish changes &nbsp;·&nbsp; "
                    f"<span style='color:#10b981;font-weight:700'>"
                    f"{len(_sugg_b)} adjustment{'s' if len(_sugg_b)!=1 else ''}</span>",
                    unsafe_allow_html=True,
                )
                _th_b = "".join(
                    f'<th style="padding:7px 12px;text-align:left;background:#faf9f6;'
                    f'border-bottom:2px solid #e0dbd2;white-space:nowrap;font-size:0.68rem;'
                    f'font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#8a8784">{h}</th>'
                    for h in ["Room","Surface","From",f"Rate ({_cur_b}/m²)","To",
                              f"Rate ({_cur_b}/m²)","Area m²",f"Delta ({_cur_b})",
                              f"New room total ({_cur_b})"]
                )
                _rows_b = ""
                for _i, _s in enumerate(_sugg_b):
                    _bg_b = "#ffffff" if _i % 2 == 0 else "#f9f9f9"
                    _d_b  = _s["delta_cost"]
                    _dc_b = "#ef4444" if _d_b > 0 else "#10b981"
                    def _tdb(v, bold=False, color=None,
                             _bs="padding:6px 12px;white-space:nowrap;font-size:0.82rem;"):
                        if color: _bs += f"color:{color};"
                        if bold:  _bs += "font-weight:600;"
                        return f'<td style="{_bs}">{v}</td>'
                    _rows_b += (
                        f'<tr style="background:{_bg_b}">'
                        + _tdb(_s["room"], bold=True)
                        + _tdb(_s["surface"].capitalize())
                        + _tdb(_s["from_material"])
                        + _tdb(f"{_s['from_rate']:,.0f}")
                        + _tdb(f"<b>{_s['to_material']}</b>", bold=True)
                        + _tdb(f"{_s['to_rate']:,.0f}", bold=True)
                        + _tdb(f"{_s['area']:.1f}")
                        + _tdb(f"{_d_b:+,.0f}", bold=True, color=_dc_b)
                        + _tdb(f"{_s['new_room_total']:,.0f}", bold=True)
                        + "</tr>"
                    )
                st.markdown(
                    f'<div style="overflow-x:auto;border:1px solid #e0dbd2;border-radius:8px">'
                    f'<table style="width:100%;border-collapse:collapse">'
                    f'<thead><tr>{_th_b}</tr></thead><tbody>{_rows_b}</tbody></table></div>',
                    unsafe_allow_html=True,
                )
                _tot_b = sum(_s["delta_cost"] for _s in _sugg_b)
                st.markdown(
                    f'<p style="margin-top:8px;font-size:12px;color:#555">'
                    f'Total adjustment: <b style="color:{"#ef4444" if _tot_b > 0 else "#10b981"}">'
                    f'{_tot_b:+,.0f} {_cur_b}</b> across {len(_sugg_b)} room{"s" if len(_sugg_b)!=1 else ""}.</p>',
                    unsafe_allow_html=True,
                )


    else:
        st.info("Upload a layout in the sidebar to see the heatmap.")



# ── RIGHT: Vertical tab navigation ───────────────────────────────────────────
with col_panel:
    st.markdown('<p class="section-lbl">Agent Chat</p>', unsafe_allow_html=True)
    if st.session_state.selected_plan_key:
        st.caption(f"Active: {st.session_state.selected_plan_key}")

    chat_area = st.container(height=380, key="agent_chat_scroll_area")
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

    if user_text and user_text.strip() and st.session_state.layout is not None:
        _clean_user_text = user_text.strip()
        _wants_highlight = _highlight_intent(_clean_user_text)
        st.session_state.messages.append({"role": "user", "content": _clean_user_text})
        with chat_area:
            with st.chat_message("user"):
                st.markdown(_clean_user_text)
            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("_Thinking..._")
        reply = None
        gh_synced = False
        try:
            reply = st.session_state.agent.process(
                _clean_user_text,
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

            # Make highlight prompt actionable by selecting the highest-cost room on the map.
            if _wants_highlight and st.session_state.layout is not None:
                _target_room = _find_most_expensive_room(st.session_state.layout)
                if _target_room is not None:
                    _set_selected_room_from_chat(_target_room, st.session_state.layout)
                    if reply:
                        reply += "\n\nHighlighted on heatmap: **" + str(_target_room.get("name") or _target_room.get("id") or "room") + "**."
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

    st.divider()

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
            proj = _cm_layout.get("project", {})
            if isinstance(proj, str):
                proj = {}
            _cm_currency = proj.get("currency", "USD")
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
                    st.info(
                        f"**{len(_sugg)} adjustment{'s' if len(_sugg)!=1 else ''}** suggested — "
                        f"see the full table in the main area on the left ↙",
                        icon="📋",
                    )

                st.caption("Full table and before/after chart are shown in the main area ↙")

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

                proj = st.session_state.layout.get("project", {})
                if isinstance(proj, str):
                    proj = {}
                _currency = proj.get("currency", "")
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
