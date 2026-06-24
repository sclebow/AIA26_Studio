"""
GHPython component: set_viewport
MCP tool for viewport visualization toggle.

PURPOSE:
    Lightweight layout renderer — receives a layout JSON and a display mode,
    outputs Rhino geometry for real-time viewport preview. Unlike
    collision-detector-grid, this does NO analysis — it only draws geometry,
    making before/after toggling instant.

SWIFTLET SETUP:
    1. In team_03_working.gh, add a new GHPython component.
    2. Rename it to "set_viewport" (this becomes the MCP tool name).
    3. Add these INPUT parameters (right-click component > Manage Inputs):
         layout_json   (str)  — Full layout JSON string
         mode          (str)  — Display mode: "all", "rooms", "furniture",
                                "doors", "structure", "outline_only"
    4. Add these OUTPUT parameters (right-click component > Manage Outputs):
         room_curves       (list)  — Room boundary polylines
         room_names        (list)  — Room name labels
         door_curves       (list)  — Door line segments
         door_names        (list)  — Door name labels
         furniture_curves  (list)  — Furniture footprint polylines
         furniture_names   (list)  — Furniture name labels
         furniture_heights (list)  — Furniture extrusion heights in metres
         window_curves     (list)  — Window line segments
         structure_curves  (list)  — Structure (wall) line segments
         mep_curves        (list)  — MEP footprint polylines
         outline_curve     (curve) — Exterior boundary polyline
         info              (str)   — Status message
    5. Paste this entire script into the GHPython editor.
    6. Connect furniture_heights to the Extrude height input instead of
       the hardcoded Panel value.
    7. Restart Swiftlet — the tool will auto-discover.

MODES:
    "all"          — Draw everything (rooms, doors, windows, furniture,
                     mep, structure, outline). Default.
    "rooms"        — Rooms + doors + outline only (no furniture).
    "furniture"    — Furniture footprints + room boundaries only.
    "doors"        — Doors + room boundaries only.
    "structure"    — Structure + outline only.
    "outline_only" — Just the exterior boundary.

INPUTS (from Swiftlet MCP call):
    layout_json  (str)  — Full layout JSON (all 7 layers)
    mode         (str)  — Display mode (default: "all")

OUTPUTS:
    Rhino geometry objects assigned to component outputs.
    furniture_heights (list) — Per-object extrusion heights from knowledge base.
    info (str) — status message returned to the Python agent.
"""

import json
import Rhino.Geometry as rg


# ---------------------------------------------------------------------------
# Default heights per object type — matches knowledge/industrial/equipment_heights.json
# Used as fallback when attributes.height is not set in the layout JSON.
# ---------------------------------------------------------------------------

DEFAULT_HEIGHTS = {
    "workbench":                0.900,
    "quality_control_station":  0.900,
    "qc_station":               0.900,
    "qc_table":                 0.900,
    "assembly_station":         0.850,
    "packaging_station":        0.850,
    "labeling_station":         0.900,
    "conveyor":                 0.850,
    "conveyor_section":         0.850,
    "parts_bin_rack":           2.100,
    "storage_rack":             2.400,
    "cnc_machine":              1.800,
    "press_brake":              1.600,
    "lathe":                    1.400,
    "welding_station":          0.900,
    "robot_cell":               2.200,
    "electrical_panel":         2.000,
    "compressor":               1.200,
    "forklift_charging_station": 1.500,
    "pallet_station":           0.150,
    "office_desk":              0.750,
    "tool_cabinet":             1.000,
    "sink":                     0.850,
    "toilet":                   0.400,
}

FALLBACK_HEIGHT = 0.900  # standard workbench height


def _get_furniture_height(furn):
    """
    Resolve the correct extrusion height for a furniture item.
    Priority:
      1. attributes.height — set by add_objects.py when the LLM specifies height
      2. DEFAULT_HEIGHTS lookup by object name (normalized)
      3. FALLBACK_HEIGHT (0.9m)
    """
    # Priority 1: height stored in attributes by add_objects.py
    h = furn.get("attributes", {}).get("height")
    if h is not None:
        try:
            return float(h)
        except (ValueError, TypeError):
            pass

    # Priority 2: match by name against default heights dict
    name = furn.get("name", "").lower().strip()
    # Try exact match first
    if name in DEFAULT_HEIGHTS:
        return DEFAULT_HEIGHTS[name]
    # Try partial match — e.g. "Assembly Station 1" → "assembly_station"
    name_normalized = name.replace(" ", "_")
    if name_normalized in DEFAULT_HEIGHTS:
        return DEFAULT_HEIGHTS[name_normalized]
    # Try substring match — e.g. "Conveyor Section 5" contains "conveyor"
    for key, height in DEFAULT_HEIGHTS.items():
        if key.replace("_", " ") in name or key in name_normalized:
            return height

    # Priority 3: fallback
    return FALLBACK_HEIGHT


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def create_polyline(points, close=True):
    """Convert a list of [x, y] points to a Rhino PolylineCurve."""
    pts = [rg.Point3d(x, y, 0) for x, y in points]
    if close and len(pts) > 1 and pts[0] != pts[-1]:
        pts.append(pts[0])
    if len(pts) < 2:
        return None
    return rg.Polyline(pts).ToPolylineCurve()


def create_line(points):
    """Convert a 2-point list to a Rhino LineCurve."""
    if len(points) != 2:
        return None
    p1 = rg.Point3d(points[0][0], points[0][1], 0)
    p2 = rg.Point3d(points[1][0], points[1][1], 0)
    return rg.LineCurve(p1, p2)


def centroid_point(points, z=0.0):
    """Return a simple centroid point for polygon-like [x, y] coordinates."""
    if not points:
        return None
    xs = [p[0] for p in points if len(p) >= 2]
    ys = [p[1] for p in points if len(p) >= 2]
    if not xs or not ys:
        return None
    return rg.Point3d(sum(xs) / len(xs), sum(ys) / len(ys), z)


def midpoint_label(points, z=0.0):
    """Return the midpoint of a 2-point segment for door/window labels."""
    if len(points) != 2:
        return None
    return rg.Point3d(
        (points[0][0] + points[1][0]) / 2.0,
        (points[0][1] + points[1][1]) / 2.0,
        z,
    )


def create_label(text, point):
    """Create Rhino label geometry that is visible directly in the viewport."""
    if not text or point is None:
        return None
    return rg.TextDot(str(text), point)


# ---------------------------------------------------------------------------
# Initialize ALL outputs to empty — prevents GH "null" errors
# ---------------------------------------------------------------------------

room_curves      = []
room_names       = []
door_curves      = []
door_names       = []
furniture_curves  = []
furniture_names  = []
furniture_heights = []  # NEW — per-object extrusion heights
window_curves    = []
structure_curves = []
mep_curves       = []
outline_curve    = None
info             = ""


# ---------------------------------------------------------------------------
# Read inputs from GH component (set by Swiftlet MCP call)
# ---------------------------------------------------------------------------

_layout_input = None
try:
    _layout_input = layout_json
except NameError:
    pass

_mode = "all"
try:
    if mode is not None and str(mode).strip() != "":
        _mode = str(mode).strip().lower()
except NameError:
    pass

# Handle list inputs (Swiftlet sometimes wraps in a list)
if isinstance(_layout_input, list):
    _layout_input = _layout_input[0] if len(_layout_input) > 0 else None

if _layout_input is None or str(_layout_input).strip() == "":
    info = json.dumps({"status": "error", "message": "No layout_json received"})
else:
    # ---------------------------------------------------------------------------
    # Parse layout JSON
    # ---------------------------------------------------------------------------
    layout    = None
    json_text = str(_layout_input).strip()

    try:
        layout = json.loads(json_text)
    except Exception:
        import os
        if os.path.isfile(json_text):
            try:
                with open(json_text, "r") as fh:
                    layout = json.load(fh)
            except Exception as ex:
                info = json.dumps({"status": "error",
                                   "message": "Could not read file: {}".format(ex)})

    if layout is None and info == "":
        info = json.dumps({"status": "error",
                           "message": "Could not parse layout_json"})

    if layout is not None:
        if _mode == "none":
            info = json.dumps({"status": "ok", "mode": "none", "message": "cleared"})

        else:
            show_rooms      = _mode in ("all", "rooms", "furniture", "doors")
            show_doors      = _mode in ("all", "rooms", "doors")
            show_windows    = _mode in ("all", "rooms")
            show_furniture  = _mode in ("all", "furniture")
            show_mep        = _mode in ("all",)
            show_structure  = _mode in ("all", "structure")
            show_outline    = _mode in ("all", "rooms", "outline_only",
                                        "structure", "furniture", "doors")

            counts = {}

            # -- Rooms --
            if show_rooms:
                for room in layout.get("rooms", []):
                    name     = room.get("name")
                    geometry = room.get("geometry")
                    if name and geometry:
                        curve = create_polyline(geometry, close=True)
                        if curve:
                            label = create_label(name, centroid_point(geometry, z=0.05))
                            if label:
                                room_names.append(label)
                            room_curves.append(curve)
                counts["rooms"] = len(room_curves)

            # -- Doors --
            if show_doors:
                for door in layout.get("doors", []):
                    name     = door.get("name")
                    geometry = door.get("geometry")
                    if name and geometry:
                        curve = create_line(geometry)
                        if curve:
                            label = create_label(name, midpoint_label(geometry, z=0.08))
                            if label:
                                door_names.append(label)
                            door_curves.append(curve)
                counts["doors"] = len(door_curves)

            # -- Windows --
            if show_windows:
                for window in layout.get("windows", []):
                    name     = window.get("name")
                    geometry = window.get("geometry")
                    if name and geometry:
                        curve = create_line(geometry)
                        if curve:
                            window_curves.append(curve)
                counts["windows"] = len(window_curves)

            # -- Furniture --
            if show_furniture:
                for furn in layout.get("furniture", []):
                    name     = furn.get("name")
                    geometry = furn.get("geometry")
                    if name and geometry:
                        curve = create_polyline(geometry, close=True)
                        if curve:
                            # Resolve correct height for this object
                            fh = _get_furniture_height(furn)
                            furniture_curves.append(curve)
                            furniture_heights.append(fh)

                            # Place label above the object at its actual height
                            label = create_label(
                                name,
                                centroid_point(geometry, z=fh + 0.05)
                            )
                            if label:
                                furniture_names.append(label)
                counts["furniture"] = len(furniture_curves)

            # -- MEP --
            if show_mep:
                for mep_item in layout.get("mep", []):
                    name     = mep_item.get("name")
                    geometry = mep_item.get("geometry")
                    if name and geometry:
                        curve = create_polyline(geometry, close=True)
                        if curve:
                            mep_curves.append(curve)
                counts["mep"] = len(mep_curves)

            # -- Structure --
            if show_structure:
                for s in layout.get("structure", []):
                    name     = s.get("name")
                    geometry = s.get("geometry")
                    if name and geometry:
                        curve = create_line(geometry)
                        if curve:
                            structure_curves.append(curve)
                counts["structure"] = len(structure_curves)

            # -- Outline --
            if show_outline and "outline" in layout:
                outline_curve = create_polyline(layout["outline"], close=True)
                if outline_curve:
                    counts["outline"] = 1

            layout_id = layout.get("layoutId", "unknown")
            info = json.dumps({
                "status":   "ok",
                "mode":     _mode,
                "layoutId": layout_id,
                "counts":   counts,
            })