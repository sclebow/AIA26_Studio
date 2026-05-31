import json
import Rhino.Geometry as rg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def create_polyline(points, close=True):
    pts = [rg.Point3d(x, y, 0) for x, y in points]
    if close and pts[0] != pts[-1]:
        pts.append(pts[0])
    return rg.Polyline(pts).ToPolylineCurve()

def create_line(points):
    if len(points) != 2:
        return None
    p1 = rg.Point3d(points[0][0], points[0][1], 0)
    p2 = rg.Point3d(points[1][0], points[1][1], 0)
    return rg.LineCurve(p1, p2)

# ---------------------------------------------------------------------------
# Initialize all outputs (so they always exist)
# ---------------------------------------------------------------------------
a = b = c = d = e = f = g = h = i = j = k = l = []
m = None
info = ""

# ---------------------------------------------------------------------------
# Validate input
# ---------------------------------------------------------------------------
try:
    _input = json_str
except NameError:
    _input = None

# If input is a list, take the first item
if isinstance(_input, list):
    _input = _input[0] if len(_input) > 0 else None

if _input is None or str(_input).strip() == "":
    print("[DEBUG] json_str is None or empty. Type: {}".format(type(_input)))
else:
    json_text = str(_input).strip()

    # ---------------------------------------------------------------------------
    # Parse JSON — could be a JSON string or a file path
    # ---------------------------------------------------------------------------
    layout = None

    # Try parsing as JSON directly
    try:
        layout = json.loads(json_text)
    except:
        pass

    # If that failed, maybe it's a file path
    if layout is None:
        import os
        if os.path.isfile(json_text):
            try:
                with open(json_text, "r") as fh:
                    layout = json.load(fh)
            except Exception as ex:
                info = "[ERROR] Could not read file: {}".format(ex)

    if layout is None and info == "":
        print("[DEBUG] Could not parse input. Type: {} | First 200 chars: {}".format(
            type(_input), json_text[:200]))

    if layout is not None:
        print("[DEBUG] Layout parsed OK. Keys: {}".format(list(layout.keys())))
        print("[DEBUG] Rooms: {}".format(len(layout.get("rooms", []))))
        # -- Rooms --
        room_names = []
        room_curves = []
        for room in layout.get("rooms", []):
            name = room.get("name")
            geometry = room.get("geometry")
            if name and geometry:
                room_names.append(name)
                room_curves.append(create_polyline(geometry, close=True))

        # -- Doors --
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

        # -- Windows --
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

        # -- Furniture --
        furniture_names = []
        furniture_curves = []
        for furn in layout.get("furniture", []):
            name = furn.get("name")
            geometry = furn.get("geometry")
            if name and geometry:
                furniture_names.append(name)
                furniture_curves.append(create_polyline(geometry, close=True))

        # -- MEP --
        mep_names = []
        mep_curves = []
        for mep_item in layout.get("mep", []):
            name = mep_item.get("name")
            geometry = mep_item.get("geometry")
            if name and geometry:
                mep_names.append(name)
                mep_curves.append(create_polyline(geometry, close=True))

        # -- Structure --
        structure_names = []
        structure_curves = []
        for s in layout.get("structure", []):
            name = s.get("name")
            geometry = s.get("geometry")
            if name and geometry:
                curve = create_line(geometry)
                if curve:
                    structure_names.append(name)
                    structure_curves.append(curve)

        # -- Outline --
        outline_curve = None
        if "outline" in layout:
            outline_curve = create_polyline(layout["outline"], close=True)

        # -- Outputs --
        a = room_names
        b = room_curves
        c = door_names
        d = door_curves
        e = window_names
        f = window_curves
        g = furniture_names
        h = furniture_curves
        i = mep_names
        j = mep_curves
        k = structure_names
        l = structure_curves
        m = outline_curve
        info = "[OK] {} rooms, {} doors, {} windows, {} furniture, {} mep, {} structure".format(
            len(room_names), len(door_names), len(window_names),
            len(furniture_names), len(mep_names), len(structure_names)
        )
