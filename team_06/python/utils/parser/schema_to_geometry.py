import json
import Rhino.Geometry as rg

def load_json_from_string(json_string):
    try:
        data = json.loads(json_string)
    except Exception as e:
        raise ValueError(f"Invalid JSON string: {e}")
    return data

def create_polyline(points, close=True):
    """Create a Rhino PolylineCurve from 2D points"""
    pts = [rg.Point3d(x, y, 0) for x, y in points]

    if close and pts[0] != pts[-1]:
        pts.append(pts[0])

    return rg.Polyline(pts).ToPolylineCurve()

def create_line(points):
    """Create a Rhino LineCurve from 2 points"""
    if len(points) != 2:
        return None
    p1 = rg.Point3d(points[0][0], points[0][1], 0)
    p2 = rg.Point3d(points[1][0], points[1][1], 0)
    return rg.LineCurve(p1, p2)

# Load JSON
layout = load_json_from_string(json_str)

# ------------------------
# FACADE (polylines)
# ------------------------
facade_curves = []
for facade in layout.get("facades", []):
    geometry = facade.get("geometry")
    if geometry:
        curve = create_polyline(geometry, close=False)
        facade_curves.append(curve)

# ------------------------
# CIRCULATION (polylines)
# ------------------------
circulation_curves = []
for circulation in layout.get("circulation", []):
    geometry = circulation.get("geometry")
    if geometry:
        curve = create_polyline(geometry, close=True)
        circulation_curves.append(curve)

# ------------------------
# ROOMS (polygons)
# ------------------------
room_names = []
room_curves = []

for room in layout.get("rooms", []):
    name = room.get("name")
    geometry = room.get("geometry")

    if name and geometry:
        curve = create_polyline(geometry, close=True)
        room_names.append(name)
        room_curves.append(curve)

# ------------------------
# DOORS (lines)
# ------------------------
door_names = []
door_curves = []

for door in layout.get("doors", []):
    name = door.get("name")
    geometry = door.get("geometry")

    if name and geometry:
        curve = create_line(geometry)
        if curve:
            door_names.append(name)
            door_curves.append(curve)

# ------------------------
# WINDOWS (lines)
# ------------------------
window_names = []
window_curves = []

for window in layout.get("windows", []):
    name = window.get("name")
    geometry = window.get("geometry")

    if name and geometry:
        curve = create_line(geometry)
        if curve:
            window_names.append(name)
            window_curves.append(curve)

# ------------------------
# FURNITURE (polygons)
# ------------------------
furniture_names = []
furniture_curves = []

for furn in layout.get("furniture", []):
    name = furn.get("name")
    geometry = furn.get("geometry")

    if name and geometry:
        curve = create_polyline(geometry, close=True)
        furniture_names.append(name)
        furniture_curves.append(curve)

# ------------------------
# OUTLINE (optional)
# ------------------------
outline_curve = None
if "outline" in layout:
    outline_curve = create_polyline(layout["outline"], close=True)

# ------------------------
# OUTPUTS
# ------------------------
a = room_names
b = room_curves

c = door_names
d = door_curves

e = window_names
f = window_curves

g = furniture_names
h = furniture_curves

i = outline_curve
j = facade_curves
k = circulation_curves