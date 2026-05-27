"""
GHPython component: Computes shortest path through doors and draws it in the
Rhino viewport. Self-contained — does NOT depend on shortest_path output.

INPUTS:
    layout_json  (str)   - Layout JSON string. Falls back to disk file if empty.
    target_room  (str)   - Destination room name (e.g. "bedroom1").
    start_room   (str)   - Origin room name. If empty, uses layout's "start_room".
    show_preview (bool)  - Toggle the live viewport overlay (default True).

OUTPUTS:
    polyline  (PolylineCurve) - Path through door positions.
    points    (list)          - Individual points along the path.
    info      (str)           - Description / debug status.
"""

import json
from collections import deque
import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg
from System.Drawing import Color


LAYOUT_FILE_FALLBACK = r"C:\IAAC Repositories 2026\AIA26_Studio\layout_input\layout_schema.json"
STICKY_KEY = "team_03_path_ramon_display"


# ---------- Overlay cleanup ----------
prev = sc.sticky.get(STICKY_KEY)
if prev is not None:
    try:
        prev.Dispose()
    except Exception:
        pass
    sc.sticky[STICKY_KEY] = None

# Default toggle
try:
    _ = show_preview
    if show_preview is None:
        show_preview = True
except NameError:
    show_preview = True


# ---------- Helpers ----------
def _coerce_to_string(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return "\n".join(str(v) for v in value)
    except TypeError:
        return str(value)


def _load_layout_text(wired_value):
    try:
        candidate = _coerce_to_string(wired_value)
        if candidate and candidate.strip():
            json.loads(candidate)
            return candidate, "wire"
    except Exception:
        pass
    try:
        with open(LAYOUT_FILE_FALLBACK, "r") as f:
            text = f.read()
        json.loads(text)
        return text, "disk fallback"
    except Exception:
        return None, None


def _room_id_by_name(layout, name):
    for r in layout.get("rooms", []):
        if r.get("name") == name or r.get("id") == name:
            return r.get("id")
    return None


def _room_name_by_id(layout, rid):
    for r in layout.get("rooms", []):
        if r.get("id") == rid:
            return r.get("name", rid)
    return rid


def _build_graph(layout):
    graph = {}
    for r in layout.get("rooms", []):
        graph[r["id"]] = []
    for d in layout.get("doors", []):
        c = d.get("connects", [])
        if len(c) != 2:
            continue
        r1, r2 = c
        if r1 not in graph or r2 not in graph:
            continue
        graph[r1].append({"room": r2, "door": d["id"], "position": d["position"]})
        graph[r2].append({"room": r1, "door": d["id"], "position": d["position"]})
    return graph


def _bfs_path(graph, start_id, target_id):
    if start_id == target_id:
        return []
    visited = {start_id}
    parents = {start_id: (None, None)}  # node -> (prev_node, door_id)
    queue = deque([start_id])
    while queue:
        cur = queue.popleft()
        for nb in graph.get(cur, []):
            if nb["room"] in visited:
                continue
            visited.add(nb["room"])
            parents[nb["room"]] = (cur, nb["door"])
            if nb["room"] == target_id:
                doors = []
                node = target_id
                while parents[node][0] is not None:
                    doors.append(parents[node][1])
                    node = parents[node][0]
                doors.reverse()
                return doors
            queue.append(nb["room"])
    return None  # unreachable


def _room_centroid(layout, room_name):
    for r in layout.get("rooms", []):
        if r.get("name") == room_name or r.get("id") == room_name:
            geom = r.get("geometry")
            if geom and len(geom) > 0:
                xs = [p[0] for p in geom]
                ys = [p[1] for p in geom]
                return [sum(xs) / len(xs), sum(ys) / len(ys)]
    rid = _room_id_by_name(layout, room_name)
    if rid:
        connected = [d["position"] for d in layout.get("doors", []) if rid in d.get("connects", [])]
        if connected:
            ax = sum(p[0] for p in connected) / len(connected)
            ay = sum(p[1] for p in connected) / len(connected)
            return [ax, ay]
    return None


def draw_overlay(pts):
    try:
        disp = Rhino.Display.CustomDisplay(True)
    except Exception as e:
        return "CustomDisplay constructor failed: {}".format(e)

    line_color = Color.FromArgb(255, 80, 220, 120)
    pt_color = Color.FromArgb(255, 255, 220, 0)

    try:
        if len(pts) >= 2:
            pl_curve = rg.Polyline(pts).ToPolylineCurve()
            try:
                disp.AddCurve(pl_curve, line_color, 5)
            except Exception:
                # Fallback: draw each segment as a separate line
                for i in range(len(pts) - 1):
                    disp.AddLine(rg.Line(pts[i], pts[i + 1]), line_color, 5)
    except Exception as e:
        return "polyline draw failed: {}".format(e)

    try:
        for p in pts:
            disp.AddPoint(p, pt_color)
    except Exception as e:
        return "AddPoint failed: {}".format(e)

    # Numbered labels next to each point
    try:
        # Label size = ~3% of path diagonal, clamped
        xs = [p.X for p in pts]
        ys = [p.Y for p in pts]
        diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
        label_size = max(diag * 0.03, 0.15)
        offset = label_size * 0.6
        text_color = Color.White

        for i, p in enumerate(pts):
            # Slight offset so the number doesn't sit on top of the point
            origin = rg.Point3d(p.X + offset, p.Y + offset, p.Z)
            plane = rg.Plane(origin, rg.Vector3d.ZAxis)
            label = "{}".format(i)
            drawn = False
            # Try Text3d-based API (Rhino 7/8 standard)
            try:
                t3d = Rhino.Display.Text3d(label, plane, label_size)
                disp.AddText(t3d, text_color)
                drawn = True
            except Exception:
                pass
            if not drawn:
                # Fallback: AddText with separate args (older API)
                try:
                    disp.AddText(label, plane, label_size, "Arial", False, False, text_color)
                    drawn = True
                except Exception:
                    pass
            # If both fail, silently skip labels (points still visible)
    except Exception:
        pass

    sc.sticky[STICKY_KEY] = disp
    try:
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    except Exception as e:
        return "Views.Redraw failed: {}".format(e)
    return None


# ---------- Outputs ----------
polyline = None
points = []
info = ""

# Inputs
try:
    _layout_wired = layout_json
except NameError:
    _layout_wired = None
try:
    _target = target_room
except NameError:
    _target = None
try:
    _start_in = start_room
except NameError:
    _start_in = None

if not _target:
    info = "[WAITING] Missing input: target_room"
else:
    layout_text, source = _load_layout_text(_layout_wired)
    if layout_text is None:
        info = "[ERROR] Could not load layout_json (wire empty AND disk fallback failed)"
    else:
        try:
            layout = json.loads(layout_text)
        except Exception as e:
            layout = None
            info = "[ERROR] Invalid layout_json: {}".format(e)

        if layout is not None:
            start_name = _start_in if _start_in else layout.get("start_room")
            if not start_name:
                info = "[ERROR] No start_room provided and layout has no 'start_room' field"
            else:
                start_id = _room_id_by_name(layout, start_name)
                target_id = _room_id_by_name(layout, _target)
                if start_id is None:
                    info = "[NO MATCH] start_room '{}' not in layout".format(start_name)
                elif target_id is None:
                    available = [r.get("name") for r in layout.get("rooms", [])]
                    info = "[NO MATCH] target_room '{}' not in layout. Available: {}".format(
                        _target, ", ".join(available)
                    )
                else:
                    path_doors = _bfs_path(_build_graph(layout), start_id, target_id)
                    if path_doors is None:
                        info = "[ERROR] No path from '{}' to '{}'".format(start_name, _target)
                    elif len(path_doors) == 0:
                        info = "[OK] Target equals start - no path needed."
                    else:
                        door_positions = {d["id"]: d["position"] for d in layout.get("doors", [])}
                        coords = []
                        sc_pt = _room_centroid(layout, start_name)
                        if sc_pt:
                            coords.append(sc_pt)
                        for did in path_doors:
                            if did in door_positions:
                                coords.append(door_positions[did])
                        ec_pt = _room_centroid(layout, _target)
                        if ec_pt:
                            coords.append(ec_pt)

                        points = [rg.Point3d(p[0], p[1], 0) for p in coords]
                        if len(points) >= 2:
                            polyline = rg.Polyline(points).ToPolylineCurve()
                            info = "[OK] Path '{}' -> '{}' | doors: {} | points: {} | source: {} | preview: {}".format(
                                start_name, _target, " -> ".join(path_doors),
                                len(points), source, show_preview
                            )
                            if show_preview:
                                err = draw_overlay(points)
                                if err:
                                    info = info + " | [DRAW ERROR] " + err
                        else:
                            info = "[ERROR] Not enough points to build polyline"
