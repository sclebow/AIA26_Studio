"""
Interactive spatial graph visualizer — Apple-minimalist aesthetic.

Generates a standalone HTML file (no server required) with:
- Nodes positioned at their real architectural coordinates (mirrors the floor plan)
- Drag nodes to explore — they spring back to their original position on release
- Click any node to open a detail panel with full metadata and connections
- Dark / Light mode toggle (persists via localStorage)
- Legend panel: click to filter/highlight by node or edge type (shift-click = multi)
- Hover tooltips with full element attributes and analysis results
- New-element glow + "new" badge when enrich_graph runs
- Live-refresh toggle for automatic updates during agent runs

Usage:
    python visualize_interactive.py                    # uses industrial_005
    python visualize_interactive.py industrial_03      # specify layout name
    python visualize_interactive.py --session          # uses workspace/session_active.json
    python visualize_interactive.py --open             # re-open existing HTML
"""

import http.server
import json
import socket
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spatial_graph import build_graph_from_layout

# ── Local HTTP server — required for live change-detection polling ────────────
# Browsers silently block fetch() on file:// origins (same-origin policy),
# so the polling JS can never read the updated file. A minimal localhost server
# fixes this: the browser fetches from http://127.0.0.1:PORT/ and change
# detection works correctly. The server is a daemon thread — exits with Python.

_SRV_PORT    = 7477
_srv_started = False
_srv_lock    = threading.Lock()


def _ensure_server(directory: Path) -> int:
    """Start the background HTTP server if not already running.

    Returns the port on success, 0 on failure. Idempotent — safe to call
    on every HTML write; the daemon thread is created only once per process.
    """
    global _srv_started
    with _srv_lock:
        if _srv_started:
            return _SRV_PORT
        # Port already occupied → assume a previous run's server is alive.
        try:
            with socket.create_connection(("127.0.0.1", _SRV_PORT), timeout=0.4):
                _srv_started = True
                return _SRV_PORT
        except OSError:
            pass
        # Spin up a new server.
        try:
            srv_dir = str(directory)

            class _Silent(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *a, **kw):
                    super().__init__(*a, directory=srv_dir, **kw)
                def log_message(self, *_):
                    pass  # no console noise
                def end_headers(self):
                    # Allow cross-origin fetch from file:// pages.
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-store")
                    super().end_headers()

            httpd = http.server.HTTPServer(("127.0.0.1", _SRV_PORT), _Silent,
                                            bind_and_activate=True)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            import time; time.sleep(0.15)   # let the thread bind before returning
            _srv_started = True
            return _SRV_PORT
        except OSError:
            return 0


def http_url(output_path: Path) -> str:
    """Return the localhost URL for `output_path` (starts the server if needed)."""
    port = _ensure_server(output_path.parent)
    return (f"http://127.0.0.1:{port}/{output_path.name}"
            if port else output_path.as_uri())

# ── Color palette (muted, low-saturation — scientific / Apple aesthetic) ──────

NODE_COLORS_DARK = {
    "room":      "#6B9BD2",
    "door":      "#D4A574",
    "wall":      "#8B9DAF",
    "window":    "#7BC4C4",
    "furniture": "#7DB87D",
    "mep":       "#C47070",
}
NODE_COLORS_LIGHT = {
    "room":      "#4A7FB5",
    "door":      "#B8865A",
    "wall":      "#6B7D8F",
    "window":    "#5AA8A8",
    "furniture": "#5A9B5A",
    "mep":       "#A85050",
}
NODE_RADII = {
    "room": 14, "door": 9, "wall": 8, "window": 8, "furniture": 11, "mep": 10,
}
EDGE_COLORS_DARK = {
    "contained_in":  "#8B9DAF",
    "door_connects": "#D4A574",
    "adjacent":      "#6B9BD2",
    "near":          "#7DB87D",
    "near_wall":     "#C47070",
    "near_window":   "#7BC4C4",
    "blocks":        "#E05252",
    "sightline":     "#9B7BC4",
    "path":          "#5ABEAE",
}
EDGE_DESCRIPTIONS = {
    "contained_in":  "element belongs to room",
    "door_connects": "door links to room",
    "adjacent":      "rooms share a door",
    "near":          "furniture < 3m apart",
    "near_wall":     "furniture < 3m from wall",
    "near_window":   "furniture < 3m from window",
    "blocks":        "object blocks access to another",
    "sightline":     "direct line of sight",
    "path":          "navigable route with distance",
}
EDGE_DASHES = {
    "contained_in":  True,
    "door_connects": False,
    "adjacent":      False,
    "near":          True,
    "near_wall":     [6, 4, 2, 4],
    "near_window":   [6, 4, 2, 4],
    "blocks":        False,
    "sightline":     [6, 4, 2, 4],
    "path":          True,
}
NODE_DESCRIPTIONS = {
    "room":      "A space enclosed by walls and accessible through doors. Rooms define the primary functional zones of the layout and contain placed furniture and MEP elements.",
    "door":      "An opening element connecting two spaces. Doors define the circulation network, determine access paths, and set minimum clearance requirements at thresholds.",
    "wall":      "A structural boundary element that encloses and separates spaces. Walls carry loads, define the room geometry, and host windows and doors.",
    "window":    "An opening in a wall providing natural light and ventilation. Windows influence furniture placement through glare and sightline considerations.",
    "furniture": "A placed object occupying floor area. Each piece requires clearance zones on its working sides for ergonomic access and code compliance.",
    "mep":       "Mechanical, Electrical, or Plumbing element. These carry service zones and access requirements that must remain unobstructed.",
}


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _compute_scale(G):
    """Return (min_x, min_y, scale) that maps layout metres → vis.js pixels."""
    xs, ys = [], []
    for _, data in G.nodes(data=True):
        c = data.get("center")
        if c and c[0] is not None and c[1] is not None:
            xs.append(float(c[0]))
            ys.append(float(c[1]))
    if not xs:
        return 0.0, 0.0, 40.0
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    x_range = max_x - min_x or 1.0
    y_range = max_y - min_y or 1.0
    scale = min(1200.0 / x_range, 800.0 / y_range)
    return min_x, min_y, scale


def _node_xy(data: dict, min_x: float, min_y: float, scale: float,
             fallback_idx: int = 0) -> tuple[float, float]:
    """Canvas (x, y) for a node.  Y is flipped so the plan reads correctly."""
    c = data.get("center")
    if c and c[0] is not None and c[1] is not None:
        x = (float(c[0]) - min_x) * scale
        y = -(float(c[1]) - min_y) * scale
        return round(x, 1), round(y, 1)
    col = fallback_idx % 8
    row = fallback_idx // 8
    return -200.0 + col * 90.0, 300.0 + row * 70.0


# ── Tooltip HTML builders ─────────────────────────────────────────────────────

def _build_tooltip(nid: str, data: dict) -> str:
    ntype = data.get("ntype", "?")
    name  = data.get("name", nid)
    rows = [
        f"<div class='tt-name'>{name}</div>",
        f"<div class='tt-row'><span class='tt-lbl'>type</span><span class='tt-val'>{ntype}</span></div>",
        f"<div class='tt-row'><span class='tt-lbl'>id</span><span class='tt-val tt-muted'>{nid}</span></div>",
    ]
    if ntype == "room":
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>area</span>"
                    f"<span class='tt-val'>{data.get('area', '?')} m\u00b2</span></div>")
    elif ntype == "door":
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>width</span>"
                    f"<span class='tt-val'>{data.get('width', '?')}m</span></div>")
    elif ntype == "wall":
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>type</span>"
                    f"<span class='tt-val'>{data.get('wall_type', '?')}</span></div>")
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>length</span>"
                    f"<span class='tt-val'>{data.get('length', '?')}m</span></div>")
    elif ntype == "window":
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>type</span>"
                    f"<span class='tt-val'>{data.get('window_type', '?')}</span></div>")
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>width</span>"
                    f"<span class='tt-val'>{data.get('width', '?')}m</span></div>")
    elif ntype == "furniture":
        c = data.get("center")
        if c:
            rows.append(f"<div class='tt-row'><span class='tt-lbl'>pos</span>"
                        f"<span class='tt-val'>({c[0]:.1f}, {c[1]:.1f})</span></div>")
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>bbox</span>"
                    f"<span class='tt-val'>{data.get('bbox_w', '?')} \u00d7 {data.get('bbox_d', '?')}m</span></div>")
    elif ntype == "mep":
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>system</span>"
                    f"<span class='tt-val'>{data.get('system', '?')}</span></div>")

    analysis = []
    if "clearance_ok" in data:
        ok = data["clearance_ok"]
        analysis.append(f"<div class='tt-divider'></div>")
        analysis.append(f"<div class='tt-row'><span class='tt-lbl'>clearance</span>"
                        f"<span class='tt-val tt-{'ok' if ok else 'fail'}'>{'OK' if ok else 'FAIL'}</span></div>")
        if not ok:
            analysis.append(f"<div class='tt-row tt-ind'><span class='tt-lbl'>has/needs</span>"
                            f"<span class='tt-val'>{data.get('min_clearance_m', '?')}m / "
                            f"{data.get('required_clearance_m', '?')}m</span></div>")
            md = data.get("move_direction")
            mdist = data.get("move_distance_m")
            if md and mdist:
                analysis.append(f"<div class='tt-row tt-ind'><span class='tt-lbl'>fix</span>"
                                f"<span class='tt-val tt-accent'>move [{md[0]:+.2f}, {md[1]:+.2f}] {mdist}m</span></div>")
    if "reachable" in data:
        ok = data["reachable"]
        analysis.append(f"<div class='tt-row'><span class='tt-lbl'>reachable</span>"
                        f"<span class='tt-val tt-{'ok' if ok else 'fail'}'>{'YES' if ok else 'NO'}</span></div>")
    if "facing_ok" in data:
        ok = data["facing_ok"]
        diff = data.get("angle_diff", "?")
        analysis.append(f"<div class='tt-row'><span class='tt-lbl'>facing</span>"
                        f"<span class='tt-val tt-{'ok' if ok else 'warn'}'>{'OK' if ok else f'off {diff}\u00b0'}</span></div>")

    rows.extend(analysis)
    return f"<div class='tt-box'>{''.join(rows)}</div>"


def _build_edge_title(u: str, v: str, data: dict, G) -> str:
    etype = data.get("etype", "?")
    uname = G.nodes[u].get("name", u)
    vname = G.nodes[v].get("name", v)
    desc  = EDGE_DESCRIPTIONS.get(etype, "")
    rows = [
        f"<div class='tt-name'>{etype}</div>",
        f"<div class='tt-row tt-muted' style='margin-bottom:4px'>{desc}</div>",
        f"<div class='tt-divider'></div>",
        f"<div class='tt-row'><span class='tt-lbl'>from</span><span class='tt-val'>{uname}</span></div>",
        f"<div class='tt-row'><span class='tt-lbl'>to</span><span class='tt-val'>{vname}</span></div>",
    ]
    if "distance_m" in data:
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>distance</span>"
                    f"<span class='tt-val'>{data['distance_m']}m</span></div>")
    if "door_width" in data:
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>door width</span>"
                    f"<span class='tt-val'>{data['door_width']}m</span></div>")
    if "visible" in data:
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>visible</span>"
                    f"<span class='tt-val'>{'Yes' if data['visible'] else 'No'}</span></div>")
    if "reachable" in data:
        rows.append(f"<div class='tt-row'><span class='tt-lbl'>reachable</span>"
                    f"<span class='tt-val'>{'Yes' if data['reachable'] else 'No'}</span></div>")
    return f"<div class='tt-box'>{''.join(rows)}</div>"


# ── Data serialization ────────────────────────────────────────────────────────

def _node_meta(nid: str, data: dict) -> dict:
    """Extract all displayable attributes for the detail panel."""
    SKIP = {"center", "geometry", "ntype", "name"}
    LIST_OK = {"move_direction"}
    meta = {"id": nid}
    for k, v in data.items():
        if k in SKIP:
            continue
        if isinstance(v, (list, tuple)):
            if k in LIST_OK and v:
                meta[k] = [round(x, 3) if isinstance(x, float) else x for x in v]
        elif isinstance(v, dict):
            pass
        elif v is not None:
            meta[k] = round(v, 3) if isinstance(v, float) else v
    return meta


def _serialize_nodes(G, new_ids: set, min_x: float, min_y: float, scale: float) -> list:
    result = []
    fallback_idx = 0
    for nid, data in G.nodes(data=True):
        ntype = data.get("ntype", "unknown")
        c = data.get("center")
        if not (c and c[0] is not None):
            x, y = _node_xy(data, min_x, min_y, scale, fallback_idx)
            fallback_idx += 1
        else:
            x, y = _node_xy(data, min_x, min_y, scale)
        label = data.get("name", nid)
        if len(label) > 16:
            label = label[:14] + "\u2026"
        result.append({
            "id":    nid,
            "label": label,
            "title": _build_tooltip(nid, data),
            "ntype": ntype,
            "x":     x,
            "y":     y,
            "size":  NODE_RADII.get(ntype, 9),
            "_new":  nid in new_ids,
            "_meta": _node_meta(nid, data),
        })
    return result


def _serialize_edges(G, new_ids: set) -> list:
    ENRICH_ETYPES = {"blocks", "sightline", "path"}
    result = []
    for u, v, key, data in G.edges(keys=True, data=True):
        etype = data.get("etype", "unknown")
        eid   = f"{u}__{v}__{etype}__{key}"
        is_new = (etype in ENRICH_ETYPES) or (u in new_ids) or (v in new_ids)
        result.append({
            "id":     eid,
            "from":   u,
            "to":     v,
            "etype":  etype,
            "title":  _build_edge_title(u, v, data, G),
            "dashes": EDGE_DASHES.get(etype, False),
            "_new":   is_new,
        })
    return result


def _build_legend_html(nodes_data: list, edges_data: list) -> str:
    from collections import Counter
    nc = Counter(n["ntype"] for n in nodes_data)
    ec = Counter(e["etype"] for e in edges_data)
    rows = ['<div class="leg-section">Nodes</div>']
    for ntype, color in NODE_COLORS_DARK.items():
        count = nc.get(ntype, 0)
        if not count:
            continue
        rows.append(
            f'<div class="leg-item" data-ft="{ntype}" data-fc="nodes">'
            f'<span class="leg-dot" style="background:{color}"></span>'
            f'<span class="leg-label">{ntype}</span>'
            f'<span class="leg-count">{count}</span>'
            f'</div>'
        )
    rows.append('<div class="leg-section leg-sep">Edges</div>')
    for etype, color in EDGE_COLORS_DARK.items():
        count = ec.get(etype, 0)
        if not count:
            continue
        desc = EDGE_DESCRIPTIONS.get(etype, "")
        rows.append(
            f'<div class="leg-item" data-ft="{etype}" data-fc="edges" title="{desc}">'
            f'<span class="leg-line" style="background:{color}"></span>'
            f'<span class="leg-label">{etype}</span>'
            f'<span class="leg-count">{count}</span>'
            f'</div>'
        )
    return "\n".join(rows)


def _build_stats(G) -> str:
    from collections import Counter
    counts = Counter(d.get("ntype", "?") for _, d in G.nodes(data=True))
    return "  \u00b7  ".join(f"{t}: {c}" for t, c in sorted(counts.items()))


# ── HTML template ─────────────────────────────────────────────────────────────
# Uses %%SLOT%% placeholders to avoid conflict with JS curly braces.

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%%TITLE%%</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/dist/vis-network.min.css" integrity="sha512-WgxfT5LWjfszlPHXRmBWHkV2eceiWTOBvrKCNbdgDYTHrT2AeLCGbF4sZlZw3UMN3WtL0tGUoIAKsu8mllg/XA==" crossorigin="anonymous" referrerpolicy="no-referrer">
<style>
/* ── Custom properties ────────────────────────────────────────── */
:root[data-theme="dark"] {
  --bg:          #0a0a0a;
  --panel-bg:    rgba(255,255,255,0.05);
  --panel-bd:    rgba(255,255,255,0.09);
  --text:        #e0e0e0;
  --muted:       #606060;
  --accent:      #007AFF;
  --accent-dim:  rgba(0,122,255,0.13);
  --ok:          #34C759;
  --fail:        #FF453A;
  --warn:        #FF9F0A;
}
:root[data-theme="light"] {
  --bg:          #f5f5f7;
  --panel-bg:    rgba(255,255,255,0.78);
  --panel-bd:    rgba(0,0,0,0.07);
  --text:        #1d1d1f;
  --muted:       #ababab;
  --accent:      #007AFF;
  --accent-dim:  rgba(0,122,255,0.10);
  --ok:          #28a745;
  --fail:        #dc3545;
  --warn:        #fd7e14;
}

/* ── Reset ────────────────────────────────────────────────────── */
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
html,body {
  width:100%; height:100%; overflow:hidden;
  font-family: -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",system-ui,sans-serif;
  background: var(--bg);
  color: var(--text);
  transition: background .35s ease, color .35s ease;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
#graph-container { position:fixed; inset:0; }

/* ── Glass panel base ─────────────────────────────────────────── */
.panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-bd);
  border-radius: 10px;
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  transition: background .35s, border-color .35s;
}

/* ── Title bar ────────────────────────────────────────────────── */
.title-bar {
  position:fixed; top:16px; left:16px; z-index:200;
  padding:6px 14px;
  font-size:11px; font-weight:500; letter-spacing:.015em;
  color:var(--muted);
  pointer-events:none;
}

/* ── Controls top-right ───────────────────────────────────────── */
.controls {
  position:fixed; top:16px; right:16px; z-index:200;
  display:flex; gap:7px; align-items:center;
}
.ctrl-btn {
  padding:6px 12px;
  font-size:11px; font-weight:500; letter-spacing:.01em;
  color:var(--text);
  background:var(--panel-bg);
  border:1px solid var(--panel-bd);
  border-radius:8px;
  cursor:pointer;
  backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);
  transition:background .2s, border-color .2s, color .2s;
  white-space:nowrap;
}
.ctrl-btn:hover { background:var(--panel-bd); }
.ctrl-btn.live-on {
  color:#34C759;
  border-color:rgba(52,199,89,.35);
  background:rgba(52,199,89,.07);
}

/* ── Legend ───────────────────────────────────────────────────── */
.legend {
  position:fixed; top:50%; left:16px; z-index:200;
  transform:translateY(-50%);
  width:148px; max-height:82vh;
  overflow-y:auto; padding:8px 0;
  scrollbar-width:none;
}
.legend::-webkit-scrollbar { display:none; }

.leg-section {
  padding:5px 13px 3px;
  font-size:9px; font-weight:600; letter-spacing:.09em;
  text-transform:uppercase; color:var(--muted);
}
.leg-sep {
  margin-top:4px; padding-top:9px;
  border-top:1px solid var(--panel-bd);
}
.leg-item {
  display:flex; align-items:center; gap:7px;
  padding:4px 13px;
  font-size:10.5px; color:var(--text);
  cursor:pointer; user-select:none;
  transition:background .15s, opacity .2s;
}
.leg-item:hover { background:var(--panel-bd); }
.leg-item.leg-on  { background:var(--accent-dim); }
.leg-item.leg-dim { opacity:.25; }
.leg-dot  { width:7px; height:7px; border-radius:50%; flex-shrink:0; opacity:.9; }
.leg-line { width:14px; height:1.5px; border-radius:1px; flex-shrink:0; opacity:.7; }
.leg-label { flex:1; }
.leg-count { font-size:9px; color:var(--muted); font-variant-numeric:tabular-nums; }

/* ── Detail panel (right side, click-to-open) ─────────────────── */
.detail-panel {
  position:fixed; right:16px; top:50%; z-index:200;
  transform:translateY(-50%);
  width:248px; max-height:80vh;
  overflow:hidden;
  display:none;
}
.dp-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 14px 9px;
  border-bottom:1px solid var(--panel-bd);
  position:sticky; top:0;
  background:var(--panel-bg);
  backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);
}
.dp-type-chip {
  font-size:9px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
  padding:2px 7px; border-radius:5px; margin-right:6px;
}
.dp-title-row { display:flex; align-items:center; flex:1; min-width:0; }
.dp-name { font-size:12px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.dp-close {
  background:none; border:none; cursor:pointer;
  color:var(--muted); font-size:13px; line-height:1;
  padding:3px 6px; border-radius:5px;
  transition:background .15s, color .15s;
  flex-shrink:0;
}
.dp-close:hover { background:var(--panel-bd); color:var(--text); }

.dp-scroll { overflow-y:auto; max-height:calc(80vh - 48px); padding:10px 14px 14px; scrollbar-width:thin; scrollbar-color:var(--panel-bd) transparent; }

.dp-desc { font-size:10px; color:var(--muted); line-height:1.55; margin-bottom:10px; }
.dp-section {
  font-size:9px; font-weight:600; letter-spacing:.09em; text-transform:uppercase;
  color:var(--muted); margin:10px 0 5px;
}
.dp-section:first-child { margin-top:0; }
.dp-row { display:flex; gap:6px; align-items:baseline; margin-bottom:3px; }
.dp-lbl { font-size:9.5px; color:var(--muted); min-width:88px; flex-shrink:0; letter-spacing:.01em; }
.dp-val { font-size:10.5px; word-break:break-word; }
.dp-val.ok   { color:var(--ok);   font-weight:500; }
.dp-val.fail { color:var(--fail); font-weight:500; }
.dp-val.warn { color:var(--warn); font-weight:500; }
.dp-val.accent { color:var(--accent); }
.dp-divider { height:1px; background:var(--panel-bd); margin:8px 0; }

.dp-neighbor {
  display:flex; align-items:center; gap:8px;
  padding:4px 0;
  border-bottom:1px solid var(--panel-bd);
  cursor:pointer;
  transition:background .1s;
}
.dp-neighbor:last-child { border-bottom:none; }
.dp-neighbor:hover { background:var(--panel-bd); margin:0 -4px; padding:4px 4px; border-radius:5px; }
.dp-ndot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.dp-nname { flex:1; font-size:10px; }
.dp-etype { font-size:9px; color:var(--muted); }

/* ── Status bars ──────────────────────────────────────────────── */
.stats-bar, .updated-bar {
  position:fixed; bottom:16px; z-index:200;
  padding:5px 12px;
  font-size:10px; letter-spacing:.01em;
  color:var(--muted);
  pointer-events:none;
}
.stats-bar   { left:16px; }
.updated-bar { right:16px; }

/* ── vis.js tooltip override ─────────────────────────────────── */
.vis-tooltip {
  background:var(--panel-bg) !important;
  border:1px solid var(--panel-bd) !important;
  border-radius:10px !important;
  color:var(--text) !important;
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif !important;
  font-size:11px !important; line-height:1.55 !important;
  padding:0 !important;
  box-shadow:0 10px 40px rgba(0,0,0,.4) !important;
  backdrop-filter:blur(24px) saturate(180%) !important;
  -webkit-backdrop-filter:blur(24px) saturate(180%) !important;
  max-width:230px; overflow:hidden;
}
.tt-box  { padding:10px 12px; }
.tt-name { font-weight:600; font-size:12px; margin-bottom:5px; }
.tt-row  { display:flex; gap:6px; align-items:baseline; margin-bottom:2px; }
.tt-ind  { padding-left:10px; }
.tt-lbl  { font-size:9.5px; color:var(--muted); min-width:52px; letter-spacing:.01em; flex-shrink:0; }
.tt-val  { font-size:10.5px; }
.tt-muted  { color:var(--muted); font-size:10px; }
.tt-ok     { color:var(--ok);   font-weight:500; }
.tt-fail   { color:var(--fail); font-weight:500; }
.tt-warn   { color:var(--warn); font-weight:500; }
.tt-accent { color:var(--accent); font-weight:500; }
.tt-divider { height:1px; background:var(--panel-bd); margin:5px 0; }

/* ── New-element badge ────────────────────────────────────────── */
.new-badge {
  position:fixed; z-index:300;
  background:var(--accent); color:#fff;
  font-size:7px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
  padding:1px 4px; border-radius:4px;
  pointer-events:none;
  opacity:1; transition:opacity 2.5s ease 1.5s;
}
.new-badge.fade { opacity:0; }
</style>
</head>
<body>

<div class="title-bar panel">%%TITLE%%</div>

<div class="controls">
  <button class="ctrl-btn live-on" id="liveBtn">Live &#x25cf;</button>
  <button class="ctrl-btn" id="themeBtn">Light</button>
</div>

<div class="legend panel" id="legend">
%%LEGEND_HTML%%
</div>

<!-- Detail panel: opens on node click -->
<div class="detail-panel panel" id="detailPanel">
  <div class="dp-header">
    <div class="dp-title-row">
      <span class="dp-type-chip" id="dpChip"></span>
      <span class="dp-name" id="dpName"></span>
    </div>
    <button class="dp-close" id="dpClose">&#x2715;</button>
  </div>
  <div class="dp-scroll" id="dpScroll"></div>
</div>

<div class="stats-bar panel">%%STATS%%</div>
<div class="updated-bar panel" id="updBar">Updated %%TS%%</div>

<div id="graph-container"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js" integrity="sha512-LnvoEWDFrqGHlHmDD2101OrLcbsfkrzoSpvtSQtxK3RMnRV0eOkhhBN2dXHKRrUU8p2DGRTk35n4O8nWSVe1mQ==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<script>
const NODES_RAW  = %%NODES_JSON%%;
const EDGES_RAW  = %%EDGES_JSON%%;
const CLR_DARK   = %%CLR_DARK_JSON%%;
const CLR_LIGHT  = %%CLR_LIGHT_JSON%%;
const ECLR_DARK  = %%ECLR_DARK_JSON%%;
const NODE_DESCS = %%NODE_DESCS_JSON%%;
const EDGE_DESCS = %%EDGE_DESCS_JSON%%;
const PAGE_TS    = "%%PAGE_TS%%";  // ms-precision build timestamp — change detection anchor

// ── Build lookup indexes ───────────────────────────────────────
const NODE_IDX = {};
NODES_RAW.forEach(n => NODE_IDX[n.id] = n);

// EDGE_IDX[nodeId] = [{etype, neighborId}]
const EDGE_IDX = {};
EDGES_RAW.forEach(e => {
  (EDGE_IDX[e.from] = EDGE_IDX[e.from] || []).push({ etype: e.etype, id: e.to });
  (EDGE_IDX[e.to]   = EDGE_IDX[e.to]   || []).push({ etype: e.etype, id: e.from });
});

// ── Theme ──────────────────────────────────────────────────────
const THEME_KEY = "sgTheme";
let theme = localStorage.getItem(THEME_KEY) || "dark";
setTheme(theme, false);

function setTheme(t, updateNetwork) {
  theme = t;
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
  document.getElementById("themeBtn").textContent = t === "dark" ? "Light" : "Dark";
  if (updateNetwork && typeof nodesDS !== "undefined") {
    nodesDS.update(nodesDS.get().map(n => ({
      id: n.id,
      color: nodeColor(n.ntype, false),
      font: { ...n.font, color: fontColor() },
    })));
    edgesDS.update(edgesDS.get().map(e => ({
      id: e.id,
      color: edgeColor(e.etype, false),
    })));
  }
}
function fontColor() { return theme === "dark" ? "#b8b8b8" : "#505050"; }

// ── Color builders ─────────────────────────────────────────────
function nodeColor(ntype, isNew) {
  const pal    = theme === "dark" ? CLR_DARK : CLR_LIGHT;
  const fill   = pal[ntype]  || "#888";
  const border = theme === "dark" ? "rgba(255,255,255,0.13)" : "rgba(0,0,0,0.09)";
  const accent = "#007AFF";
  if (isNew) return {
    background: fill, border: accent,
    highlight: { background: fill, border: accent },
    hover:     { background: fill, border: accent },
  };
  return {
    background: fill, border,
    highlight: { background: fill, border: accent },
    hover:     { background: fill, border },
  };
}
function edgeColor(etype, isNew) {
  const base = ECLR_DARK[etype] || "#666";
  if (isNew) return { color: "#007AFF", highlight: "#007AFF", hover: "#007AFF", opacity: 0.9 };
  return { color: base, highlight: base, hover: base, opacity: 0.4 };
}

// ── DataSets ───────────────────────────────────────────────────
const FONT_FACE = '-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif';
const nodesDS = new vis.DataSet(NODES_RAW.map(n => ({
  id:    n.id,
  label: n.label,
  title: n.title,
  ntype: n.ntype,
  x: n.x, y: n.y,
  _ox: n.x, _oy: n.y,   // original architectural position
  fixed: false,          // allow dragging
  size:  n.size,
  shape: "dot",
  color: nodeColor(n.ntype, n._new),
  borderWidth:         n._new ? 2.0 : 0.9,
  borderWidthSelected: 2.2,
  shadow: { enabled: true, size: 5, x: 0, y: 2, color: "rgba(0,0,0,0.13)" },
  font:  { size: 9, face: FONT_FACE, color: fontColor(), align: "center", vadjust: 2 },
  _new: n._new,
})));

const edgesDS = new vis.DataSet(EDGES_RAW.map(e => ({
  id:    e.id,
  from:  e.from,
  to:    e.to,
  title: e.title,
  etype: e.etype,
  dashes: e.dashes,
  color: edgeColor(e.etype, e._new),
  width:          e._new ? 1.8 : 0.7,
  selectionWidth: 2.0,
  smooth: { type: "continuous", roundness: 0.3 },
  _new: e._new,
})));

// ── Network ────────────────────────────────────────────────────
const network = new vis.Network(
  document.getElementById("graph-container"),
  { nodes: nodesDS, edges: edgesDS },
  {
    physics: { enabled: false },
    interaction: {
      hover: true, tooltipDelay: 130,
      dragNodes: true, dragView: true, zoomView: true,
      multiselect: false,
    },
    nodes: { shape: "dot" },
    edges: { smooth: { type: "continuous", roundness: 0.3 } },
  }
);

// ── Reload state — detect actual content changes across reloads ─
const _prevTS = sessionStorage.getItem("sg_ts");
const _isNewContent = _prevTS !== PAGE_TS;
sessionStorage.setItem("sg_ts", PAGE_TS);

let _noChangeRuns = 0;
if (_isNewContent) {
  sessionStorage.setItem("sg_nc", "0");
} else {
  _noChangeRuns = parseInt(sessionStorage.getItem("sg_nc") || "0") + 1;
  sessionStorage.setItem("sg_nc", String(_noChangeRuns));
}

// Fit viewport (no animation) — restore zoom/pan on no-change reloads
network.once("afterDrawing", () => {
  const sv = sessionStorage.getItem("sg_view");
  if (sv && !_isNewContent) {
    try {
      const v = JSON.parse(sv);
      network.moveTo({ position: v.pos, scale: v.scale, animation: false });
    } catch(e) { network.fit({ animation: false }); }
  } else {
    network.fit({ animation: false });
  }
  if (_isNewContent) spawnBadges();
});

// ── Drag: spring snap-back to original architectural position ──
network.on("dragEnd", params => {
  if (!params.nodes.length) return;
  params.nodes.forEach(nid => {
    const n = nodesDS.get(nid);
    if (!n) return;
    const ox = n._ox, oy = n._oy;
    const cur = network.getPositions([nid])[nid];
    if (!cur) return;
    const dur = 550;
    let t0 = null;
    const sx = cur.x, sy = cur.y;
    function step(ts) {
      if (!t0) t0 = ts;
      const p = Math.min((ts - t0) / dur, 1);
      const ease = 1 - Math.pow(1 - p, 3);   // ease-out cubic
      network.moveNode(nid, sx + (ox - sx) * ease, sy + (oy - sy) * ease);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
});

// ── Theme toggle ───────────────────────────────────────────────
document.getElementById("themeBtn").addEventListener("click", () => {
  setTheme(theme === "dark" ? "light" : "dark", true);
});

// ── Legend filtering ───────────────────────────────────────────
const filters = { nodes: new Set(), edges: new Set() };

document.querySelectorAll(".leg-item").forEach(el => {
  el.addEventListener("click", ev => {
    const type = el.dataset.ft;
    const cat  = el.dataset.fc;
    const set  = filters[cat];
    if (ev.shiftKey) {
      set.has(type) ? set.delete(type) : set.add(type);
    } else {
      if (set.size === 1 && set.has(type)) set.clear();
      else { set.clear(); set.add(type); }
    }
    applyFilters();
    syncLegend();
  });
});

function applyFilters() {
  const nf = filters.nodes.size > 0;
  const ef = filters.edges.size > 0;
  const any = nf || ef;

  nodesDS.update(nodesDS.get().map(n => ({
    id: n.id,
    opacity: (!nf || filters.nodes.has(n.ntype)) ? 1.0 : 0.06,
  })));

  edgesDS.update(edgesDS.get().map(e => {
    const fn = nodesDS.get(e.from);
    const tn = nodesDS.get(e.to);
    const nodeOk = !nf || (
      (fn && filters.nodes.has(fn.ntype)) ||
      (tn && filters.nodes.has(tn.ntype))
    );
    const edgeOk = !ef || filters.edges.has(e.etype);
    const match = nodeOk && edgeOk;
    return { id: e.id, opacity: match ? (any ? 0.85 : 0.4) : 0.04 };
  }));
}

function syncLegend() {
  document.querySelectorAll(".leg-item").forEach(el => {
    const set = filters[el.dataset.fc];
    el.classList.toggle("leg-on",  set.has(el.dataset.ft));
    el.classList.toggle("leg-dim", set.size > 0 && !set.has(el.dataset.ft));
  });
}

// ── Detail panel ───────────────────────────────────────────────
function fmtVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return "[" + v.map(x => typeof x === "number" ? x.toFixed(2) : x).join(", ") + "]";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

function openPanel(nid) {
  const raw = NODE_IDX[nid];
  if (!raw) return;
  const meta  = raw._meta || {};
  const pal   = theme === "dark" ? CLR_DARK : CLR_LIGHT;
  const color = pal[raw.ntype] || "#888";

  // Header
  const chip = document.getElementById("dpChip");
  chip.textContent = raw.ntype;
  chip.style.background = color + "22";
  chip.style.color = color;
  document.getElementById("dpName").textContent = raw.label;

  // Body
  let h = "";

  // Description
  const desc = NODE_DESCS[raw.ntype];
  if (desc) h += `<div class="dp-desc">${desc}</div>`;

  // Properties — all metadata from the JSON
  const ANALYSIS_KEYS = new Set(["clearance_ok","reachable","facing_ok","min_clearance_m","required_clearance_m","move_direction","move_distance_m","angle_diff"]);
  const SKIP_KEYS     = new Set(["id"]);
  const propEntries   = Object.entries(meta).filter(([k]) => !ANALYSIS_KEYS.has(k) && !SKIP_KEYS.has(k));

  if (propEntries.length) {
    h += `<div class="dp-section">Properties</div>`;
    propEntries.forEach(([k, v]) => {
      h += `<div class="dp-row"><span class="dp-lbl">${k.replace(/_/g," ")}</span><span class="dp-val">${fmtVal(v)}</span></div>`;
    });
  }

  // Analysis (if any enrichment attrs present)
  const analysisEntries = Object.entries(meta).filter(([k]) => ANALYSIS_KEYS.has(k));
  if (analysisEntries.length) {
    h += `<div class="dp-divider"></div>`;
    h += `<div class="dp-section">Analysis</div>`;

    if (meta.clearance_ok !== undefined) {
      const ok = meta.clearance_ok;
      h += `<div class="dp-row"><span class="dp-lbl">clearance</span><span class="dp-val ${ok?'ok':'fail'}">${ok ? 'OK' : 'FAIL'}</span></div>`;
      if (!ok && meta.min_clearance_m !== undefined)
        h += `<div class="dp-row"><span class="dp-lbl">has / needs</span><span class="dp-val">${fmtVal(meta.min_clearance_m)}m / ${fmtVal(meta.required_clearance_m)}m</span></div>`;
      if (!ok && meta.move_direction)
        h += `<div class="dp-row"><span class="dp-lbl">suggested fix</span><span class="dp-val accent">move ${fmtVal(meta.move_direction)} · ${fmtVal(meta.move_distance_m)}m</span></div>`;
    }
    if (meta.reachable !== undefined) {
      const ok = meta.reachable;
      h += `<div class="dp-row"><span class="dp-lbl">reachable</span><span class="dp-val ${ok?'ok':'fail'}">${ok ? 'YES' : 'NO'}</span></div>`;
    }
    if (meta.facing_ok !== undefined) {
      const ok = meta.facing_ok;
      h += `<div class="dp-row"><span class="dp-lbl">facing</span><span class="dp-val ${ok?'ok':'warn'}">${ok ? 'OK' : 'off ' + fmtVal(meta.angle_diff) + '°'}</span></div>`;
    }
  }

  // Connections
  const conns = EDGE_IDX[nid] || [];
  if (conns.length) {
    h += `<div class="dp-divider"></div>`;
    h += `<div class="dp-section">Connections (${conns.length})</div>`;
    conns.slice(0, 18).forEach(c => {
      const nb      = NODE_IDX[c.id];
      const nbColor = (theme === "dark" ? CLR_DARK : CLR_LIGHT)[nb?.ntype] || "#888";
      const eColor  = ECLR_DARK[c.etype] || "#888";
      const nbLabel = nb ? nb.label : c.id;
      h += `<div class="dp-neighbor" data-nid="${c.id}">`;
      h += `<span class="dp-ndot" style="background:${nbColor}"></span>`;
      h += `<span class="dp-nname">${nbLabel}</span>`;
      h += `<span class="dp-etype" style="color:${eColor}">${c.etype}</span>`;
      h += `</div>`;
    });
    if (conns.length > 18) h += `<div style="font-size:9px;color:var(--muted);margin-top:4px">+${conns.length - 18} more</div>`;
  }

  document.getElementById("dpScroll").innerHTML = h;

  // Click neighbor rows to jump to that node
  document.querySelectorAll(".dp-neighbor[data-nid]").forEach(row => {
    row.addEventListener("click", () => {
      const tid = row.dataset.nid;
      network.selectNodes([tid]);
      network.focus(tid, { animation: { duration: 400, easingFunction: "easeInOutQuad" }, scale: Math.max(network.getScale(), 1.2) });
      openPanel(tid);
    });
  });

  document.getElementById("detailPanel").style.display = "block";
}

// Click node → open panel; click background → close
network.on("click", params => {
  if (params.nodes.length) {
    openPanel(params.nodes[0]);
  } else {
    document.getElementById("detailPanel").style.display = "none";
  }
});

// Double-click node → focus + zoom
network.on("doubleClick", params => {
  if (params.nodes.length) {
    network.focus(params.nodes[0], {
      scale: Math.max(network.getScale() * 1.6, 1.8),
      animation: { duration: 400, easingFunction: "easeInOutQuad" },
    });
  }
});

document.getElementById("dpClose").addEventListener("click", () => {
  document.getElementById("detailPanel").style.display = "none";
  network.unselectAll();
});

// ── New-element animation ──────────────────────────────────────
function spawnBadges() {
  const newNodes = NODES_RAW.filter(n => n._new).map(n => n.id);
  const newEdges = EDGES_RAW.filter(e => e._new).map(e => e.id);

  newNodes.forEach(id => {
    const pos = network.getPositions([id])[id];
    if (!pos) return;
    const dp = network.canvasToDOM(pos);
    const badge = document.createElement("div");
    badge.className = "new-badge";
    badge.textContent = "new";
    badge.style.left = (dp.x + 9) + "px";
    badge.style.top  = (dp.y - 16) + "px";
    document.body.appendChild(badge);
    requestAnimationFrame(() => badge.classList.add("fade"));
    setTimeout(() => badge.remove(), 4500);
  });

  if (newNodes.length || newEdges.length) {
    setTimeout(() => {
      nodesDS.update(newNodes.map(id => {
        const n = nodesDS.get(id);
        return { id, color: nodeColor(n ? n.ntype : "unknown", false), borderWidth: 0.9 };
      }));
      edgesDS.update(newEdges.map(id => {
        const e = edgesDS.get(id);
        return { id, color: edgeColor(e ? e.etype : "unknown", false), width: 0.7 };
      }));
    }, 4000);
  }
}

// ── Live refresh — dual-mode with adaptive backoff ───────────
// 1. Try smart detection via localhost HTTP server (compare PAGE_TS).
// 2. If server unreachable → blind location.reload() which always
//    re-reads the file from disk, even on file:// origins.
// 3. sessionStorage tracks consecutive no-change reloads to back off
//    and avoid rapid flickering when the agent is idle.
//    Resets to fast polling the instant content actually changes.

const _SRV_URL = "http://127.0.0.1:7477/"
  + location.href.split("/").pop().split("?")[0].split("#")[0];
// Adaptive: 2 s when fresh, backs off +2 s per no-change, cap 10 s
const _POLL_MS = Math.min(2000 + _noChangeRuns * 2000, 10000);
let liveTimer  = null;
let _checking  = false;

function _saveView() {
  try {
    sessionStorage.setItem("sg_view", JSON.stringify({
      pos: network.getViewPosition(),
      scale: network.getScale(),
    }));
  } catch(e) {}
}

function _checkForUpdate() {
  if (_checking) return;
  _checking = true;
  _saveView();

  fetch(_SRV_URL + "?_t=" + Date.now(), { cache: "no-store" })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.text(); })
    .then(html => {
      _checking = false;
      const m = html.match(/const PAGE_TS\\s*=\\s*"(\\d+)"/);
      if (m && m[1] !== PAGE_TS) location.reload();
      // Server reachable, content unchanged — do nothing (no flicker).
    })
    .catch(() => {
      _checking = false;
      // Server unreachable (file:// or server down).
      // Blind reload — the browser re-reads the file from disk.
      // The adaptive backoff (_POLL_MS) prevents rapid flickering.
      location.reload();
    });
}

function _startLive() {
  if (liveTimer) return;
  liveTimer = setInterval(_checkForUpdate, _POLL_MS);
  const btn = document.getElementById("liveBtn");
  btn.textContent = "Live \u25cf";
  btn.classList.add("live-on");
}

function _stopLive() {
  clearInterval(liveTimer);
  liveTimer = null;
  const btn = document.getElementById("liveBtn");
  btn.textContent = "Live";
  btn.classList.remove("live-on");
}

// Active by default.
_startLive();

document.getElementById("liveBtn").addEventListener("click", () => {
  if (liveTimer) _stopLive(); else _startLive();
});
</script>
</body>
</html>"""


# ── Core rendering ────────────────────────────────────────────────────────────

def _render_html(G, title: str, new_ids: set, output_path: Path) -> Path:
    """Serialize G into the HTML template and write to output_path."""
    # Ensure the HTTP server is running so the browser can poll via localhost.
    _ensure_server(output_path.parent)

    min_x, min_y, scale = _compute_scale(G)
    nodes_data = _serialize_nodes(G, new_ids, min_x, min_y, scale)
    edges_data = _serialize_edges(G, new_ids)
    legend_html = _build_legend_html(nodes_data, edges_data)
    stats_text  = _build_stats(G)
    timestamp   = datetime.now().strftime("%H:%M:%S")
    short_title = f"{title}  —  {G.number_of_nodes()} nodes  ·  {G.number_of_edges()} edges"

    page_ts = str(int(datetime.now().timestamp() * 1000))

    html = _HTML_TEMPLATE
    html = html.replace("%%TITLE%%",        short_title)
    html = html.replace("%%LEGEND_HTML%%",  legend_html)
    html = html.replace("%%STATS%%",        stats_text)
    html = html.replace("%%TS%%",           timestamp)
    html = html.replace("%%PAGE_TS%%",      page_ts)
    html = html.replace("%%NODES_JSON%%",   json.dumps(nodes_data, ensure_ascii=False))
    html = html.replace("%%EDGES_JSON%%",   json.dumps(edges_data, ensure_ascii=False))
    html = html.replace("%%CLR_DARK_JSON%%",   json.dumps(NODE_COLORS_DARK))
    html = html.replace("%%CLR_LIGHT_JSON%%",  json.dumps(NODE_COLORS_LIGHT))
    html = html.replace("%%ECLR_DARK_JSON%%",  json.dumps(EDGE_COLORS_DARK))
    html = html.replace("%%NODE_DESCS_JSON%%", json.dumps(NODE_DESCRIPTIONS))
    html = html.replace("%%EDGE_DESCS_JSON%%", json.dumps(EDGE_DESCRIPTIONS))

    output_path.write_text(html, encoding="utf-8")
    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def build_interactive_graph(
    layout_or_graph,
    title: str = "Spatial Graph",
    output_path: Path | None = None,
    new_ids: set | None = None,
) -> Path:
    """Generate the interactive HTML from a layout dict or nx.MultiGraph."""
    import networkx as nx
    if isinstance(layout_or_graph, dict):
        G = build_graph_from_layout(layout_or_graph)
    else:
        G = layout_or_graph

    if output_path is None:
        output_path = Path(__file__).parent / "view_graph" / "spatial_graph_interactive.html"

    return _render_html(G, title, new_ids or set(), output_path)


def update_from_enriched_graph(
    G_enriched,
    output_path: Path | None = None,
    extra_new_ids: set | None = None,
) -> Path:
    """Regenerate the HTML with an enriched graph, marking new elements.

    extra_new_ids: node IDs already highlighted from a prior add_objects step
    (carried forward so placement highlights survive into the enrich step).
    """
    ENRICH_ETYPES = {"blocks", "sightline", "path"}
    new_ids: set[str] = set(extra_new_ids or [])
    for u, v, data in G_enriched.edges(data=True):
        if data.get("etype") in ENRICH_ETYPES:
            new_ids.add(u)
            new_ids.add(v)

    if output_path is None:
        output_path = Path(__file__).parent / "view_graph" / "spatial_graph_interactive.html"

    return _render_html(G_enriched, "Spatial Graph", new_ids, output_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def find_layout(name: str) -> Path:
    layout_dir = Path(__file__).parent.parent / "layout"
    for f in layout_dir.rglob("*.json"):
        if name in f.stem and "backup" not in f.name:
            return f
    raise FileNotFoundError(f"No layout matching '{name}' in {layout_dir}")


def main():
    args = sys.argv[1:]

    if "--open" in args:
        path = Path(__file__).parent / "view_graph" / "spatial_graph_interactive.html"
        if path.exists():
            webbrowser.open(http_url(path))
        else:
            print(f"File not found: {path}")
        return

    if "--session" in args:
        layout_path = Path(__file__).parent.parent / "workspace" / "session_active.json"
        if not layout_path.exists():
            print(f"No active session at: {layout_path}")
            sys.exit(1)
        title = "Session Active"
    else:
        name = args[0] if args else "industrial_005"
        layout_path = find_layout(name)
        title = layout_path.stem

    with open(layout_path, "r", encoding="utf-8") as f:
        layout = json.load(f)

    print(f"Layout : {layout_path.name}")
    print(f"  Rooms    : {len(layout.get('rooms', []))}")
    print(f"  Doors    : {len(layout.get('doors', []))}")
    print(f"  Walls    : {len(layout.get('structure', []))}")
    print(f"  Windows  : {len(layout.get('windows', []))}")
    print(f"  Furniture: {len(layout.get('furniture', []))}")
    print(f"  MEP      : {len(layout.get('mep', []))}")

    out = build_interactive_graph(layout, title=f"Spatial Graph — {title}")
    url = http_url(out)
    print(f"\nInteractive graph: {url}")
    webbrowser.open(url)

    # Keep the process alive so the HTTP server keeps serving.
    # When invoked from the agent pipeline (graph.py), the long-running
    # main.py process keeps the daemon alive instead.
    print("Serving — press Ctrl+C to stop.")
    try:
        threading.Event().wait()   # block forever, Ctrl+C to exit
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
