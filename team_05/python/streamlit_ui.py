"""
AIA Studio Cost Advisor — Team 05
Streamlit GUI: interactive floor-plan cost heatmap + agent chat.

Run with:  streamlit run streamlit_ui.py
Requires:  streamlit>=1.33, plotly, pandas
"""
import copy
import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from langgraph_agent import LangGraphAgent

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AIA Cost Advisor — Team 05",
    page_icon="🏗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* main background white, text dark */
.stApp { background: #ffffff; color: #111111; }
.stApp * { color: #111111 !important; }
section[data-testid="stSidebar"] { background: #f0f0f0; border-right: 1px solid #dddddd; }
/* sidebar text */
section[data-testid="stSidebar"] * { color: #111111 !important; }
/* headings */
h1, h2, h3, h4, h5 { color: #111111 !important; }
/* metric labels and values */
[data-testid="stMetricLabel"] { color: #111111 !important; }
[data-testid="stMetricValue"] { color: #111111 !important; }
/* divider */
hr { border-color: #dddddd; }
/* remove dark backgrounds from buttons and input surfaces */
.stButton > button,
button[kind="secondary"],
button[kind="primary"],
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-primary"] {
    background: #f2f2f2 !important;
    color: #111111 !important;
    border: 1px solid #cccccc !important;
}
/* uploader area */
[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzone"] * {
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #cccccc !important;
}
/* chat input container and controls */
[data-testid="stChatInput"] {
    background: #ffffff !important;
    border: 1px solid #cccccc !important;
    border-radius: 10px;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] section {
    background: #ffffff !important;
}
[data-testid="stChatInput"] button {
    background: #f2f2f2 !important;
    color: #111111 !important;
    border: 1px solid #cccccc !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="input"] input {
    background: #ffffff !important;
    color: #111111 !important;
    border: 1px solid #cccccc !important;
}
/* chat bubbles */
[data-testid="stChatMessageContent"] {
    background: #f7f7f7 !important;
    color: #111111 !important;
    border: 1px solid #dddddd !important;
    border-radius: 8px;
}
/* expander + dataframe/table surfaces */
[data-testid="stExpander"] details,
[data-testid="stExpander"] summary,
[data-testid="stDataFrame"],
[data-testid="stDataFrame"] *,
[data-testid="stTable"],
[data-testid="stTable"] * {
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #dddddd !important;
}
/* room card */
.room-card { background: #f7f7f7; border: 1px solid #ddd;
             border-radius: 10px; padding: 0.85rem 1rem; margin-top: 0.5rem; }
.room-card h4 { margin: 0 0 0.5rem 0; color: #1a1a1a; }
.kv-row { display: flex; justify-content: space-between;
          border-bottom: 1px solid #e5e5e5; padding: 0.2rem 0; font-size: 0.88rem; }
.kv-key { color: #666; }
.kv-val { color: #111; font-weight: 600; }
/* caption / small text */
.stCaption, small { color: #666 !important; }
/* selectbox — active plan dropdown */
[data-baseweb="select"] > div,
[data-baseweb="select"] [data-testid="stSelectboxVirtualDropdown"],
[data-baseweb="popover"] ul,
[data-baseweb="popover"] li {
    background: #e8e8e8 !important;
    color: #111111 !important;
    border-color: #cccccc !important;
}
[data-baseweb="select"] svg { fill: #555555 !important; }
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
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── helpers ───────────────────────────────────────────────────────────────────

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
            line=dict(color="#60a5fa" if is_sel else "#555", width=3 if is_sel else 1),
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

    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#ffffff", plot_bgcolor="#f7f7f7",
        xaxis=dict(showgrid=False, zeroline=False, scaleanchor="y",
                   scaleratio=1, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
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
  <div style="font-size:0.78rem;color:#555;margin-bottom:3px">
    {cat.capitalize()} ({lo:,.0f}–{hi:,.0f} {currency})
  </div>
  <div style="height:14px;border-radius:4px;background:{grad};border:1px solid #ccc"></div>
  <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:#888;margin-top:2px">
    <span>{lo:,.0f}</span><span>{hi:,.0f}</span>
  </div>
</div>""")
    return "\n".join(blocks)


# ── cost table ────────────────────────────────────────────────────────────────
def build_cost_df(layout: dict) -> pd.DataFrame:
    currency = layout.get("project", {}).get("currency", "")
    rows = [{"Room": r.get("name",""), "Category": r.get("category","").capitalize(),
             "Area (m²)": round(r.get("area_m2",0),1),
             f"Rate ({currency}/m²)": int(r.get("rate_per_m2",0)),
             f"Cost ({currency})": int(r.get("total_cost",0))}
            for r in layout.get("rooms", [])]
    df = pd.DataFrame(rows)
    if not df.empty:
        currency = layout.get("project", {}).get("currency", "")
        totals = {"Room":"TOTAL","Category":"","Area (m²)":df["Area (m²)"].sum(),
                  f"Rate ({currency}/m²)":0,
                  f"Cost ({currency})":df[f"Cost ({currency})"].sum()}
        df = pd.concat([df, pd.DataFrame([totals])], ignore_index=True)
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
        f'<div style="background:#f0f4ff;border:1.5px solid #4a90d9;border-radius:10px;'
        f'padding:0.7rem 1rem 0.2rem 1rem;margin-bottom:0">'
        f'<span style="font-size:0.78rem;color:#4a90d9;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.05em">{etype.capitalize()}</span>'
        f'<h4 style="margin:0 0 0.6rem 0;color:#1a1a2e">{name}</h4>',
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
        if el.get("category"):
            st.caption(f"Category · {el['category'].capitalize()}")
        if st.button("Ask agent about this room", key="ask_agent_panel", use_container_width=True):
            st.session_state.pending_prompt = (
                f"Analyse the cost of the {name} "
                f"({el.get('area', 0):.1f} m² at "
                f"{el.get('rate', 0):,.0f} {currency}/m²). "
                "How does it compare to similar rooms and how could it be reduced?"
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


# =============================================================================
# SIDEBAR — layout upload is the ONLY source of truth for the layout
# =============================================================================
with st.sidebar:
    st.markdown("### Load Layouts")
    st.caption("Upload up to 5 layout JSON files, keep them, and choose which one to analyze.")
    uploads = st.file_uploader(
        "Layout JSON files",
        type=["json"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploads:
        uploaded_ids = set(st.session_state._uploaded_ids)
        added_count = 0
        failed_names: list[str] = []
        for uploaded in uploads:
            file_uid = getattr(uploaded, "file_id", uploaded.name)
            if file_uid in uploaded_ids:
                continue
            if len(st.session_state.layouts) >= 5:
                st.warning("Maximum 5 plans can be saved at once.")
                break
            try:
                loaded_layout = json.load(uploaded)
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

    if st.session_state.layouts:
        plan_keys = list(st.session_state.layouts.keys())
        selected_key = st.session_state.selected_plan_key
        if selected_key not in st.session_state.layouts:
            selected_key = plan_keys[0]
            st.session_state.selected_plan_key = selected_key

        selected_idx = plan_keys.index(selected_key)
        chosen_key = st.selectbox("Active plan", options=plan_keys, index=selected_idx)
        if chosen_key != st.session_state.selected_plan_key:
            st.session_state.selected_plan_key = chosen_key
            st.session_state.selected_room = None
            st.session_state.pending_prompt = ""

        st.session_state.layout = st.session_state.layouts[st.session_state.selected_plan_key]

        proj     = st.session_state.layout.get("project", {})
        rooms    = st.session_state.layout.get("rooms", [])
        currency = proj.get("currency", "")
        totals   = st.session_state.layout.get("totals", {})
        room_total = totals.get("rooms", sum(r.get("total_cost",0) for r in rooms))
        grand      = totals.get("grand", room_total)

        st.markdown(f"**{proj.get('name','')}**")
        c1, c2 = st.columns(2)
        c1.metric("Rooms", len(rooms))
        c2.metric("Footprint", f"{proj.get('footprint_m2',0):.0f} m²")
        st.metric("Room construction", f"{room_total:,.0f} {currency}")
        if grand != room_total:
            st.metric("Grand total", f"{grand:,.0f} {currency}")

        st.divider()
        st.markdown("### Grasshopper")
        if st.button("Check connection", use_container_width=True):
            from swiftlet_mcp import check_connection
            ok, info = check_connection()
            if ok:
                st.success(f"Connected — {len(info.split(','))} tools")
            else:
                st.error(f"Not reachable: {info[:80]}")

        if st.button("Analyze All Saved Plans", use_container_width=True):
            from swiftlet_mcp import push_layout_to_grasshopper
            updated_counter = 0
            with st.spinner("Analyzing all saved plans via Grasshopper..."):
                for name, layout in list(st.session_state.layouts.items()):
                    try:
                        result = push_layout_to_grasshopper(layout)
                        if result.get("ok") and result.get("gh_layout"):
                            st.session_state.layouts[name] = _merge_gh_colors(layout, result["gh_layout"])
                            updated_counter += 1
                    except Exception:
                        pass

            st.session_state.layout = st.session_state.layouts.get(
                st.session_state.selected_plan_key,
                st.session_state.layout,
            )
            st.success(f"Analyzed {updated_counter} / {len(st.session_state.layouts)} plans.")

        if st.button("Remove Active Plan", use_container_width=True):
            key_to_remove = st.session_state.selected_plan_key
            if key_to_remove in st.session_state.layouts:
                st.session_state.layouts.pop(key_to_remove)
                if st.session_state.layouts:
                    st.session_state.selected_plan_key = next(iter(st.session_state.layouts))
                    st.session_state.layout = st.session_state.layouts[st.session_state.selected_plan_key]
                else:
                    st.session_state.selected_plan_key = None
                    st.session_state.layout = None
                st.session_state.selected_room = None
                st.rerun()

        st.divider()
        st.markdown("### Quick Prompts")
        for qp in [
            "What is the total project cost?",
            "Which room is most expensive?",
            "Which room has the highest rate per m²?",
            "How can I reduce the bathroom cost?",
            "Compare the living room and master bedroom",
        ]:
            if st.button(qp, key=f"qp_{qp[:18]}", use_container_width=True):
                st.session_state.pending_prompt = qp
                st.rerun()
    else:
        st.session_state.layout = None
        st.info("Upload one or more layout JSON files to begin.")


# =============================================================================
# MAIN — floor plan (left) + chat (right)
# =============================================================================
st.markdown("## AIA Studio · Cost Advisor · Team 05")
st.caption("Upload plans in the sidebar · choose an active plan · compare up to 5 plans")
st.divider()

tab_floor, tab_advice, tab_match = st.tabs(["Floor Plan & Chat", "Architectural Advice", "Cost Matching"])

# ─────────────────────────── FLOOR PLAN ──────────────────────────────────────
with tab_floor:
    col_plan, col_chat = st.columns([3, 2], gap="large")

    with col_plan:
        if st.session_state.layout:
            st.markdown("#### Floor Plan — Cost Heatmap")
            st.caption("Colors from Grasshopper. Click a room to select it.")

            sel_id = (st.session_state.selected_room or {}).get("id")
            fig    = build_floor_plan(st.session_state.layout, sel_id)

            # On-chart callout annotation for the selected element
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
                    arrowcolor="#4a90d9",
                    arrowwidth=1.5,
                    bgcolor="white",
                    bordercolor="#4a90d9",
                    borderwidth=1.5,
                    borderpad=6,
                    font=dict(size=10, color="#1a1a2e"),
                    align="left",
                    ax=60, ay=-60,
                    xanchor="left",
                )

            plan_col, legend_col = st.columns([5, 1], gap="small")

            with legend_col:
                st.markdown(
                    '<div style="padding-top:2.5rem">'
                    + build_gh_legend(st.session_state.layout)
                    + "</div>",
                    unsafe_allow_html=True,
                )

            with plan_col:
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

            # element info panel — appears below chart when any element is clicked
            _render_element_panel()

            # cost table
            with st.expander("Cost Breakdown Table", expanded=False):
                df       = build_cost_df(st.session_state.layout)
                currency = st.session_state.layout.get("project", {}).get("currency", "")
                fmt      = {f"Rate ({currency}/m²)": "{:,.0f}",
                            f"Cost ({currency})": "{:,.0f}", "Area (m²)": "{:.1f}"}

                def _hl(row):
                    return (["font-weight:bold;background:#f3f4f6;color:#111111"] * len(row)
                            if row["Room"] == "TOTAL" else [""] * len(row))

                st.dataframe(df.style.apply(_hl, axis=1).format(fmt),
                             use_container_width=True, hide_index=True)
        else:
            st.markdown("#### Floor Plan")
            st.info("Upload a **layout JSON** in the sidebar to see the interactive floor plan.")

    # ────────────────────────────── CHAT ─────────────────────────────────────────
    with col_chat:
        st.markdown("#### Agent Chat")
        if st.session_state.selected_plan_key:
            st.caption(f"Analyzing: {st.session_state.selected_plan_key}")

        chat_area = st.container(height=400)
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

        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # ── cost pie charts (inside Floor Plan tab) ───────────────────────────────
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

# ────────────────────────────── ARCHITECTURAL ADVICE ─────────────────────────
with tab_advice:
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

    # ── collect materials ─────────────────────────────────────────────────────
    _layout_mats: list[str] = (
        _extract_layout_mats(st.session_state.layout)
        if st.session_state.layout else []
    )
    _msg_mats: list[str] = _extract_msg_mats(st.session_state.messages)
    _combined: list[str] = list(dict.fromkeys(_msg_mats + _layout_mats))

    # ── source summary ────────────────────────────────────────────────────────
    _src_parts: list[str] = []
    if _msg_mats:
        _src_parts.append(f"chat: {', '.join(m.replace('_', ' ') for m in _msg_mats)}")
    if _layout_mats:
        _src_parts.append(f"plan: {', '.join(m.replace('_', ' ') for m in _layout_mats)}")
    if _src_parts:
        st.caption("Detected — " + " | ".join(_src_parts))
    else:
        st.info("No materials detected yet. Mention materials in the chat (e.g. 'bedroom floor finish marble') to populate this table.")

    # ── auto-generate when material list changes (no spinner — avoids state race) ──
    if _combined:
        _mat_sig = ",".join(_combined) + "|" + _selected_standard + "|" + _selected_region
        if st.session_state.get("_advice_mat_sig") != _mat_sig:
            try:
                st.session_state.arch_advice_rows = _gen_table(_combined, _selected_standard, _selected_region)
                st.session_state["_advice_mat_sig"] = _mat_sig
            except Exception as _exc:
                st.error(f"Advice generation failed: {_exc}")
                st.session_state.arch_advice_rows = []

    # ── render HTML table (avoids st.dataframe rendering issues) ─────────────
    _adv_rows: list[dict] = st.session_state.get("arch_advice_rows") or []
    if _adv_rows:
        _FIRE_COLOR = {
            "A1": "#27ae60", "A2": "#27ae60",
            "B": "#f39c12", "C": "#e67e22",
            "D": "#c0392b", "E": "#c0392b", "F": "#c0392b",
        }
        _th = (
            "text-align:left;padding:8px 14px;"
            "border-bottom:2px solid #ddd;color:#555;font-size:0.82rem;font-weight:600"
        )
        _td = "padding:8px 14px;border-bottom:1px solid #eee;font-size:0.88rem;color:#111"
        _headers = ["Material", "Carbon Footprint", "Fire Rating", "Lifespan (yrs)", "Lower-Carbon Alternative", "Recommendation"]
        _head_html = "".join(f'<th style="{_th}">{h}</th>' for h in _headers)
        _body_html = ""
        _td_alt = _td + ";color:#1a7a3a;font-style:italic"
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

        # ── CSV export ────────────────────────────────────────────────────────
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

    # ── Carbon Budget Tracker ─────────────────────────────────────────────────
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

        _bar_color = "#27ae60" if _pct < 70 else "#f39c12" if _pct < 100 else "#c0392b"
        st.markdown(
            f'<div style="background:#eee;border-radius:6px;height:18px;margin:6px 0">'
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
                _th_s = "text-align:left;padding:6px 12px;border-bottom:2px solid #ddd;color:#555;font-size:0.8rem;font-weight:600"
                _td_s = "padding:6px 12px;border-bottom:1px solid #eee;font-size:0.85rem;color:#111"
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

    # ── Cost × Carbon Matrix ──────────────────────────────────────────────────
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

            # Average reference lines
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
                plot_bgcolor="#f7f7f7",
                font=dict(color="#111"),
                height=420,
                margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            )
            st.plotly_chart(_mx_fig, use_container_width=True)
        else:
            st.info("Assign finish materials to rooms via chat to populate the matrix.")
    else:
        st.info("Upload a layout to enable the cost × carbon matrix.")

# ──────────────────────────── COST MATCHING ──────────────────────────────────
with tab_match:
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

            # KPI row
            _k1, _k2, _k3, _k4 = st.columns(4)
            _k1.metric("Target",         f"{_tgt:,.0f} {_cur}")
            _k2.metric("Adjusted total", f"{_adj:,.0f} {_cur}",
                       delta=f"{_delta:+,.0f}")
            _k3.metric("Gap remaining",  f"{abs(_tgt - _adj):,.0f} {_cur}")
            _k4.metric("Similarity",     f"{_pct:.1f}%",
                       delta=f"{'On target' if _pct >= 99 else 'Approx match'}")

            # similarity bar
            _bar_color = "#2ecc71" if _pct >= 90 else "#f39c12" if _pct >= 70 else "#e74c3c"
            st.markdown(
                f'<div style="background:#e9e9e9;border-radius:8px;height:18px;margin:6px 0 14px">'
                f'<div style="background:{_bar_color};width:{min(_pct,100):.1f}%;height:100%;'
                f'border-radius:8px;transition:width 0.5s"></div></div>',
                unsafe_allow_html=True,
            )

            _sugg = _cm_res["suggestions"]
            if not _sugg:
                st.success("Plan is already at your target — no changes needed.")
            else:
                st.markdown(f"#### Suggested finish changes ({len(_sugg)} adjustment{'s' if len(_sugg)!=1 else ''})")

                # header
                _th = "".join(
                    f'<th style="padding:6px 10px;text-align:left;background:#f0f0f0;'
                    f'border-bottom:2px solid #ccc;white-space:nowrap">{h}</th>'
                    for h in ["Room", "Surface", "From", f"Rate ({_cur}/m²)",
                              "To", f"Rate ({_cur}/m²)", "Area m²",
                              f"Delta ({_cur})", f"New room total ({_cur})"]
                )
                _rows_html = ""
                for i, s in enumerate(_sugg):
                    _bg  = "#ffffff" if i % 2 == 0 else "#f9f9f9"
                    _d   = s["delta_cost"]
                    _dc  = "#c0392b" if _d > 0 else "#27ae60"
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

                # summary footer
                _total_delta = sum(s["delta_cost"] for s in _sugg)
                _dc_total = "#c0392b" if _total_delta > 0 else "#27ae60"
                st.markdown(
                    f'<p style="margin-top:10px;font-size:13px;color:#555">'
                    f'Total adjustment: <b style="color:{_dc_total}">{_total_delta:+,.0f} {_cur}</b> '
                    f'across {len(_sugg)} room{"s" if len(_sugg)!=1 else ""}. '
                    f'Non-room costs (doors, windows, columns) are fixed at '
                    f'<b>{_cm_non_room:,.0f} {_cur}</b>.</p>',
                    unsafe_allow_html=True,
                )

            # ── Before / After bar chart ──────────────────────────────
            st.divider()
            st.markdown("#### Room Cost — Before vs After")
            st.caption("Each room shows its original cost and the adjusted cost after suggested finish changes.")

            _all_rooms   = _cm_layout.get("rooms", [])
            _room_names  = [r.get("name", "") for r in _all_rooms]
            _orig_costs  = [r.get("total_cost", 0) or 0 for r in _all_rooms]

            # build adjusted costs map from suggestions
            _adj_map = {r.get("name"): r.get("total_cost", 0) or 0 for r in _all_rooms}
            if _sugg:
                for _s in _sugg:
                    _adj_map[_s["room"]] = _s["new_room_total"]
            _adj_costs = [_adj_map.get(n, 0) for n in _room_names]

            _bar_colors = [
                "#27ae60" if _adj_map.get(n, 0) < (r.get("total_cost", 0) or 0)
                else "#c0392b" if _adj_map.get(n, 0) > (r.get("total_cost", 0) or 0)
                else "#95a5a6"
                for n, r in zip(_room_names, _all_rooms)
            ]

            _fig_bar = go.Figure()
            _fig_bar.add_trace(go.Bar(
                name="Current cost",
                x=_room_names,
                y=_orig_costs,
                marker_color="#aab4c8",
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
            # target line
            _fig_bar.add_hline(
                y=_tgt / max(len(_room_names), 1),
                line_dash="dot", line_color="#e67e22", line_width=1.5,
                annotation_text=f"Target avg/room: {_tgt/max(len(_room_names),1):,.0f}",
                annotation_position="top right",
            )
            _fig_bar.update_layout(
                barmode="group",
                paper_bgcolor="#ffffff",
                plot_bgcolor="#f7f7f7",
                font=dict(color="#111"),
                height=380,
                margin=dict(l=10, r=10, t=30, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25,
                            xanchor="center", x=0.5),
                yaxis=dict(title=f"Cost ({_cur})", gridcolor="#e5e5e5"),
                xaxis=dict(tickangle=-20),
            )
            st.plotly_chart(_fig_bar, use_container_width=True)




# ── multi-plan comparison (all saved plans) ─────────────────────────────────
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
            _palette = ["#ef4444", "#f59e0b", "#3b82f6", "#10b981", "#8b5cf6"]
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
                    plot_bgcolor="#f7f7f7",
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
