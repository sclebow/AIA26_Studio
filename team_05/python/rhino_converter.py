"""
rhino_converter.py
Pure-Python .3dm → layout JSON converter.
Reads a Rhino 8 file without Rhino being open.

Install once:  pip install rhino3dm
"""

import json
import math
import os
import tempfile
from pathlib import Path

# ── layer keyword → element type ─────────────────────────────────────────────
_LAYER_TYPE_MAP = {
    # ── habitable / residential ──
    "bedroom":    "room",
    "living":     "room",
    "dining":     "room",
    "kitchen":    "room",
    "bathroom":   "room",
    "toilet":     "room",
    "wc":         "room",
    "balcony":    "room",
    "terrace":    "room",
    "pantry":     "room",
    "laundry":    "room",
    "wardrobe":   "room",
    "dressing":   "room",
    # ── staff / auxiliary ──
    "maid":       "room",
    "servant":    "room",
    "driver":     "room",
    "staff":      "room",
    # ── circulation / vertical ──
    "corridor":   "room",
    "lobby":      "room",
    "entrance":   "room",
    "reception":  "room",
    "foyer":      "room",
    "stair":      "room",
    "staircase":  "room",
    "lift":       "room",
    "elevator":   "room",
    "shaft":      "room",
    # ── service / MEP ──
    "mep":        "room",
    "mechanical": "room",
    "electrical": "room",
    "generator":  "room",
    "pump":       "room",
    "plant":      "room",
    "storage":    "room",
    "store":      "room",
    "storage":    "room",
    "utility":    "room",
    "util":       "room",
    "service":    "room",
    # ── amenity ──
    "gym":        "room",
    "spa":        "room",
    "lounge":     "room",
    "prayer":     "room",
    "office":     "room",
    # ── doors ──
    "door":         "door",
    "doors":        "door",
    # ── windows / glazing ──
    "window":       "window",
    "windows":      "window",
    "glazing":      "window",
    "curtain_wall": "window",
    # ── columns / structural posts ──
    "column":       "column",
    "columns":      "column",
    "structural_col": "column",
    "str_col":      "column",
    # ── walls ──
    "wall":         "wall",
    "walls":        "wall",
    "partition":    "wall",
    "parapet":      "wall",
    "ext_wall":     "wall",
    "int_wall":     "wall",
    # ── non-space structure (skipped) ──
    "slab":         "structure",
    "soffit":       "structure",
    "beam":         "structure",
    "truss":        "structure",
}

# ── default construction rates per room category (AED / m²) ──────────────────
_DEFAULT_RATES = {
    # residential
    "bedroom":    1200,
    "living":     1400,
    "dining":     1300,
    "kitchen":    1500,
    "bathroom":   1600,
    "toilet":     1600,
    "wc":         1600,
    "balcony":     900,
    "terrace":     800,
    "pantry":     1000,
    "laundry":     900,
    "wardrobe":    800,
    "dressing":    900,
    # staff
    "maid":       1000,
    "servant":     900,
    "driver":      900,
    "staff":       900,
    # circulation
    "corridor":    800,
    "lobby":      1100,
    "entrance":    900,
    "reception":  1200,
    "foyer":      1000,
    "stair":       600,
    "staircase":   600,
    "lift":        500,
    "elevator":    500,
    "shaft":       300,
    # service / MEP
    "mep":         400,
    "mechanical":  400,
    "electrical":  400,
    "generator":   400,
    "pump":        400,
    "plant":       400,
    "storage":     700,
    "store":       700,
    "utility":     700,
    "util":        700,
    "service":     800,
    # amenity
    "gym":        1300,
    "spa":        1400,
    "lounge":     1200,
    "prayer":     1000,
    "office":     1100,
    # fallback
    "room":       1000,
}

_DEFAULT_FINISHES = {
    "floor":   {"material": "ceramic_tile", "rate": 45},
    "wall":    {"material": "paint",        "rate": 18},
    "ceiling": {"material": "paint",        "rate": 12},
}

_RAMP = [
    {"t": 0.0, "color": "#2E7D32"},
    {"t": 0.5, "color": "#C8A200"},
    {"t": 1.0, "color": "#EF5252"},
]

# ── helpers ───────────────────────────────────────────────────────────────────

_ELEMENT_TYPES = {"door", "window", "column", "wall", "structure"}

def _classify_layer(layer_path: str) -> str:
    lp = layer_path.lower()
    # Pass 1: element types (door/window/column/wall/structure) — longest keyword first
    for kw, typ in sorted(_LAYER_TYPE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if typ in _ELEMENT_TYPES and kw in lp:
            return typ
    # Pass 2: room types — longest keyword first
    for kw, typ in sorted(_LAYER_TYPE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if typ == "room" and kw in lp:
            return typ
    return "unknown"


def _room_category(layer_path: str) -> str:
    lp = layer_path.lower()
    # "room" is a generic fallback — skip it in the keyword scan so layer names
    # like "mep_room" don't match the word "room" before "mep".
    for kw in sorted((k for k in _DEFAULT_RATES if k != "room"), key=len, reverse=True):
        if kw in lp:
            return kw
    return "room"


def _parse_name(name: str) -> dict:
    """F04_404_bedroom_3  →  floor=4, apt_id='404', room_type='bedroom', index='3'"""
    result = {"floor": None, "apt_id": None, "room_type": None, "index": None}
    if not name or not name.upper().startswith("F"):
        return result
    parts = name.split("_")
    if len(parts) < 3:
        return result
    try:
        result["floor"] = int(parts[0][1:])
    except Exception:
        pass
    result["apt_id"]    = parts[1] if len(parts) > 1 else None
    result["room_type"] = "_".join(parts[2:-1]) if len(parts) > 3 else (parts[2] if len(parts) > 2 else None)
    result["index"]     = parts[-1] if len(parts) > 3 else None
    return result


def _heat_color(t: float) -> str:
    """Interpolate ramp stops → hex color string."""
    stops = _RAMP
    if t <= stops[0]["t"]:
        return stops[0]["color"]
    if t >= stops[-1]["t"]:
        return stops[-1]["color"]
    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        if a["t"] <= t <= b["t"]:
            f = (t - a["t"]) / (b["t"] - a["t"])
            def _ch(c): return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            ra, ga, ba = _ch(a["color"])
            rb, gb, bb_ = _ch(b["color"])
            r = int(ra + f * (rb - ra))
            g = int(ga + f * (gb - ga))
            b_ = int(ba + f * (bb_ - ba))
            return f"#{r:02x}{g:02x}{b_:02x}"
    return "#888888"


def _nearest_room_idx(rooms: list, cx: float, cy: float) -> int:
    best, best_d = 0, float("inf")
    for j, rm in enumerate(rooms):
        rc = rm.get("centroid", [0, 0])
        d = math.sqrt((rc[0] - cx) ** 2 + (rc[1] - cy) ** 2)
        if d < best_d:
            best, best_d = j, d
    return best


# ── main converter ────────────────────────────────────────────────────────────

def convert_3dm(file_path: str, project_name: str = None, currency: str = "AED") -> dict:
    """
    Read a .3dm file and return a layout JSON dict compatible with
    the cost copilot (same schema as uploaded layout JSON files).

    Parameters
    ----------
    file_path    : path to .3dm file on disk
    project_name : override project name (default = filename stem)
    currency     : currency code stored in project block (default "AED")
    """
    try:
        import rhino3dm
    except ImportError:
        raise ImportError(
            "rhino3dm is not installed. Run:  pip install rhino3dm"
        )

    f = rhino3dm.File3dm.Read(file_path)
    if f is None:
        raise ValueError(f"rhino3dm could not read: {file_path}")

    project_name = project_name or Path(file_path).stem

    # build layer-index → full path map
    layer_map: dict[int, str] = {}
    for layer in f.Layers:
        layer_map[layer.Index] = layer.FullPath

    rooms_raw:   list[dict] = []
    doors_raw:   list[dict] = []
    windows_raw: list[dict] = []
    columns_raw: list[dict] = []
    walls_raw:   list[dict] = []

    for obj in f.Objects:
        geo  = obj.Geometry
        attr = obj.Attributes

        # only process solid geometry
        if not isinstance(geo, (rhino3dm.Mesh, rhino3dm.Brep, rhino3dm.Extrusion)):
            continue

        name       = attr.Name or ""
        layer_path = layer_map.get(attr.LayerIndex, "")
        el_type    = _classify_layer(layer_path)

        try:
            bb = geo.GetBoundingBox()
            mn, mx = bb.Min, bb.Max
        except Exception:
            continue

        w  = round(mx.X - mn.X, 3)
        d  = round(mx.Y - mn.Y, 3)
        h  = round(mx.Z - mn.Z, 3)
        cx = round((mn.X + mx.X) / 2, 3)
        cy = round((mn.Y + mx.Y) / 2, 3)
        area_m2      = round(w * d, 4)          # footprint (XY plane)
        face_area_m2 = round(max(w, d) * h, 4)  # largest vertical face (for walls/doors/windows)

        parsed = _parse_name(name)

        record = {
            "name":          name,
            "layer":         layer_path,
            "floor":         parsed["floor"],
            "apt_id":        parsed["apt_id"],
            "room_type":     parsed["room_type"],
            "centroid":      [cx, cy],
            "size_m":        {"width": w, "depth": d, "height": h},
            "footprint_m2":  area_m2,
            "face_area_m2":  face_area_m2,
            "polygon": [
                [round(mn.X, 3), round(mn.Y, 3)],
                [round(mx.X, 3), round(mn.Y, 3)],
                [round(mx.X, 3), round(mx.Y, 3)],
                [round(mn.X, 3), round(mx.Y, 3)],
            ],
        }

        if el_type == "room":
            rooms_raw.append(record)
        elif el_type == "door":
            doors_raw.append(record)
        elif el_type == "window":
            windows_raw.append(record)
        elif el_type == "column":
            columns_raw.append(record)
        elif el_type == "wall":
            walls_raw.append(record)

    if not rooms_raw:
        raise ValueError(
            "No room objects found. Check layer names contain keywords: "
            "bedroom / living / dining / corridor / bathroom / kitchen / "
            "balcony / storage / lobby / service / util"
        )

    # ── build cost-schema room objects ────────────────────────────────────────
    rooms_out: list[dict] = []
    all_costs: list[float] = []

    for i, r in enumerate(rooms_raw):
        cat   = _room_category(r["layer"])
        rate  = _DEFAULT_RATES.get(cat, 1000)
        area  = r["footprint_m2"]
        total = round(rate * area, 2)
        all_costs.append(total)

        rooms_out.append({
            "id":         f"room_{i + 1:03d}",
            "name":       r["name"] or f"{cat.title()} {i + 1}",
            "category":   cat,
            "floor":      r["floor"],
            "apt_id":     r.get("apt_id"),
            "area_m2":    area,
            "rate_per_m2": rate,
            "total_cost": total,
            "centroid":   r["centroid"],
            "polygon":    r["polygon"],
            "size_m":     r["size_m"],
            "finishes": {
                "floor":   dict(_DEFAULT_FINISHES["floor"]),
                "wall":    dict(_DEFAULT_FINISHES["wall"]),
                "ceiling": dict(_DEFAULT_FINISHES["ceiling"]),
            },
            "heatmap":  {"heat_t": 0.0, "color_hex": "#2E7D32"},
            "doors":    [],
            "windows":  [],
            "columns":  [],
            "walls":    [],
        })

    # ── assign doors / windows / columns / walls to nearest room ─────────────
    for dobj in doors_raw:
        idx = _nearest_room_idx(rooms_out, dobj["centroid"][0], dobj["centroid"][1])
        rooms_out[idx]["doors"].append({
            "id":          dobj["name"],
            "layer":       dobj["layer"],
            "width_m":     dobj["size_m"]["width"],
            "height_m":    dobj["size_m"]["height"],
            "face_area_m2": dobj["face_area_m2"],
            "cost":        round(dobj["face_area_m2"] * 400, 2),   # AED 400/m² face area
        })

    for wobj in windows_raw:
        idx = _nearest_room_idx(rooms_out, wobj["centroid"][0], wobj["centroid"][1])
        rooms_out[idx]["windows"].append({
            "id":          wobj["name"],
            "layer":       wobj["layer"],
            "width_m":     wobj["size_m"]["width"],
            "height_m":    wobj["size_m"]["height"],
            "face_area_m2": wobj["face_area_m2"],
            "cost":        round(wobj["face_area_m2"] * 600, 2),   # AED 600/m² face area
        })

    for cobj in columns_raw:
        idx = _nearest_room_idx(rooms_out, cobj["centroid"][0], cobj["centroid"][1])
        rooms_out[idx]["columns"].append({
            "id":            cobj["name"],
            "layer":         cobj["layer"],
            "width_m":       cobj["size_m"]["width"],
            "depth_m":       cobj["size_m"]["depth"],
            "height_m":      cobj["size_m"]["height"],
            "footprint_m2":  cobj["footprint_m2"],
            "cost":          round(cobj["footprint_m2"] * 800, 2),  # AED 800/m² footprint
        })

    for walobj in walls_raw:
        idx = _nearest_room_idx(rooms_out, walobj["centroid"][0], walobj["centroid"][1])
        rooms_out[idx]["walls"].append({
            "id":          walobj["name"],
            "layer":       walobj["layer"],
            "length_m":    max(walobj["size_m"]["width"], walobj["size_m"]["depth"]),
            "thickness_m": min(walobj["size_m"]["width"], walobj["size_m"]["depth"]),
            "height_m":    walobj["size_m"]["height"],
            "face_area_m2": walobj["face_area_m2"],
            "cost":        round(walobj["face_area_m2"] * 350, 2),  # AED 350/m² face area
        })

    # ── recompute heatmap across all rooms ────────────────────────────────────
    if all_costs:
        min_c = min(all_costs)
        max_c = max(all_costs)
        span  = max_c - min_c if max_c > min_c else 1.0
        for rm in rooms_out:
            t = round((rm["total_cost"] - min_c) / span, 4)
            rm["heatmap"] = {
                "heat_t":    t,
                "color_hex": _heat_color(t),
                "min_cost":  min_c,
                "max_cost":  max_c,
                "ramp_stops": _RAMP,
            }

    # ── totals ────────────────────────────────────────────────────────────────
    rooms_total   = round(sum(rm["total_cost"] for rm in rooms_out), 2)
    doors_total   = round(sum(d.get("cost", 0) for rm in rooms_out for d in rm["doors"]), 2)
    windows_total = round(sum(w.get("cost", 0) for rm in rooms_out for w in rm["windows"]), 2)
    columns_total = round(sum(c.get("cost", 0) for rm in rooms_out for c in rm["columns"]), 2)
    walls_total   = round(sum(w.get("cost", 0) for rm in rooms_out for w in rm["walls"]), 2)
    grand         = round(rooms_total + doors_total + windows_total + columns_total + walls_total, 2)

    return {
        "project": {
            "name":     project_name,
            "currency": currency,
            "source":   "rhino_3dm",
            "floors":   sorted({r["floor"] for r in rooms_out if r["floor"] is not None}),
        },
        "rooms":   rooms_out,
        "totals": {
            "rooms":   rooms_total,
            "doors":   doors_total,
            "windows": windows_total,
            "columns": columns_total,
            "walls":   walls_total,
            "grand":   grand,
        },
        "heatmap_ramp": _RAMP,
    }


def convert_3dm_bytes(
    data: bytes,
    filename: str = "upload.3dm",
    project_name: str = None,
    currency: str = "AED",
) -> dict:
    """
    Convert from raw bytes (e.g. Streamlit UploadedFile.read()).
    Writes to a temp file, converts, then cleans up.
    """
    with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return convert_3dm(
            tmp_path,
            project_name=project_name or Path(filename).stem,
            currency=currency,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
