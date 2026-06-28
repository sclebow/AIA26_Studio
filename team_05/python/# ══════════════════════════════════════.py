# ═══════════════════════════════════════════════════════════════════════════════
# VenustaMeter — Brep Bridge v2
# Two-input bridge: solid geometry + glazing, each with explicit colour
# GHPython — CPython 3 (Rhino 8)
# ═══════════════════════════════════════════════════════════════════════════════
#
# WHY THIS IS BETTER THAN AUTO-CLASSIFICATION:
#   You already know what is solid and what is glazing.
#   This bridge trusts you — no guessing, no misclassification.
#   Both sets get explicit colours → N_C opponent channels fire correctly.
#
# COMPONENT INPUTS (right-click → Manage component I/O):
#   solid_breps    → Brep (list)    Walls, mullions, slabs, ornaments
#   solid_color    → Colour         Colour for all solid elements
#   glazing_breps  → Brep (list)    Glass panels, openings
#   glazing_color  → Colour         Colour for all glazing elements
#   mesh           → Mesh (item)    Optional — auto-built if absent
#   sun_vec        → Vector3d       Optional — default (0.5, 0.7, 0.5)
#   facade_id      → Text           Optional — default "facade_01"
#   run            → Boolean        Button or Toggle
#
# COMPONENT OUTPUTS:
#   breps_out  → Brep list   All breps with vm_role + colour embedded
#   mesh_out   → Mesh        Coloured display mesh (solid / glazing)
#   geo_json   → Text        Connect to venustameter 'geo_dict' input
#   report     → Text        Connect to Panel
#
# WIRING:
#   solid_breps  ──┐
#   solid_color  ──┤
#   glazing_breps──┤  [VM_BrepBridge v2]  geo_json ──► venustameter
#   glazing_color──┤                      breps_out──► preview
#   run          ──┘                      mesh_out ──► preview
# ═══════════════════════════════════════════════════════════════════════════════

import Rhino
import Rhino.Geometry as rg
import System.Drawing as sd
import System
import math
import json

_DEF_SOL_COL = sd.Color.FromArgb(30, 120, 200)
_DEF_GLZ_COL = sd.Color.FromArgb(20, 180, 120)

# ── Safe defaults ──────────────────────────────────────────────────────────────
breps_out = []
mesh_out  = None
geo_json  = "{}"
report    = "Set run = True"

# ── Read inputs ────────────────────────────────────────────────────────────────
def _to_list(x):
    if x is None: return []
    try:    return list(x)
    except: return [x]

def _flatten_values(x, max_depth=12):
    """Flatten GH tree/list-like inputs while keeping geometry objects atomic."""
    out = []

    def _walk(v, d):
        if d > max_depth or v is None:
            return

        # Treat geometry/color objects as atomic values.
        if isinstance(v, (rg.Brep, rg.Mesh, rg.Surface, rg.Extrusion)):
            out.append(v)
            return
        if hasattr(v, "R") and hasattr(v, "G") and hasattr(v, "B"):
            out.append(v)
            return

        if isinstance(v, (str, bytes)):
            out.append(v)
            return

        try:
            seq = list(v)
            if not seq:
                return
            for it in seq:
                _walk(it, d + 1)
            return
        except:
            out.append(v)

    _walk(x, 0)
    return out

def _unwrap_gh_value(v, max_depth=6):
    """Unwrap common GH wrapper objects to RhinoCommon runtime values."""
    cur = v
    for _ in range(max_depth):
        if cur is None:
            return None

        # Rhino object reference by Guid -> resolve to document geometry.
        try:
            if isinstance(cur, System.Guid):
                doc = Rhino.RhinoDoc.ActiveDoc
                if doc:
                    ro = doc.Objects.FindId(cur)
                    if ro and ro.Geometry:
                        cur = ro.Geometry
                        continue
                return cur
        except:
            pass

        # Guid as string -> parse and resolve.
        try:
            if isinstance(cur, str):
                ok, gid = System.Guid.TryParse(cur)
                if ok:
                    doc = Rhino.RhinoDoc.ActiveDoc
                    if doc:
                        ro = doc.Objects.FindId(gid)
                        if ro and ro.Geometry:
                            cur = ro.Geometry
                            continue
                    return gid
        except:
            pass

        # Grasshopper goo often exposes ScriptVariable.
        try:
            if hasattr(cur, "ScriptVariable"):
                nxt = cur.ScriptVariable()
                if nxt is not None and nxt is not cur:
                    cur = nxt
                    continue
        except:
            pass

        # Some wrappers expose Value.
        try:
            if hasattr(cur, "Value"):
                nxt = cur.Value
                if nxt is not None and nxt is not cur:
                    cur = nxt
                    continue
        except:
            pass

        # ObjRef-like wrappers can expose Geometry().
        try:
            if hasattr(cur, "Geometry") and callable(cur.Geometry):
                nxt = cur.Geometry()
                if nxt is not None and nxt is not cur:
                    cur = nxt
                    continue
        except:
            pass

        break

    return cur

def _to_brep_list(x):
    """Convert GH item/list/tree input into a clean list of valid Breps."""
    out = []
    for item in _flatten_values(x):
        item = _unwrap_gh_value(item)
        try:
            if isinstance(item, rg.Brep):
                if item and item.IsValid:
                    out.append(item)
                continue
            if isinstance(item, rg.BrepFace):
                b = item.DuplicateFace(False)
                if b and b.IsValid:
                    out.append(b)
                continue
            if isinstance(item, rg.Surface):
                b = item.ToBrep()
                if b and b.IsValid:
                    out.append(b)
                continue
            if isinstance(item, rg.Extrusion):
                b = item.ToBrep()
                if b and b.IsValid:
                    out.append(b)
                continue
            # Generic geometry fallback for RhinoCommon types with ToBrep.
            if hasattr(item, "ToBrep"):
                b = item.ToBrep()
                if b and b.IsValid:
                    out.append(b)
                continue
        except:
            pass
    return out

def _to_mesh(x):
    """Get first valid mesh from GH item/list/tree input."""
    for item in _flatten_values(x):
        item = _unwrap_gh_value(item)
        try:
            if isinstance(item, rg.Mesh) and item and item.IsValid and item.Vertices.Count > 0:
                return item
        except:
            pass
    return None

def _coerce_color(x, default_color):
    """Coerce GH item/list/tree-like color inputs into System.Drawing.Color."""
    cur = x
    for _ in range(10):
        if cur is None:
            return default_color

        # System.Drawing.Color or color-like object
        if hasattr(cur, "R") and hasattr(cur, "G") and hasattr(cur, "B"):
            try:
                return sd.Color.FromArgb(int(cur.R), int(cur.G), int(cur.B))
            except:
                return default_color

        # Numeric RGB-like tuple/list
        if isinstance(cur, (list, tuple)):
            if len(cur) == 0:
                return default_color
            if len(cur) >= 3:
                try:
                    return sd.Color.FromArgb(int(cur[0]), int(cur[1]), int(cur[2]))
                except:
                    pass
            cur = cur[0]
            continue

        # Generic iterable (e.g. GH tree branch) -> take first
        if not isinstance(cur, (str, bytes)):
            try:
                seq = list(cur)
                if not seq:
                    return default_color
                cur = seq[0]
                continue
            except:
                pass

        # Optional string support: "r,g,b"
        if isinstance(cur, str):
            try:
                parts = [int(float(p.strip())) for p in cur.split(",")]
                if len(parts) >= 3:
                    return sd.Color.FromArgb(parts[0], parts[1], parts[2])
            except:
                pass

        return default_color

    return default_color

def _to_color(x, r_def, g_def, b_def):
    return _coerce_color(x, sd.Color.FromArgb(r_def, g_def, b_def))

try:    _sol_breps  = _to_brep_list(solid_breps)
except: _sol_breps  = []

try:    _glz_breps  = _to_brep_list(glazing_breps)
except: _glz_breps  = []

try:
    _sol_raw_items = _flatten_values(solid_breps)
except:
    _sol_raw_items = []

try:
    _glz_raw_items = _flatten_values(glazing_breps)
except:
    _glz_raw_items = []

def _types_preview(items, n=4):
    names = []
    for it in items[:n]:
        try:
            names.append(type(_unwrap_gh_value(it)).__name__)
        except:
            names.append(type(it).__name__)
    return ", ".join(names) if names else "none"

try:    _sol_col    = _to_color(solid_color,    30, 120, 200)  # default blue
except: _sol_col    = _DEF_SOL_COL

try:    _glz_col    = _to_color(glazing_color,  20, 180, 120)  # default teal
except: _glz_col    = _DEF_GLZ_COL

# Final guard: ensure colors are valid even if upstream produced nested lists.
_sol_col = _coerce_color(_sol_col, _DEF_SOL_COL)
_glz_col = _coerce_color(_glz_col, _DEF_GLZ_COL)

try:    _mesh_in    = _to_mesh(mesh)
except: _mesh_in    = None

try:    _sun  = [float(sun_vec.X), float(sun_vec.Y), float(sun_vec.Z)] \
                if sun_vec else [0.5, 0.7, 0.5]
except: _sun  = [0.5, 0.7, 0.5]

try:    _fid  = str(facade_id) if facade_id else "facade_01"
except: _fid  = "facade_01"

try:    _run  = bool(run)
except: _run  = False


# ── Helpers ────────────────────────────────────────────────────────────────────
def color_to_mat(c):
    """System.Drawing.Color → venustameter material dict."""
    c = _coerce_color(c, _DEF_SOL_COL)
    return {
        "r": round(c.R / 255.0, 4),
        "g": round(c.G / 255.0, 4),
        "b": round(c.B / 255.0, 4),
    }

def embed_color(brep, role, color):
    """Embed vm_role and colour into a Brep's UserStrings."""
    color = _coerce_color(color, _DEF_SOL_COL if role == "solid" else _DEF_GLZ_COL)
    brep.SetUserString("vm_role",    role)
    brep.SetUserString("vm_color_r", str(color.R))
    brep.SetUserString("vm_color_g", str(color.G))
    brep.SetUserString("vm_color_b", str(color.B))
    return brep

def mesh_from_breps(brep_list):
    """Create a combined mesh from a list of Breps."""
    mp = rg.MeshingParameters()
    mp.MaximumEdgeLength = 0.25
    mp.SimplePlanes      = True
    mp.Tolerance         = 0.001
    combined = rg.Mesh()
    for br in brep_list:
        ms = rg.Mesh.CreateFromBrep(br, mp)
        if ms:
            for m in ms: combined.Append(m)
    if combined.Vertices.Count > 0:
        combined.Weld(math.pi)
        combined.RebuildNormals()
    return combined

def subtract_openings_from_solids(solid_breps, opening_breps):
    """Boolean-subtract opening breps from solids; fallback to original solids on failure."""
    if not solid_breps:
        return []
    if not opening_breps:
        return list(solid_breps)

    tol = 0.01
    try:
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc:
            tol = float(doc.ModelAbsoluteTolerance)
    except:
        pass

    carved = []
    for s in solid_breps:
        try:
            diff = rg.Brep.CreateBooleanDifference(s, opening_breps, tol)
            if diff and len(diff) > 0:
                carved.extend([b for b in diff if b and b.IsValid])
            else:
                carved.append(s)
        except:
            carved.append(s)

    return carved

def color_mesh_vertices(mesh, color):
    """Apply a flat color to all vertices of a mesh."""
    color = _coerce_color(color, _DEF_SOL_COL)
    mesh.VertexColors.Clear()
    for _ in range(mesh.Vertices.Count):
        mesh.VertexColors.Add(color)

def extract_faces(brep_list, role, color, facade_plane_y):
    """
    Extract per-face records from a list of Breps.
    Returns (face_records, opening_records_if_glazing, breps_with_metadata)
    """
    color = _coerce_color(color, _DEF_SOL_COL if role == "solid" else _DEF_GLZ_COL)
    mat = color_to_mat(color)
    is_glazing = (role == "glass")
    faces    = []
    openings = []
    out_breps = []

    for br in brep_list:
        b2 = br.DuplicateBrep()
        embed_color(b2, role, color)
        out_breps.append(b2)

        for fi in range(br.Faces.Count):
            fc = br.Faces[fi]
            u  = (fc.Domain(0).Min + fc.Domain(0).Max) * 0.5
            v  = (fc.Domain(1).Min + fc.Domain(1).Max) * 0.5
            n  = fc.NormalAt(u, v)
            if not n.Unitize(): continue
            am = rg.AreaMassProperties.Compute(
                fc.ToBrep(), True, False, False, False)
            if not am: continue

            c  = am.Centroid
            a  = float(am.Area)
            d  = abs(c.Y - facade_plane_y)

            faces.append({
                "centroid":         [round(c.X,4), round(c.Y,4), round(c.Z,4)],
                "normal":           [round(n.X,4), round(n.Y,4), round(n.Z,4)],
                "area":             round(a, 5),
                "material":         mat,
                "depth_from_plane": round(d, 4),
                "is_opening":       is_glazing,
            })

            # Glazing faces with area > 0.05 m² → openings list
            if is_glazing and a > 0.05:
                bb = fc.ToBrep().GetBoundingBox(True)
                openings.append({
                    "centroid":     [round(c.X,4), round(c.Y,4), round(c.Z,4)],
                    "reveal_depth": round(d, 4),
                    "width":        round(abs(bb.Max.X - bb.Min.X), 4),
                    "height":       round(abs(bb.Max.Z - bb.Min.Z), 4),
                    "material":     mat,
                })

    return faces, openings, out_breps


# ── Main ───────────────────────────────────────────────────────────────────────
if not _run:
    report = "Set run = True"

elif not _sol_breps and not _glz_breps:
    report = "ERROR: No breps connected.\nConnect solid_breps and/or glazing_breps."

else:
    try:

        carved_solids = subtract_openings_from_solids(_sol_breps, _glz_breps)
        all_breps = carved_solids + _glz_breps

        # ── [1] Global bounding box ────────────────────────────────────────────
        all_bb = [b.GetBoundingBox(True) for b in all_breps]
        bb_min = [min(b.Min.X for b in all_bb),
                  min(b.Min.Y for b in all_bb),
                  min(b.Min.Z for b in all_bb)]
        bb_max = [max(b.Max.X for b in all_bb),
                  max(b.Max.Y for b in all_bb),
                  max(b.Max.Z for b in all_bb)]

        # ── [2] Facade reference plane ─────────────────────────────────────────
        # The "back" of the facade = minimum Y extent across all breps.
        # depth_from_plane = how far each face projects forward from there.
        facade_plane_y = bb_min[1]

        # ── [3] Extract faces from solid + glazing ─────────────────────────────
        sol_faces, _,           sol_breps_out = extract_faces(
            carved_solids, "solid",  _sol_col, facade_plane_y)

        glz_faces, glz_openings, glz_breps_out = extract_faces(
            _glz_breps, "glass",  _glz_col, facade_plane_y)

        all_face_records     = sol_faces + glz_faces
        all_opening_records  = glz_openings
        breps_out            = sol_breps_out + glz_breps_out

        # ── [4] Build combined display mesh ────────────────────────────────────
        display_mesh = rg.Mesh()
        # Optional external mesh can be shown too, but never replaces facade geometry.
        if _mesh_in and _mesh_in.Vertices.Count > 0:
            display_mesh.Append(_mesh_in.DuplicateMesh())
        # Solid mesh (carved by glazing)
        if carved_solids:
            sm = mesh_from_breps(carved_solids)
            if sm.Vertices.Count > 0:
                color_mesh_vertices(sm, _sol_col)
                display_mesh.Append(sm)
        # Glazing mesh
        if _glz_breps:
            gm = mesh_from_breps(_glz_breps)
            if gm.Vertices.Count > 0:
                color_mesh_vertices(gm, _glz_col)
                display_mesh.Append(gm)

        if display_mesh.Vertices.Count > 0:
            display_mesh.RebuildNormals()
            mesh_out = display_mesh
        else:
            mesh_out = None

        # ── [5] Edge extraction from combined mesh ─────────────────────────────
        edge_records = []
        edge_mesh = mesh_out if mesh_out else (
            mesh_from_breps(all_breps) if all_breps else None)

        if edge_mesh and edge_mesh.Vertices.Count > 0:
            topo = edge_mesh.TopologyEdges
            for ei in range(topo.Count):
                if len(topo.GetConnectedFaces(ei)) >= 1:   # ALL edges
                    ln = topo.EdgeLine(ei)
                    edge_records.append({
                        "start": [round(ln.From.X,4),
                                  round(ln.From.Y,4),
                                  round(ln.From.Z,4)],
                        "end":   [round(ln.To.X,4),
                                  round(ln.To.Y,4),
                                  round(ln.To.Z,4)],
                    })

        # ── [6] Build geo_json ─────────────────────────────────────────────────
        geo_json = json.dumps({
            "facade_id":    _fid,
            "bounding_box": {"min": bb_min, "max": bb_max},
            "sun_vector":   [round(x,4) for x in _sun],
            "faces":        all_face_records,
            "edges":        edge_records,
            "openings":     all_opening_records,
        })

        # ── [7] Report ─────────────────────────────────────────────────────────
        d_vals = [f["depth_from_plane"] for f in all_face_records]
        d_max  = max(d_vals) if d_vals else 0.0
        d_mean = sum(d_vals) / len(d_vals) if d_vals else 0.0

        report = "\n".join([
            "VenustaMeter — Brep Bridge v2",
            "=" * 42,
            f"  Facade ID:      {_fid}",
            "",
            "  Input parse diagnostics:",
            f"    solid raw:    {len(_sol_raw_items)} ({_types_preview(_sol_raw_items)})",
            f"    glazing raw:  {len(_glz_raw_items)} ({_types_preview(_glz_raw_items)})",
            f"    solid breps:  {len(_sol_breps)}",
            f"    glazing breps:{len(_glz_breps)}",
            f"    carved solids:{len(carved_solids)}",
            "",
            "  SOLID geometry:",
            f"    Breps:        {len(carved_solids)}",
            f"    Faces:        {len(sol_faces)}",
            f"    Colour:       RGB({_sol_col.R},{_sol_col.G},{_sol_col.B})",
            "",
            "  GLAZING geometry:",
            f"    Breps:        {len(_glz_breps)}",
            f"    Faces:        {len(glz_faces)}",
            f"    Openings:     {len(glz_openings)}",
            f"    Colour:       RGB({_glz_col.R},{_glz_col.G},{_glz_col.B})",
            "",
            "  Combined:",
            f"    Total faces:  {len(all_face_records)}",
            f"    Total edges:  {len(edge_records)}",
            f"    Facade ref Y: {facade_plane_y:.4f}",
            f"    Max depth:    {d_max:.4f}",
            f"    Mean depth:   {d_mean:.4f}",
            f"    geo_json:     {len(geo_json)} chars",
            "",
            "  Bounding box:",
            f"    X: {bb_min[0]:.2f} → {bb_max[0]:.2f}",
            f"    Y: {bb_min[1]:.2f} → {bb_max[1]:.2f}",
            f"    Z: {bb_min[2]:.2f} → {bb_max[2]:.2f}",
            "",
            "  ✓ Connect 'geo_json' → venustameter geo_dict",
            "  ✓ Connect 'breps_out' → preview (shows roles)",
            "  ✓ Connect 'mesh_out'  → preview (shows colours)",
        ])

    except Exception as e:
        import traceback
        geo_json  = "{}"
        breps_out = []
        mesh_out  = None
        report    = "\n".join([
            "ERROR: " + str(e),
            "",
            "Diagnostics:",
            "  type(solid_color):   " + str(type(solid_color)),
            "  type(glazing_color): " + str(type(glazing_color)),
            "  type(_sol_col):      " + str(type(_sol_col)),
            "  type(_glz_col):      " + str(type(_glz_col)),
            "",
            traceback.format_exc(),
        ])