"""
GHPython component: Arrange existing geometry in a grid.

INPUTS:
    geometry   (DataTree)  - Geometry in branches (one branch per layout). Tree Access, ghdoc Object.
    points     (DataTree)  - Points in branches (for text tags). Tree Access, ghdoc Object.
    floors     (DataTree)  - Floor surfaces/curves in branches. Tree Access, ghdoc Object.
    columns    (int)       - Number of columns. Default: 3.
    spacing    (float)     - Gap between cells in meters. Default: 5.0.

OUTPUTS:
    a  = moved geometry (flat list)
    b  = moved points (DataTree grouped by layout)
    c  = moved floors (DataTree grouped by layout)
    d  = bounding boxes per cell
    e  = info
"""

import Rhino.Geometry as rg
import Rhino
import System
import clr
clr.AddReference("Grasshopper")
from Grasshopper.Kernel.Types import GH_GeometricGoo
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# Read inputs
# ---------------------------------------------------------------------------
try:
    _cols = int(columns) if columns is not None else 3
except:
    _cols = 3
if _cols < 1:
    _cols = 1

try:
    _spacing = float(spacing) if spacing is not None else 5.0
except:
    _spacing = 5.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_geos(item):
    """Get list of raw Rhino geometries, flattening nested lists/wrappers."""
    results = []
    try:
        if hasattr(item, "__iter__") and not isinstance(item, str):
            for sub in item:
                results.extend(_extract_geos(sub))
            return results
    except:
        pass
    # .NET List[Object]
    try:
        cnt = item.Count if hasattr(item, "Count") else -1
        if cnt >= 0:
            for idx in range(cnt):
                results.extend(_extract_geos(item[idx]))
            return results
    except:
        pass
    if isinstance(item, GH_GeometricGoo):
        geo = item.DuplicateGeometry()
        if geo is not None:
            results.append(geo)
        return results
    if hasattr(item, "Value"):
        val = item.Value
        if val is not None:
            return _extract_geos(val)
    # Guid — reference to Rhino doc object
    if isinstance(item, System.Guid):
        obj = Rhino.RhinoDoc.ActiveDoc.Objects.FindId(item)
        if obj is not None:
            geo = obj.Geometry
            if geo is not None:
                results.append(geo.Duplicate())
        return results
    if hasattr(item, "GetBoundingBox"):
        results.append(item)
    return results

def _extract_points(item):
    """Get list of Point3d from nested lists/wrappers."""
    results = []
    if isinstance(item, rg.Point3d):
        results.append(item)
        return results
    if isinstance(item, rg.Point):
        results.append(item.Location)
        return results
    if hasattr(item, "Value"):
        val = item.Value
        if val is not None:
            return _extract_points(val)
    try:
        cnt = item.Count if hasattr(item, "Count") else len(item)
        for idx in range(cnt):
            results.extend(_extract_points(item[idx]))
        return results
    except:
        pass
    return results

def _read_tree(tree_input):
    """Safely read branches from a tree input."""
    try:
        return list(tree_input.Branches), len(tree_input.Branches)
    except:
        return [], 0

# ---------------------------------------------------------------------------
# Read trees
# ---------------------------------------------------------------------------
geo_branches, count = _read_tree(geometry)

pt_branches, pt_count = _read_tree(points)
has_points = pt_count > 0

fl_branches, fl_count = _read_tree(floors)
has_floors = fl_count > 0

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
a = []                          # moved geometry
b = DataTree[rg.Point3d]()     # moved points grouped by layout
c = DataTree[object]()         # moved floors grouped by layout
d = []                          # bounding boxes
e = ""                          # info

if count == 0:
    e = "[ERROR] No geometry connected. Set input to Tree Access."
else:
    # --- First pass: extract geos and find max cell size ---
    branch_geos = []
    branch_pts = []
    branch_fls = []
    bboxes = []
    max_w = 0.0
    max_h = 0.0

    for bi in range(count):
        # Geometry
        geos = []
        bb = rg.BoundingBox.Empty
        for item in geo_branches[bi]:
            extracted = _extract_geos(item)
            for geo in extracted:
                bb.Union(geo.GetBoundingBox(True))
                geos.append(geo)
        branch_geos.append(geos)
        bboxes.append(bb)
        if bb.IsValid:
            w = bb.Max.X - bb.Min.X
            h = bb.Max.Y - bb.Min.Y
            if w > max_w:
                max_w = w
            if h > max_h:
                max_h = h

        # Points
        pts = []
        if has_points and bi < pt_count:
            for item in pt_branches[bi]:
                pts.extend(_extract_points(item))
        branch_pts.append(pts)

        # Floors
        fls = []
        if has_floors and bi < fl_count:
            for item in fl_branches[bi]:
                fls.extend(_extract_geos(item))
            if bi == 0:
                print("DEBUG floors branch 0: {} items, {} extracted".format(
                    len(fl_branches[bi]), len(fls)))
                if len(fl_branches[bi]) > 0:
                    print("DEBUG first floor item type: {}".format(type(fl_branches[bi][0])))
        branch_fls.append(fls)

    cell_w = max_w + _spacing
    cell_h = max_h + _spacing

    # --- Second pass: move everything to grid ---
    for idx in range(count):
        col = idx % _cols
        row = idx // _cols
        bb = bboxes[idx]

        if not bb.IsValid:
            continue

        move_vec = rg.Vector3d(
            col * cell_w - bb.Min.X,
            -(row * cell_h) - bb.Min.Y,
            0
        )
        xform = rg.Transform.Translation(move_vec)
        path = GH_Path(idx)

        # Move geometry
        for geo in branch_geos[idx]:
            if hasattr(geo, "Duplicate"):
                copy = geo.Duplicate()
                copy.Transform(xform)
                a.append(copy)
            elif hasattr(geo, "Transform"):
                geo.Transform(xform)
                a.append(geo)

        # Move points
        for pt in branch_pts[idx]:
            moved = rg.Point3d(pt.X + move_vec.X, pt.Y + move_vec.Y, pt.Z + move_vec.Z)
            b.Add(moved, path)

        # Move floors
        for fl in branch_fls[idx]:
            if hasattr(fl, "Duplicate"):
                copy = fl.Duplicate()
                copy.Transform(xform)
                c.Add(copy, path)
            elif hasattr(fl, "Transform"):
                fl.Transform(xform)
                c.Add(fl, path)

        # Bounding box rectangle
        tx = col * cell_w
        ty = -(row * cell_h)
        pad = _spacing * 0.25
        bb_pts = [
            rg.Point3d(tx - pad, ty - pad, 0),
            rg.Point3d(tx + max_w + pad, ty - pad, 0),
            rg.Point3d(tx + max_w + pad, ty + max_h + pad, 0),
            rg.Point3d(tx - pad, ty + max_h + pad, 0),
            rg.Point3d(tx - pad, ty - pad, 0),
        ]
        d.append(rg.Polyline(bb_pts).ToPolylineCurve())

    e = "[OK] {} layouts in {}x{} grid (cell: {:.1f} x {:.1f} m) | {} pts | {} floors".format(
        count, _cols, (count + _cols - 1) // _cols, cell_w, cell_h,
        b.DataCount, c.DataCount
    )
    print(e)
