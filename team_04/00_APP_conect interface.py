from __future__ import annotations
from interface_mcp_bridge import run_interface_command
import json, math, sys, time
from pathlib import Path
import httpx
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
    SUPPORTED_BUILDING_TYPES = ("I", "L", "T", "U", "Y", "H", "X", "O")
    def generate_building_boundary(area, building_type="I", **_kw):
        w = math.sqrt(area)
        pts = [(-w/2,-w/2),(w/2,-w/2),(w/2,w/2),(-w/2,w/2)]
        return {"success":True,"data":{"boundary":[[x,y,0.] for x,y in pts],"boundary_area_sqm":area,"perimeter_m":4*w,"centroid":[0.,0.,0.],"shape_type":building_type}}

# ── agent integration ─────────────────────────────────────────────────────────
_agent_available = False
_py_workflow_available = False

# ── Move / Rotate 指令 ────────────────────────────────────────
 

# PY design workflow — same pipeline as design_main.py
_PY_DIR = str(Path(__file__).parent / "PY")
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

try:
    from design_config import load_design_settings as _load_design_settings
    from mcp_client import McpClient as _McpClient
    from design_workflow_graph import run_design_workflow as _run_design_workflow
    import plan_agent as _plan_agent
    from plan_agent import generate_plan_agent_payload, should_request_clarification
    from tool_node import create_chat_llm as _create_chat_llm
    from shape_generator_node import ShapeGenerator as _ShapeGenerator
    _py_workflow_available = True
except Exception:
    pass

try:
    from agent.config import load_settings as _load_agent_settings
    from agent.mcp_client import HttpMcpClient, build_default_local_tool_client, CompositeToolClient
    from agent.decision_engine import OpenAIDecisionEngine, RuleBasedPlanner
    from agent.graph import run_agent
    from agent.tool_catalog import ToolCatalog
    from langchain_openai import ChatOpenAI
    _agent_available = True
except Exception:
    pass

BUILDING_FUNCTIONS = ("residential","commercial","healthcare","institutional","entertainment","mixed use")
SHAPE_DESCRIPTIONS = {"I":"linear bar","L":"L-shaped wing","T":"T-shaped","U":"U-courtyard","Y":"Y-branched","H":"H-courtyard","X":"cross / plus","O":"O-courtyard"}

# wizard steps: 0=shape, 1=function, 2=floors, 3=trees, 4=done
_DEFAULTS = {
    "site_lat": 41.0082,
    "site_lon": 28.9784,
    "drawn_area": None,
    "step": 0,
    "building_shape": None,
    "building_function": None,
    "building_floors": None,
    "building_trees": 0,
    "mesh_vertices": [],
    "mesh_faces": [],
    "mesh_options": [],
    "last_mesh_genes": {},
    "agent_chat_history": [],
    "vp_view": "top",
    "gh_send_status": None,
    "building_boundary": None,
    "building_area_sqm": None,
    "selected_option_idx": None,
}
# Initialize session state with defaults if keys are missing
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

def _get_site_bbox() -> dict[str, float]:
    """Return a fallback site bounding box around the current site coordinates."""
    delta = 0.05
    lat = st.session_state.site_lat
    lon = st.session_state.site_lon
    return {
        "south": lat - delta,
        "north": lat + delta,
        "west": lon - delta,
        "east": lon + delta,
    }


def _load_model_info() -> dict[str, str]:
    """Load LLM and MCP settings from available project configuration."""
    if _py_workflow_available:
        try:
            s = _load_design_settings()
            return {
                "provider": s.llm_provider,
                "model": s.llm_model,
                "api_key": s.api_key,
                "base_url": s.base_url,
                "mcp_endpoint": s.mcp_endpoint,
            }
        except Exception:
            pass
    if _agent_available:
        try:
            s = _load_agent_settings()
            return {
                "provider": s.llm_provider,
                "model": s.llm_model,
                "api_key": s.api_key,
                "base_url": s.base_url,
                "mcp_endpoint": s.mcp_endpoint,
            }
        except Exception:
            pass
    return {
        "provider": "n/a",
        "model": "unknown",
        "api_key": "",
        "base_url": "",
        "mcp_endpoint": "",
    }


def _site_polygon_latlon() -> tuple[list[float], list[float]]:
    """Return site polygon coordinates as (lons, lats)."""
    drawn = st.session_state.drawn_area
    if drawn:
        coords = drawn
        if isinstance(coords, dict):
            if "features" in coords:
                features = coords.get("features") or []
                if features:
                    coords = features[0].get("geometry") or coords
            if isinstance(coords, dict) and "coordinates" in coords:
                coords = coords["coordinates"]
        # Flatten nested coordinate lists, if needed
        while isinstance(coords, list) and coords and isinstance(coords[0], list) and isinstance(coords[0][0], list):
            coords = coords[0]
        if isinstance(coords, list) and coords and isinstance(coords[0], (list, tuple)) and len(coords[0]) >= 2:
            first = coords[0]
            lon0, lat0 = first[0], first[1]
            if abs(lat0 - st.session_state.site_lat) < abs(lon0 - st.session_state.site_lat):
                # Preserve lat/lon order if the first value is closer to site latitude
                lats = [c[0] for c in coords]
                lons = [c[1] for c in coords]
            else:
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]
            if len(lons) > 0 and len(lats) > 0:
                return lons, lats
    # fallback to a simple square around site center
    lat = st.session_state.site_lat
    lon = st.session_state.site_lon
    delta = 0.02
    return (
        [lon - delta, lon + delta, lon + delta, lon - delta, lon - delta],
        [lat - delta, lat - delta, lat + delta, lat + delta, lat - delta],
    )


def _site_area_sqm() -> float:
    """Return the site area in square meters."""
    lons, lats = _site_polygon_latlon()
    if len(lons) < 3 or len(lats) < 3:
        return 400.0
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)
    cos_lat = math.cos(math.radians(clat))
    pts = [((lon - clon) * cos_lat * 111320, (lat - clat) * 111320)
           for lon, lat in zip(lons, lats)]
    area = abs(sum(
        x0 * y1 - x1 * y0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])
    )) / 2.0
    return max(area, 400.0)


def _check_mcp_alive():
    """Return True if MCP endpoint responds to initialize request."""
    mi = _load_model_info()
    ep = mi.get("mcp_endpoint")
    if not ep:
        return False
    try:
        resp = httpx.post(
            ep,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"clientInfo": {"name": "status", "version": "1.0"}, "capabilities": {}}},
            timeout=3.0,
        )
        return resp.status_code < 400
    except Exception:
        return False

def _capture_rhino_screenshot():
    """Capture the Rhino window (or full screen) and return PNG bytes."""
    import io, ctypes
    try:
        from PIL import ImageGrab
        class _RECT(ctypes.Structure):
            _fields_ = [("left",ctypes.c_long),("top",ctypes.c_long),
                        ("right",ctypes.c_long),("bottom",ctypes.c_long)]
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        found = []
        def _cb(hwnd, _):
            n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
            if 'Rhino' in buf.value and ctypes.windll.user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        ctypes.windll.user32.EnumWindows(EnumProc(_cb), 0)
        if found:
            r = _RECT()
            ctypes.windll.user32.GetWindowRect(found[0], ctypes.byref(r))
            img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
        else:
            img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None


def _apply_modification(text: str):
    """Parse move/rotate, call GH MCP, then refresh local mesh from updated genes."""
    import re
    mi = _load_model_info()
    ep = mi.get("mcp_endpoint")
    t = text.strip().lower()

    # ── 1. 解析指令参数 ──────────────────────────────────────────────────
    is_rotate = bool(re.search(r'\brotate\b', t))
    is_move   = bool(re.search(r'\bmove\b', t))

    if not is_rotate and not is_move:
        return False, "couldn't parse — try: move 10 m left · rotate 45 clockwise"

    num_m = re.search(r'(\d+(?:\.\d+)?)', t)
    value = float(num_m.group(1)) if num_m else (15.0 if is_rotate else 1.0)

    # ── 2. 本地 genes 更新（不依赖 MCP，始终执行）──────────────────────
    genes = dict(st.session_state.get("last_mesh_genes") or {})
    label = ""

    if is_rotate:
        cw = 'counter' not in t and 'ccw' not in t
        delta = value if cw else -value
        genes["rotation"]       = (genes.get("rotation", 0) + delta) % 360
        genes["rotation_angle"] = genes["rotation"]
        label = f"✓ rotated {value}° {'clockwise' if cw else 'counter-clockwise'}"
    else:
        dir_m = re.search(r'(left|right|up|down|north|south|east|west)', t)
        dir_  = dir_m.group(1) if dir_m else "right"
        dir_map = {
            "left": (-1, 0), "west":  (-1, 0),
            "right": (1, 0), "east":  (1, 0),
            "up":   (0, 1),  "north": (0, 1),
            "down": (0, -1), "south": (0, -1),
        }
        dx, dy = dir_map.get(dir_, (1, 0))
        bp = list(genes.get("base_point", [0.0, 0.0, 0.0]))
        bp[0] += dx * value
        bp[1] += dy * value
        genes["base_point"] = bp
        label = f"✓ moved {value} m {dir_}"

    # 本地 mesh 立刻更新（离线也能看到效果）
    if _py_workflow_available:
        lv, lf = _generate_local_mesh(genes)
        if lv and lf:
            st.session_state.mesh_vertices = lv
            st.session_state.mesh_faces    = lf
            st.session_state.last_mesh_genes = genes
            alts = _generate_alternatives(genes, n=3)
            st.session_state.mesh_options  = alts
            st.session_state.selected_option_idx = 0

    # ── 3. Try syncing through the interface bridge (preferred) ──────────
    # Spawn a background thread to call the MCP bridge so UI doesn't block
    try:
        import threading

        def _bg_call():
            try:
                res = run_interface_command(text)
            except Exception as _e:
                res = {"success": False, "message": str(_e)}
            try:
                msg = res.get("message") if isinstance(res, dict) else str(res)
            except Exception:
                msg = str(res)
            st.session_state.agent_chat_history.append({
                "user": f"→ {text} (MCP)",
                "agent": f"MCP: {msg}",
            })

        threading.Thread(target=_bg_call, daemon=True).start()
        label += " (GH sync requested)"
    except Exception as e:
        label += f" (background MCP error: {e})"

    return True, label


_SHAPE_TO_GH = {
    "I": "bar", "L": "l_shape", "T": "bar",
    "U": "u_shape", "Y": "cluster", "H": "h_shape",
    "X": "cluster", "O": "courtyard",
}

_SHAPE_CONSTRAINTS = {
    "U": "maximize courtyard area, opening facing south, min leg width 8 m, min opening depth 6 m",
    "H": "symmetric double courtyard, min leg width 8 m",
    "O": "enclosed courtyard, courtyard at least 20% of footprint",
    "L": "maximize south-facing facade, arms at 90\u00b0",
    "T": "central circulation spine perpendicular to main bar",
    "I": "linear bar aligned to the longest site axis",
    "Y": "three-arm radial arrangement, 120\u00b0 between arms",
    "X": "cross-shaped with four equal arms and central hub",
}

def _build_design_prompt() -> str:
    """Build a detailed design prompt from current wizard selections."""
    shape  = st.session_state.building_shape or "I"
    func   = st.session_state.building_function or "residential"
    floors = st.session_state.building_floors or 3
    trees  = st.session_state.building_trees or 0
    gh_shape   = _SHAPE_TO_GH.get(shape, "bar")
    constraint = _SHAPE_CONSTRAINTS.get(shape, "optimize for natural light and ventilation")
    return (
        f"Create a {shape}-shape {func} building inside the site boundary already loaded in Grasshopper. "
        f"{constraint}. "
        f"3 m setbacks on all sides, max building area 60% of site. "
        f"{floors} floors, {trees} trees on site. "
        f"locked_shape_type={gh_shape}. "
        f"Return the final building footprint as a JSON array called vertices_2d "
        f"([[x,y,z], ...] coordinate list), total_area_m2, and a short note explaining the placement choice."
    )


def _generate_local_mesh(genes: dict) -> tuple:
    """Generate 3-D mesh locally via ShapeGenerator (no GH required)."""
    try:
        gen = _ShapeGenerator()
        shape = gen.generate_from_genes(genes)
        if shape and shape.vertices_3d and shape.faces:
            return shape.vertices_3d, shape.faces
    except Exception:
        pass
    return None, None


def _generate_alternatives(base_genes: dict, n: int = 2) -> list:
    """Generate n geometric variations of base_genes for design exploration."""
    if not _py_workflow_available:
        return []
    L = float(base_genes.get("length", 40) or 40)
    W = float(base_genes.get("width", 15) or 15)
    R = float(base_genes.get("rotation", 0) or 0)
    cd = float(base_genes.get("courtyard_size", 10) or 10)
    variants = [
        {**base_genes, "rotation": round((R + 35) % 360, 1), "rotation_angle": round((R + 35) % 360, 1)},
        {**base_genes, "length": round(L * 1.3, 1), "width": round(W * 0.75, 1), "courtyard_size": round(cd * 1.2, 1)},
        {**base_genes, "length": round(L * 0.75, 1), "width": round(W * 1.3, 1), "rotation": round((R - 25) % 360, 1), "rotation_angle": round((R - 25) % 360, 1)},
        {**base_genes, "length": round(L * 1.15, 1), "width": round(W * 1.15, 1), "rotation": round((R + 15) % 360, 1), "rotation_angle": round((R + 15) % 360, 1), "courtyard_size": round(cd * 0.85, 1)},
    ]
    results = []
    for var in variants[:n]:
        v, f = _generate_local_mesh(var)
        if v and f:
            results.append({"vertices": v, "faces": f, "genes": var})
    return results


def _score_design(genes: dict) -> dict:
    """Score a design option (0–100 per metric + total)."""
    try:
        L = float(genes.get("length", 40) or 40)
        W = float(genes.get("width", 15) or 15)
        H = float(genes.get("height", 15) or 15)
        shape = (genes.get("shape_type") or "rectangle").lower()
        fp_ratios = {"rectangle": 1.0, "l_shape": 0.75, "t_shape": 0.75,
                     "u_shape": 0.65, "h_shape": 0.62, "plus_shape": 0.58, "i_shape": 0.80}
        fp = L * W * fp_ratios.get(shape, 0.80)
        perim = 2 * (L + W)
        compact = min(1.0, (4 * 3.14159 * fp) / max(perim ** 2, 1.0)) * 100
        aspect = max(L, W) / max(min(L, W), 1.0)
        prop = max(0.0, 100.0 - abs(aspect - 1.618) * 18)
        vol_score = min(100.0, fp * H / 30.0)
        total = round(0.40 * compact + 0.30 * prop + 0.30 * vol_score, 1)
        return {"compactness": round(compact, 1), "proportions": round(prop, 1),
                "volume": round(vol_score, 1), "total": round(total, 1)}
    except Exception:
        return {"compactness": 0.0, "proportions": 0.0, "volume": 0.0, "total": 0.0}


def _mini_fig_3d(vertices: list, faces: list, selected: bool = False):
    """Tiny Plotly Mesh3d thumbnail for option cards."""
    mfig = go.Figure()
    xs = [v[0] for v in vertices]; ys = [v[1] for v in vertices]; zs = [v[2] for v in vertices]
    cx = (min(xs) + max(xs)) / 2; cy = (min(ys) + max(ys)) / 2; min_z = min(zs)
    ext = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
    ms = 30.0 / ext
    mxs = [(x - cx) * ms for x in xs]; mys = [(y - cy) * ms for y in ys]
    mzs = [(z - min_z) * ms for z in zs]  # bottom at z=0
    # Triangulate — quad wall faces (4 indices) → 2 triangles
    ti, tj, tk = [], [], []
    for f in faces:
        if len(f) >= 3:
            ti.append(f[0]); tj.append(f[1]); tk.append(f[2])
        if len(f) == 4:
            ti.append(f[0]); tj.append(f[2]); tk.append(f[3])
    _c = "#1a1a1a" if selected else "#888888"
    _kw = dict(color=_c, opacity=1.0, flatshading=True,
               lighting=dict(ambient=0.85, diffuse=0.6, specular=0.0, roughness=1.0),
               showlegend=False, hoverinfo="skip")
    mfig.add_trace(go.Mesh3d(x=mxs, y=mys, z=mzs, i=ti, j=tj, k=tk, **_kw))
    _bg = "#f5f5f5" if selected else "#fafafa"
    mfig.update_layout(
        scene=dict(
            bgcolor=_bg,
            xaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
            yaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
            zaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
            camera=dict(eye=dict(x=1.25, y=1.25, z=1.25), projection=dict(type="orthographic")),
            aspectmode="cube",
        ),
        plot_bgcolor=_bg, paper_bgcolor=_bg,
        margin=dict(l=0, r=0, t=0, b=0),
        height=95, showlegend=False,
    )
    return mfig


def _clean_agent_reply(text: str) -> str:
    """Strip JSON blobs and tool output from agent reply for clean display."""
    import re
    # Remove multi-line JSON blobs (lines starting with { or containing tool outputs)
    text = re.sub(r'\{(?:[^{}]|\{[^{}]*\})*\}', '', text)
    # Remove lines that are obviously raw data/report headers
    lines = text.split('\n')
    clean = [l for l in lines if not l.strip().startswith(('{"', '[{', '"parametric'))]
    text = '\n'.join(clean)
    # Collapse extra blank lines
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text if len(text) > 10 else ""


def _parse_mesh_from_response(text: str):
    """Extract vertices_3d and faces from a ShapeOutput JSON embedded in a response string."""
    import re
    candidates = []
    # Collect all JSON objects in the text
    for m in re.finditer(r'\{', text):
        start = m.start()
        depth, end = 0, start
        for i, ch in enumerate(text[start:], start):
            if ch == '{': depth += 1
            elif ch == '}': depth -= 1
            if depth == 0:
                end = i + 1
                break
        if end > start:
            candidates.append(text[start:end])
    for blob in candidates:
        try:
            obj = json.loads(blob)
            # support nested under 'data' key
            if 'data' in obj and isinstance(obj['data'], dict):
                obj = obj['data']
            v3d = obj.get('vertices_3d')
            faces = obj.get('faces')
            if v3d and faces and len(v3d) >= 3 and len(faces) >= 1:
                return v3d, faces
        except Exception:
            pass
    return None, None


def _parse_boundary_from_response(text: str):
    """Extract a [[x,y,z],...] coordinate list from an LLM/GH response."""
    import re
    pattern = (
        r'\[\s*\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?){1,2}\s*\]'
        r'(?:\s*,\s*\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?){1,2}\s*\]){2,}\s*\]'
    )
    for m in re.finditer(pattern, text):
        try:
            pts = json.loads(m.group())
            if len(pts) >= 3:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                return [[p[0] - cx, p[1] - cy, p[2] if len(p) > 2 else 0.0] for p in pts]
        except Exception:
            pass
    try:
        cm = re.search(r'"coordinates"\s*:\s*(\[\s*\[[\s\S]*?\]\s*\])', text)
        if cm:
            pts = json.loads(cm.group(1))
            if len(pts) >= 3:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                return [[p[0] - cx, p[1] - cy, p[2] if len(p) > 2 else 0.0] for p in pts]
    except Exception:
        pass
    return None


def _send_to_grasshopper():
    """Direct parametric_shape_generator call — no LLM, instant GH execution."""
    mi = _load_model_info()
    ep = mi.get("mcp_endpoint")
    if not ep:
        return False, "MCP endpoint not configured (.env missing?)", None

    shape  = st.session_state.building_shape or "I"
    floors = st.session_state.building_floors or 3
    trees  = st.session_state.building_trees or 0
    gh_shape = _SHAPE_TO_GH.get(shape, "bar")

    # Estimate dimensions from site area
    site_sqm = _site_area_sqm()
    side = math.sqrt(max(site_sqm, 400.0))
    arm_len   = round(side * 0.55, 1)
    bld_width = round(max(8.0, side * 0.15), 1)
    genes_dict = {
        "shape_type":     gh_shape,
        "length":         arm_len,
        "width":          arm_len * 0.6,
        "height":         floors * 3.5,
        "courtyard_size": round(max(6.0, side * 0.25), 1),
        "rotation_angle": 0.0,
        "base_point":     [0.0, 0.0, 0.0],
    }
    genes = json.dumps(genes_dict)

    # Generate local mesh immediately (no GH required)
    if _py_workflow_available:
        _lv, _lf = _generate_local_mesh(genes_dict)
        if _lv and _lf:
            st.session_state.mesh_vertices = _lv
            st.session_state.mesh_faces = _lf
            st.session_state.last_mesh_genes = genes_dict
            _alts = _generate_alternatives(genes_dict, n=3)
            st.session_state.mesh_options = _alts
            st.session_state.selected_option_idx = 0

    # Tree positions spread around origin
    import random; random.seed(42)
    n_trees = min(trees, 50)
    tree_pts  = ";".join(f"{random.uniform(-side*0.4,side*0.4):.1f},{random.uniform(-side*0.4,side*0.4):.1f},0" for _ in range(n_trees)) or "0,0,0"
    tree_sz   = ";".join("3.0" for _ in range(n_trees)) or "3.0"

    try:
        client = _McpClient(ep, timeout_seconds=30.0) if _py_workflow_available else HttpMcpClient(ep, timeout_seconds=30.0)
        client.initialize()
        raw = client.call_tool("parametric_shape_generator", {
            "genes_json":        genes,
            "locked_shape_type": gh_shape,
            "site_boundary":     "",
            "tree_points":       tree_pts,
            "tree_count":        str(n_trees),
            "tree_sizes":        tree_sz,
            "iterations":        "50",
            "seed":              42,
        })
        client.close()

        # Try to extract boundary from GH JSON response
        boundary = _parse_boundary_from_response(raw)

        # Local preview fallback
        if boundary is None:
            try:
                area = max(site_sqm * 0.4, 200.0)
                r = generate_building_boundary(area=area, building_type=shape,
                                               floors=floors)
                boundary = r.get("data", {}).get("boundary")
            except Exception:
                pass

        # Extract full 3-D mesh when available
        v3d, faces = _parse_mesh_from_response(raw)
        if v3d and faces:
            st.session_state.mesh_vertices = v3d
            st.session_state.mesh_faces = faces

        short = raw[:400] + ("\u2026" if len(raw) > 400 else "")
        return True, short, boundary
    except Exception as e:
        return False, str(e), None

def _run_agent_chat(prompt: str, _log=None) -> str:
    """Route to PY design workflow (primary) or agent/ LangGraph pipeline (fallback)."""
    _log = _log or (lambda _: None)
    if _py_workflow_available:
        return _run_py_design_workflow(prompt, _log=_log)
    if _agent_available:
        return _run_langgraph_agent(prompt, _log=_log)
    return "\u26a0 no agent pipeline available \u2014 check requirements."


def _run_py_design_workflow(prompt: str, _log=None) -> str:
    """Run via PY/design_main.py pipeline: plan_agent \u2192 run_design_workflow \u2192 GH MCP."""
    _log = _log or (lambda _: None)
    try:
        _log("Loading settings...")
        s = _load_design_settings()
        _log("Connecting to Grasshopper MCP...")
        mcp = _McpClient(s.mcp_endpoint, s.request_timeout_seconds)
        mcp.initialize()
        tools = mcp.list_tools()
        planning_llm = _create_chat_llm(
            api_key=s.api_key,
            base_url=s.base_url,
            llm_model=s.llm_model,
            timeout_seconds=min(s.request_timeout_seconds, 20.0),
        )
        _log("Thinking about your design...")
        try:
            planning_context = generate_plan_agent_payload(
                llm=planning_llm,
                user_prompt=prompt,
                tools=tools,
                layout_schema={},
                dbg=lambda _: None,
            )
        except Exception:
            planning_context = _plan_agent._fallback_plan(
                prompt, _plan_agent.build_shape_generation_state(prompt)
            )
        if should_request_clarification(planning_context):
            q = str(planning_context.get("clarification_question", "please clarify the design intent"))
            mcp.close()
            return f"\u2753 {q}"

        _log("Generating geometry...")
        # Generate local mesh immediately from planning_context genes
        _plan_genes = {
            "shape_type": planning_context.get("selected_shape_type") or "rectangle",
            "length": float(planning_context.get("length", 40.0) or 40.0),
            "width": float(planning_context.get("width", 15.0) or 15.0),
            "height": float(planning_context.get("height", 15.0) or 15.0),
            "rotation": float(planning_context.get("rotation", 0.0) or 0.0),
            "courtyard_size": float(planning_context.get("courtyard_size", 10.0) or 10.0),
            "wing_depth": planning_context.get("wing_depth"),
            "base_point": [0.0, 0.0, 0.0],
        }
        _lv, _lf = _generate_local_mesh(_plan_genes)
        if _lv and _lf:
            st.session_state.mesh_vertices = _lv
            st.session_state.mesh_faces = _lf
            st.session_state.last_mesh_genes = _plan_genes
            _alts = _generate_alternatives(_plan_genes, n=3)
            st.session_state.mesh_options = _alts
            st.session_state.selected_option_idx = 0

        # If GH not connected, skip the heavy workflow — mesh is already generated
        if not _check_mcp_alive():
            mcp.close()
            _log("Done.")
            _sc = _score_design(_plan_genes)
            return (
                f"Design generated — score **{_sc['total']}/100**.\n\n"
                "**3 options** are shown on the right panel. "
                "Click → select on any option, or type:\n"
                "- *\"Option 2\"* — switch to that option\n"
                "- *\"Option 1 but make it taller\"* — refine\n"
                "- *\"yes\"* — keep current option"
            )

        _log("Sending to Grasshopper...")
        response = _run_design_workflow(
            user_prompt=prompt,
            tools=tools,
            mcp_client=mcp,
            api_key=s.api_key,
            base_url=s.base_url,
            llm_model=s.llm_model,
            debug_graph=False,
            timeout_seconds=min(s.request_timeout_seconds, 60.0),
            max_iterations=min(s.max_iterations, 3),
            planning_context=planning_context,
        )
        _log("Done.")
        mcp.close()
        return response
    except Exception as e:
        return f"\u26a0 design workflow error: {e}"


def _run_langgraph_agent(prompt: str, _log=None) -> str:
    """Fallback: run via agent/ LangGraph pipeline."""
    _log = _log or (lambda _: None)
    mi = _load_model_info()
    if mi.get("provider") in ("n/a", "?"):
        return f"\u26a0 LLM not configured \u2014 check .env: {mi.get('model', '')}"
    try:
        s = _load_agent_settings()
        _log("Connecting to tools...")
        local_client = build_default_local_tool_client()
        clients = [local_client]
        mcp_conn = None
        if _check_mcp_alive():
            try:
                mcp_conn = HttpMcpClient(s.mcp_endpoint, timeout_seconds=s.request_timeout_seconds)
                mcp_conn.initialize()
                clients.append(mcp_conn)
            except Exception:
                mcp_conn = None
        composite = CompositeToolClient(clients)
        catalog = ToolCatalog.from_discovered_tools(composite.list_tools())
        llm = ChatOpenAI(
            api_key=s.api_key,
            base_url=s.base_url,
            model=s.llm_model,
            timeout=s.request_timeout_seconds,
            temperature=0,
        )
        engine = OpenAIDecisionEngine(llm=llm)
        planner = RuleBasedPlanner()
        lons, lats = _site_polygon_latlon()
        clat = sum(lats) / len(lats)
        clon = sum(lons) / len(lons)
        cos_lat = math.cos(math.radians(clat))
        site_boundary = [
            [(lo - clon) * cos_lat * 111320, (la - clat) * 111320, 0.0]
            for lo, la in zip(lons, lats)
        ]
        layout_payload: dict = {"site_boundary": site_boundary}
        if st.session_state.building_boundary:
            layout_payload["existing_boundary"] = st.session_state.building_boundary
        _log("Running agent...")
        final_state = run_agent(
            user_prompt=prompt,
            decision_engine=engine,
            tool_client=composite,
            catalog=catalog,
            initial_layout=layout_payload,
            max_optimization_cycles=s.max_optimization_cycles,
            planner=planner,
        )
        if mcp_conn:
            mcp_conn.close()
        return final_state.get("final_response") or "Agent completed without a response."
    except Exception as e:
        return f"\u26a0 agent error: {e}"

# ── Rhino viewport ────────────────────────────────────────────────────────────
def _rhino_fig():
    fig = go.Figure()
    GR, STEP = 55, 10
    for v in range(-GR, GR+1, STEP):
        for xs, ys in [([v,v],[-GR,GR]),([-GR,GR],[v,v])]:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                line=dict(color="#ebebeb", width=1), showlegend=False, hoverinfo="skip"))
    for xs, ys in [([-GR,GR],[0,0]),([0,0],[-GR,GR])]:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
            line=dict(color="#e0e0e0", width=1.5), showlegend=False, hoverinfo="skip"))

    lons, lats = _site_polygon_latlon()
    clat = sum(lats)/len(lats); clon = sum(lons)/len(lons)
    cos_lat = math.cos(math.radians(clat))
    sx_m = [(lo-clon)*cos_lat*111320 for lo in lons]
    sy_m = [(la-clat)*111320 for la in lats]
    max_ext = max(max(abs(x) for x in sx_m), max(abs(y) for y in sy_m), 1.)
    scale = (GR*0.80)/max_ext
    sx = [x*scale for x in sx_m]; sy = [y*scale for y in sy_m]
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines",
        line=dict(color="#c8c8c8", width=1, dash="dot"),
        fill="toself", fillcolor="rgba(0,0,0,0.015)",
        showlegend=False, hoverinfo="skip"))

    if st.session_state.building_boundary:
        bpts = st.session_state.building_boundary
        bxs = [p[0]*scale for p in bpts]+[bpts[0][0]*scale]
        bys = [p[1]*scale for p in bpts]+[bpts[0][1]*scale]
        fig.add_trace(go.Scatter(x=bxs, y=bys, mode="lines",
            line=dict(color="#444444", width=2),
            fill="toself", fillcolor="rgba(0,0,0,0.05)",
            showlegend=False, hovertemplate=f"{st.session_state.building_shape} footprint<extra></extra>"))
        fig.add_annotation(x=0, y=0, text=st.session_state.building_shape or "",
            showarrow=False, font=dict(size=16, color="#cccccc", family="JetBrains Mono"))

    # tree dots
    if st.session_state.building_trees and st.session_state.building_trees > 0:
        import random; random.seed(42)
        n = min(st.session_state.building_trees, 50)
        txs = [random.uniform(-GR*0.7, GR*0.7) for _ in range(n)]
        tys = [random.uniform(-GR*0.7, GR*0.7) for _ in range(n)]
        fig.add_trace(go.Scatter(x=txs, y=tys, mode="markers",
            marker=dict(color="#5a8a5a", size=5, symbol="circle"),
            showlegend=False, hoverinfo="skip"))

    fig.update_layout(
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        margin=dict(l=0,r=0,t=0,b=0),
        xaxis=dict(visible=False, range=[-GR-3,GR+3], scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False, range=[-GR-3,GR+3]),
        height=360,
    )

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


def _rhino_fig_3d(cam_mode: str = "iso"):
    """3-D Plotly figure — cam_mode: 'iso' (isometric ortho) or 'persp' (perspective)."""
    fig = go.Figure()

    lons, lats = _site_polygon_latlon()
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)
    cos_lat = math.cos(math.radians(clat))
    sx_m = [(lo - clon) * cos_lat * 111320 for lo in lons]
    sy_m = [(la - clat) * 111320 for la in lats]
    max_ext = max(max(abs(x) for x in sx_m), max(abs(y) for y in sy_m), 1.0)
    scale = 44.0 / max_ext
    sx = [x * scale for x in sx_m]
    sy = [y * scale for y in sy_m]

    # site boundary and ground — shown only when no mesh loaded
    if not (st.session_state.get("mesh_vertices") and st.session_state.get("mesh_faces")):
        fig.add_trace(go.Scatter3d(
            x=sx + [sx[0]], y=sy + [sy[0]], z=[0.0] * (len(sx) + 1),
            mode="lines", line=dict(color="#cccccc", width=2),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Mesh3d(
            x=sx, y=sy, z=[0.0] * len(sx),
            color="#f0f0f0", opacity=0.8, alphahull=0,
            showlegend=False, hoverinfo="skip",
        ))

    mesh_verts = st.session_state.get("mesh_vertices")
    mesh_faces = st.session_state.get("mesh_faces")

    if mesh_verts and mesh_faces:
        # ── Single mesh view ─────────────────────────────────────────────────
        xs = [v[0] for v in mesh_verts]
        ys = [v[1] for v in mesh_verts]
        zs = [v[2] for v in mesh_verts]
        cx_m = (min(xs) + max(xs)) / 2
        cy_m = (min(ys) + max(ys)) / 2
        min_z = min(zs)  # keep bottom at z=0 so building sits on ground
        mesh_ext = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
        # Scale mesh to fill viewport (target ~80 units wide)
        ms = 80.0 / mesh_ext
        mxs = [(v[0] - cx_m) * ms for v in mesh_verts]
        mys = [(v[1] - cy_m) * ms for v in mesh_verts]
        mzs = [(v[2] - min_z) * ms for v in mesh_verts]  # bottom at z=0
        # Triangulate — shape generator may emit quad wall faces (4 indices)
        tri_i, tri_j, tri_k = [], [], []
        for f in mesh_faces:
            if len(f) >= 3:
                tri_i.append(f[0]); tri_j.append(f[1]); tri_k.append(f[2])
            if len(f) == 4:
                tri_i.append(f[0]); tri_j.append(f[2]); tri_k.append(f[3])
        fi, fj, fk = tri_i, tri_j, tri_k
        _mesh_kwargs = dict(
            color="#c8c8c8", opacity=1.0,
            flatshading=True,
            lighting=dict(ambient=0.85, diffuse=0.6, specular=0.0, roughness=1.0),
            showlegend=False, hoverinfo="skip",
        )
        # Single-sided — no back face trace (avoids interior faces showing)
        fig.add_trace(go.Mesh3d(x=mxs, y=mys, z=mzs, i=fi, j=fj, k=fk, **_mesh_kwargs))

        # Footprint outline at bottom z
        bot_z = min(zs)
        fp = [v for v in mesh_verts if abs(v[2] - bot_z) < 0.05]
        if len(fp) >= 3:
            fpx = [(v[0] - cx_m) * ms for v in fp] + [(fp[0][0] - cx_m) * ms]
            fpy = [(v[1] - cy_m) * ms for v in fp] + [(fp[0][1] - cy_m) * ms]
            fig.add_trace(go.Scatter3d(
                x=fpx, y=fpy, z=[0.0] * len(fpx),
                mode="lines", line=dict(color="#222222", width=2),
                showlegend=False, hoverinfo="skip",
            ))
        # Fit scene to mesh bounds
        _iso_eye = dict(x=1.25, y=1.25, z=1.25)
        _persp_eye = dict(x=1.4, y=-1.4, z=0.85)
        _cam_eye = _iso_eye if cam_mode == "iso" else _persp_eye
        _projection = dict(type="orthographic") if cam_mode == "iso" else dict(type="perspective")
        _label = "ISOMETRIC" if cam_mode == "iso" else "PERSPECTIVE"
        pad = mesh_ext * ms * 0.15
        ax_range = [-40 - pad, 40 + pad]
        fig.update_layout(
            scene=dict(
                bgcolor="#ffffff",
                xaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False, range=ax_range),
                yaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False, range=ax_range),
                zaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
                camera=dict(eye=_cam_eye, projection=_projection),
                aspectmode="cube",
            ),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            margin=dict(l=0, r=0, t=0, b=0),
            height=360, showlegend=False,
        )
        fig.add_annotation(x=0.01, y=0.98, xref="paper", yref="paper", text=_label,
            showarrow=False, font=dict(size=9, color="#cccccc", family="JetBrains Mono"),
            xanchor="left", yanchor="top")
        return fig

    elif st.session_state.building_boundary:
        # ── Fallback: extrude boundary polygon ───────────────────────────────
        bpts = st.session_state.building_boundary
        bx = [p[0] * scale for p in bpts]
        by = [p[1] * scale for p in bpts]
        fl = st.session_state.building_floors or 1
        h = fl * 3.2 * scale
        nb = len(bx)
        vx = bx + bx; vy = by + by; vz = [0.0] * nb + [h] * nb
        ii, jj, kk = [], [], []
        for idx in range(nb):
            nxt = (idx + 1) % nb
            ii += [idx, idx]; jj += [nxt, nb + nxt]; kk += [nb + nxt, nb + idx]
        for idx in range(1, nb - 1):
            ii.append(nb); jj.append(nb + idx); kk.append(nb + idx + 1)
        fig.add_trace(go.Mesh3d(
            x=vx, y=vy, z=vz, i=ii, j=jj, k=kk,
            color="#aaaaaa", opacity=0.55,
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter3d(
            x=bx + [bx[0]], y=by + [by[0]], z=[0.0] * (nb + 1),
            mode="lines", line=dict(color="#aaaaaa", width=2),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter3d(
            x=bx + [bx[0]], y=by + [by[0]], z=[h] * (nb + 1),
            mode="lines", line=dict(color="#333333", width=2),
            showlegend=False, hoverinfo="skip",
        ))
        for bxi, byi in zip(bx, by):
            fig.add_trace(go.Scatter3d(
                x=[bxi, bxi], y=[byi, byi], z=[0.0, h],
                mode="lines", line=dict(color="#cccccc", width=1),
                showlegend=False, hoverinfo="skip",
            ))

    if st.session_state.building_trees and st.session_state.building_trees > 0:
        import random; random.seed(42)
        nt = min(st.session_state.building_trees, 50)
        txs = [random.uniform(-38, 38) for _ in range(nt)]
        tys = [random.uniform(-38, 38) for _ in range(nt)]
        fig.add_trace(go.Scatter3d(
            x=txs, y=tys, z=[0.0] * nt,
            mode="markers", marker=dict(color="#5a8a5a", size=4),
            showlegend=False, hoverinfo="skip",
        ))

    fig.update_layout(
        scene=dict(
            bgcolor="#ffffff",
            xaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
            yaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
            zaxis=dict(visible=False, showgrid=False, zeroline=False, showbackground=False),
            camera=dict(eye=dict(x=1.5, y=-1.5, z=0.9)),
            aspectmode="data",
        ),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        margin=dict(l=0, r=0, t=0, b=0),
        height=360, showlegend=False,
    )
    fig.add_annotation(x=0.01, y=0.98, xref="paper", yref="paper", text="PERSPECTIVE",
        showarrow=False, font=dict(size=9, color="#cccccc", family="JetBrains Mono"),
        xanchor="left", yanchor="top")
    return fig


# ── wizard step processor ──────────────────────────────────────────────────────────
STEP_QUESTIONS = [
    # (question_text, hint_text, field, validator_fn)
    (
        "1 — select your building shape",
        "(I · L · T · U · Y · H · X · O)",
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
  <div class="flowline">select site &rarr; define building &rarr; preview &rarr; building modifications &rarr; export</div>
</div>
<div class="top-rule"></div>
""", unsafe_allow_html=True)

left_col, main_col = st.columns([1.3, 4.7], gap="large")

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
        b = _get_site_bbox()
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

    map_data = st_folium(_m, key="site_map", height=300, width=None)

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
    _mi = _load_model_info()
    _mcp_ok = _check_mcp_alive()
    _mcp_dot = "<span style='color:#2ecc71;'>&#9679;</span>" if _mcp_ok else "<span style='color:#444;'>&#9676;</span>"
    _mcp_label = "rhino connected" if _mcp_ok else "rhino offline"
    st.markdown(f"""
    <div class='rhino-bar'>
        <span style='color:#c0392b;font-size:8px;'>&#9632;</span>
        <span style='color:#e67e22;font-size:8px;'>&#9632;</span>
        <span style='color:#2ecc71;font-size:8px;'>&#9632;</span>
        &nbsp;&nbsp; Rhino 8 &nbsp;&rarr;&nbsp; {st.session_state.get("vp_view","top").upper()} &nbsp;|&nbsp; TerraPilot viewport
        &nbsp;&nbsp;&nbsp;<span style='color:#333;'>|</span>&nbsp;&nbsp;&nbsp;
        {_mcp_dot} <span class='mcp-status'>{_mcp_label}</span>
        &nbsp;&nbsp;&nbsp;<span style='color:#333;'>|</span>&nbsp;&nbsp;&nbsp;
        <span style='color:#555;'>llm:</span>&nbsp;{_mi["model"]}&nbsp;<span style='color:#444;'>({_mi["provider"]})</span>
    </div>""", unsafe_allow_html=True)

    _mesh_opts_now = st.session_state.get("mesh_options", [])
    _has_opts = bool(_mesh_opts_now and st.session_state.get("mesh_vertices"))
    _vp_ratio = [3.2, 2.5] if _has_opts else [5, 1]
    vp_col, brief_col = st.columns(_vp_ratio)

    with vp_col:
        vp_opts = ["iso", "persp", "top"]
        cur_view = st.session_state.get("vp_view", "iso")
        if cur_view not in vp_opts:
            cur_view = "iso"
        vp = st.radio("view", vp_opts, horizontal=True,
                      index=vp_opts.index(cur_view),
                      label_visibility="collapsed")
        st.session_state.vp_view = vp
        if vp in ("iso", "persp"):
            st.plotly_chart(_rhino_fig_3d(cam_mode=vp), width="stretch", config={"displayModeBar": False})
        else:
            st.plotly_chart(_rhino_fig(), width="stretch", config={"displayModeBar": False})
        # ── Score display below active viewport ──────────────────────────────────
        _cur_genes = st.session_state.get("last_mesh_genes")
        if _cur_genes and st.session_state.get("mesh_vertices"):
            _sc = _score_design(_cur_genes)
            _sel_label = ""
            if _has_opts:
                _si = st.session_state.get("selected_option_idx", 0)
                _sel_label = f" · Option {_si + 1} selected"
            st.markdown(
                f"<div style='font-family:\"JetBrains Mono\",monospace;font-size:9px;color:#999;"
                f"padding:5px 4px 2px;border-top:1px solid #efefef;display:flex;gap:18px;flex-wrap:wrap;'>"
                f"<span>SCORE&nbsp;<b style='color:#333;font-size:13px;'>{_sc['total']}</b>/100{_sel_label}</span>"
                f"<span>compactness&nbsp;<b style='color:#555;'>{_sc['compactness']}</b></span>"
                f"<span>proportions&nbsp;<b style='color:#555;'>{_sc['proportions']}</b></span>"
                f"<span>volume&nbsp;<b style='color:#555;'>{_sc['volume']}</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with brief_col:
        if _has_opts:
            # ── Option cards: 3 columns side by side ──────────────────────
            _all_opts = [
                {"vertices": st.session_state.mesh_vertices,
                 "faces": st.session_state.mesh_faces,
                 "genes": st.session_state.get("last_mesh_genes", {})}
            ] + _mesh_opts_now
            _sel_idx = st.session_state.get("selected_option_idx", 0)
            _opt_labels = ["Option 1", "Option 2", "Option 3", "Option 4"]
            st.markdown(
                "<div style='font-family:\"JetBrains Mono\",monospace;font-size:9px;"
                "color:#aaa;margin-bottom:6px;letter-spacing:0.05em;'>DESIGN OPTIONS — click to select</div>",
                unsafe_allow_html=True,
            )
            # 2×2 grid
            _row1_cols = st.columns(2, gap="small")
            _row2_cols = st.columns(2, gap="small")
            _grid_cols = _row1_cols + _row2_cols
            for _oi, (_opt, _ocol) in enumerate(zip(_all_opts[:4], _grid_cols)):
                with _ocol:
                    _is_sel = (_oi == _sel_idx)
                    _osc = _score_design(_opt.get("genes", {}))
                    _border_col = "#333" if _is_sel else "#e0e0e0"
                    _bg_col = "#f5f5f5" if _is_sel else "#ffffff"
                    _label_weight = "700" if _is_sel else "400"
                    _tick = "\u2713 " if _is_sel else ""
                    st.markdown(
                        f"<div style='border:1.5px solid {_border_col};border-radius:4px;"
                        f"padding:4px 6px 2px;background:{_bg_col};text-align:center;'>"
                        f"<span style='font-family:\"JetBrains Mono\",monospace;font-size:8px;"
                        f"color:#444;font-weight:{_label_weight};'>{_tick}"
                        f"{_opt_labels[_oi] if _oi < 4 else f'Opt {_oi+1}'}</span><br/>"
                        f"<b style='color:#222;font-size:13px;'>{_osc['total']}</b>"
                        f"<span style='font-size:8px;color:#999;'>/100</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(
                        _mini_fig_3d(_opt["vertices"], _opt["faces"], selected=_is_sel),
                        width="stretch", config={"displayModeBar": False},
                        key=f"mini_plot_{_oi}",
                    )
                    st.markdown(
                        f"<div style='font-family:\"JetBrains Mono\",monospace;font-size:7px;"
                        f"color:#bbb;text-align:center;margin-top:-10px;'>"
                        f"c {_osc['compactness']} &middot; p {_osc['proportions']} &middot; v {_osc['volume']}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if not _is_sel:
                        if st.button(
                            f"\u2192 select",
                            key=f"sel_opt_btn_{_oi}",
                            use_container_width=True,
                        ):
                            _chosen = _all_opts[_oi]
                            st.session_state.mesh_vertices = _chosen["vertices"]
                            st.session_state.mesh_faces = _chosen["faces"]
                            if _chosen.get("genes"):
                                st.session_state.last_mesh_genes = _chosen["genes"]
                            st.session_state.selected_option_idx = _oi
                            _osc_sel = _score_design(_chosen.get("genes") or {})
                            st.session_state.agent_chat_history.append({
                                "user": f"→ selected Option {_oi + 1}",
                                "agent": f"✓ Option {_oi + 1} active — score **{_osc_sel['total']}/100**. Type a refinement or start a new design."
                            })
                            st.rerun()
                    else:
                        st.markdown(
                            "<div style='font-family:\"JetBrains Mono\",monospace;font-size:8px;"
                            "color:#2ecc71;text-align:center;padding:2px 0;'>\u2713 active</div>",
                            unsafe_allow_html=True,
                        )
        else:
            # ── Default status panel when no alternatives ────────────────────
            _site_sqm_brief = _site_area_sqm()
            _mcp_brief = _check_mcp_alive()
            _has_mesh = bool(st.session_state.get("mesh_vertices"))
            _geo_status = "mesh ready \u25cf" if _has_mesh else "no geometry yet"
            _geo_color = "#2ecc71" if _has_mesh else "#aaa"
            st.markdown(f"""
<div class='chat-bubble-agent' style='padding:8px 14px;margin-top:30px;'>
<table style='border-collapse:collapse;font-size:11px;line-height:1.8;'>
  <tr><td style='color:#888;padding-right:16px;white-space:nowrap;'>site area</td><td><b>{_site_sqm_brief:,.0f} m&sup2;</b></td></tr>
  <tr><td style='color:#888;'>grasshopper</td><td><b>{'connected' if _mcp_brief else 'offline'}</b></td></tr>
  <tr><td style='color:#888;'>geometry</td><td><b style='color:{_geo_color};'>{_geo_status}</b></td></tr>
</table>
</div>
""", unsafe_allow_html=True)

    # ── chat area ─────────────────────────────────────────────────────────────
    if st.session_state.agent_chat_history:
        _chat_html = "<div style='max-height:200px;overflow-y:auto;padding-right:4px;'>"
        for _entry in st.session_state.agent_chat_history:
            _chat_html += f"<div class='chat-bubble-user'>{_entry['user']}</div>"
            _dt = _clean_agent_reply(_entry['agent'])
            if _dt:
                _chat_html += f"<div class='chat-bubble-agent'>{_dt}</div>"
        _chat_html += "</div>"
        st.markdown(_chat_html, unsafe_allow_html=True)

    with st.form("main_chat_form", clear_on_submit=True):
        _has_history = bool(st.session_state.agent_chat_history)
        _placeholder = "refine, select an option, or describe next modification…" if _has_history else "e.g. Create a U-shape building, maximize courtyard, 3 m setbacks, max 60% coverage…"
        _chat_input = st.text_input(
            label="prompt",
            label_visibility="collapsed",
            placeholder=_placeholder,
        )
        import re as _re
        _opts = st.session_state.get("mesh_options", [])
        _inp = _chat_input.strip()
        _chat_submitted = st.form_submit_button("→ send")

        # ── Option selection handling ──────────────────────────────────
        _sel_idx = None
        if _chat_submitted and _inp and _opts:
            _lo = _inp.lower()
            for _n, _pat in [
                (0, r'\boption\s*1\b|option\s*one\b|first\b|birinci\b'),
                (1, r'\boption\s*2\b|option\s*two\b|second\b|ikinci\b'),
                (2, r'\boption\s*3\b|option\s*three\b|third\b|\büçüncü\b'),
                (3, r'\boption\s*4\b|option\s*four\b|fourth\b|dördüncü\b'),
            ]:
                if _re.search(_pat, _lo):
                    _sel_idx = _n
                    break
            if _sel_idx is None and _re.search(r'\byes\b|evet\b|like it\b|beğendim\b|perfect\b|güzel\b|go with it\b', _lo):
                _sel_idx = 0

        if _sel_idx is not None:
            _all_opts = [
                {"vertices": st.session_state.mesh_vertices, "faces": st.session_state.mesh_faces,
                 "genes": st.session_state.get("last_mesh_genes", {})}
            ] + _opts
            if _sel_idx < len(_all_opts):
                _chosen = _all_opts[_sel_idx]
                st.session_state.mesh_vertices = _chosen["vertices"]
                st.session_state.mesh_faces = _chosen["faces"]
                if _chosen.get("genes"):
                    st.session_state.last_mesh_genes = _chosen["genes"]
                st.session_state.selected_option_idx = _sel_idx
            _has_mod = bool(_re.search(
                r'\bbut\b|ama\b|also\b|make\b|yap\b|daha\b|bigger\b|smaller\b|taller\b|wider\b|shorter\b|büyük\b|küçük\b|yüksek\b',
                _lo
            ))
            if not _has_mod:
                st.session_state.mesh_options = []
                _confirm_label = ["Option 1", "Option 2", "Option 3", "Option 4"][_sel_idx] if _sel_idx < 4 else f"Option {_sel_idx+1}"
                st.session_state.agent_chat_history.append({
                    "user": _inp,
                    "agent": f"✓ {_confirm_label} selected. Viewport updated. Type any further refinements or start a new design."
                })
                st.session_state.vp_view = "persp"
                st.rerun()
            # has modification — fall through to agent

        # ── Move / Rotate 指令：处理后直接 rerun，绝不跌落到 agent ──────
        if _sel_idx is None and _re.search(r'\b(move|rotate)\b', _inp, _re.I):
            _ok, _msg = _apply_modification(_inp)

            # MCP offline 时的本地 mesh 回退
            if not _ok and st.session_state.get("last_mesh_genes"):
                _r_num = _re.search(r'(\d+(?:\.\d+)?)', _inp)
                _angle = float(_r_num.group(1)) if _r_num else 15.0
                _cw = 'counter' not in _inp.lower() and 'ccw' not in _inp.lower()
                _delta = _angle if _cw else -_angle

                _genes = dict(st.session_state.last_mesh_genes)

                if _re.search(r'\brotate\b', _inp, _re.I):
                    # 旋转：更新 rotation gene
                    _genes["rotation"] = (_genes.get("rotation", 0) + _delta) % 360
                    _genes["rotation_angle"] = _genes["rotation"]
                    _label = f"✓ rotated {_angle}° {'clockwise' if _cw else 'counter-clockwise'} (local preview)"
                else:
                    # 移动：更新 base_point gene
                    _r_dir = _re.search(
                        r'(left|right|up|down|north|south|east|west)', _inp.lower()
                    )
                    _dir = _r_dir.group(1) if _r_dir else "right"
                    _dir_map = {
                        "left": (-1, 0), "west": (-1, 0),
                        "right": (1, 0),  "east": (1, 0),
                        "up": (0, 1),     "north": (0, 1),
                        "down": (0, -1),  "south": (0, -1),
                    }
                    _dx, _dy = _dir_map.get(_dir, (1, 0))
                    _bp = list(_genes.get("base_point", [0.0, 0.0, 0.0]))
                    _bp[0] += _dx * _angle
                    _bp[1] += _dy * _angle
                    _genes["base_point"] = _bp
                    _label = f"✓ moved {_angle} m {_dir} (local preview)"

                _lv, _lf = _generate_local_mesh(_genes)
                if _lv and _lf:
                    st.session_state.mesh_vertices = _lv
                    st.session_state.mesh_faces = _lf
                    st.session_state.last_mesh_genes = _genes
                    _alts = _generate_alternatives(_genes, n=3)
                    st.session_state.mesh_options = _alts
                    st.session_state.selected_option_idx = 0
                    _msg = _label
                    _ok = True

            # 无论 MCP 是否在线、本地是否成功，都在这里结束，不跑 agent
            st.session_state.agent_chat_history.append({
                "user": _inp,
                "agent": _msg,
            })
            st.session_state.vp_view = "persp"
            st.rerun()

        # ── Normal agent call ────────────────────────────────────────────
        _status_slot = st.empty()
        def _log_step(msg: str):
            _status_slot.markdown(
                f'<p style="font-size:10px;color:#aaaaaa;font-family:JetBrains Mono,monospace;'
                f'margin:2px 0 4px 0;letter-spacing:0.2px;">↻ {msg}</p>',
                unsafe_allow_html=True
            )
        _chat_response = _run_agent_chat(_inp, _log=_log_step)
        _status_slot.empty()
        _v3d, _faces = _parse_mesh_from_response(_chat_response)
        if _v3d and _faces:
            st.session_state.mesh_vertices = _v3d
            st.session_state.mesh_faces = _faces
            st.session_state.vp_view = "persp"
        _bnd = _parse_boundary_from_response(_chat_response)
        if _bnd:
            st.session_state.building_boundary = _bnd
            st.session_state.vp_view = "persp"
        _new_alts = st.session_state.get("mesh_options", [])
        if _new_alts and st.session_state.get("mesh_vertices"):
            _sc_main = _score_design(st.session_state.get("last_mesh_genes") or {})
            _agent_reply = (
                f"Design generated — score **{_sc_main['total']}/100**.\n\n"
                "**3 options** are shown on the right panel. "
                "Click → select on any option, or type:\n"
                "- *\"Option 2\"* — switch to that option\n"
                "- *\"Option 1 but make it taller\"* — refine\n"
                "- *\"yes\"* — keep current option"
            )
        else:
            _agent_reply = _clean_agent_reply(_chat_response) or "Design updated."
        st.session_state.agent_chat_history.append({"user": _inp, "agent": _agent_reply})
        st.rerun()

    if st.session_state.agent_chat_history:
        if st.button("clear chat", key="clear_chat_btn"):
            st.session_state.agent_chat_history = []
            st.rerun()

    if st.session_state.gh_send_status:
        _kind, _txt = st.session_state.gh_send_status
        _c = "#2ecc71" if _kind == "ok" else "#cc4444"
        st.markdown(f"<div style='font-size:10px;color:{_c};margin-top:2px;margin-bottom:6px;'>{_txt}</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
