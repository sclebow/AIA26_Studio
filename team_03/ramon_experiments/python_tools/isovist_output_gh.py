"""
GhPython component — append the isovist polygon to the set_observer result.

WHERE TO PLACE IT
  After `set_observer` AND after the node that computes the isovist `boundary`
  curve (the same closed Curve you already feed into your metrics component,
  the one that calls `boundary.Contains(...)`).

INPUTS (add these on the GhPython component, "Item Access"):
  result   : Text   -> the JSON string that set_observer currently outputs
                       e.g. {"status":"ok","mode":"single","x":-1.617,"y":14.774,"h":1.7}
                       (optional — if omitted, output is just status + isovist)
  boundary : Curve  -> the closed isovist boundary curve (layout metres, WorldXY).
                       Must be ONE closed curve. If yours is several pieces,
                       Join them first.

OUTPUT:
  a        : Text   -> JSON = result merged with {"isovist": [[x,y], ...]}.
                       Wire THIS into the MCP tool's result (where set_observer's
                       JSON currently goes).

RESULT the web UI then receives (and draws as the visibility surface):
  {"status":"ok","mode":"single","x":-1.617,"y":14.774,"h":1.7,
   "isovist": [[x1,y1],[x2,y2], ... , [x1,y1]]}

Compatible with both GhPython (IronPython 2.7) and the Rhino 8 Python 3 script
component (no f-strings; uses Rhino.Geometry).
"""
import Rhino.Geometry as rg
import json


def _first(x):
    """GH may hand inputs as a list; take the first item."""
    if isinstance(x, list):
        return x[0] if x else None
    return x


# Base dict from set_observer's existing JSON (keeps status/mode/x/y/h).
data = {}
_res = _first(result)
if _res:
    try:
        data = json.loads(str(_res))
    except Exception:
        data = {}
if "status" not in data:
    data["status"] = "ok"

# Extract the isovist polygon points (layout metres, XY) from the boundary curve.
iso = []
crv = _first(boundary)
if crv is not None:
    poly = None
    try:
        ok, pl = crv.TryGetPolyline()       # exact vertices if it's a polyline
        if ok and pl is not None and pl.Count >= 3:
            poly = pl
    except Exception:
        poly = None

    if poly is not None:
        iso = [[round(pt.X, 3), round(pt.Y, 3)] for pt in poly]
    else:
        try:                                 # fallback: sample any closed curve
            params = crv.DivideByCount(96, True)
            if params:
                iso = [[round(crv.PointAt(t).X, 3), round(crv.PointAt(t).Y, 3)] for t in params]
        except Exception:
            iso = []

    # Close the ring so the UI draws a filled polygon.
    if len(iso) >= 3 and iso[0] != iso[-1]:
        iso.append(iso[0])

data["isovist"] = iso
a = json.dumps(data)
