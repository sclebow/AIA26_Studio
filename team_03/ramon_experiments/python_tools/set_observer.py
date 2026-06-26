"""
GHPython component: set_observer
MCP tool for placing a draggable "observer" / person point from the web UI.

PURPOSE:
    Receives a single ground point (and a person height) dragged in the
    AGENT_ui 3D viewport and materializes it in Grasshopper/Rhino as:
      - a base point on the floor (z = 0),
      - an eye/head point at the person height,
      - a vertical line representing the 1.7m person,
    so downstream GH logic (visibility, isovist, sightlines, etc.) can use the
    observer location chosen interactively in the browser.

    Coordinates arrive in LAYOUT metres (origin bottom-left), the same basis as
    the layout JSON and the other GH scripts (x, y on the ground, z up).

SWIFTLET SETUP:
    1. In team_03_working.gh, add a new GHPython component.
    2. Rename it to "set_observer" (this becomes the MCP tool name).
    3. Add these INPUT parameters (right-click component > Manage Inputs):
         point   (str)  — "x,y,h" or "x,y" in layout metres
         height  (str)  — person height in metres (optional; default 1.7)
    4. Add these OUTPUT parameters (right-click component > Manage Outputs):
         observer_point  (point) — base point on the floor (z = 0)
         observer_eye    (point) — point at person height (z = h)
         person_curve    (curve) — vertical line base -> eye
         info            (str)   — status JSON (REQUIRED for Swiftlet response)
    5. Paste this entire script into the GHPython editor.
    6. Restart Swiftlet — the tool will auto-discover.
    7. (Optional) Wire a Panel to observer_point / info to inspect the value,
       and person_curve to a Custom Preview to see the person in the viewport.

INPUTS (from Swiftlet MCP call):
    point   (str) — "x,y,h" comma-separated, layout metres.
    height  (str) — fallback height if not encoded in `point`.

OUTPUTS:
    observer_point, observer_eye, person_curve, info
"""

import json
import Rhino.Geometry as rg


# ---------------------------------------------------------------------------
# Initialize ALL outputs to empty — prevents GH "null" errors
# ---------------------------------------------------------------------------

observer_point = None
observer_eye   = None
person_curve   = None
info           = ""

DEFAULT_HEIGHT = 1.7


# ---------------------------------------------------------------------------
# Read inputs (set by Swiftlet MCP call)
# ---------------------------------------------------------------------------

_point_input = None
try:
    _point_input = point
except NameError:
    pass

_height_input = None
try:
    _height_input = height
except NameError:
    pass

# Swiftlet sometimes wraps a single value in a list.
if isinstance(_point_input, list):
    _point_input = _point_input[0] if len(_point_input) > 0 else None
if isinstance(_height_input, list):
    _height_input = _height_input[0] if len(_height_input) > 0 else None


def _to_float(value, fallback):
    try:
        return float(str(value).strip())
    except (ValueError, TypeError, AttributeError):
        return fallback


if _point_input is None or str(_point_input).strip() == "":
    info = json.dumps({"status": "error", "message": "No point received"})
else:
    # -----------------------------------------------------------------------
    # Parse "x,y[,h]" — fall back to the separate `height` input for h.
    # -----------------------------------------------------------------------
    h = _to_float(_height_input, DEFAULT_HEIGHT)

    parts = [p for p in str(_point_input).strip().split(",") if p.strip() != ""]

    if len(parts) < 2:
        info = json.dumps({
            "status": "error",
            "message": "Expected 'x,y' or 'x,y,h', got: {}".format(_point_input),
        })
    else:
        x = _to_float(parts[0], None)
        y = _to_float(parts[1], None)
        if len(parts) >= 3:
            h = _to_float(parts[2], h)

        if x is None or y is None:
            info = json.dumps({
                "status": "error",
                "message": "Could not parse coordinates from: {}".format(_point_input),
            })
        else:
            if h is None or h <= 0:
                h = DEFAULT_HEIGHT

            observer_point = rg.Point3d(x, y, 0.0)
            observer_eye   = rg.Point3d(x, y, h)
            person_curve   = rg.LineCurve(observer_point, observer_eye)

            info = json.dumps({
                "status": "ok",
                "x": round(x, 3),
                "y": round(y, 3),
                "h": round(h, 3),
            })
